# TomatOS 环境配置及启动初始化脚本 (Windows PowerShell)

# 设置工作目录
Set-Location -Path $PSScriptRoot

# 检查 Python 是否安装
$pythonPath = ""
if (Get-Command python -ErrorAction SilentlyContinue) {
    $pythonPath = "python"
} elseif (Get-Command python3 -ErrorAction SilentlyContinue) {
    $pythonPath = "python3"
} else {
    Write-Host "错误: Python 未安装。请先安装 Python。" -ForegroundColor Red
    exit 1
}

# 检查是否在虚拟环境中运行，如果不是则尝试激活
if (-not $env:VIRTUAL_ENV) {
    # 检查是否存在 venv 目录
    if (Test-Path "venv") {
        Write-Host "激活虚拟环境..." -ForegroundColor Yellow
        & "venv\Scripts\Activate.ps1"
    } else {
        Write-Host "未找到虚拟环境。" -ForegroundColor Yellow
        $create_venv = Read-Host "是否要创建新的虚拟环境？(y/n)"
        if ($create_venv -match "^[Yy]$") {
            Write-Host "创建虚拟环境..." -ForegroundColor Yellow
            & $pythonPath -m venv venv
            & "venv\Scripts\Activate.ps1"
            Write-Host "虚拟环境已创建并激活。" -ForegroundColor Green
        } else {
            Write-Host "警告: 将使用系统 Python" -ForegroundColor Yellow
        }
    }
}

# 检查依赖是否安装
if (Test-Path "requirements.txt") {
    Write-Host "检查 Python 依赖..." -ForegroundColor Yellow
    & $pythonPath -m pip install -r requirements.txt
}

# 运行初始化程序
Write-Host "启动 TomatOS 初始化程序..." -ForegroundColor Green
& $pythonPath setup.py

# 如果初始化程序被销毁，脚本结束
if (-not (Test-Path "setup.py")) {
    Write-Host "初始化程序已完成并已销毁。" -ForegroundColor Green
    exit 0
}

Write-Host "初始化完成。" -ForegroundColor Green
Write-Host ""
Write-Host "要手动启动服务器，请运行: $pythonPath server.py" -ForegroundColor Cyan
Write-Host "要查看帮助，请运行: $pythonPath server.py --help" -ForegroundColor Cyan

# 保持窗口打开（如果双击运行）
Write-Host ""
Write-Host "按任意键退出..." -ForegroundColor Gray
$null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")