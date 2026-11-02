"""Exclui o administrador e uma conta financeira sem vínculos, com backup local."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
import sqlite3
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))

from financeos.db import Database, default_database
from financeos.domain import FinanceError, brl
from financeos.service import FinanceService


def target_state(con, account_id: int):
    if con.execute("PRAGMA user_version").fetchone()[0] != 2:
        raise FinanceError("A base não é compatível com esta ferramenta do Finance OS 2.")
    owners = con.execute("SELECT * FROM users ORDER BY id").fetchall()
    if len(owners) != 1:
        raise FinanceError("É necessário haver exatamente um administrador cadastrado. Nenhum cadastro foi excluído.")
    account = con.execute("SELECT * FROM accounts WHERE id=?", (account_id,)).fetchone()
    if not account:
        raise FinanceError("Conta financeira não encontrada. Nenhum cadastro foi excluído.")
    entries = con.execute(
        "SELECT count(*) FROM transactions WHERE account_id=? OR peer_account_id=?",
        (account_id, account_id),
    ).fetchone()[0]
    bills = con.execute(
        "SELECT count(*) FROM obligations WHERE account_id=?", (account_id,)
    ).fetchone()[0]
    if entries or bills:
        raise FinanceError(
            f"Esta conta tem {entries} lançamento(s) e {bills} compromisso(s) vinculados, "
            "incluindo registros estornados ou cancelados. Nenhum cadastro foi excluído. "
            "Use Editar conta para corrigir o nome ou o tipo."
        )
    return {"owner": dict(owners[0]), "account": dict(account)}


def inspect_target(db: Database, account_id: int):
    if not db.path.is_file():
        raise FinanceError("Não foi encontrado o banco da instalação real. Confira FINANCE_OS_DATA_DIR; esta ferramenta não usa a demonstração.")
    with db.read() as con:
        return target_state(con, account_id)


def save_backup(db: Database) -> Path:
    folder = db.path.parent / "backups-cadastros"
    folder.mkdir(parents=True, exist_ok=True, mode=0o700)
    backup = folder / ("antes-dos-cadastros-" + datetime.now().strftime("%Y%m%d-%H%M%S-%f") + ".db")
    destination = sqlite3.connect(str(backup))
    try:
        with db.read() as source:
            source.backup(destination)
        if destination.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise FinanceError("A cópia de segurança não passou na verificação. Nenhum cadastro foi excluído.")
    finally:
        destination.close()
    try:
        backup.chmod(0o600)
    except OSError:
        pass
    return backup


def remove_registrations(db: Database, account_id: int, reviewed):
    # Revalida antes do backup e novamente sob bloqueio de escrita.
    if inspect_target(db, account_id) != reviewed:
        raise FinanceError("Os cadastros mudaram. Execute novamente para conferir os dados atuais.")
    backup = save_backup(db)
    with db.write() as con:
        state = target_state(con, account_id)
        if state != reviewed:
            raise FinanceError("Os cadastros mudaram durante a operação. Nenhum cadastro foi excluído.")
        owner = state["owner"]
        account = state["account"]
        con.execute("DELETE FROM accounts WHERE id=?", (account_id,))
        con.execute("DELETE FROM users WHERE id=?", (owner["id"],))
        service = FinanceService(db, "recuperacao-local")
        service._audit(con, "Excluir cadastro", "conta", account_id, {"nome": account["name"]})
        service._audit(con, "Excluir cadastro", "usuário", owner["id"], {"nome": owner["username"]})
    return backup


def main() -> int:
    db = default_database()
    try:
        if not db.path.is_file():
            raise FinanceError("Nenhuma instalação real encontrada. Esta ferramenta não altera os dados temporários da demonstração.")
        print("REFORMULAR CADASTROS DO FINANCE OS")
        print("Feche o Finance OS antes de continuar.")
        print("Banco selecionado:", db.path)
        with db.read() as con:
            accounts = con.execute("SELECT id,name,type FROM accounts ORDER BY name,id").fetchall()
        if not accounts:
            raise FinanceError("Nenhuma conta financeira cadastrada. Nenhum cadastro foi excluído.")
        print("\nEscolha a conta financeira criada por engano:")
        for index, row in enumerate(accounts, 1):
            print(f"  {index}. {row['name']} — {row['type']}")
        answer = input("Número da conta (Enter cancela): ").strip()
        if not answer:
            print("Operação cancelada.")
            return 0
        if not answer.isdecimal() or not 1 <= int(answer) <= len(accounts):
            raise FinanceError("Número inválido. Nenhum cadastro foi excluído.")
        account_id = accounts[int(answer) - 1]["id"]
        reviewed = inspect_target(db, account_id)
        print("\nUsuário de acesso a excluir:", reviewed["owner"]["username"])
        print("Conta financeira a excluir:", reviewed["account"]["name"])
        print("Saldo inicial dessa conta:", brl(reviewed["account"]["opening_cents"]))
        print("A conta não tem lançamentos nem compromissos vinculados.")
        print("Será guardado um backup antes da exclusão desses dois cadastros.")
        print("Os demais dados financeiros serão mantidos.")
        if input("Digite EXCLUIR para confirmar estes dois cadastros: ").strip() != "EXCLUIR":
            print("Operação cancelada.")
            return 0
        backup = remove_registrations(db, account_id, reviewed)
        print("\nOs dois cadastros foram excluídos.")
        print("Cópia de segurança:", backup)
        print("Abra o Finance OS sem --demo para criar seu usuário novamente.")
        print("Depois, cadastre a conta correta em Contas e categorias.")
        return 0
    except (FinanceError, OSError, sqlite3.Error) as exc:
        print("\nNão foi possível concluir:", exc)
        return 1
    except (EOFError, KeyboardInterrupt):
        print("\nOperação cancelada.")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
