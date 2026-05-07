@echo off
chcp 65001 >nul
python -c "import ctypes; ctypes.windll.kernel32.SetConsoleTitleW('稻也 - AgentLoop 持续循环')"

echo ============================================
echo   稻也 AgentLoop 持续循环
echo   13个任务错峰执行,永不停止
echo ============================================
echo.
echo   日志: logs/agent_loop.log
echo   按 Ctrl+C 停止
echo.

set PYTHONIOENCODING=utf-8
python scripts/start_agent_loop.py
pause
