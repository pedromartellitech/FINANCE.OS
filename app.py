"""Entrypoint. Nenhuma tela financeira é renderizada antes da autenticação."""

from __future__ import annotations

import logging
import os
import sqlite3
import tempfile
import time
from datetime import timedelta
from pathlib import Path

import streamlit as st

from financeos import __version__
from financeos.auth import authenticate, create_owner, credential_stamp, has_owner
from financeos.db import Database, default_database
from financeos.demo import seed_demo
from financeos.domain import FinanceError, add_months, today
from financeos.service import FinanceService
from financeos.ui import brand, heading, safe, style
from financeos.views import accounts, agenda, overview, planning, reports, settings, transactions

st.set_page_config(
    page_title="Finance OS · Clareza para crescer",
    page_icon="◈",
    layout="wide",
    initial_sidebar_state="expanded",
)
style()
logger = logging.getLogger("financeos")
PAGES = {
    "Visão geral": overview,
    "Movimentações": transactions,
    "Agenda financeira": agenda,
    "Contas e categorias": accounts,
    "Planejamento": planning,
    "Relatórios": reports,
    "Dados e ajustes": settings,
}
MONTH_NAMES = [
    "Janeiro",
    "Fevereiro",
    "Março",
    "Abril",
    "Maio",
    "Junho",
    "Julho",
    "Agosto",
    "Setembro",
    "Outubro",
    "Novembro",
    "Dezembro",
]


def logout():
    temp = st.session_state.get("demo_temp")
    for key in list(st.session_state):
        del st.session_state[key]
    if temp:
        temp.cleanup()
    st.rerun()


def start_demo():
    for key in list(st.session_state):
        if key.startswith(("setup_", "login_")):
            del st.session_state[key]
    temp = tempfile.TemporaryDirectory(prefix="financeos-demo-")
    db = Database(Path(temp.name) / "demo.db")
    db.initialize()
    seed_demo(FinanceService(db, "demo"))
    st.session_state.update(mode="demo", demo_temp=temp, demo_db=str(db.path), user="Demonstração")


def login_screen(db):
    left, right = st.columns([1.2, 1], gap="large", vertical_alignment="center")
    with left:
        brand()
        st.html(
            '<div class="fo-login-art"><div class="fo-login-tag">FINANCE OS · VERSÃO 2.0</div><h1>Mais clareza.<br>Mais espaço<br>para crescer.</h1><p>Seu financeiro merece um lugar simples. Organize o presente, planeje os próximos passos e acompanhe cada conquista.</p><div class="fo-login-features"><span>Fluxo de caixa</span><span>Contas e agenda</span><span>Metas e relatórios</span></div></div>'
        )
    with right:
        setup = not has_owner(db)
        heading(
            "Seu espaço começa aqui." if setup else "Bom ter você de volta.",
            "Crie o administrador desta instalação. A senha deve ter ao menos 12 caracteres."
            if setup
            else "Entre para continuar cuidando do seu financeiro.",
            "Primeiro acesso" if setup else "Acesso privado",
        )
        with st.form("setup_form" if setup else "login_form"):
            username = st.text_input(
                "Usuário",
                max_chars=40,
                key="setup_username" if setup else "login_username",
                placeholder="seu.usuario",
            )
            password = st.text_input(
                "Senha",
                type="password",
                max_chars=256,
                key="setup_password" if setup else "login_password",
            )
            workspace = (
                st.text_input(
                    "Nome do seu espaço",
                    max_chars=80,
                    placeholder="Ex.: Studio Martelli",
                    key="setup_workspace",
                )
                if setup
                else None
            )
            repeat = (
                st.text_input("Repita a senha", type="password", max_chars=256, key="setup_repeat")
                if setup
                else None
            )
            if st.form_submit_button(
                "Criar meu espaço" if setup else "Entrar no Finance OS",
                type="primary",
                width="stretch",
            ):
                try:
                    if setup:
                        if password != repeat:
                            raise FinanceError("As senhas não conferem.")
                        create_owner(db, username, password, workspace)
                    user = authenticate(db, username, password)
                    st.session_state.update(
                        mode="private",
                        user=user,
                        auth_stamp=credential_stamp(db, user),
                        login_at=time.time(),
                        last_activity=time.time(),
                    )
                    st.rerun()
                except FinanceError as exc:
                    st.error(str(exc))
        st.write("")
        st.caption(
            "Quer conhecer antes? A demonstração usa dados fictícios e permite testar os recursos."
        )
        if st.button("Explorar demonstração →", width="stretch", key="enter_demo"):
            start_demo()
            st.rerun()
        st.caption(
            "Os dados reais ficam no diretório desta instalação. A demonstração é independente e temporária."
        )
    st.stop()


def main():
    for key in st.session_state.pop("clear_on_rerun", []):
        st.session_state.pop(key, None)
    demo_only = os.getenv("FINANCE_OS_DEMO_ONLY", "0") == "1"
    if demo_only and st.session_state.get("mode") != "demo":
        start_demo()
    if st.session_state.get("mode") == "demo":
        db = Database(st.session_state["demo_db"])
    else:
        db = default_database()
        db.initialize()
        if st.session_state.get("mode") != "private":
            login_screen(db)
        if st.session_state.get("auth_stamp") != credential_stamp(db, st.session_state["user"]):
            logout()
        if (
            time.time() - st.session_state.get("last_activity", 0) > 1800
            or time.time() - st.session_state.get("login_at", 0) > 28800
        ):
            logout()
        st.session_state["last_activity"] = time.time()
    service = FinanceService(db, st.session_state["user"])
    with st.sidebar:
        brand()
        st.html(
            f'<div class="fo-workspace"><small>ESPAÇO FINANCEIRO</small>{safe(service.workspace())}</div>'
        )
        page = st.radio("Navegação", list(PAGES), label_visibility="collapsed", key="navigation")
        st.divider()
        base = today().replace(day=1)
        months = [add_months(base, i).strftime("%Y-%m") for i in range(3, -37, -1)]
        month = st.selectbox(
            "Período de análise",
            months,
            index=3,
            format_func=lambda m: f"{MONTH_NAMES[int(m[5:]) - 1]} {m[:4]}",
            key="global_month",
        )
        st.caption(
            "O período filtra as análises e o extrato. Saldos e compromissos consideram todo o histórico."
        )
        st.divider()
        st.caption(
            f"{st.session_state['user']} · {'Demo' if st.session_state['mode'] == 'demo' else 'Acesso privado'}"
        )
        if st.button(
            "Reiniciar demonstração" if demo_only else "Sair do espaço",
            width="stretch",
            key="logout",
        ):
            logout()
        st.caption(f"Finance OS {__version__} · por Pedro Martelli")
    if st.session_state["mode"] == "demo":
        st.html(
            '<div class="fo-demo">◈ DEMONSTRAÇÃO INTERATIVA · Dados fictícios e independentes por sessão. As alterações são temporárias.</div>'
        )
    if flash := st.session_state.pop("flash", None):
        st.success(flash)
    PAGES[page].render(service, month)
    st.html(
        '<div class="fo-footer"><span>financeos. · Clareza para crescer</span><span>Desenvolvido por Pedro Martelli · Python + Streamlit + SQLite</span></div>'
    )


try:
    main()
except FinanceError as exc:
    st.error(str(exc))
except sqlite3.Error:
    logger.exception("Falha ao acessar a base financeira")
    st.error(
        "Não foi possível concluir o acesso aos dados. Tente novamente. Se persistir, confira o diretório e as permissões da instalação."
    )
