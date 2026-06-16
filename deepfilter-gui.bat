@echo off
:: deepfilter-gui.bat — Launch DeepFilterNet GUI on Windows without activating venv.
SETLOCAL

SET "SCRIPT_DIR=%~dp0"
SET "REPO_ROOT=%SCRIPT_DIR%"

:: Priority 1: Repo-local venv
set "VENV_LOCAL=%REPO_ROOT%\.venv\Scripts\python.exe"

if exist "%VENV_LOCAL%" (
    set "VENV_PYTHON=%VENV_LOCAL%"
) else (
    echo Error: No virtual environment found at %VENV_LOCAL%
    echo Please run the setup steps first.
    pause
    exit /b 1
)

"%VENV_PYTHON%" -m gui.main %*
