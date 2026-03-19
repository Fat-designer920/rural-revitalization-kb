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
%PYTHON_CMD% -m pip install --upgrade pip
%PYTHON_CMD% -m pip install requests flask cryptography pdfplumber python-docx openpyxl Pillow
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
echo   下一步: 将文件放入 data\pending\ 文件夹
echo   然后双击[处理新文件.bat]开始使用
echo   ========================================
pause
