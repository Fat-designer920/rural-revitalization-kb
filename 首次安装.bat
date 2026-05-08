@echo off
cd /d "%~dp0"
set PYTHON_CMD=python
if exist "python\python.exe" set PYTHON_CMD=python\python.exe
chcp 65001 >nul
echo.
echo   稻也 - 首次安装
echo   --------------------
REM 1. Python >= 3.8
%PYTHON_CMD% -c "import sys; sys.exit(0 if sys.version_info >= (3,8) else 1)"
if %errorlevel% neq 0 (
    echo   [FAIL] 需要 Python 3.8+
    pause
    exit /b 1
)
echo   [OK] Python 环境
REM 2. 依赖
echo   [..] 安装依赖...
%PYTHON_CMD% -m pip install -r requirements.txt --quiet
if %errorlevel% neq 0 echo   [WARN] 依赖安装有警告
echo   [OK] 依赖就绪
REM 3. 配置
echo.
echo   [!!] 请编辑 config/settings.json 填入 deepseek_api_key_encrypted
echo.
echo   Done. 双击 启动后台.bat 启动服务。
pause
