from pathlib import Path
from typing import List, Optional

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from .analytics import compute_rfm_and_risk
from .pdf_export import build_report_pdf
from .report_component import (
    section_header,
    metric_card,
    chart_card,
    insight_box,
    action_card,
    table_block,
    gauge_card,
)
from .storage import save_run, list_runs, get_run, delete_run


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


def _fmt_float2(x) -> str:
    try:
        return f"{float(x):.2f}"
    except Exception:
        return "-"


def _pick_col(df: pd.DataFrame, candidates: List[str]) -> Optional[str]:
    if df is None or df.empty:
        return None
    cols = set(df.columns)
    for c in candidates:
        if c in cols:
            return c
    return None


def _fmt_saved_at(x) -> str:
    try:
        if x is None or str(x).strip() == "":
            return "저장일시 없음"
        dt = pd.to_datetime(x)
        return dt.strftime("%Y-%m-%d %H:%M")
    except Exception:
        return str(x) if x is not None else "저장일시 없음"


def _make_run_label(run: dict) -> str:
    run_name = str((run.get("run_name") or "")).strip()
    created = run.get("created_at", "")
    saved_at_str = _fmt_saved_at(created)
    title = run_name if run_name else "저장 분석"
    return f"{title} · {saved_at_str}"


def _df_to_records(df: pd.DataFrame | None, limit: int = 2000) -> list[dict]:
    if df is None or not isinstance(df, pd.DataFrame) or df.empty:
        return []
    tmp = df.head(limit).copy()
    for col in tmp.select_dtypes(include=["datetimetz", "datetime64[ns]", "datetime"]).columns:
        tmp[col] = tmp[col].astype(str)
    return tmp.to_dict(orient="records")


def _pack_report_for_storage(result: dict) -> dict:
    return {
        "kpi": result.get("kpi", {}),
        "forecast": result.get("forecast", {}),
        "category_risk": _df_to_records(result.get("category_risk"), 300),
        "segment_summary": _df_to_records(result.get("segment_summary"), 300),
        "customer_list": _df_to_records(result.get("customer_list"), 500),
        "inventory": _df_to_records(result.get("inventory"), 300),
        "rfm": _df_to_records(result.get("rfm"), 3000),
        "churn_summary": result.get("churn_summary", {}),
        "churn_scored": _df_to_records(result.get("churn_scored"), 500),
        "category_churn": _df_to_records(result.get("category_churn"), 1000),
        "refund": {
            "refund_rate": float((result.get("refund", {}) or {}).get("refund_rate", 0.0) or 0.0),
            "refund_customers": _df_to_records((result.get("refund", {}) or {}).get("refund_customers"), 300),
            "refund_category": _df_to_records((result.get("refund", {}) or {}).get("refund_category"), 300),
        },
        "refill_cycle_by_category": _df_to_records(result.get("refill_cycle_by_category"), 300),
        "refill_category_group": _df_to_records(result.get("refill_category_group"), 300),
        "multi_pet_customers": _df_to_records(result.get("multi_pet_customers"), 300),
        "pet_insights": result.get("pet_insights", {}),
        "negative_sales_mode": st.session_state.get("negative_sales_mode", "refund"),
    }


def _metrics_from_result(result: dict) -> dict:
    df_work = result.get("df_work")
    revenue = int(df_work["매출"].sum()) if isinstance(df_work, pd.DataFrame) and "매출" in df_work.columns else 0
    orders = int(len(df_work)) if isinstance(df_work, pd.DataFrame) else 0
    customers = int(result.get("kpi", {}).get("total_customers", 0) or 0)
    return {"revenue": revenue, "orders": orders, "customers": customers}


def _get_negative_sales_mode() -> str:
    mode = st.session_state.get("negative_sales_mode", "refund")
    return mode if mode in {"refund", "exclude", "keep"} else "refund"


def _negative_sales_mode_label(mode: str) -> str:
    return {
        "refund": "환불/취소 후보로 처리",
        "exclude": "분석에서 제외",
        "keep": "원본 그대로 유지",
    }.get(mode, mode)


def _negative_sales_mode_desc(mode: str) -> str:
    return {
        "refund": "음수 매출은 환불/취소 후보로 간주하여 환불 분석에도 반영합니다.",
        "exclude": "음수 매출은 이상치 또는 비분석 데이터로 간주하여 현재 분석에서 제외합니다.",
        "keep": "음수 매출을 원본 그대로 유지하여 정산/오류 가능성까지 함께 해석합니다.",
    }.get(mode, "")


def _render_negative_sales_mode_notice(mode: str):
    st.markdown(
        f"""
        <div class="action-card" style="border-left-color:#7C3AED;">
          <div class="action-title">음수 매출 처리 방식 · {_negative_sales_mode_label(mode)}</div>
          <div class="action-body">{_negative_sales_mode_desc(mode)}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _build_exec_summary(high_ratio, expected_loss, refund_rate, top_seg, top_cat):
    lines = [
        f"고위험 고객 비율은 {high_ratio:.1f}%로, 단기 리텐션 개입이 필요한 수준입니다.",
        f"예상 매출 이탈 규모는 {_fmt_currency(expected_loss)} 수준으로 추정됩니다.",
    ]
    if refund_rate > 0:
        lines.append(f"환불률은 {refund_rate*100:.1f}%로, 상품/배송/품질 이슈를 병행 점검할 필요가 있습니다.")
    if top_seg and top_seg != "-":
        lines.append(f"고객군 기준 우선 관리 세그먼트는 {top_seg}입니다.")
    if top_cat and top_cat != "-":
        lines.append(f"카테고리 기준으로는 {top_cat} 영역의 위험도가 가장 높습니다.")
    return lines[:4]


def _render_saved_runs_sidebar(effective_user_key: str, is_member: bool):
    with st.sidebar:
        st.markdown('<div class="side-section-title">📌 내 분석 기록</div>', unsafe_allow_html=True)
        if not is_member:
            st.caption("로그인하면 분석 기록을 저장하고 다시 불러올 수 있어요.")
            return

        runs = list_runs(effective_user_key)
        if not runs:
            st.caption("저장된 기록이 없습니다.")
            st.session_state["view_run_id"] = None
            st.session_state["sidebar_run_pick"] = "현재 분석"
            return

        rid_list = [r.get("run_id") for r in runs if r.get("run_id") is not None]
        label_map = {r["run_id"]: _make_run_label(r) for r in runs if r.get("run_id") is not None}
        options = ["현재 분석"] + rid_list
        previous_pick = st.session_state.get("sidebar_run_pick", "현재 분석")
        if previous_pick not in options:
            previous_pick = "현재 분석"
            st.session_state["sidebar_run_pick"] = "현재 분석"

        picked = st.selectbox(
            "저장된 분석 보기",
            options,
            index=options.index(previous_pick),
            format_func=lambda x: "현재 분석" if x == "현재 분석" else label_map.get(x, str(x)),
        )

        if picked != previous_pick:
            st.session_state["sidebar_run_pick"] = picked
            st.session_state["view_run_id"] = None if picked == "현재 분석" else picked
            st.rerun()

        if picked != "현재 분석":
            c1, c2 = st.columns(2)
            if c1.button("현재 분석 보기", use_container_width=True):
                st.session_state["view_run_id"] = None
                st.session_state["sidebar_run_pick"] = "현재 분석"
                st.rerun()
            if c2.button("기록 삭제", use_container_width=True):
                ok = delete_run(effective_user_key, picked)
                if ok:
                    st.session_state["view_run_id"] = None
                    st.session_state["sidebar_run_pick"] = "현재 분석"
                    st.success("선택한 기록을 삭제했어요.")
                    st.rerun()
                st.error("삭제에 실패했습니다.")


def _save_panel(result: dict, metrics: dict, effective_user_key: str, is_member: bool):
    if not is_member:
        st.info("로그인하면 현재 분석을 저장하고 나중에 다시 열 수 있습니다.")
        return

    default_name = st.session_state.get("draft_run_name", "새 분석")
    with st.form("save_run_form", border=True):
        st.markdown("#### 분석 저장")
        run_name = st.text_input("저장 이름", value=default_name, placeholder="예: 6월 캠페인 이후 고객이탈 분석")
        c1, c2 = st.columns(2)
        do_save = c1.form_submit_button("저장", use_container_width=True, type="primary")
        clear_name = c2.form_submit_button("이름 지우기", use_container_width=True)

    if clear_name:
        st.session_state["draft_run_name"] = ""
        st.rerun()

    if do_save:
        name = (run_name or "").strip()
        if not name:
            st.warning("저장 이름을 입력해주세요.")
            return
        packed = _pack_report_for_storage(result)
        run_id = save_run(effective_user_key, name, metrics, packed)
        st.session_state["draft_run_name"] = name
        st.session_state["view_run_id"] = None
        st.session_state["sidebar_run_pick"] = "현재 분석"
        st.success(f"저장 완료! (run_id={run_id})")
        st.rerun()


def _pdf_controls(
    pdf_title: str,
    pdf_user_name: str,
    pdf_run_name: str,
    kpi: dict,
    cat: pd.DataFrame,
    seg: pd.DataFrame,
    cust: pd.DataFrame,
    churn_scored: pd.DataFrame,
    refund_category: pd.DataFrame,
    inv: pd.DataFrame,
    forecast: dict,
):
    st.session_state.setdefault("show_pdf_options", False)
    st.session_state.setdefault("report_pdf_bytes", None)

    st.markdown("#### PDF 내보내기")
    c1, c2 = st.columns([1, 1])

    with c1:
        if st.button("PDF 준비", use_container_width=True):
            st.session_state["show_pdf_options"] = True

    with c2:
        if st.session_state["show_pdf_options"]:
            if st.button("PDF 옵션 닫기", use_container_width=True):
                st.session_state["show_pdf_options"] = False
                st.rerun()

    if st.session_state["show_pdf_options"]:
        st.info("포함할 탭을 선택한 뒤 PDF 생성 버튼을 눌러주세요.")

        section_options = [
            ("overview", "Executive Summary"),
            ("segment", "세그먼트"),
            ("category", "카테고리"),
            ("ml", "ML 이탈예측"),
            ("refund", "환불"),
            ("inventory", "재고 전략"),
        ]

        selected_sections = {}
        cols = st.columns(4)

        for idx, (key, label) in enumerate(section_options):
            with cols[idx % 4]:
                selected_sections[key] = st.checkbox(
                    label,
                    value=True,
                    key=f"pdf_section_{key}",
                )

        if st.button("PDF 생성", type="primary", use_container_width=True):
            try:
                pdf_bytes = build_report_pdf(
                    title=pdf_title,
                    user_name=pdf_user_name,
                    run_name=pdf_run_name,
                    kpi=kpi,
                    category_df=cat,
                    segment_df=seg,
                    customer_df=cust,
                    ml_df=churn_scored,
                    refund_df=refund_category,
                    inventory_df=inv,
                    forecast=forecast,
                    selected_sections=selected_sections,
                )
                st.session_state["report_pdf_bytes"] = pdf_bytes
                st.success("PDF가 준비되었습니다.")
            except Exception as e:
                st.error(f"PDF 생성 중 오류가 발생했습니다: {e}")

    pdf_bytes = st.session_state.get("report_pdf_bytes")
    if pdf_bytes:
        safe_pdf_name = "".join(
            ch if ch.isalnum() or ch in (" ", "_", "-") else "_"
            for ch in str(pdf_run_name)
        ).strip()
        safe_pdf_name = safe_pdf_name.replace(" ", "_") or "pet_report"

        st.download_button(
            label="PDF 다운로드",
            data=pdf_bytes,
            file_name=f"{safe_pdf_name}_report.pdf",
            mime="application/pdf",
            use_container_width=True,
        )


def _pet_category_label(value: str) -> str:
    s = str(value).strip().lower()

    mapping = [
        (["pet food", "food", "feed", "사료", "주식"], "사료/주식"),
        (["treat", "snack", "간식"], "간식"),
        (["grooming", "미용", "샴푸", "브러시"], "미용관리"),
        (["supplement", "health", "영양제", "건강"], "건강관리"),
        (["disposable", "pad", "패드", "litter", "모래", "배변"], "배변·소모품"),
        (["cleaning", "위생", "청소", "탈취", "물티슈"], "위생·청결"),
        (["toy", "놀이", "장난감"], "장난감/놀이"),
        (["house", "bed", "carrier", "하우스", "침대", "이동장", "캐리어"], "하우스·이동용품"),
        (["electronic", "electronics", "자동급식기", "급수기"], "펫 가전"),
        (["clothes", "wear", "의류"], "의류/액세서리"),
    ]

    for keywords, label in mapping:
        if any(k in s for k in keywords):
            return label
    return str(value)


def _pet_action_by_label(label: str, group: str = "", cycle: float | int | None = None) -> str:
    cycle_txt = ""
    try:
        if cycle is not None and pd.notna(cycle):
            cycle_txt = f" (권장 알림 D+{max(int(cycle) - 5, 1)})"
    except Exception:
        cycle_txt = ""

    if "사료/주식" in label:
        return f"핵심 재구매 방어 · 사료 리마인드/구독 제안{cycle_txt}"
    if "배변·소모품" in label:
        return f"반복소비 관리 · 패드/모래 묶음 제안{cycle_txt}"
    if "건강관리" in label:
        return "프리미엄 업셀 · 영양제/건강관리 추천"
    if "미용관리" in label:
        return "주기성 관리 · 미용 관련 재방문 유도"
    if "간식" in label:
        return "충동구매 활성화 · 장바구니 추가 제안"
    if "위생·청결" in label:
        return "생활소모품 리마인드 · 번들 프로모션"
    if "장난감/놀이" in label:
        return "보완상품 추천 · 교차판매 강화"
    if "하우스·이동용품" in label:
        return "고관여 상품 · 리뷰/콘텐츠 중심 설득"
    if "펫 가전" in label:
        return "고가 상품 · 비교 콘텐츠/후기 강화"

    if str(group) == "정기구매":
        return "정기소비 카테고리 · 리마인드 발송"
    if str(group) == "단발성구매":
        return "단발 구매 카테고리 · 보완상품 추천"
    return "카테고리 맞춤 CRM 운영"


def _prepare_pet_refill_table(refill_cycle: pd.DataFrame) -> pd.DataFrame:
    if not isinstance(refill_cycle, pd.DataFrame) or refill_cycle.empty:
        return pd.DataFrame()

    df = refill_cycle.copy()
    if "카테고리" in df.columns:
        df["펫카테고리"] = df["카테고리"].apply(_pet_category_label)
    else:
        df["펫카테고리"] = "-"

    if "추천발송시점(일)" not in df.columns and "재구매주기" in df.columns:
        df["추천발송시점(일)"] = pd.to_numeric(df["재구매주기"], errors="coerce").fillna(0).apply(
            lambda x: max(int(x) - 5, 1) if x > 0 else 0
        )

    df["운영액션"] = df.apply(
        lambda r: _pet_action_by_label(
            r.get("펫카테고리", "-"),
            r.get("그룹", ""),
            r.get("재구매주기", None),
        ),
        axis=1,
    )

    show_cols = [
        "펫카테고리",
        "카테고리",
        "재구매주기",
        "추천발송시점(일)",
        "재구매율",
        "그룹",
        "운영액션",
    ]
    show_cols = [c for c in show_cols if c in df.columns]
    df = df[show_cols].copy()

    if "재구매율" in df.columns:
        df["재구매율"] = pd.to_numeric(df["재구매율"], errors="coerce").round(1)

    return df.sort_values(
        by=[c for c in ["재구매주기", "재구매율"] if c in df.columns],
        ascending=[True, False][: len([c for c in ["재구매주기", "재구매율"] if c in df.columns])],
    ).reset_index(drop=True)


def _build_pet_core_points(refill_cycle: pd.DataFrame) -> list[str]:
    if not isinstance(refill_cycle, pd.DataFrame) or refill_cycle.empty:
        return [
            "카테고리 데이터가 충분하지 않아 펫 특화 운영 포인트를 계산하지 못했습니다.",
        ]

    pet_df = _prepare_pet_refill_table(refill_cycle)
    points = []

    def _pick_first(keyword: str):
        subset = pet_df[pet_df["펫카테고리"].astype(str).str.contains(keyword, na=False)]
        return subset.iloc[0] if not subset.empty else None

    food_row = _pick_first("사료/주식")
    if food_row is not None:
        points.append(
            f"사료/주식은 재구매주기 {int(food_row['재구매주기'])}일로, "
            f"D+{int(food_row['추천발송시점(일)'])} 리마인드가 적절합니다."
        )

    dispo_row = _pick_first("배변·소모품")
    if dispo_row is not None:
        points.append(
            "배변·소모품은 반복소비 카테고리로, 묶음상품/정기구독 제안 효과가 큽니다."
        )

    health_row = _pick_first("건강관리")
    if health_row is not None:
        points.append(
            "건강관리 카테고리는 프리미엄 고객 업셀 후보로 해석할 수 있습니다."
        )

    if not points:
        top_rows = pet_df.head(3)
        for _, row in top_rows.iterrows():
            points.append(
                f"{row.get('펫카테고리', row.get('카테고리', '-'))}: "
                f"{row.get('운영액션', '카테고리 맞춤 운영')}"
            )

    return points[:3]


def _make_pet_category_sales_summary(data_for_cat: pd.DataFrame, cat_col: str, sales_col: str) -> pd.DataFrame:
    if data_for_cat.empty or not cat_col or not sales_col:
        return pd.DataFrame()

    plot = data_for_cat.copy()
    plot[sales_col] = pd.to_numeric(plot[sales_col], errors="coerce")
    plot = plot.dropna(subset=[cat_col, sales_col]).copy()
    plot["펫카테고리"] = plot[cat_col].apply(_pet_category_label)

    agg = (
        plot.groupby("펫카테고리")
        .agg(총매출=(sales_col, "sum"), 판매건수=(sales_col, "count"))
        .reset_index()
        .sort_values("총매출", ascending=False)
    )
    return agg


def _prepare_inventory_table(inv_df: pd.DataFrame) -> pd.DataFrame:
    if not isinstance(inv_df, pd.DataFrame) or inv_df.empty:
        return pd.DataFrame()

    df = inv_df.copy()
    if "펫카테고리" not in df.columns and "카테고리" in df.columns:
        df["펫카테고리"] = df["카테고리"].apply(_pet_category_label)

    if "우선순위" not in df.columns and "안전재고량" in df.columns:
        high_cut = float(df["안전재고량"].quantile(0.67))
        mid_cut = float(df["안전재고량"].quantile(0.34))

        def _priority(v):
            if float(v) >= high_cut:
                return "최우선 확보"
            if float(v) >= mid_cut:
                return "집중 관리"
            return "기본 운영"

        df["우선순위"] = df["안전재고량"].apply(_priority)

    if "추천액션" not in df.columns:
        df["추천액션"] = df.apply(
            lambda r: _pet_action_by_label(str(r.get("펫카테고리", "-"))),
            axis=1,
        )

    show_cols = [
        "펫카테고리",
        "카테고리",
        "예상판매량",
        "일평균판매량",
        "안전재고량",
        "권장보유일수",
        "우선순위",
        "추천액션",
    ]
    show_cols = [c for c in show_cols if c in df.columns]
    out = df[show_cols].copy()

    for col in ["예상판매량", "일평균판매량"]:
        if col in out.columns:
            out[col] = pd.to_numeric(out[col], errors="coerce").round(1)
    if "안전재고량" in out.columns:
        out["안전재고량"] = pd.to_numeric(out["안전재고량"], errors="coerce").round(0).astype("Int64")
    if "권장보유일수" in out.columns:
        out["권장보유일수"] = pd.to_numeric(out["권장보유일수"], errors="coerce").round(0).astype("Int64")


    return out


def _prepare_category_axis_chart_df(
    df: pd.DataFrame,
    value_cols: list[str],
    include_priority: bool = False,
) -> pd.DataFrame:
    if not isinstance(df, pd.DataFrame) or df.empty:
        return pd.DataFrame()

    out = df.copy()

    if "카테고리" not in out.columns and "펫카테고리" in out.columns:
        out["카테고리"] = out["펫카테고리"]

    if "펫카테고리" not in out.columns and "카테고리" in out.columns:
        out["펫카테고리"] = out["카테고리"].apply(_pet_category_label)

    if "카테고리" not in out.columns:
        return pd.DataFrame()

    out["카테고리"] = out["카테고리"].astype(str)
    out["펫카테고리"] = out["펫카테고리"].astype(str)

    out["표시라벨"] = out.apply(
        lambda r: f"{r['카테고리']} ({r['펫카테고리']})"
        if r.get("펫카테고리", "-") not in {"", "-", r.get("카테고리", "-")}
        else str(r.get("카테고리", "-")),
        axis=1,
    )

    valid_value_cols = [c for c in value_cols if c in out.columns]
    if not valid_value_cols:
        return pd.DataFrame()

    for col in valid_value_cols:
        out[col] = pd.to_numeric(out[col], errors="coerce")

    sort_cols = valid_value_cols.copy()
    if include_priority and "우선순위" in out.columns:
        priority_order = {"최우선 확보": 0, "집중 관리": 1, "기본 운영": 2}
        out["__priority_order"] = out["우선순위"].map(priority_order).fillna(9)
        sort_cols = ["__priority_order"] + sort_cols

    out = out.sort_values(sort_cols, ascending=[True] + [False] * (len(sort_cols) - 1) if include_priority and "우선순위" in out.columns else [False] * len(sort_cols), na_position="last").reset_index(drop=True)

    order = out["표시라벨"].tolist()
    out["표시라벨"] = pd.Categorical(out["표시라벨"], categories=order[::-1], ordered=True)
    if "__priority_order" in out.columns:
        out = out.drop(columns=["__priority_order"])
    return out


def _build_inventory_points(inv_df: pd.DataFrame, forecast: dict, total_customers: int) -> list[str]:
    points = []
    if isinstance(forecast, dict):
        forecast_value = int((forecast or {}).get("value", 0) or 0)
        avg_daily = float((forecast or {}).get("avg_daily_revenue", 0) or 0)
        basis_days = int((forecast or {}).get("basis_days", 0) or 0)
        if forecast_value > 0:
            points.append(f"다음달 예상 매출은 {_fmt_currency(forecast_value)} 수준이며, 최근 {basis_days}일 일평균 매출은 {_fmt_currency(avg_daily)}입니다.")
    if total_customers > 0:
        points.append(f"현재 분석 기준 고객 규모는 {_fmt_int(total_customers)}명으로, 핵심 반복소비 카테고리 중심 재고 운영이 필요합니다.")

    show = _prepare_inventory_table(inv_df)
    if not show.empty:
        top = show.iloc[0]
        points.append(f"안전재고 우선순위 1위는 {top.get('펫카테고리', top.get('카테고리', '-'))}이며, 권장 안전재고는 {_fmt_int(top.get('안전재고량', 0))} 수준입니다.")
        priority_count = int((show["우선순위"] == "최우선 확보").sum()) if "우선순위" in show.columns else 0
        points.append(f"즉시 발주 혹은 일일 모니터링이 필요한 최우선 확보 카테고리는 {priority_count}개입니다.")
    else:
        points.append("재고 전략을 계산할 수 있는 카테고리 데이터가 충분하지 않습니다.")
    return points[:4]


def _inventory_action_cards(inv_df: pd.DataFrame) -> list[dict]:
    show = _prepare_inventory_table(inv_df)
    if show.empty:
        return []

    cards = []
    for _, row in show.head(3).iterrows():
        cards.append({
            "title": f"{row.get('펫카테고리', row.get('카테고리', '-'))} · {row.get('우선순위', '기본 운영')}",
            "body": row.get("추천액션", "카테고리별 판매 추이를 기준으로 재고를 운영합니다."),
            "tag": row.get("우선순위", "기본 운영"),
        })
    return cards


def _prepare_multi_pet_table(multi_pet_df: pd.DataFrame) -> pd.DataFrame:
    if not isinstance(multi_pet_df, pd.DataFrame) or multi_pet_df.empty:
        return pd.DataFrame()

    df = multi_pet_df.copy()
    rename_map = {
        "근거": "추정근거",
        "카테고리다양도": "카테고리 다양도",
        "구매빈도": "주문 빈도",
    }
    df = df.rename(columns=rename_map)

    if "multi_pet" in df.columns:
        df["다반려추정"] = df["multi_pet"].map({True: "예", False: "아니오"})
        df = df.drop(columns=["multi_pet"])

    if "추정근거" in df.columns:
        df["운영액션"] = df["추정근거"].apply(
            lambda x: "강아지·고양이 교차판매 / 복합 장바구니 제안"
            if "강아지+고양이" in str(x)
            else "다반려 가구 묶음상품 / 소모품 세트 추천"
        )

    preferred = ["고객ID", "다반려추정", "추정근거", "카테고리 다양도", "주문 빈도", "운영액션"]
    preferred = [c for c in preferred if c in df.columns]
    return df[preferred].head(20).copy()


def _prepare_category_churn_table(category_churn_df: pd.DataFrame) -> pd.DataFrame:
    if not isinstance(category_churn_df, pd.DataFrame) or category_churn_df.empty:
        return pd.DataFrame()

    df = category_churn_df.copy()
    if "카테고리" in df.columns:
        df["펫카테고리"] = df["카테고리"].apply(_pet_category_label)

    if "이탈확률" in df.columns:
        df["이탈확률"] = (pd.to_numeric(df["이탈확률"], errors="coerce") * 100).round(1).astype(str) + "%"

    if "누적매출" in df.columns:
        df["누적매출"] = df["누적매출"].apply(_fmt_currency)

    preferred = [
        "고객ID",
        "펫카테고리",
        "카테고리",
        "구매횟수",
        "평균구매주기(일)",
        "경과일",
        "이탈확률",
        "위험도",
        "예측방식",
        "추천액션",
        "누적매출",
    ]
    preferred = [c for c in preferred if c in df.columns]
    return df[preferred].copy()


def _safe_float(value, default: float = 0.0) -> float:
    try:
        if value is None or (isinstance(value, str) and value.strip() == ""):
            return default
        return float(value)
    except Exception:
        return default


def _safe_int(value, default: int = 0) -> int:
    try:
        if value is None or (isinstance(value, str) and value.strip() == ""):
            return default
        return int(round(float(value)))
    except Exception:
        return default


def _build_compare_snapshot(run: dict) -> dict:
    metrics = (run or {}).get("metrics", {}) or {}
    report = (run or {}).get("report", {}) or {}
    kpi = report.get("kpi", {}) or {}
    forecast = report.get("forecast", {}) or {}
    refund = report.get("refund", {}) or {}
    seg_df = pd.DataFrame(report.get("segment_summary", []) or [])
    cat_df = pd.DataFrame(report.get("category_risk", []) or [])

    top_segment = "-"
    if not seg_df.empty and {"세그먼트", "인원"}.issubset(seg_df.columns):
        seg_tmp = seg_df.copy()
        seg_tmp["인원"] = pd.to_numeric(seg_tmp["인원"], errors="coerce")
        seg_tmp = seg_tmp.sort_values("인원", ascending=False)
        if not seg_tmp.empty:
            top_segment = str(seg_tmp.iloc[0].get("세그먼트", "-"))

    top_category = "-"
    if not cat_df.empty and {"카테고리", "위험"}.issubset(cat_df.columns):
        cat_tmp = cat_df.copy()
        cat_tmp["위험"] = pd.to_numeric(cat_tmp["위험"], errors="coerce")
        cat_tmp = cat_tmp.sort_values("위험", ascending=False)
        if not cat_tmp.empty:
            top_category = _pet_category_label(str(cat_tmp.iloc[0].get("카테고리", "-")))

    return {
        "run_id": run.get("run_id"),
        "label": _make_run_label(run),
        "run_name": run.get("run_name", "저장 분석"),
        "created_at": run.get("created_at", ""),
        "revenue": _safe_int(metrics.get("revenue", 0)),
        "orders": _safe_int(metrics.get("orders", 0)),
        "customers": _safe_int(metrics.get("customers", kpi.get("total_customers", 0))),
        "high_ratio": _safe_float(kpi.get("high_ratio", 0.0)),
        "avg_risk": _safe_float(kpi.get("avg_risk", 0.0)),
        "expected_loss": _safe_int(kpi.get("expected_loss", 0)),
        "refund_rate": _safe_float(refund.get("refund_rate", 0.0)),
        "forecast_value": _safe_int(forecast.get("value", 0)),
        "top_segment": top_segment,
        "top_category": top_category,
    }


def _comparison_delta_text(current, base, kind: str = "number") -> str:
    delta = current - base
    if kind == "percent":
        return f"{delta:+.1f}%p"
    if kind == "ratio":
        return f"{delta:+.1%}"
    return f"{int(round(delta)):+,}"


def _comparison_delta_color(delta: float) -> str:
    if delta > 0:
        return "#10B981"
    if delta < 0:
        return "#EF4444"
    return "#64748B"


def _comparison_delta_bg(delta: float) -> str:
    if delta > 0:
        return "linear-gradient(135deg, rgba(16,185,129,0.16), rgba(16,185,129,0.05))"
    if delta < 0:
        return "linear-gradient(135deg, rgba(239,68,68,0.16), rgba(239,68,68,0.05))"
    return "linear-gradient(135deg, rgba(100,116,139,0.14), rgba(100,116,139,0.05))"


def _render_compare_metric_card(title: str, value: str, delta_text: str, delta_value: float, subtitle: str = ""):
    accent = _comparison_delta_color(delta_value)
    bg = _comparison_delta_bg(delta_value)
    arrow = "▲" if delta_value > 0 else "▼" if delta_value < 0 else "■"
    subtitle_html = (
        f'<div style="margin-top:10px;font-size:0.92rem;color:#64748B;font-weight:600;">{subtitle}</div>'
        if str(subtitle).strip()
        else ""
    )
    st.markdown(
        f"""
        <div style="
            background:{bg};
            border:1px solid rgba(148,163,184,0.20);
            border-left:6px solid {accent};
            border-radius:22px;
            padding:20px 22px 18px 22px;
            min-height:156px;
            box-shadow:0 10px 30px rgba(15,23,42,0.08);
        ">
          <div style="font-size:0.86rem;font-weight:700;color:#475569;letter-spacing:0.01em;">{title}</div>
          <div style="margin-top:10px;font-size:2.05rem;line-height:1.1;font-weight:900;color:#0F172A;">{value}</div>
          <div style="margin-top:14px;display:inline-flex;align-items:center;gap:8px;padding:8px 12px;border-radius:999px;background:rgba(255,255,255,0.88);color:{accent};font-size:1.08rem;font-weight:900;">
            <span style="font-size:1rem;">{arrow}</span>
            <span>{delta_text}</span>
          </div>
          {subtitle_html}
        </div>
        """,
        unsafe_allow_html=True,
    )


def _build_compare_metric_chart(left: dict, right: dict, metric_key: str, metric_label: str, value_kind: str = "number"):
    left_value = float(left.get(metric_key, 0) or 0)
    right_value = float(right.get(metric_key, 0) or 0)
    delta = right_value - left_value
    target_color = _comparison_delta_color(delta)

    fig = go.Figure()
    fig.add_bar(
        x=["기준", "대상"],
        y=[left_value, right_value],
        marker_color=["#CBD5E1", target_color],
        text=[left_value, right_value],
        textposition="outside",
        hovertemplate="구분=%{x}<br>값=%{y:,.1f}<extra></extra>",
    )

    if value_kind == "currency":
        fig.update_traces(texttemplate="₩%{y:,.0f}")
        delta_text = _comparison_delta_text(right_value, left_value)
    elif value_kind == "percent":
        fig.update_traces(texttemplate="%{y:.1f}%")
        delta_text = _comparison_delta_text(right_value, left_value, kind="percent")
    else:
        fig.update_traces(texttemplate="%{y:,.0f}")
        delta_text = _comparison_delta_text(right_value, left_value)

    fig.update_layout(
        height=280,
        margin=dict(l=10, r=10, t=58, b=10),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(248,250,252,0.85)",
        showlegend=False,
        title=dict(
            text=f"{metric_label}<br><sup style='color:{target_color};font-size:13px;'>변화 {delta_text}</sup>",
            x=0.03,
            xanchor="left",
            font=dict(size=16, color="#0F172A"),
        ),
        yaxis=dict(title="", gridcolor="rgba(148,163,184,0.18)", zeroline=False),
        xaxis=dict(title=""),
    )
    return fig


def _render_compare_section_style():
    st.markdown(
        """
        <style>
        .compare-panel {
            background: linear-gradient(180deg, rgba(248,250,252,0.98), rgba(241,245,249,0.92));
            border: 1px solid rgba(148,163,184,0.20);
            border-radius: 24px;
            padding: 18px 20px;
            box-shadow: 0 12px 28px rgba(15,23,42,0.06);
            margin-bottom: 12px;
        }
        .compare-panel-title {
            font-size: 1rem;
            font-weight: 800;
            color: #0F172A;
            margin-bottom: 4px;
        }
        .compare-panel-subtitle {
            font-size: 0.92rem;
            color: #64748B;
            font-weight: 600;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def _ml_risk_grade(prob: float) -> str:
    p = _safe_float(prob, 0.0)
    if p >= 0.8:
        return "Critical"
    if p >= 0.6:
        return "High"
    if p >= 0.4:
        return "Medium"
    return "Low"


def _prepare_ml_scored_view(churn_scored: pd.DataFrame) -> pd.DataFrame:
    if not isinstance(churn_scored, pd.DataFrame) or churn_scored.empty:
        return pd.DataFrame()

    df = churn_scored.copy()

    def _num(col: str, default: float = 0.0) -> pd.Series:
        if col in df.columns:
            return pd.to_numeric(df[col], errors="coerce").fillna(default)
        return pd.Series(default, index=df.index, dtype=float)

    df["churn_prob"] = _num("churn_prob", 0.0).clip(lower=0, upper=1)
    df["lifetime_sales"] = _num("lifetime_sales", 0.0).clip(lower=0)
    df["sales_per_30d"] = _num("sales_per_30d", 0.0).clip(lower=0)
    df["sales_sum_30d"] = _num("sales_sum_30d", 0.0).clip(lower=0)
    df["sales_sum_90d"] = _num("sales_sum_90d", 0.0).clip(lower=0)
    df["sales_sum_180d"] = _num("sales_sum_180d", 0.0).clip(lower=0)
    df["recency_days"] = _num("recency_days", 0.0)
    df["lifetime_order_count"] = _num("lifetime_order_count", 0.0)
    df["avg_order_value"] = _num("avg_order_value", 0.0).clip(lower=0)

    recent_30_actual = df["sales_sum_30d"].copy()
    recent_90_monthly = (df["sales_sum_90d"] / 3.0).round(0)
    recent_180_monthly = (df["sales_sum_180d"] / 6.0).round(0)

    blended_base = (
        recent_30_actual * 0.70
        + recent_90_monthly * 0.20
        + recent_180_monthly * 0.10
    )

    fallback_base = (
        recent_90_monthly.where(recent_90_monthly > 0, recent_180_monthly)
        .where(lambda s: s > 0, 0)
    )

    df["recent_30d_actual_sales"] = recent_30_actual.round(0)
    df["recent_90d_monthly_avg_sales"] = recent_90_monthly.clip(lower=0)
    df["recent_180d_monthly_avg_sales"] = recent_180_monthly.clip(lower=0)
    df["protection_value_base"] = blended_base.where(recent_30_actual > 0, fallback_base).fillna(0).round(0)
    df["protection_value"] = (df["churn_prob"] * df["protection_value_base"]).round(0)
    df["protection_value_strict_30d"] = (df["churn_prob"] * df["recent_30d_actual_sales"]).round(0)

    df["risk_grade"] = df["churn_prob"].apply(_ml_risk_grade)
    df["expected_loss"] = (df["churn_prob"].fillna(0) * df["lifetime_sales"].fillna(0)).round(0)
    df["expected_loss_30d"] = df["protection_value"]

    if "Final_Segment" not in df.columns:
        df["Final_Segment"] = "미분류"

    if "고객ID" not in df.columns:
        id_col = _pick_col(df, ["customer_id", "CustomerID", "user_id", "id"])
        if id_col:
            df["고객ID"] = df[id_col]

    if "last_order_date" in df.columns:
        try:
            df["last_order_date"] = pd.to_datetime(df["last_order_date"], errors="coerce").dt.strftime("%Y-%m-%d")
        except Exception:
            pass

    return df


def _build_ml_summary_lines(df: pd.DataFrame) -> list[str]:
    if not isinstance(df, pd.DataFrame) or df.empty:
        return ["ML 이탈예측 결과가 없어 요약을 생성하지 못했습니다."]

    total = len(df)
    critical = int(df["risk_grade"].eq("Critical").sum()) if "risk_grade" in df.columns else 0
    high = int(df["risk_grade"].eq("High").sum()) if "risk_grade" in df.columns else 0
    medium = int(df["risk_grade"].eq("Medium").sum()) if "risk_grade" in df.columns else 0

    expected_loss = float(df.get("expected_loss", pd.Series(dtype=float)).fillna(0).sum()) if "expected_loss" in df.columns else 0.0
    expected_loss_30d = float(df.get("expected_loss_30d", pd.Series(dtype=float)).fillna(0).sum()) if "expected_loss_30d" in df.columns else 0.0

    top_seg = "-"
    if "Final_Segment" in df.columns:
        top_seg_s = df.groupby("Final_Segment").size().sort_values(ascending=False)
        if not top_seg_s.empty:
            top_seg = str(top_seg_s.index[0])

    top_loss_label = "-"
    group_col = None
    for cand in ["category", "카테고리", "Final_Segment", "segment"]:
        if cand in df.columns:
            group_col = cand
            break
    if group_col:
        tmp = df.dropna(subset=[group_col]).groupby(group_col)["expected_loss"].sum().sort_values(ascending=False)
        if not tmp.empty:
            top_loss_label = _pet_category_label(str(tmp.index[0])) if group_col in {"category", "카테고리"} else str(tmp.index[0])

    lines = [
        f"전체 고객 {total:,}명 중 Critical {critical:,}명, High {high:,}명, Medium {medium:,}명으로 확인됩니다.",
        f"누적매출 기준 예상 이탈손실은 {_fmt_currency(expected_loss)} 수준입니다.",
        f"최근 실매출 기반 예상 방어가치는 {_fmt_currency(expected_loss_30d)} 수준입니다.",
        f"가장 큰 위험군은 {top_seg} 세그먼트이며, 손실 집중 영역은 {top_loss_label}입니다.",
    ]
    return lines


def _prepare_ml_download_table(df: pd.DataFrame) -> pd.DataFrame:
    if not isinstance(df, pd.DataFrame) or df.empty:
        return pd.DataFrame()

    out = df.copy()
    if "churn_prob" in out.columns:
        out["이탈확률"] = (pd.to_numeric(out["churn_prob"], errors="coerce") * 100).round(1)
    if "expected_loss" in out.columns:
        out["예상이탈손실"] = out["expected_loss"].apply(_fmt_currency)
    if "lifetime_sales" in out.columns:
        out["누적매출"] = out["lifetime_sales"].apply(_fmt_currency)
    if "sales_per_30d" in out.columns:
        out["최근30일실매출"] = out["recent_30d_actual_sales"].apply(_fmt_currency) if "recent_30d_actual_sales" in out.columns else out["sales_per_30d"].apply(_fmt_currency)
    if "recency_days" in out.columns:
        out["휴면일수"] = pd.to_numeric(out["recency_days"], errors="coerce").round(0)
    if "avg_order_value" in out.columns:
        out["평균주문금액"] = out["avg_order_value"].apply(_fmt_currency)

    preferred = [
        "고객ID", "risk_grade", "이탈확률", "휴면일수", "lifetime_order_count",
        "누적매출", "최근30일실매출", "예상이탈손실", "Final_Segment", "last_order_date"
    ]
    preferred = [c for c in preferred if c in out.columns]
    return out[preferred].copy()


def _prepare_ml_loss_focus_table(df: pd.DataFrame) -> tuple[pd.DataFrame, str]:
    if not isinstance(df, pd.DataFrame) or df.empty or "expected_loss" not in df.columns:
        return pd.DataFrame(), ""

    group_col = None
    for cand in ["category", "카테고리", "Final_Segment"]:
        if cand in df.columns:
            group_col = cand
            break
    if not group_col:
        return pd.DataFrame(), ""

    tmp = df.dropna(subset=[group_col]).copy()
    if tmp.empty:
        return pd.DataFrame(), ""

    tmp["expected_loss"] = pd.to_numeric(tmp["expected_loss"], errors="coerce").fillna(0)
    tmp = (
        tmp.groupby(group_col, as_index=False)["expected_loss"]
        .sum()
        .sort_values("expected_loss", ascending=False)
    )
    if tmp.empty:
        return pd.DataFrame(), group_col

    label_col = "표시그룹"
    if group_col in {"category", "카테고리"}:
        tmp[label_col] = tmp[group_col].apply(_pet_category_label)
        tmp = tmp.groupby(label_col, as_index=False)["expected_loss"].sum().sort_values("expected_loss", ascending=False)
    else:
        tmp[label_col] = tmp[group_col].astype(str)

    tmp = tmp.head(5).copy()
    tmp["예상 이탈 손실"] = tmp["expected_loss"].apply(_fmt_currency)
    return tmp, group_col


def _prepare_ml_recency_bucket_table(df: pd.DataFrame) -> pd.DataFrame:
    if not isinstance(df, pd.DataFrame) or df.empty or "recency_days" not in df.columns:
        return pd.DataFrame()

    tmp = df.copy()
    tmp["recency_days"] = pd.to_numeric(tmp["recency_days"], errors="coerce")
    tmp = tmp.dropna(subset=["recency_days"]).copy()
    if tmp.empty:
        return pd.DataFrame()

    bins = [-1, 30, 60, 90, 180, 10**9]
    labels = ["0-30일", "31-60일", "61-90일", "91-180일", "181일+"]
    tmp["휴면구간"] = pd.cut(tmp["recency_days"], bins=bins, labels=labels)

    agg_dict = {"고객수": ("recency_days", "size")}
    if "churn_prob" in tmp.columns:
        tmp["churn_prob"] = pd.to_numeric(tmp["churn_prob"], errors="coerce")
        agg_dict["평균이탈확률"] = ("churn_prob", "mean")

    out = tmp.groupby("휴면구간", observed=False).agg(**agg_dict).reset_index()
    out = out.dropna(subset=["휴면구간"]).copy()
    if "평균이탈확률" in out.columns:
        out["평균이탈확률_pct"] = (out["평균이탈확률"] * 100).round(1)
    return out


def _ml_grade_label(grade: str) -> str:
    return {
        "Critical": "즉시 관리",
        "High": "관리 필요",
        "Medium": "관심 필요",
        "Low": "안정",
    }.get(str(grade), str(grade))


def _ml_action_label(row: pd.Series) -> str:
    grade = str(row.get("risk_grade", ""))
    recency = _safe_int(row.get("recency_days", 0), 0)
    if grade == "Critical":
        return "쿠폰 발송 + 재구매 알림"
    if grade == "High":
        return "재구매 알림 발송"
    if recency >= 90:
        return "휴면 복귀 메시지 발송"
    if grade == "Medium":
        return "관심상품 재노출"
    return "일반 CRM 유지"


def _prepare_ml_easy_table(df: pd.DataFrame) -> pd.DataFrame:
    if not isinstance(df, pd.DataFrame) or df.empty:
        return pd.DataFrame()

    out = df.copy()
    if "고객ID" not in out.columns:
        out["고객ID"] = out.index.astype(str)

    out["위험상태"] = out.get("risk_grade", "").apply(_ml_grade_label)
    out["추천액션"] = out.apply(_ml_action_label, axis=1)

    if "churn_prob" in out.columns:
        out["이탈확률"] = (pd.to_numeric(out["churn_prob"], errors="coerce").fillna(0) * 100).round(1).astype(str) + "%"
    if "recency_days" in out.columns:
        out["휴면일수"] = pd.to_numeric(out["recency_days"], errors="coerce").fillna(0).round(0).astype(int)
    if "lifetime_sales" in out.columns:
        out["누적매출"] = pd.to_numeric(out["lifetime_sales"], errors="coerce").fillna(0).apply(_fmt_currency)
    if "expected_loss_30d" in out.columns:
        out["예상방어가치"] = pd.to_numeric(out["protection_value"], errors="coerce").fillna(0).apply(_fmt_currency)
    elif "expected_loss" in out.columns:
        out["예상방어가치"] = pd.to_numeric(out["expected_loss"], errors="coerce").fillna(0).apply(_fmt_currency)
    if "last_order_date" in out.columns:
        out["최근 구매일"] = out["last_order_date"].fillna("-")
    else:
        out["최근 구매일"] = "-"

    preferred = [
        "고객ID", "위험상태", "최근 구매일", "휴면일수", "누적매출", "예상방어가치", "추천액션", "이탈확률"
    ]
    preferred = [c for c in preferred if c in out.columns]
    return out[preferred].copy()


def _build_ml_easy_insights(df: pd.DataFrame) -> list[str]:
    if not isinstance(df, pd.DataFrame) or df.empty:
        return ["ML 이탈예측 결과가 없어 쉬운 요약을 만들지 못했습니다."]

    risky = df[df["risk_grade"].isin(["Critical", "High"])].copy() if "risk_grade" in df.columns else df.copy()
    critical_cnt = int(df["risk_grade"].eq("Critical").sum()) if "risk_grade" in df.columns else 0
    high_cnt = int(df["risk_grade"].eq("High").sum()) if "risk_grade" in df.columns else 0

    if "recency_days" in risky.columns:
        risky["recency_days"] = pd.to_numeric(risky["recency_days"], errors="coerce")
        overdue_90 = int((risky["recency_days"] >= 90).sum())
    else:
        overdue_90 = 0

    top10_protect = 0
    if "expected_loss_30d" in risky.columns:
        top10_protect = _safe_int(risky["expected_loss_30d"].fillna(0).sort_values(ascending=False).head(10).sum(), 0)
    elif "expected_loss" in risky.columns:
        top10_protect = _safe_int(risky["expected_loss"].fillna(0).sort_values(ascending=False).head(10).sum(), 0)

    action_df = _prepare_ml_action_counts(df)
    top_action = str(action_df.iloc[0]["추천액션"]) if not action_df.empty else "쿠폰 발송 + 재구매 알림"

    return [
        f"지금 바로 관리가 필요한 고객은 {critical_cnt:,}명이고, 추가로 관리가 필요한 고객은 {high_cnt:,}명입니다.",
        f"최근 90일 이상 구매가 없는 위험 고객은 {overdue_90:,}명으로, 휴면 복귀 메시지를 먼저 보내는 것이 좋습니다.",
        f"매출 영향이 큰 상위 10명만 먼저 관리해도 {_fmt_currency(top10_protect)} 수준의 방어 기회를 볼 수 있고, 가장 추천되는 액션은 '{top_action}'입니다.",
    ]


def _prepare_ml_action_counts(df: pd.DataFrame) -> pd.DataFrame:
    if not isinstance(df, pd.DataFrame) or df.empty:
        return pd.DataFrame()
    tmp = df.copy()
    tmp["추천액션"] = tmp.apply(_ml_action_label, axis=1)
    out = tmp.groupby("추천액션").size().reset_index(name="고객수").sort_values("고객수", ascending=False)
    return out


def _render_saved_runs_comparison_tab(effective_user_key: str, is_member: bool):
    section_header("비교분석", "저장된 분석 2건을 선택해 핵심 성과와 위험도를 한 화면에서 비교합니다.", kicker="COMPARE")

    if not is_member:
        st.info("비교분석은 로그인 후 저장한 분석이 2건 이상 있을 때 사용할 수 있습니다.")
        return

    runs = list_runs(effective_user_key)
    if len(runs) < 2:
        st.info("비교할 저장 분석이 부족합니다. 분석을 2건 이상 저장하면 비교 탭이 활성화됩니다.")
        return

    options = [r.get("run_id") for r in runs if r.get("run_id") is not None]
    label_map = {r.get("run_id"): _make_run_label(r) for r in runs if r.get("run_id") is not None}
    if len(options) < 2:
        st.info("비교 가능한 저장 분석을 찾지 못했습니다.")
        return

    default_left = st.session_state.get("compare_left_run_id", options[0])
    default_right = st.session_state.get("compare_right_run_id", options[1])
    if default_left not in options:
        default_left = options[0]
    if default_right not in options or default_right == default_left:
        default_right = next((rid for rid in options if rid != default_left), options[0])

    c1, c2 = st.columns(2)
    with c1:
        left_id = st.selectbox(
            "비교 기준 분석",
            options,
            index=options.index(default_left),
            format_func=lambda x: label_map.get(x, str(x)),
            key="compare_left_run_select",
        )
    with c2:
        right_candidates = [rid for rid in options if rid != left_id] or options
        right_default = default_right if default_right in right_candidates else right_candidates[0]
        right_id = st.selectbox(
            "비교 대상 분석",
            right_candidates,
            index=right_candidates.index(right_default),
            format_func=lambda x: label_map.get(x, str(x)),
            key="compare_right_run_select",
        )

    st.session_state["compare_left_run_id"] = left_id
    st.session_state["compare_right_run_id"] = right_id

    left_run = get_run(effective_user_key, int(left_id))
    right_run = get_run(effective_user_key, int(right_id))
    if not left_run or not right_run:
        st.warning("선택한 저장 분석을 불러오지 못했습니다.")
        return

    left = _build_compare_snapshot(left_run)
    right = _build_compare_snapshot(right_run)

    _render_compare_section_style()

    st.markdown(
        f"""
        <div class="compare-panel">
          <div class="compare-panel-title">비교 기준</div>
          <div class="compare-panel-subtitle">좌측 기준: <b>{left['label']}</b> · 우측 대상: <b>{right['label']}</b></div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    m1, m2, m3, m4 = st.columns(4)
    with m1:
        _render_compare_metric_card(
            "매출 비교",
            _fmt_currency(right["revenue"]),
            _comparison_delta_text(right["revenue"], left["revenue"]),
            right["revenue"] - left["revenue"],

        )
    with m2:
        _render_compare_metric_card(
            "주문수 비교",
            _fmt_int(right["orders"]),
            _comparison_delta_text(right["orders"], left["orders"]),
            right["orders"] - left["orders"],

        )
    with m3:
        _render_compare_metric_card(
            "고객수 비교",
            _fmt_int(right["customers"]),
            _comparison_delta_text(right["customers"], left["customers"]),
            right["customers"] - left["customers"],

        )
    with m4:
        _render_compare_metric_card(
            "고위험 고객 비율",
            f"{right['high_ratio']:.1f}%",
            _comparison_delta_text(right["high_ratio"], left["high_ratio"], kind="percent"),
            right["high_ratio"] - left["high_ratio"],

        )

    metric_options = {
        "매출": ("revenue", "currency"),
        "주문수": ("orders", "number"),
        "고객수": ("customers", "number"),
        "예상 이탈 매출": ("expected_loss", "currency"),
        "다음달 예상 매출": ("forecast_value", "currency"),
        "평균 리스크": ("avg_risk", "number"),
        "고위험 고객 비율": ("high_ratio", "percent"),
        "환불률": ("refund_rate_pct", "percent"),
    }

    chart_left = dict(left)
    chart_right = dict(right)
    chart_left["refund_rate_pct"] = left["refund_rate"] * 100
    chart_right["refund_rate_pct"] = right["refund_rate"] * 100

    st.markdown(
        """
        <div class="compare-panel">
          <div class="compare-panel-title">비교 차트</div>
          <div class="compare-panel-subtitle">3개 슬롯을 각각 선택해서 보고 싶은 지표를 동시에 비교할 수 있습니다.</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    selector_cols = st.columns(3)
    metric_labels = list(metric_options.keys())
    default_metrics = ["매출", "주문수", "고위험 고객 비율"]
    selected_metrics = []
    for idx, col in enumerate(selector_cols):
        with col:
            selected_metrics.append(
                st.selectbox(
                    f"차트 {idx+1}",
                    metric_labels,
                    index=metric_labels.index(default_metrics[idx]),
                    key=f"compare_chart_metric_{idx+1}",
                )
            )

    chart_cols = st.columns(3)
    for idx, metric_name in enumerate(selected_metrics):
        metric_key, metric_kind = metric_options[metric_name]
        fig = _build_compare_metric_chart(chart_left, chart_right, metric_key, metric_name, metric_kind)
        with chart_cols[idx]:
            chart_card(metric_name, fig, "기준 대비 대상 분석의 증감을 색상과 수치로 강조합니다.", height=320)

    summary_lines = []
    revenue_delta = right["revenue"] - left["revenue"]
    risk_delta = right["avg_risk"] - left["avg_risk"]
    high_ratio_delta = right["high_ratio"] - left["high_ratio"]
    refund_delta = (right["refund_rate"] - left["refund_rate"]) * 100

    if revenue_delta > 0:
        summary_lines.append(f"대상 분석의 매출은 기준 대비 {_fmt_currency(revenue_delta)} 높습니다.")
    elif revenue_delta < 0:
        summary_lines.append(f"대상 분석의 매출은 기준 대비 {_fmt_currency(abs(revenue_delta))} 낮습니다.")
    else:
        summary_lines.append("두 분석의 매출 수준은 동일합니다.")

    risk_direction = "높아졌습니다" if risk_delta > 0 else "낮아졌습니다" if risk_delta < 0 else "같습니다"
    if risk_delta != 0:
        summary_lines.append(f"평균 리스크는 기준 대비 {abs(risk_delta):.1f}p {risk_direction}.")
    else:
        summary_lines.append("평균 리스크는 두 분석이 동일합니다.")

    summary_lines.append(f"고위험 고객 비율 변화는 {high_ratio_delta:+.1f}%p입니다.")
    summary_lines.append(f"환불률 변화는 {refund_delta:+.1f}%p입니다.")

    if left["top_category"] != right["top_category"]:
        summary_lines.append(f"핵심 관리 카테고리는 {left['top_category']} → {right['top_category']}로 바뀌었습니다.")
    else:
        summary_lines.append(f"핵심 관리 카테고리는 두 분석 모두 {left['top_category']}입니다.")

    if left["top_segment"] != right["top_segment"]:
        summary_lines.append(f"주요 세그먼트는 {left['top_segment']} → {right['top_segment']}로 이동했습니다.")
    else:
        summary_lines.append(f"주요 세그먼트는 두 분석 모두 {left['top_segment']}입니다.")

    insight_box("비교 요약", summary_lines[:6], tone="info")

    detail_rows = [
        {
            "항목": "저장일시",
            "기준 분석": _fmt_saved_at(left["created_at"]),
            "대상 분석": _fmt_saved_at(right["created_at"]),
            "변화": "-",
        },
        {
            "항목": "매출",
            "기준 분석": _fmt_currency(left["revenue"]),
            "대상 분석": _fmt_currency(right["revenue"]),
            "변화": _comparison_delta_text(right["revenue"], left["revenue"]),
        },
        {
            "항목": "주문수",
            "기준 분석": _fmt_int(left["orders"]),
            "대상 분석": _fmt_int(right["orders"]),
            "변화": _comparison_delta_text(right["orders"], left["orders"]),
        },
        {
            "항목": "고객수",
            "기준 분석": _fmt_int(left["customers"]),
            "대상 분석": _fmt_int(right["customers"]),
            "변화": _comparison_delta_text(right["customers"], left["customers"]),
        },
        {
            "항목": "평균 리스크",
            "기준 분석": f"{left['avg_risk']:.1f}",
            "대상 분석": f"{right['avg_risk']:.1f}",
            "변화": f"{right['avg_risk'] - left['avg_risk']:+.1f}",
        },
        {
            "항목": "고위험 고객 비율",
            "기준 분석": f"{left['high_ratio']:.1f}%",
            "대상 분석": f"{right['high_ratio']:.1f}%",
            "변화": _comparison_delta_text(right["high_ratio"], left["high_ratio"], kind="percent"),
        },
        {
            "항목": "예상 이탈 매출",
            "기준 분석": _fmt_currency(left["expected_loss"]),
            "대상 분석": _fmt_currency(right["expected_loss"]),
            "변화": _comparison_delta_text(right["expected_loss"], left["expected_loss"]),
        },
        {
            "항목": "다음달 예상 매출",
            "기준 분석": _fmt_currency(left["forecast_value"]),
            "대상 분석": _fmt_currency(right["forecast_value"]),
            "변화": _comparison_delta_text(right["forecast_value"], left["forecast_value"]),
        },
        {
            "항목": "환불률",
            "기준 분석": f"{left['refund_rate']*100:.1f}%",
            "대상 분석": f"{right['refund_rate']*100:.1f}%",
            "변화": f"{(right['refund_rate'] - left['refund_rate']) * 100:+.1f}%p",
        },
        {
            "항목": "주요 세그먼트",
            "기준 분석": left["top_segment"],
            "대상 분석": right["top_segment"],
            "변화": "변경" if left["top_segment"] != right["top_segment"] else "동일",
        },
        {
            "항목": "핵심 카테고리",
            "기준 분석": left["top_category"],
            "대상 분석": right["top_category"],
            "변화": "변경" if left["top_category"] != right["top_category"] else "동일",
        },
    ]
    table_block(pd.DataFrame(detail_rows), caption="저장 분석 비교표", height=460)


def report_step(df_std: pd.DataFrame, user_key: str = "guest"):
    session_user = st.session_state.get("user_key", "guest")
    effective_user_key = session_user if (session_user != "guest" and user_key == "guest") else user_key
    is_member = effective_user_key != "guest"

    st.session_state.setdefault("view_run_id", None)
    st.session_state.setdefault("sidebar_run_pick", "현재 분석")

    _render_saved_runs_sidebar(effective_user_key, is_member)

    selected_run_id = st.session_state.get("view_run_id")
    saved_run = saved_report = saved_metrics = None
    if is_member and selected_run_id is not None:
        saved_run = get_run(effective_user_key, int(selected_run_id))
        if saved_run:
            saved_report = saved_run.get("report", {})
            saved_metrics = saved_run.get("metrics", {})

    showing_saved = saved_report is not None
    negative_sales_mode = _get_negative_sales_mode()

    if not showing_saved:
        result = compute_rfm_and_risk(df_std)
        kpi = result.get("kpi", {})
        cat = result.get("category_risk", pd.DataFrame())
        cust_list = result.get("customer_list", pd.DataFrame())
        seg = result.get("segment_summary", pd.DataFrame())
        forecast = result.get("forecast", {})
        inv = result.get("inventory", pd.DataFrame())
        rfm_df = result.get("rfm", pd.DataFrame())
        churn_summary = result.get("churn_summary", {}) or {}
        churn_scored = result.get("churn_scored", pd.DataFrame())
        category_churn_df = result.get("category_churn", pd.DataFrame())
        refund = result.get("refund", {}) or {}
        refund_rate = float(refund.get("refund_rate", 0.0) or 0.0)
        refund_customers = refund.get("refund_customers", pd.DataFrame())
        refund_category = refund.get("refund_category", pd.DataFrame())
        refill_cycle = result.get("refill_cycle_by_category", pd.DataFrame())
        refill_group = result.get("refill_category_group", pd.DataFrame())
        multi_pet_df = result.get("multi_pet_customers", pd.DataFrame())
        pet_insights = result.get("pet_insights", {}) or {}
        metrics = _metrics_from_result(result)
        df_work = result.get("df_work")
    else:
        kpi = saved_report.get("kpi", {}) or {}
        forecast = saved_report.get("forecast", {}) or {}
        cat = pd.DataFrame(saved_report.get("category_risk", []) or [])
        seg = pd.DataFrame(saved_report.get("segment_summary", []) or [])
        cust_list = pd.DataFrame(saved_report.get("customer_list", []) or [])
        inv = pd.DataFrame(saved_report.get("inventory", []) or [])
        churn_summary = saved_report.get("churn_summary", {}) or {}
        churn_scored = pd.DataFrame(saved_report.get("churn_scored", []) or [])
        category_churn_df = pd.DataFrame(saved_report.get("category_churn", []) or [])
        refund_saved = saved_report.get("refund", {}) or {}
        refund_rate = float(refund_saved.get("refund_rate", 0.0) or 0.0)
        refund_customers = pd.DataFrame(refund_saved.get("refund_customers", []) or [])
        refund_category = pd.DataFrame(refund_saved.get("refund_category", []) or [])
        refill_cycle = pd.DataFrame(saved_report.get("refill_cycle_by_category", []) or [])
        refill_group = pd.DataFrame(saved_report.get("refill_category_group", []) or [])
        multi_pet_df = pd.DataFrame(saved_report.get("multi_pet_customers", []) or [])
        pet_insights = saved_report.get("pet_insights", {}) or {}
        rfm_df = pd.DataFrame(saved_report.get("rfm", []) or [])
        metrics = saved_metrics or {}
        df_work = None
        negative_sales_mode = saved_report.get("negative_sales_mode", negative_sales_mode)

    total_customers = int(kpi.get("total_customers", 0) or 0)
    high_ratio = float(kpi.get("high_ratio", 0) or 0)
    avg_risk = float(kpi.get("avg_risk", 0) or 0)
    expected_loss = int(kpi.get("expected_loss", 0) or 0)

    top_seg_name = "-"
    if isinstance(seg, pd.DataFrame) and not seg.empty and {"세그먼트", "인원"}.issubset(seg.columns):
        top_seg_name = str(seg.sort_values("인원", ascending=False).iloc[0]["세그먼트"])

    top_cat_name = "-"
    if isinstance(cat, pd.DataFrame) and not cat.empty and {"카테고리", "위험"}.issubset(cat.columns):
        top_cat_name = str(cat.sort_values("위험", ascending=False).iloc[0]["카테고리"])

    high_cnt = 0
    if isinstance(rfm_df, pd.DataFrame) and not rfm_df.empty and "위험도" in rfm_df.columns:
        high_cnt = int(rfm_df["위험도"].eq("High").sum())
    elif isinstance(cust_list, pd.DataFrame) and not cust_list.empty and "위험도" in cust_list.columns:
        high_cnt = int(cust_list["위험도"].astype(str).eq("High").sum())

    st.markdown('<div class="page-eyebrow">PRO REPORT</div>', unsafe_allow_html=True)
    st.markdown('<div class="page-title">펫커머스 재구매 · 이탈 대응 리포트</div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="page-subtitle">반려동물 커머스 거래 데이터를 바탕으로 고객 행동, 핵심 카테고리 재구매 주기, 다반려 고객 구조, 카테고리 이탈 위험을 운영 액션 중심으로 정리했습니다.</div>',
        unsafe_allow_html=True,
    )

    if showing_saved:
        saved_label = _make_run_label(saved_run or {})
        st.info(f"📌 저장된 분석을 보고 있어요: {saved_label}")

    if not showing_saved:
        _save_panel(result, metrics, effective_user_key, is_member)

    _pdf_controls(
        "펫커머스 재구매 · 이탈 대응 리포트",
        st.session_state.get("user_key", "guest"),
        (saved_run.get("run_name") if showing_saved and saved_run else None) or st.session_state.get("draft_run_name", "현재 분석"),
        kpi,
        cat if isinstance(cat, pd.DataFrame) else pd.DataFrame(),
        seg if isinstance(seg, pd.DataFrame) else pd.DataFrame(),
        cust_list if isinstance(cust_list, pd.DataFrame) else pd.DataFrame(),
        churn_scored if isinstance(churn_scored, pd.DataFrame) else pd.DataFrame(),
        refund_category if isinstance(refund_category, pd.DataFrame) else pd.DataFrame(),
        inv if isinstance(inv, pd.DataFrame) else pd.DataFrame(),
        forecast if isinstance(forecast, dict) else {},
    )

    tab_overview, tab_segment, tab_category, tab_ml, tab_refund, tab_inventory, tab_compare = st.tabs([
        "Executive Summary", "세그먼트", "카테고리", "ML 이탈예측", "환불", "재고", "비교분석"
    ])

    with tab_overview:
        section_header("Executive Summary", "핵심 KPI와 우선 대응 포인트를 먼저 보여주는 경영진 요약 화면입니다.", kicker="OVERVIEW")
        c1, c2, c3, c4 = st.columns(4)
        with c1:
            metric_card("고위험 고객 비율", f"{high_ratio:.1f}%", f"고위험 고객 {_fmt_int(high_cnt)}명")
        with c2:
            metric_card("평균 리스크 스코어", f"{avg_risk:.0f}", "기준 예시: High ≥ 70")
        with c3:
            metric_card("예상 매출 이탈", _fmt_currency(expected_loss), "단기 리텐션 우선 대응 필요")
        with c4:
            metric_card("환불률", f"{refund_rate*100:.1f}%", "상품/배송/품질 이슈 점검")

        _render_negative_sales_mode_notice(negative_sales_mode)
        insight_box("핵심 인사이트", _build_exec_summary(high_ratio, expected_loss, refund_rate, top_seg_name, top_cat_name), tone="info")

        g1, g2 = st.columns([1, 1])
        with g1:
            chart_card("현재 위험 수준", gauge_card(avg_risk, "평균 리스크", reference=70), "평균 위험 점수를 0~100 기준으로 요약합니다.", height=300)
        with g2:
            if isinstance(cat, pd.DataFrame) and not cat.empty and {"카테고리", "위험"}.issubset(cat.columns):
                cat_plot = cat.copy()
                cat_plot["위험"] = pd.to_numeric(cat_plot["위험"], errors="coerce")
                cat_plot = cat_plot.dropna(subset=["위험"]).copy()
                cat_plot["펫카테고리"] = cat_plot["카테고리"].apply(_pet_category_label)

                # 같은 펫카테고리로 매핑되는 세부 카테고리를 하나로 집계해
                # 동일 라벨에 막대가 중복으로 그려지는 현상을 방지합니다.
                agg_dict = {"위험": ("위험", "mean")}
                if "고객수" in cat_plot.columns:
                    agg_dict["고객수"] = ("고객수", "sum")
                else:
                    agg_dict["고객수"] = ("위험", "size")

                cat_plot = (
                    cat_plot.groupby("펫카테고리", as_index=False)
                    .agg(**agg_dict)
                )

                cat_plot["위험"] = cat_plot["위험"].round(1)
                cat_plot = cat_plot.sort_values("위험", ascending=True)

                fig = px.bar(
                    cat_plot,
                    x="위험",
                    y="펫카테고리",
                    orientation="h",
                    text="위험",
                    color="위험",
                    color_continuous_scale="Blues",
                    hover_data={"고객수": True, "위험": ":.1f"},
                )
                fig.update_layout(
                    coloraxis_showscale=False,
                    xaxis_title="위험",
                    yaxis_title="카테고리",
                )
                fig.update_traces(texttemplate="%{text:.1f}", textposition="outside")
                chart_card("핵심 펫카테고리 위험 우선순위", fig, "사료·소모품·건강관리 등 핵심 카테고리부터 우선 관리합니다.")
            else:
                st.info("카테고리 위험도 데이터가 없습니다.")

        if isinstance(rfm_df, pd.DataFrame) and not rfm_df.empty and {"Recency", "Monetary", "위험도"}.issubset(rfm_df.columns):
            fig = px.scatter(
                rfm_df.sample(min(len(rfm_df), 1500), random_state=42),
                x="Recency",
                y="Monetary",
                color="위험도",
                opacity=0.75,
            )
            chart_card("고객 가치 vs 최근성 분포", fig, "오른쪽 위 고객은 최근 구매가 오래됐지만 가치가 큰 고객으로, 이탈 시 영향이 큽니다.")

        section_header("Recommended Actions", "이 리포트를 보고 바로 실행할 수 있는 액션을 우선순위로 정리했습니다.", kicker="ACTION")
        action_card("사료/소모품 재구매 방어", "사료·패드·모래 같은 반복소비 카테고리는 재구매주기 기준으로 리마인드와 구독 제안을 먼저 적용하세요.", "Priority 1")
        action_card("핵심 카테고리 이탈 방지", "전체 이탈보다 '왜 우리 몰에서 사료만 안 사는가'를 먼저 점검해야 합니다. 카테고리별 이탈 위험 고객부터 관리하세요.", "Priority 2")
        action_card("다반려 고객 교차판매", "강아지·고양이 교차구매 또는 높은 카테고리 다양도를 보이는 고객은 묶음상품과 장바구니 추천에 적합합니다.", "Priority 3")

    with tab_segment:
        section_header("세그먼트 분석", "고객군별 규모, 가치, 평균 위험도를 시각적으로 확인합니다.", kicker="SEGMENT")
        if isinstance(seg, pd.DataFrame) and not seg.empty:
            left, right = st.columns(2)
            with left:
                if {"세그먼트", "인원"}.issubset(seg.columns):
                    fig = px.pie(seg, names="세그먼트", values="인원", hole=0.58)
                    fig.update_traces(textposition="inside", textinfo="percent+label")
                    chart_card("세그먼트 구성 비율", fig, "고객군이 어떤 구조로 구성되어 있는지 보여줍니다.")
            with right:
                if {"세그먼트", "평균금액"}.issubset(seg.columns):
                    seg_plot = seg.copy()
                    seg_plot["평균금액"] = pd.to_numeric(seg_plot["평균금액"], errors="coerce")
                    fig = px.bar(seg_plot, x="세그먼트", y="평균금액", text="평균금액", color="평균금액", color_continuous_scale="Blues")
                    fig.update_layout(coloraxis_showscale=False)
                    fig.update_traces(texttemplate="%{text:,.0f}", textposition="outside")
                    chart_card("세그먼트별 평균 매출", fig, "가치가 높은 고객군과 규모가 큰 고객군을 함께 판단합니다.")
            if {"세그먼트", "평균위험"}.issubset(seg.columns):
                seg_plot = seg.copy()
                seg_plot["평균위험"] = pd.to_numeric(seg_plot["평균위험"], errors="coerce")
                fig = px.bar(seg_plot, x="세그먼트", y="평균위험", text="평균위험", color="평균위험", color_continuous_scale="RdYlBu_r")
                fig.update_layout(coloraxis_showscale=False)
                fig.update_traces(texttemplate="%{text:.1f}", textposition="outside")
                chart_card("세그먼트별 평균 위험도", fig, "어떤 고객군의 리텐션 개입 우선순위가 높은지 보여줍니다.")
            table_block(seg, caption="세그먼트 상세 집계표")
        else:
            st.info("세그먼트 데이터가 없습니다.")

    with tab_category:
        section_header("카테고리 분석", "일반 카테고리 표가 아니라, 펫 운영자가 바로 실행할 수 있는 재구매·이탈 대응 포인트를 보여줍니다.", kicker="CATEGORY")

        data_for_cat = df_work.copy() if isinstance(df_work, pd.DataFrame) and not df_work.empty else pd.DataFrame()
        cat_col = _pick_col(data_for_cat, ["카테고리", "category", "Category"])
        sales_col = _pick_col(data_for_cat, ["매출", "주문금액", "금액"])

        pet_refill = _prepare_pet_refill_table(refill_cycle)
        pet_multi = _prepare_multi_pet_table(multi_pet_df)
        pet_cat_churn = _prepare_category_churn_table(category_churn_df)

        core_points = _build_pet_core_points(refill_cycle)
        insight_box("펫커머스 핵심 운영 포인트", core_points, tone="info")

        if isinstance(pet_refill, pd.DataFrame) and not pet_refill.empty:
            summary_cols = st.columns(min(3, len(pet_refill.head(3))))
            for idx, (_, row) in enumerate(pet_refill.head(3).iterrows()):
                with summary_cols[idx]:
                    metric_card(
                        row.get("펫카테고리", row.get("카테고리", "-")),
                        f"{_fmt_int(row.get('재구매주기', 0))}일",
                        str(row.get("운영액션", "-"))[:40],
                    )

        if cat_col and sales_col:
            pet_sales = _make_pet_category_sales_summary(data_for_cat, cat_col, sales_col)
            if not pet_sales.empty:
                c1, c2 = st.columns(2)
                with c1:
                    fig = px.bar(
                        pet_sales,
                        x="펫카테고리",
                        y="총매출",
                        text="총매출",
                        color="총매출",
                        color_continuous_scale="Blues",
                    )
                    fig.update_layout(coloraxis_showscale=False)
                    fig.update_traces(texttemplate="%{text:,.0f}", textposition="outside")
                    chart_card("펫카테고리별 총매출", fig, "사료·소모품·건강관리 등 펫 운영 기준 카테고리로 다시 묶어 보여줍니다.")
                with c2:
                    fig = px.pie(pet_sales, names="펫카테고리", values="총매출", hole=0.58)
                    fig.update_traces(textposition="inside", textinfo="percent+label")
                    chart_card("펫카테고리 매출 비중", fig, "어떤 펫 카테고리가 핵심 매출축인지 보여줍니다.")

        section_header("재구매 주기 기반 운영 시점", "재구매주기를 보는 데서 끝내지 않고, 언제 어떤 CRM 액션을 넣을지까지 연결합니다.", kicker="REFILL")

        if isinstance(pet_refill, pd.DataFrame) and not pet_refill.empty:
            st.caption("반복소비 카테고리는 재구매주기보다 3~7일 앞서 알림하는 전략을 권장합니다.")
            table_block(pet_refill, caption="펫카테고리별 재구매 주기 · 추천 발송 시점 · 운영 액션")
        else:
            st.info("재구매주기 데이터가 없습니다.")

        section_header("다반려 추정 고객", "실제 반려 수를 확정하는 데이터는 아니지만, 구매 패턴 기반으로 다반려 가구 후보를 찾아 교차판매에 활용합니다.", kicker="MULTI-PET")

        mp_cnt = int((pet_insights or {}).get("multi_pet_cnt", 0) or 0)
        mp_ratio = float((pet_insights or {}).get("multi_pet_ratio", 0) or 0)

        insight_box(
            "다반려 추정 해석",
            [
                f"다반려 추정 고객은 {_fmt_int(mp_cnt)}명, 전체의 {mp_ratio:.1f}%입니다.",
                "강아지·고양이 키워드 동시 탐지 또는 카테고리 다양도/구매빈도 패턴을 기반으로 추정했습니다.",
                "이 고객군은 복합 장바구니, 소모품 세트, 교차 카테고리 추천의 우선 대상입니다.",
            ],
            tone="success",
        )

        if isinstance(pet_multi, pd.DataFrame) and not pet_multi.empty:
            table_block(pet_multi, caption="다반려 추정 고객 Top 20")
        else:
            st.info("다반려 추정 데이터가 없습니다.")

        section_header("핵심 카테고리 이탈 고객", "전체 고객 이탈이 아니라, 특정 고객이 우리 몰에서 특정 펫 카테고리 구매를 끊을 가능성을 탐지합니다.", kicker="CATEGORY CHURN")
        insight_box(
            "왜 중요한가",
            [
                "펫커머스에서는 간식은 사지만 사료는 다른 곳에서 사는 고객이 발생합니다.",
                "이 기능은 고객 전체 이탈이 아니라 핵심 카테고리 이탈을 따로 포착합니다.",
                "즉, '왜 우리 몰에서 사료만 빠졌는가?' 같은 운영 질문에 직접 연결됩니다.",
            ],
            tone="info",
        )

        if not pet_cat_churn.empty:
            dormant = int((pet_cat_churn["위험도"] == "휴면").sum()) if "위험도" in pet_cat_churn.columns else 0
            danger = int((pet_cat_churn["위험도"] == "위험").sum()) if "위험도" in pet_cat_churn.columns else 0
            ml_cnt = int((pet_cat_churn["예측방식"] == "ML").sum()) if "예측방식" in pet_cat_churn.columns else 0
            rule_cnt = int((pet_cat_churn["예측방식"] == "규칙기반").sum()) if "예측방식" in pet_cat_churn.columns else 0

            st.markdown("#### 핵심 지표")
            kc1, kc2, kc3, kc4 = st.columns(4)
            with kc1:
                metric_card("휴면 위험", f"{dormant:,}건", "장기 미구매로 전환된 카테고리 고객")
            with kc2:
                metric_card("이탈 위험", f"{danger:,}건", "핵심 카테고리 이탈 가능 고객")
            with kc3:
                metric_card("ML 예측", f"{ml_cnt:,}건", "모델 기반으로 탐지된 건수")
            with kc4:
                metric_card("규칙기반", f"{rule_cnt:,}건", "주기/경과일 기반 탐지 건수")

            risk_filter = st.selectbox(
                "위험도 필터",
                ["전체(위험+휴면)", "휴면", "위험"],
                key="cat_churn_risk_filter"
            )
            if risk_filter == "휴면":
                show_df = pet_cat_churn[pet_cat_churn["위험도"] == "휴면"].copy()
            elif risk_filter == "위험":
                show_df = pet_cat_churn[pet_cat_churn["위험도"] == "위험"].copy()
            else:
                show_df = pet_cat_churn[pet_cat_churn["위험도"] != "정상"].copy()

            table_block(show_df, caption=f"핵심 펫카테고리 이탈 위험 고객 ({risk_filter})")

            try:
                csv_bytes = pet_cat_churn.to_csv(index=False).encode("utf-8-sig")
                st.download_button(
                    "카테고리 이탈 위험 고객 다운로드",
                    data=csv_bytes,
                    file_name="category_churn_risk.csv",
                    mime="text/csv",
                )
            except Exception:
                pass
        else:
            st.info("카테고리 이탈 위험 데이터가 없습니다.")

        with st.expander("데이터 구조 안내", expanded=False):
            if not cat_col:
                st.warning(
                    "카테고리 컬럼이 없어 펫 특화 분석 일부가 제한됩니다. "
                    "재구매주기, 카테고리 이탈, 다반려 추정의 정확도가 낮아질 수 있습니다. "
                    "쿠팡형 데이터처럼 카테고리가 상품데이터에만 있다면, 매핑 단계에서 카테고리 컬럼을 추가해주세요."
                )
            else:
                st.caption("현재 데이터에는 카테고리 정보가 포함되어 있어 펫 특화 분석을 수행했습니다.")

    with tab_ml:
        section_header("ML 기반 이탈예측", "복잡한 모델 화면보다 지금 바로 챙겨야 할 고객과 추천 액션을 쉽게 보여줍니다.", kicker="ML")
        avg_churn_prob = float((churn_summary or {}).get("avg_churn_prob", 0.0) or 0.0)
        ml_view = _prepare_ml_scored_view(churn_scored)

        high_risk_count = int(ml_view["risk_grade"].isin(["Critical", "High"]).sum()) if not ml_view.empty else int((churn_summary or {}).get("high_risk_count", 0) or 0)
        critical_count = int(ml_view["risk_grade"].eq("Critical").sum()) if not ml_view.empty else 0
        protectable_sales = int(ml_view["expected_loss_30d"].fillna(0).sum()) if not ml_view.empty and "expected_loss_30d" in ml_view.columns else 0

        s1, s2, s3 = st.columns(3)
        with s1:
            metric_card("이탈 위험 고객", f"{high_risk_count:,}명", "관리 필요 + 즉시 관리 고객")
        with s2:
            metric_card("즉시 관리 필요", f"{critical_count:,}명", "지금 바로 쿠폰/알림 권장")
        with s3:
            metric_card("예상 방어 가능 매출", _fmt_currency(protectable_sales), "최근 30일 매출 기준")

        if not ml_view.empty:
            insight_box("한눈에 보는 요약", _build_ml_easy_insights(ml_view), tone="info")

            top_left, top_right = st.columns(2)
            with top_left:
                grade_df = (
                    ml_view.groupby("risk_grade")
                    .size()
                    .reset_index(name="고객수")
                )
                if not grade_df.empty:
                    grade_df["위험상태"] = grade_df["risk_grade"].apply(_ml_grade_label)
                    grade_df["순서"] = grade_df["risk_grade"].map({"Critical": 0, "High": 1, "Medium": 2, "Low": 3}).fillna(9)
                    grade_df = grade_df.sort_values("순서")
                    fig = px.bar(
                        grade_df,
                        x="위험상태",
                        y="고객수",
                        text="고객수",
                        color="위험상태",
                        color_discrete_map={
                            "즉시 관리": "#EF4444",
                            "관리 필요": "#F59E0B",
                            "관심 필요": "#3B82F6",
                            "안정": "#10B981",
                        },
                    )
                    fig.update_traces(textposition="outside")
                    fig.update_layout(xaxis_title="", yaxis_title="고객 수", showlegend=False, height=340)
                    chart_card("위험상태별 고객 수", fig, "복잡한 확률 대신 지금 관리가 얼마나 필요한지만 보여줍니다.", height=340)

            with top_right:
                recency_bucket_df = _prepare_ml_recency_bucket_table(ml_view)
                if not recency_bucket_df.empty:
                    fig = px.bar(
                        recency_bucket_df,
                        x="휴면구간",
                        y="고객수",
                        text="고객수",
                        color="휴면구간",
                        color_discrete_map={
                            "0-30일": "#10B981",
                            "31-60일": "#3B82F6",
                            "61-90일": "#6366F1",
                            "91-180일": "#F59E0B",
                            "181일+": "#EF4444",
                        },
                    )
                    fig.update_traces(textposition="outside")
                    fig.update_layout(xaxis_title="휴면일수 구간", yaxis_title="고객 수", showlegend=False, height=340)
                    chart_card("최근 구매가 끊긴 고객 수", fig, "어느 시점의 고객이 많이 쌓여 있는지 쉽게 확인할 수 있습니다.", height=340)
                else:
                    st.info("휴면일수 기준 요약 차트를 만들 데이터가 없습니다.")

            action_df = _prepare_ml_action_counts(ml_view)
            if not action_df.empty:
                section_header("추천 액션", "어려운 차트 대신 바로 실행할 수 있는 액션으로 정리했습니다.", kicker="ACTION")
                action_cols = st.columns(min(3, len(action_df.head(3))))
                for idx, (_, row) in enumerate(action_df.head(3).iterrows()):
                    with action_cols[idx]:
                        action_card(str(row.get("추천액션", "추천 액션")), f"대상 고객 {int(row.get('고객수', 0)):,}명", f"우선순위 {idx+1}")

            section_header("우선 대응 인사이트", "카테고리보다 먼저, 누가 왜 위험한지 쉽게 읽을 수 있도록 정리했습니다.", kicker="INSIGHT")
            insight_rows = []
            recency_bucket_df = _prepare_ml_recency_bucket_table(ml_view)
            if not recency_bucket_df.empty:
                top_bucket = recency_bucket_df.sort_values("고객수", ascending=False).iloc[0]
                insight_rows.append({
                    "항목": "가장 많이 쌓인 고객 구간",
                    "내용": f"{top_bucket['휴면구간']} 고객 {int(top_bucket['고객수']):,}명",
                })
            critical_sales = 0
            if "expected_loss_30d" in ml_view.columns:
                critical_sales = _safe_int(ml_view.loc[ml_view["risk_grade"] == "Critical", "expected_loss_30d"].fillna(0).sum(), 0)
            elif "expected_loss" in ml_view.columns:
                critical_sales = _safe_int(ml_view.loc[ml_view["risk_grade"] == "Critical", "expected_loss"].fillna(0).sum(), 0)
            insight_rows.append({
                "항목": "즉시 관리 고객 영향",
                "내용": f"즉시 관리 고객군의 예상 방어가치는 {_fmt_currency(critical_sales)}입니다.",
            })
            if not action_df.empty:
                top_action = action_df.iloc[0]
                insight_rows.append({
                    "항목": "가장 추천되는 액션",
                    "내용": f"{top_action['추천액션']} · 대상 고객 {int(top_action['고객수']):,}명",
                })
            table_block(pd.DataFrame(insight_rows), caption="지금 바로 보면 좋은 핵심 포인트", height=220)

            section_header("방어 우선 고객", "누구를 먼저 챙길지 쉽게 볼 수 있도록 꼭 필요한 정보만 남겼습니다.", kicker="ACTIONABLE LIST")
            filter_cols = st.columns(3)
            with filter_cols[0]:
                state_options = ["전체", "즉시 관리", "관리 필요", "관심 필요", "안정"]
                selected_state = st.selectbox("위험상태", state_options, key="ml_easy_state_filter")
            with filter_cols[1]:
                sort_option = st.selectbox("정렬 기준", ["예상 방어가치 큰 순", "이탈확률 높은 순", "휴면일수 긴 순"], key="ml_easy_sort")
            with filter_cols[2]:
                top_n = st.selectbox("표시 건수", [20, 50, 100, 200], index=1, key="ml_easy_top_n")

            filtered = ml_view.copy()
            filtered["위험상태"] = filtered["risk_grade"].apply(_ml_grade_label)
            if selected_state != "전체":
                filtered = filtered[filtered["위험상태"] == selected_state]

            if sort_option == "이탈확률 높은 순" and "churn_prob" in filtered.columns:
                filtered = filtered.sort_values("churn_prob", ascending=False)
            elif sort_option == "휴면일수 긴 순" and "recency_days" in filtered.columns:
                filtered = filtered.sort_values("recency_days", ascending=False)
            elif "expected_loss_30d" in filtered.columns:
                filtered = filtered.sort_values("expected_loss_30d", ascending=False)
            elif "expected_loss" in filtered.columns:
                filtered = filtered.sort_values("expected_loss", ascending=False)

            easy_table = _prepare_ml_easy_table(filtered).head(int(top_n))
            table_block(easy_table, caption="방어 우선 고객 리스트", height=460)

            dl_full = _prepare_ml_easy_table(filtered)
            dl_now = _prepare_ml_easy_table(filtered[filtered["risk_grade"] == "Critical"]) if "risk_grade" in filtered.columns else pd.DataFrame()
            try:
                d1, d2 = st.columns(2)
                with d1:
                    st.download_button(
                        "방어 우선 고객 전체 다운로드",
                        data=dl_full.to_csv(index=False).encode("utf-8-sig"),
                        file_name="ml_priority_customers.csv",
                        mime="text/csv",
                        use_container_width=True,
                    )
                with d2:
                    st.download_button(
                        "즉시 관리 고객만 다운로드",
                        data=dl_now.to_csv(index=False).encode("utf-8-sig"),
                        file_name="ml_critical_customers.csv",
                        mime="text/csv",
                        use_container_width=True,
                    )
            except Exception:
                pass

            with st.expander("상세 수치 보기", expanded=False):
                detail_rows = []
                if not recency_bucket_df.empty and "평균이탈확률_pct" in recency_bucket_df.columns:
                    for _, row in recency_bucket_df.iterrows():
                        detail_rows.append({
                            "휴면구간": row["휴면구간"],
                            "고객수": int(row["고객수"]),
                            "평균 이탈확률": f"{float(row['평균이탈확률_pct']):.1f}%",
                        })
                if detail_rows:
                    table_block(pd.DataFrame(detail_rows), caption="휴면구간별 상세 수치", height=260)
                st.caption(f"전체 고객 평균 이탈확률은 {avg_churn_prob:.1%}입니다.")
        else:
            st.info("ML 이탈예측 결과가 없습니다.")
    with tab_refund:
        section_header("환불 분석", "환불률과 환불 위험 고객, 카테고리별 환불 구조를 확인합니다.", kicker="REFUND")
        _render_negative_sales_mode_notice(negative_sales_mode)

        if isinstance(refund_category, pd.DataFrame) and not refund_category.empty and {"카테고리", "환불률"}.issubset(refund_category.columns):
            refund_plot = refund_category.copy()
            refund_plot["환불률"] = pd.to_numeric(refund_plot["환불률"], errors="coerce")
            refund_plot["환불률표시"] = refund_plot["환불률"].round(4)
            refund_plot["펫카테고리"] = refund_plot["카테고리"].apply(_pet_category_label)
            refund_chart = _prepare_category_axis_chart_df(refund_plot, ["환불률"])
            refund_chart["환불률표시"] = pd.to_numeric(refund_chart["환불률"], errors="coerce").round(4)

            fig = px.bar(
                refund_chart.sort_values("표시라벨", ascending=True),
                x="환불률",
                y="표시라벨",
                orientation="h",
                text="환불률표시",
                color="환불률",
                hover_data={
                    "카테고리": True,
                    "펫카테고리": True,
                    "환불률": False,
                    "환불률표시": ":.4f",
                    "표시라벨": False,
                },
                color_continuous_scale="Reds",
            )
            fig.update_layout(coloraxis_showscale=False, yaxis_title="카테고리", xaxis_title="환불률 (%)")
            fig.update_traces(texttemplate="%{text:.4f}%", textposition="outside")
            chart_card("카테고리별 환불률", fig, "하단 표와 같은 기준으로 환불률을 표시해 스케일 혼동을 줄였습니다.")

        c1, c2 = st.columns(2)
        with c1:
            if isinstance(refund_customers, pd.DataFrame) and not refund_customers.empty:
                table_block(refund_customers, caption="환불 위험 고객")
            else:
                st.info("환불 위험 고객 데이터가 없습니다.")
        with c2:
            if isinstance(refund_category, pd.DataFrame) and not refund_category.empty:
                show_refund = refund_category.copy()
                if "카테고리" in show_refund.columns:
                    show_refund["펫카테고리"] = show_refund["카테고리"].apply(_pet_category_label)
                table_block(show_refund, caption="카테고리 환불 집계")
            else:
                st.info("카테고리 환불 데이터가 없습니다.")

    with tab_compare:
        _render_saved_runs_comparison_tab(effective_user_key, is_member)

    with tab_inventory:
        section_header("재고 전략 및 판매 예측", "품절로 인한 매출 손실을 줄이기 위해 카테고리별 안전재고 우선순위와 다음달 판매 규모를 함께 제안합니다.", kicker="INVENTORY STRATEGY")
        forecast_value = int((forecast or {}).get("value", 0) or 0)
        avg_daily_revenue = float((forecast or {}).get("avg_daily_revenue", 0) or 0)
        basis_days = int((forecast or {}).get("basis_days", 0) or 0)
        inventory_show = _prepare_inventory_table(inv)
        priority_count = int((inventory_show["우선순위"] == "최우선 확보").sum()) if not inventory_show.empty and "우선순위" in inventory_show.columns else 0

        c1, c2, c3 = st.columns(3)
        with c1:
            metric_card("다음달 예상 매출", _fmt_currency(forecast_value), f"최근 {basis_days}일 추세를 반영한 간이 예측")
        with c2:
            metric_card("일평균 예상 매출", _fmt_currency(avg_daily_revenue), "최근 거래 흐름 기준 일평균 매출")
        with c3:
            metric_card("최우선 확보 카테고리", f"{_fmt_int(priority_count)}개", "즉시 발주 또는 일일 점검 필요")

        insight_box("재고 전략 요약", _build_inventory_points(inv, forecast, total_customers), tone="info")

        action_cols = st.columns(3)
        for idx, card in enumerate(_inventory_action_cards(inv)):
            with action_cols[idx % 3]:
                action_card(card["title"], card["body"], card["tag"])

        inventory_chart = _prepare_category_axis_chart_df(inventory_show, ["안전재고량", "예상판매량"], include_priority=True)
        if isinstance(inventory_show, pd.DataFrame) and not inventory_show.empty and not inventory_chart.empty and {"표시라벨", "안전재고량"}.issubset(inventory_chart.columns):
            chart_left, chart_right = st.columns(2)
            with chart_left:
                inv_plot = inventory_chart.sort_values("표시라벨", ascending=True).copy()
                fig = px.bar(
                    inv_plot,
                    x="안전재고량",
                    y="표시라벨",
                    orientation="h",
                    text="안전재고량",
                    color="우선순위" if "우선순위" in inv_plot.columns else "안전재고량",
                    hover_data={
                        "카테고리": True,
                        "펫카테고리": True,
                        "안전재고량": ":,",
                        "예상판매량": ":.1f" if "예상판매량" in inv_plot.columns else False,
                        "표시라벨": False,
                    },
                    color_discrete_map={
                        "최우선 확보": "#EF4444",
                        "집중 관리": "#F59E0B",
                        "기본 운영": "#10B981",
                    },
                    color_continuous_scale="Teal",
                )
                fig.update_layout(coloraxis_showscale=False, yaxis_title="카테고리", xaxis_title="안전재고량")
                fig.update_traces(textposition="outside")
                chart_card("카테고리별 안전재고량", fig, "실제 카테고리 기준으로 권장 안전재고량을 비교하고, 우선순위는 색상으로만 표시합니다.")

            with chart_right:
                sales_plot = inventory_chart.sort_values("표시라벨", ascending=True).copy()
                if "예상판매량" in sales_plot.columns:
                    fig2 = px.bar(
                        sales_plot,
                        x="예상판매량",
                        y="표시라벨",
                        orientation="h",
                        text="예상판매량",
                        color="우선순위" if "우선순위" in sales_plot.columns else "예상판매량",
                        hover_data={
                            "카테고리": True,
                            "펫카테고리": True,
                            "예상판매량": ":.1f",
                            "안전재고량": ":," if "안전재고량" in sales_plot.columns else False,
                            "표시라벨": False,
                        },
                        color_discrete_map={
                            "최우선 확보": "#EF4444",
                            "집중 관리": "#F59E0B",
                            "기본 운영": "#10B981",
                        },
                        color_continuous_scale="Blues",
                    )
                    fig2.update_layout(coloraxis_showscale=False, yaxis_title="카테고리", xaxis_title="예상판매량")
                    fig2.update_traces(textposition="outside")
                    chart_card("카테고리별 예상 판매량", fig2, "같은 카테고리 순서를 유지해 안전재고량과 예상 판매량을 쉽게 비교할 수 있습니다.")

            table_block(inventory_show, caption="재고 전략 상세표")
        else:
            st.info("재고 전략을 계산할 수 있는 데이터가 없습니다.")
