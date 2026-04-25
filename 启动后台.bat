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

title 乡村振兴知识库 - 管理后台
echo.
echo ============================================================
echo   乡村振兴知识库 - 管理后台 v2.3.3-mvp-part1a
echo   Tab1 知识审核 ^| Tab2 系统管理 ^| Tab3 智能问答(自用调试)
echo ============================================================

REM === v2.3.3-mvp-part1a: 提取局域网 IP 打印朋友访问地址 ===
REM 用 ipconfig + findstr "IPv4" 取第一个有效 IPv4 (局域网 IP)
set LOCAL_IP=
for /f "tokens=2 delims=:" %%i in ('ipconfig ^| findstr "IPv4"') do (
    if not defined LOCAL_IP set "LOCAL_IP=%%i"
)
REM 去掉前导空格
if defined LOCAL_IP set "LOCAL_IP=%LOCAL_IP: =%"

echo.
if defined LOCAL_IP (
    echo [朋友试用产品页 - 把地址复制发给朋友]
    echo   http://%LOCAL_IP%:5000/qa?u=朋友姓名
    echo.
    echo   说明: 把 ?u=朋友姓名 改成对方真名, 便于反馈分析
    echo         朋友需与你在同一 WiFi 下才能访问
    echo.
    echo [本地后台管理入口 - 仅你本机使用]
    echo   http://localhost:5000/
) else (
    echo [本地后台管理入口]
    echo   http://localhost:5000/
    echo [提示] 未检测到局域网 IP, 朋友试用页暂时仅本机可访问
)
echo.
echo ============================================================
echo.

REM === 切换UTF-8代码页(在echo之后、Python之前) ===
chcp 65001 >nul 2>nul
set PYTHONIOENCODING=utf-8

%PYTHON_CMD% scripts/api_server.py

pause
