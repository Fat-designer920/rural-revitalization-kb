@echo off
title 乡村振兴知识库 - 浏览器
cd /d "%~dp0"
if exist "python\python.exe" (set PYTHON_CMD=python\python.exe) else (set PYTHON_CMD=python)
echo   正在启动, 关闭此窗口将停止服务
chcp 65001 >nul
set PYTHONIOENCODING=utf-8
%PYTHON_CMD% scriptspi_server.py
