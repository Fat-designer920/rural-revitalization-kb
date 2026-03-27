@echo off
title 乡村振兴知识库 - 一键备份
cd /d "%~dp0"
if exist "python\python.exe" (set PYTHON_CMD=python\python.exe) else (set PYTHON_CMD=python)
chcp 65001 >nul
set PYTHONIOENCODING=utf-8
%PYTHON_CMD% scripts\backup_manager.py backup
pause
