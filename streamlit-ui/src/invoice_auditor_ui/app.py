"""AI Invoice Auditor -- human-in-the-loop Streamlit dashboard.

Lets a non-technical auditor review processed invoice reports and
discrepancies, correct extracted values, request revalidation, and ask
natural-language questions about processed invoices. All mutations
(feedback, revalidation, querying) are delegated to the Agent API; the
dashboard only reads audit data directly from PostgreSQL.
"""

from __future__ import annotations

import re
import inspect
import os
import json
from html import escape
from datetime import datetime
from zoneinfo import ZoneInfo
import sqlalchemy as sa

import streamlit as st

from invoice_auditor_ui import agent_client, db
from invoice_auditor_ui.theme import inject_theme, section, chip

PREVIEW = os.getenv('INVOICE_UI_PREVIEW', '0') == '1'
if PREVIEW:
    from invoice_auditor_ui import preview as db

st.set_page_config(
    page_title="auditflow | Invoice intelligence",
    page_icon=":material/receipt_long:",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Header fields an auditor may correct. Must match the keys the
# revalidation workflow recognizes on the extracted invoice (see
# agent's workflows/revalidation.py: apply_corrections).
CORRECTABLE_FIELDS = [
    "invoice_number",
    "invoice_date",
    "vendor_name",
    "po_number",
    "currency",
    "total_amount",
    "subtotal_amount",
    "tax_amount",
    "tax_rate",
]

inject_theme()


def _badge(label: str) -> str:
    labels = {"approve": "Approved", "review": "Needs review", "manual_review": "Needs review",
              "reject": "Rejected", "passed": "Passed", "failed": "Failed",
              "partial": "Partial", "pending": "Pending"}
    return labels.get(str(label).lower(), str(label).replace("_", " ").capitalize())


def render_page_header(title: str, subtitle: str) -> None:
    date_label = datetime.now(ZoneInfo("Asia/Kolkata")).strftime("%d %b %Y")
    st.markdown(
        f'<div class="breadcrumb">Workspace &nbsp;/&nbsp; <b>{escape(title)}</b></div>'
        f'<div class="page-top"><div><h1>{escape(title)}</h1><p>{escape(subtitle)}</p></div>'
        f'<div class="date-label">{date_label}</div></div>', unsafe_allow_html=True,
    )


def render_sidebar() -> str:
    st.sidebar.markdown('<div class="brand"><div class="brand-mark">a</div><div class="brand-name">auditflow<small>INVOICE INTELLIGENCE</small></div></div><div class="nav-label">YOUR WORKSPACE</div>', unsafe_allow_html=True)
    page = st.sidebar.radio("Navigate", ["Invoice Dashboard", "Ask a Question"],
                            format_func=lambda value: "Overview" if value == "Invoice Dashboard" else "Invoice assistant",
                            label_visibility="collapsed", key="workspace_nav")
    st.sidebar.markdown('<div class="sidebar-note"><strong>Every detail. Accounted for.</strong>Review the evidence, resolve exceptions, and keep every decision traceable.</div>', unsafe_allow_html=True)
    if st.sidebar.button("Refresh workspace", use_container_width=True):
        st.cache_data.clear()
        st.rerun()
    healthy = False if PREVIEW else agent_client.health_check()
    st.session_state["agent_healthy"] = healthy
    status = "Sample-data preview" if PREVIEW else "Agent service connected" if healthy else "Agent service offline"
    dot = "dot" if healthy else "dot off"
    st.sidebar.markdown(f'<div class="service"><span class="{dot}"></span>{status}</div>', unsafe_allow_html=True)
    if not healthy and not PREVIEW:
        st.sidebar.caption("Saved invoices remain available. Questions and corrections need the agent service.")
    return page


def render_summary() -> None:
    summary = db.get_dashboard_summary() or {}
    total = int(summary.get("total_invoices") or 0)
    st.markdown('<div class="hero"><div><div class="hero-kicker">YOUR AUDIT CONTROL CENTER</div><div class="hero-title">Confidence in every invoice.</div><div class="hero-copy">A clear view of what is approved, what needs attention, and the evidence behind every decision.</div></div><div class="hero-pill">Human-led. AI-assisted.</div></div>', unsafe_allow_html=True)
    items = [("Total invoices", total, "All processed documents", "", "&#9636;"),
             ("Approved", summary.get("approved", 0), "Ready for the next step", "green", "&#10003;"),
             ("Needs review", summary.get("review", 0), "An auditor's attention needed", "amber", "&#9671;"),
             ("Rejected", summary.get("rejected", 0), "Flagged by validation", "red", "&#215;"),
             ("Processing errors", summary.get("processing_errors", 0), "Items to investigate", "", "&#8943;")]
    cards = "".join(f'<div class="kpi {tone}"><div class="kpi-label">{label}<span class="kpi-icon">{icon}</span></div><div class="kpi-number">{int(value or 0):,}</div><div class="kpi-foot">{escape(foot)}</div></div>' for label, value, foot, tone, icon in items)
    st.markdown(f'<div class="kpi-grid">{cards}</div>', unsafe_allow_html=True)


def render_invoice_list() -> str | None:
    section("Invoice queue", "Find an invoice, review the evidence, and resolve what matters.")
    filters = st.columns([2.3, 1, 1], gap="small")
    search = filters[0].text_input("Search invoices", placeholder="Search by invoice, vendor or purchase order", label_visibility="collapsed", key="queue_search")
    status_filter = filters[1].selectbox("Validation status", ["All", "passed", "failed", "partial", "pending"], format_func=lambda x: "All statuses" if x == "All" else x.capitalize(), label_visibility="collapsed", key="queue_status")
    recommendation_filter = filters[2].selectbox("Recommendation", ["All", "approve", "review", "reject"], format_func=lambda x: "All outcomes" if x == "All" else _badge(x), label_visibility="collapsed", key="queue_recommendation")
    invoices = db.list_invoices(status=None if status_filter == "All" else status_filter,
                                recommendation=None if recommendation_filter == "All" else recommendation_filter)
    if search.strip() and not invoices.empty:
        columns = [c for c in ("invoice_number", "vendor_name", "po_number") if c in invoices]
        mask = invoices[columns].fillna("").astype(str).apply(lambda col: col.str.contains(search.strip(), case=False, regex=False)).any(axis=1)
        invoices = invoices[mask]
    if invoices.empty:
        st.info("No invoices found. Try another search or change the filters.")
        return None
    display = invoices.copy()
    display["recommendation"] = display["recommendation"].map(lambda v: _badge(v) if v else "Pending")
    display["validation_status"] = display["validation_status"].map(_badge)
    st.dataframe(display[["invoice_number", "vendor_name", "invoice_date", "currency", "total_amount", "validation_status", "recommendation"]],
                 width="stretch", hide_index=True, row_height=43,
                 column_config={"invoice_number": st.column_config.TextColumn("Invoice", width="small"),
                                "vendor_name": st.column_config.TextColumn("Vendor", width="medium"),
                                "invoice_date": st.column_config.TextColumn("Issue date"),
                                "currency": st.column_config.TextColumn("Currency", width="small"),
                                "total_amount": st.column_config.NumberColumn("Amount", format="%.2f"),
                                "validation_status": st.column_config.TextColumn("Validation"),
                                "recommendation": st.column_config.TextColumn("Outcome")})
    st.caption(f"{len(invoices)} invoice{'s' if len(invoices) != 1 else ''} shown")
    options = {f"{row.invoice_number or 'Untitled invoice'}  /  {row.vendor_name or 'Unknown vendor'}  ({str(row.invoice_id)[:8]})": str(row.invoice_id) for row in invoices.itertuples()}
    pending_invoice = st.session_state.pop("open_uploaded_invoice", None)
    if pending_invoice:
        matching = next((label for label, value in options.items() if value == pending_invoice), None)
        if matching:
            st.session_state["selected_invoice"] = matching
    selected = st.selectbox("Review an invoice", list(options), key="selected_invoice")
    return options[selected]


def render_invoice_detail(invoice_id: str) -> None:
    invoice = db.get_invoice(invoice_id)
    if invoice is None:
        st.warning("Invoice not found.")
        return

    st.divider()
    st.markdown(
        f'<div class="app-eyebrow">INVOICE REVIEW</div>',
        unsafe_allow_html=True,
    )
    st.subheader(f"Invoice {invoice.get('invoice_number') or invoice_id}")
    if invoice.get("processing_error"):
        st.error(f"Processing error: {invoice['processing_error']}")

    header_cols = st.columns(4)
    header_cols[0].metric("Vendor", invoice.get("vendor_name") or "—")
    total = invoice.get("total_amount")
    currency = invoice.get("currency") or ""
    header_cols[1].metric("Invoice total", f"{total} {currency}".strip() if total is not None else "—")
    header_cols[2].metric("Validation", _badge(invoice.get("validation_status") or "pending"))
    header_cols[3].metric("Recommendation", _badge(invoice.get("recommendation") or "pending"))

    detail_cols = st.columns(3)
    detail_cols[0].write(f"**Purchase order**  \n{invoice.get('po_number') or '—'}")
    detail_cols[1].write(f"**Source language**  \n{invoice.get('source_language') or '—'}")
    confidence = invoice.get("translation_confidence")
    detail_cols[2].write(
        "**Translation confidence**  \n"
        + (f"{float(confidence):.2f}" if confidence is not None else "—")
    )

    tabs = st.tabs(
        ["Report", "Line items", "Discrepancies", "Extracted text", "Corrections"]
    )
    report = (invoice.get("extracted_raw") or {}).get("report")

    with tabs[0]:
        st.markdown("#### Audit report")
        if report:
            recommendation = _badge(report.get("recommendation") or invoice.get("recommendation") or "pending")
            count = (report.get("discrepancy_summary") or {}).get("total", len(report.get("discrepancies") or []))
            st.markdown(f'<div class="report-summary"><strong>{escape(recommendation)}</strong><p>{int(count)} discrepancy findings. Review the evidence and resolve any exceptions before your next decision.</p></div>', unsafe_allow_html=True)
            for error in report.get("validation_errors") or []:
                st.write(f"- {error}")
            if report.get("missing_fields"):
                st.caption("Missing fields: " + ", ".join(report["missing_fields"]))
            st.download_button("Download audit report", json.dumps(report, indent=2, default=str), file_name=f"audit-{invoice_id}.json", mime="application/json")
            with st.expander("View full report data"):
                st.json(report, expanded=False)
        else:
            st.info("No report has been generated for this invoice yet.")

    line_items = db.get_line_items(invoice_id)
    with tabs[1]:
        if line_items.empty:
            st.info("No line items recorded.")
        else:
            st.dataframe(line_items, width="stretch", hide_index=True)

    with tabs[2]:
        discrepancies = db.get_discrepancies(invoice_id)
        if discrepancies.empty:
            st.success("No discrepancies detected.")
        else:
            discrepancies = discrepancies.copy()
            product_labels = {}
            for item in line_items.fillna("").itertuples(index=False):
                description = str(item.description).strip()
                code = str(item.item_code).strip()
                if description and code and description != code:
                    product_labels[item.line_number] = f"{description} ({code})"
                elif description or code:
                    product_labels[item.line_number] = description or code
            discrepancies["field_name"] = discrepancies["field_name"].map(
                lambda field: format_discrepancy_field(field, product_labels)
            )
            st.dataframe(discrepancies, width="stretch", hide_index=True)

    with tabs[3]:
        text_cols = st.columns(2)
        with text_cols[0]:
            st.markdown("#### Original extracted text")
            st.text_area(
                "raw_extracted_text",
                invoice.get("raw_extracted_text") or "",
                height=300,
                label_visibility="collapsed",
            )
        with text_cols[1]:
            st.markdown("#### English translation")
            st.text_area(
                "translated_text",
                invoice.get("translated_text") or "",
                height=300,
                label_visibility="collapsed",
            )

    with tabs[4]:
        render_corrections(invoice_id, invoice)


def format_discrepancy_field(field_name: str, product_labels: dict[int, str]) -> str:
    match = re.fullmatch(r"line_items\[(\d+)\](?:\.([a-z_][a-z_0-9]*))?", field_name, re.I)
    if match:
        index, field = match.groups()
        number = int(index) + 1
        line = product_labels.get(number, f"Line item {number}")
        return f"{line} · {field.replace('_', ' ').capitalize()}" if field else line
    return field_name.replace("_", " ").capitalize()


def render_corrections(invoice_id: str, invoice: dict) -> None:
    st.markdown("#### Submit a correction")
    st.caption(
        "Corrections are stored separately from the original extraction and are "
        "applied only when you request revalidation."
    )

    field_name = st.selectbox("Field to correct", CORRECTABLE_FIELDS, format_func=lambda value: value.replace("_", " ").capitalize(), key=f"correction_field_{invoice_id}")
    parsed = (invoice.get("extracted_raw") or {}).get("parsed_invoice") or {}
    current_value = invoice.get(field_name, parsed.get(field_name))
    with st.form(f"feedback_form_{invoice_id}", clear_on_submit=True):
        st.text_input(
            "Current extracted value",
            value=str(current_value) if current_value is not None else "",
            disabled=True,
        )
        corrected_value = st.text_input("Corrected value")
        corrected_by = st.text_input(
            "Auditor name / ID",
            value=st.session_state.get("auditor_name", ""),
        )
        submitted = st.form_submit_button("Submit correction", type="primary", disabled=PREVIEW)

        if submitted:
            if not corrected_value or not corrected_by:
                st.warning("Please provide both a corrected value and your name.")
            else:
                st.session_state["auditor_name"] = corrected_by
                try:
                    agent_client.submit_feedback(
                        invoice_id=invoice_id,
                        field_name=field_name,
                        corrected_value=corrected_value,
                        corrected_by=corrected_by,
                        original_value=str(current_value) if current_value is not None else None,
                    )
                    st.success("Correction recorded.")
                    st.cache_data.clear()
                except agent_client.AgentApiError as exc:
                    st.error(str(exc))

    st.markdown("#### Correction history")
    feedback = db.get_feedback(invoice_id)
    if feedback.empty:
        st.info("No corrections have been submitted for this invoice yet.")
    else:
        display = feedback.copy()
        display["revalidated"] = display["revalidated"].map(lambda v: "Completed" if v else "Pending")
        st.dataframe(display, width="stretch", hide_index=True)

        pending = (feedback["revalidated"] == False).sum()  # noqa: E712
        if pending:
            st.warning(f"{pending} correction(s) are awaiting revalidation.")
            if st.button("Revalidate invoice", type="primary", disabled=PREVIEW):
                try:
                    result = agent_client.revalidate_invoice(invoice_id)
                    st.success(
                        "Revalidation complete. New recommendation: "
                        f"{result.get('recommendation', 'unknown')}"
                    )
                    st.json(result, expanded=False)
                    st.cache_data.clear()
                except agent_client.AgentApiError as exc:
                    st.error(str(exc))
        else:
            st.caption("All submitted corrections have been revalidated.")


def render_query_page() -> None:
    render_page_header("Invoice assistant", "Answers backed by your invoice evidence.")
    st.markdown('<div class="assistant-welcome"><div class="assistant-symbol">&#10023;</div><h2>A little clarity goes a long way.</h2><p>Ask about totals, discrepancies, or the details in an invoice. Your assistant searches the evidence so you can focus on the decision.</p></div>', unsafe_allow_html=True)
    invoices = db.list_invoices()
    scope_options = {"All processed invoices": None}
    if not invoices.empty:
        scope_options.update({f"{row.invoice_number or 'Untitled'} ({str(row.invoice_id)[:8]})": str(row.invoice_id) for row in invoices.itertuples()})
    pending_scope = st.session_state.pop("pending_query_invoice", None)
    if pending_scope:
        matching = next((label for label, value in scope_options.items() if value == pending_scope), None)
        if matching:
            st.session_state["query_scope"] = matching
    with st.container(border=True):
        scope_label = st.selectbox("Search within", list(scope_options), key="query_scope")
        question = st.text_area("What would you like to know?", placeholder="Which invoices need review, and why?", height=110, max_chars=4000, key="assistant_question")
        examples = st.columns(3)
        for col, text in zip(examples, ["How many invoices were rejected?", "Which invoices need review?", "What discrepancies were found?"]):
            col.button(text, on_click=_set_question, args=(text,), use_container_width=True)
        ask = st.button("Ask the assistant", type="primary", disabled=PREVIEW or not question.strip())
        st.caption("Responses are checked against available evidence. An answer may be withheld when confidence is too low.")
    if ask:
        with st.spinner("Looking through your invoice evidence..."):
            try:
                result = agent_client.ask_question(question=question, invoice_id=scope_options[scope_label])
                st.session_state["last_query"] = {"result": result, "question": question, "scope": scope_label}
            except agent_client.AgentApiError as exc:
                st.error(str(exc))
                return
    saved = st.session_state.get("last_query")
    if saved:
        result = saved["result"]
        section("Your answer", f'{saved["scope"]} / {saved["question"]}')
        if result.get("status") == "completed":
            with st.container(border=True):
                st.write(result.get("answer") or "No answer returned.")
        else:
            st.warning(result.get("answer") or "The available evidence could not support a confident answer.")
        cols = st.columns(4)
        cols[0].metric("Query type", result.get("query_type") or "Unavailable")
        cols[1].metric("Answer source", result.get("answer_source") or "Unavailable")
        score = result.get("average_score")
        cols[2].metric("Evidence score", f"{float(score):.2f}" if score is not None else "Not applicable")
        cols[3].metric("Retries", result.get("retry_count") or 0)
        if result.get("error"):
            st.error(result["error"])


def _set_question(value: str) -> None:
    st.session_state["assistant_question"] = value




def _open_uploaded_invoice_assistant(invoice_id: str) -> None:
    st.session_state["workspace_nav"] = "Ask a Question"
    st.session_state["pending_query_invoice"] = invoice_id
    st.session_state["assistant_question"] = "What discrepancies were found on this invoice?"
    st.session_state.pop("last_query", None)


def render_upload_panel() -> None:
    with st.expander("Upload a new invoice", expanded=False):
        st.caption("PDF, DOCX or PNG / up to 20 MB. The file is saved, audited, and indexed for invoice questions.")
        upload_options = {}
        if "max_upload_size" in inspect.signature(st.file_uploader).parameters:
            upload_options["max_upload_size"] = 20
        uploaded = st.file_uploader("Choose an invoice", type=["pdf", "docx", "png"],
                                    accept_multiple_files=False, disabled=PREVIEW, key="invoice_upload",
                                    **upload_options)
        too_large = uploaded is not None and uploaded.size > 20 * 1024 * 1024
        if too_large:
            st.error("This file exceeds the 20 MB invoice limit.")
        if PREVIEW:
            st.caption("Uploads are disabled in the sample-data design preview.")
        if st.button("Upload & process invoice", type="primary",
                     disabled=PREVIEW or uploaded is None or too_large):
            with st.status("Saving and processing your invoice...", expanded=True) as progress:
                st.write("Running extraction, translation, validation, reporting and RAG indexing.")
                try:
                    result = agent_client.upload_invoice(uploaded.name, uploaded.getvalue(), uploaded.type)
                    st.session_state["upload_receipt"] = result
                    st.session_state["open_uploaded_invoice"] = result["invoice_id"]
                    # Clear queue filters before their widgets are rendered.
                    st.session_state["queue_search"] = ""
                    st.session_state["queue_status"] = "All"
                    st.session_state["queue_recommendation"] = "All"
                    st.cache_data.clear()
                    label = ("Invoice processed and indexed" if result.get("rag_ready") else
                             "Invoice saved; some processing steps need attention")
                    progress.update(label=label, state="complete" if result.get("rag_ready") else "error")
                except agent_client.AgentApiError as exc:
                    progress.update(label="Upload could not finish", state="error")
                    st.error(str(exc))
                    st.caption("If processing timed out, refresh the workspace or upload the same file again. Checksum matching prevents a second audit record.")
        result = st.session_state.get("upload_receipt")
        if result:
            if result.get("duplicate"):
                st.info("This file is already in the audit workspace. No duplicate record was created.")
            if result.get("rag_ready"):
                st.success("Invoice saved and available to the invoice assistant.")
            elif result.get("processing_status") == "processing":
                st.info("The invoice is registered. Refresh its status to check processing progress.")
            else:
                st.warning(result.get("error") or "The invoice is saved, but processing is not fully complete.")
            st.caption("Invoice ID: " + result["invoice_id"])
            states = st.columns(4)
            states[0].write("**File stored**\n\n" + ("Yes" if result.get("stored") else "Not confirmed"))
            states[1].write("**Audit record**\n\n" + ("Persisted" if result.get("persisted") else "Not confirmed"))
            states[2].write("**Report**\n\n" + str(result.get("report_status", "Not complete")).replace("_", " ").capitalize())
            states[3].write("**RAG index**\n\n" + ("Ready" if result.get("rag_ready") else "Not ready"))
            actions = st.columns(3)
            if actions[0].button("Refresh upload status", disabled=PREVIEW):
                try:
                    st.session_state["upload_receipt"] = agent_client.invoice_status(result["invoice_id"])
                    st.cache_data.clear()
                    st.rerun()
                except agent_client.AgentApiError as exc:
                    st.error(str(exc))
            if not result.get("rag_ready") and result.get("report_status") == "completed":
                if actions[1].button("Retry RAG indexing", disabled=PREVIEW):
                    with st.spinner("Indexing saved invoice evidence..."):
                        try:
                            st.session_state["upload_receipt"] = agent_client.retry_invoice_indexing(result["invoice_id"])
                            st.cache_data.clear()
                            st.rerun()
                        except agent_client.AgentApiError as exc:
                            st.error(str(exc))
            actions[2].button("Ask about this invoice", disabled=PREVIEW or not result.get("rag_ready"),
                              on_click=_open_uploaded_invoice_assistant, args=(result["invoice_id"],))


def main() -> None:
    page = render_sidebar()
    if PREVIEW:
        st.info("Design preview / sample invoices. Submission actions are disabled.")
    try:
        if page == "Invoice Dashboard":
            render_page_header("Invoice overview", "Your invoices, exceptions, and decisions. In one place.")
            render_upload_panel()
            render_summary()
            selected_invoice_id = render_invoice_list()
            if selected_invoice_id:
                render_invoice_detail(selected_invoice_id)
        else:
            render_query_page()
    except (sa.exc.SQLAlchemyError, OSError):
        st.warning("Your audit workspace is waiting for a database connection.")
        st.caption("Connect the configured database and refresh to load your invoices. No changes have been made.")
    st.markdown('<div class="footer"><span>auditflow / invoice intelligence</span><span>Evidence first. Every decision traceable.</span></div>', unsafe_allow_html=True)


if __name__ == "__main__":
    main()