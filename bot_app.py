import asyncio
from typing import Union
from message import TomatOS_Msghandler
from message_adapters.message_core import Messagebase
from logger import logger
import os
import re
from aiohttp import web
import aiohttp
import datetime
import inspect

# 导入新系统接口
from bot.ai_chat import create_ai_chat, AIChat, ChatMessage
from bot.model import get_model
from bot.tools import gettools
from bot.memory_diary import memories
from bot.api import PROMPT_TEMPLATES, bot_name, dev_auth

# 实例化消息处理器
msg_handler = TomatOS_Msghandler()

class TomatOS_bot:
    def __init__(self):
        self.bot_instance = None # 机器人实例（新系统）
        self.default_model = "deepseek-chat"
        self.commands = []
        self.msg_handler = msg_handler # 暴露消息处理器
        
        # 将 msg_handler 中注册的命令绑定到当前实例
        for cmd in msg_handler.commands:
            if hasattr(self, cmd['function'].__name__):
                cmd['function'] = getattr(self, cmd['function'].__name__)
        
        # 将 msg_handler 中注册的消息处理器绑定到当前实例
        for handler in msg_handler.message_handlers:
            if hasattr(self, handler['function'].__name__):
                handler['function'] = getattr(self, handler['function'].__name__)
        
        # 同步命令列表
        self.commands = msg_handler.commands

    def register_ai_tools(self):
        """将 AI 工具注册为命令"""
        tools_manager = gettools()
        if not tools_manager:
            return

        for name, tool_info in tools_manager._tools.items():
            # 跳过已存在的命令
            if any(cmd['name'] == name for cmd in self.msg_handler.commands):
                continue

            func = tools_manager._tool_functions.get(name)
            if not func:
                continue

            # 创建命令包装器
            async def tool_wrapper(message: str, _func=func, _name=name):
                # 简单的参数解析：按空格分割
                # 假设命令格式: /tool_name arg1 arg2 ...
                parts = message.strip().split()
                args = parts[1:] if len(parts) > 1 else []
                
                # 获取函数签名
                sig = inspect.signature(_func)
                bound_args = {}
                params = list(sig.parameters.values())
                
                try:
                    for i, param in enumerate(params):
                        if i < len(args):
                            val = args[i]
                            # 简单的类型转换
                            if param.annotation == int:
                                val = int(val)
                            elif param.annotation == float:
                                val = float(val)
                            elif param.annotation == bool:
                                val = val.lower() in ('true', '1', 'yes')
                            bound_args[param.name] = val
                    
                    result = await _func(**bound_args)
                    return f"工具 {_name} 执行结果:\n{str(result)}"
                except Exception as e:
                    return f"工具 {_name} 执行失败: {str(e)}"

            # 注册命令
            description = tool_info.get("function", {}).get("description", "AI Tool")
            self.msg_handler.commands.append({
                "name": name,
                "alias": [name],
                "description": description,
                "parameters": tool_info.get("function", {}).get("parameters", {}),
                "function": tool_wrapper
            })
            logger.info(f"已将 AI 工具 {name} 注册为命令")
        
        # 同步更新 self.commands
        self.commands = self.msg_handler.commands

    async def start(self):
        """启动机器人核心服务"""
        logger.info("正在启动机器人核心服务...")
        # 初始化消息适配器
        msg_handler.init_message_adapter()
        
        # 注册 AI 工具
        self.register_ai_tools()
        
        # 自动启动 AI 实例
        await self.bot_run_command("start")
        logger.info("机器人核心服务启动完成")

    def generate_session_id(self, bot_msg: dict) -> str:
        """智能会话ID生成器，支持私聊和群聊
        
        会话ID格式:
        - 私聊: {platform}/private/{user_id}/{conv_id}
        - 群聊: {platform}/group/{group_id}/{user_id}
        
        参数:
            bot_msg: 包含用户和场景信息的字典
        
        返回:
            生成的会话ID字符串
        """
        user_id = bot_msg.get('user_id', 'unknown')
        conv_id = bot_msg.get('conv_id', 'default')
        is_group = bot_msg.get('is_group', False)
        group_id = bot_msg.get('group_id', conv_id)  # 如果没有group_id，使用conv_id
        platform = bot_msg.get('platform', 'unknown')
        
        if is_group:
            # 群聊模式: 平台/群聊/群ID/用户ID
            return f"{platform}/group/{group_id}/{user_id}"
        else:
            # 私聊模式: 平台/私聊/用户ID/对话场景
            return f"{platform}/private/{user_id}/{conv_id}"

    @msg_handler.on_command(cmd="help",
                               alias=[r"help", r"帮助", r"cmds", r"命令"],
                               description="显示可用命令列表",
                               parameters={})
    async def help_command(self, message: str):
        # 移除命令前缀和 help 命令本身
        cmd_pattern = r'^[/!！y]?(?:help|帮助|cmds|命令)\s*'
        args = re.sub(cmd_pattern, '', message, flags=re.IGNORECASE).strip()
        
        # 直接使用 msg_handler.commands 确保获取最新命令列表
        available_commands = self.msg_handler.commands
        
        # 如果有参数，尝试匹配命令
        if args:
            detailed_cmds = [cmd for cmd in available_commands if cmd["name"] in args]
            if detailed_cmds:
                help_text = "详细帮助:\n"
                for cmd in detailed_cmds:
                    help_text += f"{cmd['name']}: {cmd['description']}\n"
                return help_text
            else:
                return f"未找到命令: {args}"
        
        # 否则显示所有命令及其描述
        help_text = "可用命令:\n"
        for cmd in available_commands:
            help_text += f"{cmd['name']}: {cmd['description']}\n"
        return help_text
    
    @staticmethod
    def color_to_ansi(fcolor: tuple = (255, 255, 255), bcolor: tuple = None, text="", style=""):
        # rgb数组
        def rgb_to_ansi(r, g, b, is_background=False):
            code = 48 if is_background else 38
            return f"\033[{code};2;{r};{g};{b}m"
        
        ansi_sequence = ""
        if fcolor:
            ansi_sequence += rgb_to_ansi(*fcolor, is_background=False)
        if bcolor:
            ansi_sequence += rgb_to_ansi(*bcolor, is_background=True)
        style_codes = {"bold": "1", "underline": "4", "reversed": "7"}
        for s in style.split(","):
            if s in style_codes:
                ansi_sequence += f"\033[{style_codes[s]}m"
        reset_sequence = "\033[0m"
        return f"{ansi_sequence}{text}{reset_sequence}"
    
    @msg_handler.on_message(from_adapter="*", from_user="*", from_event="*")
    async def handle_chat_message(self, message: Union[Messagebase, dict]):
        """处理聊天消息"""
        if not self.bot_instance:
            return "机器人未启动，请先使用 /bot_run start 启动机器人。"
        
        # 统一转换为字典
        if hasattr(message, "__dict__"):
            msg_dict = message.__dict__
        elif isinstance(message, dict):
            msg_dict = message
        else:
            logger.error(f"不支持的消息类型: {type(message)}")
            return "内部错误: 消息类型不支持"

        # 转换为 bot 需要的 messageitem 格式
        # 注意：这里做了一个简单的转换，实际可能需要更严谨的类型检查
        bot_msg = {
            "text": msg_dict.get("text", ""),
            "user_id": str(msg_dict.get("userid", "unknown")),
            "user_name": msg_dict.get("username", "unknown"),
            "conv_id": msg_dict.get("conversation_id", "default"),
            "timestamp": datetime.datetime.now().isoformat(),
            "is_group": msg_dict.get("is_group", False),
            "group_id": msg_dict.get("group_id", msg_dict.get("conversation_id", "default")),  # 群聊ID
            "platform": msg_dict.get("platform", "unknown"),  # 平台标识
            "user_role": msg_dict.get("userrole", "user"),
            "image": msg_dict.get("image"),
            "video": msg_dict.get("video"),
            "audio": msg_dict.get("audio"),
            "user_card": msg_dict.get("usercard", "")
        }
        
        logger.info(f"收到聊天消息: {bot_msg['text']}")
        
        # 使用新系统接口处理消息
        try:
            # 获取或创建会话（使用智能会话ID生成器）
            session_id = self.generate_session_id(bot_msg)
            session = self.bot_instance.get_session(session_id)
            if not session:
                # 根据场景选择系统提示词
                if bot_msg.get('is_group', False):
                    # 群聊使用群聊专用提示词
                    system_prompt = PROMPT_TEMPLATES.get("group", PROMPT_TEMPLATES.get("default", ""))
                else:
                    # 私聊使用默认提示词（工具调用指导会在AI层动态添加）
                    system_prompt = PROMPT_TEMPLATES.get("default", "")
                
                session = self.bot_instance.create_session(
                    session_id, 
                    system_prompt
                )
            
            # 调用聊天
            response = await self.bot_instance.chat(session_id, bot_msg['text'])
            # 优先使用final_response字段，如果没有则使用response字段
            raw_response = response.get("final_response", response.get("response", "喵？"))
            # 处理多余的空行
            if raw_response:
                # 替换连续两个或更多换行符为一个换行符
                cleaned_response = re.sub(r'\n\n+|\r\n\r\n+', '\n', raw_response)
                return cleaned_response
            return raw_response
            
        except Exception as e:
            logger.error(f"处理聊天消息失败: {e}")
            return f"处理消息时出错: {str(e)}"

    @msg_handler.on_command(cmd="bot_run",
                               alias=[r"botrun"],
                               description="""机器人运行命令, start: 启动机器人; stop: 停止机器人; status: 机器人状态, restart: 重启机器人""",
                               parameters={})
    async def bot_run_command(self, message: str):
        # 提取命令参数（去除命令前缀和命令名）
        # 消息格式可能是: "/botrun start" 或 "ybotrun start" 或 "!bot_run start"
        
        # 移除命令前缀（支持 /, !, ！, y）和命令名
        # 注意：需要转义中文感叹号 "！"
        cmd_pattern = r'^[/!！y]?(?:bot_run|botrun)\s*'
        clean_message = re.sub(cmd_pattern, '', message, flags=re.IGNORECASE).strip()
        
        # 如果没有参数，显示帮助
        if not clean_message:
            return "请指定操作: start, stop, restart, status"
        
        # 提取操作
        args = clean_message.split()
        action = None
        for arg in args:
            if arg in ["start", "stop", "restart", "status"]:
                action = arg
                break
        
        if not action:
            return "请指定操作: start, stop, restart, status"

        if action == "start":
            if self.bot_instance:
                return "机器人已经在运行中"
            try:
                logger.info("正在启动机器人（新系统）...")
                # 使用新系统创建AI聊天实例
                self.bot_instance = create_ai_chat(
                    model_name=self.default_model,
                    tools_enabled=True,
                    system_prompt=PROMPT_TEMPLATES.get("default", "")
                )
                logger.info(f"机器人启动成功，使用模型: {self.default_model}")
                return "机器人启动成功"
            except Exception as e:
                logger.error(f"机器人启动失败: {e}")
                return f"机器人启动失败: {e}"
        
        elif action == "stop":
            if not self.bot_instance:
                return "机器人未运行"
            self.bot_instance = None
            return "机器人已停止"
            
        elif action == "restart":
            self.bot_instance = None
            try:
                # 已迁移到新系统，此代码不再使用
                return "机器人重启成功"
            except Exception as e:
                return f"机器人重启失败: {e}"
                
        elif action == "status":
            status = "运行中" if self.bot_instance else "未运行"
            return f"机器人状态: {status}"

    async def handle_console_input(self, cmd: str):
        """处理控制台输入"""
        if not cmd:
            return
            
        # 尝试作为命令执行
        res = await msg_handler.find_and_execute(cmd)
        if res:
            return res
        else:
            # 作为普通消息处理
            message_data: Messagebase = {
                "adapter": "TomatOS_Console",
                "text": cmd,
                "userid": "developer",
                "username": f"{dev_auth}",
                "conversation_id": "console_chat",
                "is_group": False,
                "userrole": "admin",
                "event_type": "message",
                "image": [], "file": [], "video": [], "audio": [], "at": [], "reply_to": None,
                "timestamp": int(datetime.datetime.now().timestamp()),
                "messageid": None, "usercard": None, "raw_data": None
            }
            # 直接调用 handle_chat_message 或者通过 msg_handler 分发
            # 这里直接调用 handle_chat_message 因为它是主要的聊天逻辑
            return await self.handle_chat_message(message_data)
        
async def start_bot_terminal():
    """启动机器人终端交互"""
    bot = TomatOS_bot()
    await bot.start()
    
    print("=== TomatOS 机器人终端 ===")
    print("输入命令或消息，输入 'exit' 退出")
    
    loop = asyncio.get_event_loop()
    while True:
        cmd = await loop.run_in_executor(None, input, ">> ")
        if cmd.lower() in ["exit", "quit"]:
            print("退出机器人终端")
            break
        response = await bot.handle_console_input(cmd)
        if response:
            print(f"<< {response}")

if __name__ == "__main__":
    try:
        asyncio.run(start_bot_terminal())
    except KeyboardInterrupt:
        logger.info("机器人终端已退出")
    except Exception as e:
        logger.exception(f"启动机器人终端失败: {e}")