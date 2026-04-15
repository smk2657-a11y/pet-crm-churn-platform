from __future__ import annotations

from datetime import datetime
from html import escape
from typing import Any

import pandas as pd


def _safe(v: Any) -> str:
    if v is None:
        return "-"
    return escape(str(v))


def _fmt_int(v: Any) -> str:
    try:
        return f"{int(float(v)):,}"
    except Exception:
        return "-"


def _fmt_currency(v: Any) -> str:
    try:
        return f"₩{int(round(float(v))):,}"
    except Exception:
        return "-"


def _fmt_pct(v: Any, multiply_100: bool = False) -> str:
    try:
        x = float(v)
        if multiply_100:
            x *= 100
        return f"{x:.1f}%"
    except Exception:
        return "-"


def _build_colgroup(show: pd.DataFrame, table_class: str) -> str:
    if table_class == "ml-wide" and len(show.columns) == 8:
        widths = ["10%", "12%", "12%", "8%", "14%", "14%", "18%", "12%"]
        return "<colgroup>" + "".join(f'<col style="width:{w};">' for w in widths) + "</colgroup>"
    return ""


def _df_to_html_table(
    df: pd.DataFrame | None,
    max_rows: int = 20,
    table_class: str = "",
) -> str:
    if df is None or not isinstance(df, pd.DataFrame) or df.empty:
        return '<div class="empty-box">데이터 없음</div>'

    show = df.head(max_rows).copy()

    for col in show.columns:
        show[col] = show[col].map(lambda x: "-" if pd.isna(x) else str(x))

    headers = "".join(f"<th>{_safe(col)}</th>" for col in show.columns)
    rows = []
    for _, row in show.iterrows():
        cells = []
        for idx, value in enumerate(row.tolist()):
            cls = ""
            if table_class == "ml-wide" and len(show.columns) == 8:
                if idx in (0, 1, 2, 3, 4, 5, 7):
                    cls = ' class="nowrap-cell"'
                elif idx == 6:
                    cls = ' class="action-cell"'
            cells.append(f"<td{cls}>{_safe(value)}</td>")
        rows.append(f"<tr>{''.join(cells)}</tr>")

    body = "".join(rows)
    colgroup = _build_colgroup(show, table_class)

    return f"""
    <div class="table-card {table_class}">
      <table class="{table_class}">
        {colgroup}
        <thead><tr>{headers}</tr></thead>
        <tbody>{body}</tbody>
      </table>
    </div>
    """


def build_report_html(
    title: str,
    user_name: str,
    run_name: str,
    kpi: dict,
    category_df: pd.DataFrame | None = None,
    segment_df: pd.DataFrame | None = None,
    customer_df: pd.DataFrame | None = None,
    ml_df: pd.DataFrame | None = None,
    refund_df: pd.DataFrame | None = None,
    inventory_df: pd.DataFrame | None = None,
    forecast: dict | None = None,
    selected_sections: dict | None = None,
    negative_sales_mode: str = "refund",
) -> str:
    forecast = forecast or {}
    selected_sections = selected_sections or {
        "overview": True,
        "segment": True,
        "category": True,
        "risk": True,
        "ml": True,
        "refund": True,
        "forecast": True,
        "inventory": True,
    }

    generated_at = datetime.now().strftime("%Y-%m-%d %H:%M")

    mode_label = {
        "refund": "환불/취소 후보로 처리",
        "exclude": "분석에서 제외",
        "keep": "원본 그대로 유지",
    }.get(negative_sales_mode, negative_sales_mode)

    mode_desc = {
        "refund": "음수 매출은 환불/취소 후보로 간주하여 환불 분석에 반영했습니다.",
        "exclude": "음수 매출은 현재 분석에서 제외한 뒤 지표를 계산했습니다.",
        "keep": "음수 매출을 원본 그대로 유지한 상태로 지표를 계산했습니다.",
    }.get(negative_sales_mode, "")

    ml_total = len(ml_df) if isinstance(ml_df, pd.DataFrame) and not ml_df.empty else 0
    if isinstance(ml_df, pd.DataFrame) and not ml_df.empty:
        risk_col = "위험상태" if "위험상태" in ml_df.columns else None
        prob_col = "이탈확률" if "이탈확률" in ml_df.columns else None
        value_col = "예상방어가치" if "예상방어가치" in ml_df.columns else ("예상방어매출" if "예상방어매출" in ml_df.columns else None)

        immediate_cnt = int((ml_df[risk_col] == "즉시 관리").sum()) if risk_col else int(kpi.get("critical_customers", 0))
        manage_cnt = int((ml_df[risk_col] == "관리 필요").sum()) if risk_col else int(kpi.get("high_risk_customers", 0))
        avg_prob = "-"
        if prob_col:
            try:
                avg_prob = _fmt_pct(pd.to_numeric(ml_df[prob_col].astype(str).str.replace("%", "", regex=False), errors="coerce").mean())
            except Exception:
                avg_prob = "-"
        elif "avg_risk" in kpi:
            avg_prob = _fmt_pct(kpi.get("avg_risk", 0))

        protection_value = _fmt_currency(pd.to_numeric(ml_df[value_col], errors="coerce").fillna(0).sum()) if value_col else _fmt_currency(kpi.get("protection_value", 0))
    else:
        immediate_cnt = int(kpi.get("critical_customers", 0))
        manage_cnt = int(kpi.get("high_risk_customers", 0))
        avg_prob = _fmt_pct(kpi.get("avg_risk", 0))
        protection_value = _fmt_currency(kpi.get("protection_value", 0))

    overview_html = ""
    if selected_sections.get("overview", True):
        overview_html = f"""
        <section class="section">
          <div class="section-title">개요</div>

          <div class="kpi-grid">
            <div class="kpi-card blue">
              <div class="kpi-label">총 고객 수</div>
              <div class="kpi-value">{_fmt_int(kpi.get("total_customers", 0))}</div>
            </div>
            <div class="kpi-card red">
              <div class="kpi-label">즉시 관리 고객</div>
              <div class="kpi-value">{_fmt_int(immediate_cnt)}</div>
            </div>
            <div class="kpi-card yellow">
              <div class="kpi-label">관리 필요 고객</div>
              <div class="kpi-value">{_fmt_int(manage_cnt)}</div>
            </div>
            <div class="kpi-card purple">
              <div class="kpi-label">예상 방어가치</div>
              <div class="kpi-value">{protection_value}</div>
            </div>
          </div>

          <div class="notice-card">
            <div class="notice-title">음수 매출 처리 방식</div>
            <div class="notice-strong">{_safe(mode_label)}</div>
            <div class="notice-text">{_safe(mode_desc)}</div>
          </div>
        </section>
        """

    segment_html = ""
    if selected_sections.get("segment", True):
        segment_html = f"""
        <section class="section">
          <div class="section-title">세그먼트</div>
          {_df_to_html_table(segment_df, max_rows=20)}
        </section>
        """

    category_html = ""
    if selected_sections.get("category", True):
        category_html = f"""
        <section class="section">
          <div class="section-title">카테고리</div>
          {_df_to_html_table(category_df, max_rows=20)}
        </section>
        """

    risk_html = ""
    if selected_sections.get("risk", True):
        risk_html = f"""
        <section class="section">
          <div class="section-title">이탈리스크</div>
          {_df_to_html_table(customer_df, max_rows=20)}
        </section>
        """

    ml_html = ""
    if selected_sections.get("ml", True):
        ml_html = f"""
        <section class="section">
          <div class="section-title">방어 우선 고객</div>

          <div class="kpi-grid ml-kpi-grid">
            <div class="kpi-card red">
              <div class="kpi-label">즉시 관리 고객</div>
              <div class="kpi-value">{_fmt_int(immediate_cnt)}</div>
            </div>
            <div class="kpi-card yellow">
              <div class="kpi-label">관리 필요 고객</div>
              <div class="kpi-value">{_fmt_int(manage_cnt)}</div>
            </div>
            <div class="kpi-card blue">
              <div class="kpi-label">평균 이탈확률</div>
              <div class="kpi-value">{avg_prob}</div>
            </div>
            <div class="kpi-card purple">
              <div class="kpi-label">상위 고객 수</div>
              <div class="kpi-value">{_fmt_int(ml_total)}</div>
            </div>
          </div>

          <div class="notice-card neutral">
            <div class="notice-title">방어 우선 고객 해석</div>
            <div class="notice-strong">최근 실매출 기반 예상 방어가치</div>
            <div class="notice-text">표의 예상방어가치는 최근 실매출 흐름과 이탈확률을 함께 반영한 운영 우선순위 지표입니다. 즉시 관리 고객과 관리 필요 고객을 먼저 확인해 CRM 액션 우선순위를 결정하는 데 활용합니다.</div>
          </div>

          <div class="subsection-title">상위 이탈위험 고객</div>
          {_df_to_html_table(ml_df, max_rows=12, table_class="ml-wide")}
        </section>
        """

    refund_html = ""
    if selected_sections.get("refund", True):
        refund_html = f"""
        <section class="section">
          <div class="section-title">환불 분석</div>
          {_df_to_html_table(refund_df, max_rows=20)}
        </section>
        """

    forecast_html = ""
    if selected_sections.get("forecast", True):
        forecast_html = f"""
        <section class="section">
          <div class="section-title">매출전망</div>
          <div class="forecast-card">
            <div class="forecast-label">{_safe(forecast.get("label", "전망"))}</div>
            <div class="forecast-value">{_fmt_currency(forecast.get("value", 0))}</div>
          </div>
        </section>
        """

    inventory_html = ""
    if selected_sections.get("inventory", True):
        inventory_html = f"""
        <section class="section">
          <div class="section-title">재고전략</div>
          {_df_to_html_table(inventory_df, max_rows=20)}
        </section>
        """

    html = f"""
    <!DOCTYPE html>
    <html lang="ko">
    <head>
      <meta charset="utf-8" />
      <title>{_safe(title)}</title>
      <style>
        @page {{
          size: A4 landscape;
          margin: 10mm;
        }}

        * {{
          box-sizing: border-box;
        }}

        body {{
          font-family: "Apple SD Gothic Neo", "Malgun Gothic", "NanumGothic", sans-serif;
          color: #111827;
          background: #ffffff;
          margin: 0;
        }}

        .header {{
          padding: 18px 22px;
          border: 1px solid #e5e7eb;
          border-radius: 18px;
          background: linear-gradient(135deg, #f8fafc 0%, #eef2ff 100%);
          margin-bottom: 16px;
        }}

        .title {{
          font-size: 28px;
          font-weight: 800;
          margin-bottom: 8px;
        }}

        .sub {{
          font-size: 12px;
          color: #6b7280;
          line-height: 1.6;
        }}

        .meta {{
          margin-top: 10px;
          display: grid;
          grid-template-columns: repeat(3, 1fr);
          gap: 8px;
        }}

        .meta-item {{
          background: white;
          border: 1px solid #e5e7eb;
          border-radius: 12px;
          padding: 8px 10px;
          font-size: 11px;
        }}

        .section {{
          margin-bottom: 18px;
          page-break-inside: avoid;
        }}

        .section-title {{
          font-size: 18px;
          font-weight: 800;
          margin-bottom: 10px;
          padding-left: 10px;
          border-left: 5px solid #6366f1;
        }}

        .subsection-title {{
          font-size: 15px;
          font-weight: 800;
          margin: 14px 0 8px 0;
        }}

        .kpi-grid {{
          display: grid;
          grid-template-columns: repeat(4, 1fr);
          gap: 10px;
          margin-bottom: 12px;
        }}

        .kpi-card {{
          border-radius: 16px;
          padding: 14px;
          border: 1px solid #e5e7eb;
          background: #ffffff;
          min-height: 86px;
        }}

        .kpi-card.red {{ background: #fff1f2; border-color: #fecdd3; }}
        .kpi-card.yellow {{ background: #fffbeb; border-color: #fde68a; }}
        .kpi-card.blue {{ background: #eff6ff; border-color: #bfdbfe; }}
        .kpi-card.purple {{ background: #f5f3ff; border-color: #ddd6fe; }}

        .kpi-label {{
          font-size: 11px;
          color: #6b7280;
          margin-bottom: 8px;
          font-weight: 700;
        }}

        .kpi-value {{
          font-size: 22px;
          font-weight: 800;
          letter-spacing: -0.02em;
        }}

        .notice-card {{
          border: 1px solid #ddd6fe;
          background: #f5f3ff;
          border-radius: 16px;
          padding: 14px;
        }}

        .notice-card.neutral {{
          border-color: #dbeafe;
          background: #eff6ff;
        }}

        .notice-title {{
          font-size: 11px;
          color: #7c3aed;
          font-weight: 800;
          margin-bottom: 5px;
        }}

        .notice-card.neutral .notice-title {{
          color: #2563eb;
        }}

        .notice-strong {{
          font-size: 14px;
          font-weight: 800;
          margin-bottom: 4px;
        }}

        .notice-text {{
          font-size: 12px;
          color: #4b5563;
          line-height: 1.6;
        }}

        .forecast-card {{
          border: 1px solid #bfdbfe;
          background: #eff6ff;
          border-radius: 18px;
          padding: 18px;
        }}

        .forecast-label {{
          color: #2563eb;
          font-weight: 800;
          margin-bottom: 8px;
        }}

        .forecast-value {{
          font-size: 30px;
          font-weight: 900;
        }}

        .table-card {{
          width: 100%;
          border: 1px solid #e5e7eb;
          border-radius: 16px;
          overflow: hidden;
          background: white;
        }}

        table {{
          width: 100%;
          min-width: 100%;
          border-collapse: collapse;
          table-layout: fixed;
          font-size: 10px;
        }}

        thead {{
          background: #f3f4f6;
        }}

        th, td {{
          border-bottom: 1px solid #e5e7eb;
          padding: 6px 8px;
          text-align: left;
          vertical-align: top;
          word-break: break-word;
          overflow-wrap: anywhere;
        }}

        th {{
          font-weight: 800;
          font-size: 9.5px;
        }}

        tbody tr:nth-child(even) {{
          background: #fafafa;
        }}

        .ml-wide table {{
          table-layout: fixed;
          width: 100%;
          min-width: 100%;
          font-size: 9.3px;
        }}

        .ml-wide th,
        .ml-wide td {{
          padding: 5px 6px;
        }}

        .ml-wide .nowrap-cell {{
          white-space: nowrap;
          word-break: normal;
          overflow-wrap: normal;
        }}

        .ml-wide .action-cell {{
          white-space: normal;
          word-break: keep-all;
          overflow-wrap: break-word;
          line-height: 1.25;
          font-size: 8.8px;
        }}

        .empty-box {{
          border: 1px dashed #d1d5db;
          background: #f9fafb;
          border-radius: 14px;
          padding: 18px;
          color: #6b7280;
          font-size: 12px;
        }}
      </style>
    </head>
    <body>
      <div class="header">
        <div class="title">{_safe(title)}</div>
        <div class="sub">플랫폼 화면 스타일을 반영한 분석 리포트 PDF</div>
        <div class="meta">
          <div class="meta-item"><b>사용자</b><br>{_safe(user_name)}</div>
          <div class="meta-item"><b>저장 이름</b><br>{_safe(run_name)}</div>
          <div class="meta-item"><b>생성 시각</b><br>{_safe(generated_at)}</div>
        </div>
      </div>

      {overview_html}
      {segment_html}
      {category_html}
      {risk_html}
      {ml_html}
      {refund_html}
      {forecast_html}
      {inventory_html}
    </body>
    </html>
    """
    return html
