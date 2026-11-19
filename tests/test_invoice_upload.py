"""Upload -> real ORM persistence/report -> real MCP RAG -> query.
SQLite is a disposable test substitute for PostgreSQL. Provider, vector-store
and non-RAG A2A boundaries are controlled; production code paths are reused.
"""
import io
import re
import socket
import sys
import time
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from threading import Thread
from types import SimpleNamespace
from uuid import UUID

import pytest
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from fastapi import FastAPI
from fastapi.testclient import TestClient
from docx import Document
import uvicorn

from invoice_auditor.api import invoice_api, query_api
from invoice_auditor.db.base import Base
from invoice_auditor.models import InvoiceAudit, InvoiceLineItem
from invoice_auditor.services import ingestion_service as ingest
from invoice_auditor.services.invoice_audit_service import save_translation
from invoice_auditor.workflows import invoice_workflow as flow, rag_workflow
from invoice_auditor.agents import reporting_agent, validation_agent, invoice_monitor_agent, business_validation_agent as business
from invoice_auditor.agents.Invoice_Extractor_Agent import extraction_service
from invoice_auditor.agents.Invoice_RAG_Agent.pipeline import indexing_agent, retrieval_agent, augmentation_agent, generation_agent, reflection_agent
from invoice_auditor.agents.Invoice_RAG_Agent.mcp_tool_server.main import create_mcp_server

@compiles(JSONB, "sqlite")
def sqlite_jsonb(type_, compiler, **kwargs):
    return "JSON"

@compiles(sa.BigInteger, "sqlite")
def sqlite_bigint(type_, compiler, **kwargs):
    return "INTEGER"

TEXT = """Example Logistics
Invoice Number: INV-UP-1001
Invoice Date: 2026-11-20
PO Number: PO-UP-1
Currency: USD
SKU-1 | Freight service | 2 | 10.00 | 20.00
Subtotal: 20.00
Tax (10%): 2.00
Total: 22.00
"""

def docx_bytes(text=TEXT):
    document = Document()
    for line in text.splitlines(): document.add_paragraph(line)
    stream = io.BytesIO()
    document.save(stream)
    return stream.getvalue()

@pytest.fixture
def upload_runtime(tmp_path, monkeypatch):
    engine = sa.create_engine("sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})
    @sa.event.listens_for(engine, "connect")
    def attach(connection, _):
        connection.execute("ATTACH DATABASE ? AS audit", (str(tmp_path / "audit.sqlite"),))
        connection.create_function("NOW", 0, lambda: datetime.now(timezone.utc).isoformat(" "))
    # Copy metadata so PostgreSQL models/defaults remain unchanged.
    metadata = sa.MetaData()
    for table in Base.metadata.sorted_tables: table.to_metadata(metadata)
    for table in metadata.tables.values():
        for column in table.columns:
            if column.server_default and "::jsonb" in str(column.server_default.arg):
                column.server_default = sa.DefaultClause(sa.text("'{}'"))
    metadata.create_all(engine)
    sessions = sessionmaker(engine)
    incoming = tmp_path / "incoming"
    incoming.mkdir()
    reports = tmp_path / "reports"
    monkeypatch.setenv("REPORT_OUTPUT_DIR", str(reports))
    for module in (ingest, invoice_api, flow, reporting_agent, indexing_agent, augmentation_agent, invoice_monitor_agent):
        monkeypatch.setattr(module, "SessionLocal", sessions)
    monkeypatch.setattr(invoice_api, "INCOMING_DIR", incoming)
    monkeypatch.setattr(extraction_service, "INCOMING_DIR", incoming)
    monkeypatch.setattr(invoice_monitor_agent, "INCOMING_DIR", incoming)
    counters = {"extract": 0}
    def extract(path):
        counters["extract"] += 1
        text, method = extraction_service.extract_document(Path(path))
        return {"raw_extracted_text": text, "extraction_method": method}
    def translate(invoice_id, raw_extracted_text):
        with sessions() as db:
            save_translation(db, UUID(invoice_id), source_language="en",
                             translated_text=raw_extracted_text, confidence=1.0)
        return dict(translation_status="completed", source_language="en", translated_text=raw_extracted_text, translation_confidence=1.0)
    def validate(invoice, translation_confidence=None):
        return validation_agent.invoice_validation_graph.invoke({"invoice": invoice, "translation_confidence": translation_confidence})
    def business_check(invoice):
        state = {"invoice": invoice}
        state.update(business.load_rules_node(state))
        state.update(business.fetch_erp_data_node(state))
        state.update(business.compare_business_rules_node(state))
        return state
    def erp(url):
        if "/po/" in url:
            return {"po_number": "PO-UP-1", "vendor_id": "V-1", "currency": "USD",
                    "line_items": [{"item_code": "SKU-1", "description": "Freight service", "quantity": 2, "unit_price": 10, "currency": "USD"}]}
        if "/vendor/" in url: return {"vendor_id": "V-1", "vendor_name": "Example Logistics", "name": "Example Logistics"}
        return {"item_code": "SKU-1", "description": "Freight service", "unit_price": 10, "currency": "USD"}
    monkeypatch.setattr(business, "get_json", erp)
    monkeypatch.setattr(flow, "extract_invoice_via_a2a", extract)
    monkeypatch.setattr(flow, "translate_invoice_via_a2a", translate)
    monkeypatch.setattr(flow, "validate_invoice_via_a2a", validate)
    monkeypatch.setattr(flow, "validate_business_invoice_via_a2a", business_check)
    monkeypatch.setattr(flow, "generate_invoice_report_via_a2a", reporting_agent.reporting_graph.invoke)
    # An uploaded invoice must not invoke the directory scan/claim other files.
    monkeypatch.setattr(flow, "scan_invoices_via_a2a", lambda *_: pytest.fail("Upload scanned unrelated invoices"))
    vectors = []
    def index_text(**kwargs):
        vectors.append(dict(invoice_id=kwargs["invoice_id"], source_type=kwargs["source_type"],
                            chunk_text=kwargs["text"], score=0.95))
        return 1
    def clear(invoice_id):
        vectors[:] = [point for point in vectors if point["invoice_id"] != invoice_id]
    monkeypatch.setattr(indexing_agent, "index_text", index_text)
    monkeypatch.setattr(indexing_agent, "reindex_invoice", clear)
    monkeypatch.setattr(retrieval_agent, "retrieve", lambda query, top_k, invoice_id=None: [
        dict(point) for point in vectors if not invoice_id or point["invoice_id"] == invoice_id][:top_k])
    class Cache:
        def get(self, key): return None
        def set(self, *args, **kwargs): pass
    monkeypatch.setattr(generation_agent, "redis_client", Cache())
    def synth(messages):
        source = re.search(r"invoice_id=([0-9a-f-]{36})", messages[-1][1])[1]
        return SimpleNamespace(content="The uploaded invoice total is USD 22.00. Source: " + source)
    monkeypatch.setattr(generation_agent, "ChatLiteLLM", lambda **_: SimpleNamespace(invoke=synth))
    monkeypatch.setattr(reflection_agent, "ChatLiteLLM", lambda **_: SimpleNamespace(invoke=lambda _: SimpleNamespace(content='{"answer_relevance":0.95,"groundedness":0.95,"context_relevance":0.95}')))
    monkeypatch.setattr(rag_workflow, "input_guardrail_graph", SimpleNamespace(invoke=lambda _: {"is_safe": True}))
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    server = uvicorn.Server(uvicorn.Config(create_mcp_server().streamable_http_app(), log_level="critical"))
    thread = Thread(target=server.run, kwargs={"sockets": [listener]}, daemon=True)
    thread.start()
    for _ in range(100):
        if server.started: break
        time.sleep(0.05)
    assert server.started
    monkeypatch.setenv("RAG_MCP_URL", f"http://127.0.0.1:{listener.getsockname()[1]}/mcp")
    application = FastAPI()
    application.include_router(invoice_api.router)
    application.include_router(query_api.router)
    with TestClient(application) as client:
        yield SimpleNamespace(client=client, sessions=sessions, incoming=incoming,
                              reports=reports, vectors=vectors, counters=counters, index_text=index_text)
    server.should_exit = True
    thread.join(timeout=5)
    listener.close()
    engine.dispose()

MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
def upload(runtime, content=None, name="invoice.docx", mime=MIME):
    return runtime.client.post("/api/v1/invoices/upload", files={"file": (name, docx_bytes() if content is None else content, mime)})

def test_upload_persists_full_invoice_and_answers_via_rag(upload_runtime):
    runtime = upload_runtime
    response = upload(runtime)
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["stored"] and result["persisted"] and result["rag_ready"], result
    assert result["report_status"] == "completed" and result["index_status"] == "completed"
    invoice_id = UUID(result["invoice_id"])
    with runtime.sessions() as db:
        record = db.get(InvoiceAudit, invoice_id)
        assert record.invoice_number == "INV-UP-1001"
        assert record.currency == "USD" and record.total_amount == Decimal("22")
        assert record.raw_extracted_text.strip() == TEXT.strip()
        assert record.translated_text.strip() == TEXT.strip()
        assert record.extracted_raw["original_filename"] == "invoice.docx"
        assert record.extracted_raw["validation"]
        assert record.extracted_raw["report"]
        assert record.extracted_raw["indexing"]["index_status"] == "completed"
        assert db.scalar(sa.select(sa.func.count()).select_from(InvoiceLineItem)) == 1
        assert Path(record.file_path).is_file()
    assert list(runtime.reports.glob("*.json")) and list(runtime.reports.glob("*.html"))
    assert runtime.vectors and all(p["invoice_id"] == str(invoice_id) for p in runtime.vectors)
    query = runtime.client.post("/api/v1/query", json={"question": "What is the total amount on this invoice?", "invoice_id": str(invoice_id)})
    assert query.status_code == 200, query.text
    assert query.json()["status"] == "completed", query.json()
    assert "22.00" in query.json()["answer"] and str(invoice_id) in query.json()["answer"]
    assert query.json()["average_score"] > 0.7
    assert runtime.client.get(f"/api/v1/invoices/{invoice_id}/status").json()["rag_ready"]

def test_same_file_renamed_is_not_processed_twice(upload_runtime):
    runtime = upload_runtime
    content = docx_bytes()
    first = upload(runtime, content).json()
    second = upload(runtime, content, name="renamed.docx").json()
    assert first["invoice_id"] == second["invoice_id"]
    assert second["duplicate"] and second["rag_ready"]
    assert runtime.counters["extract"] == 1
    with runtime.sessions() as db:
        assert db.scalar(sa.select(sa.func.count()).select_from(InvoiceAudit)) == 1
    assert len(list(runtime.incoming.iterdir())) == 1
    scanned = invoice_monitor_agent.invoice_monitor_graph.invoke({"incoming_dir": str(runtime.incoming)})
    assert not scanned["pending_invoices"] and scanned["duplicate_files"]


@pytest.mark.parametrize("name,content,mime,status", [
    ("../invoice.docx", b"bad", MIME, 400),
    ("invoice.exe", b"bad", "application/octet-stream", 415),
    ("invoice.pdf", b"forged", "application/pdf", 422),
    ("invoice.docx", b"", MIME, 422),
    ("invoice.docx", b"bad", "text/plain", 415),
])
def test_bad_upload_never_persists_or_publishes(upload_runtime, name, content, mime, status):
    runtime = upload_runtime
    response = upload(runtime, content, name, mime)
    assert response.status_code == status, response.text
    assert not list(runtime.incoming.iterdir())
    with runtime.sessions() as db:
        assert db.scalar(sa.select(sa.func.count()).select_from(InvoiceAudit)) == 0

def test_upload_size_limit_cleans_staging(upload_runtime, monkeypatch):
    monkeypatch.setattr(ingest, "MAX_UPLOAD_BYTES", 10)
    response = upload(upload_runtime, b"x" * 11)
    assert response.status_code == 413
    assert not list(upload_runtime.incoming.iterdir())

def test_failed_index_retains_evidence_and_can_retry_without_ocr(upload_runtime, monkeypatch):
    runtime = upload_runtime
    def fail(**kwargs): raise ConnectionError("vector storage unavailable")
    monkeypatch.setattr(indexing_agent, "index_text", fail)
    result = upload(runtime).json()
    assert result["stored"] and result["persisted"]
    assert not result["rag_ready"] and result["index_status"] == "failed", result
    assert result["report_status"] == "completed"
    monkeypatch.setattr(indexing_agent, "index_text", runtime.index_text)
    response = runtime.client.post(f"/api/v1/invoices/{result['invoice_id']}/reindex")
    assert response.status_code == 200, response.text
    assert response.json()["rag_ready"], response.json()
    assert runtime.counters["extract"] == 1
    with runtime.sessions() as db:
        assert db.get(InvoiceAudit, UUID(result["invoice_id"])).extracted_raw["report"]

def test_extraction_failure_is_audited_not_reported_ready(upload_runtime, monkeypatch):
    def fail(path): raise RuntimeError("OCR service unavailable")
    monkeypatch.setattr(flow, "extract_invoice_via_a2a", fail)
    result = upload(upload_runtime).json()
    assert result["stored"] and result["persisted"]
    assert result["processing_status"] == "failed" and not result["rag_ready"]
    assert upload_runtime.client.post(f"/api/v1/invoices/{result['invoice_id']}/reindex").status_code == 409
    with upload_runtime.sessions() as db:
        assert db.get(InvoiceAudit, UUID(result["invoice_id"])).processing_error


def test_existing_drop_folder_workflow_still_processes_invoices(upload_runtime, monkeypatch):
    from invoice_auditor.agents.Invoice_Monitoring_Agent.monitoring_service import prepare_monitoring_response
    runtime = upload_runtime
    (runtime.incoming / "dropped.docx").write_bytes(docx_bytes())
    def scan(directory):
        return prepare_monitoring_response(invoice_monitor_agent.invoice_monitor_graph.invoke({"incoming_dir": directory}))
    monkeypatch.setattr(flow, "scan_invoices_via_a2a", scan)
    result = flow.invoice_audit_graph.invoke({"incoming_dir": str(runtime.incoming)})
    assert len(result["extraction_results"]) == 1
    item = result["extraction_results"][0]
    assert item["status"] == "extracted" and item["report_status"] == "completed"
    assert ingest.get_receipt(item["invoice_id"])["rag_ready"]

def test_database_failure_does_not_publish_or_claim_persistence(upload_runtime, monkeypatch):
    def unavailable(): raise ConnectionError("database unavailable")
    monkeypatch.setattr(ingest, "SessionLocal", unavailable)
    response = upload(upload_runtime)
    assert response.status_code == 503
    assert not list(upload_runtime.incoming.iterdir())
