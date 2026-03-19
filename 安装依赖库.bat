@echo off
title 乡村振兴知识库 - 安装依赖库
cd /d "%~dp0"
echo ============================================================
echo   安装依赖库
echo ============================================================
if exist "python\python.exe" (set PIP_CMD=python\python.exe -m pip) else (set PIP_CMD=python -m pip)
echo.
%PIP_CMD% install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple --trusted-host pypi.tuna.tsinghua.edu.cn
echo.
echo Done
pause
