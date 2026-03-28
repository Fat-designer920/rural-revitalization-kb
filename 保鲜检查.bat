@echo off
chcp 65001 >nul 2>&1
echo ============================================================
echo   乡村振兴知识库 - 保鲜检查
echo ============================================================
echo.

if exist "python\python.exe" (
    set PYTHON_CMD=python\python.exe
) else (
    set PYTHON_CMD=python
)

%PYTHON_CMD% scripts/freshness_checker.py

echo.
pause
