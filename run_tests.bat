@echo off
cd /d "%~dp0"
echo ========================================
echo  Running Smoke Test (L0+L3)...
echo ========================================
python scripts/auto_tester.py --smoke
if %errorlevel% neq 0 (
    echo.
    echo TESTS FAILED - Smoke test returned error
    exit /b 1
)
echo.
echo ========================================
echo  Running Full No-AI Test (L0-L5)...
echo ========================================
python scripts/auto_tester.py --auto --no-ai
if %errorlevel% neq 0 (
    echo.
    echo TESTS FAILED - Full test returned error
    exit /b 1
)
echo.
echo ========================================
echo  ALL TESTS PASSED
echo ========================================
