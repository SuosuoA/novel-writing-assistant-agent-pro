@echo off
chcp 65001 >nul
title Novel Writing Assistant-Agent Pro 启动器

echo ========================================
echo   Novel Writing Assistant-Agent Pro
echo   智能小说写作辅助工具
echo ========================================
echo.

REM 切换到脚本所在目录
cd /d "%~dp0"

REM 检查Python是否可用
python --version >nul 2>&1
if errorlevel 1 (
    echo [错误] 未检测到Python环境，请先安装Python 3.12.x
    echo 下载地址: https://www.python.org/downloads/
    pause
    exit /b 1
)

REM 显示Python版本
for /f "tokens=2" %%i in ('python --version 2^>^&1') do set PYVER=%%i
echo [信息] Python版本: %PYVER%
echo.

REM 检查虚拟环境
if exist "venv\Scripts\activate.bat" (
    echo [信息] 检测到虚拟环境，正在激活...
    call venv\Scripts\activate.bat
) else (
    echo [信息] 使用系统Python环境
)

REM 检查依赖是否安装
echo [检查] 正在检查依赖...
python -c "import sv_ttk" >nul 2>&1
if errorlevel 1 (
    echo [警告] 依赖未完全安装，正在安装依赖...
    pip install -r requirements.txt
    if errorlevel 1 (
        echo [错误] 依赖安装失败，请手动执行: pip install -r requirements.txt
        pause
        exit /b 1
    )
)

echo [完成] 依赖检查通过
echo.
echo [启动] 正在启动GUI界面...
echo.

REM 启动主程序
python gui_main.py

REM 如果程序异常退出，暂停以显示错误信息
if errorlevel 1 (
    echo.
    echo [错误] 程序异常退出，错误代码: %errorlevel%
    pause
)
