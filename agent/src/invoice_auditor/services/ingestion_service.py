"""Upload admission and registration; processing uses the existing invoice graph."""
import hashlib
import logging
import os
import tempfile
from pathlib import Path
from uuid import uuid4, UUID

from invoice_auditor.db.session import SessionLocal
from invoice_auditor.agents.Invoice_Extractor_Agent.guardrails.file_security import validate_invoice_file
from invoice_auditor.security.content import GuardrailError
from invoice_auditor.services.invoice_audit_service import (
    create_audit_record, find_by_checksum, get_invoice_audit, mark_processing_failed,
)

logger = logging.getLogger(__name__)
MAX_UPLOAD_BYTES = 20 * 1024 * 1024
MIME_TYPES = {
    ".pdf": {"application/pdf"},
    ".png": {"image/png"},
    ".docx": {"application/vnd.openxmlformats-officedocument.wordprocessingml.document", "application/zip"},
}

class UploadError(ValueError):
    def __init__(self, message, status_code=422):
        super().__init__(message)
        self.status_code = status_code

def invoice_receipt(record, *, duplicate=False, filename=None):
    evidence = record.extracted_raw or {}
    indexing = evidence.get("indexing") or {}
    report_done = bool(evidence.get("report"))
    rag_ready = (indexing.get("index_status") == "completed"
                 and int(indexing.get("indexed_chunks") or 0) > 0)
    status = ("completed" if report_done and rag_ready and not record.processing_error
              else "partial" if report_done
              else "failed" if record.processing_error else "processing")
    return {
        "invoice_id": str(record.invoice_id),
        "original_filename": evidence.get("original_filename") or filename or Path(record.file_path).name,
        "duplicate": duplicate,
        "stored": Path(record.file_path).is_file(),
        "persisted": True,
        "processing_status": status,
        "extraction_status": "completed" if record.raw_extracted_text else "not_completed",
        "validation_status": record.validation_status,
        "recommendation": record.recommendation,
        "report_status": "completed" if report_done else "not_completed",
        "index_status": indexing.get("index_status", "not_started"),
        "indexed_chunks": int(indexing.get("indexed_chunks") or 0),
        "rag_ready": rag_ready,
        "error": "Invoice processing did not finish successfully. Review the audit record."
                 if record.processing_error else
                 "RAG indexing is incomplete. The saved audit record is retained."
                 if report_done and not rag_ready else None,
    }

def get_receipt(invoice_id, *, duplicate=False, filename=None):
    with SessionLocal() as db:
        record = get_invoice_audit(db, UUID(str(invoice_id)))
        if record is None:
            raise UploadError("Invoice audit record not found", 404)
        return invoice_receipt(record, duplicate=duplicate, filename=filename)

def ingest_invoice(stream, filename, content_type, incoming_dir, processor):
    if (not isinstance(filename, str) or not filename or len(filename) > 200
        or "/" in filename or "\\" in filename or any(ord(c) < 32 for c in filename)):
        raise UploadError("Provide a plain invoice filename, without a directory", 400)
    suffix = Path(filename).suffix.lower()
    if suffix not in MIME_TYPES:
        raise UploadError("Upload a PDF, DOCX or PNG invoice", 415)
    mime = (content_type or "").split(";")[0].strip().lower()
    if mime and mime != "application/octet-stream" and mime not in MIME_TYPES[suffix]:
        raise UploadError("Content type does not match the invoice file extension", 415)
    root = Path(incoming_dir).resolve()
    stage = None
    invoice_id = None
    try:
        root.mkdir(parents=True, exist_ok=True)
        digest = hashlib.sha256()
        size = 0
        # Hidden staging files are invisible to the polling monitor.
        with tempfile.NamedTemporaryFile(dir=root, prefix=".upload-", suffix=suffix, delete=False) as target:
            stage = Path(target.name)
            while chunk := stream.read(512 * 1024):
                size += len(chunk)
                if size > MAX_UPLOAD_BYTES:
                    raise UploadError("Invoice exceeds the 20 MB upload limit", 413)
                digest.update(chunk)
                target.write(chunk)
        if not size:
            raise UploadError("Invoice file is empty", 422)
        validate_invoice_file(stage, root)
        checksum = digest.hexdigest()
        destination = root / (uuid4().hex + suffix)
        with SessionLocal() as db:
            existing = find_by_checksum(db, checksum)
            if existing is not None:
                return invoice_receipt(existing, duplicate=True, filename=filename)
            invoice_id = create_audit_record(db, str(destination), checksum)
            if invoice_id is None:
                existing = find_by_checksum(db, checksum)
                if existing is None:
                    raise UploadError("Duplicate registration could not be resolved", 409)
                return invoice_receipt(existing, duplicate=True, filename=filename)
            record = get_invoice_audit(db, invoice_id)
            record.extracted_raw = {**(record.extracted_raw or {}), "original_filename": filename}
            db.add(record)
            db.commit()
        # Registration precedes publication: background polling sees a duplicate,
        # while this request owns processing this one registered invoice.
        os.chmod(stage, 0o644)
        os.replace(stage, destination)
        processor({"incoming_dir": str(root), "uploaded_invoice": {
            "invoice_id": str(invoice_id), "file_path": str(destination),
            "file_type": suffix, "checksum": checksum,
            "original_filename": filename, "status": "pending",
        }})
        return get_receipt(invoice_id)
    except GuardrailError as exc:
        raise UploadError(str(exc), 422) from exc
    except UploadError:
        raise
    except Exception as exc:
        logger.exception("Invoice upload/processing failed")
        if invoice_id is not None:
            with SessionLocal() as db:
                mark_processing_failed(db, invoice_id, "Uploaded invoice processing failed")
            return get_receipt(invoice_id)
        raise UploadError("Invoice storage or database is unavailable. Please retry.", 503) from exc
    finally:
        if stage is not None:
            stage.unlink(missing_ok=True)
