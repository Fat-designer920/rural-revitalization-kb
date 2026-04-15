@echo off
cd /d "%~dp0"

REM === 检测Python环境 ===
if exist "python\python.exe" (set PYTHON_CMD=python\python.exe) else (set PYTHON_CMD=python)

title 乡村振兴知识库 - 首次安装
echo.
echo   ========================================
echo   乡村振兴知识库 - 首次安装向导
echo   ========================================
echo.
echo   即将执行:
echo     [1] 安装Python依赖库
echo     [2] 初始化系统(创建数据库+文件夹)
echo     [3] 配置API密钥
echo   ----------------------------------------
echo.

echo   [1/3] 安装依赖库...
echo.
%PYTHON_CMD% -m pip install --upgrade pip 2>nul
%PYTHON_CMD% -m pip install requests flask flask-cors cryptography pdfplumber python-docx openpyxl Pillow PyMuPDF 2>nul
if %errorlevel% neq 0 (
    echo.
    echo   尝试备用安装方式...
    %PYTHON_CMD% -m pip install --break-system-packages requests flask flask-cors cryptography pdfplumber python-docx openpyxl Pillow PyMuPDF
)
echo.

echo   [2/3] 初始化系统...
echo.

REM === 切换UTF-8（在中文echo之后，Python之前） ===
chcp 65001 >nul
set PYTHONIOENCODING=utf-8

%PYTHON_CMD% scripts/setup.py

echo.
echo   [3/3] ...
echo.
%PYTHON_CMD% scripts/config_wizard.py

echo.
echo   ========================================
echo   Done!
echo   Next: run 启动后台.bat
echo   ========================================
pause