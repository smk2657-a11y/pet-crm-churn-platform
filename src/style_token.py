import streamlit as st


def apply_design_tokens():
    css = """
    <style>
    /* ═══════════════════════════════════════════════════
       DESIGN TOKENS
    ═══════════════════════════════════════════════════ */
    :root {
        --primary: #4F46E5;
        --primary-2: #6366F1;
        --primary-3: #8B5CF6;
        --accent: #0EA5E9;
        --accent-2: #14B8A6;
        --ink: #0F172A;
        --ink-2: #1E293B;
        --muted: #64748B;
        --muted-2: #94A3B8;
        --line: rgba(15, 23, 42, 0.07);
        --line-strong: rgba(79, 70, 229, 0.16);
        --bg-main: #F4F7FB;
        --bg-card: #FFFFFF;
        --bg-soft: #F8FAFC;
        --bg-tint: #EEF2FF;
        --bg-elev: #F8FAFF;
        --success: #16A34A;
        --warning: #D97706;
        --danger: #DC2626;
        --radius-2xl: 28px;
        --radius-xl: 22px;
        --radius-lg: 18px;
        --radius-md: 14px;
        --radius-sm: 10px;
        --shadow-soft: 0 16px 40px rgba(15, 23, 42, 0.06);
        --shadow-card: 0 6px 24px rgba(15, 23, 42, 0.06);
        --shadow-strong: 0 18px 48px rgba(79, 70, 229, 0.12);
        --gradient-main: linear-gradient(135deg, #4F46E5 0%, #7C3AED 52%, #0EA5E9 100%);
        --gradient-soft: linear-gradient(180deg, rgba(255,255,255,0.99) 0%, rgba(246,249,255,0.99) 100%);
        --gradient-panel: linear-gradient(135deg, rgba(79,70,229,0.07) 0%, rgba(14,165,233,0.06) 100%);
        --transition: 0.18s ease;
    }

    /* ═══════════════════════════════════════════════════
       BASE TYPOGRAPHY
    ═══════════════════════════════════════════════════ */
    html, body, [class*="css"] {
        font-family: "Pretendard", "Inter", "Apple SD Gothic Neo", "Malgun Gothic", sans-serif;
        -webkit-font-smoothing: antialiased;
    }

    /* ═══════════════════════════════════════════════════
       APP BACKGROUND
    ═══════════════════════════════════════════════════ */
    div[data-testid="stAppViewContainer"] {
        background:
            radial-gradient(circle at 8% 10%, rgba(99, 102, 241, 0.07), transparent 26%),
            radial-gradient(circle at 92% 10%, rgba(14, 165, 233, 0.07), transparent 24%),
            linear-gradient(180deg, #F7F9FC 0%, #F4F7FB 100%);
    }

    /* ═══════════════════════════════════════════════════
       PAGE HERO TEXT
    ═══════════════════════════════════════════════════ */
    .page-eyebrow {
        display: inline-flex;
        align-items: center;
        gap: 8px;
        padding: 7px 13px;
        border-radius: 999px;
        background: rgba(79, 70, 229, 0.09);
        border: 1px solid rgba(79, 70, 229, 0.14);
        color: var(--primary);
        font-size: 11px;
        font-weight: 800;
        letter-spacing: 0.08em;
        text-transform: uppercase;
        margin-bottom: 12px;
    }

    .page-title {
        font-size: clamp(30px, 3.5vw, 52px);
        line-height: 1.04;
        font-weight: 900;
        letter-spacing: -0.04em;
        color: var(--ink);
        margin: 0;
        word-break: keep-all;
    }

    .page-subtitle {
        font-size: 14px;
        line-height: 1.85;
        color: var(--muted);
        margin: 12px 0 0 0;
        max-width: 820px;
    }

    /* ═══════════════════════════════════════════════════
       SECTION HEADERS
    ═══════════════════════════════════════════════════ */
    .section-kicker {
        font-size: 11px;
        color: var(--primary);
        font-weight: 800;
        letter-spacing: 0.10em;
        text-transform: uppercase;
        margin-bottom: 7px;
    }

    .section-title {
        font-size: 26px;
        line-height: 1.1;
        font-weight: 900;
        letter-spacing: -0.03em;
        color: var(--ink);
        margin: 0;
        word-break: keep-all;
    }

    .section-desc {
        margin-top: 8px;
        color: var(--muted);
        font-size: 14px;
        line-height: 1.8;
        max-width: 860px;
    }

    /* ═══════════════════════════════════════════════════
       CARDS & SHELLS
    ═══════════════════════════════════════════════════ */
    .workspace-shell,
    .panel-shell,
    .card-pro {
        background: var(--gradient-soft);
        border: 1px solid var(--line);
        border-radius: var(--radius-2xl);
        box-shadow: var(--shadow-card);
        padding: 22px 24px;
        margin-bottom: 16px;
        backdrop-filter: blur(6px);
    }

    .card-soft {
        background: var(--bg-soft);
        border: 1px solid var(--line);
        border-radius: var(--radius-lg);
        padding: 16px 18px;
    }

    .workspace-panel {
        background: linear-gradient(145deg, rgba(255,255,255,0.98) 0%, rgba(244,247,255,0.98) 100%);
        border: 1px solid var(--line);
        border-radius: 24px;
        padding: 20px 22px;
        box-shadow: var(--shadow-card);
    }

    /* ═══════════════════════════════════════════════════
       BADGES & CHIPS
    ═══════════════════════════════════════════════════ */
    .workspace-badge,
    .mode-badge {
        display: inline-flex;
        align-items: center;
        gap: 7px;
        padding: 6px 12px;
        border-radius: 999px;
        background: rgba(79, 70, 229, 0.08);
        color: var(--primary);
        border: 1px solid rgba(79, 70, 229, 0.13);
        font-size: 11px;
        font-weight: 800;
        margin-bottom: 10px;
        letter-spacing: 0.04em;
    }

    .workspace-title {
        font-size: 15px;
        font-weight: 800;
        color: var(--ink);
        margin: 4px 0 12px;
        line-height: 1.45;
    }

    .workspace-sub {
        font-size: 13px;
        color: var(--muted);
        line-height: 1.65;
        margin-bottom: 14px;
    }

    /* ═══════════════════════════════════════════════════
       STATUS CHIPS
    ═══════════════════════════════════════════════════ */
    .status-inline {
        display: flex;
        flex-wrap: wrap;
        gap: 8px;
        margin-top: 14px;
    }

    .status-chip {
        display: inline-flex;
        align-items: center;
        gap: 7px;
        padding: 7px 12px;
        border-radius: 999px;
        border: 1px solid var(--line);
        background: #fff;
        color: var(--ink-2);
        font-size: 12px;
        font-weight: 700;
        white-space: nowrap;
        transition: all var(--transition);
    }

    .status-chip.active {
        border-color: rgba(79, 70, 229, 0.22);
        background: rgba(79, 70, 229, 0.08);
        color: var(--primary);
    }

    /* ═══════════════════════════════════════════════════
       STEP MINI CARDS
    ═══════════════════════════════════════════════════ */
    .hero-mini-card {
        background: linear-gradient(180deg, rgba(255,255,255,0.98) 0%, rgba(248,250,255,0.97) 100%);
        border: 1px solid rgba(15, 23, 42, 0.06);
        box-shadow: 0 8px 24px rgba(15, 23, 42, 0.05);
        border-radius: 22px;
        padding: 18px 20px;
        min-height: 124px;
        transition: transform var(--transition), box-shadow var(--transition);
    }

    .hero-mini-card:hover {
        transform: translateY(-2px);
        box-shadow: 0 12px 32px rgba(15, 23, 42, 0.08);
    }

    .hero-mini-label {
        font-size: 11px;
        color: var(--muted);
        font-weight: 800;
        letter-spacing: 0.08em;
        text-transform: uppercase;
    }

    .hero-mini-value {
        margin-top: 11px;
        font-size: 24px;
        font-weight: 900;
        color: var(--ink);
        letter-spacing: -0.03em;
        line-height: 1.1;
    }

    .hero-mini-foot {
        margin-top: 9px;
        color: var(--muted);
        font-size: 13px;
        line-height: 1.6;
    }

    /* ═══════════════════════════════════════════════════
       KPI CARDS
    ═══════════════════════════════════════════════════ */
    .kpi-shell {
        background: linear-gradient(180deg, #FFFFFF 0%, #FBFDFF 100%);
        border: 1px solid var(--line);
        border-radius: 24px;
        padding: 22px 20px 18px;
        box-shadow: var(--shadow-card);
        min-height: 150px;
        position: relative;
        overflow: hidden;
        transition: transform var(--transition), box-shadow var(--transition);
    }

    .kpi-shell:hover {
        transform: translateY(-2px);
        box-shadow: 0 12px 36px rgba(15, 23, 42, 0.09);
    }

    .kpi-shell::before {
        content: "";
        position: absolute;
        inset: 0 auto auto 0;
        width: 100%;
        height: 3px;
        background: var(--gradient-main);
        opacity: 0.9;
    }

    .kpi-shell .kpi-label {
        font-size: 11px;
        font-weight: 800;
        color: var(--muted);
        letter-spacing: 0.06em;
        text-transform: uppercase;
    }

    .kpi-shell .kpi-value {
        margin-top: 16px;
        font-size: clamp(26px, 2.8vw, 40px);
        line-height: 1.06;
        font-weight: 900;
        letter-spacing: -0.04em;
        color: var(--ink);
        overflow-wrap: anywhere;
        word-break: break-word;
    }

    .kpi-shell .kpi-foot {
        margin-top: 10px;
        font-size: 12px;
        line-height: 1.7;
        color: var(--muted);
    }

    /* ═══════════════════════════════════════════════════
       INSIGHT PANEL
    ═══════════════════════════════════════════════════ */
    .insight-panel {
        border: 1px solid var(--line);
        background: linear-gradient(135deg, rgba(79,70,229,0.05), rgba(14,165,233,0.05));
        border-radius: 22px;
        padding: 18px 20px;
        box-shadow: var(--shadow-card);
    }

    .bullet-list {
        margin: 10px 0 0 0;
        padding-left: 18px;
        color: var(--muted);
        line-height: 1.85;
        font-size: 14px;
    }

    .bullet-list li + li {
        margin-top: 4px;
    }

    /* ═══════════════════════════════════════════════════
       METRIC PILL
    ═══════════════════════════════════════════════════ */
    .metric-pill {
        display: inline-flex;
        align-items: center;
        gap: 6px;
        padding: 4px 10px;
        border-radius: 999px;
        background: rgba(15, 23, 42, 0.06);
        color: #334155;
        font-size: 11px;
        font-weight: 700;
    }

    /* ═══════════════════════════════════════════════════
       CHART CARD
    ═══════════════════════════════════════════════════ */
    .chart-shell {
        background: var(--bg-card);
        border: 1px solid var(--line);
        border-radius: 24px;
        padding: 18px 18px 4px;
        box-shadow: var(--shadow-card);
        margin-bottom: 16px;
        overflow: hidden;
    }

    .chart-head {
        display: flex;
        flex-wrap: wrap;
        gap: 10px;
        align-items: flex-start;
        justify-content: space-between;
        margin-bottom: 6px;
    }

    .chart-head-left {
        min-width: 0;
        flex: 1 1 240px;
    }

    .chart-title {
        font-size: 16px;
        font-weight: 800;
        color: var(--ink);
        line-height: 1.4;
        margin: 0;
    }

    .chart-desc {
        margin-top: 4px;
        color: var(--muted);
        font-size: 12px;
        line-height: 1.65;
    }

    /* ═══════════════════════════════════════════════════
       ACTION CARDS
    ═══════════════════════════════════════════════════ */
    .action-card {
        background: linear-gradient(180deg, #FFFFFF 0%, #FAFCFF 100%);
        border: 1px solid var(--line);
        border-left: 4px solid var(--primary);
        border-radius: 20px;
        padding: 16px 18px;
        box-shadow: var(--shadow-card);
        margin-bottom: 12px;
        transition: transform var(--transition), box-shadow var(--transition);
    }

    .action-card:hover {
        transform: translateX(2px);
        box-shadow: 0 10px 28px rgba(15, 23, 42, 0.08);
    }

    .action-title {
        font-size: 14px;
        font-weight: 800;
        color: var(--ink);
        margin-bottom: 6px;
        line-height: 1.45;
    }

    .action-body {
        color: var(--muted);
        font-size: 13px;
        line-height: 1.75;
    }

    /* ═══════════════════════════════════════════════════
       TABLE
    ═══════════════════════════════════════════════════ */
    .table-caption {
        font-size: 12px;
        color: var(--muted);
        font-weight: 700;
        margin-bottom: 8px;
        letter-spacing: 0.02em;
    }

    /* ═══════════════════════════════════════════════════
       EMPTY HERO
    ═══════════════════════════════════════════════════ */
    .empty-hero {
        border: 1px solid var(--line);
        background: linear-gradient(135deg, rgba(255,255,255,0.98), rgba(243,247,255,0.98));
        border-radius: 32px;
        box-shadow: var(--shadow-soft);
        padding: 44px 44px 38px;
        min-height: 360px;
    }

    .empty-badge {
        display: inline-flex;
        align-items: center;
        gap: 8px;
        padding: 8px 14px;
        border-radius: 999px;
        background: rgba(79, 70, 229, 0.09);
        color: var(--primary);
        border: 1px solid rgba(79, 70, 229, 0.13);
        font-size: 11px;
        font-weight: 800;
        letter-spacing: 0.08em;
        text-transform: uppercase;
    }

    .empty-title {
        margin-top: 22px;
        font-size: clamp(24px, 2.35vw, 38px);
        line-height: 1.14;
        letter-spacing: -0.035em;
        font-weight: 900;
        color: var(--ink);
        max-width: 1280px;
        width: 100%;
        word-break: keep-all;
        white-space: nowrap;
    }

    .empty-desc {
        margin-top: 16px;
        max-width: 1100px;
        color: var(--muted);
        font-size: 14px;
        line-height: 1.8;
    }

    .empty-grid {
        display: grid;
        grid-template-columns: repeat(3, minmax(0, 1fr));
        gap: 14px;
        margin-top: 26px;
    }

    .empty-feature {
        background: #fff;
        border: 1px solid var(--line);
        border-radius: 20px;
        padding: 18px;
        box-shadow: var(--shadow-card);
        min-width: 0;
        transition: transform var(--transition);
    }

    .empty-feature:hover {
        transform: translateY(-2px);
    }

    .empty-feature-title {
        font-size: 14px;
        font-weight: 800;
        color: var(--ink);
        margin-bottom: 8px;
    }

    .empty-feature-desc {
        color: var(--muted);
        font-size: 13px;
        line-height: 1.75;
    }

    /* ═══════════════════════════════════════════════════
       SIDEBAR
    ═══════════════════════════════════════════════════ */
    .sidebar-upload-card,
    .sidebar-guide-card {
        background: linear-gradient(180deg, rgba(255,255,255,0.97), rgba(248,250,255,0.97));
        border: 1px solid var(--line);
        border-radius: 20px;
        padding: 16px 15px;
        box-shadow: 0 6px 20px rgba(15, 23, 42, 0.04);
        margin-bottom: 12px;
    }

    .sidebar-card-kicker {
        font-size: 11px;
        font-weight: 800;
        letter-spacing: 0.08em;
        text-transform: uppercase;
        color: var(--primary);
        margin-bottom: 8px;
    }

    .sidebar-card-title {
        font-size: 15px;
        font-weight: 900;
        line-height: 1.45;
        color: var(--ink);
    }

    .sidebar-card-desc {
        margin-top: 8px;
        font-size: 12px;
        line-height: 1.8;
        color: var(--muted);
    }

    .sidebar-divider {
        display: flex;
        align-items: center;
        gap: 10px;
        margin: 12px 0 14px;
        color: var(--muted-2);
        font-size: 11px;
        font-weight: 800;
        letter-spacing: 0.08em;
    }

    .sidebar-divider::before,
    .sidebar-divider::after {
        content: "";
        flex: 1;
        height: 1px;
        background: rgba(15, 23, 42, 0.09);
    }

    .sidebar-history-item {
        display: block;
        padding: 11px 13px;
        border-radius: 14px;
        background: #fff;
        border: 1px solid var(--line);
        font-size: 12px;
        line-height: 1.55;
        color: var(--ink-2);
        box-shadow: 0 4px 14px rgba(15, 23, 42, 0.04);
        margin-bottom: 7px;
        word-break: keep-all;
    }

    .sidebar-note {
        color: var(--muted);
        font-size: 12px;
        line-height: 1.7;
    }

    /* ═══════════════════════════════════════════════════
       UTILITY
    ═══════════════════════════════════════════════════ */
    .workspace-divider {
        height: 1px;
        background: rgba(15, 23, 42, 0.07);
        margin: 14px 0 16px;
    }

    .section-gap {
        height: 10px;
    }

    .label {
        font-size: 11px;
        font-weight: 800;
        letter-spacing: 0.08em;
        text-transform: uppercase;
        color: var(--muted);
        margin-bottom: 8px;
        padding: 2px 0;
    }

    .hr {
        height: 1px;
        margin: 14px 0;
        background: rgba(15, 23, 42, 0.09);
    }

    /* ═══════════════════════════════════════════════════
       STREAMLIT OVERRIDES
    ═══════════════════════════════════════════════════ */
    div[data-testid="stForm"],
    div[data-testid="stExpander"],
    .stAlert {
        border-radius: 18px !important;
    }

    .stButton > button,
    .stDownloadButton > button {
        border-radius: 13px !important;
        min-height: 44px !important;
        font-weight: 800 !important;
        letter-spacing: -0.01em;
        border: 1px solid rgba(15, 23, 42, 0.08) !important;
        box-shadow: 0 4px 14px rgba(15, 23, 42, 0.05);
        transition: transform var(--transition), box-shadow var(--transition), border-color var(--transition) !important;
        font-size: 14px !important;
    }

    .stButton > button:hover,
    .stDownloadButton > button:hover {
        transform: translateY(-1px);
        box-shadow: 0 8px 22px rgba(15, 23, 42, 0.09);
        border-color: rgba(79, 70, 229, 0.20) !important;
    }

    .stButton > button:active,
    .stDownloadButton > button:active {
        transform: translateY(0);
        box-shadow: 0 2px 8px rgba(15, 23, 42, 0.06);
    }

    .stButton > button[kind="primary"],
    .stDownloadButton > button[kind="primary"] {
        background: linear-gradient(135deg, #4F46E5, #6366F1) !important;
        border-color: transparent !important;
    }

    .stTextInput > div > div > input,
    .stSelectbox > div > div,
    .stTextArea textarea {
        border-radius: 13px !important;
    }

    .stTabs [data-baseweb="tab-list"] {
        gap: 5px;
        overflow-x: auto;
        scrollbar-width: none;
        padding-bottom: 2px;
    }

    .stTabs [data-baseweb="tab-list"]::-webkit-scrollbar {
        display: none;
    }

    .stTabs [data-baseweb="tab"] {
        height: 40px;
        padding: 0 15px;
        border-radius: 11px 11px 0 0;
        white-space: nowrap;
        font-weight: 700;
        font-size: 13px;
    }

    .stPlotlyChart > div {
        border-radius: 16px;
        overflow: hidden;
    }

    .stDataFrame,
    .stTable {
        border-radius: 16px !important;
        overflow: hidden !important;
    }

    div[data-testid="stMetric"] {
        border-radius: 16px !important;
    }

    details[data-testid="stExpander"] > summary {
        border-radius: 14px !important;
        font-weight: 700;
    }

    .side-section-title {
        font-size: 12px;
        font-weight: 800;
        letter-spacing: 0.06em;
        text-transform: uppercase;
        color: var(--muted);
        margin: 12px 0 8px;
        padding: 0 2px;
    }

    .step-section-label {
        display: inline-flex;
        align-items: center;
        gap: 8px;
        font-size: 13px;
        font-weight: 800;
        color: var(--primary);
        letter-spacing: 0.04em;
        text-transform: uppercase;
        margin: 20px 0 8px;
        padding: 6px 12px;
        border-radius: 999px;
        background: rgba(79, 70, 229, 0.07);
        border: 1px solid rgba(79, 70, 229, 0.12);
    }

    .step-section-title {
        font-size: 22px;
        font-weight: 900;
        letter-spacing: -0.03em;
        color: var(--ink);
        margin: 6px 0 4px;
    }

    .step-section-desc {
        font-size: 13px;
        color: var(--muted);
        line-height: 1.7;
        margin-bottom: 16px;
    }

    .quality-header-card {
        border-radius: 22px;
        padding: 24px 26px;
        margin: 8px 0 18px;
    }

    .info-banner {
        border: 1px solid rgba(59, 130, 246, 0.18);
        background: rgba(59, 130, 246, 0.05);
        border-radius: 16px;
        padding: 14px 16px;
        font-size: 13px;
        line-height: 1.75;
        color: var(--ink-2);
        margin: 10px 0;
    }

    .warn-banner {
        border: 1px solid rgba(245, 158, 11, 0.22);
        background: rgba(245, 158, 11, 0.07);
        border-radius: 16px;
        padding: 14px 16px;
        font-size: 13px;
        line-height: 1.75;
        color: var(--ink-2);
        margin: 10px 0;
    }

    .danger-banner {
        border: 1px solid rgba(239, 68, 68, 0.18);
        background: rgba(239, 68, 68, 0.05);
        border-radius: 16px;
        padding: 14px 16px;
        font-size: 13px;
        line-height: 1.75;
        color: var(--ink-2);
        margin: 10px 0;
    }

    .success-banner {
        border: 1px solid rgba(22, 163, 74, 0.18);
        background: rgba(22, 163, 74, 0.06);
        border-radius: 16px;
        padding: 14px 16px;
        font-size: 13px;
        line-height: 1.75;
        color: var(--ink-2);
        margin: 10px 0;
    }

    /* ═══════════════════════════════════════════════════
       LOADING OVERLAY
    ═══════════════════════════════════════════════════ */
    .loading-overlay {
        position: fixed;
        inset: 0;
        z-index: 99999;
        background: rgba(15, 23, 42, 0.22);
        backdrop-filter: blur(6px);
        display: flex;
        align-items: center;
        justify-content: center;
    }

    .loading-modal {
        width: min(460px, 92vw);
        background: linear-gradient(180deg, rgba(255,255,255,0.98), rgba(248,250,255,0.98));
        border: 1px solid rgba(79, 70, 229, 0.14);
        border-radius: 24px;
        box-shadow: 0 24px 70px rgba(15, 23, 42, 0.18);
        padding: 26px 24px 22px;
        text-align: center;
    }

    .loading-badge {
        display: inline-flex;
        align-items: center;
        gap: 8px;
        padding: 6px 12px;
        border-radius: 999px;
        background: rgba(79, 70, 229, 0.08);
        border: 1px solid rgba(79, 70, 229, 0.14);
        color: var(--primary);
        font-size: 11px;
        font-weight: 800;
        letter-spacing: 0.08em;
        text-transform: uppercase;
    }

    .loading-title {
        margin-top: 16px;
        font-size: 28px;
        font-weight: 900;
        letter-spacing: -0.03em;
        color: var(--ink);
        line-height: 1.2;
    }

    .loading-desc {
        margin-top: 10px;
        font-size: 14px;
        color: var(--muted);
        line-height: 1.75;
    }

    .loading-dots {
        margin: 18px auto 0;
        display: flex;
        justify-content: center;
        gap: 8px;
    }

    .loading-dots span {
        width: 10px;
        height: 10px;
        border-radius: 999px;
        background: linear-gradient(135deg, #4F46E5, #0EA5E9);
        animation: loading-bounce 1.2s infinite ease-in-out;
    }

    .loading-dots span:nth-child(2) {
        animation-delay: 0.15s;
    }

    .loading-dots span:nth-child(3) {
        animation-delay: 0.30s;
    }

    @keyframes loading-bounce {
        0%, 80%, 100% {
            transform: scale(0.7);
            opacity: 0.45;
        }
        40% {
            transform: scale(1);
            opacity: 1;
        }
    }

    /* ═══════════════════════════════════════════════════
       RESPONSIVE
    ═══════════════════════════════════════════════════ */
    @media (max-width: 1200px) {
        .empty-grid {
            grid-template-columns: 1fr;
        }
    }

    @media (max-width: 992px) {
        .page-title,
        .empty-title,
        .section-title {
            word-break: keep-all;
        }

        .empty-title {
            white-space: normal;
            font-size: clamp(24px, 5.8vw, 34px);
            line-height: 1.16;
        }

        .workspace-shell,
        .panel-shell,
        .card-pro,
        .empty-hero {
            padding: 18px;
        }

        .hero-mini-card,
        .kpi-shell,
        .chart-shell {
            min-height: auto;
        }
    }
    </style>
    """
    st.markdown(css, unsafe_allow_html=True)