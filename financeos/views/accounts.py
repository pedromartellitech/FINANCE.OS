import streamlit as st

from financeos.domain import ACCOUNT_TYPES, brl, money_to_cents
from financeos.forms import execute
from financeos.ui import empty, heading, safe


def render(service, month):
    heading(
        "Uma casa para cada valor.",
        "Organize contas e categorias sem perder o histórico das suas movimentações.",
        "Organização / Contas e categorias",
    )
    accounts_tab, categories_tab = st.tabs(["Contas financeiras", "Categorias"])
    with accounts_tab:
        accounts = service.accounts()
        if accounts:
            columns = st.columns(3)
            for i, a in enumerate(accounts):
                with columns[i % 3]:
                    st.html(
                        f'<div class="fo-account"><div class="fo-account-label">{safe(a["name"])}</div><small>{safe(a["type"])} · {"Ativa" if a["active"] else "Arquivada"}</small><h3>{safe(brl(a["balance_cents"]))}</h3><small>Saldo inicial: {safe(brl(a["opening_cents"]))}</small></div>'
                    )
            st.caption(
                f"Saldo consolidado: {brl(sum(a['balance_cents'] for a in accounts))}. Contas arquivadas continuam no saldo e no histórico."
            )
        else:
            empty(
                "Comece pela sua primeira conta",
                "Use o saldo que você tem antes das movimentações que serão registradas.",
            )
        l, r = st.columns(2)
        with l:
            st.subheader("Adicionar conta")
            with st.form("account_create"):
                name = st.text_input(
                    "Nome da conta",
                    max_chars=80,
                    placeholder="Ex.: Conta principal",
                    key="account_name",
                )
                kind = st.selectbox("Tipo de conta", ACCOUNT_TYPES, key="account_type")
                opening = st.text_input("Saldo inicial (R$)", "0,00", key="account_opening")
                st.caption(
                    "Pode ser negativo. O saldo inicial não é uma receita. Depois do cadastro, ajustes são feitos por movimentações."
                )
                if st.form_submit_button("Criar conta", type="primary", width="stretch"):
                    execute(
                        lambda: service.create_account(
                            name, kind, money_to_cents(opening, allow_negative=True)
                        ),
                        "Conta criada. Você já pode registrar movimentações.",
                    )
        with r:
            if accounts:
                st.subheader("Editar conta")
                mapping = {a["id"]: a for a in accounts}
                aid = st.selectbox(
                    "Conta para editar",
                    list(mapping),
                    format_func=lambda i, options=mapping: options[i]["name"],
                    key="account_edit_id",
                )
                row = mapping[aid]
                with st.form(f"account_edit_{aid}"):
                    name = st.text_input("Nome", row["name"], max_chars=80)
                    kind = st.selectbox(
                        "Tipo", ACCOUNT_TYPES, index=ACCOUNT_TYPES.index(row["type"])
                    )
                    active = st.toggle("Conta ativa", value=bool(row["active"]))
                    st.caption(
                        "Arquivar preserva todo o histórico. Compromissos pendentes precisam ser resolvidos antes."
                    )
                    if st.form_submit_button("Salvar conta", width="stretch"):
                        execute(lambda: service.update_account(aid, name, kind, active))
    with categories_tab:
        rows = service.categories(active_only=False)
        st.dataframe(
            [
                {
                    "ID": r["id"],
                    "Nome": r["name"],
                    "Tipo": r["kind"],
                    "Cor": r["color"],
                    "Ativa": "Sim" if r["active"] else "Não",
                }
                for r in rows
            ],
            hide_index=True,
            width="stretch",
            height=300,
        )
        l, r = st.columns(2)
        with l:
            st.subheader("Nova categoria")
            with st.form("category_create"):
                name = st.text_input("Nome da categoria", max_chars=60, key="cat_name")
                kind = st.selectbox("Tipo", ["Receita", "Despesa"], key="cat_kind")
                color = st.color_picker("Cor", "#FFAA56", key="cat_color")
                if st.form_submit_button("Adicionar categoria", type="primary", width="stretch"):
                    execute(lambda: service.save_category(name, kind, color))
        with r:
            st.subheader("Editar categoria")
            mapping = {c["id"]: c for c in rows}
            cid = st.selectbox(
                "Categoria para editar",
                list(mapping),
                format_func=lambda i, options=mapping: (
                    f"{options[i]['name']} · {options[i]['kind']}"
                ),
                key="cat_edit_id",
            )
            row = mapping[cid]
            with st.form(f"cat_edit_{cid}"):
                name = st.text_input("Nome", row["name"], max_chars=60)
                color = st.color_picker("Cor", row["color"])
                active = st.toggle("Categoria ativa", value=bool(row["active"]))
                if st.form_submit_button("Salvar categoria", width="stretch"):
                    execute(lambda: service.save_category(name, row["kind"], color, cid, active))
