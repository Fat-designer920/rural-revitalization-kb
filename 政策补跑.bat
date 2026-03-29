@echo off
chcp 65001 >nul 2>&1
echo.
echo ========================================
echo   政策依赖补跑校验
echo   对已入库但未校验的知识点补跑政策校验
echo ========================================
echo.

REM === 便携Python检测 ===
set "PYTHON_CMD="
if exist "%~dp0python\python.exe" (
    set "PYTHON_CMD=%~dp0python\python.exe"
    echo   [OK] 使用便携版Python
) else if exist "%~dp0..\python\python.exe" (
    set "PYTHON_CMD=%~dp0..\python\python.exe"
    echo   [OK] 使用便携版Python
) else (
    where python >nul 2>&1
    if %errorlevel%==0 (
        set "PYTHON_CMD=python"
        echo   [OK] 使用系统Python
    ) else (
        echo   [FAIL] 未找到Python
        echo   请安装Python 3.8+或将便携版Python放到python文件夹
        pause
        exit /b 1
    )
)

echo.
echo   正在执行数据库迁移检查...
%PYTHON_CMD% -c "import sys;sys.path.insert(0,'%~dp0');from scripts.migrate_v210d import migrate;migrate()" 2>nul
echo.
echo   开始补跑政策校验...
echo.
%PYTHON_CMD% -c "import sys;sys.path.insert(0,'%~dp0');from scripts.policy_validator import PolicyValidator;pv=PolicyValidator();pv.run_standalone()"

echo.
echo ========================================
echo   补跑完成
echo ========================================
pause
