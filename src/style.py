import streamlit as st


TOPBAR_H = 88


def apply_style():
    css = f"""
    <style>
    :root {{
      --topbar-h: {TOPBAR_H}px;
      --sidebar-top-gap: 16px;
    }}

    html {{
      scroll-behavior: smooth;
    }}

    header[data-testid="stHeader"] {{
      visibility: hidden !important;
      height: 0 !important;
    }}

    header[data-testid="stHeader"] [data-testid*="Sidebar"],
    header[data-testid="stHeader"] button[aria-label*="sidebar"],
    header[data-testid="stHeader"] button[title*="sidebar"],
    header[data-testid="stHeader"] button[kind="headerNoPadding"]{{
      visibility: visible !important;
      opacity: 1 !important;
      pointer-events: auto !important;
    }}

    footer {{
      visibility: hidden !important;
    }}

    div[data-testid="stAppViewContainer"] {{
      overflow-x: clip !important;
    }}

    div[data-testid="stAppViewContainer"] .main .block-container{{
      padding-top: calc(var(--topbar-h) + 42px) !important;
      padding-bottom: 64px !important;
      max-width: 1400px !important;
      margin-left: auto !important;
      margin-right: auto !important;
      padding-left: 1.85rem !important;
      padding-right: 1.85rem !important;
    }}

    section[data-testid="stSidebar"]{{
      top: var(--topbar-h) !important;
      height: calc(100vh - var(--topbar-h)) !important;
      background: linear-gradient(180deg, #F8FAFD 0%, #F3F6FB 100%) !important;
      border-right: 1px solid rgba(15,23,42,0.06) !important;
    }}

    section[data-testid="stSidebar"] > div{{
      padding-top: var(--sidebar-top-gap) !important;
      height: 100% !important;
      overflow-y: auto !important;
      overflow-x: hidden !important;
    }}

    section[data-testid="stSidebar"] [data-testid="stVerticalBlock"] > div{{
      gap: 0.50rem !important;
    }}

    #top-hero {{
      position: fixed;
      top: 0;
      left: 0;
      right: 0;
      height: var(--topbar-h);
      z-index: 9999;
      display: flex;
      align-items: center;
      pointer-events: none;
      background:
        radial-gradient(circle at 10% 12%, rgba(255,255,255,0.14), transparent 18%),
        radial-gradient(circle at 90% 18%, rgba(255,255,255,0.12), transparent 16%),
        linear-gradient(135deg, #4338CA 0%, #6366F1 45%, #0EA5E9 100%);
      box-shadow: 0 16px 40px rgba(67,56,202,0.20);
      border-bottom: 1px solid rgba(255,255,255,0.12);
      backdrop-filter: blur(16px);
    }}

    #top-hero .inner {{
      width: 100%;
      max-width: 1400px;
      margin: 0 auto;
      padding: 0 1.85rem;
      color: white;
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 18px;
      pointer-events: auto;
    }}

    #top-hero .brand-wrap {{
      display:flex;
      flex-direction:column;
      justify-content:center;
      gap:4px;
      min-width:0;
    }}

    #top-hero .eyebrow {{
      display:inline-flex;
      width:fit-content;
      align-items:center;
      gap:8px;
      padding:6px 10px;
      border-radius:999px;
      background:rgba(255,255,255,0.12);
      border:1px solid rgba(255,255,255,0.16);
      font-size:11px;
      font-weight:800;
      letter-spacing:0.08em;
      text-transform:uppercase;
      white-space:nowrap;
    }}

    #top-hero .title {{
      font-size:26px;
      font-weight:900;
      line-height: 1.05;
      margin: 0;
      color: #fff;
      letter-spacing:-0.03em;
      white-space:nowrap;
      overflow:hidden;
      text-overflow:ellipsis;
    }}

    #top-hero .sub {{
      font-size: 13px;
      font-weight: 600;
      color: rgba(255,255,255,0.88);
      white-space:nowrap;
      overflow:hidden;
      text-overflow:ellipsis;
    }}

    #top-hero .hero-right {{
      display:flex;
      align-items:center;
      gap:10px;
      flex-shrink:0;
    }}

    #top-hero .hero-pill {{
      display:inline-flex;
      align-items:center;
      gap:8px;
      padding:9px 12px;
      border-radius:999px;
      background:rgba(255,255,255,0.12);
      border:1px solid rgba(255,255,255,0.16);
      color:#fff;
      font-size:12px;
      font-weight:700;
      white-space:nowrap;
    }}

    .card {{
      background: #ffffff;
      border-radius: 22px;
      padding: 24px;
      box-shadow: 0 12px 28px rgba(0,0,0,0.06);
      border: 1px solid rgba(15,23,42,0.07);
    }}

    .card-muted {{
      background: linear-gradient(145deg, rgba(79,70,229,0.08), rgba(14,165,233,0.06));
      border: 1px solid rgba(79,70,229,0.14);
      border-radius: 18px;
      padding: 15px 16px;
    }}

    .label{{
      font-size:12px;
      font-weight:800;
      letter-spacing:0.08em;
      text-transform:uppercase;
      color:#475569;
      margin-bottom:8px;
    }}

    .hr{{
      height:1px;
      margin:14px 0;
      background:rgba(15,23,42,0.10);
    }}

    [data-testid="stSidebarCollapsedControl"],
    button[aria-label="Open sidebar"],
    button[title="Open sidebar"],
    button[aria-label*="Open sidebar"],
    button[title*="Open sidebar"]{{
      position: fixed !important;
      top: calc(var(--topbar-h) + 14px) !important;
      left: 14px !important;
      z-index: 10001 !important;
      visibility: visible !important;
      opacity: 1 !important;
      pointer-events: auto !important;
    }}

    div[data-testid="stForm"],
    div[data-testid="stExpander"],
    .stAlert,
    div[data-testid="stMetric"]{{
      border-radius:18px !important;
    }}

    .stButton > button,
    .stDownloadButton > button{{
      border-radius:14px !important;
      min-height:46px !important;
      font-weight:800 !important;
      letter-spacing:-0.01em;
      border:1px solid rgba(15,23,42,0.08) !important;
      box-shadow:0 8px 20px rgba(15,23,42,0.05);
      transition: transform .14s ease, box-shadow .14s ease, border-color .14s ease !important;
    }}

    .stButton > button:hover,
    .stDownloadButton > button:hover{{
      transform: translateY(-1px);
      box-shadow:0 12px 24px rgba(15,23,42,0.08);
      border-color:rgba(79,70,229,0.18) !important;
    }}

    .stTextInput > div > div > input,
    .stSelectbox > div > div,
    .stTextArea textarea{{
      border-radius:14px !important;
    }}

    .stTabs [data-baseweb="tab-list"]{{
      gap: 6px;
      overflow-x: auto;
      scrollbar-width: none;
    }}

    .stTabs [data-baseweb="tab"]{{
      height: 42px;
      padding: 0 14px;
      border-radius: 12px 12px 0 0;
      white-space: nowrap;
    }}

    .stPlotlyChart > div{{
      border-radius: 18px;
      overflow: hidden;
    }}

    .stDataFrame, .stTable{{
      border-radius:18px !important;
      overflow:hidden !important;
    }}

    @media (max-width: 1200px){{
      div[data-testid="stAppViewContainer"] .main .block-container{{
        padding-left: 1.2rem !important;
        padding-right: 1.2rem !important;
      }}
    }}

    @media (max-width: 1024px){{
      :root {{
        --topbar-h: 76px;
      }}

      #top-hero .inner{{
        align-items:center;
      }}

      #top-hero .hero-right{{
        display:none;
      }}

      #top-hero .title{{
        font-size:22px;
      }}

      #top-hero .sub{{
        display:none;
      }}

      div[data-testid="stAppViewContainer"] .main .block-container{{
        padding-top: calc(var(--topbar-h) + 28px) !important;
      }}
    }}

    @media (max-width: 768px){{
      div[data-testid="stAppViewContainer"] .main .block-container{{
        padding-left: 0.95rem !important;
        padding-right: 0.95rem !important;
        padding-top: calc(var(--topbar-h) + 22px) !important;
      }}
    }}
    </style>
    """
    st.markdown(css, unsafe_allow_html=True)


def render_top_hero(title: str, subtitle: str):
    st.markdown(
        f"""
        <div id="top-hero">
          <div class="inner">
            <div class="brand-wrap">
              <div class="eyebrow">AI CRM Intelligence</div>
              <div class="title">{title}</div>
              <div class="sub">{subtitle}</div>
            </div>
            <div class="hero-right">
              <div class="hero-pill">실시간 업로드 기반 분석</div>
              <div class="hero-pill">RFM · Churn · Action Plan</div>
            </div>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
