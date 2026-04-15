@echo off
cd /d "%~dp0"

REM === 检测Python环境 ===
set PYTHON_CMD=
if exist "python\python.exe" (
    set PYTHON_CMD=python\python.exe
) else if exist "Python\python.exe" (
    set PYTHON_CMD=Python\python.exe
) else (
    where python >nul 2>nul
    if %errorlevel%==0 (
        set PYTHON_CMD=python
    ) else (
        echo [ERROR] Python not found. Please install Python 3.8+
        pause
        exit /b 1
    )
)

title 乡村振兴知识库 - 管理后台
echo.
echo ============================================================
echo   乡村振兴知识库 - 管理后台 v2.2.0
echo   Tab1 知识审核 ^| Tab2 系统管理
echo ============================================================
echo.

REM === 切换UTF-8（在中文echo之后，Python之前） ===
chcp 65001 >nul 2>nul
set PYTHONIOENCODING=utf-8

%PYTHON_CMD% scripts/api_server.py

pause