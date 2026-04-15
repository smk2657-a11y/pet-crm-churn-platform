import re
import math
import warnings
from typing import Dict, List, Tuple, Optional

import joblib
import numpy as np
import pandas as pd

from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.linear_model import LogisticRegression
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import (
    roc_auc_score,
    average_precision_score,
    f1_score,
    precision_score,
    recall_score,
)

warnings.filterwarnings("ignore")

# =========================================================
# 경로
# =========================================================

from .paths import MODEL_DIR

MODEL_DIR.mkdir(exist_ok=True)

# 고객 전체 이탈 모델
CUSTOMER_MODEL_PATH_3_6 = MODEL_DIR / "customer_churn_rf_3_6.pkl"
CUSTOMER_FEATURE_PATH_3_6 = MODEL_DIR / "customer_churn_feature_cols_3_6.pkl"
CUSTOMER_THRESHOLD_PATH_3_6 = MODEL_DIR / "customer_churn_threshold_3_6.pkl"
CUSTOMER_MODEL_NAME_PATH_3_6 = MODEL_DIR / "customer_churn_model_name_3_6.pkl"

CUSTOMER_MODEL_PATH_6_12 = MODEL_DIR / "customer_churn_lgbm_6_12.pkl"
CUSTOMER_FEATURE_PATH_6_12 = MODEL_DIR / "customer_churn_feature_cols_6_12.pkl"
CUSTOMER_THRESHOLD_PATH_6_12 = MODEL_DIR / "customer_churn_threshold_6_12.pkl"
CUSTOMER_MODEL_NAME_PATH_6_12 = MODEL_DIR / "customer_churn_model_name_6_12.pkl"

# 카테고리 이탈 모델
CATEGORY_MODEL_PATH = MODEL_DIR / "category_churn_lgbm.pkl"
CATEGORY_FEATURE_PATH = MODEL_DIR / "category_churn_feature_cols.pkl"
CATEGORY_THRESHOLD_PATH = MODEL_DIR / "category_churn_threshold.pkl"
CATEGORY_RULE_CATS_PATH = MODEL_DIR / "category_churn_rule_cats.pkl"


# =========================================================
# 공통 유틸
# =========================================================

def _normalize_col(s: str) -> str:
    s = str(s).strip()
    s = s.replace("\n", " ").replace("\t", " ")
    s = re.sub(r"\s+", "", s)
    return s.lower()


def _safe_div(a, b):
    if isinstance(b, pd.Series):
        b = b.replace(0, np.nan)
    else:
        b = np.where(np.abs(b) < 1e-9, np.nan, b)
    return a / b


def _exp_decay_weight(days_from_snapshot: pd.Series, half_life: float = 30.0) -> pd.Series:
    days_from_snapshot = pd.to_numeric(days_from_snapshot, errors="coerce").fillna(0)
    return np.exp(-np.log(2) * days_from_snapshot / max(half_life, 1.0))


def estimate_data_months(df: pd.DataFrame) -> float:
    if df.empty:
        return 0.0
    return max(0.0, (df["거래일시"].max() - df["거래일시"].min()).days / 30.0)


def get_router_key_by_data_months(data_months: float) -> str:
    if data_months < 3:
        return "not_enough_data"
    if data_months < 6:
        return "model_3_6"
    return "model_6_12"


def get_data_reliability(data_months: float) -> str:
    if data_months < 4:
        return "low"
    if data_months < 7:
        return "medium"
    return "high"


def assign_history_segment(history_days: int) -> str:
    if history_days < 90:
        return "cold"
    if history_days < 180:
        return "m3_6"
    if history_days <= 365:
        return "m6_12"
    return "other"


def add_segment_column(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out["history_segment"] = out["history_days"].apply(assign_history_segment)
    return out


def precision_at_top_k(y_true: pd.Series, prob: np.ndarray, k_ratio: float = 0.1) -> float:
    y_true = np.array(y_true)
    prob = np.array(prob)
    n = len(y_true)
    if n == 0:
        return np.nan
    k = max(1, int(math.ceil(n * k_ratio)))
    idx = np.argsort(-prob)[:k]
    return y_true[idx].mean()


def build_metrics_frame(
    y_true: pd.Series,
    prob: np.ndarray,
    threshold: float = 0.5,
    pred: Optional[np.ndarray] = None,
) -> Dict[str, float]:
    y_true = np.array(y_true).astype(int)
    prob = np.array(prob)

    if pred is None:
        pred = (prob >= threshold).astype(int)
    else:
        pred = np.array(pred).astype(int)

    metrics = {
        "roc_auc": np.nan,
        "pr_auc": np.nan,
        "f1": np.nan,
        "precision": np.nan,
        "recall": np.nan,
        "precision_at_10pct": precision_at_top_k(y_true, prob, 0.10),
        "precision_at_20pct": precision_at_top_k(y_true, prob, 0.20),
        "churn_rate": float(np.mean(y_true)) if len(y_true) > 0 else np.nan,
        "threshold": float(threshold),
        "n": int(len(y_true)),
    }

    if len(np.unique(y_true)) >= 2:
        metrics["roc_auc"] = roc_auc_score(y_true, prob)
        metrics["pr_auc"] = average_precision_score(y_true, prob)

    metrics["f1"] = f1_score(y_true, pred, zero_division=0)
    metrics["precision"] = precision_score(y_true, pred, zero_division=0)
    metrics["recall"] = recall_score(y_true, pred, zero_division=0)
    return metrics


def pick_threshold_on_validation(
    y_true: pd.Series,
    prob: np.ndarray,
    precision_floor: Optional[float] = None,
) -> Tuple[float, pd.DataFrame]:
    rows = []
    for th in np.arange(0.05, 0.96, 0.01):
        pred = (prob >= th).astype(int)
        p = precision_score(y_true, pred, zero_division=0)
        r = recall_score(y_true, pred, zero_division=0)
        f1 = f1_score(y_true, pred, zero_division=0)
        rows.append([th, p, r, f1])

    th_df = pd.DataFrame(rows, columns=["threshold", "precision", "recall", "f1"])

    if precision_floor is not None:
        cand = th_df[th_df["precision"] >= precision_floor].copy()
        if len(cand) > 0:
            best = cand.sort_values(["f1", "precision"], ascending=False).iloc[0]
            return float(best["threshold"]), th_df

    best = th_df.sort_values(["f1", "precision"], ascending=False).iloc[0]
    return float(best["threshold"]), th_df


def _fill_numeric_na(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    num_cols = out.select_dtypes(include=[np.number]).columns.tolist()
    out[num_cols] = out[num_cols].replace([np.inf, -np.inf], np.nan)
    for c in num_cols:
        out[c] = 0 if out[c].isna().all() else out[c].fillna(out[c].median())
    return out


# =========================================================
# 전처리
# =========================================================

def preprocess_pet_data(
    df: pd.DataFrame,
    column_mapping: Optional[Dict[str, str]] = None,
) -> pd.DataFrame:
    df = df.copy()
    raw_cols = list(df.columns)

    if column_mapping:
        rename_map = {
            original_col: std_col
            for std_col, original_col in column_mapping.items()
            if original_col in df.columns
        }
        df = df.rename(columns=rename_map)

    alias_map = {
        "고객ID": [
            "고객id", "고객번호", "회원id", "회원번호", "customerid", "customer_id",
            "custid", "cust_id", "userid", "user_id", "buyerid", "buyer_id", "clientid"
        ],
        "주문번호": [
            "주문번호", "주문id", "주문코드", "구매번호", "orderid", "order_id",
            "invoice", "invoiceno", "transactionid", "transaction_id", "purchaseid",
            "거래id", "거래번호"
        ],
        "거래일시": [
            "거래일시", "주문일시", "구매일시", "결제일시", "주문일", "거래일", "구매일",
            "date", "datetime", "orderdate", "order_date", "purchasedate", "purchase_date",
            "transactiondate", "transaction_date", "invoicedate",
            "거래날짜", "주문날짜", "구매날짜"
        ],
        "매출": [
            "매출", "실결제금액", "결제금액", "주문금액", "구매금액", "판매금액",
            "sales", "amount", "revenue", "totalprice", "total_price", "grosssales"
        ],
        "단가": [
            "단가", "상품단가", "판매단가", "price", "unitprice", "unit_price",
            "평균금액", "금액", "평균구매금액"
        ],
        "카테고리": [
            "카테고리", "상품카테고리", "대분류", "중분류", "소분류",
            "category", "productcategory", "product_category", "제품카테고리"
        ],
        "상품명": [
            "상품명", "제품명", "품목명", "브랜드상품명", "itemname", "item_name",
            "product", "productname", "product_name", "제품id", "제품코드", "productid", "product_id"
        ],
        "수량": [
            "수량", "구매수량", "주문수량", "qty", "quantity", "orderqty"
        ],
    }

    normalized_to_original = {_normalize_col(c): c for c in raw_cols}
    rename_map = {}

    for std_col, aliases in alias_map.items():
        if std_col in df.columns:
            continue
        for alias in aliases:
            key = _normalize_col(alias)
            if key in normalized_to_original:
                rename_map[normalized_to_original[key]] = std_col
                break

    df = df.rename(columns=rename_map)

    required_base = ["고객ID", "주문번호", "거래일시"]
    missing_base = [c for c in required_base if c not in df.columns]
    if missing_base:
        raise ValueError(f"필수 컬럼이 부족합니다: {missing_base}")

    if "카테고리" not in df.columns:
        df["카테고리"] = "UNKNOWN"
    if "상품명" not in df.columns:
        df["상품명"] = "UNKNOWN"
    if "수량" not in df.columns:
        df["수량"] = 1

    df["고객ID"] = df["고객ID"].astype(str).str.strip()
    df["주문번호"] = df["주문번호"].astype(str).str.strip()
    df["거래일시"] = pd.to_datetime(df["거래일시"], errors="coerce")
    df["수량"] = pd.to_numeric(df["수량"], errors="coerce").fillna(1)

    if "단가" in df.columns:
        df["단가"] = pd.to_numeric(df["단가"], errors="coerce")
    if "매출" in df.columns:
        df["매출"] = pd.to_numeric(df["매출"], errors="coerce")

    if "매출" not in df.columns:
        if "단가" in df.columns:
            df["매출"] = df["단가"] * df["수량"]
        else:
            raise ValueError("필수 컬럼 부족: ['매출'] 또는 ['단가'] 필요")
    else:
        if "단가" in df.columns:
            missing_sales_mask = df["매출"].isna()
            df.loc[missing_sales_mask, "매출"] = (
                df.loc[missing_sales_mask, "단가"] * df.loc[missing_sales_mask, "수량"]
            )

    df["카테고리"] = df["카테고리"].astype(str).fillna("UNKNOWN").replace("", "UNKNOWN")
    df["상품명"] = df["상품명"].astype(str).fillna("UNKNOWN").replace("", "UNKNOWN")

    df = df.dropna(subset=["고객ID", "주문번호", "거래일시", "매출"]).copy()
    df = df[df["수량"] > 0].copy()
    df = df[df["매출"] >= 0].copy()

    subset_cols = ["고객ID", "주문번호", "거래일시", "매출", "상품명", "카테고리"]
    subset_cols = [c for c in subset_cols if c in df.columns]
    df = df.drop_duplicates(subset=subset_cols, keep="first").copy()

    return df.sort_values(["거래일시", "고객ID", "주문번호"]).reset_index(drop=True)


# =========================================================
# 고객 전체 이탈용 피처
# =========================================================

def build_customer_features_generalized(
    df: pd.DataFrame,
    snapshot_date: pd.Timestamp,
    lookback_windows: Tuple[int, ...] = (14, 30, 60, 90, 180),
) -> pd.DataFrame:
    hist = df[df["거래일시"] <= snapshot_date].copy()
    if hist.empty:
        return pd.DataFrame()

    g = hist.groupby("고객ID")
    first_order = g["거래일시"].min()
    last_order = g["거래일시"].max()
    order_count = g["주문번호"].nunique()
    sales_sum = g["매출"].sum()
    qty_sum = g["수량"].sum()

    out = pd.DataFrame({
        "고객ID": first_order.index,
        "snapshot_date": snapshot_date,
        "first_order_date": first_order.values,
        "last_order_date": last_order.values,
        "history_days": (snapshot_date - first_order).dt.days.values,
        "recency_days": (snapshot_date - last_order).dt.days.values,
        "lifetime_order_count": order_count.values,
        "lifetime_sales": sales_sum.values,
        "lifetime_qty": qty_sum.values,
    })

    out["avg_order_value"] = _safe_div(out["lifetime_sales"], out["lifetime_order_count"])
    out["orders_per_30d"] = _safe_div(out["lifetime_order_count"], np.maximum(out["history_days"], 1)) * 30
    out["sales_per_30d"] = _safe_div(out["lifetime_sales"], np.maximum(out["history_days"], 1)) * 30

    ord_day = (
        hist[["고객ID", "주문번호", "거래일시"]]
        .drop_duplicates()
        .sort_values(["고객ID", "거래일시"])
        .copy()
    )
    ord_day["prev_order_date"] = ord_day.groupby("고객ID")["거래일시"].shift(1)
    ord_day["gap_days"] = (ord_day["거래일시"] - ord_day["prev_order_date"]).dt.days

    gap_stats = ord_day.groupby("고객ID")["gap_days"].agg(
        avg_gap_days="mean",
        std_gap_days="std",
        min_gap_days="min",
        max_gap_days="max",
        last_gap_days="last"
    ).reset_index()

    out = out.merge(gap_stats, on="고객ID", how="left")

    for w in lookback_windows:
        st = snapshot_date - pd.Timedelta(days=w)
        sub = hist[hist["거래일시"] > st].copy()

        if sub.empty:
            temp = pd.DataFrame({"고객ID": out["고객ID"].copy()})
        else:
            sg = sub.groupby("고객ID")
            temp = pd.DataFrame({
                "고객ID": sg["주문번호"].nunique().index,
                f"order_count_{w}d": sg["주문번호"].nunique().values,
                f"sales_sum_{w}d": sg["매출"].sum().values,
                f"category_nunique_{w}d": sg["카테고리"].nunique().values,
            })

            order_seq = (
                sub[["고객ID", "주문번호", "거래일시"]]
                .drop_duplicates()
                .sort_values(["고객ID", "거래일시"])
                .copy()
            )
            order_seq["prev_order_date"] = order_seq.groupby("고객ID")["거래일시"].shift(1)
            order_seq["gap_days"] = (order_seq["거래일시"] - order_seq["prev_order_date"]).dt.days

            gap_w = order_seq.groupby("고객ID")["gap_days"].agg(
                **{f"avg_gap_{w}d": "mean", f"last_gap_{w}d": "last"}
            ).reset_index()

            temp = temp.merge(gap_w, on="고객ID", how="left")

        out = out.merge(temp, on="고객ID", how="left")

    prev30_start = snapshot_date - pd.Timedelta(days=60)
    prev30_end = snapshot_date - pd.Timedelta(days=30)
    prev30 = hist[(hist["거래일시"] > prev30_start) & (hist["거래일시"] <= prev30_end)].copy()

    if prev30.empty:
        prev30_feat = pd.DataFrame({"고객ID": out["고객ID"].copy()})
    else:
        pg = prev30.groupby("고객ID")
        prev30_feat = pd.DataFrame({
            "고객ID": pg["주문번호"].nunique().index,
            "order_count_prev30d": pg["주문번호"].nunique().values,
            "sales_sum_prev30d": pg["매출"].sum().values,
        })

        prev30_seq = (
            prev30[["고객ID", "주문번호", "거래일시"]]
            .drop_duplicates()
            .sort_values(["고객ID", "거래일시"])
            .copy()
        )
        prev30_seq["prev_order_date"] = prev30_seq.groupby("고객ID")["거래일시"].shift(1)
        prev30_seq["gap_days"] = (prev30_seq["거래일시"] - prev30_seq["prev_order_date"]).dt.days

        prev30_gap = prev30_seq.groupby("고객ID")["gap_days"].agg(
            avg_gap_prev30d="mean",
            last_gap_prev30d="last"
        ).reset_index()

        prev30_feat = prev30_feat.merge(prev30_gap, on="고객ID", how="left")

    out = out.merge(prev30_feat, on="고객ID", how="left")

    out["order_change_rate_30_vs_prev30"] = _safe_div(
        out.get("order_count_30d", 0) - out.get("order_count_prev30d", 0),
        np.maximum(out.get("order_count_prev30d", 0), 1)
    )
    out["sales_change_rate_30_vs_prev30"] = _safe_div(
        out.get("sales_sum_30d", 0) - out.get("sales_sum_prev30d", 0),
        np.maximum(out.get("sales_sum_prev30d", 0), 1)
    )
    out["gap_change_30_vs_prev30"] = out.get("avg_gap_30d", np.nan) - out.get("avg_gap_prev30d", np.nan)

    if 14 in lookback_windows:
        prev14_start = snapshot_date - pd.Timedelta(days=28)
        prev14_end = snapshot_date - pd.Timedelta(days=14)
        prev14 = hist[(hist["거래일시"] > prev14_start) & (hist["거래일시"] <= prev14_end)].copy()

        if prev14.empty:
            prev14_feat = pd.DataFrame({"고객ID": out["고객ID"].copy()})
        else:
            pg = prev14.groupby("고객ID")
            prev14_feat = pd.DataFrame({
                "고객ID": pg["주문번호"].nunique().index,
                "order_count_prev14d": pg["주문번호"].nunique().values,
                "sales_sum_prev14d": pg["매출"].sum().values,
            })

        out = out.merge(prev14_feat, on="고객ID", how="left")
        out["order_change_rate_14_vs_prev14"] = _safe_div(
            out.get("order_count_14d", 0) - out.get("order_count_prev14d", 0),
            np.maximum(out.get("order_count_prev14d", 0), 1)
        )
        out["sales_change_rate_14_vs_prev14"] = _safe_div(
            out.get("sales_sum_14d", 0) - out.get("sales_sum_prev14d", 0),
            np.maximum(out.get("sales_sum_prev14d", 0), 1)
        )

    recent_gap_df = ord_day.dropna(subset=["gap_days"]).copy()
    recent_gap_df["gap_rank_desc"] = recent_gap_df.groupby("고객ID")["거래일시"].rank(method="first", ascending=False)
    recent_3 = recent_gap_df[recent_gap_df["gap_rank_desc"] <= 3].copy()
    if not recent_3.empty:
        recent_gap_feat = recent_3.groupby("고객ID")["gap_days"].agg(
            recent_gap_ma3="mean"
        ).reset_index()
        out = out.merge(recent_gap_feat, on="고객ID", how="left")
        out["last_gap_acceleration"] = out["last_gap_days"] - out["recent_gap_ma3"]

    weighted_hist = hist[["고객ID", "주문번호", "거래일시", "매출"]].copy()
    weighted_hist["days_from_snapshot"] = (snapshot_date - weighted_hist["거래일시"]).dt.days
    weighted_hist["decay_w"] = _exp_decay_weight(weighted_hist["days_from_snapshot"], half_life=30.0)
    weighted_hist["weighted_sales"] = weighted_hist["매출"] * weighted_hist["decay_w"]

    weighted_sales = weighted_hist.groupby("고객ID")["weighted_sales"].sum().reset_index(name="weighted_sales_sum")
    weighted_order = (
        weighted_hist[["고객ID", "주문번호", "decay_w"]]
        .drop_duplicates()
        .groupby("고객ID")["decay_w"]
        .sum()
        .reset_index(name="weighted_order_count")
    )

    out = out.merge(weighted_sales, on="고객ID", how="left")
    out = out.merge(weighted_order, on="고객ID", how="left")
    out["weighted_avg_order_value"] = _safe_div(out["weighted_sales_sum"], out["weighted_order_count"])

    if 30 in lookback_windows and 90 in lookback_windows:
        out["order_trend_30_vs_90"] = _safe_div(out["order_count_30d"], out["order_count_90d"])
        out["sales_trend_30_vs_90"] = _safe_div(out["sales_sum_30d"], out["sales_sum_90d"])

    out["recency_vs_avg_gap"] = _safe_div(out["recency_days"], out["avg_gap_days"])
    out["recency_vs_last_gap"] = _safe_div(out["recency_days"], out["last_gap_days"])
    out["recency_minus_avg_gap"] = out["recency_days"] - out["avg_gap_days"]
    out["recency_minus_last_gap"] = out["recency_days"] - out["last_gap_days"]
    out["gap_zscore"] = _safe_div(
        out["recency_days"] - out["avg_gap_days"],
        np.maximum(out["std_gap_days"], 1)
    )

    out["has_repeat_purchase"] = (out["lifetime_order_count"] >= 2).astype(int)
    out["is_high_recency_risk"] = (out["recency_days"] >= 60).astype(int)
    out["sales_vs_personal_avg"] = _safe_div(out.get("sales_sum_30d", 0), np.maximum(out["avg_order_value"], 1))
    out["orders_vs_personal_avg"] = _safe_div(out.get("order_count_30d", 0), np.maximum(out["orders_per_30d"], 1))

    cat_sales = hist.groupby(["고객ID", "카테고리"])["매출"].sum().reset_index()
    total_sales = hist.groupby("고객ID")["매출"].sum().rename("total_sales").reset_index()
    cat_sales = cat_sales.merge(total_sales, on="고객ID", how="left")
    cat_sales["ratio"] = cat_sales["매출"] / cat_sales["total_sales"].replace(0, 1)

    pivot = cat_sales.pivot_table(index="고객ID", columns="카테고리", values="ratio", aggfunc="sum", fill_value=0).reset_index()
    pivot.columns.name = None

    rename_map = {}
    for c in pivot.columns:
        if c != "고객ID":
            rename_map[c] = f"cat_ratio_{str(c).strip().lower()}"
    pivot = pivot.rename(columns=rename_map)

    out = out.merge(pivot, on="고객ID", how="left")
    out = _fill_numeric_na(out)
    return out


def add_customer_churn_target(
    feature_df: pd.DataFrame,
    raw_df: pd.DataFrame,
    horizon_days: int = 60,
    personalized: bool = True,
    min_personal_horizon: int = 30,
    max_personal_horizon: int = 90,
    gap_multiplier: float = 1.8,
) -> pd.DataFrame:
    feature_df = feature_df.copy()
    future_orders = raw_df[["고객ID", "거래일시"]].copy()

    churn_list = []
    future_buy_count_list = []
    applied_horizon_list = []

    for row in feature_df.itertuples(index=False):
        cust_id = row.고객ID
        snap = row.snapshot_date

        if personalized:
            avg_gap = getattr(row, "avg_gap_days", np.nan)
            last_gap = getattr(row, "last_gap_days", np.nan)
            base_gap = avg_gap
            if pd.isna(base_gap) or base_gap <= 0:
                base_gap = last_gap
            if pd.isna(base_gap) or base_gap <= 0:
                base_gap = horizon_days

            personal_horizon = int(round(base_gap * gap_multiplier))
            personal_horizon = max(min_personal_horizon, min(max_personal_horizon, personal_horizon))
        else:
            personal_horizon = horizon_days

        end_dt = snap + pd.Timedelta(days=personal_horizon)

        fut = future_orders[
            (future_orders["고객ID"] == cust_id) &
            (future_orders["거래일시"] > snap) &
            (future_orders["거래일시"] <= end_dt)
        ]

        future_buy_count = fut.shape[0]
        churn = 1 if future_buy_count == 0 else 0

        churn_list.append(churn)
        future_buy_count_list.append(future_buy_count)
        applied_horizon_list.append(personal_horizon)

    feature_df["future_buy_count"] = future_buy_count_list
    feature_df["applied_horizon_days"] = applied_horizon_list
    feature_df["churn"] = churn_list
    return feature_df


def make_customer_rolling_dataset(
    df: pd.DataFrame,
    horizon_days: int = 60,
    n_snapshots: int = 8,
    step_days: int = 30,
    min_history_days: int = 90,
    lookback_windows: Tuple[int, ...] = (14, 30, 60, 90, 180),
    personalized_label: bool = True,
    min_personal_horizon: int = 30,
    max_personal_horizon: int = 90,
    gap_multiplier: float = 1.8,
    verbose: bool = True,
) -> pd.DataFrame:
    max_dt = df["거래일시"].max()
    latest_snapshot = max_dt - pd.Timedelta(days=horizon_days)
    snapshots = [latest_snapshot - pd.Timedelta(days=step_days * i) for i in range(n_snapshots)]
    snapshots = sorted(snapshots)

    results = []
    for snap in snapshots:
        feat = build_customer_features_generalized(df, snap, lookback_windows=lookback_windows)
        if feat.empty:
            continue

        feat = feat[feat["history_days"] >= min_history_days].copy()
        if feat.empty:
            continue

        feat = add_customer_churn_target(
            feat,
            df,
            horizon_days=horizon_days,
            personalized=personalized_label,
            min_personal_horizon=min_personal_horizon,
            max_personal_horizon=max_personal_horizon,
            gap_multiplier=gap_multiplier,
        )

        results.append(feat)

        if verbose:
            print(f"[customer snapshot={snap.date()}] rows={len(feat):,}, churn_rate={feat['churn'].mean():.4f}")

    if not results:
        raise ValueError("고객 롤링 데이터셋이 비어 있습니다.")

    out = pd.concat(results, axis=0, ignore_index=True)
    return out.sort_values(["snapshot_date", "고객ID"]).reset_index(drop=True)


# =========================================================
# 카테고리 이탈용 피처
# =========================================================

def build_customer_category_features(
    df: pd.DataFrame,
    snapshot_date: pd.Timestamp,
    lookback_windows: Tuple[int, ...] = (14, 30, 60, 90, 180),
    min_category_orders: int = 1,
) -> pd.DataFrame:
    hist = df[df["거래일시"] <= snapshot_date].copy()
    if hist.empty:
        return pd.DataFrame()

    cust_feat = build_customer_features_generalized(df, snapshot_date, lookback_windows=lookback_windows)
    if cust_feat.empty:
        return pd.DataFrame()

    cg = hist.groupby(["고객ID", "카테고리"])
    first_order = cg["거래일시"].min()
    last_order = cg["거래일시"].max()
    order_count = cg["주문번호"].nunique()
    sales_sum = cg["매출"].sum()
    qty_sum = cg["수량"].sum()

    out = pd.DataFrame({
        "고객ID": first_order.index.get_level_values(0),
        "카테고리": first_order.index.get_level_values(1),
        "snapshot_date": snapshot_date,
        "cat_first_order_date": first_order.values,
        "cat_last_order_date": last_order.values,
        "cat_history_days": (snapshot_date - first_order).dt.days.values,
        "cat_recency_days": (snapshot_date - last_order).dt.days.values,
        "cat_lifetime_order_count": order_count.values,
        "cat_lifetime_sales": sales_sum.values,
        "cat_lifetime_qty": qty_sum.values,
    })

    out = out[out["cat_lifetime_order_count"] >= min_category_orders].copy()

    out["cat_avg_order_value"] = _safe_div(out["cat_lifetime_sales"], out["cat_lifetime_order_count"])
    out["cat_orders_per_30d"] = _safe_div(out["cat_lifetime_order_count"], np.maximum(out["cat_history_days"], 1)) * 30
    out["cat_sales_per_30d"] = _safe_div(out["cat_lifetime_sales"], np.maximum(out["cat_history_days"], 1)) * 30

    ord_day = (
        hist[["고객ID", "카테고리", "주문번호", "거래일시"]]
        .drop_duplicates()
        .sort_values(["고객ID", "카테고리", "거래일시"])
        .copy()
    )
    ord_day["prev_order_date"] = ord_day.groupby(["고객ID", "카테고리"])["거래일시"].shift(1)
    ord_day["gap_days"] = (ord_day["거래일시"] - ord_day["prev_order_date"]).dt.days

    gap_stats = ord_day.groupby(["고객ID", "카테고리"])["gap_days"].agg(
        cat_avg_gap_days="mean",
        cat_std_gap_days="std",
        cat_last_gap_days="last",
    ).reset_index()

    out = out.merge(gap_stats, on=["고객ID", "카테고리"], how="left")

    for w in lookback_windows:
        st = snapshot_date - pd.Timedelta(days=w)
        sub = hist[hist["거래일시"] > st].copy()

        if sub.empty:
            temp = pd.DataFrame({"고객ID": out["고객ID"], "카테고리": out["카테고리"]})
        else:
            sg = sub.groupby(["고객ID", "카테고리"])
            temp = pd.DataFrame({
                "고객ID": sg["주문번호"].nunique().index.get_level_values(0),
                "카테고리": sg["주문번호"].nunique().index.get_level_values(1),
                f"cat_order_count_{w}d": sg["주문번호"].nunique().values,
                f"cat_sales_sum_{w}d": sg["매출"].sum().values,
            })

        out = out.merge(temp, on=["고객ID", "카테고리"], how="left")

    prev30_start = snapshot_date - pd.Timedelta(days=60)
    prev30_end = snapshot_date - pd.Timedelta(days=30)
    prev30 = hist[(hist["거래일시"] > prev30_start) & (hist["거래일시"] <= prev30_end)].copy()

    if prev30.empty:
        prev30_feat = pd.DataFrame({"고객ID": out["고객ID"], "카테고리": out["카테고리"]})
    else:
        pg = prev30.groupby(["고객ID", "카테고리"])
        prev30_feat = pd.DataFrame({
            "고객ID": pg["주문번호"].nunique().index.get_level_values(0),
            "카테고리": pg["주문번호"].nunique().index.get_level_values(1),
            "cat_order_count_prev30d": pg["주문번호"].nunique().values,
            "cat_sales_sum_prev30d": pg["매출"].sum().values,
        })

    out = out.merge(prev30_feat, on=["고객ID", "카테고리"], how="left")

    out["cat_order_change_rate_30_vs_prev30"] = _safe_div(
        out.get("cat_order_count_30d", 0) - out.get("cat_order_count_prev30d", 0),
        np.maximum(out.get("cat_order_count_prev30d", 0), 1)
    )
    out["cat_sales_change_rate_30_vs_prev30"] = _safe_div(
        out.get("cat_sales_sum_30d", 0) - out.get("cat_sales_sum_prev30d", 0),
        np.maximum(out.get("cat_sales_sum_prev30d", 0), 1)
    )

    weighted_hist = hist[["고객ID", "카테고리", "주문번호", "거래일시", "매출"]].copy()
    weighted_hist["days_from_snapshot"] = (snapshot_date - weighted_hist["거래일시"]).dt.days
    weighted_hist["decay_w"] = _exp_decay_weight(weighted_hist["days_from_snapshot"], half_life=30.0)
    weighted_hist["weighted_sales"] = weighted_hist["매출"] * weighted_hist["decay_w"]

    ws = weighted_hist.groupby(["고객ID", "카테고리"])["weighted_sales"].sum().reset_index(name="cat_weighted_sales_sum")
    wo = (
        weighted_hist[["고객ID", "카테고리", "주문번호", "decay_w"]]
        .drop_duplicates()
        .groupby(["고객ID", "카테고리"])["decay_w"]
        .sum()
        .reset_index(name="cat_weighted_order_count")
    )

    out = out.merge(ws, on=["고객ID", "카테고리"], how="left")
    out = out.merge(wo, on=["고객ID", "카테고리"], how="left")
    out["cat_weighted_avg_order_value"] = _safe_div(out["cat_weighted_sales_sum"], out["cat_weighted_order_count"])

    cust_total_sales = hist.groupby("고객ID")["매출"].sum().rename("cust_total_sales").reset_index()
    cat_total_sales = hist.groupby(["고객ID", "카테고리"])["매출"].sum().rename("cat_total_sales").reset_index()
    cat_ratio = cat_total_sales.merge(cust_total_sales, on="고객ID", how="left")
    cat_ratio["category_sales_ratio"] = _safe_div(cat_ratio["cat_total_sales"], np.maximum(cat_ratio["cust_total_sales"], 1))
    out = out.merge(cat_ratio[["고객ID", "카테고리", "category_sales_ratio"]], on=["고객ID", "카테고리"], how="left")

    main_cat = cat_total_sales.sort_values(["고객ID", "cat_total_sales"], ascending=[True, False]).drop_duplicates("고객ID")
    main_cat["is_main_category"] = 1
    out = out.merge(main_cat[["고객ID", "카테고리", "is_main_category"]], on=["고객ID", "카테고리"], how="left")
    out["is_main_category"] = out["is_main_category"].fillna(0)

    recent_cat = (
        hist[["고객ID", "주문번호", "카테고리", "거래일시"]]
        .drop_duplicates(subset=["고객ID", "주문번호", "카테고리", "거래일시"])
        .sort_values(["고객ID", "거래일시"], ascending=[True, False])
        .copy()
    )
    recent_cat["rank_desc"] = recent_cat.groupby("고객ID").cumcount() + 1
    recent_cat = recent_cat[recent_cat["rank_desc"] <= 3].copy()

    if not recent_cat.empty:
        seq = recent_cat.pivot_table(index="고객ID", columns="rank_desc", values="카테고리", aggfunc="first").reset_index()
        seq = seq.rename(columns={1: "recent_cat_1", 2: "recent_cat_2", 3: "recent_cat_3"})
        out = out.merge(seq, on="고객ID", how="left")

    cat_prob = hist.groupby(["고객ID", "카테고리"])["매출"].sum().reset_index()
    total = cat_prob.groupby("고객ID")["매출"].sum().rename("total").reset_index()
    cat_prob = cat_prob.merge(total, on="고객ID", how="left")
    cat_prob["p"] = _safe_div(cat_prob["매출"], np.maximum(cat_prob["total"], 1))
    cat_prob["entropy_part"] = -(cat_prob["p"] * np.log(cat_prob["p"].replace(0, np.nan)))
    entropy = cat_prob.groupby("고객ID")["entropy_part"].sum().reset_index(name="category_entropy")
    out = out.merge(entropy, on="고객ID", how="left")

    last30 = hist[hist["거래일시"] > snapshot_date - pd.Timedelta(days=30)].copy()
    last180 = hist[hist["거래일시"] > snapshot_date - pd.Timedelta(days=180)].copy()

    if not last30.empty and not last180.empty:
        main30 = last30.groupby(["고객ID", "카테고리"])["매출"].sum().reset_index()
        main30 = main30.sort_values(["고객ID", "매출"], ascending=[True, False]).drop_duplicates("고객ID")
        main30 = main30.rename(columns={"카테고리": "main_cat_30d"})[["고객ID", "main_cat_30d"]]

        main180 = last180.groupby(["고객ID", "카테고리"])["매출"].sum().reset_index()
        main180 = main180.sort_values(["고객ID", "매출"], ascending=[True, False]).drop_duplicates("고객ID")
        main180 = main180.rename(columns={"카테고리": "main_cat_180d"})[["고객ID", "main_cat_180d"]]

        out = out.merge(main30, on="고객ID", how="left")
        out = out.merge(main180, on="고객ID", how="left")
        out["main_category_changed"] = (out["main_cat_30d"] != out["main_cat_180d"]).astype(int)

    out["expected_repurchase_due_food"] = np.where(
        out["카테고리"].astype(str).str.contains("food|사료", case=False, regex=True),
        _safe_div(out["cat_recency_days"], np.maximum(out["cat_avg_gap_days"], 1)),
        0
    )
    out["expected_repurchase_due_disposable"] = np.where(
        out["카테고리"].astype(str).str.contains("disposable|배변|용품", case=False, regex=True),
        _safe_div(out["cat_recency_days"], np.maximum(out["cat_avg_gap_days"], 1)),
        0
    )

    out["cat_recency_vs_avg_gap"] = _safe_div(out["cat_recency_days"], out["cat_avg_gap_days"])
    out["cat_gap_zscore"] = _safe_div(
        out["cat_recency_days"] - out["cat_avg_gap_days"],
        np.maximum(out["cat_std_gap_days"], 1)
    )

    out = out.merge(cust_feat, on=["고객ID", "snapshot_date"], how="left")
    out = _fill_numeric_na(out)
    return out


def add_category_churn_target(
    feature_df: pd.DataFrame,
    raw_df: pd.DataFrame,
    horizon_days: int = 60,
    personalized: bool = True,
    min_personal_horizon: int = 30,
    max_personal_horizon: int = 90,
    gap_multiplier: float = 1.8,
) -> pd.DataFrame:
    feature_df = feature_df.copy()
    future_orders = raw_df[["고객ID", "카테고리", "거래일시"]].copy()

    churn_list = []
    future_buy_count_list = []
    applied_horizon_list = []

    for row in feature_df.itertuples(index=False):
        cust_id = row.고객ID
        cat = row.카테고리
        snap = row.snapshot_date

        if personalized:
            avg_gap = getattr(row, "cat_avg_gap_days", np.nan)
            last_gap = getattr(row, "cat_last_gap_days", np.nan)

            base_gap = avg_gap
            if pd.isna(base_gap) or base_gap <= 0:
                base_gap = last_gap
            if pd.isna(base_gap) or base_gap <= 0:
                base_gap = horizon_days

            personal_horizon = int(round(base_gap * gap_multiplier))
            personal_horizon = max(min_personal_horizon, min(max_personal_horizon, personal_horizon))
        else:
            personal_horizon = horizon_days

        end_dt = snap + pd.Timedelta(days=personal_horizon)

        fut = future_orders[
            (future_orders["고객ID"] == cust_id) &
            (future_orders["카테고리"] == cat) &
            (future_orders["거래일시"] > snap) &
            (future_orders["거래일시"] <= end_dt)
        ]

        future_buy_count = fut.shape[0]
        churn = 1 if future_buy_count == 0 else 0

        churn_list.append(churn)
        future_buy_count_list.append(future_buy_count)
        applied_horizon_list.append(personal_horizon)

    feature_df["future_cat_buy_count"] = future_buy_count_list
    feature_df["cat_applied_horizon_days"] = applied_horizon_list
    feature_df["category_churn"] = churn_list
    return feature_df


def make_category_rolling_dataset(
    df: pd.DataFrame,
    horizon_days: int = 60,
    n_snapshots: int = 8,
    step_days: int = 30,
    min_history_days: int = 90,
    lookback_windows: Tuple[int, ...] = (14, 30, 60, 90, 180),
    personalized_label: bool = True,
    min_personal_horizon: int = 30,
    max_personal_horizon: int = 90,
    gap_multiplier: float = 1.8,
    min_category_orders: int = 2,
    min_category_rows: int = 100,
    verbose: bool = True,
) -> Tuple[pd.DataFrame, List[str]]:
    max_dt = df["거래일시"].max()
    latest_snapshot = max_dt - pd.Timedelta(days=horizon_days)
    snapshots = [latest_snapshot - pd.Timedelta(days=step_days * i) for i in range(n_snapshots)]
    snapshots = sorted(snapshots)

    cat_count = df.groupby("카테고리")["주문번호"].nunique().sort_values(ascending=False)
    usable_cats = cat_count[cat_count >= min_category_rows].index.tolist()

    results = []
    for snap in snapshots:
        feat = build_customer_category_features(
            df[df["카테고리"].isin(usable_cats)].copy(),
            snap,
            lookback_windows=lookback_windows,
            min_category_orders=min_category_orders,
        )
        if feat.empty:
            continue

        feat = feat[feat["history_days"] >= min_history_days].copy()
        if feat.empty:
            continue

        feat = add_category_churn_target(
            feat,
            df[df["카테고리"].isin(usable_cats)].copy(),
            horizon_days=horizon_days,
            personalized=personalized_label,
            min_personal_horizon=min_personal_horizon,
            max_personal_horizon=max_personal_horizon,
            gap_multiplier=gap_multiplier,
        )

        results.append(feat)

        if verbose:
            print(f"[category snapshot={snap.date()}] rows={len(feat):,}, churn_rate={feat['category_churn'].mean():.4f}")

    if not results:
        raise ValueError("카테고리 롤링 데이터셋이 비어 있습니다.")

    out = pd.concat(results, axis=0, ignore_index=True)
    out = out.sort_values(["snapshot_date", "고객ID", "카테고리"]).reset_index(drop=True)
    return out, usable_cats


# =========================================================
# 피처 리스트
# =========================================================

SIMPLE_FEATURES_3_6M = [
    "history_days",
    "recency_days",
    "lifetime_order_count",
    "lifetime_sales",
    "avg_order_value",
    "orders_per_30d",
    "sales_per_30d",
    "has_repeat_purchase",
    "is_high_recency_risk",
    "avg_gap_days",
    "last_gap_days",
    "recency_vs_avg_gap",
    "recency_vs_last_gap",
    "order_count_30d",
    "order_count_60d",
    "order_count_90d",
    "sales_sum_30d",
    "sales_sum_60d",
    "sales_sum_90d",
    "category_nunique_30d",
    "category_nunique_90d",
    "avg_gap_30d",
    "last_gap_30d",
]

SIMPLE_FEATURES_6_12M = [
    "history_days",
    "recency_days",
    "lifetime_order_count",
    "lifetime_sales",
    "avg_order_value",
    "orders_per_30d",
    "sales_per_30d",
    "has_repeat_purchase",
    "avg_gap_days",
    "last_gap_days",
    "recency_vs_avg_gap",
    "recency_vs_last_gap",
    "order_count_30d",
    "order_count_60d",
    "order_count_90d",
    "order_count_180d",
    "sales_sum_30d",
    "sales_sum_60d",
    "sales_sum_90d",
    "sales_sum_180d",
    "category_nunique_30d",
    "category_nunique_90d",
    "category_nunique_180d",
    "order_trend_30_vs_90",
    "sales_trend_30_vs_90",
]

CATEGORY_FEATURES = [
    "history_days", "recency_days", "lifetime_order_count", "lifetime_sales",
    "avg_gap_days", "last_gap_days", "recency_vs_avg_gap", "gap_zscore",
    "category_sales_ratio", "is_main_category", "category_entropy", "main_category_changed",
    "cat_history_days", "cat_recency_days", "cat_lifetime_order_count", "cat_lifetime_sales",
    "cat_avg_order_value", "cat_orders_per_30d", "cat_sales_per_30d",
    "cat_avg_gap_days", "cat_std_gap_days", "cat_last_gap_days",
    "cat_order_count_14d", "cat_order_count_30d", "cat_order_count_60d", "cat_order_count_90d",
    "cat_sales_sum_14d", "cat_sales_sum_30d", "cat_sales_sum_60d", "cat_sales_sum_90d",
    "cat_order_count_prev30d", "cat_sales_sum_prev30d",
    "cat_order_change_rate_30_vs_prev30", "cat_sales_change_rate_30_vs_prev30",
    "cat_weighted_sales_sum", "cat_weighted_order_count", "cat_weighted_avg_order_value",
    "cat_recency_vs_avg_gap", "cat_gap_zscore",
    "expected_repurchase_due_food", "expected_repurchase_due_disposable",
]


def prepare_simple_X_y(df: pd.DataFrame, feature_set: str = "6_12m"):
    df = df.copy()
    y = df["churn"].astype(int).copy()

    if feature_set == "3_6m":
        candidate_cols = SIMPLE_FEATURES_3_6M
    elif feature_set == "6_12m":
        candidate_cols = SIMPLE_FEATURES_6_12M
    else:
        raise ValueError("feature_set must be '3_6m' or '6_12m'")

    feature_cols = [c for c in candidate_cols if c in df.columns]
    X = df[feature_cols].copy()
    for c in X.columns:
        X[c] = pd.to_numeric(X[c], errors="coerce")
    X = _fill_numeric_na(X)
    return X, y, feature_cols


def prepare_X_y(df: pd.DataFrame, feature_cols: List[str], target_col: str):
    cols = [c for c in feature_cols if c in df.columns]
    X = df[cols].copy()
    for c in X.columns:
        X[c] = pd.to_numeric(X[c], errors="coerce")
    X = _fill_numeric_na(X)
    y = df[target_col].astype(int).copy()
    return X, y, cols


def align_columns(X: pd.DataFrame, feature_cols: List[str]) -> pd.DataFrame:
    X = X.copy()
    for c in feature_cols:
        if c not in X.columns:
            X[c] = 0
    X = X[feature_cols].copy()
    X = _fill_numeric_na(X)
    return X


# =========================================================
# 모델 정의
# =========================================================

def get_candidate_models() -> Dict[str, object]:
    models: Dict[str, object] = {}

    models["logistic"] = Pipeline([
        ("scaler", StandardScaler()),
        ("clf", LogisticRegression(
            C=0.3,
            class_weight="balanced",
            max_iter=2000,
            random_state=42,
        )),
    ])

    try:
        import lightgbm as lgb
        models["lightgbm"] = lgb.LGBMClassifier(
            n_estimators=300,
            learning_rate=0.03,
            num_leaves=15,
            max_depth=4,
            min_child_samples=60,
            subsample=0.8,
            colsample_bytree=0.8,
            reg_alpha=2.0,
            reg_lambda=2.0,
            class_weight="balanced",
            random_state=42,
            verbose=-1,
        )
    except Exception:
        pass

    try:
        from xgboost import XGBClassifier
        models["xgboost"] = XGBClassifier(
            n_estimators=250,
            learning_rate=0.03,
            max_depth=4,
            min_child_weight=6,
            subsample=0.8,
            colsample_bytree=0.8,
            reg_alpha=2.0,
            reg_lambda=2.0,
            objective="binary:logistic",
            eval_metric="logloss",
            random_state=42,
            n_jobs=-1,
        )
    except Exception:
        pass

    try:
        from catboost import CatBoostClassifier
        models["catboost"] = CatBoostClassifier(
            iterations=300,
            learning_rate=0.03,
            depth=4,
            l2_leaf_reg=8.0,
            loss_function="Logloss",
            eval_metric="PRAUC",
            random_seed=42,
            verbose=0,
        )
    except Exception:
        pass

    return models


def get_customer_model_3_6():
    models = get_candidate_models()
    return models.get("xgboost", models["logistic"])


def get_customer_model_6_12():
    models = get_candidate_models()
    return models["logistic"]


def fit_one_model_with_validation(model_name, model, X_train, y_train, X_valid, y_valid):
    if model_name == "lightgbm":
        try:
            from lightgbm import early_stopping, log_evaluation
            model.fit(
                X_train,
                y_train,
                eval_set=[(X_valid, y_valid)],
                eval_metric="average_precision",
                callbacks=[early_stopping(50, verbose=False), log_evaluation(0)],
            )
        except Exception:
            model.fit(X_train, y_train)
    elif model_name == "xgboost":
        model.fit(
            X_train,
            y_train,
            eval_set=[(X_valid, y_valid)],
            verbose=False,
        )
    elif model_name == "catboost":
        model.fit(
            X_train,
            y_train,
            eval_set=(X_valid, y_valid),
            use_best_model=True,
            verbose=False,
        )
    else:
        model.fit(X_train, y_train)

    valid_prob = model.predict_proba(X_valid)[:, 1]
    best_th, th_df = pick_threshold_on_validation(y_valid, valid_prob)
    return model, valid_prob, best_th, th_df


def get_category_model():

    try:
        import lightgbm as lgb
        return lgb.LGBMClassifier(
            n_estimators=200,
            learning_rate=0.05,
            num_leaves=31,
            max_depth=6,
            min_child_samples=20,
            subsample=0.8,
            colsample_bytree=0.8,
            random_state=42,
            n_jobs=-1,
        )
    except Exception:
        return RandomForestClassifier(
            n_estimators=150,
            max_depth=8,
            min_samples_leaf=10,
            min_samples_split=5,
            max_features="sqrt",
            class_weight="balanced",
            random_state=42,
            n_jobs=-1,
        )


# =========================================================
# 학습 공통
# =========================================================

def fit_final_single_model(
    model_df: pd.DataFrame,
    model_name: str,
    feature_set: str = "6_12m",
) -> Dict:
    df = model_df.copy().sort_values(["snapshot_date", "고객ID"]).reset_index(drop=True)

    X, y, feature_cols = prepare_simple_X_y(df, feature_set=feature_set)
    snap_list = sorted(df["snapshot_date"].unique())
    if len(snap_list) < 3:
        raise ValueError("snapshot 수가 부족합니다.")

    train_snaps = snap_list[:-2]
    valid_snaps = [snap_list[-2]]
    test_snaps = [snap_list[-1]]

    train_idx = df.index[df["snapshot_date"].isin(train_snaps)]
    valid_idx = df.index[df["snapshot_date"].isin(valid_snaps)]
    test_idx = df.index[df["snapshot_date"].isin(test_snaps)]

    models = get_candidate_models()
    if model_name not in models:
        raise ValueError(f"지원하지 않는 모델입니다: {model_name}. 사용 가능: {list(models.keys())}")

    model = models[model_name]
    fitted_model, _, best_th, th_df = fit_one_model_with_validation(
        model_name,
        model,
        X.loc[train_idx], y.loc[train_idx],
        X.loc[valid_idx], y.loc[valid_idx],
    )

    test_prob = fitted_model.predict_proba(X.loc[test_idx])[:, 1]
    test_pred = (test_prob >= best_th).astype(int)
    metrics = build_metrics_frame(
        y_true=y.loc[test_idx],
        prob=test_prob,
        threshold=best_th,
        pred=test_pred,
    )

    return {
        "model_name": model_name,
        "model": fitted_model,
        "threshold": best_th,
        "threshold_table": th_df,
        "feature_cols": feature_cols,
        "feature_set": feature_set,
        "metrics": metrics,
        "test_df": df.loc[test_idx].copy().assign(
            pred_prob=test_prob,
            pred_label=test_pred,
        ),
    }


# =========================================================
# 고객 전체 이탈 모델 학습
# =========================================================

def train_and_save_customer_models(
    input_csv_path: str,
    column_mapping: Optional[Dict[str, str]] = None,
    horizon_days: int = 60,
    n_snapshots: int = 8,
    step_days: int = 30,
    min_history_days: int = 90,
    lookback_windows: Tuple[int, ...] = (14, 30, 60, 90, 180),
    personalized_label: bool = True,
    min_personal_horizon: int = 30,
    max_personal_horizon: int = 90,
    gap_multiplier: float = 1.8,
    best_model_name_3_6: str = "xgboost",
    best_model_name_6_12: str = "logistic",
    verbose: bool = True,
) -> Dict:
    raw_df = pd.read_csv(input_csv_path)
    raw_df = preprocess_pet_data(raw_df, column_mapping=column_mapping)

    if verbose:
        print("raw shape:", raw_df.shape)
        print("date range:", raw_df["거래일시"].min(), "~", raw_df["거래일시"].max())
        print("data months:", round(estimate_data_months(raw_df), 2))

    rolling_df = make_customer_rolling_dataset(
        df=raw_df,
        horizon_days=horizon_days,
        n_snapshots=n_snapshots,
        step_days=step_days,
        min_history_days=min_history_days,
        lookback_windows=lookback_windows,
        personalized_label=personalized_label,
        min_personal_horizon=min_personal_horizon,
        max_personal_horizon=max_personal_horizon,
        gap_multiplier=gap_multiplier,
        verbose=verbose,
    )
    rolling_df = add_segment_column(rolling_df)

    rolling_3_6 = rolling_df[rolling_df["history_segment"] == "m3_6"].copy()
    rolling_6_12 = rolling_df[rolling_df["history_segment"] == "m6_12"].copy()

    if len(rolling_3_6) == 0:
        raise ValueError("3~6개월 학습 데이터가 부족합니다.")
    if len(rolling_6_12) == 0:
        raise ValueError("6~12개월 학습 데이터가 부족합니다.")

    result_3_6 = fit_final_single_model(
        rolling_3_6,
        model_name=best_model_name_3_6,
        feature_set="3_6m",
    )
    joblib.dump(result_3_6["model"], CUSTOMER_MODEL_PATH_3_6)
    joblib.dump(result_3_6["feature_cols"], CUSTOMER_FEATURE_PATH_3_6)
    joblib.dump(result_3_6["threshold"], CUSTOMER_THRESHOLD_PATH_3_6)
    joblib.dump(result_3_6["model_name"], CUSTOMER_MODEL_NAME_PATH_3_6)

    result_6_12 = fit_final_single_model(
        rolling_6_12,
        model_name=best_model_name_6_12,
        feature_set="6_12m",
    )
    joblib.dump(result_6_12["model"], CUSTOMER_MODEL_PATH_6_12)
    joblib.dump(result_6_12["feature_cols"], CUSTOMER_FEATURE_PATH_6_12)
    joblib.dump(result_6_12["threshold"], CUSTOMER_THRESHOLD_PATH_6_12)
    joblib.dump(result_6_12["model_name"], CUSTOMER_MODEL_NAME_PATH_6_12)

    if verbose:
        print("saved:", CUSTOMER_MODEL_PATH_3_6)
        print("saved:", CUSTOMER_MODEL_PATH_6_12)

    return {
        "rolling_df": rolling_df,
        "model_3_6_name": result_3_6["model_name"],
        "model_6_12_name": result_6_12["model_name"],
        "model_3_6_metrics": result_3_6["metrics"],
        "model_6_12_metrics": result_6_12["metrics"],
    }


# =========================================================
# 카테고리 이탈 모델 학습
# =========================================================

def train_and_save_category_model(
    input_csv_path: str,
    column_mapping: Optional[Dict[str, str]] = None,
    horizon_days: int = 60,
    n_snapshots: int = 8,
    step_days: int = 30,
    min_history_days: int = 90,
    lookback_windows: Tuple[int, ...] = (14, 30, 60, 90, 180),
    personalized_label: bool = True,
    min_personal_horizon: int = 30,
    max_personal_horizon: int = 90,
    gap_multiplier: float = 1.8,
    min_category_orders: int = 2,
    min_category_rows: int = 100,
    verbose: bool = True,
) -> Dict:
    raw_df = pd.read_csv(input_csv_path)
    raw_df = preprocess_pet_data(raw_df, column_mapping=column_mapping)

    if verbose:
        print("raw shape:", raw_df.shape)
        print("date range:", raw_df["거래일시"].min(), "~", raw_df["거래일시"].max())
        print("data months:", round(estimate_data_months(raw_df), 2))

    rolling_df, usable_cats = make_category_rolling_dataset(
        df=raw_df,
        horizon_days=horizon_days,
        n_snapshots=n_snapshots,
        step_days=step_days,
        min_history_days=min_history_days,
        lookback_windows=lookback_windows,
        personalized_label=personalized_label,
        min_personal_horizon=min_personal_horizon,
        max_personal_horizon=max_personal_horizon,
        gap_multiplier=gap_multiplier,
        min_category_orders=min_category_orders,
        min_category_rows=min_category_rows,
        verbose=verbose,
    )

    if len(rolling_df) == 0:
        raise ValueError("카테고리 학습 데이터가 부족합니다.")

    result = fit_final_single_model(
        rolling_df,
        model=get_category_model(),
        feature_cols=CATEGORY_FEATURES,
        target_col="category_churn",
    )

    joblib.dump(result["model"], CATEGORY_MODEL_PATH)
    joblib.dump(result["feature_cols"], CATEGORY_FEATURE_PATH)
    joblib.dump(result["threshold"], CATEGORY_THRESHOLD_PATH)
    joblib.dump(usable_cats, CATEGORY_RULE_CATS_PATH)

    if verbose:
        print("saved:", CATEGORY_MODEL_PATH)

    return {
        "rolling_df": rolling_df,
        "usable_categories": usable_cats,
        "category_model_metrics": result["metrics"],
    }


# =========================================================
# 추론용 보조
# =========================================================

def cold_start_rule_score(df: pd.DataFrame) -> np.ndarray:
    recency = df.get("recency_days", pd.Series(0, index=df.index)).fillna(0)
    freq = df.get("lifetime_order_count", pd.Series(1, index=df.index)).fillna(1)
    sales30 = df.get("sales_sum_30d", pd.Series(0, index=df.index)).fillna(0)
    repeat = df.get("has_repeat_purchase", pd.Series(0, index=df.index)).fillna(0)

    score = (
        0.45 * np.clip(recency / 90, 0, 1) +
        0.25 * (1 - np.clip(freq / 3, 0, 1)) +
        0.20 * (1 - np.clip(sales30 / max(float(sales30.quantile(0.75)) if len(sales30) > 0 else 1.0, 1.0), 0, 1)) +
        0.10 * (1 - repeat)
    )
    return np.clip(score, 0.01, 0.99)


def fit_dual_router_models(
    rolling_df: pd.DataFrame,
    model_name_3_6: str = "xgboost",
    model_name_6_12: str = "logistic",
) -> Dict:
    rolling_df = add_segment_column(rolling_df.copy())

    df_3_6 = rolling_df[rolling_df["history_segment"] == "m3_6"].copy()
    df_6_12 = rolling_df[rolling_df["history_segment"] == "m6_12"].copy()

    if df_3_6.empty:
        raise ValueError("3~6개월 학습 데이터가 부족합니다.")
    if df_6_12.empty:
        raise ValueError("6~12개월 학습 데이터가 부족합니다.")

    model_3_6 = fit_final_single_model(df_3_6, model_name=model_name_3_6, feature_set="3_6m")
    model_6_12 = fit_final_single_model(df_6_12, model_name=model_name_6_12, feature_set="6_12m")

    return {
        "model_3_6": model_3_6,
        "model_6_12": model_6_12,
    }


def get_model_risk_label(prob: float, router_key: str) -> str:
    if pd.isna(prob):
        return "판단불가"

    if router_key == "model_3_6":
        if prob >= 0.80:
            return "상위위험군"
        elif prob >= 0.60:
            return "주의"
        return "관찰"

    if router_key == "model_6_12":
        if prob >= 0.80:
            return "휴면직전"
        elif prob >= 0.60:
            return "위험"
        elif prob >= 0.30:
            return "주의"
        return "안정"

    if router_key == "category_model":
        if prob >= 0.80:
            return "카테고리 이탈 고위험"
        elif prob >= 0.60:
            return "카테고리 이탈 주의"
        return "카테고리 안정"

    return "주의" if prob >= 0.70 else "참고"


def _load_customer_artifacts():
    if not CUSTOMER_MODEL_PATH_3_6.exists():
        raise FileNotFoundError(f"파일 없음: {CUSTOMER_MODEL_PATH_3_6}")
    if not CUSTOMER_MODEL_PATH_6_12.exists():
        raise FileNotFoundError(f"파일 없음: {CUSTOMER_MODEL_PATH_6_12}")

    model_name_3_6 = "xgboost"
    model_name_6_12 = "logistic"
    if CUSTOMER_MODEL_NAME_PATH_3_6.exists():
        model_name_3_6 = str(joblib.load(CUSTOMER_MODEL_NAME_PATH_3_6))
    if CUSTOMER_MODEL_NAME_PATH_6_12.exists():
        model_name_6_12 = str(joblib.load(CUSTOMER_MODEL_NAME_PATH_6_12))

    return {
        "model_3_6": joblib.load(CUSTOMER_MODEL_PATH_3_6),
        "feature_cols_3_6": joblib.load(CUSTOMER_FEATURE_PATH_3_6),
        "threshold_3_6": float(joblib.load(CUSTOMER_THRESHOLD_PATH_3_6)),
        "model_name_3_6": model_name_3_6,
        "feature_set_3_6": "3_6m",
        "model_6_12": joblib.load(CUSTOMER_MODEL_PATH_6_12),
        "feature_cols_6_12": joblib.load(CUSTOMER_FEATURE_PATH_6_12),
        "threshold_6_12": float(joblib.load(CUSTOMER_THRESHOLD_PATH_6_12)),
        "model_name_6_12": model_name_6_12,
        "feature_set_6_12": "6_12m",
    }


def _load_category_artifacts():
    if not CATEGORY_MODEL_PATH.exists():
        raise FileNotFoundError(f"파일 없음: {CATEGORY_MODEL_PATH}")

    return {
        "model": joblib.load(CATEGORY_MODEL_PATH),
        "feature_cols": joblib.load(CATEGORY_FEATURE_PATH),
        "threshold": float(joblib.load(CATEGORY_THRESHOLD_PATH)),
        "usable_categories": joblib.load(CATEGORY_RULE_CATS_PATH) if CATEGORY_RULE_CATS_PATH.exists() else [],
    }


# =========================================================
# 고객 전체 이탈 추론
# =========================================================

def score_customers(
    df_std: pd.DataFrame,
    column_mapping: Optional[Dict[str, str]] = None,
    horizon_days: int = 60,
) -> pd.DataFrame:
    df = preprocess_pet_data(df_std, column_mapping=column_mapping)
    data_months = estimate_data_months(df)
    router_key = get_router_key_by_data_months(data_months)
    reliability = get_data_reliability(data_months)

    latest_snapshot = df["거래일시"].max() - pd.Timedelta(days=horizon_days)
    feat = build_customer_features_generalized(
        df,
        snapshot_date=latest_snapshot,
        lookback_windows=(30, 60, 90, 180),
    )
    if feat.empty:
        raise ValueError("예측 가능한 고객 피처가 생성되지 않았습니다.")

    feat = add_segment_column(feat)
    display_df = feat.copy()
    display_df["data_months"] = data_months
    display_df["router_key"] = router_key
    display_df["reliability"] = reliability

    if router_key == "not_enough_data":
        prob = cold_start_rule_score(display_df)
        pred = (prob >= 0.45).astype(int)
        model_used = "cold_rule"
        threshold = 0.45
    else:
        artifacts = _load_customer_artifacts()
        if router_key == "model_3_6":
            X, _, _ = prepare_simple_X_y(display_df.assign(churn=0), feature_set=artifacts["feature_set_3_6"])
            X = align_columns(X, artifacts["feature_cols_3_6"])
            prob = artifacts["model_3_6"].predict_proba(X)[:, 1]
            threshold = artifacts["threshold_3_6"]
            pred = (prob >= threshold).astype(int)
            model_used = f"3_6_{artifacts['model_name_3_6']}"
        else:
            X, _, _ = prepare_simple_X_y(display_df.assign(churn=0), feature_set=artifacts["feature_set_6_12"])
            X = align_columns(X, artifacts["feature_cols_6_12"])
            prob = artifacts["model_6_12"].predict_proba(X)[:, 1]
            threshold = artifacts["threshold_6_12"]
            pred = (prob >= threshold).astype(int)
            model_used = f"6_12_{artifacts['model_name_6_12']}"

    display_df["churn_prob"] = prob
    display_df["pred_label"] = pred
    display_df["model_used"] = model_used
    display_df["threshold_used"] = threshold
    display_df["risk_percentile"] = display_df["churn_prob"].rank(pct=True)

    def risk_group(pct: float) -> str:
        if pd.isna(pct):
            return "unknown"
        if pct >= 0.9:
            return "high"
        if pct >= 0.7:
            return "medium"
        return "low"

    display_df["risk_group"] = display_df["risk_percentile"].apply(risk_group)
    display_df["model_risk"] = display_df["churn_prob"].apply(lambda x: get_model_risk_label(x, router_key))
    return display_df.sort_values("churn_prob", ascending=False).reset_index(drop=True)


# =========================================================
# 카테고리 이탈 추론
# =========================================================

def score_customer_categories(
    df_std: pd.DataFrame,
    column_mapping: Optional[Dict[str, str]] = None,
) -> pd.DataFrame:
    df = preprocess_pet_data(df_std, column_mapping=column_mapping)
    artifacts = _load_category_artifacts()

    snapshot_date = df["거래일시"].max()
    feat = build_customer_category_features(
        df[df["카테고리"].isin(artifacts["usable_categories"])].copy(),
        snapshot_date,
        lookback_windows=(14, 30, 60, 90, 180),
        min_category_orders=1,
    )

    if feat.empty:
        raise ValueError("예측 가능한 카테고리 피처가 생성되지 않았습니다.")

    X = align_columns(feat, artifacts["feature_cols"])
    prob = artifacts["model"].predict_proba(X)[:, 1]
    threshold = artifacts["threshold"]
    pred = (prob >= threshold).astype(int)

    feat["category_churn_prob"] = prob
    feat["category_pred_label"] = pred
    feat["category_threshold_used"] = threshold
    feat["category_model_used"] = "category_lgbm"
    feat["category_risk"] = feat["category_churn_prob"].apply(lambda x: get_model_risk_label(x, "category_model"))

    cols = [
        "고객ID", "카테고리", "snapshot_date",
        "history_days", "recency_days", "lifetime_sales",
        "cat_history_days", "cat_recency_days", "cat_lifetime_order_count", "cat_lifetime_sales",
        "category_sales_ratio", "is_main_category",
        "cat_recency_vs_avg_gap", "cat_gap_zscore",
        "category_churn_prob", "category_pred_label", "category_risk",
    ]
    cols = [c for c in cols if c in feat.columns]

    return feat[cols].sort_values(["고객ID", "category_churn_prob"], ascending=[True, False]).reset_index(drop=True)


# =========================================================
# 통합 학습
# =========================================================

def train_all_models(
    input_csv_path: str,
    column_mapping: Optional[Dict[str, str]] = None,
    verbose: bool = True,
) -> Dict:
    customer_result = train_and_save_customer_models(
        input_csv_path=input_csv_path,
        column_mapping=column_mapping,
        verbose=verbose,
    )

    category_result = train_and_save_category_model(
        input_csv_path=input_csv_path,
        column_mapping=column_mapping,
        verbose=verbose,
    )

    return {
        "customer_model_3_6_name": customer_result["model_3_6_name"],
        "customer_model_6_12_name": customer_result["model_6_12_name"],
        "customer_model_3_6_metrics": customer_result["model_3_6_metrics"],
        "customer_model_6_12_metrics": customer_result["model_6_12_metrics"],
        "category_model_metrics": category_result["category_model_metrics"],
    }


if __name__ == "__main__":
    # 예시:
    # result = train_all_models("pet2.csv")
    # print(result)
    #
    # df = pd.read_csv("pet2.csv")
    # customer_scored = score_customers(df)
    # category_scored = score_customer_categories(df)
    # print(customer_scored.head())
    # print(category_scored.head())
    pass