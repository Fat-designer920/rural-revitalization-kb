@echo off
title 乡村振兴知识库 - 保鲜检查
cd /d "%~dp0"
if exist "python\python.exe" (set PYTHON_CMD=python\python.exe) else (set PYTHON_CMD=python)
chcp 65001 >nul
set PYTHONIOENCODING=utf-8
echo.
echo   ============================================
echo   乡村振兴知识库 - 保鲜检查
echo   ============================================
echo.
%PYTHON_CMD% scripts\freshness_checker.py
echo.
pause