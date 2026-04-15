import re
import streamlit as st
import pandas as pd

from .data_io import get_sample_mapping_hint
from .category_merge_component import render_category_merge_section, CategoryMerger

DISPLAY_REQUIRED = "고객ID / 주문번호 / 거래일시 / 매출"
CORE_REQUIRED = ["고객ID", "주문번호", "거래일시", "매출"]

CATEGORY_CANDIDATES = [
    "카테고리", "분류", "상품분류", "category", "productcategory",
    "producttype", "type", "class", "group", "대분류", "중분류", "소분류"
]


def _find_category_column(cols: list[str]) -> str | None:
    for col in cols:
        norm_col = _normalize_text(col)
        for keyword in CATEGORY_CANDIDATES:
            norm_keyword = _normalize_text(keyword)
            if norm_col == norm_keyword or norm_keyword in norm_col or norm_col in norm_keyword:
                return col
    return None




# ─── helpers ─────────────────────────────────────────────────────────────────

def _normalize_text(value: str) -> str:
    return re.sub(r"[\s_\-\/\(\)\[\]\.]+", "", str(value).strip().lower())


def _build_keyword_map() -> dict[str, list[str]]:
    return {
        "고객ID": [
            "고객", "고객id", "고객번호", "회원", "회원번호", "customer", "customerid",
            "cust", "custid", "user", "userid", "member", "memberid", "client",
            "clientid", "uid", "buyer", "buyerid",
        ],
        "주문번호": [
            "주문", "주문번호", "order", "orderid", "orderno", "invoice",
            "transaction", "transactionid", "tx", "txid", "receipt",
        ],
        "거래일시": [
            "거래일시", "거래일", "구매일", "주문일", "일시", "날짜", "일자", "datetime",
            "timestamp", "date", "time", "created", "createdat", "purchase",
            "purchasedate", "orderdate", "orderdatetime",
        ],
        "매출": [
            "매출", "매출액", "금액", "결제금액", "주문금액", "구매금액", "amount",
            "sales", "revenue", "price", "payment", "pay", "total", "totalprice",
            "gmv", "subtotal",
        ],
        "카테고리": [
            "카테고리", "분류", "상품분류", "category", "productcategory",
            "producttype", "type", "class", "group",
        ],
        "구매채널": [
            "구매채널", "판매채널", "채널", "유입채널", "channel", "source",
            "saleschannel", "storetype", "onoffline", "onlineoffline",
            "offline", "online",
        ],
        "온라인채널": [
            "온라인채널", "플랫폼", "몰", "마켓", "입점몰", "platform", "mall",
            "market", "marketplace", "shop", "store", "app", "web",
        ],
        "결제수단": [
            "결제수단", "결제방법", "결제", "payment", "paymethod", "paymentmethod",
            "method", "card", "cash", "bank", "transfer", "wallet",
        ],
        "시도": [
            "시도", "지역", "주소", "도시", "province", "region", "state", "city",
            "location", "area",
        ],
    }


def _guess_mapping(cols: list[str]) -> dict[str, str | None]:
    keyword_map = _build_keyword_map()
    normalized_cols = {col: _normalize_text(col) for col in cols}
    guessed: dict[str, str | None] = {}

    for std_col in CORE_REQUIRED:
        best_col = None
        best_score = -1

        for col, norm_col in normalized_cols.items():
            score = 0
            if norm_col == _normalize_text(std_col):
                score += 100
            for keyword in keyword_map.get(std_col, []):
                norm_keyword = _normalize_text(keyword)
                if norm_col == norm_keyword:
                    score += 80
                elif norm_keyword in norm_col:
                    score += 35
                elif norm_col in norm_keyword:
                    score += 20

            if std_col == "고객ID" and ("order" in norm_col or "date" in norm_col or "price" in norm_col):
                score -= 25
            if std_col == "주문번호" and ("customer" in norm_col or "user" in norm_col):
                score -= 20
            if std_col == "거래일시" and ("price" in norm_col or "amount" in norm_col):
                score -= 20
            if std_col == "매출" and ("date" in norm_col or "time" in norm_col):
                score -= 20

            if score > best_score:
                best_score = score
                best_col = col

        guessed[std_col] = best_col if best_score > 0 else None

    return guessed


def _mapping_table_for_sample() -> pd.DataFrame:
    hint = get_sample_mapping_hint()
    explain = {
        "고객ID": "누가 샀는지(회원번호/고객번호)",
        "주문번호": "어떤 주문인지(주문 1건 ID)",
        "거래일시": "언제 샀는지(구매/주문 날짜·시간)",
        "매출": "얼마에 샀는지(주문 금액)",
        "카테고리": "무엇을 샀는지(상품 분류)",
        "구매채널": "어디서 샀는지(온라인/오프라인)",
        "온라인채널": "어느 플랫폼인지(쿠팡/스마트스토어/자사몰 등)",
        "결제수단": "어떻게 결제했는지(카드/현금 등)",
        "시도": "어느 지역인지(시/도)",
    }
    return pd.DataFrame(
        [{"표준 컬럼": k, "샘플 컬럼(추천)": v, "설명": explain.get(k, "")} for k, v in hint.items()]
    )


def _standardize_mapped_df(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    if "거래일시" in out.columns:
        out["거래일시"] = pd.to_datetime(out["거래일시"], errors="coerce")
    if "매출" in out.columns:
        out["매출"] = (
            out["매출"]
            .astype(str).str.strip()
            .str.replace(",", "", regex=False)
            .str.replace("원", "", regex=False)
            .str.replace("₩", "", regex=False)
            .str.replace("KRW", "", regex=False)
            .str.replace("−", "-", regex=False)
            .str.replace(r"\((.*?)\)", r"-\1", regex=True)
            .str.replace(r"[^0-9\.-]", "", regex=True)
        )
        out["매출"] = pd.to_numeric(out["매출"], errors="coerce")
    text_cols = ["고객ID", "주문번호", "카테고리", "구매채널", "온라인채널", "결제수단", "시도"]
    for col in text_cols:
        if col in out.columns:
            out[col] = out[col].astype(str).str.strip()
            out.loc[out[col].isin(["nan", "None", "NaT", ""]), col] = pd.NA
    return out


def _apply_negative_sales_mode(df: pd.DataFrame, mode: str) -> tuple[pd.DataFrame, dict]:
    out = df.copy()
    meta = {
        "negative_sales_mode": mode,
        "negative_count": 0,
        "excluded_count": 0,
        "refund_candidate_count": 0,
    }
    if "매출" not in out.columns:
        return out, meta
    negative_mask = out["매출"].fillna(0) < 0
    negative_count = int(negative_mask.sum())
    meta["negative_count"] = negative_count
    if mode == "exclude":
        out = out.loc[~negative_mask].copy()
        meta["excluded_count"] = negative_count
    elif mode == "refund":
        meta["refund_candidate_count"] = negative_count
    return out, meta


def _assess_data_quality(df: pd.DataFrame, negative_sales_mode: str = "refund") -> dict:
    issues: list[str] = []
    info_notes: list[str] = []
    stats: dict = {}
    total_rows = len(df)
    stats["전체 행 수"] = total_rows
    stats["데이터 기간(일)"] = 0

    if total_rows == 0:
        return {
            "grade": "D",
            "issues": ["데이터 행이 없습니다."],
            "info_notes": [],
            "stats": {"전체 행 수": 0},
            "refund_count": 0,
            "duplicate_order_count": 0,
            "score": 0,
            "negative_sales_mode": negative_sales_mode,
            "negative_sales_count": 0,
        }

    required_cols = CORE_REQUIRED
    missing_required_cols = [c for c in required_cols if c not in df.columns]
    if missing_required_cols:
        issues.append(f"필수 표준 컬럼이 누락되었습니다: {', '.join(missing_required_cols)}")

    null_count = 0
    null_ratio_map: dict[str, float] = {}
    for col in required_cols:
        if col in df.columns:
            cnt = int(df[col].isna().sum())
            ratio = cnt / total_rows if total_rows else 0.0
            null_count += cnt
            null_ratio_map[col] = ratio
    stats["필수컬럼 결측치 수"] = null_count

    high_null_cols = [f"{col} {ratio*100:.1f}%" for col, ratio in null_ratio_map.items() if ratio >= 0.10]
    medium_null_cols = [f"{col} {ratio*100:.1f}%" for col, ratio in null_ratio_map.items() if 0.03 <= ratio < 0.10]
    if high_null_cols:
        issues.append("필수 컬럼 결측 비율이 높습니다: " + ", ".join(high_null_cols))
    elif medium_null_cols:
        issues.append("필수 컬럼 일부에 결측이 있습니다: " + ", ".join(medium_null_cols))

    order_null_cnt = int(null_ratio_map.get("주문번호", 0) * total_rows)
    if order_null_cnt > 0:
        issues.append(
            f"주문번호 결측 {order_null_cnt}건이 감지되었습니다. "
            "같은 날짜·같은 고객의 주문번호가 있으면 자동으로 채우고, "
            "없으면 임의 번호(FILL_XXXXX)를 부여합니다."
        )

    duplicate_orders = 0
    if "주문번호" in df.columns:
        duplicate_orders = int(df["주문번호"].duplicated().sum())
    stats["중복 주문 수"] = duplicate_orders
    if duplicate_orders > 0:
        info_notes.append(
            f"주문번호 중복 {duplicate_orders}건이 감지되었습니다. "
            "동일 주문의 상품 행 분리 구조라면 정상일 수 있습니다."
        )

    invalid_sales = 0
    negative_sales = 0
    if "매출" in df.columns:
        invalid_sales = int(df["매출"].isna().sum())
        negative_sales = int((df["매출"].fillna(0) < 0).sum())
        stats["매출 변환 실패 수"] = invalid_sales
        stats["음수 매출 수"] = negative_sales
    else:
        stats["매출 변환 실패 수"] = 0
        stats["음수 매출 수"] = 0

    if invalid_sales > 0:
        ratio = invalid_sales / total_rows if total_rows else 0.0
        if ratio >= 0.10:
            issues.append(f"매출 숫자 변환 실패가 많습니다: {invalid_sales}건 ({ratio*100:.1f}%)")
        else:
            issues.append(f"매출 숫자 변환 실패가 {invalid_sales}건 있습니다.")

    invalid_datetime = 0
    if "거래일시" in df.columns:
        invalid_datetime = int(df["거래일시"].isna().sum())
        stats["거래일시 변환 실패 수"] = invalid_datetime
    else:
        stats["거래일시 변환 실패 수"] = 0

    if invalid_datetime > 0:
        ratio = invalid_datetime / total_rows if total_rows else 0.0
        if ratio >= 0.10:
            issues.append(f"거래일시 변환 실패가 많습니다: {invalid_datetime}건 ({ratio*100:.1f}%)")
        else:
            issues.append(f"거래일시 변환 실패가 {invalid_datetime}건 있습니다.")

    if negative_sales_mode == "refund" and negative_sales > 0:
        info_notes.append(f"음수 매출 {negative_sales}건은 환불/취소 후보로 간주하여 이후 환불 분석에 활용합니다.")
    elif negative_sales_mode == "exclude" and negative_sales > 0:
        info_notes.append(f"음수 매출 {negative_sales}건은 이상치/비분석 데이터로 보고 현재 분석에서 제외했습니다.")
    elif negative_sales_mode == "keep" and negative_sales > 0:
        info_notes.append(f"음수 매출 {negative_sales}건을 원본 그대로 유지합니다. 환불/정산/오류 여부는 리포트 해석 시 함께 확인하세요.")

    score = 100
    short_period = False
    if "거래일시" in df.columns:
        valid_dates = pd.to_datetime(df["거래일시"], errors="coerce").dropna()
        if len(valid_dates) > 0:
            date_range_days = (valid_dates.max() - valid_dates.min()).days
            if date_range_days < 90:
                short_period = True
                score -= 15
                issues.append(
                    f"데이터 기간이 {date_range_days}일로 3개월 미만입니다. "
                    "이탈 예측 및 구매 주기 분석의 신뢰도가 낮을 수 있습니다."
                )
                info_notes.append("분석 정확도를 높이려면 최소 3개월 이상의 거래 데이터를 권장합니다.")

    if missing_required_cols:
        score -= 40
    for ratio in null_ratio_map.values():
        if ratio >= 0.30:
            score -= 20
        elif ratio >= 0.10:
            score -= 12
        elif ratio >= 0.03:
            score -= 5

    sales_fail_ratio = (invalid_sales / total_rows) if total_rows else 0.0
    dt_fail_ratio = (invalid_datetime / total_rows) if total_rows else 0.0

    if sales_fail_ratio >= 0.30:
        score -= 20
    elif sales_fail_ratio >= 0.10:
        score -= 12
    elif sales_fail_ratio > 0:
        score -= 5
    if dt_fail_ratio >= 0.30:
        score -= 20
    elif dt_fail_ratio >= 0.10:
        score -= 12
    elif dt_fail_ratio > 0:
        score -= 5

    if score >= 90:
        grade = "A"
    elif score >= 75:
        grade = "B"
    elif score >= 55:
        grade = "C"
    else:
        grade = "D"

    return {
        "grade": grade,
        "issues": issues,
        "info_notes": info_notes,
        "stats": stats,
        "refund_count": negative_sales if negative_sales_mode == "refund" else 0,
        "duplicate_order_count": duplicate_orders,
        "score": score,
        "negative_sales_mode": negative_sales_mode,
        "negative_sales_count": negative_sales,
        "short_period": short_period,
    }


def _init_mapping_session_state() -> None:
    for key, value in {
        "mapping_confirmed": False,
        "quality_result": None,
        "df_std": None,
        "negative_sales_mode": "refund",
    }.items():
        if key not in st.session_state:
            st.session_state[key] = value


# ─── Section label helper ────────────────────────────────────────────────────

def _step_label(num: str, title: str, desc: str = ""):
    desc_html = f'<div class="step-section-desc">{desc}</div>' if desc else ""
    st.markdown(
        f"""
        <div style="margin: 22px 0 12px 0;">
          <div class="step-section-label">STEP {num}</div>
          <div class="step-section-title">{title}</div>
          {desc_html}
        </div>
        """,
        unsafe_allow_html=True,
    )


# ─── Render helpers ──────────────────────────────────────────────────────────

def _render_mapping_intro(is_sample: bool) -> None:
    if is_sample:
        st.markdown(
            """
            <div class="card-muted">
              <b>샘플 데이터로 연습 중 👶</b><br/>
              이 단계는 컬럼 이름이 제각각인 CSV 또는 XLSX 파일도 분석할 수 있게
              <b>표준 컬럼</b>으로 맞춰주는 과정입니다.<br/>
              먼저 <b>필수 4개</b>만 맞추면 바로 품질 점검까지 진행할 수 있습니다.
            </div>
            """,
            unsafe_allow_html=True,
        )
        with st.expander("📌 샘플 데이터 추천 매핑표", expanded=True):
            st.dataframe(_mapping_table_for_sample(), use_container_width=True)
            st.caption("드롭다운 기본값이 이미 채워져 있으면 그대로 '확인'만 누르세요.")
    else:
        st.caption(f"필수 4개({DISPLAY_REQUIRED})만 매핑하면 품질 점검까지 진행할 수 있어요.")
        with st.expander("도움말 (필요할 때만 보기)", expanded=False):
            st.markdown("##### 매핑은 이렇게 하시면 됩니다")
            st.caption(
                f"업로드한 파일의 컬럼명을 우리 앱의 표준 컬럼에 1:1로 연결하면 됩니다. "
                f"아래 필수 4개({DISPLAY_REQUIRED})만 지정하면 분석과 품질 점검을 진행할 수 있어요."
            )

            help_col1, help_col2 = st.columns([1.2, 1])

            with help_col1:
                st.markdown("###### 표준 컬럼 설명")
                std_help_df = pd.DataFrame(
                    [
                        ["고객ID", "같은 사람을 구분하는 값", "고객번호, 회원ID, user_id"],
                        ["주문번호", "주문 1건을 구분하는 값", "주문ID, order_id, 거래번호"],
                        ["거래일시", "구매한 날짜 또는 날짜시간", "주문일자, 결제일시, purchase_date"],
                        ["매출", "결제된 금액", "주문금액, 실결제금액, sales, amount"],
                    ],
                    columns=["표준 컬럼", "의미", "예시"],
                )
                st.dataframe(std_help_df, use_container_width=True, hide_index=True)

            with help_col2:
                st.markdown("###### 빠른 판단 기준")
                st.info(
                    "- 사람을 구분하면 **고객ID**\n"
                    "- 주문 1건을 구분하면 **주문번호**\n"
                    "- 날짜/시간이면 **거래일시**\n"
                    "- 돈 금액이면 **매출**"
                )
                st.success(
                    "드롭다운 기본값이 이미 잘 들어가 있으면 그대로 진행하셔도 됩니다.\n\n"
                    "컬럼명이 조금 달라도 실제 의미만 맞으면 괜찮습니다."
                )

            st.markdown("###### 매핑 예시")
            example_df = pd.DataFrame(
                [
                    ["회원번호", "고객ID"],
                    ["주문ID", "주문번호"],
                    ["구매일자", "거래일시"],
                    ["실결제금액", "매출"],
                ],
                columns=["내 파일의 컬럼", "앱 표준 컬럼"],
            )
            st.dataframe(example_df, use_container_width=True, hide_index=True)

            st.caption("예: 파일에 `회원번호 / 주문ID / 구매일자 / 실결제금액` 이 있다면 위처럼 연결하시면 됩니다.")


def _render_mapping_form(cols: list[str], guesses: dict[str, str | None], is_sample: bool):
    with st.form("mapping_form", border=True):
        st.markdown("##### 필수 컬럼 매핑")

        selected: dict[str, str | None] = {}

        def dropdown(label: str, default_col: str | None, key: str) -> str | None:
            options = ["(선택 안함)"] + cols
            index = options.index(default_col) if default_col in cols else 0
            choice = st.selectbox(label, options, index=index, key=key)
            return None if choice == "(선택 안함)" else choice

        req_col_a, req_col_b = st.columns(2)
        req_list = list(CORE_REQUIRED)
        for i, std_col in enumerate(req_list):
            with (req_col_a if i % 2 == 0 else req_col_b):
                selected[std_col] = dropdown(std_col, guesses.get(std_col), key=f"req_{std_col}")

        st.markdown("##### 음수 매출 처리 방식")
        st.caption("음수 매출은 환불/취소/정산조정/입력오류일 수 있습니다.")

        mode_options = ["refund", "exclude", "keep"]
        saved_mode = st.session_state.get("negative_sales_mode", "refund")
        negative_sales_mode = st.radio(
            "음수 매출 처리",
            options=mode_options,
            index=mode_options.index(saved_mode) if saved_mode in mode_options else 0,
            format_func=lambda x: {
                "refund": "환불/취소 후보로 처리",
                "exclude": "분석에서 제외",
                "keep": "원본 그대로 유지",
            }.get(x, x),
            horizontal=True,
            key="negative_sales_mode_radio",
        )

        selected_values = [v for v in selected.values() if v is not None]
        duplicates = sorted({c for c in selected_values if selected_values.count(c) > 1})
        missing_required = [k for k in CORE_REQUIRED if selected.get(k) is None]

        if duplicates:
            st.error(f"중복 매핑이 있습니다: {duplicates}")
        if missing_required:
            st.warning(
                f"필수 컬럼이 아직 비어있어요: {missing_required}"
                if is_sample
                else f"필수 컬럼 누락: {missing_required}"
            )

        st.markdown("<div style='height:4px'></div>", unsafe_allow_html=True)
        c1, c2 = st.columns([1, 1], gap="small")
        back = c1.form_submit_button("← 업로드로 돌아가기", use_container_width=True)
        confirm = c2.form_submit_button("✅ 확인 및 품질 점검", type="primary", use_container_width=True)

    return selected, negative_sales_mode, duplicates, missing_required, back, confirm


def _process_mapping_confirmation(
    df_raw: pd.DataFrame,
    selected: dict[str, str | None],
    duplicates: list[str],
    missing_required: list[str],
    negative_sales_mode: str,
) -> pd.DataFrame | None:
    if duplicates:
        st.error("중복 매핑을 먼저 해결해주세요.")
        st.session_state["mapping_confirmed"] = False
        return None
    if missing_required:
        st.error("필수 4개를 모두 매핑해야 품질 점검을 진행할 수 있어요.")
        st.session_state["mapping_confirmed"] = False
        return None

    rename_map = {src: dst for dst, src in selected.items() if src is not None}

    if "카테고리" not in rename_map.values():
        auto_category_col = _find_category_column(list(df_raw.columns))
        if auto_category_col and auto_category_col not in rename_map:
            rename_map[auto_category_col] = "카테고리"

    try:
        df_mapped = df_raw[list(rename_map.keys())].copy()
        df_mapped.rename(columns=rename_map, inplace=True)
        df_std = _standardize_mapped_df(df_mapped)
        df_std_processed, negative_meta = _apply_negative_sales_mode(df_std, negative_sales_mode)
        quality_result = _assess_data_quality(df_std_processed, negative_sales_mode=negative_sales_mode)
        quality_result["negative_meta"] = negative_meta

        st.session_state["negative_sales_mode"] = negative_sales_mode
        st.session_state["df_std"] = df_std_processed
        st.session_state["quality_result"] = quality_result
        st.session_state["mapping_confirmed"] = True
        st.success("✅ 매핑과 품질 점검이 완료됐어요. 아래에서 결과를 확인하세요.")
        return df_std_processed
    except Exception as e:
        st.session_state["mapping_confirmed"] = False
        st.error("표준화 또는 품질 점검 중 오류가 발생했습니다.")
        st.exception(e)
        return None


# ─── Quality Section ─────────────────────────────────────────────────────────

def render_quality_section(quality_result: dict):
    grade = str(quality_result.get("grade", "D")).upper()
    issues = quality_result.get("issues", []) or []
    info_notes = quality_result.get("info_notes", []) or []
    stats = quality_result.get("stats", {}) or {}
    refund_count = int(quality_result.get("refund_count", 0) or 0)
    score = int(quality_result.get("score", 0) or 0)
    negative_sales_mode = quality_result.get("negative_sales_mode", "refund")
    negative_sales_count = int(quality_result.get("negative_sales_count", 0) or 0)

    color_map = {
        "A": {"main": "#16a34a", "bg": "rgba(22,163,74,0.07)", "border": "rgba(22,163,74,0.22)", "label": "매우 양호"},
        "B": {"main": "#2563eb", "bg": "rgba(37,99,235,0.07)", "border": "rgba(37,99,235,0.22)", "label": "양호"},
        "C": {"main": "#d97706", "bg": "rgba(245,158,11,0.08)", "border": "rgba(245,158,11,0.26)", "label": "주의 필요"},
        "D": {"main": "#dc2626", "bg": "rgba(239,68,68,0.07)", "border": "rgba(239,68,68,0.22)", "label": "개선 필요"},
    }
    theme = color_map.get(grade, color_map["D"])

    mode_label_map = {
        "refund": "환불 후보로 처리",
        "exclude": "분석에서 제외",
        "keep": "원본 그대로 유지",
    }
    guide_map = {
        "A": "필수 컬럼과 형식이 안정적입니다. 현재 상태로 리포트 분석 진행이 가능합니다.",
        "B": "전반적으로 양호합니다. 일부 보정 이슈는 있을 수 있지만 분석 진행이 가능합니다.",
        "C": "주의가 필요합니다. 일부 누락이나 형식 이슈를 함께 고려해 결과를 해석하는 것이 좋습니다.",
        "D": "현재 데이터 상태로는 결과 신뢰도가 낮을 수 있습니다. 매핑 또는 원본 파일을 다시 확인하세요.",
    }

    _step_label("03", "데이터 품질 점검", "표준화된 데이터의 품질 지표와 주요 이슈를 확인합니다.")

    st.markdown(
        f"""
        <div class="quality-header-card" style="
            border: 1px solid {theme['border']};
            background: {theme['bg']};
        ">
            <div style="display:flex; justify-content:space-between; align-items:center;
                        flex-wrap:wrap; gap:14px;">
                <div>
                    <div style="font-size:11px; font-weight:800; color:{theme['main']};
                                letter-spacing:0.08em; text-transform:uppercase; margin-bottom:8px;">
                        DATA QUALITY CHECK
                    </div>
                    <div style="font-size:26px; font-weight:900; color:#1f2937; line-height:1.1;">
                        품질 등급 &nbsp;<span style="color:{theme['main']};">{grade}</span>
                    </div>
                    <div style="font-size:13px; color:#4b5563; margin-top:7px; line-height:1.65;">
                        {theme['label']} · {guide_map.get(grade, "")}
                    </div>
                    <div style="font-size:12px; color:#6b7280; margin-top:5px;">
                        품질 점수 {score} / 100
                    </div>
                </div>
                <div style="
                    min-width:82px; text-align:center;
                    padding:12px 16px; border-radius:18px;
                    background:white; border:1px solid {theme['border']};
                ">
                    <div style="font-size:11px; color:#6b7280; font-weight:700; margin-bottom:4px;">GRADE</div>
                    <div style="font-size:36px; font-weight:900; color:{theme['main']}; line-height:1;">{grade}</div>
                </div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    metric_items = [
        ("전체 행 수", stats.get("전체 행 수", 0)),
        ("필수컬럼 결측치", stats.get("필수컬럼 결측치 수", 0)),
        ("중복 주문", stats.get("중복 주문 수", 0)),
        ("음수 매출", stats.get("음수 매출 수", 0)),
    ]
    m_cols = st.columns(4)
    for i, (label, value) in enumerate(metric_items):
        m_cols[i].markdown(
            f"""
            <div style="
                border: 1px solid rgba(15,23,42,0.07);
                background: white;
                border-radius: 16px;
                padding: 16px 16px 14px;
                box-shadow: 0 2px 10px rgba(15,23,42,0.04);
            ">
                <div style="font-size:11px; color:#6b7280; font-weight:700;
                            text-transform:uppercase; letter-spacing:0.04em;">{label}</div>
                <div style="font-size:22px; font-weight:900; color:#111827; margin-top:8px;">{value:,}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    st.markdown("<div style='height:14px'></div>", unsafe_allow_html=True)

    info_col, issue_col = st.columns([1, 1], gap="large")

    with info_col:
        st.markdown("##### 분석 해석")
        st.markdown(
            f"""
            <div class="info-banner">
                <b>현재 상태</b><br/>{guide_map.get(grade, "")}
            </div>
            """,
            unsafe_allow_html=True,
        )
        if negative_sales_count > 0:
            st.markdown(
                f"""
                <div style="margin-top:10px; border:1px solid rgba(139,92,246,0.18);
                    background:rgba(139,92,246,0.05); border-radius:16px;
                    padding:14px 16px; line-height:1.75; color:#1f2937; font-size:13px;">
                    <b>음수 매출 처리 방식</b><br/>
                    음수 매출 <b>{negative_sales_count}건</b>은 현재
                    <b>{mode_label_map.get(negative_sales_mode, negative_sales_mode)}</b>으로 설정되어 있습니다.
                </div>
                """,
                unsafe_allow_html=True,
            )
        if refund_count > 0:
            st.markdown(
                f"""
                <div style="margin-top:10px; border:1px solid rgba(124,58,237,0.18);
                    background:rgba(124,58,237,0.05); border-radius:16px;
                    padding:14px 16px; line-height:1.75; color:#1f2937; font-size:13px;">
                    <b>환불 분석 활용</b><br/>
                    음수 매출 <b>{refund_count}건</b>은 환불/취소 후보로 보고 이후 환불 분석에 활용합니다.
                </div>
                """,
                unsafe_allow_html=True,
            )
        for note in info_notes:
            st.markdown(
                f"""
                <div style="margin-top:10px; border:1px solid rgba(14,165,233,0.16);
                    background:rgba(14,165,233,0.05); border-radius:14px;
                    padding:12px 14px; color:#334155; line-height:1.65; font-size:13px;">
                    {note}
                </div>
                """,
                unsafe_allow_html=True,
            )

    with issue_col:
        st.markdown("##### 확인된 문제")
        if issues:
            for issue in issues:
                st.markdown(
                    f"""
                    <div style="border:1px solid rgba(239,68,68,0.14);
                        background:rgba(239,68,68,0.04); border-radius:12px;
                        padding:11px 14px; margin-bottom:9px;
                        color:#374151; line-height:1.65; font-size:13px;">
                        {issue}
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
        else:
            st.markdown(
                """
                <div class="success-banner">
                    ✅ 주요 품질 문제는 감지되지 않았습니다.
                </div>
                """,
                unsafe_allow_html=True,
            )

    st.markdown("<div style='height:10px'></div>", unsafe_allow_html=True)
    st.markdown("##### 다음 단계 안내")

    if grade in ("A", "B"):
        st.markdown(
            '<div class="success-banner">매핑과 품질 점검이 완료되었습니다. 아래 버튼으로 리포트 단계로 이동할 수 있습니다.</div>',
            unsafe_allow_html=True,
        )
    elif grade == "C":
        st.markdown(
            '<div class="warn-banner">리포트 진행은 가능하지만, 일부 누락/형식 이슈를 함께 고려해 해석하는 것이 좋습니다.</div>',
            unsafe_allow_html=True,
        )
    else:
        st.markdown(
            '<div class="danger-banner">현재 데이터 상태로는 결과 신뢰도가 낮을 수 있습니다. 매핑 또는 원본 파일을 다시 확인하세요.</div>',
            unsafe_allow_html=True,
        )


# ─── Main step ───────────────────────────────────────────────────────────────

def mapping_step(df_raw: pd.DataFrame):
    st.markdown('<div class="page-title">컬럼 매핑 & 품질 점검</div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="page-subtitle">업로드한 데이터의 컬럼을 표준 컬럼에 연결하고 품질을 확인합니다.</div>',
        unsafe_allow_html=True,
    )
    st.markdown("<div style='height:12px'></div>", unsafe_allow_html=True)

    is_sample = st.session_state.get("data_source") == "sample"
    cols = list(df_raw.columns)
    _init_mapping_session_state()

    _step_label(
        "01",
        "데이터 확인",
        "샘플 데이터를 먼저 확인하고, 다음 단계에서 표준 컬럼으로 맞춰볼게요." if is_sample
        else "업로드한 데이터가 맞는지 확인하세요.",
    )
    st.dataframe(df_raw.head(20), use_container_width=True)

    guesses = _guess_mapping(cols)
    if is_sample:
        hint = get_sample_mapping_hint()
        guesses.update({k: v for k, v in hint.items() if v in cols})

    _step_label(
        "02",
        "컬럼 매핑",
        "업로드 파일 컬럼을 표준 컬럼에 연결해 주세요." if not is_sample
        else "샘플은 기본값이 대부분 자동으로 채워져 있어요.",
    )
    _render_mapping_intro(is_sample)

    selected, negative_sales_mode, duplicates, missing_required, back, confirm = _render_mapping_form(
        cols=cols,
        guesses=guesses,
        is_sample=is_sample,
    )

    if back:
        st.session_state["step"] = 0
        st.rerun()

    if confirm:
        _process_mapping_confirmation(
            df_raw=df_raw,
            selected=selected,
            duplicates=duplicates,
            missing_required=missing_required,
            negative_sales_mode=negative_sales_mode,
        )

    if st.session_state.get("mapping_confirmed") and st.session_state.get("df_std") is not None:
        df_std = st.session_state.get("df_std")
        quality_result = st.session_state.get("quality_result")

        st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)
        st.divider()

        _step_label("02-b", "표준화 결과 미리보기", "매핑 후 변환된 데이터 앞부분을 확인하세요.")
        st.dataframe(df_std.head(20), use_container_width=True)

        if not CategoryMerger.has_category(df_std):
            st.divider()
            _step_label(
                "02-c",
                "카테고리 정보 추가 (선택사항)",
                "제품 정보 파일이 있으면 카테고리를 자동으로 추가할 수 있습니다.",
            )
            merged_df = render_category_merge_section(df_std)
            if merged_df is not None:
                df_std = merged_df
                st.session_state["df_std"] = merged_df

        st.divider()
        render_quality_section(quality_result or {})

        st.divider()
        c1, c2 = st.columns([1, 1], gap="small")
        with c1:
            if st.button("📊 리포트 단계로 이동", use_container_width=True, type="primary"):
                st.session_state["step"] = 2
                st.rerun()
        with c2:
            if st.button("🔄 매핑 다시 확인", use_container_width=True):
                st.info("매핑 값 또는 음수 매출 처리 방식을 수정한 뒤 다시 '확인'을 눌러주세요.")

        if is_sample:
            st.caption("샘플은 연습용입니다. 실제 데이터도 같은 방식으로 매핑하면 됩니다.")

        return df_std

    return None
