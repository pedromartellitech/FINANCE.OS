@echo off
setlocal EnableExtensions DisableDelayedExpansion
cd /d "%~dp0"
title Finance OS

if not exist "app.py" goto :missing_project
if not exist "requirements.lock.txt" goto :missing_project

set "FO_ENV=.venv"
set "FO_PYTHON="

rem Reutiliza um ambiente existente somente quando ele for compativel.
if not exist ".venv\Scripts\python.exe" goto :find_python
".venv\Scripts\python.exe" -c "import sys,struct; sys.exit(0 if sys.version_info >= (3,12) and struct.calcsize('P') == 8 else 1)" >nul 2>&1
if not errorlevel 1 goto :install_dependencies
rem Preserva o ambiente antigo em vez de apaga-lo ou modifica-lo.
set "FO_ENV=.venv-finance-os"
if not exist "%FO_ENV%\Scripts\python.exe" goto :find_python
"%FO_ENV%\Scripts\python.exe" -c "import sys,struct; sys.exit(0 if sys.version_info >= (3,12) and struct.calcsize('P') == 8 else 1)" >nul 2>&1
if not errorlevel 1 goto :install_dependencies

:find_python
echo Procurando uma instalacao compativel do Python...
call :try_python py -3.12
call :try_python py -3.13
call :try_python python
call :try_python python3
call :try_python py -3
call :try_python "%LocalAppData%\Programs\Python\Python312\python.exe"
call :try_python "%LocalAppData%\Programs\Python\Python313\python.exe"
call :try_python "%ProgramFiles%\Python312\python.exe"
call :try_python "%ProgramFiles%\Python313\python.exe"
if not defined FO_PYTHON goto :missing_python

echo Criando o ambiente do Finance OS...
%FO_PYTHON% -m venv "%FO_ENV%"
if errorlevel 1 goto :environment_error

:install_dependencies
"%FO_ENV%\Scripts\python.exe" -m pip --version >nul 2>&1
if errorlevel 1 goto :environment_error
if exist "%FO_ENV%\finance-os-installed" goto :launch
echo Instalando dependencias. Aguarde a conclusao na primeira execucao...
"%FO_ENV%\Scripts\python.exe" -m pip install -r "requirements.lock.txt"
if errorlevel 1 goto :dependency_error
type nul > "%FO_ENV%\finance-os-installed"

:launch
"%FO_ENV%\Scripts\python.exe" "launcher.py" %*
if errorlevel 1 goto :launch_error
exit /b 0

:try_python
if defined FO_PYTHON exit /b 0
%* -c "import sys,struct; sys.exit(0 if sys.version_info >= (3,12) and struct.calcsize('P') == 8 else 1)" >nul 2>&1
if errorlevel 1 exit /b 0
set "FO_PYTHON=%*"
exit /b 0

:missing_python
echo.
echo Nao foi encontrado Python 3.12 ou superior de 64 bits.
echo Instale Python 3.12 ou 3.13 de 64 bits pelo site oficial:
echo https://www.python.org/downloads/windows/
echo No instalador tradicional, marque Add python.exe to PATH.
echo Depois feche esta janela e abra iniciar.bat novamente.
goto :failure

:missing_project
echo Extraia todos os arquivos do ZIP em uma pasta antes de iniciar.
echo Este iniciar.bat precisa ficar junto do app.py.
goto :failure

:environment_error
echo Nao foi possivel preparar o ambiente Python.
echo Confira a instalacao do Python e as permissoes desta pasta.
goto :failure

:dependency_error
echo A instalacao das dependencias nao terminou.
echo Confira a mensagem acima e sua conexao com a internet.
echo Ao executar novamente, a instalacao sera tentada outra vez.
goto :failure

:launch_error
echo O Finance OS encerrou com erro. Confira a mensagem acima.

:failure
echo.
pause
exit /b 1
