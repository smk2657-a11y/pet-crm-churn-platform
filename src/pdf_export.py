
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

import pandas as pd
from jinja2 import Environment, FileSystemLoader, select_autoescape


BASE_DIR = Path(__file__).resolve().parent.parent
TEMPLATES_DIR = BASE_DIR / "templates"
STATIC_DIR = BASE_DIR / "static"


def _env() -> Environment:
    return Environment(
        loader=FileSystemLoader(str(TEMPLATES_DIR)),
        autoescape=select_autoescape(["html", "xml"]),
        trim_blocks=True,
        lstrip_blocks=True,
    )


def _safe_int(x: Any, default: int = 0) -> int:
    try:
        if x is None or x == "":
            return default
        return int(float(x))
    except Exception:
        return default


def _safe_float(x: Any, default: float = 0.0) -> float:
    try:
        if x is None or x == "":
            return default
        return float(x)
    except Exception:
        return default


def _fmt_currency(x: Any) -> str:
    return f"₩{_safe_int(x):,}"


def _fmt_int(x: Any) -> str:
    return f"{_safe_int(x):,}"


def _fmt_pct(x: Any, digits: int = 1) -> str:
    v = _safe_float(x, 0.0)
    if abs(v) <= 1:
        v *= 100
    return f"{v:.{digits}f}%"


def _is_datetime_series(s: pd.Series) -> bool:
    return pd.api.types.is_datetime64_any_dtype(s) or pd.api.types.is_datetime64tz_dtype(s)


def _normalize_df_for_pdf(df: pd.DataFrame | None, limit: int = 30) -> pd.DataFrame:
    if df is None or not isinstance(df, pd.DataFrame) or df.empty:
        return pd.DataFrame()

    out = df.head(limit).copy()

    for col in out.columns:
        s = out[col]

        if pd.api.types.is_categorical_dtype(s):
            out[col] = s.astype("object")
            s = out[col]

        if _is_datetime_series(s):
            out[col] = s.astype(str)
            s = out[col]

        if pd.api.types.is_numeric_dtype(s):
            continue

        out[col] = out[col].where(pd.notna(out[col]), "")
        out[col] = out[col].astype(str)
        out[col] = out[col].replace(
            {
                "nan": "",
                "NaN": "",
                "NaT": "",
                "None": "",
                "<NA>": "",
            }
        )

    return out


def _df_records(df: pd.DataFrame | None, limit: int = 30) -> list[dict]:
    tmp = _normalize_df_for_pdf(df, limit=limit)
    if tmp.empty:
        return []
    return tmp.to_dict(orient="records")


def _select_existing_columns(df: pd.DataFrame | None, candidates: list[str], limit: int = 30) -> pd.DataFrame:
    if df is None or not isinstance(df, pd.DataFrame) or df.empty:
        return pd.DataFrame()

    existing = [c for c in candidates if c in df.columns]
    if not existing:
        return pd.DataFrame()

    return _normalize_df_for_pdf(df[existing], limit=limit)


def _pick_top_rows(
    df: pd.DataFrame | None,
    sort_candidates: list[str],
    limit: int = 8,
    ascending: bool = False,
) -> list[dict]:
    if df is None or not isinstance(df, pd.DataFrame) or df.empty:
        return []

    tmp = df.copy()

    for col in tmp.columns:
        if pd.api.types.is_categorical_dtype(tmp[col]):
            tmp[col] = tmp[col].astype("object")

    for c in sort_candidates:
        if c in tmp.columns:
            try:
                sort_series = pd.to_numeric(tmp[c], errors="coerce")
                tmp = tmp.assign(__sort_key__=sort_series)
                tmp = tmp.sort_values("__sort_key__", ascending=ascending, na_position="last")
                tmp = tmp.drop(columns=["__sort_key__"])
                break
            except Exception:
                pass

    return _df_records(tmp, limit=limit)


def _normalize_sections(selected_sections: dict | None) -> dict:
    defaults = {
        "overview": True,
        "segment": True,
        "category": True,
        "ml": True,
        "refund": True,
        "inventory": True,
    }
    if not isinstance(selected_sections, dict):
        return defaults
    defaults.update({k: bool(v) for k, v in selected_sections.items()})
    return defaults


def _negative_sales_mode_label(mode: str) -> str:
    return {
        "refund": "환불/취소 후보로 처리",
        "exclude": "분석에서 제외",
        "keep": "원본 그대로 유지",
    }.get(mode, mode or "-")


def _negative_sales_mode_desc(mode: str) -> str:
    return {
        "refund": "음수 매출은 환불/취소 후보로 간주하여 환불 분석에도 반영합니다.",
        "exclude": "음수 매출은 이상치 또는 비분석 데이터로 간주하여 현재 분석에서 제외합니다.",
        "keep": "음수 매출을 원본 그대로 유지하여 정산/오류 가능성까지 함께 해석합니다.",
    }.get(mode, "")


def _summary_lines_from_kpi(
    kpi: dict,
    top_seg: str,
    top_cat: str,
    refund_rate: float,
    avg_churn_prob: float = 0.0,
    protection_value: float = 0.0,
    critical_count: int = 0,
    high_risk_count: int = 0,
) -> list[str]:
    high_ratio = _safe_float(kpi.get("high_ratio", 0))
    avg_risk = _safe_float(kpi.get("avg_risk", 0))

    lines = [
        f"고위험 고객 비율은 {_fmt_pct(high_ratio)} 수준이며, 평균 이탈확률은 {_fmt_pct(avg_churn_prob)}입니다.",
        f"즉시 관리 고객 {critical_count:,}명, 관리 필요 고객 {high_risk_count:,}명으로 우선 대응 대상이 구분됩니다.",
        f"최근 실매출 기반 예상 방어가치는 {_fmt_currency(protection_value)} 수준입니다.",
    ]

    if refund_rate > 0:
        lines.append(f"환불률은 {_fmt_pct(refund_rate)} 수준으로, 고객 경험 이슈를 함께 점검할 필요가 있습니다.")
    if top_seg and top_seg != "-":
        lines.append(f"고객군 기준 우선 관리 세그먼트는 {top_seg}입니다.")
    if top_cat and top_cat != "-":
        lines.append(f"카테고리 관점에서는 {top_cat} 영역을 먼저 점검하는 것이 좋습니다.")
    if avg_risk > 0:
        lines.append(f"참고로 평균 위험 점수는 {avg_risk:.0f}점입니다.")

    return lines[:5]


def _make_bar_rows(rows: list[dict], label_key: str, value_key: str, max_items: int = 8) -> list[dict]:
    if not rows:
        return []

    temp = []
    for row in rows[:max_items]:
        label = str(row.get(label_key, "-"))
        try:
            value = float(row.get(value_key, 0) or 0)
        except Exception:
            value = 0.0
        temp.append({"label": label, "value": value})

    max_value = max([r["value"] for r in temp], default=1) or 1
    out = []
    for r in temp:
        out.append(
            {
                "label": r["label"],
                "value": r["value"],
                "value_display": f"{r['value']:.1f}" if abs(r["value"]) < 1000 else f"{int(round(r['value'])):,}",
                "width_pct": round((r["value"] / max_value) * 100, 1) if max_value else 0,
            }
        )
    return out


def _segment_comp_rows(seg_df: pd.DataFrame) -> list[dict]:
    rows = _pick_top_rows(seg_df, ["인원"], limit=8, ascending=False)
    if not rows:
        return []

    total = sum(_safe_int(r.get("인원", 0)) for r in rows) or 1
    out = []
    for row in rows:
        people = _safe_int(row.get("인원", 0))
        out.append(
            {
                "label": str(row.get("세그먼트", "-")),
                "value": people,
                "value_display": f"{people:,}명 · {people / total * 100:.1f}%",
                "width_pct": round(people / total * 100, 1),
            }
        )
    return out


def _ml_grade_label(grade: Any) -> str:
    return {
        "Critical": "즉시 관리",
        "High": "관리 필요",
        "Medium": "관심 필요",
        "Low": "안정",
    }.get(str(grade), str(grade) if grade is not None else "-")


def _num_series(df: pd.DataFrame, col: str, default: float = 0.0) -> pd.Series:
    if col in df.columns:
        return pd.to_numeric(df[col], errors="coerce").fillna(default)
    return pd.Series(default, index=df.index, dtype=float)


def _prepare_ml_pdf_view(ml_df: pd.DataFrame) -> pd.DataFrame:
    if ml_df is None or not isinstance(ml_df, pd.DataFrame) or ml_df.empty:
        return pd.DataFrame()

    df = ml_df.copy()

    df["churn_prob"] = _num_series(df, "churn_prob", 0.0).clip(lower=0, upper=1)
    df["recency_days"] = _num_series(df, "recency_days", 0.0)
    df["lifetime_sales"] = _num_series(df, "lifetime_sales", 0.0).clip(lower=0)
    df["sales_sum_30d"] = _num_series(df, "sales_sum_30d", 0.0).clip(lower=0)
    df["sales_sum_90d"] = _num_series(df, "sales_sum_90d", 0.0).clip(lower=0)
    df["sales_sum_180d"] = _num_series(df, "sales_sum_180d", 0.0).clip(lower=0)

    recent_30_actual = df["sales_sum_30d"].round(0)
    recent_90_monthly = (df["sales_sum_90d"] / 3.0).round(0)
    recent_180_monthly = (df["sales_sum_180d"] / 6.0).round(0)

    blended_base = recent_30_actual * 0.70 + recent_90_monthly * 0.20 + recent_180_monthly * 0.10
    fallback_base = recent_90_monthly.where(recent_90_monthly > 0, recent_180_monthly).where(lambda s: s > 0, 0)

    if "recent_30d_actual_sales" not in df.columns:
        df["recent_30d_actual_sales"] = recent_30_actual
    if "protection_value_base" not in df.columns:
        df["protection_value_base"] = blended_base.where(recent_30_actual > 0, fallback_base).fillna(0).round(0)

    if "protection_value" not in df.columns:
        df["protection_value"] = (df["churn_prob"] * df["protection_value_base"]).round(0)
    if "expected_loss_30d" not in df.columns:
        df["expected_loss_30d"] = df["protection_value"]
    else:
        df["expected_loss_30d"] = pd.to_numeric(df["expected_loss_30d"], errors="coerce").fillna(df["protection_value"])

    if "risk_grade" not in df.columns:
        df["risk_grade"] = df["churn_prob"].apply(
            lambda p: "Critical" if p >= 0.8 else "High" if p >= 0.6 else "Medium" if p >= 0.4 else "Low"
        )

    if "recommended_action" not in df.columns:
        recency = df["recency_days"]
        df["recommended_action"] = df["risk_grade"].map(
            {
                "Critical": "쿠폰 발송 + 재구매 알림",
                "High": "재구매 알림 발송",
                "Medium": "관심상품 재노출",
                "Low": "일반 CRM 유지",
            }
        )
        df.loc[(df["risk_grade"] == "Low") & (recency >= 90), "recommended_action"] = "휴면 복귀 메시지 발송"

    if "고객ID" not in df.columns:
        for cand in ["customer_id", "CustomerID", "user_id", "id"]:
            if cand in df.columns:
                df["고객ID"] = df[cand]
                break
    if "last_order_date" in df.columns:
        try:
            df["last_order_date"] = pd.to_datetime(df["last_order_date"], errors="coerce").dt.strftime("%Y-%m-%d")
        except Exception:
            pass

    return df


def _build_ml_risk_bar_rows(ml_view: pd.DataFrame) -> list[dict]:
    if ml_view.empty or "risk_grade" not in ml_view.columns:
        return []
    order = ["Critical", "High", "Medium", "Low"]
    temp = (
        ml_view["risk_grade"]
        .astype(str)
        .value_counts()
        .reindex(order, fill_value=0)
        .reset_index()
    )
    temp.columns = ["risk_grade", "고객수"]
    temp["위험상태"] = temp["risk_grade"].map(_ml_grade_label)
    rows = _make_bar_rows(temp.to_dict(orient="records"), "위험상태", "고객수", max_items=4)
    for row in rows:
        row["value_display"] = f"{int(round(row['value'])):,}명"
    return rows


def _build_ml_recency_bar_rows(ml_view: pd.DataFrame) -> list[dict]:
    if ml_view.empty:
        return []
    recency = _num_series(ml_view, "recency_days", 0)
    bins = [-1, 30, 60, 90, 180, 10**9]
    labels = ["0-30일", "31-60일", "61-90일", "91-180일", "181일+"]
    bucket = pd.cut(recency, bins=bins, labels=labels)
    temp = bucket.value_counts().reindex(labels, fill_value=0).reset_index()
    temp.columns = ["휴면구간", "고객수"]
    rows = _make_bar_rows(temp.to_dict(orient="records"), "휴면구간", "고객수", max_items=5)
    for row in rows:
        row["value_display"] = f"{int(round(row['value'])):,}명"
    return rows


def _build_ml_action_rows(ml_view: pd.DataFrame) -> list[dict]:
    if ml_view.empty or "recommended_action" not in ml_view.columns:
        return []
    temp = (
        ml_view["recommended_action"]
        .fillna("추천 액션 없음")
        .astype(str)
        .value_counts()
        .reset_index()
    )
    temp.columns = ["추천액션", "고객수"]
    rows = _make_bar_rows(temp.to_dict(orient="records"), "추천액션", "고객수", max_items=4)
    for row in rows:
        row["value_display"] = f"{int(round(row['value'])):,}명"
    return rows


def _build_ml_insight_rows(ml_view: pd.DataFrame) -> list[dict]:
    if ml_view.empty:
        return []

    insights: list[dict] = []
    risk_rows = _build_ml_risk_bar_rows(ml_view)
    if risk_rows:
        top_risk = risk_rows[0]
        insights.append({"항목": "가장 큰 위험상태", "내용": f"{top_risk['label']} 고객 {int(round(top_risk['value'])):,}명"})

    recency_rows = _build_ml_recency_bar_rows(ml_view)
    if recency_rows:
        top_bucket = max(recency_rows, key=lambda r: r.get("value", 0))
        insights.append({"항목": "가장 많이 쌓인 휴면구간", "내용": f"{top_bucket['label']} 고객 {int(round(top_bucket['value'])):,}명"})

    critical_value = 0
    if "risk_grade" in ml_view.columns and "expected_loss_30d" in ml_view.columns:
        critical_value = _safe_int(ml_view.loc[ml_view["risk_grade"] == "Critical", "expected_loss_30d"].fillna(0).sum(), 0)
    insights.append({"항목": "즉시 관리 고객 영향", "내용": f"즉시 관리 고객군의 예상 방어가치는 {_fmt_currency(critical_value)}입니다."})

    action_rows = _build_ml_action_rows(ml_view)
    if action_rows:
        top_action = action_rows[0]
        insights.append({"항목": "가장 추천되는 액션", "내용": f"{top_action['label']} · 대상 고객 {int(round(top_action['value'])):,}명"})

    return insights[:4]


def _prepare_ml_priority_table(ml_view: pd.DataFrame, limit: int = 28) -> list[dict]:
    if ml_view.empty:
        return []

    df = ml_view.copy()
    if "expected_loss_30d" in df.columns:
        df = df.sort_values("expected_loss_30d", ascending=False, na_position="last")
    elif "churn_prob" in df.columns:
        df = df.sort_values("churn_prob", ascending=False, na_position="last")

    out = pd.DataFrame()
    out["고객ID"] = df.get("고객ID", pd.Series(["-"] * len(df), index=df.index))
    out["위험상태"] = df.get("risk_grade", pd.Series(["-"] * len(df), index=df.index)).map(_ml_grade_label)
    out["최근 구매일"] = df.get("last_order_date", pd.Series(["-"] * len(df), index=df.index)).fillna("-")
    out["휴면일수"] = _num_series(df, "recency_days", 0).round(0).astype(int)
    out["누적매출"] = _num_series(df, "lifetime_sales", 0).round(0).apply(_fmt_currency)
    out["예상방어가치"] = _num_series(df, "expected_loss_30d", 0).round(0).apply(_fmt_currency)
    out["추천액션"] = df.get("recommended_action", pd.Series(["-"] * len(df), index=df.index)).fillna("-")
    out["이탈확률"] = _num_series(df, "churn_prob", 0).mul(100).round(1).astype(str) + "%"

    return _df_records(out, limit=limit)


def _build_context(
    title: str,
    user_name: str,
    run_name: str,
    kpi: dict,
    category_df: pd.DataFrame,
    segment_df: pd.DataFrame,
    customer_df: pd.DataFrame,
    ml_df: pd.DataFrame,
    refund_df: pd.DataFrame,
    inventory_df: pd.DataFrame,
    forecast: dict | None,
    selected_sections: dict,
) -> dict:
    sections = _normalize_sections(selected_sections)

    category_rows = _pick_top_rows(category_df, ["위험", "평균위험", "risk_score", "총매출"], limit=8, ascending=False)
    segment_rows = _pick_top_rows(segment_df, ["인원", "평균위험"], limit=8, ascending=False)

    top_seg = str(segment_rows[0].get("세그먼트", "-")) if segment_rows else "-"
    top_cat = str(category_rows[0].get("카테고리", "-")) if category_rows else "-"

    refund_rate = 0.0
    if isinstance(refund_df, pd.DataFrame) and not refund_df.empty and "환불률" in refund_df.columns:
        try:
            refund_rate = float(pd.to_numeric(refund_df["환불률"], errors="coerce").fillna(0).max())
        except Exception:
            refund_rate = 0.0

    ml_view = _prepare_ml_pdf_view(ml_df)

    avg_churn_prob = 0.0
    if not ml_view.empty and "churn_prob" in ml_view.columns:
        avg_churn_prob = float(pd.to_numeric(ml_view["churn_prob"], errors="coerce").fillna(0).mean())

    critical_count = int(ml_view["risk_grade"].eq("Critical").sum()) if not ml_view.empty and "risk_grade" in ml_view.columns else 0
    high_risk_count = int(ml_view["risk_grade"].isin(["Critical", "High"]).sum()) if not ml_view.empty and "risk_grade" in ml_view.columns else 0
    high_manage_count = int(ml_view["risk_grade"].eq("High").sum()) if not ml_view.empty and "risk_grade" in ml_view.columns else 0
    medium_count = int(ml_view["risk_grade"].eq("Medium").sum()) if not ml_view.empty and "risk_grade" in ml_view.columns else 0

    protection_value_total = _safe_int(ml_view.get("expected_loss_30d", pd.Series(dtype=float)).fillna(0).sum(), 0) if not ml_view.empty else 0

    action_rows = _build_ml_action_rows(ml_view)
    top_action_label = action_rows[0]["label"] if action_rows else "-"

    summary_lines = _summary_lines_from_kpi(
        kpi,
        top_seg,
        top_cat,
        refund_rate,
        avg_churn_prob=avg_churn_prob,
        protection_value=protection_value_total,
        critical_count=critical_count,
        high_risk_count=high_risk_count,
    )

    ml_risk_rows = _build_ml_risk_bar_rows(ml_view)
    ml_recency_rows = _build_ml_recency_bar_rows(ml_view)
    ml_action_rows = action_rows
    ml_insight_rows = _build_ml_insight_rows(ml_view)
    ml_priority_rows = _prepare_ml_priority_table(ml_view, limit=28)

    refund_pdf_df = _select_existing_columns(
        refund_df,
        ["카테고리", "주문수", "환불수", "환불금액", "환불률"],
        limit=10,
    )
    if not refund_pdf_df.empty and "환불률" in refund_pdf_df.columns:
        try:
            rr = pd.to_numeric(refund_pdf_df["환불률"], errors="coerce")
            refund_pdf_df["환불률"] = rr.mul(100).round(1).astype(str) + "%"
        except Exception:
            pass
    if not refund_pdf_df.empty and "환불금액" in refund_pdf_df.columns:
        refund_pdf_df["환불금액"] = refund_pdf_df["환불금액"].apply(_fmt_currency)
    refund_rows = _df_records(refund_pdf_df, limit=10)

    inventory_pdf_df = _select_existing_columns(
        inventory_df,
        ["펫카테고리", "카테고리", "예상판매량", "일평균판매량", "안전재고량", "권장보유일수", "우선순위", "추천액션"],
        limit=8,
    )
    if not inventory_pdf_df.empty:
        if "안전재고량" in inventory_pdf_df.columns:
            inventory_pdf_df["안전재고량"] = inventory_pdf_df["안전재고량"].apply(
                lambda x: f"약 {_safe_int(x):,}개" if str(x).strip() != "" else ""
            )
        if "예상판매량" in inventory_pdf_df.columns:
            try:
                inventory_pdf_df["예상판매량"] = pd.to_numeric(inventory_pdf_df["예상판매량"], errors="coerce").round(1)
            except Exception:
                pass
    inventory_rows = _df_records(inventory_pdf_df, limit=8)

    forecast = forecast if isinstance(forecast, dict) else {}
    forecast_label = str(forecast.get("label", "다음달 예상 매출"))
    forecast_value = _safe_int(forecast.get("value", kpi.get("expected_loss", 0)))
    negative_sales_mode = forecast.get("negative_sales_mode") or ""

    overview_bar_rows = _make_bar_rows(category_rows, "카테고리", "위험", max_items=7) if category_rows else []
    segment_comp = _segment_comp_rows(segment_df)
    segment_risk_bars = _make_bar_rows(segment_rows, "세그먼트", "평균위험", max_items=8)

    category_bar_rows = []
    if category_rows:
        if "위험" in category_rows[0]:
            category_bar_rows = _make_bar_rows(category_rows, "카테고리", "위험", max_items=8)
        elif "평균위험" in category_rows[0]:
            category_bar_rows = _make_bar_rows(category_rows, "카테고리", "평균위험", max_items=8)
        elif "총매출" in category_rows[0]:
            category_bar_rows = _make_bar_rows(category_rows, "카테고리", "총매출", max_items=8)

    return {
        "title": title,
        "user_name": user_name,
        "run_name": run_name,
        "sections": sections,
        "negative_sales_mode_label": _negative_sales_mode_label(negative_sales_mode),
        "negative_sales_mode_desc": _negative_sales_mode_desc(negative_sales_mode),
        "summary": {
            "total_customers": _fmt_int(kpi.get("total_customers", len(ml_view) if not ml_view.empty else 0)),
            "high_ratio": _fmt_pct(kpi.get("high_ratio", 0)),
            "avg_risk": f"{_safe_float(kpi.get('avg_risk', 0)):.0f}점",
            "expected_loss": _fmt_currency(kpi.get("expected_loss", 0)),
            "protection_value": _fmt_currency(protection_value_total),
            "critical_count": _fmt_int(critical_count),
            "high_risk_count": _fmt_int(high_risk_count),
            "high_manage_count": _fmt_int(high_manage_count),
            "medium_count": _fmt_int(medium_count),
            "avg_churn_prob": _fmt_pct(avg_churn_prob),
            "refund_rate": _fmt_pct(refund_rate),
            "forecast_label": forecast_label,
            "forecast_value": _fmt_currency(forecast_value),
            "top_action_label": top_action_label,
        },
        "summary_lines": summary_lines,
        "overview_bar_rows": overview_bar_rows,
        "segment_comp_rows": segment_comp,
        "segment_risk_rows": segment_risk_bars,
        "segment_rows": segment_rows,
        "category_rows": category_rows,
        "category_bar_rows": category_bar_rows,
        "ml_rows": ml_priority_rows,
        "ml_risk_rows": ml_risk_rows,
        "ml_recency_rows": ml_recency_rows,
        "ml_action_rows": ml_action_rows,
        "ml_insight_rows": ml_insight_rows,
        "refund_rows": refund_rows,
        "inventory_rows": inventory_rows,
    }


def build_report_pdf(
    title: str,
    user_name: str,
    run_name: str,
    kpi: dict,
    category_df: pd.DataFrame,
    segment_df: pd.DataFrame,
    customer_df: pd.DataFrame,
    ml_df: pd.DataFrame,
    refund_df: pd.DataFrame,
    inventory_df: pd.DataFrame,
    forecast: dict | None = None,
    selected_sections: dict | None = None,
) -> bytes:
    env = _env()
    template = env.get_template("report_base.html")

    category_df = category_df if isinstance(category_df, pd.DataFrame) else pd.DataFrame()
    segment_df = segment_df if isinstance(segment_df, pd.DataFrame) else pd.DataFrame()
    customer_df = customer_df if isinstance(customer_df, pd.DataFrame) else pd.DataFrame()
    ml_df = ml_df if isinstance(ml_df, pd.DataFrame) else pd.DataFrame()
    refund_df = refund_df if isinstance(refund_df, pd.DataFrame) else pd.DataFrame()
    inventory_df = inventory_df if isinstance(inventory_df, pd.DataFrame) else pd.DataFrame()

    context = _build_context(
        title=title,
        user_name=user_name,
        run_name=run_name,
        kpi=kpi or {},
        category_df=category_df,
        segment_df=segment_df,
        customer_df=customer_df,
        ml_df=ml_df,
        refund_df=refund_df,
        inventory_df=inventory_df,
        forecast=forecast,
        selected_sections=selected_sections or {},
    )

    temp_dir = Path(tempfile.mkdtemp(prefix="pet_pdf_"))
    html_path = temp_dir / "report.html"
    pdf_path = temp_dir / "report.pdf"
    payload_path = temp_dir / "payload.json"

    html = template.render(**context)
    html_path.write_text(html, encoding="utf-8")

    payload = {
        "html_path": str(html_path),
        "pdf_path": str(pdf_path),
        "css_path": str((STATIC_DIR / "pdf_report.css").resolve()),
    }
    payload_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    worker_path = Path(__file__).resolve().parent / "pdf_render_worker.py"
    completed = subprocess.run(
        [sys.executable, str(worker_path), str(payload_path)],
        capture_output=True,
        text=True,
        encoding="utf-8",
    )

    if completed.returncode != 0:
        raise RuntimeError(
            "PDF 렌더링 실패\n"
            f"STDOUT:\n{completed.stdout}\n\n"
            f"STDERR:\n{completed.stderr}"
        )

    return pdf_path.read_bytes()
