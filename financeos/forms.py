"""Formulários compartilhados com validação e confirmação explícita de estornos."""

from __future__ import annotations

from datetime import date

import streamlit as st

from financeos.domain import FinanceError, brl, input_money, money_to_cents, today

METHODS = [
    "Pix",
    "Cartão de débito",
    "Cartão de crédito",
    "Boleto",
    "Transferência bancária",
    "Dinheiro",
    "Outro",
]


def execute(action, message="Alteração salva.", clear_keys=None):
    try:
        result = action()
        st.session_state["flash"] = message
        if clear_keys:
            st.session_state["clear_on_rerun"] = clear_keys
        st.rerun()
        return result
    except FinanceError as exc:
        st.error(str(exc))


def pick_account(service, key, label="Conta financeira", default=None):
    rows = service.accounts(active_only=True)
    if not rows:
        st.info("Cadastre uma conta financeira em Contas e categorias para começar.")
        return None
    mapping = {r["id"]: r for r in rows}
    keys = list(mapping)
    return st.selectbox(
        label,
        keys,
        index=keys.index(default) if default in keys else 0,
        format_func=lambda i: f"{mapping[i]['name']} · {brl(mapping[i]['balance_cents'])}",
        key=key,
    )


def pick_category(service, kind, key, default=None):
    rows = service.categories(kind)
    if not rows:
        st.info("Cadastre uma categoria ativa para este tipo.")
        return None
    mapping = {r["id"]: r["name"] for r in rows}
    keys = list(mapping)
    return st.selectbox(
        "Categoria",
        keys,
        index=keys.index(default) if default in keys else 0,
        format_func=mapping.get,
        key=key,
    )


def transaction_form(service, prefix="new", existing=None):
    row = existing
    if row:
        kind = row["kind"]
        st.caption(
            f"Editando {kind.lower()} #{row['id']}. Para mudar as contas, estorne e registre novamente."
        )
    else:
        kind = st.segmented_control(
            "Tipo de movimentação",
            ["Receita", "Despesa", "Transferência"],
            default="Despesa",
            key=f"{prefix}_kind",
        )
        kind = kind or "Despesa"
    with st.form(f"{prefix}_form"):
        description = st.text_input(
            "Descrição",
            value=row["description"] if row else "",
            max_chars=160,
            placeholder="Ex.: projeto de site para cliente",
            key=f"{prefix}_description",
        )
        c1, c2 = st.columns(2)
        with c1:
            amount = st.text_input(
                "Valor (R$)",
                value=input_money(row["amount_cents"]) if row else "",
                placeholder="0,00",
                key=f"{prefix}_amount",
            )
            if row:
                account = row["account_id"]
                st.caption(f"Conta de origem: {row['account']}")
            else:
                account = pick_account(
                    service,
                    f"{prefix}_account",
                    "Conta de origem" if kind == "Transferência" else "Conta financeira",
                )
            category = (
                pick_category(
                    service, kind, f"{prefix}_{kind}_category", row["category_id"] if row else None
                )
                if kind != "Transferência"
                else None
            )
        with c2:
            on_date = st.date_input(
                "Data da movimentação",
                value=date.fromisoformat(row["date"]) if row else today(),
                max_value=today(),
                key=f"{prefix}_date",
            )
            peer = (
                (
                    row["peer_account_id"]
                    if row
                    else pick_account(service, f"{prefix}_peer", "Conta de destino")
                )
                if kind == "Transferência"
                else None
            )
            method = st.selectbox(
                "Forma de pagamento",
                METHODS,
                index=METHODS.index(row["method"]) if row and row["method"] in METHODS else 0,
                key=f"{prefix}_method",
            )
        notes = st.text_area(
            "Observações (opcional)",
            value=row["notes"] if row else "",
            max_chars=1000,
            height=75,
            key=f"{prefix}_notes",
        )
        st.caption(
            "Transferências não compõem receitas e despesas. Movimentações são realizadas; valores futuros entram na agenda."
        )
        submit = st.form_submit_button(
            "Salvar alterações" if row else "Registrar movimentação",
            type="primary",
            width="stretch",
            disabled=not account or (kind != "Transferência" and not category),
        )
        if submit:

            def save():
                cents = money_to_cents(amount)
                if row:
                    return service.update_transaction(
                        row["id"], description, cents, category, on_date, method, notes
                    )
                return service.create_transaction(
                    description, kind, cents, account, category, on_date, method, notes, peer
                )

            execute(
                save,
                "Movimentação salva. Os indicadores já foram atualizados.",
                clear_keys=[f"{prefix}_description", f"{prefix}_amount", f"{prefix}_notes"]
                if not row
                else None,
            )


@st.dialog("Nova movimentação", width="large")
def new_transaction_dialog(service):
    transaction_form(service, "quick")


@st.dialog("Editar movimentação", width="large")
def edit_transaction_dialog(service, row):
    transaction_form(service, f"edit_{row['id']}", row)
