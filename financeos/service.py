"""Casos de uso financeiros. Os valores públicos são sempre centavos inteiros."""

from __future__ import annotations

import json
import re
import sqlite3
import uuid
from datetime import date, timedelta

from financeos.db import Database
from financeos.domain import (
    ACCOUNT_TYPES,
    KINDS,
    FinanceError,
    add_months,
    iso_date,
    month_bounds,
    realized_date,
    text,
    today,
    valid_cents,
)

ACCOUNT_SQL = """
SELECT a.*, a.opening_cents + COALESCE((
 SELECT SUM(CASE
  WHEN t.kind='Receita' AND t.account_id=a.id THEN t.amount_cents
  WHEN t.kind='Despesa' AND t.account_id=a.id THEN -t.amount_cents
  WHEN t.kind='Transferência' AND t.account_id=a.id THEN -t.amount_cents
  WHEN t.kind='Transferência' AND t.peer_account_id=a.id THEN t.amount_cents ELSE 0 END)
 FROM transactions t WHERE t.status='Ativo' AND (t.account_id=a.id OR t.peer_account_id=a.id)
),0) AS balance_cents FROM accounts a
"""
TX_SQL = """SELECT t.*, a.name AS account, p.name AS peer_account,
 c.name AS category, c.color AS category_color,
 o.id AS obligation_id FROM transactions t
 JOIN accounts a ON a.id=t.account_id
 LEFT JOIN accounts p ON p.id=t.peer_account_id
 LEFT JOIN categories c ON c.id=t.category_id
 LEFT JOIN obligations o ON o.transaction_id=t.id
"""
BILL_SQL = """SELECT o.*, a.name AS account, c.name AS category, c.color AS category_color
 FROM obligations o JOIN accounts a ON a.id=o.account_id JOIN categories c ON c.id=o.category_id
"""


class FinanceService:
    def __init__(self, db: Database, actor="sistema"):
        self.db = db
        self.actor = str(actor)[:80]

    def _audit(self, con, action, entity, entity_id, detail):
        con.execute(
            "INSERT INTO audit(action,entity,entity_id,detail,actor) VALUES(?,?,?,?,?)",
            (action, entity, entity_id, json.dumps(detail, ensure_ascii=False), self.actor),
        )

    def _account(self, con, account_id, *, active=True):
        row = con.execute("SELECT * FROM accounts WHERE id=?", (account_id,)).fetchone()
        if not row or (active and not row["active"]):
            raise FinanceError("Selecione uma conta financeira ativa.")
        return row

    def _category(self, con, category_id, kind, *, active=True):
        row = con.execute("SELECT * FROM categories WHERE id=?", (category_id,)).fetchone()
        if not row or row["kind"] != kind or (active and not row["active"]):
            raise FinanceError("A categoria deve estar ativa e corresponder ao tipo do lançamento.")
        return row

    def workspace(self):
        with self.db.read() as con:
            return con.execute("SELECT value FROM settings WHERE key='workspace'").fetchone()[0]

    def set_workspace(self, name):
        name = text(name, "Nome do espaço", 80)
        with self.db.write() as con:
            con.execute("UPDATE settings SET value=? WHERE key='workspace'", (name,))
            self._audit(con, "Atualizar", "espaço", None, {"nome": name})

    def accounts(self, active_only=False):
        with self.db.read() as con:
            sql = (
                ACCOUNT_SQL
                + (" WHERE a.active=1" if active_only else "")
                + " ORDER BY a.active DESC,a.name"
            )
            return [dict(r) for r in con.execute(sql)]

    def create_account(self, name, account_type, opening_cents=0):
        name = text(name, "Nome da conta", 80)
        valid_cents(opening_cents, allow_zero=True, allow_negative=True)
        if account_type not in ACCOUNT_TYPES:
            raise FinanceError("Tipo de conta inválido.")
        try:
            with self.db.write() as con:
                account_id = con.execute(
                    "INSERT INTO accounts(name,type,opening_cents) VALUES(?,?,?)",
                    (name, account_type, opening_cents),
                ).lastrowid
                self._audit(
                    con,
                    "Criar",
                    "conta",
                    account_id,
                    {"nome": name, "saldo_inicial": opening_cents},
                )
                return account_id
        except sqlite3.IntegrityError as exc:
            raise FinanceError("Já existe uma conta com esse nome.") from exc

    def update_account(self, account_id, name, account_type, active):
        name = text(name, "Nome da conta", 80)
        if account_type not in ACCOUNT_TYPES or type(active) is not bool:
            raise FinanceError("Dados da conta inválidos.")
        try:
            with self.db.write() as con:
                before = dict(self._account(con, account_id, active=False))
                if (
                    not active
                    and con.execute(
                        "SELECT 1 FROM obligations WHERE account_id=? AND status='Pendente'",
                        (account_id,),
                    ).fetchone()
                ):
                    raise FinanceError(
                        "Quite, cancele ou altere os compromissos pendentes antes de arquivar a conta."
                    )
                con.execute(
                    "UPDATE accounts SET name=?,type=?,active=? WHERE id=?",
                    (name, account_type, int(active), account_id),
                )
                self._audit(
                    con,
                    "Atualizar",
                    "conta",
                    account_id,
                    {"antes": before, "nome": name, "ativa": active},
                )
        except sqlite3.IntegrityError as exc:
            raise FinanceError("Já existe uma conta com esse nome.") from exc

    def categories(self, kind=None, active_only=True):
        where, params = [], []
        if active_only:
            where.append("active=1")
        if kind:
            where.append("kind=?")
            params.append(kind)
        with self.db.read() as con:
            return [
                dict(r)
                for r in con.execute(
                    "SELECT * FROM categories"
                    + (" WHERE " + " AND ".join(where) if where else "")
                    + " ORDER BY kind,name",
                    params,
                )
            ]

    def save_category(self, name, kind, color, category_id=None, active=True):
        name = text(name, "Nome da categoria", 60)
        if kind not in KINDS[:2] or not re.fullmatch(r"#[0-9A-Fa-f]{6}", color):
            raise FinanceError("Tipo ou cor de categoria inválidos.")
        try:
            with self.db.write() as con:
                if category_id:
                    old = con.execute(
                        "SELECT * FROM categories WHERE id=?", (category_id,)
                    ).fetchone()
                    if not old or old["kind"] != kind:
                        raise FinanceError(
                            "Não é possível alterar o tipo de uma categoria existente."
                        )
                    if (
                        not active
                        and con.execute(
                            "SELECT 1 FROM obligations WHERE category_id=? AND status='Pendente'",
                            (category_id,),
                        ).fetchone()
                    ):
                        raise FinanceError(
                            "Resolva os compromissos pendentes antes de arquivar a categoria."
                        )
                    con.execute(
                        "UPDATE categories SET name=?,color=?,active=? WHERE id=?",
                        (name, color, int(active), category_id),
                    )
                else:
                    category_id = con.execute(
                        "INSERT INTO categories(name,kind,color) VALUES(?,?,?)", (name, kind, color)
                    ).lastrowid
                self._audit(
                    con,
                    "Salvar",
                    "categoria",
                    category_id,
                    {"nome": name, "tipo": kind, "ativa": active},
                )
                return category_id
        except sqlite3.IntegrityError as exc:
            raise FinanceError("Já existe uma categoria com esse nome e tipo.") from exc

    def _transaction_values(
        self,
        con,
        description,
        kind,
        amount_cents,
        account_id,
        category_id,
        on_date,
        method,
        notes,
        peer_account_id=None,
    ):
        description = text(description)
        if kind not in KINDS:
            raise FinanceError("Tipo de lançamento inválido.")
        valid_cents(amount_cents)
        on_date = realized_date(on_date)
        self._account(con, account_id)
        if kind == "Transferência":
            self._account(con, peer_account_id)
            if account_id == peer_account_id:
                raise FinanceError("A conta de destino deve ser diferente da origem.")
            category_id = None
        else:
            self._category(con, category_id, kind)
            peer_account_id = None
        notes = str(notes).strip()
        if len(notes) > 1000:
            raise FinanceError("As observações devem ter até 1.000 caracteres.")
        return (
            description,
            kind,
            amount_cents,
            account_id,
            peer_account_id,
            category_id,
            on_date,
            text(method, "Forma de pagamento", 40),
            notes,
        )

    def _insert_transaction(self, con, values, import_key=None):
        tx_id = con.execute(
            """INSERT INTO transactions(description,kind,amount_cents,account_id,
          peer_account_id,category_id,date,method,notes,import_key) VALUES(?,?,?,?,?,?,?,?,?,?)""",
            (*values, import_key),
        ).lastrowid
        self._audit(
            con,
            "Criar",
            "lançamento",
            tx_id,
            {"descricao": values[0], "tipo": values[1], "centavos": values[2]},
        )
        return tx_id

    def create_transaction(
        self,
        description,
        kind,
        amount_cents,
        account_id,
        category_id,
        on_date,
        method="Pix",
        notes="",
        peer_account_id=None,
    ):
        with self.db.write() as con:
            values = self._transaction_values(
                con,
                description,
                kind,
                amount_cents,
                account_id,
                category_id,
                on_date,
                method,
                notes,
                peer_account_id,
            )
            return self._insert_transaction(con, values)

    def update_transaction(
        self, tx_id, description, amount_cents, category_id, on_date, method, notes
    ):
        with self.db.write() as con:
            row = con.execute(
                "SELECT * FROM transactions WHERE id=? AND status='Ativo'", (tx_id,)
            ).fetchone()
            if not row:
                raise FinanceError("Lançamento ativo não encontrado.")
            if con.execute("SELECT 1 FROM obligations WHERE transaction_id=?", (tx_id,)).fetchone():
                raise FinanceError(
                    "Este lançamento pertence à agenda. Desfaça a baixa pela agenda para corrigi-lo."
                )
            values = self._transaction_values(
                con,
                description,
                row["kind"],
                amount_cents,
                row["account_id"],
                category_id,
                on_date,
                method,
                notes,
                row["peer_account_id"],
            )
            con.execute(
                """UPDATE transactions SET description=?,kind=?,amount_cents=?,account_id=?,
              peer_account_id=?,category_id=?,date=?,method=?,notes=? WHERE id=?""",
                (*values, tx_id),
            )
            self._audit(con, "Editar", "lançamento", tx_id, {"antes": dict(row), "depois": values})

    def reverse_transaction(self, tx_id):
        with self.db.write() as con:
            row = con.execute(
                "SELECT * FROM transactions WHERE id=? AND status='Ativo'", (tx_id,)
            ).fetchone()
            if not row:
                raise FinanceError("O lançamento já foi estornado ou não existe.")
            if con.execute("SELECT 1 FROM obligations WHERE transaction_id=?", (tx_id,)).fetchone():
                raise FinanceError("Desfaça a baixa na agenda para reabrir o compromisso.")
            con.execute("UPDATE transactions SET status='Estornado' WHERE id=?", (tx_id,))
            self._audit(con, "Estornar", "lançamento", tx_id, dict(row))

    def transactions(
        self, start=None, end=None, kind=None, account_id=None, search="", include_reversed=False
    ):
        clauses, params = [], []
        if not include_reversed:
            clauses.append("t.status='Ativo'")
        if start:
            clauses.append("t.date>=?")
            params.append(iso_date(start))
        if end:
            clauses.append("t.date<=?")
            params.append(iso_date(end))
        if kind:
            clauses.append("t.kind=?")
            params.append(kind)
        if account_id:
            clauses.append("(t.account_id=? OR t.peer_account_id=?)")
            params.extend([account_id, account_id])
        if search:
            clauses.append("instr(lower(t.description || ' ' || t.notes),lower(?))>0")
            params.append(str(search)[:160])
        with self.db.read() as con:
            return [
                dict(r)
                for r in con.execute(
                    TX_SQL
                    + (" WHERE " + " AND ".join(clauses) if clauses else "")
                    + " ORDER BY t.date DESC,t.id DESC",
                    params,
                )
            ]

    def create_obligations(
        self,
        description,
        kind,
        amount_cents,
        account_id,
        category_id,
        due_date,
        count=1,
        mode="Único",
        notes="",
    ):
        description = text(description)
        valid_cents(amount_cents)
        due = date.fromisoformat(iso_date(due_date))
        if (
            kind not in KINDS[:2]
            or mode not in ("Único", "Parcelado", "Recorrente")
            or type(count) is not int
            or not 1 <= count <= 60
        ):
            raise FinanceError("Use de 1 a 60 parcelas ou ocorrências.")
        if mode == "Único":
            count = 1
        if mode == "Parcelado" and amount_cents < count:
            raise FinanceError("O total deve permitir ao menos um centavo por parcela.")
        if len(str(notes)) > 1000:
            raise FinanceError("Observações: limite de 1.000 caracteres.")
        with self.db.write() as con:
            self._account(con, account_id)
            self._category(con, category_id, kind)
            series = str(uuid.uuid4()) if count > 1 else None
            base, rest = divmod(amount_cents, count) if mode == "Parcelado" else (amount_cents, 0)
            ids = []
            for i in range(count):
                cents = base + (1 if i < rest else 0)
                bill_id = con.execute(
                    """INSERT INTO obligations(description,kind,amount_cents,account_id,
                  category_id,due_date,series_id,installment,total_installments,notes)
                  VALUES(?,?,?,?,?,?,?,?,?,?)""",
                    (
                        description,
                        kind,
                        cents,
                        account_id,
                        category_id,
                        add_months(due, i).isoformat(),
                        series,
                        i + 1,
                        count,
                        str(notes).strip(),
                    ),
                ).lastrowid
                self._audit(
                    con,
                    "Agendar",
                    "compromisso",
                    bill_id,
                    {"tipo": kind, "centavos": cents, "modo": mode},
                )
                ids.append(bill_id)
            return ids

    def obligations(self, kind=None, status=None, start=None, end=None):
        clauses, params = [], []
        for column, value in (("kind", kind), ("status", status)):
            if value:
                clauses.append(f"o.{column}=?")
                params.append(value)
        if start:
            clauses.append("o.due_date>=?")
            params.append(iso_date(start))
        if end:
            clauses.append("o.due_date<=?")
            params.append(iso_date(end))
        with self.db.read() as con:
            return [
                dict(r)
                for r in con.execute(
                    BILL_SQL
                    + (" WHERE " + " AND ".join(clauses) if clauses else "")
                    + " ORDER BY o.due_date,o.id",
                    params,
                )
            ]

    def settle_obligation(self, bill_id, on_date, method="Pix"):
        on_date = realized_date(on_date)
        with self.db.write() as con:
            row = con.execute("SELECT * FROM obligations WHERE id=?", (bill_id,)).fetchone()
            if not row or row["status"] != "Pendente":
                raise FinanceError("O compromisso já foi liquidado, cancelado ou não existe.")
            values = self._transaction_values(
                con,
                row["description"],
                row["kind"],
                row["amount_cents"],
                row["account_id"],
                row["category_id"],
                on_date,
                method,
                row["notes"],
            )
            tx_id = self._insert_transaction(con, values)
            con.execute(
                "UPDATE obligations SET status='Liquidado',settled_date=?,transaction_id=? WHERE id=?",
                (on_date, tx_id, bill_id),
            )
            self._audit(con, "Liquidar", "compromisso", bill_id, {"lancamento": tx_id})
            return tx_id

    def reopen_obligation(self, bill_id):
        with self.db.write() as con:
            row = con.execute("SELECT * FROM obligations WHERE id=?", (bill_id,)).fetchone()
            if not row or row["status"] != "Liquidado":
                raise FinanceError("Selecione um compromisso liquidado.")
            con.execute(
                "UPDATE transactions SET status='Estornado' WHERE id=?", (row["transaction_id"],)
            )
            con.execute(
                "UPDATE obligations SET status='Pendente',settled_date=NULL,transaction_id=NULL WHERE id=?",
                (bill_id,),
            )
            self._audit(
                con,
                "Reabrir",
                "compromisso",
                bill_id,
                {"lancamento_estornado": row["transaction_id"]},
            )

    def update_obligation(
        self, bill_id, description, amount_cents, account_id, category_id, due_date, notes=""
    ):
        description, due_date = text(description), iso_date(due_date)
        valid_cents(amount_cents)
        if len(str(notes)) > 1000:
            raise FinanceError("Observações: limite de 1.000 caracteres.")
        with self.db.write() as con:
            old = con.execute("SELECT * FROM obligations WHERE id=?", (bill_id,)).fetchone()
            if not old or old["status"] != "Pendente":
                raise FinanceError("Somente compromissos pendentes podem ser editados.")
            self._account(con, account_id)
            self._category(con, category_id, old["kind"])
            con.execute(
                """UPDATE obligations SET description=?,amount_cents=?,account_id=?,category_id=?,
               due_date=?,notes=? WHERE id=?""",
                (
                    description,
                    amount_cents,
                    account_id,
                    category_id,
                    due_date,
                    str(notes).strip(),
                    bill_id,
                ),
            )
            self._audit(
                con,
                "Editar",
                "compromisso",
                bill_id,
                {"antes": dict(old), "centavos": amount_cents},
            )

    def cancel_obligation(self, bill_id):
        with self.db.write() as con:
            row = con.execute(
                "SELECT * FROM obligations WHERE id=? AND status='Pendente'", (bill_id,)
            ).fetchone()
            if not row:
                raise FinanceError("Somente compromissos pendentes podem ser cancelados.")
            con.execute("UPDATE obligations SET status='Cancelado' WHERE id=?", (bill_id,))
            self._audit(con, "Cancelar", "compromisso", bill_id, dict(row))

    def summary(self, month):
        start, end = month_bounds(month)
        # Um snapshot de leitura evita combinar saldos de antes e depois de uma baixa simultânea.
        with self.db.read() as con:
            con.execute("BEGIN")
            realized = con.execute(
                """SELECT
                COALESCE(SUM(CASE WHEN kind='Receita' THEN amount_cents ELSE 0 END),0) AS income,
                COALESCE(SUM(CASE WHEN kind='Despesa' THEN amount_cents ELSE 0 END),0) AS expense
                FROM transactions WHERE status='Ativo' AND date BETWEEN ? AND ?""",
                (start, end),
            ).fetchone()
            income, expense = realized["income"], realized["expense"]
            balance = sum(r["balance_cents"] for r in con.execute(ACCOUNT_SQL))
            pending = con.execute(
                "SELECT kind,amount_cents,due_date FROM obligations WHERE status='Pendente'"
            ).fetchall()
            payable = sum(r["amount_cents"] for r in pending if r["kind"] == "Despesa")
            receivable = sum(r["amount_cents"] for r in pending if r["kind"] == "Receita")
            overdue = [r for r in pending if r["due_date"] < today().isoformat()]
        return dict(
            balance=balance,
            income=income,
            expense=expense,
            result=income - expense,
            payable=payable,
            receivable=receivable,
            projected=balance + receivable - payable,
            overdue_count=len(overdue),
            savings_rate=((income - expense) / income * 100 if income else None),
        )

    def daily_flow(self, start, end):
        start, end = date.fromisoformat(iso_date(start)), date.fromisoformat(iso_date(end))
        if end < start or (end - start).days > 366:
            raise FinanceError("Selecione um intervalo de até 366 dias.")
        with self.db.read() as con:
            con.execute("BEGIN")
            opening = con.execute("SELECT COALESCE(SUM(opening_cents),0) FROM accounts").fetchone()[
                0
            ]
            previous = con.execute(
                """SELECT COALESCE(SUM(CASE WHEN kind='Receita' THEN amount_cents
              WHEN kind='Despesa' THEN -amount_cents ELSE 0 END),0) FROM transactions WHERE status='Ativo' AND date<?""",
                (start.isoformat(),),
            ).fetchone()[0]
            period_txs = con.execute(
                "SELECT * FROM transactions WHERE status='Ativo' AND date BETWEEN ? AND ?",
                (start.isoformat(), end.isoformat()),
            ).fetchall()
        buckets = {}
        for tx in period_txs:
            if tx["kind"] == "Transferência":
                continue
            bucket = buckets.setdefault(tx["date"], {"income": 0, "expense": 0})
            bucket["income" if tx["kind"] == "Receita" else "expense"] += tx["amount_cents"]
        balance, rows = opening + previous, []
        for i in range((end - start).days + 1):
            on_date = (start + timedelta(days=i)).isoformat()
            values = buckets.get(on_date, {"income": 0, "expense": 0})
            balance += values["income"] - values["expense"]
            rows.append(dict(date=on_date, balance=balance, **values))
        return rows

    def forecast(self, days=30):
        base = today()
        balance = sum(a["balance_cents"] for a in self.accounts())
        buckets = {}
        for bill in self.obligations(status="Pendente", end=base + timedelta(days=days)):
            day = max(bill["due_date"], base.isoformat())
            buckets[day] = buckets.get(day, 0) + (
                bill["amount_cents"] if bill["kind"] == "Receita" else -bill["amount_cents"]
            )
        result = []
        for i in range(days + 1):
            day = (base + timedelta(days=i)).isoformat()
            balance += buckets.get(day, 0)
            result.append({"date": day, "balance": balance})
        return result

    def save_budget(self, category_id, month, limit_cents):
        month_bounds(month)
        valid_cents(limit_cents)
        with self.db.write() as con:
            self._category(con, category_id, "Despesa")
            con.execute(
                """INSERT INTO budgets(category_id,month,limit_cents) VALUES(?,?,?)
              ON CONFLICT(category_id,month) DO UPDATE SET limit_cents=excluded.limit_cents""",
                (category_id, month, limit_cents),
            )
            self._audit(
                con, "Salvar", "orçamento", category_id, {"mes": month, "centavos": limit_cents}
            )

    def budgets(self, month):
        start, end = month_bounds(month)
        with self.db.read() as con:
            return [
                dict(r)
                for r in con.execute(
                    """SELECT b.*,c.name AS category,c.color,
             COALESCE((SELECT SUM(t.amount_cents) FROM transactions t WHERE t.category_id=b.category_id
               AND t.kind='Despesa' AND t.status='Ativo' AND t.date BETWEEN ? AND ?),0) AS spent_cents
             FROM budgets b JOIN categories c ON c.id=b.category_id WHERE b.month=? ORDER BY c.name""",
                    (start, end, month),
                )
            ]

    def delete_budget(self, budget_id):
        with self.db.write() as con:
            con.execute("DELETE FROM budgets WHERE id=?", (budget_id,))
            self._audit(con, "Remover", "orçamento", budget_id, {})

    def create_goal(self, name, target_cents, due_date):
        name, due_date = text(name, "Nome da meta", 80), iso_date(due_date)
        valid_cents(target_cents)
        with self.db.write() as con:
            goal_id = con.execute(
                "INSERT INTO goals(name,target_cents,due_date) VALUES(?,?,?)",
                (name, target_cents, due_date),
            ).lastrowid
            self._audit(con, "Criar", "meta", goal_id, {"nome": name, "centavos": target_cents})
            return goal_id

    def goals(self):
        with self.db.read() as con:
            return [
                dict(r)
                for r in con.execute("""SELECT g.*,COALESCE((SELECT SUM(amount_cents)
              FROM goal_entries e WHERE e.goal_id=g.id),0) AS saved_cents FROM goals g ORDER BY g.due_date,g.id""")
            ]

    def contribute_goal(self, goal_id, amount_cents, on_date, notes=""):
        valid_cents(amount_cents, allow_negative=True)
        on_date = realized_date(on_date)
        if len(str(notes)) > 1000:
            raise FinanceError("Observações: limite de 1.000 caracteres.")
        with self.db.write() as con:
            if not con.execute("SELECT 1 FROM goals WHERE id=?", (goal_id,)).fetchone():
                raise FinanceError("Meta não encontrada.")
            saved = con.execute(
                "SELECT COALESCE(SUM(amount_cents),0) FROM goal_entries WHERE goal_id=?", (goal_id,)
            ).fetchone()[0]
            if saved + amount_cents < 0:
                raise FinanceError("A retirada não pode superar o valor reservado na meta.")
            con.execute(
                "INSERT INTO goal_entries(goal_id,amount_cents,date,notes) VALUES(?,?,?,?)",
                (goal_id, amount_cents, on_date, str(notes).strip()),
            )
            self._audit(con, "Aporte", "meta", goal_id, {"centavos": amount_cents})

    def goal_entries(self, goal_id):
        with self.db.read() as con:
            return [
                dict(r)
                for r in con.execute(
                    "SELECT * FROM goal_entries WHERE goal_id=? ORDER BY date DESC,id DESC",
                    (goal_id,),
                )
            ]

    def audit(self, limit=200):
        with self.db.read() as con:
            return [
                dict(r)
                for r in con.execute("SELECT * FROM audit ORDER BY id DESC LIMIT ?", (limit,))
            ]
