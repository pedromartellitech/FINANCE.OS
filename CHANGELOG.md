# Histórico

## Atualização visual · AntigaFuturistica — 01/11/2026

- Identidade retrô futurista com tons mais vivos, títulos clássicos e controles atuais.
- Ocultação da navegação automática das páginas antigas, preservando o menu do aplicativo.
- Paleta atualizada no tema, gráficos e seleção inicial de cor de novas categorias.
- Instalador de tema que preserva textos personalizados, servidor, ambiente e dados.
- Cópia dos arquivos visuais anteriores e reaplicação idempotente.

## Correção do iniciador Windows — 29/10/2026

- Detecção do Python por `py`, `python`, `python3` e diretórios comuns de instalação.
- Validação de versão e arquitetura, reaproveitamento de ambiente compatível e preservação de ambiente antigo.
- Mensagens específicas para Python ausente, extração incompleta e falhas na instalação das dependências.
- Revisão estática em Linux; execução real em Windows ainda pendente.

## 2.0.0 — 29/10/2026

- Interface redesenhada com identidade visual unificada, navegação central e seleção de mês.
- Autenticação local e demonstração isolada por sessão.
- Regras financeiras separadas da interface; valores em centavos e saldos derivados do histórico.
- Cadastro e edição de contas e categorias, com arquivamento preservando vínculos.
- Edição e estorno de receitas, despesas e transferências entre contas.
- Agenda de contas a pagar e a receber, parcelamento e recorrência mensal finita.
- Baixa atômica com proteção contra repetição; reabertura com estorno.
- Orçamentos mensais e metas com aportes/retiradas de planejamento.
- Relatórios, CSV, backup validado e cópia de recuperação na restauração.
- Migração com prévia do banco anterior, recuperação de baixas sem vínculo e reconciliação de saldo.
- Testes de domínio, concorrência, autenticação, portabilidade, migração e interface.
- Iniciadores locais, ambiente com versões fixadas, Docker/Compose e documentação.

## Base anterior

Aplicação Streamlit com contas financeiras, contas a pagar, lançamentos e SQLite. A versão 2 preserva a proposta e oferece uma migração explícita da estrutura anterior.
