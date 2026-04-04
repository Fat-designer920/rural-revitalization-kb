@echo off
chcp 65001 > nul
cd /d "%~dp0"
title 重复检测 - 乡村振兴知识库

REM 检查便携Python
if exist "python\python.exe" (
    set PYTHON_CMD=python\python.exe
) else if exist "Python\python.exe" (
    set PYTHON_CMD=Python\python.exe
) else (
    set PYTHON_CMD=python
)

set PYTHONIOENCODING=utf-8
echo.
echo ============================================================
echo   重复知识点检测 - 全库扫描
echo   检测方式: 本地粗筛 + V3 AI精判
echo ============================================================
echo.
%PYTHON_CMD% scripts/duplicate_checker.py

