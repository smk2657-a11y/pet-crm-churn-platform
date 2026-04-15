import pandas as pd
import plotly.express as px
import streamlit as st

from .analytics import compute_rfm_and_risk
from .report_component import section_header, metric_card, chart_card, insight_box, action_card, table_block


def _fmt_currency(x) -> str:
    try:
        return f"₩{int(round(float(x))):,}"
    except Exception:
        return "-"


def _fmt_int(x) -> str:
    try:
        return f"{int(x):,}"
    except Exception:
        return "-"


def _fmt_percent(x) -> str:
    try:
        return f"{float(x):.1f}%"
    except Exception:
        return "-"


def free_report_step(df_std: pd.DataFrame):
    result = compute_rfm_and_risk(df_std)
    kpi = result["kpi"]
    seg = result["segment_summary"]
    cat = result["category_risk"]
    cust = result["customer_list"]
    refund = result.get("refund", {}) or {}

    section_header(
        "쉬운 분석 리포트",
        "핵심 수치와 우선 대응 고객만 빠르게 확인할 수 있는 간단 리포트입니다.",
        kicker="FREE REPORT",
    )

    st.markdown("<div style='height:16px'></div>", unsafe_allow_html=True)
    c1, c2, c3, c4 = st.columns(4, gap="medium")
    with c1:
        metric_card("전체 고객 수", f"{_fmt_int(kpi.get('total_customers', 0))}명", "현재 분석 기준 고객 규모")
    with c2:
        metric_card("고위험 고객 비율", _fmt_percent(kpi.get('high_ratio', 0)), "이탈 대응 우선순위 판단")
    with c3:
        metric_card("예상 매출 손실", _fmt_currency(kpi.get('expected_loss', 0)), "단기 이탈 방지 필요 규모")
    with c4:
        metric_card("환불률", _fmt_percent(float(refund.get('refund_rate', 0) or 0) * 100), "고객 경험 이슈 참고")

    st.markdown("<div style='height:20px'></div>", unsafe_allow_html=True)
    bullets = [
        f"현재 고위험 고객 비율은 {_fmt_percent(kpi.get('high_ratio', 0))} 수준입니다.",
        f"예상 매출 손실은 {_fmt_currency(kpi.get('expected_loss', 0))} 수준입니다.",
        "무료 버전에서는 핵심 요약과 우선 대응 대상만 간단하게 제공합니다.",
    ]
    insight_box("핵심 요약", bullets, tone="info")

    action_card("다음 단계 안내", "전문가 분석 모드에서는 카테고리 재구매 주기, ML 이탈예측, PDF 리포트까지 확장해서 볼 수 있습니다.", "UPGRADE")

    st.markdown("<div style='height:24px'></div>", unsafe_allow_html=True)
    col1, col2 = st.columns(2, gap="medium")
    with col1:
        if isinstance(seg, pd.DataFrame) and not seg.empty and {"세그먼트", "인원"}.issubset(seg.columns):
            fig = px.pie(seg, names="세그먼트", values="인원", hole=0.55)
            fig.update_traces(textposition="inside", textinfo="percent+label")
            chart_card("고객 세그먼트 구성", fig, "고객군 비중을 한눈에 확인합니다.")
        else:
            st.info("세그먼트 데이터가 없습니다.")

    with col2:
        if isinstance(cat, pd.DataFrame) and not cat.empty and {"카테고리", "위험"}.issubset(cat.columns):
            cat_plot = cat.sort_values("위험", ascending=True).copy()
            fig = px.bar(cat_plot, x="위험", y="카테고리", orientation="h", text="위험", color="위험", color_continuous_scale="Blues")
            fig.update_layout(coloraxis_showscale=False)
            fig.update_traces(textposition="outside")
            chart_card("카테고리별 위험도", fig, "위험도가 높은 카테고리부터 우선 관리가 필요합니다.")
        else:
            st.info("카테고리 데이터가 없습니다.")

    st.markdown("<div style='height:28px'></div>", unsafe_allow_html=True)
    section_header("우선 대응 고객", "고위험 고객을 중심으로 빠르게 대응할 수 있도록 간단 표를 제공합니다.")
    if isinstance(cust, pd.DataFrame) and not cust.empty:
        show = cust.copy().head(10)
        if "주문금액" in show.columns:
            show["주문금액"] = show["주문금액"].apply(_fmt_currency)
        table_block(show, caption="상위 10명 고객", height=340)
    else:
        st.info("고객 리스트가 없습니다.")

    st.markdown("<div style='height:28px'></div>", unsafe_allow_html=True)
    section_header("바로 실행할 액션", "복잡한 설명 대신 운영자가 당장 할 수 있는 액션만 정리했습니다.")
    action_card("고위험 고객 재구매 유도", "최근 구매가 끊긴 고객에게 리마인드 메시지와 재구매 쿠폰을 우선 발송하세요.", "우선순위 높음")
    action_card("위험 카테고리 집중 관리", "위험도가 높은 카테고리의 상품 설명, 배송, 가격 조건을 우선 점검하세요.", "카테고리")
    action_card("VIP 고객 이탈 방지", "구매 금액이 큰 고객은 별도 혜택과 개인화 추천으로 선제 케어하는 것이 좋습니다.", "VIP")

    st.info("전문가 분석(Pro)에서는 더 많은 그래프, ML 이탈예측, 환불/재고 전략까지 제공합니다.")