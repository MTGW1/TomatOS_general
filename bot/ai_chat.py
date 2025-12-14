"""
统一的AI聊天系统
基于OpenAI库，支持工具调用和动态prompt拼接
"""

import asyncio
import json
import traceback
from typing import Dict, List, Any, Optional, Union, AsyncGenerator
from dataclasses import dataclass, field
from datetime import datetime
import openai
from openai import AsyncOpenAI
import re

# 使用相对导入
try:
    from .logger import logger
    from . import api
    from .api import ModelConfig
    from .tools import gettools
    from .model import get_prompt_manager
except ImportError:
    # 如果相对导入失败，尝试绝对导入
    import sys
    import os
    # 将当前目录添加到 sys.path
    sys.path.append(os.path.dirname(os.path.abspath(__file__)))
    import api
    from api import ModelConfig
    from tools import gettools
    from model import get_prompt_manager
    from logger import logger

@dataclass
class ChatMessage:
    """聊天消息类"""
    role: str  # "system", "user", "assistant", "tool"
    content: str
    name: Optional[str] = None
    tool_calls: Optional[List[Dict[str, Any]]] = None
    tool_call_id: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为API请求格式"""
        result = {"role": self.role, "content": self.content}
        if self.name:
            result["name"] = self.name
        if self.tool_calls:
            result["tool_calls"] = self.tool_calls
        if self.tool_call_id:
            result["tool_call_id"] = self.tool_call_id
        return result





@dataclass
class ChatSession:
    """聊天会话类"""
    session_id: str
    messages: List[ChatMessage] = field(default_factory=list)
    model_config: Optional[ModelConfig] = None
    tools: Optional[List[Dict[str, Any]]] = None
    max_history: int = 100
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    
    def add_message(self, message: ChatMessage):
        """添加消息到会话"""
        self.messages.append(message)
        logger.debug(f"会话 {self.session_id} 添加消息: {message.role} - {message.content[:30]}...")
        self.updated_at = datetime.now()
        
        # 限制历史消息数量
        if len(self.messages) > self.max_history:
            # 保留系统消息和最近的对话
            system_messages = [msg for msg in self.messages if msg.role == "system"]
            recent_messages = self.messages[-self.max_history + len(system_messages):]
            self.messages = system_messages + recent_messages
    
    def get_messages_dict(self) -> List[Dict[str, Any]]:
        """获取消息列表的字典格式"""
        return [msg.to_dict() for msg in self.messages]
    
    def clear_history(self):
        """清空对话历史（保留系统消息）"""
        system_messages = [msg for msg in self.messages if msg.role == "system"]
        self.messages = system_messages
        self.updated_at = datetime.now()



class AIChat:
    """统一的AI聊天主类"""
    
    def __init__(self, model_name: Optional[str] = None, tools_enabled: bool = True):
        """
        初始化AI聊天
        
        Args:
            model_name: 模型名称，如果为None则使用deepseek-chat
            tools_enabled: 是否启用工具调用
        """
        self.logger = logger
        
        # 设置模型配置
        if model_name:
            self.model_config = self._get_model_config(model_name)
            if not self.model_config:
                self.logger.warning(f"模型 '{model_name}' 未找到，使用默认模型")
                self.model_config = self._get_default_model()
        else:
            self.model_config = self._get_default_model()
        
        if not self.model_config:
            raise ValueError("未找到可用的聊天模型配置")
        
        # 创建OpenAI客户端
        self.openai_client = AsyncOpenAI(
            api_key=self.model_config.api_key,
            base_url=self.model_config.base_url,
            timeout=60
        )
        
        # 会话管理
        self.sessions: Dict[str, ChatSession] = {}
        
        # 工具调用相关
        self.tools_enabled = tools_enabled
        self.tools_manager = gettools() if tools_enabled else None
        self.max_tool_iterations = 50  # 最大工具调用迭代次数
        
        # 提示词管理器
        self.prompt_manager = get_prompt_manager()
        
        self.logger.info(f"AI聊天系统初始化完成，使用模型: {self.model_config.model_name}")

    async def extract_thinking_content(self, content: str) -> Dict[str, str]:
        """从消息内容中提取思考模式和思考内容"""
        
        now_model = self.model_config.model_name
        thinking_token = api.MODEL_CONFIGS.get(now_model, {}).get("thinking_token", r"<think>(.*?)</think>") # 如果你不用openai库可以自行修改提取思考模式的正则表达式
        pattern = re.compile(thinking_token, re.DOTALL)
        match = pattern.search(content)
        if match:
            thinking_content = match.group(1).strip()
            return {"thinking": thinking_content}
        else:
            return {"thinking": ""}
        


    def _get_model_config(self, model_name: str) -> Optional[ModelConfig]:
        """从api.py配置中获取模型配置"""
        try:
            model_configs = api.MODEL_CONFIGS
            if model_name not in model_configs:
                return None
            
            config = model_configs[model_name]
            return ModelConfig(
                model_name=config.get("model_name", model_name),
                provider=config.get("provider", "unknown"),
                api_key=config.get("api_key", ""),
                base_url=config.get("base_url", ""),
                temperature=config.get("temperature", 0.7),
                max_tokens=config.get("max_tokens", 2048),
                tool_usable=config.get("tool_usable", True)
            )
        except Exception as e:
            self.logger.error(f"获取模型配置失败: {e}")
            return None
    
    def _get_default_model(self) -> Optional[ModelConfig]:
        """获取默认模型配置"""
        try:
            # 优先使用deepseek-chat
            return self._get_model_config(api.DEFAULT_MODELS.get("chat", "deepseek-chat"))
        except:
            # 如果失败，尝试获取第一个可用的模型
            try:
                model_configs = api.MODEL_CONFIGS
                for model_name, config in model_configs.items():
                    if "chat" in config.get("model_type", []):
                        return self._get_model_config(model_name)
            except:
                pass
        return None
    
    def create_session(
        self, 
        session_id: str, 
        system_prompt: str = "",
        prompt_type: str = "default",
        include_tools: bool = True,
        is_group_chat: bool = False,
        **kwargs
    ) -> ChatSession:
        """
        创建新的聊天会话
        
        Args:
            session_id: 会话ID
            system_prompt: 自定义系统提示词（如果为空则使用默认）
            prompt_type: 提示词类型，如 "default", "io", "tool_calling"
            include_tools: 是否包含工具调用
            is_group_chat: 是否是群聊
            **kwargs: 额外参数
            
        Returns:
            创建的会话对象
        """
        if session_id in self.sessions:
            self.logger.warning(f"会话 '{session_id}' 已存在，将重新创建")
        
        session = ChatSession(session_id=session_id)
        
        # 添加系统消息
        if not system_prompt:
            # 使用 PromptManager 构建系统提示词
            tools = []
            if include_tools and self.tools_enabled and self.tools_manager:
                tools = self._get_available_tools()
            
            system_prompt = self.prompt_manager.build_system_prompt(
                base_prompt_type=prompt_type,
                include_io_format=False,  # 根据需求调整
                include_tools=include_tools and len(tools) > 0,
                tools=tools,
                is_group_chat=is_group_chat,
                **kwargs
            )
        
        system_message = ChatMessage(role="system", content=system_prompt)
        session.add_message(system_message)
        
        # 设置模型配置
        session.model_config = self.model_config
        
        # 设置可用工具
        if self.tools_enabled and self.tools_manager:
            session.tools = self._get_available_tools()
        
        self.sessions[session_id] = session
        self.logger.info(f"创建新会话: {session_id}")
        
        return session
    
    def get_session(self, session_id: str) -> Optional[ChatSession]:
        """获取会话"""
        return self.sessions.get(session_id)
    
    def delete_session(self, session_id: str):
        """删除会话"""
        if session_id in self.sessions:
            del self.sessions[session_id]
            self.logger.info(f"删除会话: {session_id}")
    
    def _get_available_tools(self) -> List[Dict[str, Any]]:
        """获取可用工具列表"""
        if not self.tools_manager:
            return []
        
        # 注意：这里需要异步调用，但在同步上下文中我们返回空列表
        # 实际使用时会在异步方法中调用
        return []
    
    async def _get_available_tools_async(self) -> List[Dict[str, Any]]:
        """异步获取可用工具列表"""
        if not self.tools_manager:
            return []
        
        try:
            tools = await self.tools_manager.get_tools()
            return tools
        except Exception as e:
            self.logger.error(f"获取工具列表失败: {e}")
            return []
    
    async def chat(
        self,
        session_id: str,
        user_message: str,
        stream: bool = False,
        **kwargs
    ) -> Union[Dict[str, Any], AsyncGenerator[str, None]]:
        """
        主聊天方法
        
        Args:
            session_id: 会话ID
            user_message: 用户消息
            stream: 是否使用流式响应
            **kwargs: 额外的模型参数
            
        Returns:
            如果stream=False: 返回完整的响应字典
            如果stream=True: 返回异步生成器
        """
        # 获取或创建会话
        session = self.get_session(session_id)
        if not session:
            session = self.create_session(session_id)
        
        # 添加用户消息
        user_msg = ChatMessage(role="user", content=user_message)
        session.add_message(user_msg)
        
        # 准备工具调用
        tools = []
        if self.tools_enabled and self.tools_manager:
            tools = await self._get_available_tools_async()
        
        # 调用模型
        if stream:
            return self._chat_stream(session, tools, **kwargs)
        else:
            return await self._chat_complete(session, tools, **kwargs)
    
    async def _chat_complete(
        self,
        session: ChatSession,
        tools: List[Dict[str, Any]],
        **kwargs
    ) -> Dict[str, Any]:
        """完整的聊天响应（非流式）"""
        try:
            # 获取会话消息
            messages = session.get_messages_dict()
            
            # 如果有可用工具，使用 PromptManager 构建系统提示词
            if tools and session.model_config.tool_usable:
                # 使用 PromptManager 构建动态提示词
                conversation_history = []
                for msg in messages:
                    if msg.get("role") in ["user", "assistant", "tool"]:
                        # 保留完整的消息信息，包括 tool_call_id
                        history_msg = {
                            "role": msg["role"],
                            "content": msg.get("content", "")
                        }
                        # 如果是工具消息，添加 tool_call_id
                        if msg.get("role") == "tool" and msg.get("tool_call_id"):
                            history_msg["tool_call_id"] = msg["tool_call_id"]
                        # 如果是助手消息且有工具调用，添加 tool_calls
                        if msg.get("role") == "assistant" and msg.get("tool_calls"):
                            history_msg["tool_calls"] = msg["tool_calls"]
                        conversation_history.append(history_msg)
                
                # 获取最后一条用户消息（如果有）
                user_message = ""
                for msg in reversed(messages):
                    if msg.get("role") == "user":
                        user_message = msg.get("content", "")
                        break
                
                # 创建动态提示词
                dynamic_prompt = self.prompt_manager.create_dynamic_prompt(
                    user_message=user_message,
                    conversation_history=conversation_history,
                    available_tools=tools,
                    is_group_chat=kwargs.get("is_group_chat", False)
                )
                
                # 替换消息列表
                messages = dynamic_prompt["messages"]
            
            # 准备模型参数
            model_params = {
                "messages": messages,
                "model_name": session.model_config.model_name,
                "temperature": kwargs.get("temperature", session.model_config.temperature),
                "max_tokens": kwargs.get("max_tokens", session.model_config.max_tokens),
            }
            
            # 添加工具调用参数
            if tools and session.model_config.tool_usable:
                model_params["tools"] = tools
                model_params["tool_choice"] = kwargs.get("tool_choice", "auto")
            
            # 调用OpenAI API
            response = await self._call_openai_api(messages, tools, **{
                k: v for k, v in model_params.items() 
                if k not in ["messages", "model_name", "tools"]
            })
            
            # 处理工具调用
            if response.get("tool_calls"):
                final_response = await self._handle_tool_calls(
                    session, response, tools, **kwargs
                )
                return final_response
            
            # 如果没有工具调用，处理普通响应
            content = response.get("content", "")
            
            # 添加助手消息到会话
            assistant_msg = ChatMessage(
                role="assistant",
                content=content
            )
            session.add_message(assistant_msg)
            
            return {
                "success": True,
                "session_id": session.session_id,
                "response": content,
                "final_response": content,  # 添加最终回复字段
                "model": session.model_config.model_name,
                "usage": response.get("usage", {}),
                "tool_calls": response.get("tool_calls", []),
            }
            
        except Exception as e:
            self.logger.error(f"聊天失败: {e}")
            return {
                "success": False,
                "session_id": session.session_id,
                "error": str(e),
                "response": "抱歉，聊天过程中出现了错误。",
                "final_response": "抱歉，聊天过程中出现了错误。"
            }
    
    async def _call_openai_api(
        self,
        messages: List[Dict[str, Any]],
        tools: List[Dict[str, Any]],
        **kwargs
    ) -> Dict[str, Any]:
        """调用OpenAI API"""
        try:
            # 调试：显示消息内容
            self.logger.debug(f"发送给API的消息数量: {len(messages)}")
            for i, msg in enumerate(messages):
                self.logger.debug(f"消息[{i}]: role={msg.get('role')}, content长度={len(str(msg.get('content', '')))}, tool_call_id={msg.get('tool_call_id', '无')}")
            
            # 准备参数
            params = {
                "model": self.model_config.model_name,
                "messages": messages,
                "temperature": kwargs.get("temperature", self.model_config.temperature),
                "max_tokens": kwargs.get("max_tokens", self.model_config.max_tokens),
            }
            
            # 添加工具调用参数
            if tools and self.model_config.tool_usable:
                params["tools"] = tools
                params["tool_choice"] = kwargs.get("tool_choice", "auto")
            
            # 调用OpenAI API
            response = await self.openai_client.chat.completions.create(**params)
            
            # 解析响应
            choice = response.choices[0]
            message = choice.message
            
            result = {
                "content": message.content or "",
                "role": message.role,
                "finish_reason": choice.finish_reason,
            }
            
            # 处理工具调用
            if message.tool_calls:
                tool_calls = []
                for tool_call in message.tool_calls:
                    tool_calls.append({
                        "id": tool_call.id,
                        "type": tool_call.type,
                        "function": {
                            "name": tool_call.function.name,
                            "arguments": tool_call.function.arguments,
                        }
                    })
                result["tool_calls"] = tool_calls
            
            # 添加使用情况
            if response.usage:
                result["usage"] = {
                    "prompt_tokens": response.usage.prompt_tokens,
                    "completion_tokens": response.usage.completion_tokens,
                    "total_tokens": response.usage.total_tokens,
                }
            
            return result
            
        except openai.APIError as e:
            self.logger.exception(f"OpenAI API错误: {e}")
        except openai.APIConnectionError as e:
            self.logger.exception(f"OpenAI连接错误: {e}")
        except openai.RateLimitError as e:
            self.logger.exception(f"OpenAI速率限制: {e}")
        except Exception as e:
            self.logger.exception(f"OpenAI调用未知错误: {e}")
    
    async def _execute_tool(self, tool_name: str, args: Dict[str, Any]) -> Dict[str, Any]:
        """执行工具（使用tools.py中的工具管理器）"""
        try:
            if not self.tools_manager:
                return {"error": "工具管理器未初始化"}
            
            # 使用tools_manager执行工具
            result = await self.tools_manager.execute_tool(tool_name, **args)
            return result
            
        except Exception as e:
            self.logger.error(f"工具 '{tool_name}' 执行失败: {e}")
            return {"error": str(e)}
    
    async def _handle_tool_calls(
        self,
        session: ChatSession,
        response: Dict[str, Any],
        tools: List[Dict[str, Any]],
        **kwargs
    ) -> Dict[str, Any]:
        """处理工具调用"""
        tool_calls = response.get("tool_calls", [])
        if not tool_calls:
            return response
        
        self.logger.info(f"检测到工具调用: {len(tool_calls)} 个")
        
        # 添加助手消息（包含工具调用）
        assistant_msg = ChatMessage(
            role="assistant",
            content=response.get("content", ""),
            tool_calls=tool_calls
        )
        session.add_message(assistant_msg)
        
        # 执行工具调用
        tool_results = []
        for tool_call in tool_calls:
            tool_name = tool_call.get("function", {}).get("name")
            tool_args = tool_call.get("function", {}).get("arguments", "{}")
            tool_call_id = tool_call.get("id")
            
            try:
                # 解析参数
                args_dict = json.loads(tool_args)
                
                # 执行工具
                result = await self._execute_tool(tool_name, args_dict)
                tool_results.append({
                    "tool_call_id": tool_call_id,
                    "role": "tool",
                    "name": tool_name,
                    "content": json.dumps(result, ensure_ascii=False)
                })
                
                self.logger.info(f"工具 '{tool_name}' 执行成功")
                
            except Exception as e:
                self.logger.exception(f"工具 '{tool_name}' 执行失败: {e}")
                tool_results.append({
                    "tool_call_id": tool_call_id,
                    "role": "tool",
                    "name": tool_name,
                    "content": json.dumps({"error": str(e)}, ensure_ascii=False)
                })
        
        # 添加工具结果消息
        for tool_result in tool_results:
            tool_msg = ChatMessage(
                role=tool_result["role"],
                content=tool_result["content"],
                name=tool_result["name"],
                tool_call_id=tool_result["tool_call_id"]
            )
            session.add_message(tool_msg)
        
        # 递归调用模型处理工具结果
        iteration = kwargs.get("tool_iteration", 0)
        if iteration >= self.max_tool_iterations:
            self.logger.warning(f"达到最大工具调用迭代次数: {self.max_tool_iterations}")
            return {
                "success": True,
                "session_id": session.session_id,
                "response": "已达到最大工具调用次数，请简化您的问题。",
                "final_response": "已达到最大工具调用次数，请简化您的问题。",
                "model": session.model_config.model_name,
                "tool_calls": tool_calls,
                "tool_results": tool_results,
            }
        
        # 再次调用模型获取最终回复
        # 从kwargs中移除tool_iteration，避免重复传递
        filtered_kwargs = {k: v for k, v in kwargs.items() if k != "tool_iteration"}
        final_response = await self._chat_complete(
            session, tools, tool_iteration=iteration + 1, **filtered_kwargs
        )
        
        # 添加最终回复字段
        if "response" in final_response:
            final_response["final_response"] = final_response["response"]
        
        return final_response
    
    async def _chat_stream( #=============================================================================================================== 这里待完善
        self,
        session: ChatSession,
        tools: List[Dict[str, Any]],
        **kwargs
    ) -> AsyncGenerator[str, None]:
        """流式聊天响应"""
        # 注意：这里需要根据具体的模型API实现流式响应
        # 由于不同提供商的流式API不同，这里提供一个框架
        
        try:
            # 准备模型参数
            model_params = {
                "messages": session.get_messages_dict(),
                "model_name": session.model_config.model_name,
                "temperature": kwargs.get("temperature", session.model_config.temperature),
                "max_tokens": kwargs.get("max_tokens", session.model_config.max_tokens),
                "stream": True,
            }
            
            # 添加工具调用参数
            if tools and session.model_config.tool_usable:
                model_params["tools"] = tools
                model_params["tool_choice"] = kwargs.get("tool_choice", "auto")
            
            # 这里应该调用模型的流式API
            # 由于模型管理器的流式API尚未实现，这里返回一个简单的流式响应
            response_text = "流式响应功能正在开发中..."
            
            # 模拟流式响应
            for char in response_text:
                await asyncio.sleep(0.01)  # 模拟延迟
                yield char
            
            # 添加完整的助手消息到会话
            assistant_msg = ChatMessage(
                role="assistant",
                content=response_text
            )
            session.add_message(assistant_msg)
            
        except Exception as e:
            self.logger.error(f"流式聊天失败: {e}")
            self.logger.exception(f"流式聊天失败: {e}")
    
    # ==================== 会话管理方法 ====================

    def _get_available_tools(self) -> List[Dict[str, Any]]:
        """获取可用工具列表（简化版本）"""
        # 这里返回一个简单的工具列表
        # 实际使用时可以从 tools.py 导入，但为了简化我们先返回空列表
        return []
    
    async def _get_available_tools_async(self) -> List[Dict[str, Any]]:
        """异步获取可用工具列表"""
        try:
            # 尝试从 tools.py 导入
            try:
                from .tools import gettools
            except ImportError:
                from tools import gettools
            
            tools_manager = gettools()
            tools = await tools_manager.get_tools()
            return tools
        except ImportError:
            self.logger.warning("tools.py 未找到，使用简化工具系统")
            return self._get_available_tools()
        except Exception as e:
            self.logger.error(f"获取工具列表失败: {e}")
            return []
    
    def list_sessions(self) -> List[str]:
        """列出所有会话ID"""
        return list(self.sessions.keys())
    
    def get_session_history(self, session_id: str) -> List[Dict[str, Any]]:
        """获取会话历史"""
        session = self.get_session(session_id)
        if not session:
            return []
        
        history = []
        for msg in session.messages:
            history.append({
                "role": msg.role,
                "content": msg.content,
                "timestamp": session.updated_at.isoformat()
            })
        
        return history
    
    def clear_session_history(self, session_id: str):
        """清空会话历史"""
        session = self.get_session(session_id)
        if session:
            session.clear_history()
            self.logger.info(f"已清空会话 '{session_id}' 的历史")
    
    def export_session(self, session_id: str) -> Dict[str, Any]:
        """导出会话数据"""
        session = self.get_session(session_id)
        if not session:
            return {}
        
        return {
            "session_id": session.session_id,
            "model": session.model_config.model_name if session.model_config else None,
            "messages": [msg.to_dict() for msg in session.messages],
            "created_at": session.created_at.isoformat(),
            "updated_at": session.updated_at.isoformat(),
            "message_count": len(session.messages)
        }
    
    def import_session(self, session_data: Dict[str, Any]) -> bool:
        """导入会话数据"""
        try:
            session_id = session_data.get("session_id")
            if not session_id:
                return False
            
            # 创建会话
            session = ChatSession(session_id=session_id)
            
            # 恢复消息
            messages_data = session_data.get("messages", [])
            for msg_data in messages_data:
                message = ChatMessage(
                    role=msg_data.get("role", ""),
                    content=msg_data.get("content", ""),
                    name=msg_data.get("name"),
                    tool_calls=msg_data.get("tool_calls"),
                    tool_call_id=msg_data.get("tool_call_id")
                )
                session.add_message(message)
            
            # 恢复时间戳
            created_at = session_data.get("created_at")
            if created_at:
                session.created_at = datetime.fromisoformat(created_at)
            
            updated_at = session_data.get("updated_at")
            if updated_at:
                session.updated_at = datetime.fromisoformat(updated_at)
            
            # 保存会话
            self.sessions[session_id] = session
            
            self.logger.info(f"已导入会话: {session_id}")
            return True
            
        except Exception as e:
            self.logger.error(f"导入会话失败: {e}")
            return False
    
    # ==================== 模型管理方法 ====================
    
    def switch_model(self, model_name: str, session_id: Optional[str] = None):
        """
        切换模型
        
        Args:
            model_name: 新的模型名称
            session_id: 可选，指定会话切换模型，如果为None则切换默认模型
        """
        new_config = self._get_model_config(model_name)
        if not new_config:
            self.logger.error(f"模型 '{model_name}' 未找到")
            return False
        
        if session_id:
            # 切换指定会话的模型
            session = self.get_session(session_id)
            if session:
                session.model_config = new_config
                self.logger.info(f"会话 '{session_id}' 已切换到模型: {model_name}")
                return True
            else:
                self.logger.error(f"会话 '{session_id}' 未找到")
                return False
        else:
            # 切换默认模型
            self.model_config = new_config
            self.logger.info(f"默认模型已切换到: {model_name}")
            return True
    
    def list_available_models(self, model_type: str = "chat") -> List[str]:
        """列出可用的模型"""
        try:
            return [name for name, config in api.MODEL_CONFIGS.items() if model_type in config.get("model_type", [])]
        except Exception as e:
            self.logger.error(f"列出模型失败: {e}")
            return []
    
    # ==================== 工具管理方法 ====================
    
    def enable_tools(self, enabled: bool = True):
        """启用或禁用工具调用"""
        self.tools_enabled = enabled
        
        status = "启用" if enabled else "禁用"
        self.logger.info(f"工具调用已{status}")
    
    def list_available_tools(self) -> List[str]:
        """列出可用的工具名称"""
        # 返回简化工具列表中的工具名称
        if not self.tools_manager:
            return []
        return self.tools_manager.list_tools()
    
    # ==================== 系统信息方法 ====================
    
    def get_system_info(self) -> Dict[str, Any]:
        """获取系统信息"""
        return {
            "model": self.model_config.model_name if self.model_config else None,
            "model_provider": self.model_config.provider if self.model_config else None,
            "tools_enabled": self.tools_enabled,
            "available_tools": self.list_available_tools(),
            "session_count": len(self.sessions),
            "max_tool_iterations": self.max_tool_iterations,
        }
    
    # ==================== 流式响应支持 ====================
    
    async def chat_stream(
        self,
        session_id: str,
        user_message: str,
        **kwargs
    ) -> AsyncGenerator[str, None]:
        """
        流式聊天接口
        
        Args:
            session_id: 会话ID
            user_message: 用户消息
            **kwargs: 额外的模型参数
            
        Returns:
            异步生成器，逐块返回响应文本
        """
        # 获取或创建会话
        session = self.get_session(session_id)
        if not session:
            session = self.create_session(session_id)
        
        # 添加用户消息
        user_msg = ChatMessage(role="user", content=user_message)
        session.add_message(user_msg)
        
        # 准备工具调用
        tools = []
        if self.tools_enabled and self.tools_manager:
            tools = await self._get_available_tools_async()
        
        # 调用流式聊天
        async for chunk in self._chat_stream(session, tools, **kwargs):
            yield chunk

# ==================== 便捷函数 ====================

def create_ai_chat(
    model_name: Optional[str] = None,
    tools_enabled: bool = True,
    system_prompt: str = ""
) -> AIChat:
    """
    创建AI聊天实例的便捷函数
    
    Args:
        model_name: 模型名称
        tools_enabled: 是否启用工具调用
        system_prompt: 系统提示词
        
    Returns:
        AIChat实例
    """
    ai_chat = AIChat(model_name=model_name, tools_enabled=tools_enabled)
    
    # 创建默认会话
    if system_prompt:
        ai_chat.create_session("default", system_prompt)
    
    return ai_chat

# ==================== 测试代码 ====================

async def test_basic_chat():
    """测试基本聊天功能"""
    print("=== 测试基本聊天功能 ===")
    
    # 创建AI聊天实例
    ai_chat = AIChat(model_name="deepseek-chat", tools_enabled=False)
    
    # 创建会话
    session = ai_chat.create_session("test_session", "你是一个有用的助手")
    
    # 测试聊天
    response = await ai_chat.chat("test_session", "你好，请介绍一下你自己")
    
    print(f"会话ID: {response.get('session_id')}")
    print(f"模型: {response.get('model')}")
    print(f"响应: {response.get('response', '')[:100]}...")
    print(f"成功: {response.get('success')}")
    
    # 显示会话历史
    history = ai_chat.get_session_history("test_session")
    print(f"\n会话历史 ({len(history)} 条消息):")
    for i, msg in enumerate(history):
        print(f"  {i+1}. [{msg['role']}] {msg['content'][:50]}...")
    
    return response

async def test_tool_integration():
    """测试工具集成"""
    print("\n=== 测试工具集成 ===")
    
    # 创建AI聊天实例（启用工具）
    ai_chat = AIChat(model_name="deepseek-chat", tools_enabled=True)
    
    # 显示可用工具
    tools = ai_chat.list_available_tools()
    print(f"可用工具: {tools}")
    
    # 创建会话
    session = ai_chat.create_session("tool_test", "你可以使用工具来帮助用户")
    
    # 测试系统信息
    system_info = ai_chat.get_system_info()
    print(f"系统信息: {system_info}")
    
    return system_info

async def test_session_management():
    """测试会话管理"""
    print("\n=== 测试会话管理 ===")
    
    ai_chat = AIChat()
    
    # 创建多个会话
    for i in range(3):
        session_id = f"session_{i}"
        system_prompt = f"这是会话{i}的系统提示"
        ai_chat.create_session(session_id, system_prompt)
    
    # 列出所有会话
    sessions = ai_chat.list_sessions()
    print(f"所有会话: {sessions}")
    
    # 导出导入测试
    if sessions:
        session_data = ai_chat.export_session(sessions[0])
        print(f"导出的会话数据: {session_data.keys()}")
        
        # 导入到新会话
        session_data["session_id"] = "imported_session"
        success = ai_chat.import_session(session_data)
        print(f"导入成功: {success}")
    
    return sessions

async def test_model_switching():
    """测试模型切换"""
    print("\n=== 测试模型切换 ===")
    
    ai_chat = AIChat()
    
    # 列出可用模型
    available_models = ai_chat.list_available_models("chat")
    print(f"可用聊天模型: {available_models}")
    
    # 切换模型
    if len(available_models) > 1:
        new_model = available_models[1]  # 切换到第二个模型
        success = ai_chat.switch_model(new_model)
        print(f"切换到模型 '{new_model}': {success}")
    
    return available_models

async def main_test():
    """主测试函数"""
    print("开始测试新的AI聊天系统...")
    
    try:
        # 测试基本聊天
        await test_basic_chat()
        
        # 测试工具集成
        await test_tool_integration()
        
        # 测试会话管理
        await test_session_management()
        
        # 测试模型切换
        await test_model_switching()
        
        print("\n=== 所有测试完成 ===")
        return {"success": True, "message": "测试通过"}
        
    except Exception as e:
        print(f"测试过程中出现错误: {e}")
        traceback.print_exc()
        return {"success": False, "error": str(e)}


if __name__ == "__main__":
    # 运行测试
    asyncio.run(main_test())