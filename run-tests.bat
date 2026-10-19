@echo off
setlocal
cd /d "%~dp0"

set "PY="
if exist ".venv\Scripts\python.exe" set "PY=.venv\Scripts\python.exe"
if not defined PY if exist "..\.venv\Scripts\python.exe" set "PY=..\.venv\Scripts\python.exe"
if not defined PY (
    echo [ERROR] Python virtual environment not found.
    echo Create one first:
    echo   python -m venv .venv
    echo   .venv\Scripts\pip install -r requirements.txt
    exit /b 1
)

echo [1/3] Running tests with %PY% ...
"%PY%" -m pytest %*
set "TEST_EXIT=%ERRORLEVEL%"

echo.
echo [2/3] Generating Allure report ...
if exist "allure-results" (
    where allure >nul 2>nul
    if not errorlevel 1 (
        call allure generate allure-results --clean -o allure-report
    ) else (
        call npx --yes allure-commandline generate allure-results --clean -o allure-report
    )
)

echo.
echo [3/3] Reports:
echo   pytest-html : reports\report.html
echo   coverage    : reports\coverage\index.html
echo   allure      : allure-report\index.html
exit /b %TEST_EXIT%
