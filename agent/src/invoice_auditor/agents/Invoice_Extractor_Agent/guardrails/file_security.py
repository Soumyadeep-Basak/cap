"""Basic invoice file admission before parsing or OCR."""
from pathlib import Path
from zipfile import ZipFile
from invoice_auditor.security.content import GuardrailError

def validate_invoice_file(path, root):
    path = Path(path).resolve()
    if not path.is_relative_to(Path(root).resolve()) or not path.is_file():
        raise GuardrailError("Invoice must be a file within the incoming directory")
    if not 0 < path.stat().st_size <= 20 * 1024 * 1024:
        raise GuardrailError("Invoice is empty or larger than 20 MB")
    try:
        with path.open("rb") as stream:
            magic = stream.read(8)
        if path.suffix.lower() == ".pdf" and magic.startswith(b"%PDF-"):
            import pdfplumber
            with pdfplumber.open(path) as pdf:
                if not 1 <= len(pdf.pages) <= 50:
                    raise GuardrailError("Invoice PDF exceeds 50 pages")
        elif path.suffix.lower() == ".png" and magic == b"\x89PNG\r\n\x1a\n":
            from PIL import Image
            with Image.open(path) as image:
                if image.width * image.height > 25_000_000:
                    raise GuardrailError("Invoice image is too large")
                image.verify()
        elif path.suffix.lower() == ".docx" and magic.startswith(b"PK\x03\x04"):
            with ZipFile(path) as archive:
                if "word/document.xml" not in archive.namelist() or sum(i.file_size for i in archive.infolist()) > 50 * 1024 * 1024:
                    raise GuardrailError("Invalid or oversized DOCX")
        else:
            raise GuardrailError("Only valid PDF, DOCX or PNG invoices are supported")
    except GuardrailError:
        raise
    except Exception as exc:
        raise GuardrailError("Invoice file is malformed or unreadable") from exc
    return path
