#!/bin/bash
# TomatOS 环境配置及启动初始化脚本 (Linux/macOS)

# 设置工作目录
cd "$(dirname "$0")"

# 检查 Python3 是否安装
if ! command -v python3 &> /dev/null; then
    echo "错误: Python3 未安装。请先安装 Python3。"
    exit 1
fi

# 检查是否在虚拟环境中运行，如果不是则尝试激活
if [ -z "$VIRTUAL_ENV" ]; then
    # 检查是否存在 venv 目录
    if [ -d "venv" ]; then
        echo "激活虚拟环境..."
        source venv/bin/activate
    else
        echo "未找到虚拟环境。"
        read -p "是否要创建新的虚拟环境？(y/n): " create_venv
        if [[ $create_venv =~ ^[Yy]$ ]]; then
            echo "创建虚拟环境..."
            python3 -m venv venv
            source venv/bin/activate
            echo "虚拟环境已创建并激活。"
        else
            echo "警告: 将使用系统 Python"
        fi
    fi
fi

# 检查依赖是否安装
if [ -f "requirements.txt" ]; then
    echo "检查 Python 依赖..."
    python3 -m pip install -r requirements.txt
fi

# 运行初始化程序
echo "启动 TomatOS 初始化程序..."
python3 setup.py

# 如果初始化程序被销毁，脚本结束
if [ ! -f "setup.py" ]; then
    echo "初始化程序已完成并已销毁。"
    exit 0
fi

echo "初始化完成。"
echo ""
echo "要手动启动服务器，请运行: python3 server.py"
echo "要查看帮助，请运行: python3 server.py --help"