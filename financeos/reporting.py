"""Relatório HTML autônomo e imprimível, sem dependência de serviços externos."""

from html import escape

from financeos.domain import brl, month_bounds, today


def html_report(service, month):
    summary = service.summary(month)
    start, end = month_bounds(month)
    rows = service.transactions(start, end)
    cells = []
    for r in rows:
        cells.append(
            "<tr>"
            + "".join(
                f"<td>{escape(str(v))}</td>"
                for v in [
                    r["date"],
                    r["description"],
                    r["kind"],
                    r["category"] or "Transferência",
                    r["account"],
                    brl(r["amount_cents"]),
                ]
            )
            + "</tr>"
        )
    cards = "".join(
        f'<div class="card"><small>{label}</small><strong>{brl(summary[key])}</strong></div>'
        for label, key in [("Receitas", "income"), ("Despesas", "expense"), ("Resultado", "result")]
    )
    body = f"""<!doctype html><html lang="pt-BR"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Finance OS · Relatório {escape(month)}</title>
    <style>body{{font:14px/1.6 system-ui,sans-serif;color:#202137;max-width:1100px;margin:45px auto;padding:0 24px}}h1{{letter-spacing:-1px}}small,footer{{color:#64687f}}.cards{{display:flex;gap:18px;margin:28px 0}}.card{{padding:18px;border:1px solid #ddddec;border-radius:10px;flex:1}}strong{{display:block;font-size:24px}}table{{border-collapse:collapse;width:100%;font-size:12px}}th,td{{text-align:left;border-bottom:1px solid #e5e5ef;padding:10px 7px}}th{{background:#f4f3fa}}footer{{margin-top:30px;font-size:11px}}@media print{{body{{margin:0;max-width:none}}thead{{display:table-header-group}}tr{{break-inside:avoid}}}}</style></head><body>
    <small>FINANCE OS · GESTÃO FINANCEIRA</small><h1>{escape(service.workspace())}</h1><p>Relatório de caixa · {escape(month)} · emitido em {today().strftime("%d/%m/%Y")}</p>{cards}
    <p>Saldo consolidado de hoje: <b>{brl(summary["balance"])}</b>. O saldo de hoje considera todas as contas e independe do período do relatório.</p>
    <table><thead><tr><th>Data</th><th>Descrição</th><th>Tipo</th><th>Categoria</th><th>Conta</th><th>Valor</th></tr></thead><tbody>{"".join(cells) or '<tr><td colspan="6">Sem movimentações neste período.</td></tr>'}</tbody></table>
    <footer>Regime de caixa. Transferências não compõem receitas e despesas. Apenas lançamentos ativos. Relatório gerencial; não substitui escrituração contábil.</footer></body></html>"""
    return body.encode("utf-8")
