@echo off
cd /d "%~dp0"

REM === 检测Python环境 ===
if exist "python\python.exe" (set PYTHON_CMD=python\python.exe) else (set PYTHON_CMD=python)

chcp 65001 >nul

REM 窗口标题用Python Unicode API设置, 彻底避免cmd title命令的GBK/UTF-8编码问题
%PYTHON_CMD% -c "import ctypes; ctypes.windll.kernel32.SetConsoleTitleW('稻也 - 首次安装 v2.3.7-part6')"

echo.
echo   ========================================
echo   稻也 - 首次安装 v2.3.7-part6
echo   ========================================
echo.
echo   将执行:
echo     [1] 安装Python依赖包
echo     [2] 配置API密钥和路径
echo     [3] 初始化系统(创建文件夹+数据库)
echo   ----------------------------------------
echo.

echo   [1/3] 安装依赖包...
echo.
%PYTHON_CMD% -m pip install --upgrade pip 2>nul
%PYTHON_CMD% -m pip install requests flask flask-cors cryptography pdfplumber python-docx openpyxl Pillow PyMuPDF 2>nul
if %errorlevel% neq 0 (
    echo.
    echo   尝试备用安装方式...
    %PYTHON_CMD% -m pip install --break-system-packages requests flask flask-cors cryptography pdfplumber python-docx openpyxl Pillow PyMuPDF
)
echo.

echo   [2/3] 配置API密钥和路径...
echo   请在弹出的配置向导中填写:
echo     - DeepSeek API Key (必填)
echo     - 知识库存放路径 (建议D盘)
echo     - 每日费用上限
echo     - 硅基流动 API Key (扫描件PDF必填)
echo.

set PYTHONIOENCODING=utf-8
%PYTHON_CMD% scripts/config_wizard.py

echo.
echo   [3/3] 初始化系统...
echo.

%PYTHON_CMD% scripts/setup.py

echo.
echo   ========================================
echo   Done!
echo   Next: 双击运行 "启动后台.bat"
echo   ========================================
pause
