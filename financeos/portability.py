"""CSV portátil, prévia de importação e backup de dados sem credenciais."""

from __future__ import annotations

import csv
import hashlib
import io
import json
import re
import sqlite3
import tempfile
from pathlib import Path

from financeos.db import Database, SCHEMA
from financeos.domain import (
    ACCOUNT_TYPES,
    KINDS,
    FinanceError,
    iso_date,
    legacy_cents,
    money_to_cents,
    realized_date,
    text,
    today,
    valid_cents,
)
from financeos.service import FinanceService

TABLES = (
    "accounts",
    "categories",
    "transactions",
    "obligations",
    "budgets",
    "goals",
    "goal_entries",
)
CSV_COLUMNS = [
    "data",
    "descricao",
    "tipo",
    "valor",
    "conta",
    "categoria",
    "forma_pagamento",
    "observacao",
]
MAX_IMPORT_BYTES = 5 * 1024 * 1024


def csv_safe(value):
    value = str(value or "")
    # Neutraliza fórmulas ao abrir dados de terceiros em planilhas.
    return "'" + value if value.lstrip().startswith(("=", "+", "-", "@", "\t", "\r")) else value


def export_csv(rows) -> bytes:
    out = io.StringIO(newline="")
    writer = csv.DictWriter(out, fieldnames=CSV_COLUMNS, delimiter=";")
    writer.writeheader()
    for row in rows:
        if row["kind"] == "Transferência" or row["status"] != "Ativo":
            continue
        cents = row["amount_cents"]
        writer.writerow(
            dict(
                zip(
                    CSV_COLUMNS,
                    [
                        row["date"],
                        csv_safe(row["description"]),
                        row["kind"],
                        f"{cents // 100},{cents % 100:02d}",
                        csv_safe(row["account"]),
                        csv_safe(row["category"]),
                        csv_safe(row["method"]),
                        csv_safe(row["notes"]),
                    ],
                )
            )
        )
    return b"\xef\xbb\xbf" + out.getvalue().encode("utf-8")


def csv_template():
    out = io.StringIO(newline="")
    w = csv.writer(out, delimiter=";")
    w.writerow(CSV_COLUMNS)
    w.writerow(
        [
            today().isoformat(),
            "Serviço de exemplo",
            "Receita",
            "250,00",
            "Minha conta",
            "Serviços",
            "Pix",
            "",
        ]
    )
    return b"\xef\xbb\xbf" + out.getvalue().encode()


def _unescape(value):
    # Compatibilidade com a proteção de fórmulas do próprio exportador.
    return (
        value[1:]
        if value.startswith("'") and value[1:].lstrip().startswith(("=", "+", "-", "@", "\t", "\r"))
        else value
    )


def preview_csv(service: FinanceService, raw: bytes):
    if not raw or len(raw) > MAX_IMPORT_BYTES:
        raise FinanceError("Envie um CSV com até 5 MB.")
    try:
        decoded = raw.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise FinanceError("Salve o arquivo como CSV UTF-8, separado por ponto e vírgula.") from exc
    reader = csv.DictReader(io.StringIO(decoded, newline=""), delimiter=";")
    if reader.fieldnames != CSV_COLUMNS:
        raise FinanceError("As colunas não correspondem ao modelo. Baixe o CSV de exemplo.")
    accounts = {a["name"].casefold(): a["id"] for a in service.accounts(active_only=True)}
    categories = {(c["name"].casefold(), c["kind"]): c["id"] for c in service.categories()}
    with service.db.read() as con:
        existing = {
            r[0]
            for r in con.execute("SELECT import_key FROM transactions WHERE import_key IS NOT NULL")
        }
    prepared, errors, duplicates = [], [], 0
    seen = set()
    for line, row in enumerate(reader, 2):
        if line > 5001:
            raise FinanceError("O limite por importação é de 5.000 linhas.")
        try:
            if None in row or any(v is None for v in row.values()):
                raise FinanceError("Quantidade de colunas inválida.")
            kind = row["tipo"].strip()
            if kind not in KINDS[:2]:
                raise FinanceError(
                    "Use Receita ou Despesa; transferências são registradas no aplicativo."
                )
            account = accounts.get(_unescape(row["conta"]).strip().casefold())
            category = categories.get((_unescape(row["categoria"]).strip().casefold(), kind))
            if not account or not category:
                raise FinanceError("Conta ou categoria não encontrada entre os cadastros ativos.")
            entry = dict(
                description=text(_unescape(row["descricao"])),
                kind=kind,
                amount_cents=money_to_cents(row["valor"]),
                account_id=account,
                category_id=category,
                on_date=realized_date(row["data"].strip()),
                method=text(_unescape(row["forma_pagamento"]) or "Pix", "Forma", 40),
                notes=_unescape(row["observacao"]).strip(),
            )
            valid_cents(entry["amount_cents"])
            if len(entry["notes"]) > 1000:
                raise FinanceError("Observação excede 1.000 caracteres.")
            key = hashlib.sha256(
                json.dumps(entry, sort_keys=True, ensure_ascii=False).encode()
            ).hexdigest()
            if key in existing or key in seen:
                duplicates += 1
            else:
                prepared.append({**entry, "import_key": key})
                seen.add(key)
        except FinanceError as exc:
            errors.append(f"Linha {line}: {exc}")
    return {
        "rows": prepared,
        "errors": errors,
        "duplicates": duplicates,
        "sha256": hashlib.sha256(raw).hexdigest(),
    }


def import_csv(service: FinanceService, raw: bytes):
    preview = preview_csv(service, raw)
    if preview["errors"]:
        raise FinanceError(
            "Corrija todas as linhas inválidas antes de importar. Nenhuma linha foi gravada."
        )
    imported = 0
    with service.db.write() as con:
        for row in preview["rows"]:
            if con.execute(
                "SELECT 1 FROM transactions WHERE import_key=?", (row["import_key"],)
            ).fetchone():
                continue
            values = service._transaction_values(
                con,
                row["description"],
                row["kind"],
                row["amount_cents"],
                row["account_id"],
                row["category_id"],
                row["on_date"],
                row["method"],
                row["notes"],
            )
            service._insert_transaction(con, values, row["import_key"])
            imported += 1
        service._audit(
            con, "Importar CSV", "dados", None, {"linhas": imported, "sha256": preview["sha256"]}
        )
    return imported


def export_backup(service: FinanceService) -> bytes:
    with service.db.read() as con:
        con.execute("BEGIN")
        data = {
            table: [dict(r) for r in con.execute(f"SELECT * FROM {table} ORDER BY id")]
            for table in TABLES
        }
        workspace = con.execute("SELECT value FROM settings WHERE key='workspace'").fetchone()[0]
    return json.dumps(
        {
            "format": "finance-os",
            "version": 2,
            "workspace": workspace,
            "exported_on": today().isoformat(),
            "tables": data,
        },
        ensure_ascii=False,
        indent=2,
    ).encode()


def _validate_content(con):
    for row in con.execute("SELECT * FROM accounts"):
        text(row["name"], "Conta", 80)
        valid_cents(row["opening_cents"], allow_zero=True, allow_negative=True)
        if row["type"] not in ACCOUNT_TYPES:
            raise FinanceError("Backup contém tipo de conta inválido.")
    for row in con.execute("SELECT * FROM categories"):
        text(row["name"], "Categoria", 60)
        if not re.fullmatch(r"#[0-9a-fA-F]{6}", row["color"]):
            raise FinanceError("Backup contém cor inválida.")
    for row in con.execute("SELECT * FROM transactions"):
        text(row["description"])
        valid_cents(row["amount_cents"])
        realized_date(row["date"])
        text(row["method"], "Forma de pagamento", 40)
        if len(row["notes"]) > 1000:
            raise FinanceError("Observação inválida no backup.")
        if row["kind"] != "Transferência":
            cat = con.execute(
                "SELECT kind FROM categories WHERE id=?", (row["category_id"],)
            ).fetchone()
            if not cat or cat[0] != row["kind"]:
                raise FinanceError("Backup contém categoria incompatível com o lançamento.")
    for row in con.execute("SELECT * FROM obligations"):
        text(row["description"])
        valid_cents(row["amount_cents"])
        iso_date(row["due_date"])
        if (
            not 1 <= row["installment"] <= row["total_installments"] <= 60
            or len(row["notes"]) > 1000
        ):
            raise FinanceError("Parcelas ou observações inválidas no backup.")
        cat = con.execute(
            "SELECT kind FROM categories WHERE id=?", (row["category_id"],)
        ).fetchone()
        if not cat or cat[0] != row["kind"]:
            raise FinanceError("Backup contém categoria incompatível com o compromisso.")
        if row["status"] == "Liquidado":
            realized_date(row["settled_date"])
            tx = con.execute(
                "SELECT * FROM transactions WHERE id=?", (row["transaction_id"],)
            ).fetchone()
            if (
                not tx
                or tx["status"] != "Ativo"
                or any(
                    tx[k] != row[k] for k in ("kind", "amount_cents", "account_id", "category_id")
                )
                or tx["date"] != row["settled_date"]
            ):
                raise FinanceError("Backup contém baixa financeira inconsistente.")
    for row in con.execute("SELECT * FROM budgets"):
        from financeos.domain import month_bounds

        month_bounds(row["month"])
        valid_cents(row["limit_cents"])
        cat = con.execute(
            "SELECT kind FROM categories WHERE id=?", (row["category_id"],)
        ).fetchone()
        if not cat or cat[0] != "Despesa":
            raise FinanceError("Orçamento precisa de categoria de despesa.")
    for row in con.execute("SELECT * FROM goals"):
        text(row["name"], "Meta", 80)
        valid_cents(row["target_cents"])
        iso_date(row["due_date"])
        total = 0
        for entry in con.execute(
            "SELECT * FROM goal_entries WHERE goal_id=? ORDER BY id", (row["id"],)
        ):
            realized_date(entry["date"])
            valid_cents(entry["amount_cents"], allow_negative=True)
            total += entry["amount_cents"]
            if total < 0 or len(entry["notes"]) > 1000:
                raise FinanceError("Histórico de meta inconsistente.")


def validate_backup(raw: bytes):
    if not raw or len(raw) > MAX_IMPORT_BYTES:
        raise FinanceError("Envie um backup JSON de até 5 MB.")
    try:
        payload = json.loads(raw)
        if (
            not isinstance(payload, dict)
            or payload.get("format") != "finance-os"
            or payload.get("version") != 2
        ):
            raise FinanceError("Este arquivo não é um backup Finance OS 2.")
        text(payload["workspace"], "Nome do espaço", 80)
        if not isinstance(payload["tables"], dict) or set(payload["tables"]) != set(TABLES):
            raise FinanceError("O backup está incompleto.")
        con = sqlite3.connect(":memory:", isolation_level=None)
        con.row_factory = sqlite3.Row
        try:
            con.execute("PRAGMA foreign_keys=ON")
            con.executescript(SCHEMA)
            con.execute("BEGIN")
            for table in TABLES:
                columns = [r[1] for r in con.execute(f"PRAGMA table_info({table})")]
                rows = payload["tables"][table]
                if not isinstance(rows, list) or len(rows) > 30_000:
                    raise FinanceError("Quantidade de registros inválida no backup.")
                for row in rows:
                    if (
                        not isinstance(row, dict)
                        or set(row) != set(columns)
                        or type(row["id"]) is not int
                        or row["id"] <= 0
                    ):
                        raise FinanceError("Estrutura de registro inválida no backup.")
                    con.execute(
                        f"INSERT INTO {table}({','.join(columns)}) VALUES({','.join('?' for _ in columns)})",
                        [row[k] for k in columns],
                    )
            if con.execute("PRAGMA foreign_key_check").fetchone():
                raise FinanceError("O backup possui referências inexistentes.")
            _validate_content(con)
        finally:
            con.close()
        return payload
    except FinanceError:
        raise
    except (ValueError, KeyError, TypeError, sqlite3.Error, OverflowError, RecursionError) as exc:
        raise FinanceError("Backup inválido ou corrompido. Nenhum dado foi alterado.") from exc


def restore_backup(service: FinanceService, raw: bytes):
    payload = validate_backup(raw)
    # Snapshot exato da mesma transação que faz a substituição. Credenciais ficam no banco atual.
    with service.db.write() as con:
        before = {
            table: [dict(r) for r in con.execute(f"SELECT * FROM {table} ORDER BY id")]
            for table in TABLES
        }
        workspace = con.execute("SELECT value FROM settings WHERE key='workspace'").fetchone()[0]
        recovery = json.dumps(
            {
                "format": "finance-os",
                "version": 2,
                "workspace": workspace,
                "exported_on": today().isoformat(),
                "tables": before,
            },
            ensure_ascii=False,
        ).encode()
        root = service.db.path.parent / "backups"
        root.mkdir(exist_ok=True)
        import os

        fd, filename = tempfile.mkstemp(prefix="antes-restauracao-", suffix=".json", dir=root)
        try:
            with os.fdopen(fd, "wb") as f:
                f.write(recovery)
                f.flush()
                os.fsync(f.fileno())
        except Exception:
            Path(filename).unlink(missing_ok=True)
            raise
        for table in reversed(TABLES):
            con.execute(f"DELETE FROM {table}")
        for table in TABLES:
            columns = [r[1] for r in con.execute(f"PRAGMA table_info({table})")]
            for row in payload["tables"][table]:
                con.execute(
                    f"INSERT INTO {table}({','.join(columns)}) VALUES({','.join('?' for _ in columns)})",
                    [row[k] for k in columns],
                )
        con.execute("UPDATE settings SET value=? WHERE key='workspace'", (payload["workspace"],))
        self_detail = {
            "sha256": hashlib.sha256(raw).hexdigest(),
            "recuperacao": Path(filename).name,
            "registros": {k: len(v) for k, v in payload["tables"].items()},
        }
        service._audit(con, "Restaurar backup", "dados", None, self_detail)
    return Path(filename)


def read_legacy(raw: bytes):
    if not raw or len(raw) > 20 * 1024 * 1024 or not raw.startswith(b"SQLite format 3\x00"):
        raise FinanceError("Envie um banco SQLite da versão anterior, de até 20 MB.")
    with tempfile.TemporaryDirectory() as folder:
        source = Path(folder) / "legacy.db"
        source.write_bytes(raw)
        con = sqlite3.connect(f"{source.as_uri()}?mode=ro", uri=True)
        con.row_factory = sqlite3.Row
        try:
            con.execute("PRAGMA query_only=ON")
            con.execute("PRAGMA trusted_schema=OFF")
            if con.execute("PRAGMA quick_check").fetchone()[0] != "ok":
                raise FinanceError("O banco antigo falhou na verificação de integridade.")
            result = {}
            for table in ("contas", "categorias", "lancamentos", "contas_pagar"):
                meta = con.execute(
                    "SELECT type,sql FROM sqlite_master WHERE name=?", (table,)
                ).fetchone()
                if not meta or meta["type"] != "table" or "VIRTUAL" in meta["sql"].upper():
                    raise FinanceError("A estrutura não corresponde ao Finance OS antigo.")
                rows = [
                    dict(r) for r in con.execute(f"SELECT * FROM {table} ORDER BY id LIMIT 30001")
                ]
                if len(rows) > 30_000:
                    raise FinanceError("Banco antigo excede o limite de importação.")
                result[table] = rows
            return result
        except sqlite3.Error as exc:
            raise FinanceError("Não foi possível ler o banco antigo.") from exc
        finally:
            con.close()


def migrate_legacy(service: FinanceService, raw: bytes, *, dry_run=False):
    legacy = read_legacy(raw)
    if dry_run:
        with tempfile.TemporaryDirectory() as folder:
            db = Database(Path(folder) / "preview.db")
            db.initialize()
            return migrate_legacy(FinanceService(db), raw)
    report = {
        "contas": 0,
        "lancamentos": 0,
        "compromissos": 0,
        "ajustes_saldo_inicial": 0,
        "avisos": [],
    }
    with service.db.write() as con:
        if any(
            con.execute(f"SELECT 1 FROM {t} LIMIT 1").fetchone()
            for t in TABLES
            if t != "categories"
        ):
            raise FinanceError(
                "A migração exige uma base financeira vazia. Use uma instalação separada ou restaure um backup."
            )
        account_map, category_map, tx_map, desired_balances = {}, {}, {}, {}
        for a in legacy["contas"]:
            name = text(str(a["nome"]), "Conta", 80)
            lower = str(a["tipo"]).casefold()
            account_type = next(
                (t for t in ACCOUNT_TYPES if t.casefold() == lower), "Conta corrente"
            )
            initial = legacy_cents(a.get("saldo_inicial", 0))
            account_id = con.execute(
                "INSERT INTO accounts(name,type,opening_cents,active) VALUES(?,?,?,?)",
                (name, account_type, initial, int(bool(a.get("ativo", 1)))),
            ).lastrowid
            account_map[a["id"]] = account_id
            desired_balances[account_id] = (legacy_cents(a.get("saldo_atual", 0)), initial)
        for cat in legacy["categorias"]:
            kind = cat["tipo"]
            if kind not in KINDS[:2]:
                raise FinanceError("Categoria de tipo desconhecido no banco antigo.")
            name = text(str(cat["nome"]), "Categoria", 60)
            color = cat.get("cor") or "#93A3BB"
            if not re.fullmatch(r"#[0-9a-fA-F]{6}", color):
                color = "#93A3BB"
            con.execute(
                "INSERT OR IGNORE INTO categories(name,kind,color) VALUES(?,?,?)",
                (name, kind, color),
            )
            category_map[cat["id"]] = con.execute(
                "SELECT id FROM categories WHERE name=? COLLATE NOCASE AND kind=?", (name, kind)
            ).fetchone()[0]

        def mapped(row, key, mapping):
            if row.get(key) not in mapping:
                raise FinanceError(
                    "Há lançamento sem conta ou categoria válida no banco antigo. Corrija antes de importar."
                )
            return mapping[row[key]]

        for tx in legacy["lancamentos"]:
            kind, cents = tx["tipo"], legacy_cents(tx["valor"])
            valid_cents(cents)
            if kind not in KINDS[:2]:
                raise FinanceError("Tipo de lançamento desconhecido no banco antigo.")
            account = mapped(tx, "conta_id", account_map)
            category = mapped(tx, "categoria_id", category_map)
            cat_kind = con.execute(
                "SELECT kind FROM categories WHERE id=?", (category,)
            ).fetchone()[0]
            if cat_kind != kind:
                raise FinanceError("Categoria incompatível no banco antigo.")
            on_date = iso_date(str(tx.get("data_pagamento") or tx["data_lancamento"])[:10])
            if tx.get("status", "Pago") != "Pago" or on_date > today().isoformat():
                con.execute(
                    """INSERT INTO obligations(description,kind,amount_cents,account_id,category_id,due_date,notes)
                 VALUES(?,?,?,?,?,?,?)""",
                    (
                        text(tx["descricao"]),
                        kind,
                        cents,
                        account,
                        category,
                        on_date,
                        str(tx.get("observacao") or "")[:1000],
                    ),
                )
                report["avisos"].append(
                    "Um lançamento não realizado foi convertido em compromisso pendente."
                )
                continue
            tx_id = con.execute(
                """INSERT INTO transactions(description,kind,amount_cents,account_id,category_id,date,method,notes)
             VALUES(?,?,?,?,?,?,?,?)""",
                (
                    text(tx["descricao"]),
                    kind,
                    cents,
                    account,
                    category,
                    on_date,
                    str(tx.get("forma_pagamento") or "Outro")[:40],
                    str(tx.get("observacao") or "")[:1000],
                ),
            ).lastrowid
            tx_map[tx["id"]] = tx_id
        for bill in legacy["contas_pagar"]:
            account, category = (
                mapped(bill, "conta_id", account_map),
                mapped(bill, "categoria_id", category_map),
            )
            if (
                con.execute("SELECT kind FROM categories WHERE id=?", (category,)).fetchone()[0]
                != "Despesa"
            ):
                raise FinanceError("Conta a pagar antiga possui categoria incompatível.")
            cents = legacy_cents(bill["valor"])
            valid_cents(cents)
            due = iso_date(str(bill["data_vencimento"])[:10])
            paid = bill.get("status") == "Pago"
            tx_id, settled = tx_map.get(bill.get("lancamento_id")), None
            if paid:
                settled = realized_date(str(bill.get("data_pagamento") or due)[:10])
                if not tx_id:
                    tx_id = con.execute(
                        """INSERT INTO transactions(description,kind,amount_cents,account_id,category_id,date,method,notes)
                     VALUES(?,'Despesa',?,?,?,?,?,'Recuperado da baixa legada')""",
                        (
                            text(bill["descricao"]),
                            cents,
                            account,
                            category,
                            settled,
                            str(bill.get("forma_pagamento") or "Outro")[:40],
                        ),
                    ).lastrowid
                    report["avisos"].append(
                        "Uma baixa antiga sem vínculo recebeu lançamento recuperado; o saldo total foi preservado."
                    )
                else:
                    linked = con.execute(
                        "SELECT * FROM transactions WHERE id=?", (tx_id,)
                    ).fetchone()
                    if (
                        linked["kind"] != "Despesa"
                        or linked["amount_cents"] != cents
                        or linked["account_id"] != account
                        or linked["category_id"] != category
                    ):
                        raise FinanceError(
                            "Existe baixa vinculada a lançamento divergente no banco antigo."
                        )
                    settled = linked["date"]
            elif tx_id:
                raise FinanceError(
                    "Há conta pendente vinculada a lançamento no banco antigo. Revise antes de importar."
                )
            status = (
                "Liquidado"
                if paid
                else ("Cancelado" if bill.get("status") == "Cancelado" else "Pendente")
            )
            con.execute(
                """INSERT INTO obligations(description,kind,amount_cents,account_id,category_id,due_date,status,
             transaction_id,settled_date,notes) VALUES(?,'Despesa',?,?,?,?,?,?,?,?)""",
                (
                    text(bill["descricao"]),
                    cents,
                    account,
                    category,
                    due,
                    status,
                    tx_id,
                    settled,
                    str(bill.get("observacao") or "")[:1000],
                ),
            )
            if bill.get("recorrente"):
                report["avisos"].append(
                    "Recorrência antiga preservada apenas nas ocorrências existentes. Agende novas ocorrências na agenda."
                )
        # Reconciliar cada conta com o saldo exibido na versão anterior, sem duplicar baixas.
        for account_id, (desired, original_opening) in desired_balances.items():
            net = con.execute(
                """SELECT COALESCE(SUM(CASE WHEN kind='Receita' THEN amount_cents ELSE -amount_cents END),0)
              FROM transactions WHERE account_id=? AND status='Ativo'""",
                (account_id,),
            ).fetchone()[0]
            opening = desired - net
            valid_cents(opening, allow_zero=True, allow_negative=True)
            con.execute("UPDATE accounts SET opening_cents=? WHERE id=?", (opening, account_id))
            if opening != original_opening:
                report["ajustes_saldo_inicial"] += 1
                report["avisos"].append(
                    "Saldo inicial reconciliado para preservar o saldo atual informado pelo sistema antigo."
                )
        _validate_content(con)
        report.update(
            contas=len(account_map),
            lancamentos=con.execute("SELECT COUNT(*) FROM transactions").fetchone()[0],
            compromissos=con.execute("SELECT COUNT(*) FROM obligations").fetchone()[0],
        )
        service._audit(con, "Migrar v1", "dados", None, report)
    return report
