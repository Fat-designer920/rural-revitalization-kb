@echo off
title 乡村振兴知识库 - 初始化系统
cd /d "%~dp0"
if exist "python\python.exe" (set PYTHON_CMD=python\python.exe) else (set PYTHON_CMD=python)
chcp 65001 >nul
set PYTHONIOENCODING=utf-8
%PYTHON_CMD% scripts\setup.py
pause
