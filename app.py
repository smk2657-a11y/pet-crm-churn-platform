import pandas as pd
import streamlit as st

from src.auth import login_gate, logout_user, restore_auth_from_session, signup_form
from src.data_io import load_csv_or_sample_sidebar
from src.free_ui import free_report_step
from src.mapping_ui import mapping_step
from src.report_ui import report_step
from src.storage import init_db, list_runs, activate_pro_membership, get_user_membership_status
from src.style import apply_style, render_top_hero
from src.style_token import apply_design_tokens


st.set_page_config(
    page_title="Pet Commerce Analytics Churn & RFM Dashboard",
    page_icon="🐾",
    layout="wide",
    initial_sidebar_state="expanded",
)

init_db()
restore_auth_from_session()
apply_style()
apply_design_tokens()
render_top_hero("Pet Commerce Analytics", "AI-powered CRM dashboard for churn, segment, and action planning")

DIALOG = getattr(st, "dialog", None) or getattr(st, "experimental_dialog", None)

for key, value in {
    "user_key": "guest",
    "auth_token": None,
    "service_mode": "free",
    "pro_paid": False,
    "pro_expires_at": None,
    "pro_days_left": 0,
    "modal": None,
    "step": 0,
    "view_run_id": None,
    "sidebar_run_pick": "현재 분석",
    "df_raw": None,
    "df_std": None,
    "upload_period_days": None,
    "upload_short_period_warning": False,
    "upload_short_period_message": "",
    "analysis_ready": False,
    "prev_step": 0,
    "show_report_loading_overlay": False,
}.items():
    st.session_state.setdefault(key, value)


def _fmt_saved_at(x) -> str:
    try:
        if x is None or str(x).strip() == "":
            return "저장일시 없음"
        return pd.to_datetime(x).strftime("%Y-%m-%d %H:%M")
    except Exception:
        return str(x) if x is not None else "저장일시 없음"


def _make_run_label(run: dict) -> str:
    title = str((run.get("run_name") or "")).strip() or "저장 분석"
    return f"{title} · {_fmt_saved_at(run.get('created_at', ''))}"


def _clear_saved_run_view():
    st.session_state["view_run_id"] = None
    st.session_state["sidebar_run_pick"] = "현재 분석"


def _go_home():
    st.session_state["step"] = 0
    st.session_state["view_run_id"] = None
    st.session_state["sidebar_run_pick"] = "현재 분석"
    st.session_state["df_raw"] = None
    st.session_state["df_std"] = None
    st.session_state["analysis_ready"] = False
    st.session_state["prev_step"] = 0
    st.session_state["show_report_loading_overlay"] = False
    st.session_state.pop("analysis_saved", None)
    st.rerun()


def _render_sidebar_home_button():
    if st.session_state.get("step", 0) >= 1:
        with st.sidebar:
            st.markdown('<div class="side-section-title">🏠 홈으로</div>', unsafe_allow_html=True)
            if st.button("메인화면으로 돌아가기", key="sidebar_go_home", use_container_width=True):
                _go_home()


def _start_new_analysis(df: pd.DataFrame):
    st.session_state["df_raw"] = df
    st.session_state["df_std"] = None
    st.session_state["mapping_confirmed"] = False
    st.session_state["quality_result"] = None
    st.session_state["analysis_ready"] = False
    st.session_state.pop("analysis_saved", None)
    _clear_saved_run_view()
    st.session_state["step"] = 1


def render_recent_saved_runs_sidebar():
    user_key = st.session_state.get("user_key", "guest")
    is_logged_in = user_key != "guest"

    with st.sidebar:
        st.markdown('<div class="label">빠른 접근</div>', unsafe_allow_html=True)
        if not is_logged_in:
            st.markdown('<div class="sidebar-note">로그인하면 최근 저장한 분석을 여기서 바로 불러올 수 있습니다.</div>', unsafe_allow_html=True)
            return

        try:
            runs = list_runs(user_key)
        except Exception as e:
            st.caption("저장 기록을 불러오지 못했습니다.")
            st.exception(e)
            return

        if not runs:
            st.markdown('<div class="sidebar-note">저장된 분석이 없습니다.</div>', unsafe_allow_html=True)
            return

        for r in runs[:5]:
            rid = r.get("run_id")
            label = _make_run_label(r)
            st.markdown(f'<div class="sidebar-history-item">{label}</div>', unsafe_allow_html=True)
            if rid is not None and st.button("열기", key=f"recent_run_{rid}", use_container_width=True):
                st.session_state["view_run_id"] = rid
                st.session_state["sidebar_run_pick"] = rid
                st.session_state["step"] = 2
                st.rerun()


render_recent_saved_runs_sidebar()
_render_sidebar_home_button()


# 로그인 상태라면 DB 기준으로 Pro 상태를 복원합니다.
if st.session_state.get("user_key", "guest") != "guest":
    _member_status = get_user_membership_status(st.session_state["user_key"])
    st.session_state["pro_paid"] = bool(_member_status.get("is_pro", False))
    st.session_state["service_mode"] = _member_status.get("service_mode", "free")
    st.session_state["pro_expires_at"] = _member_status.get("pro_expires_at")
    st.session_state["pro_days_left"] = _member_status.get("days_left", 0)



def _render_login_ui():
    authed, _, username = login_gate()
    if authed and username:
        st.session_state["user_key"] = username
        st.session_state["modal"] = None
        st.success("로그인 완료!")
        st.rerun()
    c1, c2 = st.columns(2)
    if c1.button("닫기", use_container_width=True):
        st.session_state["modal"] = None
        st.rerun()
    if c2.button("회원가입으로", use_container_width=True):
        st.session_state["modal"] = "signup"
        st.rerun()


def _render_signup_ui():
    signup_form()
    if st.button("닫기", use_container_width=True):
        st.session_state["modal"] = None
        st.rerun()


def _render_logout_ui():
    st.write("정말 로그아웃할까요?")
    c1, c2 = st.columns(2)
    if c1.button("취소", use_container_width=True):
        st.session_state["modal"] = None
        st.rerun()
    if c2.button("로그아웃", type="primary", use_container_width=True):
        logout_user()
        st.session_state["modal"] = None
        st.session_state["service_mode"] = "free"
        st.session_state["pro_paid"] = False
        st.session_state["view_run_id"] = None
        st.session_state["sidebar_run_pick"] = "현재 분석"
        st.session_state["df_raw"] = None
        st.session_state["df_std"] = None
        st.session_state["analysis_ready"] = False
        st.session_state["show_report_loading_overlay"] = False
        st.session_state.pop("analysis_saved", None)
        st.rerun()



def _render_payment_ui():
    st.markdown("### Pro 업그레이드")
    st.caption("데모 결제이지만 결제 기록은 SQLite에 저장되며, Pro 권한은 결제 시점부터 30일간 유지됩니다.")

    current_user = st.session_state.get("user_key", "guest")
    if current_user == "guest":
        st.warning("결제 기록과 Pro 권한을 계정에 연결하려면 먼저 로그인해주세요.")
        c1, c2 = st.columns(2)
        if c1.button("로그인으로 이동", use_container_width=True):
            st.session_state["modal"] = "login"
            st.rerun()
        if c2.button("닫기", use_container_width=True):
            st.session_state["modal"] = None
            st.rerun()
        return

    status = get_user_membership_status(current_user)
    if status.get("is_pro"):
        st.success(
            f"현재 Pro 이용중입니다. 만료일: {status.get('pro_expires_at')} "
            f"(남은 기간 약 {status.get('days_left', 0)}일)"
        )

    with st.form("payment_form"):
        name = st.text_input("이름", value=current_user)
        email = st.text_input("이메일")
        card_number = st.text_input("카드번호", placeholder="1234-5678-9012-3456")
        expiry = st.text_input("유효기간", placeholder="MM/YY")
        cvc = st.text_input("CVC", placeholder="123")
        pay_ok = st.form_submit_button("업그레이드", type="primary", use_container_width=True)

    if pay_ok:
        if not (name and email and card_number and expiry and cvc):
            st.error("모든 항목을 입력해주세요.")
            return

        try:
            payment = activate_pro_membership(
                username=current_user,
                payer_name=name,
                email=email,
                plan="pro_monthly",
                amount=29000,
                duration_days=30,
            )
            st.session_state["pro_paid"] = True
            st.session_state["service_mode"] = "pro"
            st.session_state["pro_expires_at"] = payment.get("expires_at")
            refreshed = get_user_membership_status(current_user)
            st.session_state["pro_days_left"] = refreshed.get("days_left", 0)
            st.session_state["modal"] = None
            st.success(
                f"업그레이드가 완료되었습니다. Pro 권한은 {payment.get('expires_at')}까지 유지됩니다."
            )
            st.rerun()
        except Exception as e:
            st.error(f"결제 저장 중 오류가 발생했습니다: {e}")


if DIALOG is not None and st.session_state.get("modal") in {"login", "signup", "logout", "payment"}:
    modal = st.session_state.get("modal")
    if modal == "login":
        @DIALOG("로그인")
        def _login_dialog():
            _render_login_ui()
        _login_dialog()
    elif modal == "signup":
        @DIALOG("회원가입")
        def _signup_dialog():
            _render_signup_ui()
        _signup_dialog()
    elif modal == "logout":
        @DIALOG("로그아웃")
        def _logout_dialog():
            _render_logout_ui()
        _logout_dialog()
    elif modal == "payment":
        @DIALOG("전문가 분석 업그레이드")
        def _payment_dialog():
            _render_payment_ui()
        _payment_dialog()


def _render_data_period_warning_banner():
    warning_on = st.session_state.get("upload_short_period_warning", False)
    message = st.session_state.get("upload_short_period_message", "")
    if warning_on and message:
        st.markdown(
            f"""
            <div style="
                margin: 0 0 18px 0;
                padding: 14px 16px;
                border-radius: 16px;
                background: rgba(245, 158, 11, 0.10);
                border: 1px solid rgba(245, 158, 11, 0.26);
                color: #92400E;
                font-size: 13px;
                line-height: 1.65;
                font-weight: 600;
            ">
                {message}
            </div>
            """,
            unsafe_allow_html=True,
        )


def _render_hero_workspace():
    current_mode = "전문가 분석" if st.session_state.get("service_mode") == "pro" else "무료버전"
    pay_status = "결제완료" if st.session_state.get("pro_paid", False) else "미결제"
    pro_exp = st.session_state.get("pro_expires_at")
    pro_days_left = st.session_state.get("pro_days_left", 0)
    login_state = st.session_state["user_key"] if st.session_state["user_key"] != "guest" else "비회원"

    left, right = st.columns([7, 3], gap="large")

    with left:
        st.markdown('<div class="workspace-shell">', unsafe_allow_html=True)
        st.markdown('<div class="page-eyebrow">Data-driven CRM Platform</div>', unsafe_allow_html=True)
        st.markdown('<div class="page-title">반려동물 커머스 고객 분석 플랫폼</div>', unsafe_allow_html=True)
        st.markdown(
            '<div class="page-subtitle">업로드한 거래 데이터를 기반으로 고객 이탈 위험, 세그먼트, 카테고리 리스크, 실행 액션까지 한 번에 정리하는 전문가용 대시보드입니다.</div>',
            unsafe_allow_html=True,
        )
        st.markdown(
            f"""
            <div class="status-inline">
              <div class="status-chip active">현재 모드 · {current_mode}</div>
              <div class="status-chip">Pro 상태 · {pay_status}</div>
              <div class="status-chip">만료일 · {pro_exp or "없음"} / 남은 {pro_days_left}일</div>
              <div class="status-chip">계정 상태 · {login_state}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        st.markdown('</div>', unsafe_allow_html=True)

    with right:
        st.markdown(
            """
            <div class="workspace-panel">
              <div class="workspace-badge">Workspace Control</div>
              <div class="workspace-title">계정과 분석 모드를 여기서 관리합니다</div>
              <div class="workspace-sub">로그인 상태에 따라 저장/불러오기, 무료·전문가 분석 모드를 전환할 수 있습니다.</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        if st.session_state["user_key"] != "guest":
            st.caption(f"👤 로그인 사용자 · {st.session_state['user_key']}")
            if st.button("로그아웃", use_container_width=True):
                st.session_state["modal"] = "logout"
        else:
            a, b = st.columns(2)
            if a.button("로그인", use_container_width=True):
                st.session_state["modal"] = "login"
            if b.button("회원가입", use_container_width=True):
                st.session_state["modal"] = "signup"

        st.markdown('<div class="workspace-divider"></div>', unsafe_allow_html=True)
        st.markdown("#### 분석 모드")
        c1, c2 = st.columns(2)
        with c1:
            if st.button("🆓 무료버전", use_container_width=True):
                st.session_state["service_mode"] = "free"
        with c2:
            if st.button("⭐ 전문가 분석", use_container_width=True):
                if st.session_state.get("pro_paid", False):
                    st.session_state["service_mode"] = "pro"
                else:
                    st.session_state["modal"] = "payment"


def _render_step_summary():
    c1, c2, c3 = st.columns(3, gap="medium")
    with c1:
        st.markdown(
            """
            <div class="hero-mini-card">
              <div class="hero-mini-label">STEP 01</div>
              <div class="hero-mini-value">Upload</div>
              <div class="hero-mini-foot">CSV/XLSX 업로드 또는 샘플 데이터로 시작</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    with c2:
        st.markdown(
            """
            <div class="hero-mini-card">
              <div class="hero-mini-label">STEP 02</div>
              <div class="hero-mini-value">Mapping</div>
              <div class="hero-mini-foot">표준 컬럼 정렬과 데이터 품질 점검</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    with c3:
        st.markdown(
            """
            <div class="hero-mini-card">
              <div class="hero-mini-label">STEP 03</div>
              <div class="hero-mini-value">Report</div>
              <div class="hero-mini-foot">이탈, 세그먼트, 액션까지 실행 중심 리포트</div>
            </div>
            """,
            unsafe_allow_html=True,
        )


def _render_loading_overlay():
    st.markdown(
        """
        <div class="loading-overlay">
          <div class="loading-modal">
            <div class="loading-badge">Analysis in Progress</div>
            <div class="loading-title">분석 중입니다</div>
            <div class="loading-desc">품질 점검 결과를 바탕으로 리포트를 생성하고 있습니다.</div>
            <div class="loading-dots">
              <span></span><span></span><span></span>
            </div>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


_render_hero_workspace()
_render_data_period_warning_banner()
st.markdown('<div class="section-gap"></div>', unsafe_allow_html=True)
_render_step_summary()
st.markdown('<div style="height:18px"></div>', unsafe_allow_html=True)

current_step = int(st.session_state.get("step", 0) or 0)
prev_step = int(st.session_state.get("prev_step", current_step) or current_step)

if current_step == 2 and prev_step == 1 and st.session_state.get("analysis_ready", False):
    st.session_state["show_report_loading_overlay"] = True

report_transition_loading = bool(st.session_state.get("show_report_loading_overlay", False))
st.session_state["prev_step"] = current_step


if st.session_state["step"] == 0:
    df = load_csv_or_sample_sidebar()
    if df is None:
        st.markdown(
            """
            <div class="empty-hero">
              <div class="empty-badge">CRM Intelligence Workspace</div>
              <div class="empty-title">데이터 업로드 후 바로 분석을 시작할 수 있습니다</div>
              <div class="empty-desc">
                거래 데이터만 준비되어 있으면 고객 이탈 위험, 예상 손실, 세그먼트, 카테고리별 운영 포인트를 전문적인 UI로 정리해볼 수 있습니다.
                먼저 왼쪽 사이드바에서 데이터를 넣어주세요.
              </div>
              <div class="empty-grid">
                <div class="empty-feature">
                  <div class="empty-feature-title">Churn Monitoring</div>
                  <div class="empty-feature-desc">고위험 고객 비율, 예상 매출 손실, 대응 우선순위를 빠르게 식별합니다.</div>
                </div>
                <div class="empty-feature">
                  <div class="empty-feature-title">Segment Insight</div>
                  <div class="empty-feature-desc">RFM 기반 세그먼트를 시각적으로 정리하고 리텐션 전략으로 연결합니다.</div>
                </div>
                <div class="empty-feature">
                  <div class="empty-feature-title">Action-ready Report</div>
                  <div class="empty-feature-desc">카테고리 리스크, 환불, 재구매 주기까지 포함한 실행형 리포트를 제공합니다.</div>
                </div>
              </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    else:
        _start_new_analysis(df)
        st.rerun()

elif st.session_state["step"] == 1:
    if st.session_state.get("df_raw") is None:
        st.warning("업로드된 원본 데이터가 없습니다. 먼저 CSV 또는 XLSX 파일을 업로드해주세요.")
        st.session_state["step"] = 0
        st.session_state["analysis_ready"] = False
        st.session_state["prev_step"] = 0
        st.rerun()
    else:
        df_std = mapping_step(st.session_state["df_raw"])
        if df_std is not None:
            st.session_state["df_std"] = df_std
            st.session_state["analysis_ready"] = True
            st.session_state.pop("analysis_saved", None)

else:
    selected_saved_run = st.session_state.get("view_run_id")

    if selected_saved_run is not None:
        overlay_placeholder = st.empty()

        if report_transition_loading:
            overlay_placeholder.markdown(
                """
                <div class="loading-overlay">
                  <div class="loading-modal">
                    <div class="loading-badge">Analysis in Progress</div>
                    <div class="loading-title">분석 중입니다</div>
                    <div class="loading-desc">품질 점검 결과를 바탕으로 리포트를 생성하고 있습니다.</div>
                    <div class="loading-dots">
                      <span></span><span></span><span></span>
                    </div>
                  </div>
                </div>
                """,
                unsafe_allow_html=True,
            )

        report_step(
            st.session_state.get("df_std", pd.DataFrame()),
            user_key=st.session_state.get("user_key", "guest"),
        )

        if report_transition_loading:
            overlay_placeholder.empty()
            st.session_state["show_report_loading_overlay"] = False
            st.rerun()

    else:
        if st.session_state.get("df_std") is None:
            st.warning("현재 분석 데이터가 없습니다. CSV 또는 XLSX 파일을 다시 업로드하거나 저장된 분석을 선택해주세요.")
            if st.button("업로드 화면으로 돌아가기", type="primary"):
                st.session_state["step"] = 0
                st.session_state["analysis_ready"] = False
                st.session_state["prev_step"] = 0
                st.session_state["show_report_loading_overlay"] = False
                st.rerun()
        else:
            overlay_placeholder = st.empty()

            if report_transition_loading:
                overlay_placeholder.markdown(
                    """
                    <div class="loading-overlay">
                      <div class="loading-modal">
                        <div class="loading-badge">Analysis in Progress</div>
                        <div class="loading-title">분석 중입니다</div>
                        <div class="loading-desc">품질 점검 결과를 바탕으로 리포트를 생성하고 있습니다.</div>
                        <div class="loading-dots">
                          <span></span><span></span><span></span>
                        </div>
                      </div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

            if st.session_state.get("service_mode") == "free":
                free_report_step(st.session_state["df_std"])
            else:
                if st.session_state.get("pro_paid", False):
                    report_step(
                        st.session_state["df_std"],
                        user_key=st.session_state["user_key"],
                    )
                else:
                    st.warning("전문가 분석은 결제 후 이용할 수 있습니다.")
                    if st.button("결제 팝업 열기", type="primary"):
                        st.session_state["modal"] = "payment"
                        st.rerun()

            if report_transition_loading:
                overlay_placeholder.empty()
                st.session_state["show_report_loading_overlay"] = False
                st.rerun()