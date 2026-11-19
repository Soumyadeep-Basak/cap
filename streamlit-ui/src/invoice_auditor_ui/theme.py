"""Presentation only: visual tokens and escaped HTML components."""
from html import escape
import streamlit as st

CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;600;700&family=Manrope:wght@400;500;600;700;800&display=swap');
:root { --ink:#202638; --muted:#7a8192; --line:#e9eaf0; --purple:#6955d9; --canvas:#f6f7fb; }
html,body,[class*="css"],[data-testid="stApp"] { font-family:'DM Sans',sans-serif; }
.stApp { background:var(--canvas); color:var(--ink); }
[data-testid="stHeader"] { background:rgba(246,247,251,.94); }
.block-container { max-width:1530px; padding:2.5rem 2.6rem 4rem; }
h1,h2,h3 { font-family:'Manrope',sans-serif; color:var(--ink); letter-spacing:-.045em; }
h1 { font-size:2rem; font-weight:800; }
h3 { font-size:1.2rem; font-weight:750; }
p,label { color:var(--ink); }
[data-testid="stCaptionContainer"] p { color:var(--muted); font-size:.82rem; }
[data-testid="stSidebar"] { background:#171b2d; min-width:240px; max-width:240px; border-right:none; }
[data-testid="stSidebar"] [data-testid="stSidebarContent"] { padding:1.25rem .9rem; }
[data-testid="stSidebar"] p,[data-testid="stSidebar"] label,[data-testid="stSidebar"] span { color:#c2c5d4; }
[data-testid="stSidebar"] hr { border-color:#2c3043; margin:1.7rem 0; }
.brand { display:flex; align-items:center; gap:11px; padding:4px 8px 25px; }
.brand-mark { background:#8c7cf5; border-radius:11px; width:37px; height:40px; color:white; display:grid; place-items:center; font-size:22px; font-weight:800; }
.brand-name { color:white; font-family:Manrope,sans-serif; font-size:19px; font-weight:800; letter-spacing:-.6px; }
.brand-name small { display:block; color:#848ba5; font-family:'DM Sans',sans-serif; letter-spacing:1.9px; font-size:9px; margin-top:3px; }
.nav-label { color:#737b96; font-size:10px; font-weight:700; letter-spacing:1.7px; padding:10px 10px; }
[data-testid="stSidebar"] [data-testid="stRadio"] [role="radiogroup"] { gap:7px; }
[data-testid="stSidebar"] [data-testid="stRadio"] label { padding:12px 13px; border-radius:8px; width:100%; }
[data-testid="stSidebar"] [data-testid="stRadio"] label:has(input:checked) { background:#35304f; }
[data-testid="stSidebar"] [data-testid="stRadio"] label:has(input:checked) p { color:#ddd7ff; font-weight:600; }
[data-testid="stSidebar"] [data-testid="stRadio"] label > div:first-child { display:none; }
.sidebar-note { background:#22263a; border:1px solid #30354c; padding:16px; border-radius:12px; margin:28px 5px 18px; font-size:12px; color:#9da6c1; line-height:1.7; }
.sidebar-note strong { display:block; color:#e3e5f3; font-size:12px; margin-bottom:7px; }
.service { border-top:1px solid #30354c; padding:15px 10px; color:#9da6c1; font-size:11px; display:flex; align-items:center; gap:7px; }
.dot { width:6px; height:6px; display:inline-block; border-radius:50%; background:#56c99a; }
.dot.off { background:#e9aa66; }
.breadcrumb { color:#969aaa; font-size:11px; letter-spacing:.3px; margin-bottom:21px; }
.breadcrumb b { color:#535b72; font-weight:500; }
.page-top { display:flex; justify-content:space-between; align-items:flex-start; gap:20px; margin-bottom:23px; }
.page-top h1 { margin:0; line-height:1.25; }
.page-top p { color:var(--muted); font-size:13px; margin:9px 0 0; }
.date-label { background:white; border:1px solid var(--line); border-radius:7px; padding:9px 12px; font-size:11px; white-space:nowrap; color:#5d657a; }
.hero { background:#26223e; border:1px solid #3c3558; color:white; border-radius:15px; padding:25px 30px; margin:0 0 24px; position:relative; overflow:hidden; display:flex; align-items:center; justify-content:space-between; gap:24px; }
.hero:after { content:""; position:absolute; border:1px solid #51466c; border-radius:50%; width:260px; height:260px; right:52px; top:-126px; pointer-events:none; }
.hero:before { content:""; position:absolute; border:1px solid #51466c; border-radius:50%; width:260px; height:260px; right:-72px; top:-70px; pointer-events:none; }
.hero-kicker { color:#b6a8ef; text-transform:uppercase; font-size:9px; font-weight:700; letter-spacing:1.8px; margin-bottom:9px; }
.hero-title { color:white; font-family:Manrope,sans-serif; font-size:22px; font-weight:700; letter-spacing:-.6px; }
.hero-copy { color:#b9b4cb; font-size:12px; line-height:1.6; margin-top:8px; max-width:530px; }
.hero-pill { border:1px solid #655679; background:#39304e; border-radius:30px; padding:8px 12px; color:#dbd1f8; font-size:10px; white-space:nowrap; position:relative; z-index:1; }
.kpi-grid { display:grid; grid-template-columns:repeat(5,minmax(0,1fr)); gap:13px; margin:0 0 29px; }
.kpi { background:white; border:1px solid var(--line); border-radius:11px; padding:17px 18px; box-shadow:0 3px 7px #20263802; }
.kpi-label { font-size:11px; color:#777f91; margin-bottom:12px; display:flex; justify-content:space-between; }
.kpi-number { font-family:Manrope,sans-serif; font-size:28px; color:#252a3d; font-weight:800; line-height:1.1; letter-spacing:-1px; }
.kpi-foot { margin-top:10px; font-size:10px; color:#9198a8; }
.kpi-icon { border-radius:5px; background:#f0edff; color:#806bdc; padding:0 5px; }
.kpi.green .kpi-icon { color:#2d9b79; background:#ebf7f1; }
.kpi.amber .kpi-icon { color:#bc8b32; background:#fff6e4; }
.kpi.red .kpi-icon { color:#d16b79; background:#fff0f2; }
.section-heading { font-family:Manrope,sans-serif; color:#252c40; font-weight:800; font-size:16px; letter-spacing:-.4px; }
.section-row { display:flex; justify-content:space-between; align-items:center; margin:0 0 7px; }
.section-sub { color:#8a91a2; font-size:11px; margin-top:5px; }
.count-pill { background:#efedf9; color:#7766b3; font-size:10px; border-radius:20px; padding:4px 9px; }
[data-testid="stVerticalBlockBorderWrapper"] > div { border-radius:12px; border-color:var(--line); background:white; }
[data-testid="stDataFrame"] { border:1px solid var(--line); border-radius:9px; overflow:hidden; }
[data-testid="stTextInput"] input,[data-testid="stTextArea"] textarea { font-size:12px; }
[data-testid="stTextInput"] > div,[data-testid="stTextArea"] > div,[data-baseweb="select"] > div { background:#fff; border-radius:8px; border-color:#e4e6ee; }
.stButton button,.stFormSubmitButton button,.stDownloadButton button { border-radius:7px; font-size:12px; font-weight:600; min-height:36px; border-color:#e3e4ed; }
[data-testid="stMetric"] { background:white; border:1px solid var(--line); border-radius:10px; padding:15px 18px; }
[data-testid="stMetricLabel"] p { color:#838b9d; font-size:11px; }
[data-testid="stMetricValue"] { font-size:21px; font-weight:700; letter-spacing:-.4px; }
[data-baseweb="tab-list"] { gap:23px; border-bottom:1px solid var(--line); }
[data-baseweb="tab"] { font-size:12px; padding:14px 3px; }
[data-baseweb="tab"][aria-selected="true"] { color:#6955d9; }
[data-baseweb="tab-highlight"] { background:#6955d9; }
.status-chip { display:inline-block; padding:5px 10px; border-radius:5px; font-size:10px; font-weight:600; color:#ad7b25; background:#fff6e5; }
.status-chip.approve { color:#238063; background:#e9f7f0; }
.status-chip.reject { color:#bd5265; background:#fff0f2; }
.review-title { display:flex; justify-content:space-between; align-items:center; margin:9px 0 20px; }
.review-title h2 { margin:3px 0 0; font-size:21px; }
.review-kicker { font-size:9px; color:#9a91b0; font-weight:700; letter-spacing:1.7px; }
.report-summary { background:#f8f7fc; border:1px solid #eae6f5; border-left:3px solid #8c79dd; padding:17px 20px; border-radius:7px; margin:15px 0; }
.report-summary strong { font-size:13px; color:#4a4265; }
.report-summary p { margin:7px 0 0; color:#81768f; font-size:12px; line-height:1.7; }
.assistant-welcome { text-align:center; padding:20px 20px 30px; }
.assistant-symbol { margin:0 auto 15px; width:52px; height:52px; background:#eeeafd; color:#7561d1; border-radius:15px; display:grid; place-items:center; font-size:26px; }
.assistant-welcome h2 { font-size:24px; margin:0 0 12px; }
.assistant-welcome p { color:#8a91a3; font-size:13px; max-width:500px; margin:0 auto; line-height:1.8; }
.footer { border-top:1px solid #e6e8ef; margin-top:32px; padding-top:14px; color:#a1a7b6; font-size:10px; display:flex; justify-content:space-between; }
@media(max-width:1000px) { .block-container { padding:2rem 1.3rem; } .kpi-grid { grid-template-columns:repeat(3,1fr); } .hero-pill { display:none; } }
@media(max-width:650px) { .kpi-grid { grid-template-columns:repeat(2,1fr); } .page-top { display:block; } .date-label { display:none; } .hero { padding:20px; } .hero-title { font-size:19px; } }

.page-top h1 { padding:0; font-size:30px; }
[data-testid="stSidebarUserContent"] { padding-top:1rem; }
[data-testid="stSidebar"] .st-key-workspace_nav { width:100%; }
[data-testid="stSidebar"] [role="radiogroup"] { width:100%; }
[data-testid="stSidebar"] [role="radiogroup"] label { width:100%; flex:1; }
[data-testid="stSidebar"] [role="radiogroup"] input { accent-color:#9b88ed; }

/* Set foreground and surface together for every action state. */
:is(.stButton,.stFormSubmitButton,.stDownloadButton) button {
  background:#ffffff; color:#35415b; border-color:#d9dce6;
}
:is(.stButton,.stFormSubmitButton,.stDownloadButton) button:is(:hover,:active):not(:disabled) {
  background:#f1eefb; color:#51419d; border-color:#bfb4e7;
}
:is(.stButton,.stFormSubmitButton,.stDownloadButton) button[kind="primary"] {
  background:#6955d9; color:#ffffff; border-color:#6955d9;
}
:is(.stButton,.stFormSubmitButton,.stDownloadButton) button[kind="primary"]:is(:hover,:active):not(:disabled) {
  background:#5844c2; color:#ffffff; border-color:#5844c2;
}
:is(.stButton,.stFormSubmitButton,.stDownloadButton) button:focus-visible {
  outline:3px solid #7c65dc; outline-offset:3px; box-shadow:none;
}
:is(.stButton,.stFormSubmitButton,.stDownloadButton) button:disabled {
  background:#ebe8f3; color:#6b617f; border-color:#ddd7e9; opacity:1; cursor:not-allowed;
}
[data-testid="stSidebar"] .stButton button {
  background:#2c3148; color:#edf0ff; border-color:#49516e;
}
[data-testid="stSidebar"] .stButton button:is(:hover,:active):not(:disabled) {
  background:#3a4160; color:#ffffff; border-color:#8275b6;
}
[data-testid="stSidebar"] .stButton button:disabled {
  background:#262b3d; color:#9ea6bf; border-color:#373e56;
}
:is(.stButton,.stFormSubmitButton,.stDownloadButton) button :is(p,span),
:is(.stButton,.stFormSubmitButton,.stDownloadButton) button[kind="primary"] :is(p,span),
:is(.stButton,.stFormSubmitButton,.stDownloadButton) button:disabled :is(p,span),
:is(.stButton,.stFormSubmitButton,.stDownloadButton) button[kind="primary"]:disabled :is(p,span) {
  color:inherit;
}

</style>
"""

def inject_theme():
    st.markdown(CSS, unsafe_allow_html=True)

def chip(label, kind="review"):
    return f'<span class="status-chip {escape(kind, quote=True)}">{escape(str(label))}</span>'

def section(title, subtitle="", count=None):
    badge = f'<span class="count-pill">{count} invoices</span>' if count is not None else ""
    st.markdown(f'<div class="section-row"><div><div class="section-heading">{escape(title)}</div><div class="section-sub">{escape(subtitle)}</div></div>{badge}</div>', unsafe_allow_html=True)
