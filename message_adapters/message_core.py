from typing import Dict, Any, List, Optional, TypedDict, Union
import os
from dataclasses import dataclass, field
import websockets
import aiohttp

@dataclass
class Messagebase:
    adapter: str  # 适配器名称

    text: str
    image: List[str] # 图片 url/path 列表
    file: List[str]  # 文件 url/path 列表
    video: List[str]  # 视频 url/path 列表
    audio: List[str]  # 音频 url/path 列表
    at: List[int]  # 提及用户列表
    reply_to: Optional[str]  # 回复的消息ID

    timestamp: Optional[int]  # 时间戳
    messageid: Optional[str]  # 消息ID
    userid: Optional[int]  # 用户ID
    username: Optional[str]  # 用户名
    usercard: Optional[str]  # 用户卡片
    userrole: Optional[str]  # 用户角色

    conversation_id: Optional[str]  # 会话ID
    is_group: Optional[bool]  # 会话是否群聊

    event_type: Optional[str]  # 事件类型
    raw_data: Optional[Dict[str, Any]]  # 原始数据

    async def to_dict(self) -> Dict[str, Any]:
        return {
            "adapter": self.adapter,
            "text": self.text,
            "image": self.image,
            "file": self.file,
            "video": self.video,
            "audio": self.audio,
            "at": self.at,
            "reply_to": self.reply_to,
            "timestamp": self.timestamp,
            "messageid": self.messageid,
            "userid": self.userid,
            "username": self.username,
            "usercard": self.usercard,
            "userrole": self.userrole,
            "conversation_id": self.conversation_id,
            "is_group": self.is_group,
            "event_type": self.event_type,
            "raw_data": self.raw_data,
        }
    
    async def from_dict(data: Dict[str, Any]) -> 'Messagebase':
        return Messagebase(
            adapter=data.get("adapter", ""),
            text=data.get("text", ""),
            image=data.get("image", []),
            file=data.get("file", []),
            video=data.get("video", []),
            audio=data.get("audio", []),
            at=data.get("at", []),
            reply_to=data.get("reply_to"),
            timestamp=data.get("timestamp"),
            messageid=data.get("messageid"),
            userid=data.get("userid"),
            username=data.get("username"),
            usercard=data.get("usercard"),
            userrole=data.get("userrole"),
            conversation_id=data.get("conversation_id"),
            is_group=data.get("is_group"),
            event_type=data.get("event_type"),
            raw_data=data.get("raw_data"),
        )

class TomatOS_conn(TypedDict):
    service: str # 服务名称(方便查找的标识, 如 Napcat_QQ, TomatOS_WebTerminal)
    conn_mode: str # 连接模式 (websocket/http)
    conn_type: str # 连接类型 (server/client)
    ws: Union[websockets.ClientConnection, websockets.ServerConnection]  # WebSocket连接对象
    http: Union[aiohttp.ClientRequest, aiohttp.ClientResponse]  # HTTP请求对象
    conn_host: str # 连接主机地址
    conn_port: int # 连接端口