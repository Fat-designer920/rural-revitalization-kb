@echo off
echo 乡村振兴知识库 - 审核反馈统计
chcp 65001 >nul 2>nul

REM 检测便携版Python
set PYTHON_CMD=
if exist "%~dp0python\python.exe" (
    set PYTHON_CMD=%~dp0python\python.exe
) else if exist "%~dp0python3\python.exe" (
    set PYTHON_CMD=%~dp0python3\python.exe
) else (
    where python >nul 2>nul
    if %errorlevel%==0 (
        set PYTHON_CMD=python
    ) else (
        echo [ERROR] 未找到Python，请检查安装
        pause
        exit /b 1
    )
)

cd /d "%~dp0"
%PYTHON_CMD% scripts/review_analytics.py
