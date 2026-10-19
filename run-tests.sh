#!/usr/bin/env bash
set -u

cd "$(dirname "$0")"

if [ -x ".venv/bin/python" ]; then
    PY=".venv/bin/python"
elif [ -x ".venv/Scripts/python.exe" ]; then
    PY=".venv/Scripts/python.exe"
elif [ -x "../.venv/bin/python" ]; then
    PY="../.venv/bin/python"
elif [ -x "../.venv/Scripts/python.exe" ]; then
    PY="../.venv/Scripts/python.exe"
else
    PY="python"
fi

echo "[1/3] Running tests with $PY ..."
"$PY" -m pytest "$@"
TEST_EXIT=$?

echo
echo "[2/3] Generating Allure report ..."
if [ -d "allure-results" ]; then
    if command -v allure >/dev/null 2>&1; then
        allure generate allure-results --clean -o allure-report
    else
        npx --yes allure-commandline generate allure-results --clean -o allure-report
    fi
fi

echo
echo "[3/3] Reports:"
echo "  pytest-html : reports/report.html"
echo "  coverage    : reports/coverage/index.html"
echo "  allure      : allure-report/index.html"
exit "$TEST_EXIT"
