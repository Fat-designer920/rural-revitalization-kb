@echo off
rem =====================================================
rem  数据体检.bat - 辅助查 bug 脚本 (v1.0, 2026-04-22)
rem  只读扫描,不改数据,可反复运行
rem =====================================================

cd /d "%~dp0"

echo.
echo ============================================
echo   乡村振兴知识库 - 数据体检
echo ============================================
echo.
echo 说明: 本脚本仅读取数据库,不做任何修改
echo 输出: 终端 + db_health_check_report.txt
echo.
echo 正在扫描 10 项体检点,请稍候...
echo.

chcp 65001 >nul
python scripts\db_health_check.py
set EXITCODE=%ERRORLEVEL%
chcp 936 >nul

echo.
echo ============================================
if %EXITCODE%==0 (
  echo 体检完成,报告文件: db_health_check_report.txt
) else (
  echo 体检脚本异常退出,错误码: %EXITCODE%
  echo 请把终端截图发给 Claude
)
echo ============================================
echo.
pause
