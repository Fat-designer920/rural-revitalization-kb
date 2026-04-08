@echo off
title 乡村振兴知识库 - 管理后台
cd /d "%~dp0"

REM === 便携Python检测 ===
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
        echo [错误] 未找到Python，请安装Python 3.8+或将便携版Python放入项目根目录的python文件夹中
        pause
        exit /b 1
    )
)

chcp 65001 >nul 2>nul
set PYTHONIOENCODING=utf-8

echo.
echo ============================================================
echo   乡村振兴知识库 - 管理后台 v2.1.2
echo   Tab1 知识审核 ^| Tab2 系统管理(仪表盘+工具箱)
echo ============================================================
echo.

%PYTHON_CMD% scripts/api_server.py

pause
