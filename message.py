import asyncio
import re
from logger import logger
from typing import Dict, Any, Optional
from functools import wraps
import inspect
import importlib
import os
import sys
from message_adapters.message_core import Messagebase, TomatOS_conn

# 添加 message_adapters 目录到 Python 路径
message_adapters_path = os.path.join(os.path.dirname(__file__), "message_adapters")
if message_adapters_path not in sys.path:
    sys.path.insert(0, message_adapters_path)

cmd_prefix = ["/", "！", "!", "y"]
ada_path = os.path.join(os.path.dirname(__file__), "message_adapters") # 信息适配器路径(TomatOS\message_adapters)

class TomatOS_Msghandler:
    def __init__(self):
        self.commands = []
        self.ada = []  # 信息适配器列表
        self.adapter_path = os.path.join(os.path.dirname(__file__), "message_adapters") # 信息适配器路径(TomatOS\message_adapters)
        self.message_handlers = []  # 信息处理注册列表

        self.ada_config_base = {
            "enabled": True,
            "host": None,
            "port": None,
            "conn_mode": None,
            "auth": {
                "headers": {},
                "params": {},
            }
        }
        pass

    def init_message_adapter(self):
        # 动态加载信息适配器
        modules = []
        loaded_module_names = set()
        for filename in os.listdir(self.adapter_path):
            if filename.endswith(".py") and not filename.startswith("__"):
                module_name = filename[:-3]
                try:
                    # 避免重复加载模块
                    if module_name in loaded_module_names:
                        continue
                    module = importlib.import_module(f"message_adapters.{module_name}")
                    modules.append(module)
                    loaded_module_names.add(module_name)
                    logger.info(f"加载信息适配器模块: {module_name}")
                except Exception as e:
                    logger.error(f"加载信息适配器模块 {module_name} 失败: {e}")
        # 初始化适配器实例
        initialized_adapters = set()
        for module in modules:
            try:
                for attr_name in dir(module):
                    attr = getattr(module, attr_name)
                    if inspect.isclass(attr) and attr_name.endswith("_Messageadapter"):
                        # 避免重复初始化适配器
                        if attr_name in initialized_adapters:
                            logger.debug(f"跳过重复的适配器类: {attr_name}")
                            continue
                        ada_instance = attr()
                        self.ada.append(ada_instance)
                        initialized_adapters.add(attr_name)
                        logger.info(f"初始化信息适配器实例: {attr_name}")
            except Exception as e:
                logger.error(f"初始化信息适配器实例失败: {e}")
        pass

    def on_command(self, cmd: str, alias: list[re.Pattern], description: str, parameters: Dict[str, Any]):
        def decorator(func):
            try:
                module_name = inspect.getmodule(func).__name__
                func_line = inspect.getsourcelines(func)[1]
            except Exception:
                module_name = "unknown"
                func_line = 0
            
            logger.debug(f"[TomatOS_command]注册命令 {cmd} 注册行 {module_name}:{func_line}")
            self.commands.append({
                "name": cmd,                 # 命令名称
                "alias": alias,              # 命令别名列表
                "description": description,  # 命令描述
                "parameters": parameters,    # 命令参数
                "function": func             # 命令处理函数
            })
            @wraps(func)
            async def wrapper(*args, **kwargs):
                return await func(*args, **kwargs)
            return wrapper
        return decorator
    
    def on_message(self, from_adapter: str, from_user: str, from_event: str) -> Optional[Any]:
        # 信息处理注册
        def decorator(func):
            logger.debug(f"[TomatOS_message]注册信息处理器 来自适配器 {from_adapter} 来自用户 {from_user}")
            self.message_handlers.append({
                "from_adapter": from_adapter,
                "from_user": from_user,
                "from_event": from_event,
                "function": func
            })
            @wraps(func)
            async def wrapper(*args, **kwargs):
                return await func(*args, **kwargs)
            return wrapper
        return decorator
    
    async def find_and_execute(self, message: str) -> Optional[Any]:
        # 查找命令(前缀+命令名/别名)
        # 构建前缀正则，例如 (?:/|!|y)
        # 对前缀进行转义以防包含特殊字符
        escaped_prefixes = [re.escape(p) for p in cmd_prefix]
        prefix_regex = f"(?:{'|'.join(escaped_prefixes)})"
        
        if re.match(f"^{prefix_regex}", message):
            for command in self.commands:
                # 检查别名列表
                # 同时也检查主命令名，将其视为别名之一处理
                potential_matches = [command["name"]] + command["alias"]
                
                for alias in potential_matches:
                    # 获取别名字符串
                    if hasattr(alias, "pattern"):
                        alias_str = alias.pattern
                    else:
                        alias_str = str(alias)
                    
                    # 构建完整匹配正则：^前缀+别名+(空格或结束)
                    # 注意：这里假设 alias_str 是普通字符串，如果包含正则特殊字符需要注意
                    # 但根据 cli.py 的用法，它们似乎是普通字符串。
                    # 为了支持正则别名，我们不转义 alias_str，但这样要求 alias_str 必须是合法的正则片段
                    
                    try:
                        # 匹配：前缀 + 别名 + (空白字符 或 字符串结束)
                        # 这样可以匹配 "/help" 或 "/help me"，但不会匹配 "/helper"
                        full_pattern = f"^{prefix_regex}{alias_str}(?:\\s|$)"
                        if re.match(full_pattern, message):
                            logger.info(f"[TomatOS_command]执行命令 {command['name']} 匹配别名 {alias_str}")
                            return await command["function"](message)
                    except re.error:
                        logger.warning(f"无效的正则别名: {alias_str}")
                        continue
                        
        return None
    
    async def handle_message(self, message: Messagebase) -> Optional[Any]:
        # 处理信息
        if hasattr(message, "__dict__"):
            msg_dict = message.__dict__
        elif isinstance(message, dict):
            msg_dict = message
        else:
            logger.error(f"不支持的消息类型: {type(message)}")
            return None

        app = msg_dict.get("adapter", "unknown")
        user = msg_dict.get("username", "unknown")
        event = msg_dict.get("event_type", "unknown")
        for handler in self.message_handlers:
            if (handler["from_adapter"] in [app, "*"] and
                handler["from_user"] in [user, "*"] and
                handler["from_event"] in [event, "*"]):
                logger.info(f"[TomatOS_message]处理信息 来自适配器 {app} 来自用户 {user} 事件类型 {event}")
                return await handler["function"](message)
        pass

def test_import():
    msghandler = TomatOS_Msghandler()
    msghandler.init_message_adapter()
    logger.info(f"已加载信息适配器数量: {len(msghandler.ada)}")

async def test_command():
    # 测试命令注册和执行
    msghandler = TomatOS_Msghandler()
    
    # 1. 基础命令
    @msghandler.on_command(
        cmd="greet",
        alias=[re.compile("hi"), re.compile("hello")],
        description="打招呼命令",
        parameters={}
    )
    async def greet_command(message: str):
        return "Hello! How can I assist you?"

    # 2. 带参数的命令模拟 (echo)
    @msghandler.on_command(
        cmd="echo",
        alias=["复读", "repeat"],
        description="复读机",
        parameters={"text": "要复读的内容"}
    )
    async def echo_command(message: str):
        # 简单的参数解析演示
        # 去掉命令前缀和命令本身
        content = re.sub(r'^[/!！y]?(?:echo|复读|repeat)\s*', '', message).strip()
        return f"Echo: {content}"

    # 列举命令
    logger.info(f"已注册命令数量: {len(msghandler.commands)}")
    
    # 测试执行命令
    logger.info("--- 测试开始 ---")
    
    # 测试1: 别名匹配
    res1 = await msghandler.find_and_execute("/hi there")
    logger.info(f"测试1 (/hi there): {res1}")
    
    # 测试2: 中文别名 + 参数
    res2 = await msghandler.find_and_execute("!复读 这是一个测试")
    logger.info(f"测试2 (!复读 这是一个测试): {res2}")
    
    # 测试3: 主命令名
    res3 = await msghandler.find_and_execute("/greet")
    logger.info(f"测试3 (/greet): {res3}")

    logger.info("--- 测试结束 ---")

if __name__ == "__main__":
    # test_import()
    asyncio.run(test_command())