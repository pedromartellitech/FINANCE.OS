from datetime import date

import pandas as pd
import streamlit as st

from financeos.domain import brl, input_money, money_to_cents, today
from financeos.forms import METHODS, execute, pick_account, pick_category
from financeos.ui import empty, heading, kpi


def render(service, month):
    heading(
        "Antecipe. Organize. Respire.",
        "Contas a pagar e a receber, parcelamentos e recorrências em uma única agenda.",
        "Operação / Agenda financeira",
    )
    pending = service.obligations(status="Pendente")
    overdue = [r for r in pending if r["due_date"] < today().isoformat()]
    cols = st.columns(3)
    with cols[0]:
        kpi(
            "A pagar",
            brl(sum(r["amount_cents"] for r in pending if r["kind"] == "Despesa")),
            "Todos os vencimentos pendentes",
            "bad",
            icon="↗",
        )
    with cols[1]:
        kpi(
            "A receber",
            brl(sum(r["amount_cents"] for r in pending if r["kind"] == "Receita")),
            "Todos os vencimentos pendentes",
            "good",
            icon="↙",
        )
    with cols[2]:
        kpi(
            "Em atraso",
            str(len(overdue)),
            "Compromissos anteriores a hoje",
            "bad" if overdue else "good",
            icon="◷",
        )
    st.write("")
    list_tab, new_tab = st.tabs(["Compromissos", "＋ Agendar compromisso"])
    with new_tab:
        kind = (
            st.segmented_control(
                "Direção", ["Despesa", "Receita"], default="Despesa", key="bill_kind"
            )
            or "Despesa"
        )
        mode = st.radio(
            "Forma do agendamento",
            ["Único", "Parcelado", "Recorrente"],
            horizontal=True,
            key="bill_mode",
        )
        with st.form("bill_new_form"):
            description = st.text_input("Descrição", max_chars=160, key="bill_description")
            c1, c2 = st.columns(2)
            with c1:
                amount = st.text_input(
                    "Valor total (R$)" if mode == "Parcelado" else "Valor por ocorrência (R$)",
                    placeholder="0,00",
                    key="bill_amount",
                )
                account = pick_account(service, "bill_account")
                category = pick_category(service, kind, "bill_category_" + kind)
            with c2:
                due = st.date_input("Primeiro vencimento", today(), key="bill_due")
                count = st.number_input(
                    "Número de parcelas" if mode == "Parcelado" else "Número de ocorrências",
                    min_value=1,
                    max_value=60,
                    value=1 if mode == "Único" else 6,
                    disabled=mode == "Único",
                    key="bill_count_" + mode,
                )
                st.caption(
                    "Parcelado divide o total sem perder centavos. Recorrente repete o valor por mês, até o número informado."
                )
            notes = st.text_area("Observações (opcional)", max_chars=1000, key="bill_notes")
            if st.form_submit_button(
                "Criar agendamento",
                type="primary",
                width="stretch",
                disabled=not account or not category,
            ):
                execute(
                    lambda: service.create_obligations(
                        description,
                        kind,
                        money_to_cents(amount),
                        account,
                        category,
                        due,
                        int(count),
                        mode,
                        notes,
                    ),
                    "Compromisso(s) agendado(s). O saldo muda somente na baixa.",
                )
    with list_tab:
        a, b, c = st.columns(3)
        with a:
            kind_filter = st.selectbox(
                "Direção", ["Todas", "Despesa", "Receita"], key="bill_filter_kind"
            )
        with b:
            status = st.selectbox(
                "Situação",
                ["Pendente", "Liquidado", "Cancelado", "Todas"],
                key="bill_filter_status",
            )
        with c:
            period = st.selectbox(
                "Vencimentos", ["Todos", "Mês selecionado", "Em atraso"], key="bill_filter_period"
            )
        rows = service.obligations(
            None if kind_filter == "Todas" else kind_filter, None if status == "Todas" else status
        )
        if period == "Mês selecionado":
            rows = [r for r in rows if r["due_date"].startswith(month)]
        if period == "Em atraso":
            rows = [
                r for r in rows if r["due_date"] < today().isoformat() and r["status"] == "Pendente"
            ]
        if not rows:
            empty(
                "Agenda livre para estes filtros",
                "Seus compromissos aparecerão aqui quando forem cadastrados.",
            )
            return
        frame = pd.DataFrame(
            [
                {
                    "ID": r["id"],
                    "Vencimento": r["due_date"],
                    "Descrição": r["description"],
                    "Tipo": r["kind"],
                    "Valor": brl(r["amount_cents"]),
                    "Situação": "Em atraso"
                    if r["status"] == "Pendente" and r["due_date"] < today().isoformat()
                    else r["status"],
                    "Parcela": f"{r['installment']}/{r['total_installments']}",
                    "Conta": r["account"],
                    "Categoria": r["category"],
                }
                for r in rows
            ]
        )
        st.dataframe(frame, hide_index=True, width="stretch", height=340)
        actionable = [r for r in rows if r["status"] != "Cancelado"]
        if not actionable:
            return
        with st.expander("Dar baixa, editar ou desfazer", expanded=True):
            mapping = {r["id"]: r for r in actionable}
            bill_id = st.selectbox(
                "Compromisso",
                list(mapping),
                format_func=lambda i: (
                    f"#{i} · {mapping[i]['description']} · {brl(mapping[i]['amount_cents'])}"
                ),
                key="bill_action_id",
            )
            row = mapping[bill_id]
            if row["status"] == "Liquidado":
                st.caption(
                    "Desfazer a baixa estorna o lançamento vinculado e reabre o compromisso."
                )
                confirm = st.checkbox(
                    "Confirmo que quero desfazer esta baixa", key="bill_reopen_confirm"
                )
                if st.button("Desfazer baixa", disabled=not confirm, key="bill_reopen"):
                    execute(
                        lambda: service.reopen_obligation(bill_id),
                        "Baixa desfeita e compromisso reaberto.",
                    )
            else:
                with st.form(f"settle_{bill_id}"):
                    x, y = st.columns(2)
                    with x:
                        paid_on = st.date_input(
                            "Data da baixa",
                            today(),
                            max_value=today(),
                            key=f"settle_date_{bill_id}",
                        )
                    with y:
                        method = st.selectbox(
                            "Forma da baixa", METHODS, key=f"settle_method_{bill_id}"
                        )
                    st.caption(
                        f"A baixa registra {'uma entrada' if row['kind'] == 'Receita' else 'uma saída'} de {brl(row['amount_cents'])} em {row['account']}."
                    )
                    if st.form_submit_button(
                        "Confirmar recebimento"
                        if row["kind"] == "Receita"
                        else "Confirmar pagamento",
                        type="primary",
                        width="stretch",
                    ):
                        execute(
                            lambda: service.settle_obligation(bill_id, paid_on, method),
                            "Baixa registrada uma única vez e saldo atualizado.",
                        )
                with st.expander("Corrigir este compromisso"):
                    with st.form(f"bill_edit_{bill_id}"):
                        description = st.text_input("Descrição", row["description"], max_chars=160)
                        x, y = st.columns(2)
                        with x:
                            amount = st.text_input("Valor (R$)", input_money(row["amount_cents"]))
                            account = pick_account(
                                service, f"bill_edit_account_{bill_id}", default=row["account_id"]
                            )
                        with y:
                            due = st.date_input("Vencimento", date.fromisoformat(row["due_date"]))
                            category = pick_category(
                                service,
                                row["kind"],
                                f"bill_edit_category_{bill_id}",
                                row["category_id"],
                            )
                        notes = st.text_area("Observações", row["notes"], max_chars=1000)
                        st.caption("A alteração vale apenas para a ocorrência selecionada.")
                        if st.form_submit_button(
                            "Salvar correção", disabled=not account or not category
                        ):
                            execute(
                                lambda: service.update_obligation(
                                    bill_id,
                                    description,
                                    money_to_cents(amount),
                                    account,
                                    category,
                                    due,
                                    notes,
                                )
                            )
                confirm = st.checkbox(
                    "Confirmo o cancelamento deste compromisso",
                    key=f"bill_cancel_confirm_{bill_id}",
                )
                if st.button("Cancelar compromisso", disabled=not confirm, key="bill_cancel"):
                    execute(
                        lambda: service.cancel_obligation(bill_id),
                        "Compromisso cancelado. O saldo não foi alterado.",
                    )
