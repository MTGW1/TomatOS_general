"""
改进的工具注册器系统
支持更好的装饰器使用方式和类型提示
"""

from functools import wraps
from typing import Dict, List, Any, Callable, Optional, Union
import inspect

# 使用相对导入避免循环导入
try:
    from .logger import logger
    from . import api
except ImportError:
    from logger import logger
    import api

import os
import sys
import importlib
import datetime
import json
import cloudscraper
import asyncio

# 导入记忆模块
try:
    from .memory_diary import memories
except ImportError:
    try:
        from memory_diary import memories
    except ImportError:
        logger.warning("无法导入 memory_diary 模块，记忆工具将不可用")
        memories = None


class Tools:
    """工具注册器类"""
    
    def __init__(self):
        self._tools: Dict[str, Dict[str, Any]] = {}
        self._tool_functions: Dict[str, Callable] = {}
        
    def tool(
        self,
        name: str,
        description: str,
        parameters: Dict[str, Dict[str, Any]],
        required: List[str] = None,
        quota: Dict[str, Any] = None
    ):
        """
        工具装饰器工厂
        
        Args:
            name: 工具名称
            description: 工具描述
            parameters: 参数定义，格式为 {参数名: {类型, 描述, ...}}
            required: 必需参数列表
            quota: 配额配置，如 {"api": "serp", "cost": 1, "limit_key": "rpmonth"}
            
        Returns:
            装饰器函数
        """
        def decorator(func: Callable):
            @wraps(func)
            async def wrapper(**kwargs):
                # 验证参数
                self._validate_parameters(name, parameters, required, kwargs)
                # 执行函数
                return await func(**kwargs)
            
            # 构建工具信息
            tool_info = {
                "type": "function",
                "function": {
                    "name": name,
                    "description": description,
                    "parameters": {
                        "type": "object",
                        "properties": parameters,
                        "required": required or []
                    }
                },
                "quota": quota
            }
            
            # 注册工具
            self._tools[name] = tool_info
            self._tool_functions[name] = wrapper
            
            # 为函数添加工具信息属性
            wrapper.tool_info = tool_info
            wrapper.tool_name = name
            
            return wrapper
        
        return decorator
    
    def _validate_parameters(
        self,
        tool_name: str,
        parameters: Dict[str, Dict[str, Any]],
        required: List[str],
        kwargs: Dict[str, Any]
    ):
        """验证参数"""
        if required:
            for param in required:
                if param not in kwargs:
                    raise ValueError(f"工具 '{tool_name}' 缺少必需参数: {param}")
        
        # 检查未知参数
        for param in kwargs:
            if param not in parameters:
                logger.warning(f"工具 '{tool_name}' 接收到未知参数: {param}")
    
    async def get_tools(self) -> List[Dict[str, Any]]:
        """获取所有工具信息"""
        return list(self._tools.values())

    def get_tools_sync(self) -> List[Dict[str, Any]]:
        """获取所有工具信息（同步）"""
        return list(self._tools.values())
    
    async def execute_tool(self, name: str, **kwargs) -> Any:
        """执行指定工具"""
        if name not in self._tool_functions:
            logger.error(f"工具未找到: {name}")
            raise ValueError(f"工具 '{name}' 未注册")
        
        # 检查配额
        tool_info = self._tools.get(name)
        quota_info = None
        if tool_info and tool_info.get("quota"):
            try:
                quota_info = tool_info["quota"]
                api_name = quota_info.get("api")
                usage_key = quota_info.get("usage_key", "usage")
                limit_key = quota_info.get("limit_key")
                cost = quota_info.get("cost", 1)
                
                if api_name and limit_key:
                    if not api.check_quota(api_name, usage_key, limit_key, cost):
                        error_msg = f"工具 '{name}' 配额不足 (API: {api_name})"
                        logger.warning(error_msg)
                        return {"error": error_msg}
            except ImportError:
                logger.warning("无法导入 api 模块，跳过配额检查")
            except Exception as e:
                logger.error(f"配额检查失败: {e}")

        func = self._tool_functions[name]
        try:
            result = await func(**kwargs)
            
            # 更新配额
            if quota_info:
                try:
                    api_name = quota_info.get("api")
                    usage_key = quota_info.get("usage_key", "usage")
                    cost = quota_info.get("cost", 1)
                    
                    if api_name:
                        api.usage_update(api_name, usage_key, cost)
                except Exception as e:
                    logger.error(f"更新配额失败: {e}")
            
            logger.info(f"工具 '{name}' 执行成功")
            return result
        except Exception as e:
            logger.error(f"工具 '{name}' 执行失败: {e}")
            raise
    
    def get_tool_function(self, name: str) -> Optional[Callable]:
        """获取工具函数"""
        return self._tool_functions.get(name)
    
    def list_tools(self) -> List[str]:
        """列出所有工具名称"""
        return list(self._tools.keys())
    
    def clear_tools(self):
        """清除所有工具"""
        self._tools.clear()
        self._tool_functions.clear()
    
    def load_plugins(self):
        """加载插件目录中的工具"""
        
        # 插件目录路径
        plugins_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "plugins")
        if not os.path.exists(plugins_dir):
            logger.warning(f"插件目录不存在: {plugins_dir}")
            return
        
        # 添加插件目录到 Python 路径
        if plugins_dir not in sys.path:
            sys.path.insert(0, plugins_dir)
        
        # 遍历插件文件
        for filename in os.listdir(plugins_dir):
            # 跳过测试文件
            if filename in ["final_test.py"]:
                continue
                
            if filename.endswith(".py") and not filename.startswith("__"):
                module_name = filename[:-3]
                try:
                    # 导入插件模块
                    module = importlib.import_module(module_name)
                    logger.info(f"已加载插件模块: {module_name}")
                    
                    # 检查模块中是否有使用 @ai_tool 装饰的函数
                    for attr_name in dir(module):
                        attr = getattr(module, attr_name)
                        if callable(attr) and hasattr(attr, "tool_info"):
                            # 这个函数已经被 @ai_tool 装饰过，自动注册
                            tool_info = attr.tool_info
                            tool_name = attr.tool_name
                            
                            # 检查是否已存在同名工具
                            if tool_name not in self._tools:
                                self._tools[tool_name] = tool_info
                                self._tool_functions[tool_name] = attr
                                logger.info(f"已注册插件工具: {tool_name}")
                except Exception as e:
                    logger.error(f"加载插件模块 {module_name} 失败: {e}")


# 创建全局工具注册器实例
tools = Tools()


def gettools() -> Tools:
    """获取全局工具注册器实例"""
    # 确保插件已加载
    if not hasattr(tools, "_plugins_loaded"):
        tools.load_plugins()
        tools._plugins_loaded = True
    return tools


# 便捷装饰器函数
def ai_tool(
    name: str,
    description: str,
    parameters: Dict[str, Dict[str, Any]],
    required: List[str] = None,
    quota: Dict[str, Any] = None
):
    """
    便捷装饰器，用于注册AI工具
    
    使用示例:
    @ai_tool(
        name="search_web",
        description="搜索网页信息",
        parameters={
            "query": {"type": "string", "description": "搜索关键词"},
            "limit": {"type": "integer", "description": "结果数量", "default": 5}
        },
        required=["query"],
        quota={"api": "serp", "cost": 1, "limit_key": "rpmonth"}
    )
    async def search_web(query: str, limit: int = 5):
        # 工具实现
        pass
    """
    return tools.tool(name, description, parameters, required, quota)


# ==================== 基本工具注册 ====================

# 天气工具
# @ai_tool(
#     name="get_weather",
#     description="获取天气信息",
#     parameters={
#         "city": {"type": "string", "description": "城市名称"},
#         "days": {"type": "integer", "description": "预报天数", "default": 1}
#     },
#     required=["city"]
# )
# async def get_weather(city: str, days: int = 1):
#     """获取天气信息的工具实现"""
#     return {
#         "city": city,
#         "days": days,
#         "forecast": f"{city}未来{days}天天气晴朗"
#     }

# 计算工具
# @ai_tool(
#     name="calculate",
#     description="执行数学计算",
#     parameters={
#         "expression": {"type": "string", "description": "数学表达式"},
#         "precision": {"type": "integer", "description": "精度", "default": 2}
#     },
#     required=["expression"]
# )
# async def calculate(expression: str, precision: int = 2):
#     """计算工具实现 - 使用安全的数学表达式解析"""
#     try:
#         # 移除所有空格
#         expr = expression.replace(" ", "")
        
#         # 替换常见的数学符号
#         expr = expr.replace("×", "*").replace("÷", "/").replace("x", "*").replace("X", "*")
        
#         # 安全检查：只允许数字、小数点、基本运算符和括号
#         allowed_chars = set("0123456789.+-*/()")
#         if not all(c in allowed_chars for c in expr):
#             return {"error": f"表达式包含不安全字符: {expr}"}
        
#         # 检查括号匹配
#         stack = []
#         for c in expr:
#             if c == "(":
#                 stack.append(c)
#             elif c == ")":
#                 if not stack:
#                     return {"error": "括号不匹配"}
#                 stack.pop()
#         if stack:
#             return {"error": "括号不匹配"}
        
#         # 使用安全的eval（限制在数学表达式范围内）
#         # 注意：在生产环境中应该使用更安全的数学表达式解析库
#         result = eval(expr, {"__builtins__": {}}, {})
        
#         return {
#             "expression": expression,
#             "result": round(result, precision),
#             "precision": precision,
#             "answer": f"{expression} = {round(result, precision)}",
#             "explanation": f"计算结果: {expression} = {round(result, precision)} (精度: {precision}位小数)"
#         }
#     except Exception as e:
#         return {"error": str(e)}

# 时间工具
@ai_tool(
    name="get_current_time",
    description="获取当前时间",
    parameters={
        "timezone": {"type": "string", "description": "时区，如'Asia/Shanghai'、'UTC'", "default": "Asia/Shanghai"}
    }
)
async def get_current_time(timezone: str = "Asia/Shanghai"):
    """获取当前时间的工具实现"""
    now = datetime.datetime.now()
    return {
        "timezone": timezone,
        "current_time": now.strftime("%Y-%m-%d %H:%M:%S"),
        "timestamp": int(now.timestamp())
    }

@ai_tool(
    name="webdownloader",
    description="下载网页内容",
    parameters={
        "url": {"type": "string", "description": "网页URL地址"}
    },
    required=["url"]
)
async def web_downloader(url: str) -> str:
    """网页下载工具实现 - 最终版，正确处理Cloudflare和JSON响应"""
    
    try:
        # 使用cloudscraper绕过Cloudflare保护
        scraper = cloudscraper.create_scraper(
            browser={
                'browser': 'chrome',
                'platform': 'windows',
                'mobile': False
            }
        )
        
        # 设置请求头
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'application/json, text/html, application/xhtml+xml, application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
        }
        
        # 获取响应
        response = scraper.get(url, headers=headers, timeout=30)
        
        if response.status_code == 200:
            # 检查Content-Type
            content_type = response.headers.get('Content-Type', '').lower()
            
            # 首先尝试直接获取文本（cloudscraper应该自动处理gzip）
            text_content = response.text
            
            if 'application/json' in content_type:
                # 如果是JSON，尝试解析
                try:
                    json_data = response.json()
                    return json.dumps(json_data, ensure_ascii=False, indent=2)
                except json.JSONDecodeError:
                    # 如果无法解析为JSON，但确实是JSON Content-Type
                    # 尝试手动处理可能的编码问题
                    try:
                        # 尝试使用不同的编码
                        for encoding in ['utf-8', 'gbk', 'gb2312', 'latin-1']:
                            try:
                                decoded = response.content.decode(encoding)
                                json_data = json.loads(decoded)
                                return json.dumps(json_data, ensure_ascii=False, indent=2)
                            except:
                                continue
                        return text_content
                    except:
                        return text_content
            else:
                return text_content
        else:
            logger.warning(f"请求失败，状态码: {response.status_code}")
            return f"无法访问网页，HTTP状态码: {response.status_code}"
            
    except Exception as e:
        logger.exception(f"网页下载异常: {e}")
        return f"无法下载网页内容: {e}"

# ==================== 记忆工具注册 ====================


# 创建全局记忆实例
_memory_instance = None

def get_memory_instance():
    """获取全局记忆实例"""
    global _memory_instance
    if _memory_instance is None and memories is not None:
        _memory_instance = memories()
        _memory_instance.init_memory_db()
    return _memory_instance

# 注册记忆工具
if memories is not None:
    # 记忆查询工具
    @ai_tool(
        name="remind_research",
        description="根据查询进行记忆查找与联想",
        parameters={
            "query": {"type": "string", "description": "查询关键词"},
            "limit": {"type": "integer", "description": "返回结果数量", "default": 5}
        },
        required=["query"]
    )
    async def remind_research_tool(query: str, limit: int = 5):
        """记忆查询工具实现"""
        memory_instance = get_memory_instance()
        if memory_instance:
            results = await memory_instance.remind_research(query, limit)
            return {
                "success": True,
                "message": f"找到 {len(results)} 条相关记忆",
                "data": {"memories": [vars(m) for m in results]}
            }
        else:
            return {
                "success": False,
                "message": "记忆系统未初始化",
                "data": {}
            }
    
    # 图片联想工具
    @ai_tool(
        name="remind_images",
        description="根据查询联想图片或表情",
        parameters={
            "query": {"type": "string", "description": "查询关键词"},
            "image_type": {"type": "string", "description": "图片类型: 'image' 或 'emoji'", "enum": ["image", "emoji"]},
            "limit": {"type": "integer", "description": "返回结果数量", "default": 5}
        },
        required=["query"]
    )
    async def remind_images_tool(query: str, image_type: str = None, limit: int = 5):
        """图片联想工具实现"""
        memory_instance = get_memory_instance()
        if memory_instance:
            results = await memory_instance.remind_images(query, image_type, limit)
            return {
                "success": True,
                "message": f"找到 {len(results)} 张相关图片",
                "data": {"images": results}
            }
        else:
            return {
                "success": False,
                "message": "记忆系统未初始化",
                "data": {}
            }
    
    # 表情联想工具
    @ai_tool(
        name="remind_emojis_by_keyword",
        description="根据关键词联想表情",
        parameters={
            "keyword": {"type": "string", "description": "关键词"},
            "limit": {"type": "integer", "description": "返回结果数量", "default": 10}
        },
        required=["keyword"]
    )
    async def remind_emojis_by_keyword_tool(keyword: str, limit: int = 10):
        """表情联想工具实现"""
        memory_instance = get_memory_instance()
        if memory_instance:
            results = await memory_instance.remind_emojis_by_keyword(keyword, limit)
            return {
                "success": True,
                "message": f"找到 {len(results)} 个相关表情",
                "data": {"emojis": results}
            }
        else:
            return {
                "success": False,
                "message": "记忆系统未初始化",
                "data": {}
            }
    
    # 常用表情获取工具
    @ai_tool(
        name="get_popular_emojis",
        description="获取最常用的表情",
        parameters={
            "limit": {"type": "integer", "description": "返回结果数量", "default": 10}
        }
    )
    async def get_popular_emojis_tool(limit: int = 10):
        """常用表情获取工具实现"""
        memory_instance = get_memory_instance()
        if memory_instance:
            results = await memory_instance.get_popular_emojis(limit)
            return {
                "success": True,
                "message": f"获取到 {len(results)} 个常用表情",
                "data": {"popular_emojis": results}
            }
        else:
            return {
                "success": False,
                "message": "记忆系统未初始化",
                "data": {}
            }
    
    # 相似图片搜索工具
    @ai_tool(
        name="search_similar_images",
        description="查找相似的图片（基于文件名或路径关键词）",
        parameters={
            "image_path": {"type": "string", "description": "图片文件路径"},
            "limit": {"type": "integer", "description": "返回结果数量", "default": 5}
        },
        required=["image_path"]
    )
    async def search_similar_images_tool(image_path: str, limit: int = 5):
        """相似图片搜索工具实现"""
        memory_instance = get_memory_instance()
        if memory_instance:
            results = await memory_instance.search_similar_images(image_path, limit)
            return {
                "success": True,
                "message": f"找到 {len(results)} 张相似图片",
                "data": {"similar_images": results}
            }
        else:
            return {
                "success": False,
                "message": "记忆系统未初始化",
                "data": {}
            }
    
    logger.info("记忆工具已注册到全局工具系统")
else:
    logger.warning("记忆模块不可用，记忆工具未注册")

def test_webdownload():

    urls = [
        "https://backend.wplace.live/s0/pixel/0/0?x=0&y=0", # cloudflare 保护页面
        "https://www.python.org", # 普通页面
    ]
    async def test():
        for url in urls:
            content = await web_downloader(url=url)  # 使用关键字参数
            print(f"URL: {url}\n内容长度: {len(content)}\n")
    asyncio.run(test())

# 注意：主测试代码已经在文件前面的 if __name__ == "__main__": 部分定义
# 如果要运行网页下载测试，可以取消下面的注释：
if __name__ == "__main__":
    try:
        test_webdownload()
    except Exception as e:
        logger.exception(f"测试网页下载失败: {e}")