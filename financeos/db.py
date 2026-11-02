"""SQLite com integridade referencial, WAL e transações de escrita atômicas."""

from __future__ import annotations

import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path

SCHEMA_VERSION = 2
DEFAULT_CATEGORIES = [
    ("Serviços", "Receita", "#5DE4B2"),
    ("Vendas", "Receita", "#78C4FF"),
    ("Salário", "Receita", "#A999FF"),
    ("Outras receitas", "Receita", "#93A3BB"),
    ("Moradia", "Despesa", "#A999FF"),
    ("Alimentação", "Despesa", "#FFBD74"),
    ("Transporte", "Despesa", "#78C4FF"),
    ("Saúde", "Despesa", "#FF8196"),
    ("Educação", "Despesa", "#5DE4B2"),
    ("Lazer", "Despesa", "#F69CDB"),
    ("Assinaturas", "Despesa", "#7C91FF"),
    ("Operação", "Despesa", "#B6BDCE"),
    ("Impostos e taxas", "Despesa", "#F1CA79"),
    ("Outras despesas", "Despesa", "#93A3BB"),
]

SCHEMA = """
CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS users (
 id INTEGER PRIMARY KEY, username TEXT NOT NULL UNIQUE COLLATE NOCASE,
 password_hash TEXT NOT NULL, failed_attempts INTEGER NOT NULL DEFAULT 0,
 locked_until REAL NOT NULL DEFAULT 0, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS accounts (
 id INTEGER PRIMARY KEY, name TEXT NOT NULL UNIQUE COLLATE NOCASE,
 type TEXT NOT NULL, opening_cents INTEGER NOT NULL CHECK(typeof(opening_cents)='integer'),
 active INTEGER NOT NULL DEFAULT 1 CHECK(active IN (0,1)),
 created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS categories (
 id INTEGER PRIMARY KEY, name TEXT NOT NULL COLLATE NOCASE,
 kind TEXT NOT NULL CHECK(kind IN ('Receita','Despesa')),
 color TEXT NOT NULL DEFAULT '#A999FF', active INTEGER NOT NULL DEFAULT 1 CHECK(active IN (0,1)),
 UNIQUE(name,kind)
);
CREATE TABLE IF NOT EXISTS transactions (
 id INTEGER PRIMARY KEY, description TEXT NOT NULL,
 kind TEXT NOT NULL CHECK(kind IN ('Receita','Despesa','Transferência')),
 amount_cents INTEGER NOT NULL CHECK(typeof(amount_cents)='integer' AND amount_cents>0),
 account_id INTEGER NOT NULL REFERENCES accounts(id) ON DELETE RESTRICT,
 peer_account_id INTEGER REFERENCES accounts(id) ON DELETE RESTRICT,
 category_id INTEGER REFERENCES categories(id) ON DELETE RESTRICT,
 date TEXT NOT NULL, method TEXT NOT NULL DEFAULT 'Pix', notes TEXT NOT NULL DEFAULT '',
 status TEXT NOT NULL DEFAULT 'Ativo' CHECK(status IN ('Ativo','Estornado')),
 import_key TEXT UNIQUE, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
 CHECK((kind='Transferência' AND peer_account_id IS NOT NULL AND peer_account_id<>account_id AND category_id IS NULL)
   OR (kind<>'Transferência' AND peer_account_id IS NULL AND category_id IS NOT NULL))
);
CREATE INDEX IF NOT EXISTS idx_tx_date ON transactions(date,status);
CREATE INDEX IF NOT EXISTS idx_tx_account ON transactions(account_id);
CREATE TABLE IF NOT EXISTS obligations (
 id INTEGER PRIMARY KEY, description TEXT NOT NULL,
 kind TEXT NOT NULL CHECK(kind IN ('Receita','Despesa')),
 amount_cents INTEGER NOT NULL CHECK(typeof(amount_cents)='integer' AND amount_cents>0),
 account_id INTEGER NOT NULL REFERENCES accounts(id), category_id INTEGER NOT NULL REFERENCES categories(id),
 due_date TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'Pendente' CHECK(status IN ('Pendente','Liquidado','Cancelado')),
 settled_date TEXT, transaction_id INTEGER UNIQUE REFERENCES transactions(id),
 series_id TEXT, installment INTEGER NOT NULL DEFAULT 1, total_installments INTEGER NOT NULL DEFAULT 1,
 notes TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
 CHECK((status='Liquidado' AND transaction_id IS NOT NULL AND settled_date IS NOT NULL)
   OR (status<>'Liquidado' AND transaction_id IS NULL AND settled_date IS NULL))
);
CREATE INDEX IF NOT EXISTS idx_due_status ON obligations(status,due_date);
CREATE TABLE IF NOT EXISTS budgets (
 id INTEGER PRIMARY KEY, category_id INTEGER NOT NULL REFERENCES categories(id),
 month TEXT NOT NULL, limit_cents INTEGER NOT NULL CHECK(typeof(limit_cents)='integer' AND limit_cents>0),
 UNIQUE(category_id,month)
);
CREATE TABLE IF NOT EXISTS goals (
 id INTEGER PRIMARY KEY, name TEXT NOT NULL, target_cents INTEGER NOT NULL CHECK(typeof(target_cents)='integer' AND target_cents>0),
 due_date TEXT NOT NULL, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS goal_entries (
 id INTEGER PRIMARY KEY, goal_id INTEGER NOT NULL REFERENCES goals(id) ON DELETE CASCADE,
 amount_cents INTEGER NOT NULL CHECK(typeof(amount_cents)='integer' AND amount_cents<>0),
 date TEXT NOT NULL, notes TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS audit (
 id INTEGER PRIMARY KEY, action TEXT NOT NULL, entity TEXT NOT NULL,
 entity_id INTEGER, detail TEXT NOT NULL, actor TEXT NOT NULL,
 created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
"""


class Database:
    def __init__(self, path: str | Path):
        self.path = Path(path).expanduser().resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)

    def connect(self):
        con = sqlite3.connect(str(self.path), timeout=15, isolation_level=None)
        con.row_factory = sqlite3.Row
        con.execute("PRAGMA foreign_keys=ON")
        con.execute("PRAGMA busy_timeout=15000")
        return con

    @contextmanager
    def read(self):
        con = self.connect()
        try:
            yield con
        finally:
            con.close()

    @contextmanager
    def write(self):
        con = self.connect()
        try:
            con.execute("BEGIN IMMEDIATE")
            yield con
            con.commit()
        except Exception:
            con.rollback()
            raise
        finally:
            con.close()

    def initialize(self):
        with self.read() as con:
            version = con.execute("PRAGMA user_version").fetchone()[0]
            if version not in (0, SCHEMA_VERSION):
                raise RuntimeError("Versão de banco incompatível. Atualize o Finance OS.")
            old = con.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='contas'"
            ).fetchone()
            if old:
                raise RuntimeError(
                    "Banco legado detectado. Importe pela tela Dados em uma instalação nova."
                )
            con.execute("PRAGMA journal_mode=WAL")
            con.executescript(SCHEMA)
        with self.write() as con:
            con.executemany(
                "INSERT OR IGNORE INTO categories(name,kind,color) VALUES(?,?,?)",
                DEFAULT_CATEGORIES,
            )
            con.execute("INSERT OR IGNORE INTO settings VALUES('workspace','Meu negócio')")
            con.execute(f"PRAGMA user_version={SCHEMA_VERSION}")
        try:
            self.path.chmod(0o600)
        except OSError:
            pass


def default_database() -> Database:
    root = Path(os.getenv("FINANCE_OS_DATA_DIR", str(Path.home() / ".finance-os")))
    return Database(root / "finance_os_v2.db")
