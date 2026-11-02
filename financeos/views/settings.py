import json

import pandas as pd
import streamlit as st

from financeos.auth import change_password
from financeos.domain import FinanceError, brl
from financeos.forms import execute
from financeos.portability import (
    csv_template,
    export_backup,
    import_csv,
    migrate_legacy,
    preview_csv,
    restore_backup,
    validate_backup,
)
from financeos.ui import heading, section


def render(service, month):
    heading(
        "Seus dados. Seu controle.",
        "Importe, proteja e leve seu histórico com você quando precisar.",
        "Sistema / Dados e ajustes",
    )
    transfer, backup, legacy, preferences, audit = st.tabs(
        [
            "Importar CSV",
            "Backup e restauração",
            "Migrar versão antiga",
            "Preferências",
            "Histórico de ações",
        ]
    )
    with transfer:
        section(
            "Traga suas movimentações",
            "CSV UTF-8 separado por ponto e vírgula. Contas e categorias precisam estar cadastradas.",
        )
        st.download_button(
            "↓ Baixar modelo de CSV",
            csv_template(),
            "finance-os-modelo.csv",
            "text/csv",
            key="csv_template",
        )
        st.caption(
            "Colunas: data;descricao;tipo;valor;conta;categoria;forma_pagamento;observacao. Data no formato AAAA-MM-DD. Apenas receitas e despesas realizadas."
        )
        upload = st.file_uploader("Arquivo CSV", type=["csv"], key="csv_upload")
        if upload:
            raw = upload.getvalue()
            try:
                preview = preview_csv(service, raw)
                st.caption(
                    f"{len(preview['rows'])} linha(s) nova(s) · {preview['duplicates']} duplicata(s) de importação ignorada(s) · {len(preview['errors'])} erro(s)."
                )
                st.caption(
                    "Linhas idênticas de CSV são tratadas como duplicadas. A detecção não inclui lançamentos criados manualmente."
                )
                for error in preview["errors"][:30]:
                    st.error(error)
                if preview["rows"]:
                    st.dataframe(
                        [
                            {
                                "Data": r["on_date"],
                                "Descrição": r["description"],
                                "Tipo": r["kind"],
                                "Valor": brl(r["amount_cents"]),
                            }
                            for r in preview["rows"][:50]
                        ],
                        hide_index=True,
                        width="stretch",
                    )
                if st.button(
                    "Confirmar importação",
                    type="primary",
                    disabled=bool(preview["errors"]) or not preview["rows"],
                    key="import_csv_confirm",
                ):
                    execute(
                        lambda: import_csv(service, raw),
                        "CSV importado. Linhas já importadas foram ignoradas.",
                    )
            except FinanceError as exc:
                st.error(str(exc))
    with backup:
        section(
            "Cópia portátil do seu espaço",
            "Inclui contas, categorias, movimentações, agenda, orçamentos e metas. Não inclui senhas nem o histórico de ações.",
        )
        st.download_button(
            "↓ Baixar backup completo (JSON)",
            export_backup(service),
            "finance-os-backup.json",
            "application/json",
            type="primary",
            key="backup_export",
        )
        st.caption(
            "Guarde uma cópia fora do computador. O JSON contém informações financeiras legíveis."
        )
        st.divider()
        section(
            "Restaurar um backup",
            "A restauração substitui os dados financeiros. Seu usuário e sua senha permanecem os mesmos.",
        )
        st.caption(
            "Antes da substituição, uma cópia de recuperação é salva na pasta backups do diretório de dados da instalação."
        )
        upload = st.file_uploader("Backup Finance OS 2 (JSON)", type=["json"], key="backup_upload")
        if upload:
            try:
                payload = validate_backup(upload.getvalue())
                st.success(f"Backup válido · {payload['workspace']}")
                st.dataframe(
                    [{"Tabela": k, "Registros": len(v)} for k, v in payload["tables"].items()],
                    hide_index=True,
                    width="stretch",
                )
                confirm = st.text_input(
                    "Digite RESTAURAR para confirmar a substituição", key="restore_phrase"
                )
                if st.button(
                    "Restaurar estes dados", disabled=confirm != "RESTAURAR", key="restore_backup"
                ):
                    execute(
                        lambda: restore_backup(service, upload.getvalue()),
                        "Backup restaurado. Uma cópia de recuperação dos dados anteriores foi salva.",
                    )
            except FinanceError as exc:
                st.error(str(exc))
    with legacy:
        section(
            "Continue de onde você parou",
            "Importe o arquivo finance_os.db do Finance OS anterior em uma base financeira vazia.",
        )
        st.caption(
            "A importação lê uma cópia do banco antigo. Saldos atuais são reconciliados; divergências no saldo inicial aparecem na prévia. O arquivo original permanece intacto."
        )
        upload = st.file_uploader(
            "Banco antigo (SQLite)", type=["db", "sqlite", "sqlite3"], key="legacy_upload"
        )
        if upload:
            try:
                raw = upload.getvalue()
                report = migrate_legacy(service, raw, dry_run=True)
                st.success(
                    f"Prévia: {report['contas']} conta(s), {report['lancamentos']} lançamento(s) e {report['compromissos']} compromisso(s)."
                )
                st.caption(
                    f"{report['ajustes_saldo_inicial']} conta(s) requerem reconciliação do saldo inicial para preservar o saldo atual antigo."
                )
                for warning in dict.fromkeys(report["avisos"]):
                    st.warning(warning)
                confirm = st.checkbox(
                    "Conferi a prévia e autorizo a importação nesta base vazia",
                    key="legacy_confirm",
                )
                if st.button(
                    "Importar versão anterior",
                    disabled=not confirm,
                    type="primary",
                    key="legacy_import",
                ):
                    execute(
                        lambda: migrate_legacy(service, raw),
                        "Banco antigo importado e saldos preservados.",
                    )
            except (FinanceError, KeyError, TypeError) as exc:
                st.error(
                    str(exc)
                    if isinstance(exc, FinanceError)
                    else "A estrutura do arquivo não é compatível com a versão antiga."
                )
    with preferences:
        with st.form("workspace_settings"):
            name = st.text_input(
                "Nome do espaço financeiro", service.workspace(), max_chars=80, key="workspace_name"
            )
            if st.form_submit_button("Salvar nome", type="primary"):
                execute(lambda: service.set_workspace(name))
        if st.session_state.get("mode") == "private":
            st.subheader("Alterar senha")
            with st.form("password_change"):
                current = st.text_input("Senha atual", type="password", key="current_password")
                new = st.text_input("Nova senha", type="password", key="new_password")
                repeat = st.text_input(
                    "Repita a nova senha", type="password", key="new_password_repeat"
                )
                if st.form_submit_button("Alterar senha"):
                    if new != repeat:
                        st.error("As novas senhas não conferem.")
                    else:

                        def save_password():
                            from financeos.auth import credential_stamp

                            change_password(service.db, service.actor, current, new)
                            st.session_state["auth_stamp"] = credential_stamp(
                                service.db, service.actor
                            )

                        execute(
                            save_password,
                            "Senha atualizada. Outras sessões serão encerradas na próxima interação.",
                        )
        st.caption(
            "Finance OS 2.0.0 · Uma instalação, um administrador e um espaço financeiro. Moeda: BRL. Datas: horário de São Paulo."
        )
    with audit:
        rows = service.audit()
        st.caption(
            "Últimas 200 ações. Os registros são gerados pelas operações do sistema; não constituem um log inviolável."
        )
        if rows:
            st.dataframe(
                pd.DataFrame(
                    [
                        {
                            "Data/hora (UTC)": r["created_at"],
                            "Ação": r["action"],
                            "Item": r["entity"],
                            "ID": r["entity_id"],
                            "Usuário": r["actor"],
                        }
                        for r in rows
                    ]
                ),
                hide_index=True,
                width="stretch",
                height=400,
            )
            with st.expander("Detalhes das ações"):
                st.json(rows[:30], expanded=False)
        else:
            st.caption("Nenhuma ação registrada ainda.")
