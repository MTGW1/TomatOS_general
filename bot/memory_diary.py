import asyncio
import datetime
import duckdb
import json
import os
import uuid
from typing import List, Dict, Any, Union, Optional
from dataclasses import dataclass

# 使用相对导入避免循环导入
try:
    from .logger import logger
except ImportError:
    from logger import logger

@dataclass
class memoryitem:
    # 元信息
    memory_id: str
    timestamp: str
    # 用户信息
    userID: str
    user_name: str
    user_aliases: List[str]
    # 聊天信息
    context_id: str
    user_role: str
    messageID: str
    # 消息内容
    CoT_str: str
    content: str
    keywords: List[str]
    embeddings: List[float]
    # 图片信息（包括表情图片）
    image_paths: List[str] = None
    # 图片类型：'image' 普通图片，'emoji' 表情图片
    image_types: List[str] = None

@dataclass
class memorytoolcall:
    name: str
    description: str
    parameters: Dict[str, Any]

@dataclass
class memorytoolresponse:
    success: bool
    message: str
    data: Dict[str, Any]

@dataclass
class favouriteemoji:
    path: str
    description: str
    keywords: List[str]



class memories:
    def __init__(self):
        self.db = duckdb.connect(database=':memory:')
        pass

    def init_memory_db(self):
        """初始化记忆数据库"""
        self.db.execute("""
        CREATE TABLE IF NOT EXISTS memories (
            memory_id TEXT PRIMARY KEY,
            timestamp TEXT,
            userID TEXT,
            user_name TEXT,
            user_aliases TEXT,
            context_id TEXT,
            user_role TEXT,
            messageID TEXT,
            CoT_str TEXT,
            content TEXT,
            keywords TEXT,
            embeddings BLOB,
            image_paths TEXT,
            image_types TEXT
        )
        """)
        
        # 创建图片/表情专用表
        self.db.execute("""
        CREATE TABLE IF NOT EXISTS image_memories (
            image_id TEXT PRIMARY KEY,
            memory_id TEXT,
            image_path TEXT,
            image_type TEXT,  -- 'image' 或 'emoji'
            description TEXT,
            keywords TEXT,
            timestamp TEXT,
            FOREIGN KEY (memory_id) REFERENCES memories(memory_id)
        )
        """)
        
        # 创建表情收藏表
        self.db.execute("""
        CREATE TABLE IF NOT EXISTS favourite_emojis (
            emoji_id TEXT PRIMARY KEY,
            path TEXT,
            description TEXT,
            keywords TEXT,
            usage_count INTEGER DEFAULT 0,
            last_used TEXT
        )
        """)
        
        logger.info("记忆数据库已初始化")

    def close(self):
        """关闭数据库连接"""
        self.db.close()
        logger.info("记忆数据库连接已关闭")

    # 记忆存储
    def add_memory(self, memory: memoryitem) -> bool:
        """添加记忆"""
        try:
            self.db.execute("""
            INSERT OR REPLACE INTO memories 
            (memory_id, timestamp, userID, user_name, user_aliases, context_id, 
             user_role, messageID, CoT_str, content, keywords, embeddings, 
             image_paths, image_types)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                memory.memory_id,
                memory.timestamp,
                memory.userID,
                memory.user_name,
                json.dumps(memory.user_aliases),
                memory.context_id,
                memory.user_role,
                memory.messageID,
                memory.CoT_str,
                memory.content,
                json.dumps(memory.keywords),
                json.dumps(memory.embeddings),
                json.dumps(memory.image_paths) if memory.image_paths else None,
                json.dumps(memory.image_types) if memory.image_types else None
            ))
            
            # 如果有图片/表情，也存储到专用表
            if memory.image_paths:
                for i, image_path in enumerate(memory.image_paths):
                    image_id = f"{memory.memory_id}_image_{i}"
                    # 确定图片类型
                    image_type = 'image'
                    if memory.image_types and i < len(memory.image_types):
                        image_type = memory.image_types[i]
                    
                    description = f"图片来自消息: {memory.content[:50]}..."
                    if image_type == 'emoji':
                        description = f"表情图片: {image_path}"
                    
                    self.db.execute("""
                    INSERT OR REPLACE INTO image_memories 
                    (image_id, memory_id, image_path, image_type, description, keywords, timestamp)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """, (
                        image_id,
                        memory.memory_id,
                        image_path,
                        image_type,
                        description,
                        json.dumps(memory.keywords),
                        memory.timestamp
                    ))
                    
                    # 如果是表情图片，更新表情收藏表
                    if image_type == 'emoji':
                        self._update_favourite_emoji(image_path, memory.keywords)
            
            return True
        except Exception as e:
            logger.error(f"添加记忆失败: {e}")
            return False
        
    def del_memory(self, memory_id: str) -> bool:
        """删除记忆"""
        try:
            # 先删除image_memories表中的记录（因为有外键约束）
            self.db.execute("""
            DELETE FROM image_memories WHERE memory_id = ?
            """, (memory_id,))
            
            # 再删除memories表中的记录
            self.db.execute("""
            DELETE FROM memories WHERE memory_id = ?
            """, (memory_id,))
            
            return True
        except Exception as e:
            logger.error(f"删除记忆失败: {e}")
            return False
        
    def clr_memory(self) -> bool:
        """清空所有记忆"""
        try:
            self.db.execute("DELETE FROM memories")
            self.db.execute("DELETE FROM image_memories")
            return True
        except Exception as e:
            logger.error(f"清空记忆失败: {e}")
            return False
    
    def _update_favourite_emoji(self, image_path: str, keywords: List[str]):
        """更新表情收藏表（表情作为图片文件）"""
        try:
            # 检查表情是否已存在
            result = self.db.execute("""
            SELECT emoji_id, usage_count FROM favourite_emojis WHERE path = ?
            """, (image_path,)).fetchone()
            
            current_time = datetime.datetime.now().isoformat()
            
            if result:
                # 更新现有表情
                emoji_id, usage_count = result
                self.db.execute("""
                UPDATE favourite_emojis 
                SET usage_count = ?, last_used = ?, keywords = ?
                WHERE emoji_id = ?
                """, (
                    usage_count + 1,
                    current_time,
                    json.dumps(keywords),
                    emoji_id
                ))
            else:
                # 插入新表情 - 使用更唯一的ID
                emoji_id = f"emoji_{uuid.uuid4().hex[:8]}"
                # 从文件路径提取描述
                filename = os.path.basename(image_path)
                description = f"表情图片: {filename}"
                
                self.db.execute("""
                INSERT INTO favourite_emojis 
                (emoji_id, path, description, keywords, usage_count, last_used)
                VALUES (?, ?, ?, ?, ?, ?)
                """, (
                    emoji_id,
                    image_path,
                    description,
                    json.dumps(keywords),
                    1,
                    current_time
                ))
        except Exception as e:
            logger.error(f"更新表情收藏表失败: {e}")

    # 记忆联想
    async def remind_research(self, query: str, limit: int = 5) -> List[memoryitem]:
        """根据查询进行记忆查找与联想"""
        try:
            # 简单的关键词匹配查询
            results = self.db.execute("""
            SELECT * FROM memories 
            WHERE content LIKE ? OR keywords LIKE ?
            ORDER BY timestamp DESC
            LIMIT ?
            """, (
                f"%{query}%",
                f"%{query}%",
                limit
            )).fetchall()
            
            memories_list = []
            for row in results:
                memory = memoryitem(
                    memory_id=row[0],
                    timestamp=row[1],
                    userID=row[2],
                    user_name=row[3],
                    user_aliases=json.loads(row[4]) if row[4] else [],
                    context_id=row[5],
                    user_role=row[6],
                    messageID=row[7],
                    CoT_str=row[8],
                    content=row[9],
                    keywords=json.loads(row[10]) if row[10] else [],
                    embeddings=json.loads(row[11]) if row[11] else [],
                    image_paths=json.loads(row[12]) if row[12] else None,
                    image_types=json.loads(row[13]) if row[13] else None
                )
                memories_list.append(memory)
            
            return memories_list
        except Exception as e:
            logger.error(f"记忆查询失败: {e}")
            return []
    
    async def remind_images(self, query: str, image_type: str = None, limit: int = 5) -> List[Dict[str, Any]]:
        """根据查询联想图片/表情"""
        try:
            sql = """
            SELECT im.*, m.content, m.keywords, m.timestamp, m.user_name 
            FROM image_memories im
            LEFT JOIN memories m ON im.memory_id = m.memory_id
            WHERE (im.description LIKE ? OR im.keywords LIKE ?)
            """
            params = [f"%{query}%", f"%{query}%"]
            
            if image_type:
                sql += " AND im.image_type = ?"
                params.append(image_type)
            
            sql += " ORDER BY im.timestamp DESC LIMIT ?"
            params.append(limit)
            
            results = self.db.execute(sql, params).fetchall()
            
            images_list = []
            for row in results:
                image_info = {
                    'image_id': row[0],
                    'memory_id': row[1],
                    'image_path': row[2],
                    'image_type': row[3],
                    'description': row[4],
                    'keywords': json.loads(row[5]) if row[5] else [],
                    'timestamp': row[6],
                    'related_content': row[7],
                    'related_keywords': json.loads(row[8]) if row[8] else [],
                    'message_timestamp': row[9],
                    'user_name': row[10]
                }
                images_list.append(image_info)
            
            return images_list
        except Exception as e:
            logger.error(f"图片联想查询失败: {e}")
            return []
    
    async def remind_emojis_by_keyword(self, keyword: str, limit: int = 10) -> List[Dict[str, Any]]:
        """根据关键词联想表情"""
        try:
            results = self.db.execute("""
            SELECT * FROM favourite_emojis 
            WHERE description LIKE ? OR keywords LIKE ?
            ORDER BY usage_count DESC, last_used DESC
            LIMIT ?
            """, (
                f"%{keyword}%",
                f"%{keyword}%",
                limit
            )).fetchall()
            
            emojis_list = []
            for row in results:
                emoji_info = {
                    'emoji_id': row[0],
                    'path': row[1],
                    'description': row[2],
                    'keywords': json.loads(row[3]) if row[3] else [],
                    'usage_count': row[4],
                    'last_used': row[5]
                }
                emojis_list.append(emoji_info)
            
            return emojis_list
        except Exception as e:
            logger.error(f"表情联想查询失败: {e}")
            return []
    
    async def get_popular_emojis(self, limit: int = 10) -> List[Dict[str, Any]]:
        """获取最常用的表情"""
        try:
            results = self.db.execute("""
            SELECT * FROM favourite_emojis 
            ORDER BY usage_count DESC, last_used DESC
            LIMIT ?
            """, (limit,)).fetchall()
            
            emojis_list = []
            for row in results:
                emoji_info = {
                    'emoji_id': row[0],
                    'path': row[1],
                    'description': row[2],
                    'keywords': json.loads(row[3]) if row[3] else [],
                    'usage_count': row[4],
                    'last_used': row[5]
                }
                emojis_list.append(emoji_info)
            
            return emojis_list
        except Exception as e:
            logger.error(f"获取常用表情失败: {e}")
            return []
    
    async def search_similar_images(self, image_path: str, limit: int = 5) -> List[Dict[str, Any]]:
        """查找相似的图片（基于文件名或路径关键词）"""
        try:
            # 从图片路径提取关键词
            filename = os.path.basename(image_path)
            name_without_ext = os.path.splitext(filename)[0]
            
            # 使用文件名作为关键词进行搜索
            results = self.db.execute("""
            SELECT im.*, m.content, m.keywords 
            FROM image_memories im
            LEFT JOIN memories m ON im.memory_id = m.memory_id
            WHERE im.description LIKE ? OR im.keywords LIKE ? OR m.keywords LIKE ?
            ORDER BY im.timestamp DESC
            LIMIT ?
            """, (
                f"%{name_without_ext}%",
                f"%{name_without_ext}%",
                f"%{name_without_ext}%",
                limit
            )).fetchall()
            
            images_list = []
            for row in results:
                image_info = {
                    'image_id': row[0],
                    'memory_id': row[1],
                    'image_path': row[2],
                    'image_type': row[3],
                    'description': row[4],
                    'keywords': json.loads(row[5]) if row[5] else [],
                    'timestamp': row[6],
                    'related_content': row[7],
                    'related_keywords': json.loads(row[8]) if row[8] else []
                }
                images_list.append(image_info)
            
            return images_list
        except Exception as e:
            logger.error(f"查找相似图片失败: {e}")
            return []
    
    # 工具方法
    def get_memory_tools(self) -> List[memorytoolcall]:
        """获取记忆相关的工具调用定义"""
        return [
            memorytoolcall(
                name="remind_research",
                description="根据查询进行记忆查找与联想",
                parameters={
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "查询关键词"},
                        "limit": {"type": "integer", "description": "返回结果数量", "default": 5}
                    },
                    "required": ["query"]
                }
            ),
            memorytoolcall(
                name="remind_images",
                description="根据查询联想图片或表情",
                parameters={
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "查询关键词"},
                        "image_type": {"type": "string", "description": "图片类型: 'image' 或 'emoji'", "enum": ["image", "emoji"]},
                        "limit": {"type": "integer", "description": "返回结果数量", "default": 5}
                    },
                    "required": ["query"]
                }
            ),
            memorytoolcall(
                name="remind_emojis_by_keyword",
                description="根据关键词联想表情",
                parameters={
                    "type": "object",
                    "properties": {
                        "keyword": {"type": "string", "description": "关键词"},
                        "limit": {"type": "integer", "description": "返回结果数量", "default": 10}
                    },
                    "required": ["keyword"]
                }
            ),
            memorytoolcall(
                name="get_popular_emojis",
                description="获取最常用的表情",
                parameters={
                    "type": "object",
                    "properties": {
                        "limit": {"type": "integer", "description": "返回结果数量", "default": 10}
                    }
                }
            )
        ]
    
    async def execute_tool(self, tool_name: str, **kwargs) -> memorytoolresponse:
        """执行工具调用"""
        try:
            if tool_name == "remind_research":
                query = kwargs.get("query", "")
                limit = kwargs.get("limit", 5)
                results = await self.remind_research(query, limit)
                return memorytoolresponse(
                    success=True,
                    message=f"找到 {len(results)} 条相关记忆",
                    data={"memories": [vars(m) for m in results]}
                )
            
            elif tool_name == "remind_images":
                query = kwargs.get("query", "")
                image_type = kwargs.get("image_type")
                limit = kwargs.get("limit", 5)
                results = await self.remind_images(query, image_type, limit)
                return memorytoolresponse(
                    success=True,
                    message=f"找到 {len(results)} 张相关图片",
                    data={"images": results}
                )
            
            elif tool_name == "remind_emojis_by_keyword":
                keyword = kwargs.get("keyword", "")
                limit = kwargs.get("limit", 10)
                results = await self.remind_emojis_by_keyword(keyword, limit)
                return memorytoolresponse(
                    success=True,
                    message=f"找到 {len(results)} 个相关表情",
                    data={"emojis": results}
                )
            
            elif tool_name == "get_popular_emojis":
                limit = kwargs.get("limit", 10)
                results = await self.get_popular_emojis(limit)
                return memorytoolresponse(
                    success=True,
                    message=f"获取到 {len(results)} 个常用表情",
                    data={"popular_emojis": results}
                )
            
            else:
                return memorytoolresponse(
                    success=False,
                    message=f"未知的工具: {tool_name}",
                    data={}
                )
                
        except Exception as e:
            logger.error(f"执行工具 {tool_name} 失败: {e}")
            return memorytoolresponse(
                success=False,
                message=f"执行工具失败: {str(e)}",
                data={}
            )

async def to_memory_item(data: Dict[str, Any]) -> memoryitem:
    """将字典数据转换为 memoryitem 实例"""
    return memoryitem(
        memory_id=data.get("memory_id", ""),
        timestamp=data.get("timestamp", ""),
        userID=data.get("userID", ""),
        user_name=data.get("user_name", ""),
        user_aliases=data.get("user_aliases", []),
        context_id=data.get("context_id", ""),
        user_role=data.get("user_role", ""),
        messageID=data.get("messageID", ""),
        CoT_str=data.get("CoT_str", ""),
        content=data.get("content", ""),
        keywords=data.get("keywords", []),
        embeddings=data.get("embeddings", []),
        image_paths=data.get("image_paths"),
        image_types=data.get("image_types")
    )    