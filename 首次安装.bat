@echo off
title 乡村振兴知识库 - 首次安装
cd /d "%~dp0"
if exist "python\python.exe" (set PYTHON_CMD=python\python.exe) else (set PYTHON_CMD=python)
chcp 65001 >nul
set PYTHONIOENCODING=utf-8
echo.
echo   ========================================
echo   乡村振兴知识库 - 首次安装向导
echo   ========================================
echo.
echo   [1/3] 安装依赖库...
echo.
%PYTHON_CMD% -m pip install --upgrade pip 2>nul
%PYTHON_CMD% -m pip install requests flask cryptography pdfplumber python-docx openpyxl Pillow 2>nul
if %errorlevel% neq 0 (
    echo.
    echo   尝试备用安装方式...
    %PYTHON_CMD% -m pip install --break-system-packages requests flask cryptography pdfplumber python-docx openpyxl Pillow
)
echo.
echo   [2/3] 初始化系统...
echo.
%PYTHON_CMD% scripts\setup.py
echo.
echo   [3/3] 启动配置向导...
echo.
%PYTHON_CMD% scripts\config_wizard.py
echo.
echo   ========================================
echo   首次安装完成!
echo   下一步: 双击[启动后台.bat]进入管理后台
echo   在Tab2系统管理中完成文件预处理和知识提取
echo   ========================================
pause
