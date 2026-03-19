@echo off
title 乡村振兴知识库 - 首次安装
cd /d "%~dp0"
echo ============================================================
echo.
echo   欢迎使用乡村振兴知识库搭建助手!
echo   整个过程大约需要 5-10 分钟
echo.
echo ============================================================
echo.
echo [1/4] 检测Python...
if exist "python\python.exe" (set PYTHON_CMD=python\python.exe & set PIP_CMD=python\python.exe -m pip & echo   OK: 内嵌Python & goto :s2)
where python >nul 2>&1
if %errorlevel% equ 0 (set PYTHON_CMD=python & set PIP_CMD=python -m pip & echo   OK: 系统Python & goto :s2)
echo   FAIL: 未找到Python, 请先安装Python 3.10+ 并勾选Add to PATH
pause & exit /b 1
:s2
echo.
echo [2/4] 安装依赖库...
%PIP_CMD% install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple --trusted-host pypi.tuna.tsinghua.edu.cn -q
echo   OK
echo.
echo [3/4] 启动配置向导...
chcp 65001 >nul
set PYTHONIOENCODING=utf-8
%PYTHON_CMD% scripts