@echo off
title 乡村振兴知识库 - 审核反馈统计
cd /d "%~dp0"
if exist "python\python.exe" (set PYTHON_CMD=python\python.exe) else (set PYTHON_CMD=python)
chcp 65001 >nul
set PYTHONIOENCODING=utf-8
echo.
echo   ============================================
echo   乡村振兴知识库 - 审核反馈统计
echo   ============================================
echo.
%PYTHON_CMD% scripts\review_analytics.py
echo.
pause