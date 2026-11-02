"""Aplica somente o tema e cores; preserva código personalizado e dados."""

from __future__ import annotations

import argparse
import ast
from datetime import datetime
import io
from pathlib import Path
import re
import shutil
import sys
import tokenize
import tomllib


THEME = '''[theme]
base = "dark"
primaryColor = "#FFAA56"
backgroundColor = "#0C1518"
secondaryBackgroundColor = "#192B2D"
textColor = "#F5E8CF"
borderColor = "#30474B"
font = "sans-serif"
'''

SIDEBAR = '''[theme.sidebar]
primaryColor = "#FFAA56"
backgroundColor = "#0A1215"
secondaryBackgroundColor = "#17272A"
textColor = "#E1EEE3"
borderColor = "#3A5858"
'''

# Somente literais de cor isolados: textos, funções e cálculos são preservados.
PALETTE = {
    "#b4a6ff": "#FFAA56", "#93edce": "#5DE4AF",
    "#78c4ff": "#63D7ED", "#ffbd74": "#FFD166",
    "#ff9aae": "#FF8178", "#c5a7ed": "#BD9FFF",
    "#84bbb5": "#65CDB4", "#eacb8d": "#F4D593",
    "#8d96ae": "#B0C4BE", "#a8b0c7": "#B9CCC5",
    "#292d40": "#30474B", "#955334": "#FFAA56",
    "#52765d": "#5DE4AF", "#424a3a": "#F5E8CF",
    "#6a6f61": "#B0C4BE", "#74786b": "#B0C4BE",
    "#626958": "#B9CCC5", "#e5dfd2": "#30474B",
    "#7b8c69": "#5DE4AF", "#c09a57": "#FFD166",
    "#617c82": "#63D7ED", "#b97765": "#FF8178",
    "#8b7b91": "#BD9FFF", "#a9a17d": "#F4D593",
    "#545f4d": "#65CDB4",
}


def replace_section(text: str, name: str, replacement: str) -> str:
    pattern = re.compile(r"(?ms)^\[" + re.escape(name) + r"\][^\n]*\n.*?(?=^\[|\Z)")
    replacement = replacement.rstrip() + "\n\n"
    if pattern.search(text):
        return pattern.sub(lambda _: replacement, text, count=1)
    return text.rstrip() + "\n\n" + replacement


def theme_config(text: str) -> str:
    if text.strip():
        tomllib.loads(text)
    text = replace_section(text, "theme", THEME)
    text = replace_section(text, "theme.sidebar", SIDEBAR)
    pattern = re.compile(r"(?ms)^\[client\][^\n]*\n.*?(?=^\[|\Z)")
    match = pattern.search(text)
    if match:
        client = match.group(0)
        setting = re.compile(r"(?m)^\s*showSidebarNavigation\s*=.*$")
        if setting.search(client):
            client = setting.sub("showSidebarNavigation = false", client)
        else:
            client = client.rstrip() + "\nshowSidebarNavigation = false\n"
        text = replace_section(text, "client", client)
    else:
        text = replace_section(text, "client", "[client]\nshowSidebarNavigation = false")
    parsed = tomllib.loads(text)
    assert parsed["client"]["showSidebarNavigation"] is False
    assert parsed["theme"]["base"] == "dark"
    return text.rstrip() + "\n"


def chart_colors(text: str) -> str:
    ast.parse(text)
    tokens = []
    for token in tokenize.generate_tokens(io.StringIO(text).readline):
        if token.type == tokenize.STRING:
            try:
                value = ast.literal_eval(token.string)
            except (SyntaxError, ValueError):
                value = None
            if isinstance(value, str) and value.lower() in PALETTE:
                quote = token.string[0] if token.string[0] in "\"'" else '"'
                token = token._replace(string=quote + PALETTE[value.lower()] + quote)
        tokens.append(token)
    updated = tokenize.untokenize(tokens)
    ast.parse(updated)
    return updated


def apply_theme(project: Path, payload: Path) -> list[str]:
    project = project.resolve()
    if not (project / "app.py").is_file() or not (project / "financeos/ui.py").is_file():
        raise ValueError("Pasta incorreta. Coloque este arquivo e a pasta tema-retrofuturista junto de app.py.")
    style = payload / "style.css"
    if not style.is_file():
        raise ValueError("A pasta tema-retrofuturista deve ficar junto deste arquivo.")
    config_path = project / ".streamlit/config.toml"
    config_before = config_path.read_text(encoding="utf-8-sig") if config_path.exists() else ""
    changes = {
        config_path: theme_config(config_before).encode("utf-8"),
        project / "assets/style.css": style.read_bytes(),
    }
    for relative in ("financeos/ui.py", "financeos/views/reports.py", "financeos/views/accounts.py"):
        path = project / relative
        if path.is_file():
            changes[path] = chart_colors(path.read_text(encoding="utf-8-sig")).encode("utf-8")
    changes = {path: content for path, content in changes.items()
               if not path.exists() or path.read_bytes() != content}
    if not changes:
        return []
    backup = project / "backups-visuais" / datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    originals = {}
    for path in changes:
        originals[path] = path.read_bytes() if path.exists() else None
        if path.exists():
            saved = backup / path.relative_to(project)
            saved.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, saved)
    written = []
    try:
        for path, content in changes.items():
            path.parent.mkdir(parents=True, exist_ok=True)
            temporary = path.with_name(path.name + ".visual-tmp")
            temporary.write_bytes(content)
            temporary.replace(path)
            written.append(path)
    except OSError:
        for path in written:
            if originals[path] is None:
                path.unlink(missing_ok=True)
            else:
                path.write_bytes(originals[path])
        raise
    return [str(path.relative_to(project)) for path in written]


def main() -> int:
    parser = argparse.ArgumentParser(description="Tema AntigaFuturistica do Finance OS")
    parser.add_argument("--project", type=Path, default=Path(__file__).resolve().parent)
    args = parser.parse_args()
    try:
        changed = apply_theme(args.project, Path(__file__).resolve().parent / "tema-retrofuturista")
    except (OSError, ValueError, SyntaxError, tokenize.TokenError) as exc:
        print("Não foi possível aplicar o visual:", exc)
        return 1
    print("Visual aplicado com sucesso." if changed else "O visual já está atualizado.")
    for relative in changed:
        print("  Atualizado:", relative)
    print("Menu antigo oculto. Reinicie o Finance OS e atualize o navegador com Ctrl + F5.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
