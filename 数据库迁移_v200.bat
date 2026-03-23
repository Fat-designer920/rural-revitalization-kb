@echo off
title 乡村振兴知识库 - 数据库迁移 v1.1.0 -> v2.0.0
cd /d "%~dp0"
if exist "python\python.exe" (set PYTHON_CMD=python\python.exe) else (set PYTHON_CMD=python)
chcp 65001 >nul
set PYTHONIOENCODING=utf-8
echo.
echo  !!! 重要：请确保已备份数据库 !!!
echo  如未备份，请先关闭此窗口，运行「手动备份.bat」后再执行迁移
echo.
pause
%PYTHON_CMD% scripts\migrate_v110_to_v200.py
pause
