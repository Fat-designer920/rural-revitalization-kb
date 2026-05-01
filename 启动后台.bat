@echo off
cd /d "%~dp0"

REM === ���Python���� ===
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

title �������֪ʶ�� - ������̨
echo.
echo ============================================================
echo   �������֪ʶ�� - ������̨ v2.3.6-part1
echo   Tab1 ֪ʶ��� ^| Tab2 ϵͳ���� ^| Tab3 �����ʴ�(���õ���)
echo ============================================================

REM === v2.3.6-part1: ��ȡ������ IP ��ӡ���ѷ��ʵ�ַ ===
REM �� ipconfig + findstr "IPv4" ȡ��һ����Ч IPv4 (������ IP)
set LOCAL_IP=
for /f "tokens=2 delims=:" %%i in ('ipconfig ^| findstr "IPv4"') do (
    if not defined LOCAL_IP set "LOCAL_IP=%%i"
)
REM ȥ��ǰ���ո�
if defined LOCAL_IP set "LOCAL_IP=%LOCAL_IP: =%"

echo.
if defined LOCAL_IP (
    echo [�������ò�Ʒҳ - �ѵ�ַ���Ʒ�������]
    echo   http://%LOCAL_IP%:5000/qa?u=��������
    echo.
    echo   ˵��: �� ?u=�������� �ĳɶԷ�����, ���ڷ�������
    echo         ������������ͬһ WiFi �²��ܷ���
    echo.
    echo [���غ�̨������� - ���㱾��ʹ��]
    echo   http://localhost:5000/
) else (
    echo [���غ�̨�������]
    echo   http://localhost:5000/
    echo [��ʾ] δ��⵽������ IP, ��������ҳ��ʱ�������ɷ���
)
echo.
echo ============================================================
echo.

REM === �л�UTF-8����ҳ(��echo֮��Python֮ǰ) ===
chcp 65001 >nul 2>nul
set PYTHONIOENCODING=utf-8

%PYTHON_CMD% scripts/api_server.py

pause
