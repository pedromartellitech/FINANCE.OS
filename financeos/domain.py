"""Regras de valor e data independentes da interface."""

from __future__ import annotations

import calendar
import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from zoneinfo import ZoneInfo


class FinanceError(ValueError):
    """Erro de negócio que pode ser apresentado ao usuário."""


MAX_CENTS = 999_999_999_99
KINDS = ("Receita", "Despesa", "Transferência")
ACCOUNT_TYPES = ("Conta corrente", "Conta digital", "Dinheiro", "Poupança", "Investimento")


def today() -> date:
    return datetime.now(ZoneInfo("America/Sao_Paulo")).date()


def money_to_cents(value: str, *, allow_negative: bool = False) -> int:
    """Aceita 1.234,56 ou 1234.56 sem aritmética de ponto flutuante."""
    raw = str(value).strip().replace("R$", "").strip()
    if "," in raw:
        if not re.fullmatch(r"-?(?:\d+|\d{1,3}(?:\.\d{3})+)(?:,\d{1,2})?", raw):
            raise FinanceError("Informe um valor como 1.234,56, com até duas casas decimais.")
        raw = raw.replace(".", "").replace(",", ".")
    elif not re.fullmatch(r"-?\d+(?:\.\d{1,2})?", raw):
        raise FinanceError("Informe um valor como 1234,56, com até duas casas decimais.")
    try:
        amount = Decimal(raw)
    except InvalidOperation as exc:
        raise FinanceError("Valor monetário inválido.") from exc
    cents = int(amount * 100)
    return valid_cents(cents, allow_zero=True, allow_negative=allow_negative)


def legacy_cents(value) -> int:
    """Conversão explícita dos REAL da versão antiga, arredondada para centavos."""
    try:
        d = Decimal(str(value or 0))
        if not d.is_finite():
            raise FinanceError("Valor não finito no banco antigo.")
        return valid_cents(
            int((d * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP)),
            allow_zero=True,
            allow_negative=True,
        )
    except (InvalidOperation, OverflowError) as exc:
        raise FinanceError("Valor inválido no banco antigo.") from exc


def valid_cents(value: int, *, allow_zero=False, allow_negative=False) -> int:
    if type(value) is not int or abs(value) > MAX_CENTS:
        raise FinanceError("Valor monetário fora do limite permitido.")
    if not allow_negative and value < 0:
        raise FinanceError("O valor não pode ser negativo.")
    if not allow_zero and value == 0:
        raise FinanceError("O valor precisa ser maior que zero.")
    return value


def brl(cents: int) -> str:
    sign = "−" if cents < 0 else ""
    n = abs(int(cents))
    whole = f"{n // 100:,}".replace(",", ".")
    return f"{sign}R$ {whole},{n % 100:02d}"


def input_money(cents: int) -> str:
    return ("-" if cents < 0 else "") + f"{abs(cents) // 100},{abs(cents) % 100:02d}"


def text(value, label="Descrição", limit=160) -> str:
    if not isinstance(value, str) or not value.strip() or len(value.strip()) > limit:
        raise FinanceError(f"{label}: preencha de 1 a {limit} caracteres.")
    return value.strip()


def iso_date(value) -> str:
    try:
        return date.fromisoformat(str(value)).isoformat()
    except (ValueError, TypeError) as exc:
        raise FinanceError("Data inválida. Use AAAA-MM-DD.") from exc


def realized_date(value) -> str:
    value = iso_date(value)
    if value > today().isoformat():
        raise FinanceError("Lançamentos realizados não podem ter data futura. Use a agenda.")
    return value


def add_months(value: date, months: int) -> date:
    month = value.year * 12 + value.month - 1 + months
    year, index = divmod(month, 12)
    return date(year, index + 1, min(value.day, calendar.monthrange(year, index + 1)[1]))


def month_bounds(month: str) -> tuple[str, str]:
    try:
        first = date.fromisoformat(month + "-01")
    except (ValueError, TypeError) as exc:
        raise FinanceError("Mês inválido.") from exc
    return first.isoformat(), date(
        first.year, first.month, calendar.monthrange(first.year, first.month)[1]
    ).isoformat()
