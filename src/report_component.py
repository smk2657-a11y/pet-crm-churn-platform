import pandas as pd
import streamlit as st
import plotly.express as px
import plotly.graph_objects as go

PLOT_FONT = "Pretendard, Inter, Apple SD Gothic Neo, Malgun Gothic, sans-serif"

COLORS = {
    "primary": "#4F46E5",
    "info": "#0EA5E9",
    "success": "#10B981",
    "warning": "#F59E0B",
    "danger": "#EF4444",
    "text": "#0F172A",
    "subtext": "#64748B",
    "grid": "rgba(148,163,184,0.14)",
    "border": "rgba(15,23,42,0.08)",
}

CHART_PALETTE = ["#4F46E5", "#0EA5E9", "#10B981", "#F59E0B", "#EF4444", "#8B5CF6"]


def _apply_plot_theme(fig, height: int = 420):
    fig.update_layout(
        template="plotly_white",
        height=height,
        margin=dict(l=16, r=44, t=46, b=18),
        paper_bgcolor="white",
        plot_bgcolor="white",
        font=dict(family=PLOT_FONT, size=12, color=COLORS["text"]),
        colorway=CHART_PALETTE,
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.02,
            xanchor="right",
            x=1,
            bgcolor="rgba(255,255,255,0.86)",
            bordercolor=COLORS["border"],
            borderwidth=1,
            font=dict(size=11, color=COLORS["subtext"]),
        ),
        hoverlabel=dict(
            bgcolor="white",
            bordercolor=COLORS["border"],
            font=dict(color=COLORS["text"], family=PLOT_FONT, size=12),
        ),
        xaxis=dict(showgrid=True, gridcolor=COLORS["grid"], zeroline=False, tickfont=dict(color=COLORS["subtext"])),
        yaxis=dict(showgrid=True, gridcolor=COLORS["grid"], zeroline=False, tickfont=dict(color=COLORS["subtext"])),
    )
    return fig


def section_header(title: str, desc: str | None = None, kicker: str | None = None):
    kicker_html = f'<div class="section-kicker">{kicker}</div>' if kicker else ''
    desc_html = f'<div class="section-desc">{desc}</div>' if desc else ''
    st.markdown(
        f"""
        <div style="margin:6px 0 14px 0;">
          {kicker_html}
          <div class="section-title">{title}</div>
          {desc_html}
        </div>
        """,
        unsafe_allow_html=True,
    )


def metric_card(label: str, value: str, foot: str = ""):
    st.markdown(
        f"""
        <div class="kpi-shell">
          <div class="kpi-label">{label}</div>
          <div class="kpi-value">{value}</div>
          <div class="kpi-foot">{foot}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def insight_box(title: str, bullets: list[str], tone: str = "info"):
    tone_map = {
        "info": "rgba(37,99,235,0.06)",
        "warn": "rgba(217,119,6,0.08)",
        "danger": "rgba(220,38,38,0.07)",
        "success": "rgba(22,163,74,0.06)",
    }
    tone_color = tone_map.get(tone, tone_map["info"])
    bullet_html = ''.join(f'<li>{b}</li>' for b in bullets)
    st.markdown(
        f"""
        <div class="insight-panel" style="background:{tone_color};">
          <div style="font-size:16px; font-weight:900; color:#0F172A;">{title}</div>
          <ul class="bullet-list">{bullet_html}</ul>
        </div>
        """,
        unsafe_allow_html=True,
    )


def action_card(title: str, body: str, tag: str | None = None):
    tag_html = f'<span class="metric-pill">{tag}</span>' if tag else ''
    st.markdown(
        f"""
        <div class="action-card">
          <div style="display:flex; justify-content:space-between; gap:10px; align-items:center; flex-wrap:wrap;">
            <div class="action-title">{title}</div>
            {tag_html}
          </div>
          <div class="action-body">{body}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def chart_card(title: str, fig, desc: str | None = None, height: int = 420):
    fig = _apply_plot_theme(fig, height=height)
    st.markdown(
        f"""
        <div class="chart-shell">
          <div class="chart-head">
            <div class="chart-head-left">
              <div class="chart-title">{title}</div>
              <div class="chart-desc">{desc or ''}</div>
            </div>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.plotly_chart(
        fig,
        use_container_width=True,
        config={"displaylogo": False, "responsive": True, "modeBarButtonsToRemove": ["lasso2d", "select2d", "autoScale2d"]},
    )


def bar_chart(df: pd.DataFrame, x: str, y: str, color: str | None = None, orientation: str = "v"):
    fig = px.bar(
        df,
        x=x if orientation == "v" else y,
        y=y if orientation == "v" else x,
        color=color,
        orientation=orientation,
        color_discrete_sequence=CHART_PALETTE,
    )
    fig.update_traces(
        texttemplate="%{x}" if orientation == "h" else "%{y}",
        textposition="outside",
        cliponaxis=False,
    )
    return _apply_plot_theme(fig)


def donut_chart(df: pd.DataFrame, names: str, values: str):
    fig = px.pie(df, names=names, values=values, hole=0.58, color_discrete_sequence=CHART_PALETTE)
    fig.update_traces(textposition="inside", textinfo="percent+label")
    return _apply_plot_theme(fig)


def scatter_chart(df: pd.DataFrame, x: str, y: str, color: str | None = None, size: str | None = None):
    fig = px.scatter(df, x=x, y=y, color=color, size=size, opacity=0.78, color_discrete_sequence=CHART_PALETTE)
    fig.update_traces(marker=dict(line=dict(width=0.5, color="white")))
    return _apply_plot_theme(fig)


def line_chart(df: pd.DataFrame, x: str, y: str, color: str | None = None):
    fig = px.line(df, x=x, y=y, color=color, markers=True, color_discrete_sequence=CHART_PALETTE)
    return _apply_plot_theme(fig)


def table_block(df: pd.DataFrame, caption: str | None = None, height: int = 320):
    if caption:
        st.markdown(f'<div class="table-caption">{caption}</div>', unsafe_allow_html=True)
    st.dataframe(df, use_container_width=True, hide_index=True, height=height)


def gauge_card(value: float, title: str, reference: float = 70):
    fig = go.Figure(
        go.Indicator(
            mode="gauge+number",
            value=value,
            title={"text": f"<b>{title}</b>", "font": {"size": 22, "color": COLORS["text"], "family": PLOT_FONT}},
            number={"suffix": "점", "font": {"size": 42, "color": COLORS["text"], "family": PLOT_FONT}},
            gauge={
                "axis": {"range": [0, 100], "tickwidth": 1, "tickcolor": "#CBD5E1", "tickfont": {"size": 12, "color": "#94A3B8", "family": PLOT_FONT}},
                "bar": {"color": COLORS["primary"], "thickness": 0.72},
                "bgcolor": "white",
                "borderwidth": 0,
                "steps": [
                    {"range": [0, 40], "color": "#DCFCE7"},
                    {"range": [40, 70], "color": "#FEF3C7"},
                    {"range": [70, 100], "color": "#FEE2E2"},
                ],
                "threshold": {"line": {"color": COLORS["danger"], "width": 3}, "thickness": 0.85, "value": reference},
            },
        )
    )
    fig.update_layout(template="plotly_white", height=300, margin=dict(l=20, r=70, t=60, b=10), paper_bgcolor="white", font=dict(family=PLOT_FONT))
    return fig
