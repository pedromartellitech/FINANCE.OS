from datetime import date

import altair as alt
import pandas as pd
import streamlit as st

from financeos.domain import add_months, brl, month_bounds
from financeos.portability import export_csv
from financeos.reporting import html_report
from financeos.ui import category_chart, empty, heading, kpi, section, themed


def render(service, month):
    heading(
        "Números que contam uma história.",
        "Compare períodos e transforme seu histórico em decisões mais claras.",
        "Análise / Relatórios",
    )
    summary = service.summary(month)
    a, b, c = st.columns(3)
    with a:
        kpi("Receitas realizadas", brl(summary["income"]), "Regime de caixa", "good", icon="↙")
    with b:
        kpi("Despesas realizadas", brl(summary["expense"]), "Regime de caixa", "bad", icon="↗")
    with c:
        kpi(
            "Taxa de resultado",
            f"{summary['savings_rate']:.1f}%" if summary["savings_rate"] is not None else "—",
            "Resultado dividido pelas receitas",
            icon="%",
        )
    st.write("")
    rows = []
    first = date.fromisoformat(month + "-01")
    for offset in range(-5, 1):
        m = add_months(first, offset).strftime("%Y-%m")
        s = service.summary(m)
        for kind, key in [("Receitas", "income"), ("Despesas", "expense")]:
            rows.append({"Mês": m, "Tipo": kind, "Total": s[key] / 100, "Valor": brl(s[key])})
    with st.container(border=True):
        section(
            "O panorama dos últimos seis meses",
            "Receitas e despesas realizadas; transferências ficam fora do resultado",
        )
        chart = (
            alt.Chart(pd.DataFrame(rows))
            .mark_bar(cornerRadiusTopLeft=4, cornerRadiusTopRight=4, size=19)
            .encode(
                x=alt.X("Mês:N", sort=None),
                xOffset="Tipo:N",
                y="Total:Q",
                color=alt.Color(
                    "Tipo:N",
                    scale=alt.Scale(domain=["Receitas", "Despesas"], range=["#5DE4AF", "#FFAA56"]),
                ),
                tooltip=["Mês:N", "Tipo:N", "Valor:N"],
            )
        )
        st.altair_chart(themed(chart, 290), width="stretch")
    start, end = month_bounds(month)
    txs = service.transactions(start, end)
    l, r = st.columns(2)
    with l:
        with st.container(border=True):
            section("Despesas por categoria")
            category_chart(txs)
    with r:
        section("Detalhamento de despesas")
        groups = {}
        for tx in txs:
            if tx["kind"] == "Despesa":
                groups[tx["category"]] = groups.get(tx["category"], 0) + tx["amount_cents"]
        if groups:
            st.dataframe(
                [
                    {
                        "Categoria": k,
                        "Valor": brl(v),
                        "Participação": f"{v / summary['expense']:.1%}",
                    }
                    for k, v in sorted(groups.items(), key=lambda x: -x[1])
                ],
                hide_index=True,
                width="stretch",
            )
        else:
            empty("Sem despesas neste período", "Selecione outro mês para consultar seu histórico.")
    st.divider()
    section(
        "Leve seus números com você",
        "O relatório HTML pode ser aberto no navegador e impresso ou salvo como PDF.",
    )
    a, b = st.columns(2)
    with a:
        st.download_button(
            "↓ Extrato do mês (CSV)",
            export_csv(txs),
            f"finance-os-{month}.csv",
            "text/csv",
            width="stretch",
            key="report_csv",
        )
    with b:
        st.download_button(
            "↓ Relatório para impressão (HTML)",
            html_report(service, month),
            f"finance-os-relatorio-{month}.html",
            "text/html",
            width="stretch",
            key="report_html",
        )
