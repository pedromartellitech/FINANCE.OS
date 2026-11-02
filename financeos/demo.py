"""Cenário fictício, com datas relativas, isolado por sessão."""

from datetime import timedelta

from financeos.domain import add_months, today
from financeos.service import FinanceService


def seed_demo(service: FinanceService):
    if service.accounts():
        return
    service.set_workspace("Studio Martelli · Demo")
    operating = service.create_account("Conta principal", "Conta digital", 685000)
    reserve = service.create_account("Reserva estratégica", "Poupança", 320000)
    wallet = service.create_account("Carteira", "Dinheiro", 25000)
    cats = {(c["name"], c["kind"]): c["id"] for c in service.categories()}
    base = today()
    for month_back in range(3, -1, -1):
        first = add_months(base.replace(day=1), -month_back)
        entries = [
            (
                2,
                "Projeto de identidade digital",
                "Receita",
                340000 + month_back * 15000,
                "Serviços",
            ),
            (5, "Manutenção de sistemas", "Receita", 165000, "Serviços"),
            (8, "Coworking e estrutura", "Despesa", 85000, "Moradia"),
            (10, "Ferramentas de trabalho", "Despesa", 18990, "Assinaturas"),
            (13, "Almoço da equipe", "Despesa", 24590, "Alimentação"),
            (16, "Deslocamento a cliente", "Despesa", 12650, "Transporte"),
            (18, "Consultoria de automação", "Receita", 245000, "Serviços"),
            (21, "Curso de arquitetura", "Despesa", 29900, "Educação"),
            (24, "Tributos e taxas", "Despesa", 42650, "Impostos e taxas"),
            (26, "Infraestrutura de nuvem", "Despesa", 17800, "Operação"),
        ]
        for day, description, kind, cents, category in entries:
            on_date = first.replace(day=day)
            if on_date <= base:
                service.create_transaction(
                    description, kind, cents, operating, cats[(category, kind)], on_date
                )
    service.create_transaction(
        "Reserva mensal",
        "Transferência",
        80000,
        operating,
        None,
        base - timedelta(days=1),
        peer_account_id=reserve,
    )
    service.create_obligations(
        "Assinatura de design",
        "Despesa",
        8990,
        operating,
        cats[("Assinaturas", "Despesa")],
        base - timedelta(days=2),
    )
    service.create_obligations(
        "Entrega · Loja Aurora",
        "Receita",
        185000,
        operating,
        cats[("Serviços", "Receita")],
        base + timedelta(days=3),
    )
    service.create_obligations(
        "Internet do escritório",
        "Despesa",
        12990,
        operating,
        cats[("Operação", "Despesa")],
        base + timedelta(days=5),
        count=3,
        mode="Recorrente",
    )
    service.create_obligations(
        "Notebook de trabalho",
        "Despesa",
        360000,
        operating,
        cats[("Operação", "Despesa")],
        base + timedelta(days=10),
        count=6,
        mode="Parcelado",
    )
    month = base.strftime("%Y-%m")
    for name, limit in [
        ("Alimentação", 50000),
        ("Assinaturas", 25000),
        ("Operação", 30000),
        ("Transporte", 25000),
    ]:
        service.save_budget(cats[(name, "Despesa")], month, limit)
    goal = service.create_goal("Reserva de tranquilidade", 2000000, base + timedelta(days=180))
    service.contribute_goal(
        goal, 780000, base - timedelta(days=7), "Reserva já acumulada · exemplo fictício"
    )
    goal = service.create_goal("Novo setup de trabalho", 800000, base + timedelta(days=120))
    service.contribute_goal(goal, 235000, base - timedelta(days=3))
