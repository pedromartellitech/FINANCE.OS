from datetime import date

import streamlit as st

from financeos.domain import brl, month_bounds
from financeos.forms import edit_transaction_dialog, execute, transaction_form
from financeos.portability import export_csv
from financeos.ui import empty, heading, transaction_frame


def render(service, month):
    heading(
        "Cada movimento, no seu lugar.",
        "Registre, encontre e corrija entradas, saídas e transferências.",
        "Operação / Movimentações",
    )
    history, new = st.tabs(["Extrato", "＋ Nova movimentação"])
    with new:
        transaction_form(service, "tx_new")
    with history:
        c1, c2, c3 = st.columns([2, 1, 1])
        with c1:
            search = st.text_input(
                "Buscar no extrato", placeholder="Descrição ou observação", key="tx_search"
            )
        with c2:
            kind = st.selectbox(
                "Tipo", ["Todos", "Receita", "Despesa", "Transferência"], key="tx_filter_kind"
            )
        with c3:
            accounts = service.accounts()
            mapping = {0: "Todas as contas", **{a["id"]: a["name"] for a in accounts}}
            account = st.selectbox(
                "Conta", list(mapping), format_func=mapping.get, key="tx_filter_account"
            )
        start, end = month_bounds(month)
        c1, c2 = st.columns([2, 1])
        with c1:
            all_time = st.checkbox("Buscar em todo o histórico", key="tx_all_time")
        with c2:
            reversed_ = st.checkbox("Incluir estornados", key="tx_reversed")
        rows = service.transactions(
            None if all_time else start,
            None if all_time else end,
            kind if kind != "Todos" else None,
            account or None,
            search,
            reversed_,
        )
        if rows:
            st.dataframe(transaction_frame(rows), hide_index=True, width="stretch", height=360)
            st.caption(
                f"{len(rows)} movimentação(ões) encontrada(s). Transferências são internas e não alteram o resultado."
            )
            st.download_button(
                "↓ Exportar receitas e despesas (CSV)",
                export_csv(rows),
                "finance-os-extrato.csv",
                "text/csv",
                key="export_tx_csv",
            )
            active = [r for r in rows if r["status"] == "Ativo"]
            if active:
                with st.expander("Editar ou estornar uma movimentação"):
                    mapping = {r["id"]: r for r in active}
                    tx_id = st.selectbox(
                        "Movimentação",
                        list(mapping),
                        format_func=lambda i: (
                            f"#{i} · {mapping[i]['description']} · {brl(mapping[i]['amount_cents'])}"
                        ),
                        key="tx_action_id",
                    )
                    row = mapping[tx_id]
                    if row["obligation_id"]:
                        st.info(
                            "Movimentação gerada pela agenda. Use Desfazer baixa na agenda para corrigi-la."
                        )
                    else:
                        l, r = st.columns(2)
                        with l:
                            if st.button("Editar dados", width="stretch", key="edit_tx"):
                                edit_transaction_dialog(service, row)
                        with r:
                            confirm = st.checkbox("Confirmo o estorno", key="confirm_reverse_tx")
                            if st.button(
                                "Estornar movimentação",
                                disabled=not confirm,
                                width="stretch",
                                key="reverse_tx",
                            ):
                                execute(
                                    lambda: service.reverse_transaction(tx_id),
                                    "Movimentação estornada. O histórico foi preservado.",
                                )
        else:
            empty(
                "Nenhuma movimentação encontrada",
                "Ajuste os filtros ou registre uma nova entrada, saída ou transferência.",
            )
