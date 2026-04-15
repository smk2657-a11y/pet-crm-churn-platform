import io
from io import BytesIO
from datetime import datetime
from contextlib import contextmanager

import numpy as np
import pandas as pd
import streamlit as st

try:
    from streamlit_extras.stylable_container import stylable_container
except Exception:
    @contextmanager
    def stylable_container(key: str, css_styles: str):
        with st.container():
            yield


STD_REQUIRED = ["고객ID", "주문번호", "거래일시", "매출"]
STD_OPTIONAL = ["카테고리", "구매채널", "온라인채널", "결제수단", "시도"]


def make_sample_data(n_tx: int = 300, seed: int = 7) -> pd.DataFrame:
    rng = np.random.default_rng(seed)

    customers = rng.integers(10000, 20000, size=120)
    cust_ids = rng.choice(customers, size=n_tx, replace=True)

    start = datetime(2024, 1, 1)
    end = datetime(2024, 2, 29)
    dates = pd.to_datetime(
        rng.integers(int(start.timestamp()), int(end.timestamp()), size=n_tx),
        unit="s",
    )

    date_str = np.where(
        rng.random(n_tx) < 0.5,
        dates.strftime("%Y/%m/%d %H:%M"),
        dates.strftime("%Y-%m-%d"),
    )

    order_ids = np.arange(1, n_tx + 1)
    categories = np.array(["사료", "간식", "장난감", "위생용품", "미용"])
    cat = rng.choice(categories, size=n_tx, p=[0.30, 0.30, 0.15, 0.15, 0.10])
    channel = rng.choice(["온라인", "오프라인"], size=n_tx, p=[0.78, 0.22])
    sido = rng.choice(
        ["서울", "부산", "대구", "인천", "광주", "대전", "울산", "경기", "제주"],
        size=n_tx,
    )
    pay = rng.choice(
        ["카드", "현금", "계좌이체", "간편결제"],
        size=n_tx,
        p=[0.55, 0.15, 0.10, 0.20],
    )
    platform = rng.choice(
        ["스마트스토어", "쿠팡", "자사몰", "매장"],
        size=n_tx,
        p=[0.35, 0.35, 0.20, 0.10],
    )

    base = {
        "사료": 32000,
        "간식": 15000,
        "장난감": 22000,
        "위생용품": 18000,
        "미용": 26000,
    }
    amount = np.array([max(1000, int(rng.normal(base[c], base[c] * 0.45))) for c in cat])

    return pd.DataFrame(
        {
            "customer_no": cust_ids.astype(int),
            "order_id": order_ids.astype(int),
            "purchase_date": date_str,
            "total_price": [f"{x:,}" for x in amount],
            "product_group": cat,
            "sales_channel": channel,
            "platform_name": platform,
            "pay_type": pay,
            "region_name": sido,
            "상품명": rng.choice(["사료A", "간식B", "장난감C", "샴푸D", "패드E"], size=n_tx),
        }
    )


def get_sample_mapping_hint() -> dict:
    return {
        "고객ID": "customer_no",
        "주문번호": "order_id",
        "거래일시": "purchase_date",
        "매출": "total_price",
        "카테고리": "product_group",
        "구매채널": "sales_channel",
        "온라인채널": "platform_name",
        "결제수단": "pay_type",
        "시도": "region_name",
    }


def _normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    df.columns = [str(c).strip() for c in df.columns]
    return df


def read_csv_safely(uploaded_file) -> pd.DataFrame:
    def _try_read(enc):
        uploaded_file.seek(0)
        df = pd.read_csv(uploaded_file, encoding=enc, sep=None, engine="python")
        return _normalize_columns(df)

    for enc in ["utf-8", "cp949", None]:
        try:
            return _try_read(enc)
        except Exception:
            continue

    uploaded_file.seek(0)
    df = pd.read_csv(uploaded_file, encoding="cp949")
    return _normalize_columns(df)


def read_excel_safely(uploaded_file) -> pd.DataFrame:
    uploaded_file.seek(0)
    df = pd.read_excel(uploaded_file, engine="openpyxl")
    return _normalize_columns(df)


def read_uploaded_table(uploaded_file) -> pd.DataFrame:
    file_name = (uploaded_file.name or "").lower()
    if file_name.endswith(".csv"):
        return read_csv_safely(uploaded_file)
    if file_name.endswith(".xlsx"):
        return read_excel_safely(uploaded_file)
    raise ValueError("CSV 또는 XLSX 파일만 업로드 가능합니다.")


def get_sample_csv_text(df: pd.DataFrame) -> str:
    buf = io.StringIO()
    df.to_csv(buf, index=False)
    return buf.getvalue()


def get_sample_excel_bytes(df: pd.DataFrame) -> bytes:
    buffer = BytesIO()
    df.to_excel(buffer, index=False, engine="openpyxl")
    return buffer.getvalue()


def _render_page_css():
    st.markdown(
        """
<style>
div[data-testid="stFileUploader"] > label {
    display: none !important;
}

div[data-testid="stFileUploader"] > section {
    padding: 0 !important;
    border: none !important;
    background: transparent !important;
    box-shadow: none !important;
}

div[data-testid="stFileUploaderDropzone"] {
    border-radius: 18px !important;
    border: 1px solid rgba(148,163,184,0.22) !important;
    background: #f8fafc !important;
    padding: 18px !important;
    min-height: 110px !important;
    box-shadow: none !important;
}

/* 카드 유지용: 현재 잘 보이는 key 방식 유지 */
div[data-testid="stVerticalBlockBorderWrapper"].st-key-upload_card,
div[data-testid="stVerticalBlockBorderWrapper"].st-key-sample_card {
    background: linear-gradient(180deg, rgba(255,255,255,0.98) 0%, rgba(248,250,255,0.98) 100%) !important;
    border: 1px solid rgba(15,23,42,0.08) !important;
    border-radius: 24px !important;
    box-shadow: 0 10px 28px rgba(15,23,42,0.05) !important;
}

div[data-testid="stVerticalBlockBorderWrapper"].st-key-upload_card > div,
div[data-testid="stVerticalBlockBorderWrapper"].st-key-sample_card > div {
    padding: 24px 24px 18px 24px !important;
    background: transparent !important;
}

div[data-testid="stFileUploaderDropzone"] > div {
    padding: 0 !important;
}

.upload-card-kicker,
.sample-card-kicker {
    display: inline-block;
    padding: 6px 12px;
    border-radius: 999px;
    font-size: 11px;
    font-weight: 800;
    letter-spacing: .08em;
    text-transform: uppercase;
    margin-bottom: 14px;
    white-space: nowrap;
}

.upload-card-kicker {
    background: rgba(99,102,241,0.10);
    color: #4f46e5;
}

.sample-card-kicker {
    background: rgba(16,185,129,0.10);
    color: #059669;
}

.upload-card-title,
.sample-card-title {
    font-size: 24px;
    font-weight: 900;
    color: #0f172a;
    line-height: 1.22;
    margin-bottom: 10px;
    white-space: nowrap;
}

.upload-card-desc,
.sample-card-desc {
    font-size: 15px;
    color: #64748b;
    line-height: 1.7;
    margin-bottom: 18px;
    white-space: nowrap;
}

.upload-section-title {
    font-size: 16px;
    color: #0f172a;
    font-weight: 800;
    margin-bottom: 12px;
    white-space: nowrap;
}

.upload-guideline-banner {
    margin-top: 12px;
    padding: 12px 14px;
    border-radius: 14px;
    background: rgba(245, 158, 11, 0.10);
    border: 1px solid rgba(245, 158, 11, 0.24);
    color: #92400E;
    font-size: 14px;
    font-weight: 800;
    line-height: 1.6;
    white-space: nowrap;
}

div[data-testid="stButton"] > button,
div[data-testid="stDownloadButton"] > button {
    border-radius: 14px !important;
    min-height: 52px !important;
    font-weight: 800 !important;
    font-size: 16px !important;
    white-space: nowrap !important;
}

div[data-testid="stDownloadButton"] > button {
    background: #ffffff !important;
    border: 1px solid rgba(15,23,42,0.08) !important;
}

div[data-testid="stButton"] > button:hover,
div[data-testid="stDownloadButton"] > button:hover {
    transform: translateY(-1px);
    box-shadow: 0 8px 18px rgba(15,23,42,0.06) !important;
}
</style>
        """,
        unsafe_allow_html=True,
    )


def _render_sidebar_compact_guide():
    with st.sidebar:
        st.markdown(
            """
<div style="
    padding: 16px 16px 14px;
    border-radius: 18px;
    background: #ffffff;
    border: 1px solid rgba(15,23,42,0.06);
    box-shadow: 0 8px 24px rgba(15,23,42,0.04);
    margin-bottom: 14px;
">
  <div style="
      display:inline-block;
      padding: 5px 10px;
      border-radius: 999px;
      background: rgba(99,102,241,0.10);
      color: #4f46e5;
      font-size: 10px;
      font-weight: 800;
      letter-spacing: .08em;
      text-transform: uppercase;
      margin-bottom: 10px;
  ">Guide</div>
  <div style="font-size: 18px; font-weight: 900; color: #0f172a; margin-bottom: 8px;">
    업로드 기준
  </div>
  <div style="font-size: 13px; color: #475569; line-height: 1.75;">
    • CSV / XLSX 지원<br/>
    • 필수 4개 컬럼만 있으면 시작 가능<br/>
    • 3개월 이상 데이터 권장
  </div>
</div>
            """,
            unsafe_allow_html=True,
        )


def _set_short_period_state(span_days: int, message: str):
    st.session_state["upload_period_days"] = span_days
    st.session_state["upload_short_period_warning"] = True
    st.session_state["upload_short_period_message"] = message


def _clear_short_period_state():
    st.session_state["upload_period_days"] = None
    st.session_state["upload_short_period_warning"] = False
    st.session_state["upload_short_period_message"] = ""


def _check_short_period_warning(df: pd.DataFrame):
    if df is None or not isinstance(df, pd.DataFrame) or df.empty:
        _clear_short_period_state()
        return

    date_candidates = [
        "거래일시", "purchase_date", "purchase_datetime", "order_date", "date",
        "주문일", "구매일", "거래일", "created_at", "timestamp",
    ]
    date_col = next((c for c in date_candidates if c in df.columns), None)
    if date_col is None:
        _clear_short_period_state()
        return

    dates = pd.to_datetime(df[date_col], errors="coerce").dropna()
    if dates.empty:
        _clear_short_period_state()
        return

    span_days = int((dates.max() - dates.min()).days)
    if span_days < 90:
        message = (
            f"⚠️ 업로드한 데이터 기간이 약 {span_days}일입니다. "
            "3개월 미만 데이터는 재구매 주기 및 이탈 분석 품질이 낮아질 수 있습니다."
        )
        _set_short_period_state(span_days, message)
    else:
        _clear_short_period_state()


def _render_upload_header():
    st.markdown(
        """
<div class="upload-card-kicker">UPLOAD WORKSPACE</div>
<div class="upload-card-title">데이터 업로드 후 바로 분석을 시작하세요</div>
<div class="upload-card-desc">CSV 또는 XLSX 파일을 넣으면 컬럼 매핑, 품질 점검, 리포트 순서로 자연스럽게 이어집니다.</div>
        """,
        unsafe_allow_html=True,
    )


def _render_sample_header():
    st.markdown(
        """
<div class="sample-card-kicker">RECOMMENDED</div>
<div class="sample-card-title">샘플데이터로 먼저 둘러보기</div>
<div class="sample-card-desc">샘플데이터를 통해 권장 양식을 확인하고 매핑을 연습할 수 있습니다.</div>
        """,
        unsafe_allow_html=True,
    )


def load_csv_or_sample_sidebar() -> pd.DataFrame | None:
    _render_sidebar_compact_guide()
    _render_page_css()

    sample_df = make_sample_data()
    sample_csv = get_sample_csv_text(sample_df)
    sample_xlsx = get_sample_excel_bytes(sample_df)

    hero_col, sample_col = st.columns([1.7, 1.0], gap="large")

    with hero_col:
        with stylable_container(key="upload_card", css_styles="""
        {
            background: linear-gradient(180deg, rgba(255,255,255,0.98) 0%, rgba(248,250,255,0.98) 100%);
            border: 1px solid rgba(15,23,42,0.08);
            border-radius: 24px;
            padding: 24px 24px 18px 24px;
            box-shadow: 0 10px 28px rgba(15,23,42,0.05);
            margin-bottom: 8px;
        }
        """):
            _render_upload_header()
            st.markdown('<div class="upload-section-title">파일 업로드</div>', unsafe_allow_html=True)

            up = st.file_uploader(
                "CSV 또는 XLSX 파일 선택",
                type=["csv", "xlsx"],
                help="업로드 후 다음 단계에서 컬럼을 매핑합니다.",
                label_visibility="collapsed",
            )
            st.markdown(
                '<div class="upload-guideline-banner">⚠️ 재구매 주기와 이탈 분석 품질을 위해 3개월 이상의 데이터 사용을 권장합니다.</div>',
                unsafe_allow_html=True,
            )

            if up is not None:
                try:
                    st.session_state.data_source = "upload"
                    df = read_uploaded_table(up)
                    _check_short_period_warning(df)

                    if st.session_state.get("upload_short_period_warning"):
                        st.warning(st.session_state.get("upload_short_period_message", ""))

                    st.success("업로드가 완료되었습니다. 다음 단계에서 컬럼 매핑을 진행하세요.")
                    return df
                except Exception as e:
                    st.error(f"파일을 읽는 중 오류가 발생했습니다: {e}")
                    return None

    with sample_col:
        with stylable_container(key="sample_card", css_styles="""
        {
            background: linear-gradient(180deg, rgba(255,255,255,0.98) 0%, rgba(248,250,255,0.98) 100%);
            border: 1px solid rgba(15,23,42,0.08);
            border-radius: 24px;
            padding: 24px 24px 18px 24px;
            box-shadow: 0 10px 28px rgba(15,23,42,0.05);
            margin-bottom: 8px;
        }
        """):
            _render_sample_header()

            if st.button("✨ 샘플 데이터로 바로 시작", type="primary", use_container_width=True):
                st.session_state.data_source = "sample"
                _check_short_period_warning(sample_df)
                st.success("샘플 데이터를 불러왔습니다. 다음 단계에서 컬럼 매핑을 진행하세요.")
                return sample_df

            st.download_button(
                "📥 샘플 CSV 다운로드",
                data=sample_csv,
                file_name="sample_data.csv",
                mime="text/csv",
                use_container_width=True,
            )
            st.download_button(
                "📥 샘플 XLSX 다운로드",
                data=sample_xlsx,
                file_name="sample_data.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True,
            )

    return None
