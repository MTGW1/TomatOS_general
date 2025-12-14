#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import asyncio
import json
import os
from datetime import datetime
from aiohttp import web
import aiohttp
import platform
import sys
import psutil
import re
from logger import logger
import random
import pyotp
import hashlib
from TomatOS_UAC import UAC
from commands import CommandHandler
from dataclasses import dataclass
from bot_app import TomatOS_bot
from bot.api import bot_name
from message_adapters.message_core import Messagebase

@dataclass
class TomatOS_conn:
    service: str # 服务名称
    conn_mode: str # 连接模式 (websocket/http)
    conn_type: str # 连接类型 (server/client)
    ws: web.WebSocketResponse # WebSocket连接对象
    http: web.Request # HTTP请求对象
    conn_host: str # 连接主机地址
    conn_port: int # 连接端口
# 初始化 UAC
uac = UAC()


server_prompt = ["TomatOS-Server/1.0", "TomatOS/1.0", "TomatOS[I'm Watching You]/1.0", "TomatOS-Hello/1.0", "TomatOS/114514.1919810", "YummyShaoBing-TomatOS/1.0", "aminuos-TomatOS/1.0", f"TomatOS-Bot/{bot_name}/1.0"] # 神秘服务器名字

def get_server_header():
    return f"{random.choice(server_prompt)} Python/{platform.python_version()} aiohttp/{aiohttp.__version__}"

class TomatOSServer:
    def __init__(self):
        self.clients = {}
        self.bot_app = TomatOS_bot()
        self.command_handler = CommandHandler(self)

    async def start_bot(self):
        if self.bot_app:
            await self.bot_app.start()

    async def start_adapters(self):
        if not self.bot_app or not hasattr(self.bot_app, "msg_handler"):
            return
            
        # 使用集合跟踪已启动的适配器，避免重复启动
        started_adapters = set()
        for adapter in self.bot_app.msg_handler.ada:
            # 跳过 WebTerminal，因为它已经由 server.py 的主逻辑处理了
            # if adapter.adapter == "TomatOS_WebTerminal": # 注释掉这段以允许多实例
            #     continue
            
            # 检查是否已经启动过相同的适配器
            adapter_key = f"{adapter.adapter}:{getattr(adapter, 'conn_host', '0.0.0.0')}:{getattr(adapter, 'conn_port', 0)}"
            if adapter_key in started_adapters:
                logger.warning(f"跳过重复的适配器: {adapter.adapter} (已启动)")
                continue
                
            logger.info(f"正在启动适配器: {adapter.adapter}")
            if getattr(adapter, "conn_type", "") == "server":
                if getattr(adapter, "conn_mode", "") == "websocket":
                    await self.start_websocket_server(adapter)
                    started_adapters.add(adapter_key)

    async def start_websocket_server(self, adapter):
        host = getattr(adapter, "conn_host", "0.0.0.0")
        port = getattr(adapter, "conn_port", 8080)
        
        app = web.Application()
        
        async def ws_handler(request):
            ws = web.WebSocketResponse()
            await ws.prepare(request)
            
            logger.info(f"适配器 {adapter.adapter} 收到连接: {request.remote}")
            
            try:
                async for msg in ws:
                    if msg.type == aiohttp.WSMsgType.TEXT:
                        try:
                            data = json.loads(msg.data)
                            post_type = data.get("post_type")
                            
                            msg_base = None
                            if post_type == "message":
                                if hasattr(adapter, "handle_message"):
                                    msg_base = await adapter.handle_message(data)
                            elif post_type == "notice":
                                if hasattr(adapter, "handle_notice"):
                                    msg_base = await adapter.handle_notice(data)
                            
                            if msg_base:
                                # 1. 尝试作为命令执行 (仅针对文本消息)
                                if msg_base.text:
                                    cmd_response = await self.bot_app.msg_handler.find_and_execute(msg_base.text)
                                    if cmd_response:
                                        # 发送命令回复
                                        logger.info(f"命令执行结果: {cmd_response}")
                                        # 通过适配器发送回复
                                        if hasattr(adapter, "send_message"):
                                            reply_msg = Messagebase(
                                                adapter=adapter.adapter,
                                                text=str(cmd_response),
                                                image=[],
                                                file=[],
                                                video=[],
                                                audio=[],
                                                at=[],
                                                reply_to=None,
                                                timestamp=int(datetime.now().timestamp()),
                                                messageid=str(int(datetime.now().timestamp())),
                                                userid=10000,
                                                username=f"{bot_name}@TomatOS",
                                                usercard="",
                                                userrole="assistant",
                                                conversation_id="web_terminal",
                                                is_group=False,
                                                event_type="message",
                                                raw_data={}
                                            )
                                            await adapter.send_message(reply_msg, ws)
                                        continue

                                # 2. 转发给 bot_app 处理 (AI 聊天)
                                reply = await self.bot_app.handle_chat_message(msg_base)
                                if reply:
                                    logger.info(f"Bot 回复: {reply}")
                                    # 通过适配器发送回复
                                    if hasattr(adapter, "send_message"):
                                        reply_msg = Messagebase(
                                            adapter=adapter.adapter,
                                            text=str(reply),
                                            image=[],
                                            file=[],
                                            video=[],
                                            audio=[],
                                            at=[],
                                            reply_to=None,
                                            timestamp=int(datetime.now().timestamp()),
                                            messageid=str(int(datetime.now().timestamp())),
                                            userid=10000,
                                            username=f"{bot_name}@TomatOS",
                                            usercard="",
                                            userrole="assistant",
                                            conversation_id="web_terminal",
                                            is_group=False,
                                            event_type="message",
                                            raw_data={}
                                        )
                                        await adapter.send_message(reply_msg, ws)
                        except json.JSONDecodeError:
                            # 如果不是JSON，尝试作为纯文本消息处理
                            text_content = msg.data
                            if text_content:
                                # 创建简单的消息对象
                                simple_data = {
                                    "post_type": "message",
                                    "text": text_content,
                                    "timestamp": datetime.now().isoformat(),
                                    "userid": 10001,
                                    "username": "WebClient_user",
                                    "conversation_id": "web_terminal",
                                    "is_group": False
                                }
                                if hasattr(adapter, "handle_message"):
                                    msg_base = await adapter.handle_message(simple_data)
                                    if msg_base and msg_base.text:
                                        # 尝试作为命令执行
                                        cmd_response = await self.bot_app.msg_handler.find_and_execute(msg_base.text)
                                        if cmd_response:
                                            logger.info(f"命令执行结果: {cmd_response}")
                                            # 发送命令回复
                                            if hasattr(adapter, "send_message"):
                                                reply_msg = Messagebase(
                                                    adapter=adapter.adapter,
                                                    text=str(cmd_response),
                                                    image=[],
                                                    file=[],
                                                    video=[],
                                                    audio=[],
                                                    at=[],
                                                    reply_to=None,
                                                    timestamp=int(datetime.now().timestamp()),
                                                    messageid=str(int(datetime.now().timestamp())),
                                                    userid=10000,
                                                    username=f"{bot_name}@TomatOS",
                                                    usercard="",
                                                    userrole="assistant",
                                                    conversation_id="web_terminal",
                                                    is_group=False,
                                                    event_type="message",
                                                    raw_data={}
                                                )
                                                await adapter.send_message(reply_msg, ws)
                                        else:
                                            # 转发给 bot_app 处理
                                            reply = await self.bot_app.handle_chat_message(msg_base)
                                            if reply:
                                                logger.info(f"Bot 回复: {reply}")
                                                # 发送AI回复
                                                if hasattr(adapter, "send_message"):
                                                    reply_msg = Messagebase(
                                                        adapter=adapter.adapter,
                                                        text=str(reply),
                                                        image=[],
                                                        file=[],
                                                        video=[],
                                                        audio=[],
                                                        at=[],
                                                        reply_to=None,
                                                        timestamp=int(datetime.now().timestamp()),
                                                        messageid=str(int(datetime.now().timestamp())),
                                                        userid=10000,
                                                        username=f"{bot_name}@TomatOS",
                                                        usercard="",
                                                        userrole="assistant",
                                                        conversation_id="web_terminal",
                                                        is_group=False,
                                                        event_type="message",
                                                        raw_data={}
                                                    )
                                                    await adapter.send_message(reply_msg, ws)
                    elif msg.type == aiohttp.WSMsgType.ERROR:
                        logger.error(f'ws连接错误 {ws.exception()}')
            finally:
                logger.info(f"适配器 {adapter.adapter} 连接关闭")
            return ws

        app.router.add_get('/', ws_handler)
        
        runner = web.AppRunner(app)
        await runner.setup()
        # 设置 reuse_port 和 reuse_address 以避免 TIME_WAIT 状态导致的端口占用问题
        site = web.TCPSite(runner, host, port, reuse_port=True, reuse_address=True)
        await site.start()
        logger.info(f"适配器 {adapter.adapter} 监听在 ws://{host}:{port}")

    def generate_color(self, password, salt=""):
        # 使用 sha256 生成哈希
        h = hashlib.sha256((password + str(salt)).encode()).hexdigest()
        # 取前6位作为颜色
        color = "#" + h[:6]
        return color, h

    async def handle_websocket(self, request):
        logger.info(f"收到 WebSocket 连接请求: {request.remote}")
        ws = web.WebSocketResponse()
        ws.headers['Server'] = get_server_header()
        await ws.prepare(request)

        # Store request object in ws for later use (e.g. logging IP)
        ws._req = request

        await self.register(ws, request.host)
        try:
            async for msg in ws:
                logger.debug(f"接收到信息: {msg}")
                if msg.type == aiohttp.WSMsgType.TEXT:
                    try:
                        data = json.loads(msg.data)
                        await self.process_message(ws, data)
                    except json.JSONDecodeError:
                        pass
                elif msg.type == aiohttp.WSMsgType.ERROR:
                    logger.error(f'ws连接错误 {ws.exception()}')
        finally:
            await self.unregister(ws)
        
        return ws

    async def register(self, ws, host):
        self.clients[ws] = {"state": "init", "host": host}

    async def unregister(self, ws):
        if ws in self.clients:
            del self.clients[ws]

    async def process_message(self, ws, data):
        client_state = self.clients[ws]
        msg_type = data.get("type")

        if msg_type == "init":
            # 初始化连接，检测客户端信息
            user_agent = data.get("userAgent", "")
            language = data.get("language", "zh-CN")
            logger.debug(f"连接用户的 userAgent: {user_agent}, 语言: {language}")
            
            if "Win" in user_agent:
                client_state["os"] = "Windows"
            elif "Mac" in user_agent:
                client_state["os"] = "macOS"
            elif "Harmony" in user_agent:
                client_state["os"] = "HarmonyOS"
            elif "Android" in user_agent:
                client_state["os"] = "Android"
            elif "Linux" in user_agent:
                client_state["os"] = "Linux"
            else:
                client_state["os"] = "Linux"
            
            client_state["language"] = language
            
            # 尝试提取设备名称
            device_name = "localhost"
            if client_state["os"] == "HarmonyOS":
                # 尝试提取设备名称
                match = re.search(r"(?:HarmonyOS|Android[^;]+);\s*([^;)]+)", user_agent)
                if match:
                    parts = match.group(1).split("Build")[0].strip()
                    device_name = parts
            elif client_state["os"] == "Android":
                match = re.search(r"Android[^;]+;\s*([^;)]+)", user_agent)
                if match:
                    parts = match.group(1).split("Build")[0].strip()
                    device_name = parts
            elif client_state["os"] == "macOS":
                device_name = "macbook"
            elif client_state["os"] == "Windows":
                device_name = "PC"
            
            # 清理设备名称中的空格
            device_name = re.sub(r'\s+', '-', device_name)
            client_state["device_name"] = device_name
            
            logger.info(f"检测到操作系统: {client_state['os']}, 设备名称: {device_name}")

            # 模拟本地 shell，显示 SSH 连接提示
            os_type = client_state["os"]
            host = client_state.get("host", "localhost")
            
            if os_type == "Windows":
                if language.startswith("zh"):
                    await self.send_output(ws, "Windows PowerShell")
                    await self.send_output(ws, " ")
                    await self.send_output(ws, "版权所有 (C) Microsoft Corporation。保留所有权利。")
                    await self.send_output(ws, " ")
                    await self.send_output(ws, "安装最新的 PowerShell，以获得新功能和改进！https://aka.ms/PSWindows")
                    await self.send_output(ws, " ")
                else:
                    await self.send_output(ws, "Windows PowerShell")
                    await self.send_output(ws, " ")
                    await self.send_output(ws, "Copyright (C) Microsoft Corporation. All rights reserved.")
                    await self.send_output(ws, " ")
                    await self.send_output(ws, "Install the latest PowerShell for new features and improvements! https://aka.ms/PSWindows")
                    await self.send_output(ws, " ")
                
                prompt = "PS C:\\Windows\\System32>"
                cmd = f"ssh TomatOS@{host}"
                await self.send_output(ws, f'<span class="prompt">{prompt}</span> <span class="command">{cmd}</span>')
                
            elif os_type == "macOS":
                prompt = f"user@{device_name} ~ %"
                cmd = f"ssh tomatos@{host}"
                await self.send_output(ws, f'<span class="prompt">{prompt}</span> <span class="command">{cmd}</span>')
                
            elif os_type == "Linux":
                prompt = "user@linux:~$"
                cmd = f"ssh TomatOS@{host}"
                await self.send_output(ws, f'<span class="prompt">{prompt}</span> <span class="command">{cmd}</span>')
                
            elif os_type == "Android":
                prompt = f"user@{device_name}:/ $"
                cmd = f"ssh -p 8022 tomatos@{host}"
                await self.send_output(ws, f'<span class="prompt">{prompt}</span> <span class="command">{cmd}</span>')

            elif os_type == "HarmonyOS":
                prompt = f"user@{device_name}:/ $"
                cmd = f"ssh -p 8022 tomatos@{host}"
                await self.send_output(ws, f'<span class="prompt">{prompt}</span> <span class="command">{cmd}</span>')

            #   开始登录流程
            await self.send_prompt(ws, "login as: ", is_password=False)
            client_state["state"] = "login_user"

        elif msg_type == "input":
            content = data.get("content")
            state = client_state["state"]

            if state == "login_user":
                client_state["username"] = content
                await self.send_prompt(ws, "password: ", is_password=True)
                client_state["state"] = "login_pass"

            elif state == "login_pass":
                password_input = content
                username_input = client_state.get("username")
                
                is_admin = False
                login_success = False
                
                # 获取配置的用户名
                target_username = uac.get_admin_username()
                
                # Case 1: 尝试 Admin 登录 (必须匹配管理员用户名)
                if username_input == target_username:
                    # 尝试分离 TOTP (假设最后6位是 TOTP)
                    totp_secret = uac.get_totp_secret()
                    
                    if len(password_input) > 6:
                        potential_pass = password_input[:-6]
                        potential_code = password_input[-6:]
                        
                        # 验证密码部分
                        pass_ok, _ = uac.verify_password(potential_pass)
                        if pass_ok:
                            # 验证 TOTP 部分
                            totp = pyotp.TOTP(totp_secret)
                            if totp.verify(potential_code): # 使用 verify 方法更安全，允许一定的时间偏差
                                is_admin = True
                                login_success = True
                                logger.warning(f"管理员登录成功: {username_input} 来自 {ws._req.remote}")
                else:
                    # Case 2: 访客登录 (忽略密码)
                    is_admin = False
                    login_success = True
                    
                    # 生成访客颜色
                    salt = uac.config.get("salt", "default_salt") if uac.config else "default_salt"
                    # 如果密码为空，使用用户名作为种子，避免空密码颜色都一样
                    seed = password_input if password_input else username_input
                    color, h = self.generate_color(seed, salt)
                    client_state["username_color"] = color
                    client_state["user_id"] = h[:16]
                    
                    logger.info(f"访客登录成功(忽略密码): {username_input} 来自 {ws._req.remote}")

                if login_success:
                    client_state["auth_level"] = "admin" if is_admin else "guest"
                    
                    # 如果是管理员，也生成一个 user_id (使用用户名作为种子)
                    if is_admin:
                        salt = uac.config.get("salt", "default_salt") if uac.config else "default_salt"
                        _, h = self.generate_color(username_input, salt)
                        client_state["user_id"] = h[:16]

                    # 设置客户端 OS 类型
                    client_state["os"] = "Linux"  # 默认使用 Linux shell
                    
                    if is_admin:
                        await self.send_output(ws, f'\nAuthentication successful. 欢迎回家 <span style="color: #ff4444; font-weight: bold;">[ADMIN]</span>\n {username_input}')
                    else:
                        await self.send_output(ws, "\nAuthentication successful. Welcome to TomatOS. meow ~\n")
                        
                    await self.show_welcome_screen(ws, client_state)
                    client_state["state"] = "shell"
                    
                    prompt = self.get_prompt(client_state)
                    await self.send_prompt(ws, prompt, is_password=False)
                else:
                    logger.warning(f"登录失败: {username_input} 来自 {ws._req.remote}")
                    await self.send_output(ws, "\nAccess Denied.\n")
                    await self.send_prompt(ws, "login as: ", is_password=False)
                    client_state["state"] = "login_user"

            elif state == "shell": 
                result = await self.command_handler.process_command(ws, content)
                if result is not False:
                    prompt = self.get_prompt(client_state)
                    await self.send_prompt(ws, prompt, is_password=False)

    def get_prompt(self, client_state):
        state = client_state.get("state")
        username = client_state.get("username", "user")
        auth_level = client_state.get("auth_level", "guest")
        
        # 如果已登录（shell 状态），显示远程服务器提示符（Linux 风格）
        if state == "shell":
            # 管理员显示井号 #，访客显示美元符号 $
            symbol = "#" if auth_level == "admin" else "$"
            
            if auth_level == "admin":
                user_span = f'<span class="username-admin">{username}</span>'
            else:
                color = client_state.get("username_color")
                if color:
                    user_span = f'<span style="color: {color}; font-weight: bold;">{username}</span>'
                else:
                    user_span = f'<span class="username">{username}</span>'
            
            return f'{user_span}@<span class="hostname">TomatOS</span>:~{symbol} '

        # Otherwise, show the local simulated prompt
        os_type = client_state.get("os", "Linux")
        device_name = client_state.get("device_name", "localhost")
        
        if os_type == "Windows":
            return f"PS C:\\Windows\\System32> "
        elif os_type == "macOS":
            return f"{username}@{device_name} ~ % "
        elif os_type == "Android":
            return f"{username}@{device_name}:/ $ "
        elif os_type == "HarmonyOS":
            return f"{username}@{device_name}:/ $ "
        else:
            return f"{username}@TomatOS:~$ "
        
    def get_system_info(self):
        uname = platform.uname()
        uptime = psutil.boot_time()
        return uname, uptime

    async def handle_bot_chat(self, ws, text):
        if not self.bot_app:
             await self.send_output(ws, "Bot not available.")
             return

        # 1. 尝试作为命令执行
        cmd_response = await self.bot_app.msg_handler.find_and_execute(text)
        if cmd_response:
            # 格式化命令回复
            bot_prompt = f'<span class="username" style="color: #fffc67;">⭐{bot_name}</span>@<span class="hostname">TomatOS</span>:~# '
            await self.send_output(ws, f'<span class="prompt">{bot_prompt}</span> <span class="output">{cmd_response}</span>')
            return

        client_state = self.clients[ws]
        username = client_state.get("username", "user")
        user_id = client_state.get("user_id", "unknown")
        
        # 构造消息
        msg_obj = {
            "adapter": "TomatOS_WebTerminal",
            "text": text,
            "image": [],
            "file": [],
            "video": [],
            "audio": [],
            "at": [],
            "reply_to": None,
            "timestamp": int(datetime.now().timestamp()),
            "messageid": str(int(datetime.now().timestamp())),
            "userid": user_id, 
            "username": username,
            "usercard": "",
            "userrole": "member",
            "conversation_id": "web_terminal",
            "is_group": False,
            "event_type": "message",
            "raw_data": {}
        }
        
        try:
            # 2. 作为普通消息处理 (AI 聊天)
            reply = await self.bot_app.handle_chat_message(msg_obj)
            
            # 格式化回复
            bot_prompt = f'<span class="username" style="color: #fffc67;">⭐{bot_name}</span>@<span class="hostname">TomatOS</span>:~# '
            
            await self.send_output(ws, f'<span class="prompt">{bot_prompt}</span> <span class="output">{reply}</span>')
            
        except Exception as e:
            await self.send_output(ws, f"Bot Error: {str(e)}\n")

    async def send_output(self, ws, content, class_name="line"):
        await ws.send_str(json.dumps({
            "type": "output",
            "content": content,
            "className": class_name
        }))

    async def send_prompt(self, ws, content, is_password=False):
        await ws.send_str(json.dumps({
            "type": "prompt",
            "content": content,
            "isPassword": is_password
        }))

    async def show_welcome_screen(self, ws, client_state):
        username = client_state.get("username", "user")
        os_type = client_state.get("os", "Linux")
        uname, uptime = self.get_system_info()

        await self.send_output(ws, f'<div class="welcome-line">欢迎来到 TomatOS 喵~</div>')

        welcome_msg = """
  _______                     _    ____   _____ 
 |__   __|                   | |  / __ \\ / ____|
    | | ___  _ __ ___   __ _ | |_| |  | | (___  
    | |/ _ \\| '_ ` _ \\ / _` || __| |  | |\\___ \\ 
    | | (_) | | | | | | (_| || |_| |__| |____) |
    |_|\\___/|_| |_| |_|\\__,_||\\__|\\____/|_____/ 
"""
        await self.send_output(ws, welcome_msg, "ascii-art")


        await self.send_output(ws, f'<span class="prompt"><span class="username">{username}</span>@<span class="hostname">TomatOS</span>:~$</span> <span class="command">uname -a</span>')
        await self.send_output(ws, f'<span class="output">{uname.system} {uname.node} {uname.release} {uname.version} {uname.machine} {"GNU/Linux" if uname.system != "Windows" else ""}</span>')
        
        await self.send_output(ws, f'<span class="prompt"><span class="username">{username}</span>@<span class="hostname">TomatOS</span>:~$</span> <span class="command">whoami && hostname</span>')
        await self.send_output(ws, f'<span class="output">{username}<br>TomatOS</span>')
        
        await self.send_output(ws, f'<span class="prompt"><span class="username">{username}</span>@<span class="hostname">TomatOS</span>:~$</span> <span class="command">uptime</span>')
        
        # 计算系统运行时间
        boot_dt = datetime.fromtimestamp(psutil.boot_time())
        now_dt = datetime.now()
        delta = now_dt - boot_dt
        days = delta.days
        hours, rem = divmod(delta.seconds, 3600)
        minutes, _ = divmod(rem, 60)
        uptime_str = f"up {days} days, {hours}:{minutes:02}" if days else f"up {hours}:{minutes:02}"
        
        # 获取系统负载和用户数
        try:
            load = psutil.getloadavg()
        except (AttributeError, OSError):
            load = (0.0, 0.0, 0.0)
            
        users = len(psutil.users())
        
        output = f"{now_dt.strftime('%H:%M:%S')} {uptime_str},  {users} user{'s' if users!=1 else ''},  load average: {load[0]:.2f}, {load[1]:.2f}, {load[2]:.2f}"
        await self.send_output(ws, f'<span class="output">{output}</span>')

    def startup():
        pass


async def index(request):
    logger.info(f"收到 HTTP 访问请求: {request.remote}")
    return web.FileResponse(os.path.join(os.path.dirname(__file__), 'web', 'index.html'))

async def logging_middleware(app, handler):
    async def middleware_handler(request):
        # 简单的反爬虫/扫描器检测
        user_agent = request.headers.get('User-Agent', '').lower()
        # 常见爬虫关键字
        bot_keywords = ['bot', 'crawl', 'spider', 'slurp', 'scanner', 'curl', 'wget']
        
        # 如果是爬虫，直接返回 403
        if any(keyword in user_agent for keyword in bot_keywords):
            logger.warning(f"拦截爬虫请求: {user_agent} 来自 {request.remote}")
            return web.Response(status=403, text=f"⭐{bot_name}@TomatOS: [403]请求被{bot_name}吃掉了......\n(Permission Denied: Your request has been ate by {bot_name}.)")

        logger.info(f"请求: {request.method} {request.path} 来自 {request.remote}")
        response = await handler(request)
        if not response.prepared:
            response.headers['Server'] = get_server_header()
        return response
    return middleware_handler

async def console_input_loop(server: TomatOSServer):
    """控制台输入循环"""
    logger.info("控制台输入已就绪")
    loop = asyncio.get_event_loop()
    while True:
        try:
            cmd = await loop.run_in_executor(None, input, "")
            if cmd:
                if cmd.lower() in ["exit", "quit"]:
                    # 我们不能直接退出，因为这会杀死服务器
                    # 但我们可以停止机器人
                    await server.bot_app.bot_run_command("stop")
                    logger.info("机器人已停止")
                    continue
                
                # Pass to bot
                res = await server.bot_app.handle_console_input(cmd)
                if res:
                    print(res)
        except EOFError:
            break
        except Exception as e:
            logger.error(f"控制台错误: {e}")
            await asyncio.sleep(1)

async def on_startup(app):
    server = app['server']
    await server.start_bot()
    await server.start_adapters()
    # Start console loop in background
    asyncio.create_task(console_input_loop(server))

def main():
    server = TomatOSServer()
    app = web.Application(middlewares=[logging_middleware])
    app['server'] = server
    app.on_startup.append(on_startup)
    
    # 获取 web 目录的绝对路径
    web_dir = os.path.join(os.path.dirname(__file__), 'web')
    
    app.add_routes([
        web.get('/', index),
        web.get('/ws', server.handle_websocket),
        web.static('/', web_dir)
    ])
    
    print("服务器启动喵~ 监听端口: http://0.0.0.0:8765")
    web.run_app(app, host='0.0.0.0', port=8765)

def test():

    # 测试系统信息获取
    server = TomatOSServer()
    uname, uptime = server.get_system_info()
    print("System Info:", uname)
    print("Uptime:", uptime)

if __name__ == "__main__":
    # test()
    try:
        main()
    except KeyboardInterrupt:
        print("用户手动关闭了服务器喵~")