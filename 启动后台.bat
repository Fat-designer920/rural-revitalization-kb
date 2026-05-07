@echo off
cd /d "%~dp0"

REM === 检测Python环境 ===
set PYTHON_CMD=
if exist "python\python.exe" (
    set PYTHON_CMD=python\python.exe
) else if exist "Python\python.exe" (
    set PYTHON_CMD=Python\python.exe
) else (
    where python >nul 2>nul
    if %errorlevel%==0 (
        set PYTHON_CMD=python
    ) else (
        echo [ERROR] Python not found. Please install Python 3.8+
        pause
        exit /b 1
    )
)

chcp 65001 >nul

REM 窗口标题用Python Unicode API设置, 彻底避免cmd title命令的GBK/UTF-8编码问题
%PYTHON_CMD% -c "import ctypes; ctypes.windll.kernel32.SetConsoleTitleW('乡知 - 管理后台 v2.3.7-part6')"

echo.
echo ============================================================
echo   乡知 管理后台 v2.3.7-part6
echo ============================================================

REM 获取本机局域网IP
set LOCAL_IP=
for /f "tokens=2 delims=:" %%i in ('ipconfig ^| findstr "IPv4"') do (
    if not defined LOCAL_IP set "LOCAL_IP=%%i"
)
set "LOCAL_IP=%LOCAL_IP: =%"

echo.
echo [管理后台 - 老唐入口]
echo   http://localhost:5000/
echo.
echo [产品页 - 客户入口]
echo   产品落地页:  http://localhost:5000/landing
echo   AI问答助手:  http://localhost:5000/qa
echo   精品查看器:  http://localhost:5000/premium
echo.
if defined LOCAL_IP (
    echo [手机端 - 发给朋友试用]
    echo   http://%LOCAL_IP%:5000/qa?u=对方名字
    echo   (同一 WiFi 下可访问)
)
echo.
echo   计划上线: /course /compliance /daily /templates
echo ============================================================
echo.

set PYTHONIOENCODING=utf-8
%PYTHON_CMD% scripts/api_server.py

pause
