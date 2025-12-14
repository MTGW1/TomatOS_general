#!/bin/bash

# 获取脚本所在的绝对路径
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$SCRIPT_DIR"
echo "Current working directory: $(pwd)"

# 检查是否存在虚拟环境，如果存在则激活 (假设虚拟环境名为 venv)
if [ -d "venv" ]; then
    echo "venv? 启动!"
    source venv/bin/activate
fi

# 定义启动文件的路径
SERVER_SCRIPT="server.py"
PID_FILE="progress.json"

# 检查并清理可能占用的端口
check_and_clean_port() {
    local port=$1
    echo "检查端口 $port 是否被占用..."
    
    # 检查端口占用情况
    local pid=""
    if command -v lsof >/dev/null 2>&1; then
        pid=$(lsof -ti:$port 2>/dev/null)
    elif command -v netstat >/dev/null 2>&1; then
        pid=$(netstat -tlnp 2>/dev/null | grep ":$port " | awk '{print $7}' | cut -d'/' -f1)
    elif command -v ss >/dev/null 2>&1; then
        pid=$(ss -tlnp 2>/dev/null | grep ":$port " | awk '{print $6}' | cut -d'=' -f2 | cut -d',' -f1)
    else
        echo "警告: 无法检查端口占用情况，请手动检查端口 $port"
        return 1
    fi
    
    if [ -n "$pid" ] && [ "$pid" != "-" ]; then
        echo "端口 $port 被进程 $pid 占用，尝试终止..."
        kill -9 $pid 2>/dev/null
        sleep 2
        # 再次检查
        if command -v lsof >/dev/null 2>&1; then
            if lsof -ti:$port >/dev/null 2>&1; then
                echo "警告: 无法终止占用端口 $port 的进程，可能需要手动处理"
                echo "尝试使用 fuser 命令..."
                if command -v fuser >/dev/null 2>&1; then
                    fuser -k $port/tcp 2>/dev/null
                    sleep 1
                fi
                # 最后检查一次
                if lsof -ti:$port >/dev/null 2>&1; then
                    echo "错误: 端口 $port 仍然被占用，请手动处理"
                    return 1
                fi
            fi
        fi
        echo "端口 $port 已清理"
    else
        echo "端口 $port 可用"
    fi
    
    # 额外检查：如果端口仍然被占用（可能是 TIME_WAIT 状态），等待一段时间
    echo "等待端口 $port 完全释放..."
    local max_wait=10
    local wait_count=0
    while [ $wait_count -lt $max_wait ]; do
        if command -v lsof >/dev/null 2>&1; then
            if ! lsof -ti:$port >/dev/null 2>&1; then
                break
            fi
        fi
        sleep 1
        wait_count=$((wait_count + 1))
    done
    
    if [ $wait_count -eq $max_wait ]; then
        echo "警告: 端口 $port 可能处于 TIME_WAIT 状态，尝试继续启动..."
    else
        echo "端口 $port 已完全释放"
    fi
    
    return 0
}

# 检查主要端口 (8765 和 8075)
check_and_clean_port 8765
check_and_clean_port 8075

if [ -f "$SERVER_SCRIPT" ]; then
    echo "正在启动TomatOS服务器..."
    # 使用 python3 启动
    /usr/bin/python3.14 "$SERVER_SCRIPT"
    # 检查进程是否启动成功
    if [ $? -eq 0 ]; then
        echo "TomatOS已成功启动."
        # 创建或更新 PID 文件
        echo "{\"pid\": $$}" > "$PID_FILE"
    else
        echo "尝试使用备用路径启动TomatOS服务器..."
        /usr/bin/python3.14 "$SCRIPT_DIR/$SERVER_SCRIPT"
        if [ $? -eq 0 ]; then
            echo "TomatOS已成功启动."
            # 创建或更新 PID 文件
            echo "{\"pid\": $$}" > "$PID_FILE"
            exit 0
        fi
        echo "错误: 启动 TomatOS 失败."
        exit 1
    fi
else
    echo "错误: 找不到 $SERVER_SCRIPT"
    exit 1
fi

