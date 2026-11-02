"""Autenticação de uma instalação privada; sem senhas padrão."""

from __future__ import annotations

import hashlib
import hmac
import re
import secrets
import time

from financeos.db import Database
from financeos.domain import FinanceError, text

ITERATIONS = 600_000


def password_hash(password: str) -> str:
    if not isinstance(password, str) or not 12 <= len(password) <= 256:
        raise FinanceError("Use uma senha de 12 a 256 caracteres.")
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), ITERATIONS).hex()
    return f"pbkdf2_sha256${ITERATIONS}${salt}${digest}"


def verify_password(password: str, encoded: str) -> bool:
    try:
        algorithm, rounds, salt, expected = encoded.split("$")
        if algorithm != "pbkdf2_sha256" or not 100_000 <= int(rounds) <= 2_000_000:
            return False
        digest = hashlib.pbkdf2_hmac(
            "sha256", password.encode(), bytes.fromhex(salt), int(rounds)
        ).hex()
        return hmac.compare_digest(digest, expected)
    except (ValueError, TypeError, AttributeError):
        return False


def has_owner(db: Database) -> bool:
    with db.read() as con:
        return con.execute("SELECT count(*) FROM users").fetchone()[0] > 0


def credential_stamp(db: Database, username: str) -> str:
    """Invalida sessões existentes após uma troca administrativa da senha."""
    with db.read() as con:
        row = con.execute(
            "SELECT password_hash FROM users WHERE username=?", (username,)
        ).fetchone()
        return hashlib.sha256(row[0].encode()).hexdigest() if row else ""


def create_owner(db: Database, username: str, password: str, workspace: str):
    username = text(username, "Usuário", 40).lower()
    if not re.fullmatch(r"[a-z0-9_.-]{3,40}", username):
        raise FinanceError("Usuário: use de 3 a 40 letras sem acento, números, ponto ou traço.")
    workspace = text(workspace, "Nome do espaço", 80)
    encoded = password_hash(password)
    with db.write() as con:
        if con.execute("SELECT 1 FROM users").fetchone():
            raise FinanceError("O administrador já foi criado. Faça login.")
        con.execute("INSERT INTO users(username,password_hash) VALUES(?,?)", (username, encoded))
        con.execute("UPDATE settings SET value=? WHERE key='workspace'", (workspace,))


def authenticate(db: Database, username: str, password: str) -> str:
    if not isinstance(password, str) or len(password) > 256:
        raise FinanceError("Usuário ou senha incorretos.")
    username = str(username).strip().lower()[:40]
    error = None
    # O bloqueio é persistido no banco e não desaparece ao atualizar a página.
    with db.write() as con:
        row = con.execute("SELECT * FROM users WHERE username=?", (username,)).fetchone()
        if row and row["locked_until"] > time.time():
            error = "Muitas tentativas. Aguarde 5 minutos e tente novamente."
        elif row and verify_password(password, row["password_hash"]):
            con.execute(
                "UPDATE users SET failed_attempts=0, locked_until=0 WHERE id=?", (row["id"],)
            )
            return row["username"]
        else:
            if row:
                failures = row["failed_attempts"] + 1 if row["locked_until"] == 0 else 1
                locked = time.time() + 300 if failures >= 5 else 0
                con.execute(
                    "UPDATE users SET failed_attempts=?,locked_until=? WHERE id=?",
                    (failures, locked, row["id"]),
                )
            else:
                hashlib.pbkdf2_hmac("sha256", password.encode(), b"unknown-user-salt", ITERATIONS)
            error = "Usuário ou senha incorretos."
    raise FinanceError(error)


def change_password(db: Database, username: str, current: str, new: str):
    encoded = password_hash(new)
    with db.write() as con:
        row = con.execute("SELECT * FROM users WHERE username=?", (username,)).fetchone()
        if not row or not verify_password(current, row["password_hash"]):
            raise FinanceError("A senha atual não confere.")
        con.execute(
            "UPDATE users SET password_hash=?,failed_attempts=0,locked_until=0 WHERE id=?",
            (encoded, row["id"]),
        )
