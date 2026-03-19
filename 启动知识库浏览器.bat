@echo off
title 乡村振兴知识库 - 知识库浏览器
cd /d "%~dp0"
if exist "python\python.exe" (set PYTHON_CMD=python\python.exe) else (set PYTHON_CMD=python)
echo   正在启动知识库浏览器, 关闭此窗口将停止服务
chcp 65001 >nul
set PYTHONIOENCODING=utf-8
%PYTHON_CMD% scripts\api_server.py
pause
