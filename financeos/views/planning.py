from datetime import date, timedelta

import pandas as pd
import streamlit as st

from financeos.domain import brl, input_money, money_to_cents, today
from financeos.forms import execute, pick_category
from financeos.ui import empty, heading, section


def render(service, month):
    heading(
        "Planos que viram progresso.",
        "Limites para o presente, metas para o que você quer construir.",
        "Organização / Planejamento",
    )
    budgets_tab, goals_tab = st.tabs(["Orçamentos do mês", "Metas e reservas"])
    with budgets_tab:
        budgets = service.budgets(month)
        if budgets:
            for b in budgets:
                with st.container(border=True):
                    l, r = st.columns([3, 1])
                    with l:
                        section(
                            b["category"],
                            f"{brl(b['spent_cents'])} utilizados de {brl(b['limit_cents'])}",
                        )
                    ratio = b["spent_cents"] / b["limit_cents"]
                    with r:
                        st.markdown(f"**{ratio:.0%}**")
                    st.progress(min(ratio, 1.0))
                    if ratio > 1:
                        st.warning(
                            f"Limite ultrapassado em {brl(b['spent_cents'] - b['limit_cents'])}."
                        )
                    else:
                        st.caption(f"Ainda disponíveis: {brl(b['limit_cents'] - b['spent_cents'])}")
        else:
            empty(
                "Planeje seu mês com intenção",
                "Defina um limite para cada categoria que você quer acompanhar.",
            )
        st.subheader("Definir ou atualizar limite")
        with st.form("budget_form"):
            l, r = st.columns(2)
            with l:
                category = pick_category(service, "Despesa", "budget_category")
            with r:
                amount = st.text_input(
                    "Limite mensal (R$)", placeholder="0,00", key="budget_amount"
                )
            st.caption(
                f"O limite será aplicado ao mês {month}. Salvar a mesma categoria atualiza o limite existente."
            )
            if st.form_submit_button(
                "Salvar orçamento", type="primary", width="stretch", disabled=not category
            ):
                execute(lambda: service.save_budget(category, month, money_to_cents(amount)))
        if budgets:
            with st.expander("Remover limite"):
                mapping = {b["id"]: b["category"] for b in budgets}
                bid = st.selectbox("Orçamento", list(mapping), format_func=mapping.get)
                if st.button("Remover este limite", key="budget_delete"):
                    execute(
                        lambda: service.delete_budget(bid),
                        "Limite removido. As despesas foram preservadas.",
                    )
    with goals_tab:
        st.info(
            "As metas acompanham valores reservados manualmente. Aportes e retiradas aqui não movimentam o saldo das contas; use Transferência para mover dinheiro entre contas."
        )
        goals = service.goals()
        if goals:
            columns = st.columns(2)
            for i, g in enumerate(goals):
                with columns[i % 2]:
                    with st.container(border=True):
                        section(
                            g["name"],
                            f"Até {date.fromisoformat(g['due_date']).strftime('%d/%m/%Y')}",
                        )
                        st.subheader(brl(g["saved_cents"]))
                        ratio = g["saved_cents"] / g["target_cents"]
                        st.progress(min(ratio, 1.0))
                        st.caption(
                            f"{ratio:.0%} de {brl(g['target_cents'])} · Faltam {brl(max(g['target_cents'] - g['saved_cents'], 0))}"
                        )
                        if ratio >= 1:
                            st.success("Meta alcançada.")
        else:
            empty(
                "Qual é o seu próximo objetivo?",
                "Crie uma reserva de emergência, planeje um equipamento ou acompanhe um sonho.",
            )
        l, r = st.columns(2)
        with l:
            st.subheader("Criar meta")
            with st.form("goal_new"):
                name = st.text_input("Nome da meta", max_chars=80, key="goal_name")
                amount = st.text_input("Objetivo (R$)", placeholder="0,00", key="goal_target")
                due = st.date_input("Data desejada", today() + timedelta(days=180), key="goal_due")
                if st.form_submit_button("Criar meta", type="primary", width="stretch"):
                    execute(lambda: service.create_goal(name, money_to_cents(amount), due))
        with r:
            if goals:
                st.subheader("Atualizar reserva")
                mapping = {g["id"]: g for g in goals}
                gid = st.selectbox(
                    "Meta",
                    list(mapping),
                    format_func=lambda i: mapping[i]["name"],
                    key="goal_entry_id",
                )
                with st.form(f"goal_entry_{gid}"):
                    direction = st.selectbox(
                        "Operação", ["Aporte", "Retirada"], key="goal_entry_direction"
                    )
                    amount = st.text_input(
                        "Valor (R$)", placeholder="0,00", key="goal_entry_amount"
                    )
                    on_date = st.date_input(
                        "Data", today(), max_value=today(), key="goal_entry_date"
                    )
                    notes = st.text_input("Observação", max_chars=1000, key="goal_entry_notes")
                    if st.form_submit_button("Registrar reserva", width="stretch"):
                        execute(
                            lambda: service.contribute_goal(
                                gid,
                                money_to_cents(amount) * (1 if direction == "Aporte" else -1),
                                on_date,
                                notes,
                            ),
                            "Reserva atualizada. O saldo das contas não foi alterado.",
                        )
                with st.expander("Histórico da meta"):
                    rows = service.goal_entries(gid)
                    st.dataframe(
                        pd.DataFrame(
                            [
                                {
                                    "Data": r["date"],
                                    "Valor": brl(r["amount_cents"]),
                                    "Observação": r["notes"],
                                }
                                for r in rows
                            ]
                        ),
                        hide_index=True,
                        width="stretch",
                    ) if rows else st.caption("Ainda não há aportes.")
