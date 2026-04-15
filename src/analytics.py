import pandas as pd
import numpy as np
import streamlit as st
from typing import Dict, Any, Optional, List, Tuple

STD_REQUIRED = ["고객ID", "주문번호", "거래일시", "매출"]

REFUND_CANDIDATES = [
    "환불금액",
    "refund",
    "refund_amount",
    "cancel_amount",
    "취소금액",
]


def _safe_to_datetime(s: pd.Series) -> pd.Series:
    return pd.to_datetime(s, errors="coerce")


def _safe_to_numeric(s: pd.Series) -> pd.Series:
    return pd.to_numeric(s, errors="coerce")


def _safe_qcut_score(series, n_bins=5, labels=None, reverse=False):
    s = pd.to_numeric(series, errors="coerce")

    if s.dropna().empty:
        return pd.Series([3] * len(s), index=s.index)

    if s.dropna().nunique() < 2:
        return pd.Series([3] * len(s), index=s.index)

    ranked = s.rank(method="average")

    try:
        cat, bins = pd.qcut(ranked, q=n_bins, retbins=True, duplicates="drop")
        actual_bins = len(bins) - 1

        if labels is None:
            use_labels = list(range(1, actual_bins + 1))
        else:
            use_labels = list(labels)[:actual_bins]

        if reverse:
            use_labels = use_labels[::-1]

        cat = pd.qcut(ranked, q=actual_bins, labels=use_labels, duplicates="drop")
        return cat.astype(int)

    except Exception:
        try:
            actual_bins = min(n_bins, int(s.dropna().nunique()))
            if actual_bins < 2:
                return pd.Series([3] * len(s), index=s.index)

            if labels is None:
                use_labels = list(range(1, actual_bins + 1))
            else:
                use_labels = list(labels)[:actual_bins]

            if reverse:
                use_labels = use_labels[::-1]

            cat = pd.cut(ranked, bins=actual_bins, labels=use_labels, include_lowest=True)
            return cat.astype(int)

        except Exception:
            return pd.Series([3] * len(s), index=s.index)


# ---------------------------------------------------------
# Multi Pet Detection
# ---------------------------------------------------------
def _detect_multi_pet(
    work: pd.DataFrame,
    customer_id_col: str = "고객ID",
    category_col: str = "카테고리",
    product_col: Optional[str] = None,
) -> pd.DataFrame:
    """
    다반려 추정 로직
    - 1차: 상품명/카테고리에서 강아지/고양이 키워드 동시 탐지
    - 2차: 카테고리 다양도 + 구매빈도 기반 다반려 추정
    """
    if customer_id_col not in work.columns:
        return pd.DataFrame(columns=[customer_id_col, "multi_pet", "근거", "카테고리다양도", "구매빈도"])

    tmp = work.copy()

    text_parts = []
    if category_col in tmp.columns:
        text_parts.append(tmp[category_col].astype(str))
    if product_col and product_col in tmp.columns:
        text_parts.append(tmp[product_col].astype(str))

    if text_parts:
        text = text_parts[0].fillna("").astype(str).str.lower()
        for s in text_parts[1:]:
            text = text.str.cat(s.fillna("").astype(str).str.lower(), sep=" ")
    else:
        text = pd.Series([""] * len(tmp), index=tmp.index)

    dog_kw = ["강아지", "강쥐", "dog", "도그", "puppy", "퍼피", "견"]
    cat_kw = ["고양이", "냥", "cat", "캣", "kitten", "키튼", "묘"]

    def has_kw(series: pd.Series, kws: List[str]) -> pd.Series:
        mask = pd.Series(False, index=series.index)
        for kw in kws:
            mask = mask | series.str.contains(kw, na=False)
        return mask

    tmp["_dog"] = has_kw(text, dog_kw).astype(int)
    tmp["_cat"] = has_kw(text, cat_kw).astype(int)

    g = tmp.groupby(customer_id_col)

    freq = g["주문번호"].nunique() if "주문번호" in tmp.columns else g.size()
    cat_div = g[category_col].nunique() if category_col in tmp.columns else g.size()

    dog_any = g["_dog"].max()
    cat_any = g["_cat"].max()

    out = pd.DataFrame({
        customer_id_col: freq.index,
        "구매빈도": freq.values,
        "카테고리다양도": cat_div.values,
        "dog_signal": dog_any.values,
        "cat_signal": cat_any.values,
    })

    out["multi_pet"] = (
        ((out["dog_signal"] > 0) & (out["cat_signal"] > 0)) |
        ((out["카테고리다양도"] >= 3) & (out["구매빈도"] >= 3))
    )

    def reason(r):
        if r["dog_signal"] and r["cat_signal"]:
            return "강아지+고양이 키워드 동시 탐지"
        if r["multi_pet"]:
            return "카테고리 다양도 + 구매빈도 기반 추정"
        return "단일 반려 추정"

    out["근거"] = out.apply(reason, axis=1)

    return out[[customer_id_col, "multi_pet", "근거", "카테고리다양도", "구매빈도"]]


# ---------------------------------------------------------
# Refill Cycle 계산
# ---------------------------------------------------------
def _refill_cycle_by_category(
    work: pd.DataFrame,
    customer_id_col: str = "고객ID",
    date_col: str = "거래일시",
    category_col: str = "카테고리",
    regular_max_cycle: int = 45,
    regular_min_rate: float = 45.0,
    onetime_min_cycle: int = 70,
    onetime_max_rate: float = 20.0,
) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """
    카테고리별 재구매 주기 계산
    + 추천 발송 시점 / 추천 액션 추가
    """
    try:
        if category_col not in work.columns:
            return pd.DataFrame(), pd.DataFrame()

        tmp = work[[customer_id_col, category_col, date_col]].copy()
        tmp[date_col] = pd.to_datetime(tmp[date_col], errors="coerce")
        tmp = tmp.dropna(subset=[date_col])

        if tmp.empty:
            return pd.DataFrame(), pd.DataFrame()

        tmp["_date"] = tmp[date_col].dt.normalize()
        tmp = tmp.drop_duplicates(subset=[customer_id_col, category_col, "_date"])
        tmp = tmp.sort_values([customer_id_col, category_col, "_date"])

        tmp["gap"] = (
            tmp.groupby([customer_id_col, category_col])["_date"]
            .diff()
            .dt.days
        )
        tmp = tmp[tmp["gap"] > 0].copy()

        if tmp.empty:
            return pd.DataFrame(), pd.DataFrame()

        MAX_GAP_DAYS = 180
        tmp = tmp[tmp["gap"] <= MAX_GAP_DAYS].copy()

        if tmp.empty:
            return pd.DataFrame(), pd.DataFrame()

        cust_cycle = (
            tmp.groupby([customer_id_col, category_col])["gap"]
            .median()
            .reset_index()
        )

        cat_stats = (
            cust_cycle.groupby(category_col)["gap"]
            .agg(["median", "mean", "count"])
            .reset_index()
        )
        cat_stats.columns = ["카테고리", "재구매주기", "평균주기", "재구매고객수"]
        cat_stats["재구매주기"] = cat_stats["재구매주기"].round(0).astype(int)
        cat_stats["평균주기"] = cat_stats["평균주기"].round(0).astype(int)

        total_cust_by_cat = (
            work.groupby(category_col)[customer_id_col]
            .nunique()
            .reset_index()
        )
        total_cust_by_cat.columns = ["카테고리", "전체고객수"]

        cat_cycle = cat_stats.merge(total_cust_by_cat, on="카테고리", how="left")
        cat_cycle["전체고객수"] = cat_cycle["전체고객수"].fillna(0).astype(int)
        cat_cycle["재구매율"] = (
            (cat_cycle["재구매고객수"] / cat_cycle["전체고객수"].replace(0, 1) * 100)
            .round(1)
        )

        REGULAR_HINT = [
            "disposable", "패드", "배변", "모래", "litter",
            "위생", "물티슈", "wipe", "간식", "treat", "snack",
            "사료", "food", "feed"
        ]
        ONETIME_HINT = [
            "furniture", "가구", "하우스", "house", "bed", "침대",
            "carrier", "캐리어", "울타리", "fence",
            "electronics", "electronic", "자동급식기", "급수기"
        ]

        def _has_kw(name: str, kws: list) -> bool:
            lo = str(name).lower()
            return any(k in lo for k in kws)

        def group(row):
            cycle = row["재구매주기"]
            rate = row["재구매율"]
            cat = row["카테고리"]

            has_reg = _has_kw(cat, REGULAR_HINT)
            has_one = _has_kw(cat, ONETIME_HINT)

            if rate >= regular_min_rate:
                if cycle <= regular_max_cycle:
                    return "정기구매"
                if cycle <= (regular_max_cycle + 20):
                    return "정기구매"
                if has_reg and cycle <= (regular_max_cycle + 30):
                    return "정기구매"

            if rate < onetime_max_rate:
                return "단발성구매"
            if cycle > onetime_min_cycle:
                return "단발성구매"
            if has_one and cycle > (onetime_min_cycle - 10):
                return "단발성구매"

            return "일반구매"

        def recommend_send_timing(row):
            cycle = int(row["재구매주기"])
            grp = str(row["그룹"])

            if grp == "정기구매":
                return max(cycle - 5, 1)
            if grp == "일반구매":
                return max(cycle - 3, 1)
            return max(cycle - 7, 1)

        def recommend_message(row):
            grp = str(row["그룹"])
            cat = str(row["카테고리"]).lower()

            if any(k in cat for k in ["사료", "food", "feed"]):
                return "사료 리마인드 / 정기구독 제안"
            if any(k in cat for k in ["간식", "treat", "snack"]):
                return "간식 교차판매 / 장바구니 추가 제안"
            if any(k in cat for k in ["패드", "배변", "모래", "litter", "disposable"]):
                return "패드·모래 리마인드 / 묶음상품 제안"
            if any(k in cat for k in ["supplement", "영양제", "health"]):
                return "건강관리 업셀 / 프리미엄 추천"
            if any(k in cat for k in ["grooming", "미용"]):
                return "미용 주기 리마인드 / 재방문 유도"
            if any(k in cat for k in ["cleaning", "위생", "탈취"]):
                return "생활소모품 번들 제안 / 리마인드"
            if any(k in cat for k in ["house", "carrier", "bed", "가구", "하우스", "캐리어"]):
                return "고관여 상품 재검토 / 후기·콘텐츠 강화"
            if any(k in cat for k in ["electronic", "electronics", "자동급식기", "급수기"]):
                return "펫가전 비교 콘텐츠 / 후기 강조"

            if grp == "정기구매":
                return "리마인드 메시지 / 정기구독 제안"
            if grp == "단발성구매":
                return "보완상품 추천 / 재입고 알림"
            return "재구매 유도 쿠폰"

        cat_cycle["그룹"] = cat_cycle.apply(group, axis=1)
        cat_cycle["추천발송시점(일)"] = cat_cycle.apply(recommend_send_timing, axis=1)
        cat_cycle["추천액션"] = cat_cycle.apply(recommend_message, axis=1)
        cat_cycle = cat_cycle.sort_values("재구매주기").reset_index(drop=True)

        cat_group = cat_cycle[["카테고리", "그룹", "재구매주기", "추천발송시점(일)", "추천액션"]].copy()
        return cat_cycle, cat_group

    except Exception:
        return pd.DataFrame(), pd.DataFrame()


# ---------------------------------------------------------
# Category Churn ML
# ---------------------------------------------------------
def compute_category_churn(df: pd.DataFrame) -> pd.DataFrame:
    """
    카테고리별 이탈 예측
    - models/category_churn_lgbm.pkl 있으면 ML 예측
    - 모델이 없거나 실패하면 규칙 기반 fallback
    """
    from pathlib import Path
    import joblib

    MIN_PURCHASES = 3
    MAX_CYCLE_DAYS = 90
    CAT_COL = "카테고리"
    DATE_COL = "거래일시"
    CUST_COL = "고객ID"
    SALES_COL = "매출"

    FEATURE_COLS = [
        "purchase_count", "avg_cycle", "cycle_std",
        "active_months", "freq_per_month", "total_revenue",
        "avg_revenue", "revenue_per_month", "cat_ratio",
        "freq_trend", "cust_cat_count", "days_to_snapshot",
    ]

    if CAT_COL not in df.columns or DATE_COL not in df.columns:
        return pd.DataFrame()

    df = df.copy()
    df[DATE_COL] = pd.to_datetime(df[DATE_COL], errors="coerce")
    df[SALES_COL] = pd.to_numeric(df[SALES_COL], errors="coerce")
    df = df.dropna(subset=[CUST_COL, DATE_COL, CAT_COL, SALES_COL])
    df = df[df[SALES_COL] > 0]

    if df.empty:
        return pd.DataFrame()

    snapshot_date = df[DATE_COL].max()

    BASE_DIR = Path(__file__).resolve().parent.parent
    MODEL_PATH = BASE_DIR / "models" / "category_churn_lgbm.pkl"
    FEATURE_PATH = BASE_DIR / "models" / "category_churn_feature_cols.pkl"
    RULE_CAT_PATH = BASE_DIR / "models" / "category_churn_rule_cats.pkl"

    cat_models = {}
    feature_cols = FEATURE_COLS
    rule_cats = []

    if MODEL_PATH.exists() and FEATURE_PATH.exists():
        try:
            cat_models = joblib.load(MODEL_PATH)
            feature_cols = joblib.load(FEATURE_PATH)
        except Exception:
            cat_models = {}

    if RULE_CAT_PATH.exists():
        try:
            rule_cats = joblib.load(RULE_CAT_PATH)
        except Exception:
            rule_cats = []

    records = []
    for (cust_id, category), grp in df.groupby([CUST_COL, CAT_COL]):
        dates = grp[DATE_COL].drop_duplicates().sort_values()
        purchase_count = len(dates)
        if purchase_count < MIN_PURCHASES:
            continue

        gaps = dates.diff().dt.days.dropna()
        if gaps.empty:
            continue

        avg_cycle = gaps.mean()
        cycle_std = gaps.std() if len(gaps) > 1 else 0.0
        if avg_cycle > MAX_CYCLE_DAYS or avg_cycle <= 0:
            continue

        last_purchase = dates.max()
        first_purchase = dates.min()
        days_since = (snapshot_date - last_purchase).days
        active_months = max((snapshot_date - first_purchase).days / 30.0, 1)
        recency_ratio = days_since / avg_cycle if avg_cycle > 0 else 0.0
        total_revenue = grp[SALES_COL].sum()
        avg_revenue = grp[SALES_COL].mean()
        revenue_per_month = total_revenue / active_months
        freq_per_month = purchase_count / active_months
        cust_total = df[df[CUST_COL] == cust_id][SALES_COL].sum()
        cat_ratio = total_revenue / cust_total if cust_total > 0 else 0.0

        half = active_months / 2
        recent_grp = grp[grp[DATE_COL] > (last_purchase - pd.Timedelta(days=half * 30))]
        early_grp = grp[grp[DATE_COL] <= (last_purchase - pd.Timedelta(days=half * 30))]
        freq_trend = (len(recent_grp) / max(half, 1)) - (len(early_grp) / max(half, 1))

        cust_cat_count = df[df[CUST_COL] == cust_id][CAT_COL].nunique()
        days_to_snapshot = (snapshot_date - last_purchase).days

        records.append({
            CUST_COL: cust_id,
            CAT_COL: category,
            "purchase_count": purchase_count,
            "avg_cycle": round(avg_cycle, 2),
            "cycle_std": round(cycle_std, 2),
            "days_since": days_since,
            "recency_ratio": round(recency_ratio, 4),
            "active_months": round(active_months, 2),
            "freq_per_month": round(freq_per_month, 4),
            "total_revenue": int(total_revenue),
            "avg_revenue": round(avg_revenue, 2),
            "revenue_per_month": round(revenue_per_month, 2),
            "cat_ratio": round(cat_ratio, 4),
            "freq_trend": round(freq_trend, 4),
            "cust_cat_count": cust_cat_count,
            "days_to_snapshot": days_to_snapshot,
            "마지막구매일": last_purchase.date(),
        })

    if not records:
        return pd.DataFrame()

    feat_df = pd.DataFrame(records)

    churn_probs = []
    methods = []

    for _, row in feat_df.iterrows():
        cat = row[CAT_COL]
        if cat in cat_models and cat not in rule_cats:
            try:
                X = pd.DataFrame([row[feature_cols]])
                prob = cat_models[cat].predict_proba(X)[0][1]
                churn_probs.append(round(float(prob), 4))
                methods.append("ML")
            except Exception:
                prob = min(row["recency_ratio"] / 3.0, 1.0)
                churn_probs.append(round(prob, 4))
                methods.append("규칙기반")
        else:
            prob = min(row["recency_ratio"] / 3.0, 1.0)
            churn_probs.append(round(prob, 4))
            methods.append("규칙기반")

    feat_df["이탈확률"] = churn_probs
    feat_df["예측방식"] = methods

    def classify_risk(prob):
        if prob >= 0.7:
            return "휴면"
        elif prob >= 0.4:
            return "위험"
        return "정상"

    feat_df["위험도"] = feat_df["이탈확률"].apply(classify_risk)

    def recommend(row):
        cat = str(row[CAT_COL]).lower()

        if any(k in cat for k in ["사료", "food", "feed"]):
            if row["위험도"] == "휴면":
                return "사료 체험팩/정기구독 할인 + 리마인드"
            if row["위험도"] == "위험":
                return "사료 재구매 쿠폰 + 리마인드"
            return "-"

        if any(k in cat for k in ["간식", "treat", "snack"]):
            if row["위험도"] == "휴면":
                return "간식 재방문 쿠폰 + 교차판매"
            if row["위험도"] == "위험":
                return "간식 장바구니 추천"
            return "-"

        if any(k in cat for k in ["모래", "litter", "패드", "배변", "disposable"]):
            if row["위험도"] == "휴면":
                return "소모품 번들 제안 + 강한 재구매 알림"
            if row["위험도"] == "위험":
                return "소모품 재구매 알림 + 쿠폰"
            return "-"

        if any(k in cat for k in ["supplement", "영양제", "health"]):
            if row["위험도"] == "휴면":
                return "건강관리 카테고리 재활성화 쿠폰"
            if row["위험도"] == "위험":
                return "영양제/건강관리 업셀 제안"
            return "-"

        if row["위험도"] == "휴면":
            return f"{row[CAT_COL]} 강한 재구매 쿠폰 + 리마인드"
        elif row["위험도"] == "위험":
            return f"{row[CAT_COL]} 재구매 유도 쿠폰"
        return "-"

    feat_df["추천액션"] = feat_df.apply(recommend, axis=1)

    order = {"휴면": 0, "위험": 1, "정상": 2}
    feat_df["_sort"] = feat_df["위험도"].map(order)
    feat_df = feat_df.sort_values(["_sort", "이탈확률"], ascending=[True, False]).drop(columns=["_sort"])

    return feat_df[[
        CUST_COL, CAT_COL,
        "purchase_count", "avg_cycle", "마지막구매일",
        "days_since", "이탈확률", "위험도", "예측방식", "추천액션",
        "total_revenue",
    ]].rename(columns={
        "purchase_count": "구매횟수",
        "avg_cycle": "평균구매주기(일)",
        "days_since": "경과일",
        "total_revenue": "누적매출",
    })


# ---------------------------------------------------------
# Optional ML scoring
# ---------------------------------------------------------
def _load_churn_scored(work: pd.DataFrame) -> pd.DataFrame:
    try:
        from .churn_model import score_customers
        scored = score_customers(work.copy())
        if isinstance(scored, pd.DataFrame):
            return scored
        return pd.DataFrame()
    except Exception as e:
        st.error(f"ML 모델 로드 오류: {e}")
        return pd.DataFrame()


# ---------------------------------------------------------
# Main: RFM + Risk + Pet Insights
# ---------------------------------------------------------
@st.cache_data(show_spinner="분석 중...")
def compute_rfm_and_risk(df: pd.DataFrame) -> Dict[str, Any]:
    work = df.copy()

    for col in STD_REQUIRED:
        if col not in work.columns:
            raise ValueError(f"필수 컬럼 누락: {col}")

    work["거래일시"] = pd.to_datetime(work["거래일시"], errors="coerce")
    work = work.dropna(subset=["거래일시"]).copy()

    work["매출"] = (
        work["매출"]
        .astype(str)
        .str.strip()
        .str.replace(",", "", regex=False)
        .str.replace("₩", "", regex=False)
        .str.replace("원", "", regex=False)
        .str.replace("−", "-", regex=False)
        .str.replace(r"\((.*?)\)", r"-\1", regex=True)
        .str.replace(r"[^0-9\.-]", "", regex=True)
        .pipe(pd.to_numeric, errors="coerce")
        .fillna(0)
    )

    snapshot = work["거래일시"].max() + pd.Timedelta(days=1)

    refund_col = None
    for c in REFUND_CANDIDATES:
        if c in work.columns:
            refund_col = c
            break

    refund_rate = 0.0
    refund_customers = pd.DataFrame()
    refund_category = pd.DataFrame()

    if refund_col:
        work[refund_col] = pd.to_numeric(work[refund_col], errors="coerce").fillna(0)
        work["is_refund"] = work[refund_col] != 0
        work["refund_amount_calc"] = work[refund_col].abs()
    else:
        work["is_refund"] = work["매출"] < 0
        work["refund_amount_calc"] = work["매출"].where(work["매출"] < 0, 0).abs()

    total_orders = work["주문번호"].nunique()
    refund_orders = work.loc[work["is_refund"], "주문번호"].drop_duplicates().nunique()

    if total_orders > 0:
        refund_rate = refund_orders / total_orders

    refund_customers = (
        work.groupby("고객ID")
        .agg(
            주문수=("주문번호", "nunique"),
            환불수=("is_refund", "sum"),
            환불금액=("refund_amount_calc", "sum"),
        )
        .reset_index()
    )

    refund_customers["환불비율"] = (
        refund_customers["환불수"] / refund_customers["주문수"].replace(0, 1)
    )

    refund_customers = refund_customers[
        refund_customers["환불수"] > 0
    ].sort_values(["환불비율", "환불금액"], ascending=False)

    if "카테고리" in work.columns:
        refund_category = (
            work.groupby("카테고리")
            .agg(
                주문수=("주문번호", "nunique"),
                환불수=("is_refund", "sum"),
                환불금액=("refund_amount_calc", "sum"),
            )
            .reset_index()
        )

        refund_category["환불률"] = (
            refund_category["환불수"] / refund_category["주문수"].replace(0, 1)
        )

        refund_category = refund_category[
            refund_category["환불수"] > 0
        ].sort_values("환불률", ascending=False)

    rfm = (
        work.groupby("고객ID")
        .agg(
            Recency=("거래일시", lambda x: (snapshot - x.max()).days),
            Frequency=("주문번호", "nunique"),
            Monetary=("매출", "sum"),
        )
        .reset_index()
    )

    rfm["R"] = _safe_qcut_score(rfm["Recency"], 5, [5, 4, 3, 2, 1])
    rfm["F"] = _safe_qcut_score(rfm["Frequency"], 5, [1, 2, 3, 4, 5])
    rfm["M"] = _safe_qcut_score(rfm["Monetary"], 5, [1, 2, 3, 4, 5])
    rfm["RFM"] = rfm["R"] + rfm["F"] + rfm["M"]

    segment_cut = {
        "monetary_q80": rfm["Monetary"].quantile(0.8),
        "monetary_q60": rfm["Monetary"].quantile(0.6),
        "frequency_q80": rfm["Frequency"].quantile(0.8),
        "frequency_q60": rfm["Frequency"].quantile(0.6),
        "frequency_q50": rfm["Frequency"].quantile(0.5),
        "recency_q20": rfm["Recency"].quantile(0.2),
        "recency_q60": rfm["Recency"].quantile(0.6),
        "recency_q80": rfm["Recency"].quantile(0.8),
    }

    def segment(row):
        r = row["Recency"]
        f = row["Frequency"]
        m = row["Monetary"]

        if m >= segment_cut["monetary_q80"] and f >= segment_cut["frequency_q80"] and r <= segment_cut["recency_q20"]:
            return "VVIP"
        elif m >= segment_cut["monetary_q60"] and f >= segment_cut["frequency_q60"]:
            return "VIP"
        elif m >= segment_cut["monetary_q60"] and r > segment_cut["recency_q60"]:
            return "고가치 감소형"
        elif r > segment_cut["recency_q80"]:
            return "휴면형"
        elif f >= segment_cut["frequency_q50"]:
            return "활발한 일반 고객"
        else:
            return "관심필요 고객"

    rfm["세그먼트"] = rfm.apply(segment, axis=1)

    rec_n = (rfm["Recency"] - rfm["Recency"].min()) / (rfm["Recency"].max() - rfm["Recency"].min() + 1e-9)
    fre_n = (rfm["Frequency"] - rfm["Frequency"].min()) / (rfm["Frequency"].max() - rfm["Frequency"].min() + 1e-9)
    mon_n = (rfm["Monetary"] - rfm["Monetary"].min()) / (rfm["Monetary"].max() - rfm["Monetary"].min() + 1e-9)

    risk = (0.45 * rec_n + 0.30 * (1 - fre_n) + 0.25 * (1 - mon_n)) * 100
    rfm["위험도점수"] = risk.round().astype(int)

    def risk_label(x):
        if x >= 70:
            return "High"
        if x >= 40:
            return "Medium"
        return "Low"

    rfm["위험도"] = rfm["위험도점수"].apply(risk_label)

    high_ratio = (rfm["위험도"] == "High").mean() * 100 if len(rfm) else 0
    avg_risk = rfm["위험도점수"].mean() if len(rfm) else 0
    total_customers = rfm["고객ID"].nunique()
    expected_loss = int(
        rfm["Monetary"].mean() * (rfm["위험도"] == "High").sum() * 0.4
    ) if len(rfm) else 0

    seg_summary = (
        rfm.groupby("세그먼트")
        .agg(
            인원=("고객ID", "count"),
            평균주문=("Frequency", "mean"),
            평균금액=("Monetary", "mean"),
            평균위험=("위험도점수", "mean"),
        )
        .reset_index()
    )

    cust_list = rfm.sort_values(["위험도점수", "Monetary"], ascending=False).head(15).copy()
    cust_list = cust_list.rename(columns={"Monetary": "주문금액"})

    if "카테고리" in work.columns:
        tmp_merge = work.groupby(["고객ID", "카테고리"])["매출"].sum().reset_index()
        tmp_merge = tmp_merge.merge(rfm[["고객ID", "위험도점수"]], on="고객ID", how="left")
        category_risk = (
            tmp_merge.groupby("카테고리")
            .agg(
                고객수=("고객ID", "nunique"),
                위험=("위험도점수", "mean"),
            )
            .reset_index()
        )
        category_risk["위험"] = category_risk["위험"].round().astype(int)
    else:
        category_risk = pd.DataFrame(columns=["카테고리", "고객수", "위험"])

    if "카테고리" in work.columns and "거래일시" in work.columns:
        inventory_src = work.copy()
        inventory_src["거래일시"] = pd.to_datetime(inventory_src["거래일시"], errors="coerce")
        inventory_src["매출"] = pd.to_numeric(inventory_src["매출"], errors="coerce")
        inventory_src = inventory_src.dropna(subset=["거래일시", "카테고리"])
        inventory_src = inventory_src[inventory_src["매출"].fillna(0) > 0].copy()

        def _inventory_pet_label(value: str) -> str:
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
            ]
            for keywords, label in mapping:
                if any(k in s for k in keywords):
                    return label
            return str(value)

        def _inventory_action(label: str, priority: str) -> str:
            if priority == "최우선 확보":
                if "배변" in label or "사료" in label:
                    return "반복소비 핵심 카테고리 · 즉시 발주 및 품절 모니터링"
                return "핵심 수요 카테고리 · 안전재고 우선 확보"
            if priority == "집중 관리":
                return "주간 판매 추이를 보며 추가 발주 여부 점검"
            return "기본 재고 유지 · 프로모션/교차판매와 병행 운영"

        rows = []
        if not inventory_src.empty:
            latest_snapshot = inventory_src["거래일시"].max().normalize()
            recent_start = latest_snapshot - pd.Timedelta(days=89)
            recent_all = inventory_src[inventory_src["거래일시"] >= recent_start].copy()
            if recent_all.empty:
                recent_all = inventory_src.copy()

            recent_days = max(int((recent_all["거래일시"].max().normalize() - recent_all["거래일시"].min().normalize()).days) + 1, 1)
            total_recent_revenue = float(pd.to_numeric(recent_all["매출"], errors="coerce").fillna(0).sum())
            avg_daily_revenue = total_recent_revenue / recent_days if recent_days else 0.0

            for cat, g in recent_all.groupby("카테고리"):
                g = g.sort_values("거래일시").copy()
                if g.empty:
                    continue

                start_date = g["거래일시"].min().normalize()
                end_date = g["거래일시"].max().normalize()
                active_days = max((end_date - start_date).days + 1, 1)
                order_count = int(g["주문번호"].nunique()) if "주문번호" in g.columns else int(len(g))
                daily_order_rate = order_count / active_days
                expected_monthly_orders = daily_order_rate * 30
                buffer_days = 7
                recommended_cover_days = 30 + buffer_days
                safety_stock = daily_order_rate * recommended_cover_days
                revenue = float(pd.to_numeric(g["매출"], errors="coerce").fillna(0).sum())

                rows.append({
                    "카테고리": cat,
                    "펫카테고리": _inventory_pet_label(cat),
                    "최근분석기간(일)": active_days,
                    "최근매출": int(round(revenue)),
                    "예상판매량": round(expected_monthly_orders, 1),
                    "일평균판매량": round(daily_order_rate, 2),
                    "권장보유일수": recommended_cover_days,
                    "안전재고량": int(round(safety_stock)),
                })

            inventory = pd.DataFrame(rows)
            if not inventory.empty:
                q_high = float(inventory["안전재고량"].quantile(0.67))
                q_mid = float(inventory["안전재고량"].quantile(0.34))

                def _priority(v: float) -> str:
                    if v >= q_high:
                        return "최우선 확보"
                    if v >= q_mid:
                        return "집중 관리"
                    return "기본 운영"

                inventory["우선순위"] = inventory["안전재고량"].apply(_priority)
                inventory["추천액션"] = inventory.apply(
                    lambda r: _inventory_action(str(r.get("펫카테고리", r.get("카테고리", "-"))), str(r.get("우선순위", "기본 운영"))),
                    axis=1,
                )
                inventory = inventory.sort_values(["안전재고량", "예상판매량"], ascending=[False, False]).reset_index(drop=True)
            else:
                inventory = pd.DataFrame(columns=["카테고리", "펫카테고리", "예상판매량", "안전재고량", "우선순위", "추천액션"])

            forecast = {
                "label": "다음달 예상 매출",
                "value": int(round(avg_daily_revenue * 30)),
                "basis_days": recent_days,
                "avg_daily_revenue": float(round(avg_daily_revenue, 1)),
                "logic": "최근 90일 일평균 매출을 30일 기준으로 환산한 간이 예측값",
            }
        else:
            inventory = pd.DataFrame(columns=["카테고리", "펫카테고리", "예상판매량", "안전재고량", "우선순위", "추천액션"])
            forecast = {
                "label": "다음달 예상 매출",
                "value": 0,
                "basis_days": 0,
                "avg_daily_revenue": 0.0,
                "logic": "데이터 부족으로 예측값을 계산하지 못했습니다.",
            }
    else:
        inventory = pd.DataFrame(columns=["카테고리", "펫카테고리", "예상판매량", "안전재고량", "우선순위", "추천액션"])
        forecast = {
            "label": "다음달 예상 매출",
            "value": 0,
            "basis_days": 0,
            "avg_daily_revenue": 0.0,
            "logic": "카테고리 또는 거래일시 컬럼이 없어 예측값을 계산하지 못했습니다.",
        }

    cat_cycle, cat_group = _refill_cycle_by_category(work)
    product_col = "상품명" if "상품명" in work.columns else None
    multi_pet = _detect_multi_pet(work, product_col=product_col)

    multi_pet_cnt = int(multi_pet["multi_pet"].sum()) if not multi_pet.empty else 0
    pet_insights = {
        "multi_pet_cnt": multi_pet_cnt,
        "multi_pet_ratio": float(multi_pet_cnt / total_customers * 100) if total_customers else 0,
    }

    churn_scored = _load_churn_scored(work)
    churn_summary = {
        "avg_churn_prob": float(churn_scored["churn_prob"].mean()) if len(churn_scored) and "churn_prob" in churn_scored.columns else 0.0,
        "high_risk_count": int((churn_scored["churn_prob"] >= 0.8).sum()) if len(churn_scored) and "churn_prob" in churn_scored.columns else 0,
        "rule_dormant_count": int((churn_scored["rule_risk"] == "휴면").sum()) if len(churn_scored) and "rule_risk" in churn_scored.columns else 0,
        "rule_risk_count": int((churn_scored["rule_risk"] == "위험").sum()) if len(churn_scored) and "rule_risk" in churn_scored.columns else 0,
    }

    category_churn_df = compute_category_churn(work)

    return {
        "df_work": work,
        "rfm": rfm,
        "kpi": {
            "high_ratio": high_ratio,
            "avg_risk": avg_risk,
            "total_customers": total_customers,
            "expected_loss": expected_loss,
            "refund_rate": refund_rate,
        },
        "category_risk": category_risk,
        "customer_list": cust_list,
        "segment_summary": seg_summary,
        "forecast": forecast,
        "inventory": inventory,
        "refill_cycle_by_category": cat_cycle,
        "refill_category_group": cat_group,
        "multi_pet_customers": multi_pet,
        "pet_insights": pet_insights,
        "refund": {
            "refund_rate": refund_rate,
            "refund_customers": refund_customers.head(30),
            "refund_category": refund_category,
        },
        "churn_scored": churn_scored,
        "churn_summary": churn_summary,
        "category_churn": category_churn_df,
    }