@echo off
title 乡村振兴知识库 - 数据库迁移 v1.0.1 -> v1.1.0
cd /d "%~dp0"
if exist "python\python.exe" (set PYTHON_CMD=python\python.exe) else (set PYTHON_CMD=python)
chcp 65001 >nul
set PYTHONIOENCODING=utf-8
%PYTHON_CMD% scripts\migrate_v101_to_v110.py
pause
