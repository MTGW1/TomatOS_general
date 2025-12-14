@echo off
REM TomatOS 环境配置及启动初始化脚本 (Windows Batch)

REM 设置工作目录
cd /d "%~dp0"

REM 检查 Python 是否安装
where python >nul 2>nul
if %errorlevel% equ 0 (
    set PYTHON=python
) else (
    where python3 >nul 2>nul
    if %errorlevel% equ 0 (
        set PYTHON=python3
    ) else (
        echo 错误: Python 未安装。请先安装 Python。
        pause
        exit /b 1
    )
)

REM 检查是否在虚拟环境中运行，如果不是则尝试激活
if "%VIRTUAL_ENV%"=="" (
    REM 检查是否存在 venv 目录
    if exist "venv" (
        echo 激活虚拟环境...
        call venv\Scripts\activate.bat
    ) else (
        echo 未找到虚拟环境。
        set /p create_venv=是否要创建新的虚拟环境？(y/n): 
        if /i "%create_venv%"=="y" (
            echo 创建虚拟环境...
            %PYTHON% -m venv venv
            call venv\Scripts\activate.bat
            echo 虚拟环境已创建并激活。
        ) else (
            echo 警告: 将使用系统 Python
        )
    )
)

REM 检查依赖是否安装
if exist "requirements.txt" (
    echo 检查 Python 依赖...
    %PYTHON% -m pip install -r requirements.txt
)

REM 运行初始化程序
echo 启动 TomatOS 初始化程序...
%PYTHON% setup.py

REM 如果初始化程序被销毁，脚本结束
if not exist "setup.py" (
    echo 初始化程序已完成并已销毁。
    pause
    exit /b 0
)

echo 初始化完成。
echo.
echo 要手动启动服务器，请运行: %PYTHON% server.py
echo 要查看帮助，请运行: %PYTHON% server.py --help
echo.
pause