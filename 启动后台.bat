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
%PYTHON_CMD% -c "import ctypes; ctypes.windll.kernel32.SetConsoleTitleW('乡村振兴知识库 - 管理后台 v2.3.7-part6')"

echo.
echo ============================================================
echo   乡村振兴知识库 - 管理后台 v2.3.7-part6
echo   Tab1 知识库 ^| Tab2 系统管理 ^| Tab3 智能问答(手机可刷)
echo ============================================================

REM 获取本机局域网IP
set LOCAL_IP=
for /f "tokens=2 delims=:" %%i in ('ipconfig ^| findstr "IPv4"') do (
    if not defined LOCAL_IP set "LOCAL_IP=%%i"
)
set "LOCAL_IP=%LOCAL_IP: =%"

echo.
if defined LOCAL_IP (
    echo [手机端产品页 - 把地址发给对方]
    echo   http://%LOCAL_IP%:5000/qa?u=对方名字
    echo.
    echo   说明: 把 ?u=对方名字 改成对方的名字, 用于分人记录
    echo         你和对方需在同一 WiFi 下才能访问
    echo.
    echo [本机后台管理页 - 你自己用]
    echo   http://localhost:5000/
) else (
    echo [本机后台管理页]
    echo   http://localhost:5000/
    echo [提示] 未检测到本机 IP, 手机端产品页暂不可用
)
echo.
echo ============================================================
echo.

set PYTHONIOENCODING=utf-8
%PYTHON_CMD% scripts/api_server.py

pause
