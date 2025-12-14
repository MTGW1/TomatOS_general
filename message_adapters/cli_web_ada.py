import sys
import os
import json
from datetime import datetime

# 添加父目录到 Python 路径，以便可以导入 message_core
parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)

from message_adapters.message_core import Messagebase
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field
from logger import logger

# ==================== TomatOS Web终端适配器 ====================

class Webcli_Messageadapter:
    def __init__(self):
        self.adapter: str = "TomatOS_WebTerminal" # 适配器名称(本地/局域网远程终端)
        self.listenport: int = 8080  # 监听端口
        self.listenhost: str = "0.0.0.0"  # 监听地址(所有可用地址)
        self.conn_mode: str = "websocket"  # 连接模式(websocket/http)
        self.conn_type: str = "server"      # 连接类型(server/client)
        self.auth: Dict[str, Any] = {}  # 认证信息
        self.auto_reconnect: bool = True     # 自动重连(仅客户端模式)
    
    async def handle_message(self, message: Dict[str, Any]):
        """处理消息"""
        # 为缺少的字段提供默认值
        message_with_defaults = {
            "adapter": "TomatOS_WebTerminal",
            "text": "",
            "image": [],
            "file": [],
            "video": [],
            "audio": [],
            "at": [],
            "reply_to": None,
            "timestamp": None,
            "messageid": None,
            "userid": None,
            "username": "WebClient",
            "usercard": "",
            "userrole": "member",
            "conversation_id": "web_terminal",
            "is_group": False,
            "event_type": "message",
            "raw_data": {}
        }
        # 用实际消息数据覆盖默认值
        message_with_defaults.update(message)
        
        # 过滤掉Webcli_messageItem不需要的字段（如post_type）
        # 只保留Webcli_messageItem数据类定义的字段
        msg_item_fields = {
            "adapter", "text", "image", "file", "video", "audio", "at", "reply_to",
            "timestamp", "messageid", "userid", "username", "usercard", "userrole",
            "conversation_id", "is_group", "event_type", "raw_data"
        }
        filtered_message = {k: v for k, v in message_with_defaults.items() if k in msg_item_fields}
        
        msg_item = Webcli_messageItem(**filtered_message)
        msg_base = Messagebase(
            adapter=msg_item.adapter,
            text=msg_item.text,
            image=msg_item.image,
            file=msg_item.file,
            video=msg_item.video,
            audio=msg_item.audio,
            at=msg_item.at,
            reply_to=msg_item.reply_to,
            timestamp=msg_item.timestamp,
            messageid=msg_item.messageid,
            userid=msg_item.userid,
            username=msg_item.username,
            usercard=msg_item.usercard,
            userrole=msg_item.userrole,
            conversation_id=msg_item.conversation_id,
            is_group=msg_item.is_group,
            event_type=msg_item.event_type,
            raw_data=msg_item.raw_data
        )
        logger.info(f"收到Web终端消息: {msg_base.text[:50]}...")

        return msg_base
    
    async def send_message(self, msg: Messagebase, ws=None):
        """发送消息"""
        # 转为发送对象
        send_item = Webcli_messageSend(
            text=msg.text,
            image=msg.image,
            file=msg.file,
            video=msg.video,
            audio=msg.audio,
            at=msg.at,
            reply_to=msg.reply_to
        )
        
        # 如果有WebSocket连接，发送消息
        if ws:
            try:
                response_data = {
                    "type": "message",
                    "text": msg.text,
                    "timestamp": datetime.now().isoformat()
                }
                await ws.send_str(json.dumps(response_data))
                logger.info(f"通过Web终端发送消息: {msg.text}")
            except Exception as e:
                logger.error(f"发送Web终端消息失败: {e}")
        else:
            logger.warning("没有WebSocket连接，无法发送消息")
        
        return send_item

@dataclass
class Webcli_messageItem:    
    adapter: str = "TomatOS_WebTerminal"  # 适配器名称(TomatOS Web终端)
    text: str = ""  # 文本消息
    image: List[str] = field(default_factory=list) # 图片 url/path 列表
    file: List[str] = field(default_factory=list)  # 文件 url/path 列表
    video: List[str] = field(default_factory=list)  # 视频 url/path 列表
    audio: List[str] = field(default_factory=list)  # 音频 url/path 列表
    at: List[int] = field(default_factory=list)  # 提及用户列表
    reply_to: Optional[str] = None  # 回复的消息ID

    timestamp: Optional[int] = None  # 时间戳
    messageid: Optional[str] = None  # 消息ID
    userid: Optional[int] = None  # 用户ID
    username: Optional[str] = None  # 用户名
    usercard: Optional[str] = None  # 用户卡片
    userrole: Optional[str] = None  # 用户角色

    conversation_id: Optional[str] = None  # 会话ID
    is_group: Optional[bool] = None  # 会话是否群聊
    event_type: Optional[str] = None  # 事件类型
    raw_data: Optional[Dict[str, Any]] = None  # 原始数据

@dataclass
class Webcli_messageSend:
    """Web终端发送消息格式"""
    text: str = ""  # 文本消息
    image: List[str] = field(default_factory=list) # 图片 url/path 列表
    file: List[str] = field(default_factory=list)  # 文件 url/path 列表
    video: List[str] = field(default_factory=list)  # 视频 url/path 列表
    audio: List[str] = field(default_factory=list)  # 音频 url/path 列表
    at: List[int] = field(default_factory=list)  # 提及用户列表
    reply_to: Optional[str] = None  # 回复的消息ID 
    