![Finance OS — Clareza para crescer](assets/cover.svg)

# Finance OS

**Gestão financeira com foco em clareza, integridade dos dados e uso prático.**

Aplicação local em Python para autônomos, freelancers e pequenos negócios. Reúne contas, movimentações, pagamentos e recebimentos, orçamentos, metas e relatórios em um espaço privado. Desenvolvido por **Pedro Martelli**.

A identidade **AntigaFuturistica** combina grafite, cobre iluminado, jade e ciano, com títulos clássicos e controles atuais. O modo demonstração oferece dados fictícios para explorar o projeto.

![Python 3.12+](https://img.shields.io/badge/Python-3.12%2B-FFAA56?style=flat-square)
![Streamlit](https://img.shields.io/badge/Interface-Streamlit-5DE4AF?style=flat-square)
![SQLite](https://img.shields.io/badge/Dados-SQLite-63D7ED?style=flat-square)
![Version 2.0](https://img.shields.io/badge/Vers%C3%A3o-2.0-FFBD74?style=flat-square)

## O problema que resolve

Planilhas dispersas dificultam entender o saldo, acompanhar vencimentos e separar uma transferência de uma receita. O Finance OS reúne essas tarefas e calcula os indicadores a partir de um histórico consistente. Compromissos futuros ficam separados de movimentações realizadas e só impactam o caixa quando recebem baixa.

## O que você pode fazer

| Área | Recursos |
| --- | --- |
| **Visão geral** | Saldo consolidado, entradas e saídas por mês, histórico diário, categorias e projeção dos próximos 30 dias |
| **Movimentações** | Receitas, despesas, transferências, pesquisa, filtros, edição, estorno e CSV |
| **Agenda** | Contas a pagar e a receber, parcelamentos exatos, recorrências mensais finitas, baixa e reabertura |
| **Organização** | Contas ativas/arquivadas, saldo inicial, categorias personalizadas e cores |
| **Planejamento** | Limites mensais por categoria e metas com histórico de aportes e retiradas |
| **Relatórios** | Comparação de seis meses, resultado, despesas por categoria e relatório HTML para impressão |
| **Dados** | CSV com prévia, backup e restauração JSON, migração da versão antiga e histórico de ações |
| **Acesso** | Administrador criado no primeiro uso, senha com hash/salt, bloqueio de tentativas e expiração da sessão |
| **Demonstração** | Dados fictícios e banco temporário independente por sessão |

## Executar no seu computador

Requer **Python 3.12 ou superior** e internet apenas para a primeira instalação das dependências.

**Windows — instalação pelo Prompt:** abra o terminal na pasta do projeto e execute um comando por vez:

```bat
python -m venv .venv
.venv\Scripts\python.exe -m pip install --upgrade pip
.venv\Scripts\python.exe -m pip install --no-cache-dir --only-binary=:all: -r requirements.txt
.venv\Scripts\python.exe launcher.py --demo
```

Para uso com dados persistentes, execute o último comando sem `--demo`. Crie seu usuário no primeiro acesso e cadastre uma conta com o saldo inicial. Mantenha o terminal aberto durante o uso. O `iniciar.bat` também está disponível como alternativa.

**Linux/macOS:**

```bash
sh iniciar.sh
# Somente demonstração:
sh iniciar.sh --demo
```

**Instalação manual:**

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
# Linux/macOS: source .venv/bin/activate
python -m pip install -r requirements.lock.txt
python launcher.py
```

Abra [http://127.0.0.1:8501](http://127.0.0.1:8501). O primeiro acesso cria seu administrador. A aplicação escuta apenas na interface local por padrão. Não há credenciais embutidas.

Para demonstração: `python launcher.py --demo`. Para outra porta: `python launcher.py --port 8502`. Para não abrir o navegador automaticamente: `python launcher.py --no-browser`.

## O que torna a implementação consistente

- **Centavos inteiros:** operações financeiras sem acumular erros de `float`.
- **Saldo calculado pelo histórico:** não existe um campo de saldo atual que precise ser atualizado em vários lugares.
- **Operações atômicas:** baixa e lançamento são gravados juntos; uma segunda baixa do mesmo compromisso é recusada, inclusive sob concorrência.
- **Transferência com origem/destino:** uma movimentação interna não aumenta receita nem despesa.
- **Histórico preservado:** estorno mantém o registro e desfazer uma baixa reabre o compromisso.
- **Restauração validada:** estrutura, referências e valores são conferidos antes da substituição; uma cópia de recuperação é criada.
- **Regras fora da interface:** domínio, persistência e casos de uso podem ser exercitados sem abrir o navegador.

## Testes

```bash
python -m pip install -r requirements-dev.txt
python -m pytest -q
```

**Validação local: 70 testes passaram em Linux/Python 3.12.** A execução do workflow no GitHub será um resultado separado, disponível na aba Actions do repositório.

Os testes cobrem conversão monetária, transferências, edição/estorno, baixas simultâneas, parcelamento, recorrência, orçamentos, metas, CSV, backup, migração, login e interações com as telas via Streamlit AppTest. Há um workflow de GitHub Actions para rodar a suíte em Python 3.12 e 3.13 quando o projeto for enviado a um repositório.

Consulte [o registro de validação](docs/VALIDACAO.md) para o resultado desta entrega e seus limites.

## Seus dados

O banco fica em `~/.finance-os/finance_os_v2.db`, fora do código. Você pode alterar o diretório com a variável de ambiente `FINANCE_OS_DATA_DIR`. O arquivo `.env.example` é uma referência; variáveis não são carregadas automaticamente de um `.env`.

Use **Dados e ajustes → Backup** para gerar uma cópia portátil. O JSON não inclui senhas nem auditoria. O login não cifra os arquivos; proteja o computador e os backups.

O projeto distribuído não contém a base financeira pessoal do autor nem ambientes virtuais. Para migrar o projeto anterior, envie uma cópia de `database/finance_os.db` pela tela de migração e confira a prévia. O banco antigo não é alterado.

## Docker

```bash
docker compose up --build -d
```

O Compose publica apenas `127.0.0.1:8501` e usa um volume persistente. A imagem executa como usuário sem privilégios. Esse caminho está preparado, mas não foi executado neste ambiente; veja a validação antes de usar em uma entrega.

## Usar em portfólio ou oferecer a clientes

O escopo desta versão é **um administrador e um espaço financeiro por instalação**. É uma base para uso local, demonstração e entrega assistida a clientes. Não implementa vários clientes no mesmo banco, faturamento de assinaturas ou integração bancária.

O [guia de comercialização](docs/COMERCIALIZACAO.md) descreve o roteiro de demonstração, a instalação por cliente e o que precisa ser validado no ambiente de entrega. Hospedagem pública, operação com vários clientes e integrações são etapas adicionais.

## Documentação

- [Manual de uso e migração](docs/MANUAL.md)
- [Arquitetura e decisões técnicas](docs/ARQUITETURA.md)
- [Demonstração e comercialização](docs/COMERCIALIZACAO.md)
- [Validação da entrega](docs/VALIDACAO.md)
- [Atualização do tema](docs/ATUALIZACAO_VISUAL.md)
- [Refazer cadastros incorretos](docs/REFAZER_CADASTROS.md)
- [Evolução da versão](CHANGELOG.md)

## Autoria e uso

**Pedro Martelli** · Projeto de portfólio e produto em evolução.

Não foi atribuída automaticamente uma licença aberta ao projeto. A redistribuição e a comercialização devem seguir os termos definidos pelo titular do código e as licenças das dependências. Veja [LICENSE](LICENSE).
