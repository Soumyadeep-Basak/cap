"""AI Invoice Auditor -- human-in-the-loop Streamlit dashboard.

Lets a non-technical auditor review processed invoice reports and
discrepancies, correct extracted values, request revalidation, and ask
natural-language questions about processed invoices. All mutations
(feedback, revalidation, querying) are delegated to the Agent API; the
dashboard only reads audit data directly from PostgreSQL.
"""

from __future__ import annotations

import streamlit as st

from invoice_auditor_ui import agent_client, db

st.set_page_config(
    page_title="AI Invoice Auditor",
    page_icon="🧾",
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

# Visual-only styling: existing database and Agent API behavior is preserved.
st.markdown(
    """
    <style>
      :root {
        --navy: #14243a;
        --navy-soft: #203650;
        --teal: #167d78;
        --teal-hover: #116a66;
        --ink: #172b43;
        --muted: #64748b;
        --line: #e2e8f0;
        --surface: #ffffff;
        --canvas: #f5f7fb;
      }
      .stApp { background: var(--canvas); color: var(--ink); }
      [data-testid="stHeader"] { background: rgba(245,247,251,.92); }
      [data-testid="stSidebar"] {
        background: var(--navy);
        border-right: 1px solid #263b54;
      }
      [data-testid="stSidebar"] * { color: #edf3fa; }
      [data-testid="stSidebar"] [data-testid="stCaptionContainer"] p {
        color: #b7c6d8;
      }
      [data-testid="stSidebar"] [data-testid="stRadio"] label {
        border-radius: 8px;
        padding: 5px 8px;
      }
      h1, h2, h3 { color: var(--navy); letter-spacing: -.025em; }
      h1 { font-weight: 750; }
      h2, h3 { font-weight: 680; }
      p, label, .stMarkdown { color: var(--ink); }
      [data-testid="stMetric"] {
        background: var(--surface);
        border: 1px solid var(--line);
        border-radius: 12px;
        padding: 16px 18px;
        box-shadow: 0 2px 8px rgba(20,36,58,.035);
        min-height: 108px;
      }
      [data-testid="stMetricLabel"] p {
        color: var(--muted);
        font-size: .85rem;
        font-weight: 550;
      }
      [data-testid="stMetricValue"] {
        color: var(--navy);
        font-weight: 750;
      }
      [data-testid="stDataFrame"], [data-testid="stTable"] {
        border: 1px solid var(--line);
        border-radius: 10px;
        overflow: hidden;
        background: white;
      }
      [data-testid="stTabs"] [data-baseweb="tab-list"] {
        gap: 8px;
        border-bottom: 1px solid var(--line);
      }
      [data-testid="stTabs"] button[role="tab"] {
        padding: 12px 14px;
        color: var(--muted);
        font-weight: 600;
      }
      [data-testid="stTabs"] button[aria-selected="true"] {
        color: var(--teal);
        border-bottom-color: var(--teal);
      }
      .stButton > button, .stFormSubmitButton > button {
        border-radius: 8px;
        font-weight: 650;
        min-height: 40px;
        border: 1px solid #d5dee9;
      }
      [data-testid="stSidebar"] .stButton > button {
        background: var(--navy-soft);
        border-color: #54708f;
        color: #ffffff;
      }
      [data-testid="stSidebar"] .stButton > button:hover {
        background: var(--teal);
        border-color: var(--teal);
        color: #ffffff;
      }
      .stButton > button[kind="primary"],
      .stFormSubmitButton > button[kind="primary"] {
        background: var(--teal);
        border-color: var(--teal);
        color: white;
      }
      .stButton > button[kind="primary"]:hover,
      .stFormSubmitButton > button[kind="primary"]:hover {
        background: var(--teal-hover);
        border-color: var(--teal-hover);
        color: white;
      }
      [data-testid="stTextInput"] input,
      [data-testid="stTextArea"] textarea,
      [data-testid="stSelectbox"] [data-baseweb="select"] > div {
        border-radius: 8px;
      }
      [data-testid="stAlert"] { border-radius: 10px; }
      hr { border-color: var(--line); }
      .app-eyebrow {
        color: var(--teal);
        font-size: .76rem;
        font-weight: 750;
        letter-spacing: .12em;
        text-transform: uppercase;
        margin-bottom: .3rem;
      }
      .app-subtitle {
        color: var(--muted);
        margin-top: -.35rem;
        margin-bottom: 1.25rem;
      }
      .section-heading {
        color: var(--navy);
        font-size: 1.12rem;
        font-weight: 720;
        margin: .25rem 0 .2rem 0;
      }
      .status-chip {
        display: inline-block;
        border-radius: 999px;
        padding: 4px 10px;
        background: #e8f5f2;
        color: #11665e;
        font-size: .78rem;
        font-weight: 700;
      }
      @media (max-width: 700px) {
        [data-testid="stMetric"] { padding: 12px; }
      }
    </style>
    """,
    unsafe_allow_html=True,
)


def _badge(label: str) -> str:
    colors = {
        "approve": "🟢",
        "review": "🟡",
        "reject": "🔴",
        "passed": "🟢",
        "failed": "🔴",
        "partial": "🟡",
        "pending": "⚪",
    }
    icon = colors.get(str(label).lower(), "⚪")
    return f"{icon} {label}"


def render_page_header(title: str, subtitle: str) -> None:
    st.markdown('<div class="app-eyebrow">FINANCE OPERATIONS</div>', unsafe_allow_html=True)
    st.title(title)
    st.markdown(f'<div class="app-subtitle">{subtitle}</div>', unsafe_allow_html=True)


def render_sidebar() -> str:
    st.sidebar.markdown("## 🧾 Invoice Auditor")
    st.sidebar.caption("AI-powered invoice validation")
    st.sidebar.divider()

    healthy = agent_client.health_check()
    if healthy:
        st.sidebar.success("Agent service online")
    else:
        st.sidebar.error(
            "Agent service unreachable. Corrections, revalidation, and questions "
            "will not work until it is back online."
        )

    st.sidebar.markdown("##### WORKSPACE")
    page = st.sidebar.radio(
        "Navigate",
        ["Invoice Dashboard", "Ask a Question"],
        label_visibility="collapsed",
    )

    st.sidebar.divider()
    if st.sidebar.button("↻  Refresh data", use_container_width=True):
        st.cache_data.clear()
        st.rerun()

    st.sidebar.markdown("---")
    st.sidebar.caption(
        "Audit data is read from PostgreSQL. All changes and questions are sent "
        "through the Agent API."
    )
    return page


def render_summary() -> None:
    summary = db.get_dashboard_summary()
    if not summary:
        st.info("No invoices have been processed yet.")
        return

    cols = st.columns(5)
    cols[0].metric("Total invoices", summary.get("total_invoices", 0))
    cols[1].metric("Approved", summary.get("approved", 0))
    cols[2].metric("Needs review", summary.get("review", 0))
    cols[3].metric("Rejected", summary.get("rejected", 0))
    cols[4].metric("Processing errors", summary.get("processing_errors", 0))


def render_invoice_list() -> str | None:
    st.markdown('<div class="section-heading">Processed invoices</div>', unsafe_allow_html=True)
    st.caption("Filter the audit queue, then select an invoice to inspect its report and history.")

    filter_cols = st.columns(2)
    status_filter = filter_cols[0].selectbox(
        "Validation status",
        ["All", "passed", "failed", "partial", "pending"],
    )
    recommendation_filter = filter_cols[1].selectbox(
        "Recommendation",
        ["All", "approve", "review", "reject"],
    )

    invoices = db.list_invoices(
        status=None if status_filter == "All" else status_filter,
        recommendation=None if recommendation_filter == "All" else recommendation_filter,
    )

    if invoices.empty:
        st.info("No invoices match the selected filters.")
        return None

    display = invoices.copy()
    display["recommendation"] = display["recommendation"].map(
        lambda v: _badge(v) if v else "⚪ pending"
    )
    display["validation_status"] = display["validation_status"].map(_badge)

    st.dataframe(
        display[
            [
                "invoice_number",
                "vendor_name",
                "invoice_date",
                "currency",
                "total_amount",
                "validation_status",
                "recommendation",
                "processed_at",
            ]
        ],
        width="stretch",
        hide_index=True,
        column_config={
            "invoice_number": st.column_config.TextColumn("Invoice"),
            "vendor_name": st.column_config.TextColumn("Vendor"),
            "invoice_date": st.column_config.TextColumn("Invoice date"),
            "currency": st.column_config.TextColumn("Currency"),
            "total_amount": st.column_config.NumberColumn("Total", format="%.2f"),
            "validation_status": st.column_config.TextColumn("Validation"),
            "recommendation": st.column_config.TextColumn("Recommendation"),
            "processed_at": st.column_config.DatetimeColumn("Processed at"),
        },
    )

    options = {
        f"{row.invoice_number or '(no number)'} — "
        f"{row.vendor_name or 'unknown vendor'} ({str(row.invoice_id)[:8]})": str(row.invoice_id)
        for row in invoices.itertuples()
    }
    selected_label = st.selectbox("Open invoice details", list(options.keys()))
    return options[selected_label]


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
            st.json(report, expanded=False)
        else:
            st.info("No report has been generated for this invoice yet.")

    with tabs[1]:
        line_items = db.get_line_items(invoice_id)
        if line_items.empty:
            st.info("No line items recorded.")
        else:
            st.dataframe(line_items, width="stretch", hide_index=True)

    with tabs[2]:
        discrepancies = db.get_discrepancies(invoice_id)
        if discrepancies.empty:
            st.success("No discrepancies detected.")
        else:
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


def render_corrections(invoice_id: str, invoice: dict) -> None:
    st.markdown("#### Submit a correction")
    st.caption(
        "Corrections are stored separately from the original extraction and are "
        "applied only when you request revalidation."
    )

    with st.form("feedback_form", clear_on_submit=True):
        field_name = st.selectbox("Field to correct", CORRECTABLE_FIELDS)
        current_value = invoice.get(field_name)
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
        submitted = st.form_submit_button("Submit correction", type="primary")

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
            if st.button("Revalidate invoice", type="primary"):
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
    render_page_header(
        "Ask the invoice assistant",
        "Query processed invoices using structured database lookups or retrieval-augmented generation.",
    )

    invoices = db.list_invoices()
    scope_options = {"All processed invoices": None}
    if not invoices.empty:
        scope_options.update(
            {
                f"{row.invoice_number or '(no number)'} ({str(row.invoice_id)[:8]})": str(row.invoice_id)
                for row in invoices.itertuples()
            }
        )

    with st.container(border=True):
        scope_label = st.selectbox("Invoice scope", list(scope_options.keys()))
        question = st.text_area(
            "Your question",
            placeholder=(
                "Example: How many invoices were rejected? "
                "What discrepancies were found on this invoice?"
            ),
        )
        ask = st.button("Ask question", type="primary", disabled=not question.strip())

    if ask:
        with st.spinner("Analyzing invoice data..."):
            try:
                result = agent_client.ask_question(
                    question=question,
                    invoice_id=scope_options[scope_label],
                )
            except agent_client.AgentApiError as exc:
                st.error(str(exc))
                return

        if result.get("status") == "completed":
            st.success(result.get("answer") or "(no answer returned)")
        else:
            st.warning(result.get("answer") or "The system could not produce a confident answer.")

        meta_cols = st.columns(4)
        meta_cols[0].metric("Query type", result.get("query_type") or "—")
        meta_cols[1].metric("Answer source", result.get("answer_source") or "—")
        score = result.get("average_score")
        meta_cols[2].metric("RAG Triad score", f"{score:.2f}" if score is not None else "—")
        meta_cols[3].metric("Retries", result.get("retry_count") or 0)

        if result.get("error"):
            st.error(result["error"])


def main() -> None:
    page = render_sidebar()

    if page == "Invoice Dashboard":
        render_page_header(
            "Invoice dashboard",
            "Monitor processing outcomes, review discrepancies, and manage auditor corrections.",
        )
        render_summary()
        st.markdown("")
        selected_invoice_id = render_invoice_list()
        if selected_invoice_id:
            render_invoice_detail(selected_invoice_id)
    else:
        render_query_page()


if __name__ == "__main__":
    main()
