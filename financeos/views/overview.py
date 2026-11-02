from datetime import date, timedelta

import streamlit as st

from financeos.domain import add_months, brl, month_bounds, today
from financeos.forms import new_transaction_dialog
from financeos.ui import activity_row, balance_chart, category_chart, empty, heading, kpi, section


def render(service, month):
    left, right = st.columns([4, 1], vertical_alignment="center")
    with left:
        heading(
            "Seu dinheiro, em perspectiva.",
            "Uma visão clara do que entrou, do que saiu e do que vem pela frente.",
            f"{service.workspace()} / Visão geral",
        )
    with right:
        if st.button("＋ Movimentação", type="primary", width="stretch"):
            new_transaction_dialog(service)
    summary = service.summary(month)
    start, end = month_bounds(month)
    prev = add_months(date.fromisoformat(start), -1).strftime("%Y-%m")
    previous = service.summary(prev)
    columns = st.columns(4)
    items = [
        (
            "Saldo disponível",
            brl(summary["balance"]),
            "Todas as contas · saldo de hoje",
            "",
            True,
            "◈",
        ),
        (
            "Entradas do período",
            brl(summary["income"]),
            f"{brl(summary['income'] - previous['income'])} em relação ao mês anterior",
            "good" if summary["income"] >= previous["income"] else "bad",
            False,
            "↙",
        ),
        (
            "Saídas do período",
            brl(summary["expense"]),
            "Despesas realizadas · sem transferências",
            "bad",
            False,
            "↗",
        ),
        (
            "Resultado do período",
            brl(summary["result"]),
            "Entradas menos saídas",
            "good" if summary["result"] >= 0 else "bad",
            False,
            "≈",
        ),
    ]
    for column, item in zip(columns, items):
        with column:
            kpi(*item)
    pending = service.obligations(status="Pendente")
    if summary["overdue_count"]:
        st.html(
            f'<div class="fo-alert">◷ Você tem <strong>{summary["overdue_count"]} compromisso(s) em atraso</strong>. A agenda permite registrar a baixa ou corrigir o vencimento.</div>'
        )
    else:
        st.write("")
    l, r = st.columns([1.85, 1], gap="medium")
    with l:
        with st.container(border=True):
            section(
                "O ritmo do seu caixa", "Saldo consolidado ao final de cada dia · valores em reais"
            )
            effective_end = min(end, today().isoformat())
            if start <= effective_end:
                balance_chart(service.daily_flow(start, effective_end), height=282)
            else:
                empty(
                    "Este período ainda não começou",
                    "Consulte a projeção para acompanhar os compromissos futuros.",
                )
    with r:
        with st.container(border=True):
            section("Para onde foi", "Despesas por categoria no período selecionado")
            category_chart(service.transactions(start, end))
    l, r = st.columns([1.85, 1], gap="medium")
    with l:
        with st.container(border=True):
            section("Últimas movimentações", "Seu histórico recente no período selecionado")
            rows = service.transactions(start, end)[:5]
            if not rows:
                empty(
                    "Seu próximo passo começa aqui",
                    "Cadastre uma conta e registre sua primeira movimentação.",
                )
            for tx in rows:
                direction = (
                    "+ " if tx["kind"] == "Receita" else ("− " if tx["kind"] == "Despesa" else "↔ ")
                )
                activity_row(
                    tx["description"],
                    f"{date.fromisoformat(tx['date']).strftime('%d/%m')} · {tx['category'] or 'Transferência'} · {tx['account']}",
                    direction + brl(tx["amount_cents"]),
                    tone="green"
                    if tx["kind"] == "Receita"
                    else ("red" if tx["kind"] == "Despesa" else "purple"),
                )
    with r:
        with st.container(border=True):
            section("No seu radar", "Próximos vencimentos e compromissos em atraso")
            if not pending:
                empty("Tudo em dia", "Seus compromissos agendados aparecerão aqui.", "✓")
            for bill in pending[:4]:
                overdue = bill["due_date"] < today().isoformat()
                label = (
                    "Em atraso"
                    if overdue
                    else ("A receber" if bill["kind"] == "Receita" else "A pagar")
                )
                activity_row(
                    bill["description"],
                    date.fromisoformat(bill["due_date"]).strftime("%d/%m/%Y"),
                    brl(bill["amount_cents"]),
                    badge=label,
                    badge_tone="bad" if overdue else "good" if bill["kind"] == "Receita" else "",
                )
    st.write("")
    l, r = st.columns([1.85, 1], gap="medium")
    with l:
        with st.container(border=True):
            section(
                "Um olhar para os próximos 30 dias",
                "Projeção com os compromissos cadastrados; atrasados entram no primeiro dia",
            )
            projection = service.forecast()
            balance_chart(projection, forecast=True, height=180)
            st.caption(
                f"Saldo no fim da projeção: {brl(projection[-1]['balance'])}. Não inclui receitas ou despesas ainda não cadastradas."
            )
    with r:
        with st.container(border=True):
            section("Planejamento em andamento", "Limites do mês selecionado")
            budgets = service.budgets(month)
            if not budgets:
                empty(
                    "Dê um destino ao seu dinheiro", "Defina limites por categoria em Planejamento."
                )
            for b in budgets[:3]:
                ratio = b["spent_cents"] / b["limit_cents"]
                st.caption(f"{b['category']} · {brl(b['spent_cents'])} / {brl(b['limit_cents'])}")
                st.progress(min(ratio, 1.0))
                if ratio > 1:
                    st.caption("Limite ultrapassado")
