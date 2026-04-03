@echo off
title 乡村振兴知识库 - 政策依赖补跑校验
cd /d "%~dp0"
if exist "python\python.exe" (set PYTHON_CMD=python\python.exe) else (set PYTHON_CMD=python)
chcp 65001 >nul
set PYTHONIOENCODING=utf-8
echo.
echo   ============================================
echo   乡村振兴知识库 - 政策依赖补跑校验
echo   对已入库但未校验的知识点补跑政策校验
echo   ============================================
echo.
echo   正在执行数据库迁移检查...
%PYTHON_CMD% scripts\migrate_v210d.py
echo.
echo   开始补跑政策校验...
echo.
%PYTHON_CMD% scripts\policy_validator.py
echo.
echo   ============================================
echo   补跑完成
echo   ============================================
pause