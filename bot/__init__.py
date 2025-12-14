"""
TomatOS Bot 模块 - 整合版
提供原有接口兼容和新系统功能
"""

# ==================== 核心导出 ====================

# 导出新系统接口
from .ai_chat import AIChat, ChatMessage, create_ai_chat
from .model import ModelConfig, get_model
from .tools import ai_tool, gettools, Tools
from .memory_diary import memories
from .api import MODEL_CONFIGS, PROMPT_TEMPLATES, bot_name, bot_alliases
from .logger import logger

# ==================== 兼容性定义 ====================

def initialize_models():
    """初始化模型 - 兼容性函数"""
    model_instance = get_model()
    return model_instance

# 导出工具处理器（兼容原有接口）
class ToolHandler:
    """工具处理器 - 兼容原有接口"""
    def __init__(self):
        self.logger = logger
    
    async def handle_tool_call(self, tool_name: str, arguments: dict):
        self.logger.warning(f"ToolHandler.handle_tool_call: {tool_name} - 使用新系统工具")
        # 这里可以调用新系统的工具处理
        return {"success": False, "error": "工具处理暂未迁移"}

# 导出记忆系统（兼容原有接口）
class MemorySystem:
    """兼容原有MemorySystem接口"""
    def __init__(self):
        from .memory_diary import memories
        self.memory = memories()
        self.logger = logger
    
    async def add_memory(self, content: str, tags: list = None, importance: int = 0):
        """添加记忆 - 兼容接口"""
        return await self.memory.add_memory(content, tags or [], importance)
    
    async def search_memories(self, query: str, limit: int = 5):
        """搜索记忆 - 兼容接口"""
        return await self.memory.search_memories(query, limit)
    
    async def delete_memory(self, memory_id: int):
        """删除记忆 - 兼容接口"""
        return await self.memory.del_memory(memory_id)

# 简化类型定义
MemoryItem = dict  # 简化类型
MemoryType = str   # 简化类型

# ==================== 辅助函数 ====================

def get_bot_name() -> str:
    """获取机器人名称"""
    return bot_name

def get_prompt_template(template_name: str = "default") -> str:
    """获取提示词模板"""
    return PROMPT_TEMPLATES.get(template_name, "")

def list_available_models(model_type: str = "chat") -> list:
    """列出可用模型"""
    try:
        model_instance = get_model()
        return model_instance.list_models_by_type(model_type)
    except Exception:
        return []

# ==================== 导出列表 ====================

__all__ = [
    # 新系统接口
    "AIChat", "ChatMessage", "create_ai_chat",
    "ModelConfig", "get_model",
    "ai_tool", "gettools", "Tools",
    "memories",
    
    # 配置
    "MODEL_CONFIGS", "PROMPT_TEMPLATES",
    "bot_name", "bot_alliases",
    
    # 工具
    "logger",
    
    # 兼容函数
    "initialize_models",
    "ToolHandler",
    "MemorySystem", "MemoryItem", "MemoryType",
    
    # 辅助函数
    "get_bot_name", "get_prompt_template", "list_available_models"
]
