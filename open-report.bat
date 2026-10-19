@echo off
setlocal
cd /d "%~dp0"

if not exist "allure-report\index.html" (
    echo Allure report not found. Run run-tests.bat first.
    exit /b 1
)

where allure >nul 2>nul
if %errorlevel%==0 (
    echo Opening Allure report in browser...
    start "Allure Report" cmd /c "allure open allure-report"
) else (
    echo Allure CLI not found, trying npx...
    start "Allure Report" cmd /c "npx --yes allure-commandline open allure-report"
)
