"""UI smoke/interaction checks with controlled data and API boundaries."""
import sys
from pathlib import Path
from unittest.mock import Mock
import pytest
from streamlit.testing.v1 import AppTest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "streamlit-ui/src"))
APP = ROOT / "streamlit-ui/src/invoice_auditor_ui/app.py"

def by_label(elements, label):
    return next(element for element in elements if element.label == label)

def test_preview_dashboard_search_and_navigation(monkeypatch):
    monkeypatch.setenv("INVOICE_UI_PREVIEW", "1")
    app = AppTest.from_file(str(APP), default_timeout=30).run()
    assert not app.exception
    assert len(app.dataframe[0].value) == 6
    by_label(app.text_input, "Search invoices").set_value("Meridian").run()
    assert len(app.dataframe[0].value) == 1
    assert app.dataframe[0].value.iloc[0]["vendor_name"] == "Meridian Logistics"
    app.sidebar.radio[0].set_value("Ask a Question").run()
    assert not app.exception
    assert by_label(app.button, "Ask the assistant").disabled
    by_label(app.button, "Which invoices need review?").click().run()
    assert by_label(app.text_area, "What would you like to know?").value == "Which invoices need review?"

def configure_live_boundaries(monkeypatch):
    monkeypatch.setenv("INVOICE_UI_PREVIEW", "0")
    from invoice_auditor_ui import db, preview, agent_client
    for name in ("list_invoices", "get_invoice", "get_line_items", "get_discrepancies", "get_feedback", "get_dashboard_summary"):
        monkeypatch.setattr(db, name, getattr(preview, name))
    monkeypatch.setattr(agent_client, "health_check", lambda: True)
    return agent_client

def test_correction_selector_refreshes_original_and_preserves_api_payload(monkeypatch):
    agent = configure_live_boundaries(monkeypatch)
    submit = Mock(return_value={"status": "recorded"})
    monkeypatch.setattr(agent, "submit_feedback", submit)
    app = AppTest.from_file(str(APP), default_timeout=30).run()
    assert not app.exception
    invoice_id = "00000000-0000-4000-8000-000000000001"
    app.selectbox(key=f"correction_field_{invoice_id}").set_value("total_amount").run()
    assert by_label(app.text_input, "Current extracted value").value == "2480.0"
    by_label(app.text_input, "Corrected value").set_value("2400")
    by_label(app.text_input, "Auditor name / ID").set_value("Test reviewer")
    by_label(app.button, "Submit correction").click().run()
    assert not app.exception
    submit.assert_called_once_with(invoice_id=invoice_id, field_name="total_amount",
                                   corrected_value="2400", corrected_by="Test reviewer",
                                   original_value="2480.0")

def test_assistant_uses_existing_api_and_keeps_answer_on_rerun(monkeypatch):
    agent = configure_live_boundaries(monkeypatch)
    ask = Mock(return_value={"status": "completed", "answer": "Two invoices need review.",
                             "query_type": "structured", "answer_source": "sql"})
    monkeypatch.setattr(agent, "ask_question", ask)
    app = AppTest.from_file(str(APP), default_timeout=30).run()
    app.sidebar.radio[0].set_value("Ask a Question").run()
    by_label(app.text_area, "What would you like to know?").set_value("Which invoices need review?").run()
    by_label(app.button, "Ask the assistant").click().run()
    assert not app.exception
    ask.assert_called_once_with(question="Which invoices need review?", invoice_id=None)
    app.run()
    assert not app.exception
    assert app.session_state["last_query"]["result"]["answer"] == "Two invoices need review."
    assert ask.call_count == 1


def test_upload_ui_submits_file_then_opens_scoped_assistant(monkeypatch):
    from types import SimpleNamespace
    import streamlit as st
    agent = configure_live_boundaries(monkeypatch)
    file = SimpleNamespace(name="new-invoice.docx", size=12, type="application/octet-stream",
                           getvalue=lambda: b"invoicebytes")
    monkeypatch.setattr(st, "file_uploader", lambda *args, **kwargs: file)
    invoice_id = "00000000-0000-4000-8000-000000000002"
    receipt = dict(invoice_id=invoice_id, stored=True, persisted=True, rag_ready=True,
                   report_status="completed", index_status="completed", processing_status="completed",
                   duplicate=False, indexed_chunks=3)
    upload = Mock(return_value=receipt)
    monkeypatch.setattr(agent, "upload_invoice", upload)
    app = AppTest.from_file(str(APP), default_timeout=30).run()
    by_label(app.button, "Upload & process invoice").click().run()
    assert not app.exception
    upload.assert_called_once_with("new-invoice.docx", b"invoicebytes", "application/octet-stream")
    assert app.session_state["upload_receipt"]["rag_ready"]
    assert "Meridian" in app.selectbox(key="selected_invoice").value
    by_label(app.button, "Ask about this invoice").click().run()
    assert not app.exception
    assert app.sidebar.radio[0].value == "Ask a Question"
    assert "INV-2480" in app.selectbox(key="query_scope").value

def test_upload_ui_blocks_oversized_file(monkeypatch):
    from types import SimpleNamespace
    import streamlit as st
    agent = configure_live_boundaries(monkeypatch)
    monkeypatch.setattr(st, "file_uploader", lambda *args, **kwargs: SimpleNamespace(size=21 * 1024 * 1024))
    upload = Mock()
    monkeypatch.setattr(agent, "upload_invoice", upload)
    app = AppTest.from_file(str(APP), default_timeout=30).run()
    assert not app.exception
    assert by_label(app.button, "Upload & process invoice").disabled
    upload.assert_not_called()

def test_upload_client_uses_multipart_and_processing_timeout(monkeypatch):
    from invoice_auditor_ui import agent_client
    import httpx
    request = Mock(return_value=httpx.Response(200, json={"invoice_id": "test-id"}))
    monkeypatch.setattr(agent_client.httpx, "request", request)
    assert agent_client.upload_invoice("invoice.pdf", b"pdf", "application/pdf")["invoice_id"] == "test-id"
    args, kwargs = request.call_args
    assert args[0] == "POST" and args[1].endswith("/api/v1/invoices/upload")
    assert kwargs["files"] == {"file": ("invoice.pdf", b"pdf", "application/pdf")}
    assert kwargs["timeout"].read == 600
