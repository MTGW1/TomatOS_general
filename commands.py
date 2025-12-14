import platform
import json
from datetime import datetime
import psutil
import asyncio

class CommandHandler:
    def __init__(self, server):
        self.server = server
        self.active_battles = {}

    async def process_command(self, ws, command):
        if not command:
            return True
        
        # 检查是否在聊天模式
        if ws in self.active_battles:
            battle = self.active_battles[ws]
            if command.strip().lower() in ["exit", "quit", "stop"]:
                await battle.stop()
                if ws in self.active_battles:
                    del self.active_battles[ws]
                await self.server.send_output(ws, "已退出闲聊模式。\n")
                return True
            else:
                await battle.handle_user_message(command)
                return False
        
        cmd_parts = command.split()
        cmd = cmd_parts[0]

        if cmd == "clear":
            await ws.send_str(json.dumps({"type": "clear"}))
        elif cmd == "uname":
            uname = platform.uname()
            if len(cmd_parts) > 1 and cmd_parts[1] == "-a":
                if uname.system == "Windows":
                    output = f"{uname.system} {uname.node} {uname.release} {uname.version} {uname.machine}"
                else:
                    output = f"{uname.system} {uname.node} {uname.release} {uname.version} {uname.machine} GNU/Linux"
            else:
                output = uname.system
            await self.server.send_output(ws, output + "\n")
        elif cmd == "whoami":
            username = self.server.clients[ws].get("username", "user")
            await self.server.send_output(ws, f"{username}\n")
        elif cmd == "date":
            await self.server.send_output(ws, f"{datetime.now().strftime('%a %b %d %H:%M:%S %Z %Y')}\n")
        elif cmd == "help":
            await self.server.send_output(ws, "Available commands: uname, whoami, date, clear, help, ai_chat\n")
        else:
            if self.server.bot_app:
                await self.server.handle_bot_chat(ws, command)
            else:
                await self.server.send_output(ws, f"Command not found: {cmd}\n")
        
        return True
