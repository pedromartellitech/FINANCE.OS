"""Componentes comuns; todos os textos interpolados no HTML são escapados."""

from __future__ import annotations

from html import escape
from pathlib import Path

import altair as alt
import pandas as pd
import streamlit as st

from financeos.domain import brl

ROOT = Path(__file__).resolve().parent.parent


def style():
    st.html("<style>" + (ROOT / "assets/style.css").read_text(encoding="utf-8") + "</style>")


def safe(value):
    return escape(str(value), quote=True)


def brand():
    st.html(
        '<div class="fo-brand"><div class="fo-logo">ƒ</div><div><div class="fo-brand-name">finance<span>os.</span></div><div class="fo-brand-sub">CLAREZA PARA CRESCER</div></div></div>'
    )


def heading(title, subtitle, eyebrow="Seu espaço financeiro"):
    st.html(
        f'<div class="fo-eyebrow">{safe(eyebrow)}</div><h1 class="fo-title">{safe(title)}</h1><p class="fo-subtitle">{safe(subtitle)}</p>'
    )


def section(title, caption=""):
    st.html(
        f'<div class="fo-heading">{safe(title)}</div><div class="fo-caption">{safe(caption)}</div>'
    )


def kpi(label, value, note="", tone="", primary=False, icon="↗"):
    st.html(
        f'<div class="fo-kpi {"primary" if primary else ""}"><div class="fo-kpi-label">{safe(label)}<span class="fo-kpi-icon" aria-hidden="true">{safe(icon)}</span></div><div class="fo-kpi-value">{safe(value)}</div><div class="fo-kpi-note {safe(tone)}">{safe(note)}</div></div>'
    )


def empty(title, note, icon="◈"):
    st.html(
        f'<div class="fo-empty"><div class="fo-empty-icon" aria-hidden="true">{safe(icon)}</div><div class="fo-empty-title">{safe(title)}</div><div class="fo-empty-note">{safe(note)}</div></div>'
    )


def activity_row(title, subtitle, amount, *, tone="", badge="", badge_tone=""):
    st.html(
        f'<div class="fo-row"><div><div class="fo-row-title">{safe(title)}</div><div class="fo-row-sub">{safe(subtitle)}</div></div><div><div class="fo-row-amount fo-{safe(tone)}">{safe(amount)}</div>{f'<span class="fo-badge {safe(badge_tone)}">{safe(badge)}</span>' if badge else ""}</div></div>'
    )


def themed(chart, height=260):
    return (
        chart.properties(height=height)
        .configure_view(strokeWidth=0)
        .configure_axis(
            labelColor="#B0C4BE",
            titleColor="#B0C4BE",
            gridColor="#30474B",
            domain=False,
            tickSize=0,
            labelPadding=10,
            title=None,
            labelFontSize=10,
        )
        .configure_legend(
            labelColor="#B9CCC5", title=None, orient="bottom", symbolType="circle", labelFontSize=10
        )
        .configure(background="transparent")
    )


def balance_chart(rows, *, forecast=False, height=270):
    data = pd.DataFrame(rows)
    data["Dia"] = pd.to_datetime(data["date"])
    data["Saldo"] = data["balance"] / 100
    data["Valor"] = data["balance"].map(brl)
    base = alt.Chart(data).encode(
        x=alt.X("Dia:T", axis=alt.Axis(format="%d/%m", tickCount=6)),
        y=alt.Y("Saldo:Q", scale=alt.Scale(zero=False)),
        tooltip=[alt.Tooltip("Dia:T", format="%d/%m/%Y"), "Valor:N"],
    )
    area = base.mark_area(color="#FFAA56", opacity=0.10, interpolate="linear")
    line = base.mark_line(
        color="#FFAA56",
        strokeWidth=2.5,
        interpolate="linear",
        strokeDash=[6, 4] if forecast else [1, 0],
    )
    st.altair_chart(themed(area + line, height), width="stretch")


def category_chart(rows):
    groups = {}
    for r in rows:
        if r["kind"] == "Despesa":
            name = r["category"]
            groups[name] = groups.get(name, 0) + r["amount_cents"]
    if not groups:
        empty(
            "Sem despesas no período", "As categorias aparecem aqui após seu primeiro lançamento."
        )
        return
    data = pd.DataFrame(
        [{"Categoria": k, "Total": v / 100, "Valor": brl(v)} for k, v in groups.items()]
    )
    chart = (
        alt.Chart(data)
        .mark_arc(innerRadius=64, outerRadius=94, padAngle=0.035, cornerRadius=4)
        .encode(
            theta=alt.Theta("Total:Q"),
            color=alt.Color(
                "Categoria:N",
                scale=alt.Scale(
                    range=[
                        "#FFAA56",
                        "#5DE4AF",
                        "#63D7ED",
                        "#FFD166",
                        "#FF8178",
                        "#BD9FFF",
                        "#65CDB4",
                        "#F4D593",
                    ]
                ),
            ),
            tooltip=["Categoria:N", "Valor:N"],
        )
    )
    st.altair_chart(themed(chart, 270), width="stretch")


def transaction_frame(rows):
    return pd.DataFrame(
        [
            {
                "ID": r["id"],
                "Data": r["date"],
                "Descrição": r["description"],
                "Tipo": r["kind"],
                "Valor": brl(r["amount_cents"]),
                "Conta": r["account"],
                "Destino": r.get("peer_account") or "—",
                "Categoria": r.get("category") or "Transferência",
                "Status": r["status"],
                "Forma": r["method"],
            }
            for r in rows
        ]
    )
