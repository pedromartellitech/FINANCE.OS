"""Corrige somente o espaçamento superior do Finance OS; sem dependências extras."""

from __future__ import annotations

import argparse
from datetime import datetime
from pathlib import Path
import re
import shutil


START = "/* FINANCE_OS_SAFE_TOP_BEGIN */"
END = "/* FINANCE_OS_SAFE_TOP_END */"
SPACING = START + """
/* Reserva o espaço da barra fixa também após as regras responsivas do tema. */
.stMainBlockContainer,
[data-testid="stMainBlockContainer"] {
    padding-top: 6rem !important;
}
@media (max-width: 760px) {
    .stMainBlockContainer,
    [data-testid="stMainBlockContainer"] {
        padding-top: 5.5rem !important;
    }
}
""" + END


def corrected_css(source: str) -> str:
    pattern = re.compile(re.escape(START) + r".*?" + re.escape(END), re.DOTALL)
    source = pattern.sub("", source).rstrip()
    return source + "\n\n" + SPACING + "\n"


def correct(project: Path) -> list[str]:
    project = project.resolve()
    main = project / "assets/style.css"
    if not (project / "app.py").is_file() or not main.is_file():
        raise ValueError("Coloque este arquivo na pasta do projeto, junto de app.py.")
    paths = [main]
    payload = project / "tema-retrofuturista/style.css"
    if payload.is_file():
        paths.append(payload)
    changes = {}
    for path in paths:
        updated = corrected_css(path.read_text(encoding="utf-8-sig")).encode("utf-8")
        if updated != path.read_bytes():
            changes[path] = updated
    if not changes:
        return []
    backup = project / "backups-visuais" / ("topo-" + datetime.now().strftime("%Y%m%d-%H%M%S-%f"))
    for path in changes:
        target = backup / path.relative_to(project)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, target)
    for path, content in changes.items():
        temporary = path.with_name(path.name + ".topo-tmp")
        temporary.write_bytes(content)
        temporary.replace(path)
    return [str(path.relative_to(project)) for path in changes]


def main() -> int:
    parser = argparse.ArgumentParser(description="Corrigir o conteúdo cortado no topo do Finance OS")
    parser.add_argument("--project", type=Path, default=Path(__file__).resolve().parent)
    args = parser.parse_args()
    try:
        changed = correct(args.project)
    except (OSError, ValueError) as exc:
        print("Não foi possível aplicar a correção:", exc)
        return 1
    print("Espaçamento superior corrigido." if changed else "A correção já está aplicada.")
    print("Reinicie o Finance OS e pressione Ctrl + F5 no navegador.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
