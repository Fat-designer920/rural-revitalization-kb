@echo off
title 乡村振兴知识库 - 安装依赖库
cd /d "%~dp0"
if exist "python\python.exe" (set PYTHON_CMD=python\python.exe) else (set PYTHON_CMD=python)
chcp 65001 >nul
set PYTHONIOENCODING=utf-8
echo.
echo   ========================================
echo   正在安装依赖库, 请耐心等待...
echo   ========================================
echo.
%PYTHON_CMD% -m pip install --upgrade pip
%PYTHON_CMD% -m pip install requests flask cryptography pdfplumber python-docx openpyxl Pillow
echo.
echo   ========================================
echo   依赖库安装完成!
echo   ========================================
pause
