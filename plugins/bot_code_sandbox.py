"""
AI 代码测试沙盒 (AI Code Sandbox)
整合了 Docker 容器运行、本地 Python 执行和离线环境支持。
提供安全、灵活的多语言代码执行环境，并具备完整的 Docker 管理能力。
"""

from bot.tools import ai_tool
from bot.logger import logger
import platform
import os
import subprocess
import tempfile
import json
import shutil
import sys
import asyncio
import glob
import time

# 沙盒工作目录
PLUGIN_DIR = os.path.dirname(os.path.abspath(__file__))
SANDBOX_WORK_DIR = os.path.join(PLUGIN_DIR, 'TomatOS_run')

# 确保工作目录存在
if not os.path.exists(SANDBOX_WORK_DIR):
    try:
        os.makedirs(SANDBOX_WORK_DIR)
    except Exception as e:
        logger.error(f"无法创建沙盒工作目录: {e}")

# ==================== 辅助函数 ====================

def check_docker_available() -> tuple[bool, str]:
    """检查 Docker 是否可用"""
    try:
        result = subprocess.run(
            ["docker", "--version"],
            capture_output=True,
            text=True,
            encoding='utf-8',
            errors='ignore',
            shell=True
        )
        if result.returncode == 0:
            return True, result.stdout.strip()
        else:
            return False, "Docker 命令执行失败"
    except FileNotFoundError:
        return False, "Docker 未安装或不在 PATH 中"
    except Exception as e:
        return False, f"检查 Docker 失败: {str(e)}"

def run_docker_command(cmd: list, timeout: int = 30) -> tuple[int, str, str]:
    """运行 Docker 命令"""
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding='utf-8',
            errors='ignore',
            shell=True,
            timeout=timeout
        )
        return result.returncode, result.stdout, result.stderr
    except subprocess.TimeoutExpired:
        return -1, "", f"命令执行超时（{timeout}秒）"
    except Exception as e:
        return -1, "", f"命令执行失败: {str(e)}"

# ==================== 核心沙盒工具 ====================

@ai_tool(
    name="run_code_sandbox",
    description="在安全沙盒中运行代码。优先使用 Docker，支持多种语言。运行后会输出日志文件路径和生成的文件列表。",
    parameters={
        "language": {
            "type": "string",
            "description": "编程语言：python(TomatOS_venv), javascript, java, c, cpp, go, rust, ruby, shell",
            "default": "python"
        },
        "code": {
            "type": "string", 
            "description": "要执行的代码"
        },
        "mode": {
            "type": "string",
            "description": "运行模式：auto (自动选择), docker (强制 Docker), local (强制本地，仅限 Python/Shell)",
            "default": "auto"
        },
        "timeout": {
            "type": "integer",
            "description": "执行超时时间（秒）",
            "default": 30
        }
    },
    required=["code"],
)
async def run_code_sandbox(language: str = "python", code: str = "", mode: str = "auto", timeout: int = 30) -> str:
    """智能代码运行沙盒"""
    
    language = language.lower()
    docker_available, docker_info = check_docker_available()
    
    # 决定运行模式
    use_docker = False
    if mode == "docker":
        if not docker_available:
            return f"❌ Docker 不可用: {docker_info}"
        use_docker = True
    elif mode == "local":
        use_docker = False
    else: # auto
        use_docker = docker_available
    
    # 记录运行前的文件列表
    try:
        files_before = set(os.listdir(SANDBOX_WORK_DIR))
    except Exception:
        files_before = set()

    # 执行代码
    display_output = ""
    raw_log = ""
    
    if use_docker:
        display_output, raw_log = await _run_in_docker(language, code, timeout)
    else:
        if language not in ["python", "shell", "bash", "sh"]:
            return f"❌ 本地模式不支持 {language}，仅支持 Python 和 Shell。请安装 Docker 以支持更多语言。"
        
        if language == "python":
            display_output, raw_log = await _run_python_local(code)
        else:
            display_output, raw_log = await _run_shell_local(code)

    # 记录运行后的文件列表
    try:
        files_after = set(os.listdir(SANDBOX_WORK_DIR))
        new_files = list(files_after - files_before)
    except Exception:
        new_files = []

    # 保存日志文件
    timestamp = int(time.time())
    log_filename = f"run_{language}_{timestamp}.log"
    log_path = os.path.join(SANDBOX_WORK_DIR, log_filename)
    
    try:
        with open(log_path, "w", encoding="utf-8") as f:
            f.write(f"=== 运行日志 ({language}) powered by TomatOS_run ===\n")
            f.write(f"日志时间: {time.ctime(timestamp)}\n")
            f.write(f"运行模式: {'Docker' if use_docker else 'Local'}\n")
            f.write("=== Code ===\n")
            f.write(code + "\n")
            f.write("=== Output ===\n")
            f.write(raw_log + "\n")
    except Exception as e:
        logger.error(f"无法写入日志文件: {e}")

    # 构建最终返回信息
    final_report = display_output + "\n"
    final_report += "=" * 30 + "\n"
    final_report += f"📄 运行日志: {log_path}\n"
    
    if new_files:
        final_report += "📂 生成文件:\n"
        for nf in new_files:
            # 忽略日志文件本身
            if nf != log_filename:
                final_report += f"  - {os.path.join(SANDBOX_WORK_DIR, nf)}\n"
    else:
        final_report += "📂 生成文件: 无\n"

    return final_report

async def _run_in_docker(language: str, code: str, timeout: int) -> tuple[str, str]:
    """在 Docker 中运行代码，返回 (显示文本, 原始日志)"""
    
    # 语言配置
    lang_config = {
        "python": {"image": "python:3.14.2-slim", "ext": "py", "cmd": "python /tmp/code.py"},
        "javascript": {"image": "node:24.12.0-alpine", "ext": "js", "cmd": "node /tmp/code.js"},
        "java": {"image": "openjdk:27-ea-jdk", "ext": "java", "cmd": "javac /tmp/code.java && java -cp /tmp Main"},
        "c": {"image": "gcc:latest", "ext": "c", "cmd": "gcc /tmp/code.c -o /tmp/code && /tmp/code"},
        "cpp": {"image": "gcc:latest", "ext": "cpp", "cmd": "g++ /tmp/code.cpp -o /tmp/code && /tmp/code"},
        "go": {"image": "golang:latest", "ext": "go", "cmd": "go run /tmp/code.go"},
        "rust": {"image": "rust:latest", "ext": "rs", "cmd": "rustc /tmp/code.rs -o /tmp/code && /tmp/code"},
        "ruby": {"image": "ruby:latest", "ext": "rb", "cmd": "ruby /tmp/code.rb"},
        "shell": {"image": "alpine:latest", "ext": "sh", "cmd": "sh /tmp/code.sh"},
        "bash": {"image": "bash:latest", "ext": "sh", "cmd": "bash /tmp/code.sh"},
        "sh": {"image": "alpine:latest", "ext": "sh", "cmd": "sh /tmp/code.sh"},
    }
    
    # 优先使用自定义的 tomatos-venv 镜像（如果存在）
    if language == "python":
        ret, stdout, _ = run_docker_command(["docker", "images", "-q", "tomatos-venv:latest"])
        if stdout.strip():
            lang_config["python"]["image"] = "tomatos-venv:latest"
    
    if language not in lang_config:
        # 尝试查找离线替代镜像
        if language == "python":
            lang_config["python"]["image"] = "python:alpine"
        elif language == "javascript":
            lang_config["javascript"]["image"] = "node:alpine"
        else:
            return f"❌ 不支持的语言: {language}", ""
    
    config = lang_config[language]
    image = config["image"]
    
    # 检查是否使用自定义镜像
    using_custom_image = (language == "python" and image == "tomatos-venv:latest")
    
    # 检查镜像是否存在
    ret, stdout, _ = run_docker_command(["docker", "images", "-q", image])
    if not stdout.strip():
        if language in ["shell", "bash", "sh"]:
            image = "alpine:latest"
        else:
            logger.info(f"尝试拉取镜像: {image}")
            run_docker_command(["docker", "pull", image], timeout=60)
    
    # 创建临时文件
    with tempfile.NamedTemporaryFile(mode='w', suffix=f'.{config["ext"]}', delete=False, encoding='utf-8') as f:
        f.write(code)
        temp_file = f.name
    
    try:
        # 构建命令
        volume_mounts = [
            f"--volume={temp_file}:/tmp/code.{config['ext']}:ro",
            f"--volume={SANDBOX_WORK_DIR}:/workspace:rw"
        ]
        
        docker_cmd = [
            "docker", "run",
            "--rm",
            "--memory=256m",
            "--cpus=1",
            "--network=none",
            "--workdir=/workspace"
        ] + volume_mounts + [
            image,
            "sh", "-c", config["cmd"]
        ]
        
        # 执行
        returncode, stdout, stderr = run_docker_command(docker_cmd, timeout)
        
        raw_log = f"STDOUT:\n{stdout}\nSTDERR:\n{stderr}"
        
        output = ""
        if stdout: output += f"📝 输出:\n{stdout}\n"
        if stderr: output += f"⚠️  错误:\n{stderr}\n"
        
        if returncode == 0:
            image_info = "(使用自定义环境)" if using_custom_image else ""
            return f"✅ Docker 执行成功 ({language}) {image_info}:\n{output}", raw_log
        elif returncode == -1:
            return f"⏰ Docker 执行超时:\n{stderr}", raw_log
        else:
            return f"❌ Docker 执行失败 (Code {returncode}):\n{output}", raw_log
            
    finally:
        if os.path.exists(temp_file):
            os.unlink(temp_file)

async def _run_python_local(code: str) -> tuple[str, str]:
    """本地运行 Python 代码，返回 (显示文本, 原始日志)"""
    try:
        local_vars = {}
        import io
        from contextlib import redirect_stdout
        
        f = io.StringIO()
        error_msg = ""
        try:
            with redirect_stdout(f):
                exec(code, {}, local_vars)
        except Exception as e:
            error_msg = str(e)
        
        output = f.getvalue()
        result = local_vars.get("result", "")
        
        raw_log = f"STDOUT:\n{output}\nRESULT:\n{result}\nERROR:\n{error_msg}"
        
        response = ""
        if error_msg:
            response = f"❌ 本地 Python 执行出错: {error_msg}\n"
        else:
            response = f"✅ 本地 Python 执行成功:\n"
        
        if output:
            response += f"📝 输出:\n{output}\n"
        if result:
            response += f"📦 返回值: {result}\n"
        if not output and not result and not error_msg:
            response += "（无输出）"
            
        return response, raw_log
        
    except Exception as e:
        return f"❌ 本地 Python 执行严重错误: {e}", str(e)

async def _run_shell_local(code: str) -> tuple[str, str]:
    """本地运行 Shell 命令，返回 (显示文本, 原始日志)"""
    try:
        result = subprocess.run(
            code,
            capture_output=True,
            text=True,
            shell=True,
            timeout=30
        )
        
        raw_log = f"STDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}"
        
        output = ""
        if result.stdout: output += f"📝 输出:\n{result.stdout}\n"
        if result.stderr: output += f"⚠️  错误:\n{result.stderr}\n"
        
        if result.returncode == 0:
            return f"✅ 本地 Shell 执行成功:\n{output}", raw_log
        else:
            return f"❌ 本地 Shell 执行失败:\n{output}", raw_log
            
    except Exception as e:
        return f"❌ 本地 Shell 执行出错: {e}", str(e)

@ai_tool(
    name="manage_code_sandbox",
    description="管理代码沙盒环境，包括加载离线镜像、清理资源、查看状态、管理容器。",
    parameters={
        "action": {
            "type": "string",
            "description": "操作：status (状态), load_offline (加载离线镜像), cleanup (清理), list_files (文件列表), list_containers (列出容器), list_images (列出镜像), manage_container (管理容器)",
            "enum": ["status", "load_offline", "cleanup", "list_files", "list_containers", "list_images", "manage_container"],
            "default": "status"
        },
        "target": {
            "type": "string",
            "description": "操作目标。对于 manage_container，格式为 'sub_action:container_id' (如 stop:my-container)",
            "default": ""
        }
    },
    required=["action"],
)
async def manage_sandbox(action: str = "status", target: str = "") -> str:
    """管理沙盒环境"""
    
    docker_available, docker_info = check_docker_available()
    
    if action == "status":
        output = "🔍 沙盒环境状态:\n"
        output += "=" * 40 + "\n"
        output += f"🐳 Docker: {'✅ 可用' if docker_available else '❌ 不可用'} ({docker_info})\n"
        output += f"📂 工作目录: {SANDBOX_WORK_DIR}\n"
        
        if docker_available:
            ret, stdout, _ = run_docker_command(["docker", "images", "--format", "{{.Repository}}:{{.Tag}}"])
            count = len(stdout.strip().split('\n')) if stdout.strip() else 0
            output += f"🖼️  本地镜像数: {count}\n"
            
        return output

    elif action == "load_offline":
        if not docker_available: return "❌ Docker 不可用，无法加载镜像。"
        
        tar_files = glob.glob(os.path.join(SANDBOX_WORK_DIR, "*.tar"))
        if not tar_files:
            return f"⚠️  在 {SANDBOX_WORK_DIR} 中未找到 .tar 镜像文件。"
        
        output = "📦 加载离线镜像:\n"
        for tar_file in tar_files:
            filename = os.path.basename(tar_file)
            output += f"正在加载 {filename}...\n"
            ret, stdout, stderr = run_docker_command(["docker", "load", "-i", tar_file], timeout=300)
            if ret == 0:
                output += f"✅ 成功: {stdout.strip()}\n"
            else:
                output += f"❌ 失败: {stderr.strip()}\n"
        return output

    elif action == "cleanup":
        if not docker_available: return "❌ Docker 不可用。"
        ret, stdout, stderr = run_docker_command(["docker", "system", "prune", "-f"])
        return f"🧹 清理结果:\n{stdout if ret == 0 else stderr}"

    elif action == "list_files":
        try:
            files = os.listdir(SANDBOX_WORK_DIR)
            if not files:
                return "📂 工作目录为空。"
            return "📂 工作目录文件:\n" + "\n".join([f"- {f}" for f in files])
        except Exception as e:
            return f"❌ 无法读取目录: {e}"

    elif action == "list_containers":
        if not docker_available: return "❌ Docker 不可用。"
        ret, stdout, stderr = run_docker_command(["docker", "ps", "-a"])
        return f"📦 容器列表:\n{stdout if ret == 0 else stderr}"

    elif action == "list_images":
        if not docker_available: return "❌ Docker 不可用。"
        ret, stdout, stderr = run_docker_command(["docker", "images"])
        return f"🖼️  镜像列表:\n{stdout if ret == 0 else stderr}"

    elif action == "manage_container":
        # target format: "action:container_id" e.g. "stop:my_container"
        if not target or ":" not in target:
            return "❌ 请指定操作和容器，格式: action:container_id (action: start, stop, restart, remove)"
        
        sub_action, container_id = target.split(":", 1)
        if sub_action not in ["start", "stop", "restart", "remove"]:
            return "❌ 不支持的操作。支持: start, stop, restart, remove"
            
        # Find container
        ret, stdout, _ = run_docker_command(["docker", "ps", "-a", "--filter", f"name={container_id}", "--format", "{{.Names}}"])
        found_names = stdout.strip().splitlines()
        if not found_names:
            return f"❌ 未找到容器: {container_id}"
        
        real_name = found_names[0]
        cmd_map = {
            "start": ["docker", "start", real_name],
            "stop": ["docker", "stop", real_name],
            "restart": ["docker", "restart", real_name],
            "remove": ["docker", "rm", "-f", real_name]
        }
        
        ret, stdout, stderr = run_docker_command(cmd_map[sub_action])
        if ret == 0:
            return f"✅ 容器 {real_name} {sub_action} 成功。"
        else:
            return f"❌ 操作失败: {stderr}"
    
    return "❌ 未知操作"

@ai_tool(
    name="build_docker_image",
    description="从 Dockerfile 内容构建新的 Docker 镜像。",
    parameters={
        "dockerfile_content": {
            "type": "string",
            "description": "Dockerfile 的内容"
        },
        "image_name": {
            "type": "string",
            "description": "目标镜像名称 (如 myapp:v1)"
        }
    },
    required=["dockerfile_content", "image_name"],
)
async def build_docker_image(dockerfile_content: str, image_name: str) -> str:
    """构建 Docker 镜像"""
    docker_available, _ = check_docker_available()
    if not docker_available:
        return "❌ Docker 不可用。"

    # 创建临时构建目录
    with tempfile.TemporaryDirectory() as temp_dir:
        dockerfile_path = os.path.join(temp_dir, "Dockerfile")
        with open(dockerfile_path, "w", encoding="utf-8") as f:
            f.write(dockerfile_content)
        
        # 构建
        ret, stdout, stderr = run_docker_command(["docker", "build", "-t", image_name, temp_dir], timeout=600)
        
        if ret == 0:
            return f"✅ 镜像 {image_name} 构建成功:\n{stdout}"
        else:
            return f"❌ 构建失败:\n{stderr}"

@ai_tool(
    name="get_sandbox_system_info",
    description="获取宿主机的系统信息。",
    parameters={},
    required=[],
)
async def get_sandbox_system_info() -> str:
    """获取系统信息"""
    try:
        import psutil
        info = {
            "OS信息": f"{platform.system()} {platform.release()}",
            "服务器名称": platform.node(),
            "CPU": f"{platform.processor()} ({psutil.cpu_count()} cores)",
            "内存总量": f"{round(psutil.virtual_memory().total / (1024**3), 2)} GB",
            "运行内存": f"{round(psutil.virtual_memory().used / (1024**3), 2)} GB",
            "硬盘总量": f"{round(psutil.disk_usage('/').total / (1024**3), 2)} GB",
            "硬盘可用": f"{round(psutil.disk_usage('/').free / (1024**3), 2)} GB",
            "Python版本": sys.version.split()[0],
            "工作目录": SANDBOX_WORK_DIR
        }
        return "\n".join([f"{k}: {v}" for k, v in info.items()])
    except Exception as e:
        return f"❌ 获取信息失败: {e}"
