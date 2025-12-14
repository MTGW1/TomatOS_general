import os
import sys
import openai
import aiohttp
import asyncio
import ssl
import json
import re
import time
import random
from math import ceil, inf
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, Union

# 导入logger模块中的logger实例
try:
    from .logger import logger
except ImportError:
    from logger import logger

# 导入OpenAI库
try:
    import openai
    from openai import AsyncOpenAI
    OPENAI_AVAILABLE = True
except ImportError as e:
    logger.warning(f"无法导入openai库，将使用HTTP请求: {e}")
    OPENAI_AVAILABLE = False

# 导入api配置
try:
    from . import api
    from .api import ModelConfig
except ImportError:
    import api
    from api import ModelConfig





class PromptManager:
    """提示词管理器（从prompt_manager.py合并）"""
    
    def __init__(self, templates: Dict[str, str], bot_name: str, bot_aliases: List[str]):
        self.templates = templates
        self.bot_name = bot_name
        self.bot_aliases = bot_aliases
        
    def get_prompt(self, prompt_type: str, **kwargs) -> str:
        """
        获取指定类型的提示词
        
        Args:
            prompt_type: 提示词类型，如 "default", "io", "tool_calling"
            **kwargs: 格式化参数
            
        Returns:
            格式化后的提示词
        """
        if prompt_type not in self.templates:
            logger.warning(f"提示词类型 '{prompt_type}' 不存在，使用默认提示词")
            prompt_type = "default"
        
        template = self.templates[prompt_type]
        
        # 格式化模板
        try:
            formatted = template.format(**kwargs)
            return formatted
        except KeyError as e:
            logger.error(f"提示词模板格式化失败，缺少参数: {e}")
            return template
    
    def build_system_prompt(
        self, 
        base_prompt_type: str = "default",
        include_io_format: bool = False,
        include_tools: bool = False,
        tools: Optional[List[Dict[str, Any]]] = None,
        **kwargs
    ) -> str:
        """
        构建系统提示词
        
        Args:
            base_prompt_type: 基础提示词类型
            include_io_format: 是否包含IO格式
            include_tools: 是否包含工具调用
            tools: 工具列表
            **kwargs: 额外参数
            
        Returns:
            拼接后的系统提示词
        """
        # 获取基础提示词
        system_prompt = self.get_prompt(base_prompt_type, **kwargs)
        
        # 添加IO格式（如果需要）
        if include_io_format:
            io_prompt = self.get_prompt("io", **kwargs)
            system_prompt += "\n\n" + io_prompt
        
        # 添加工具调用（如果需要）
        if include_tools and tools:
            # 构建工具列表描述
            available_tools_list = self._build_tools_list(tools)
            
            # 工具调用格式
            tool_calling_format = """--- tool_call ---
<tool_name>工具名称</tool_name>
<parameters>{"参数名": "参数值"}</parameters>
<explanation>调用此工具的原因和说明</explanation>
--- end_tool_call ---"""
            
            # 获取工具调用提示词
            tool_prompt = self.get_prompt(
                "tool_calling",
                tool_calling_format=tool_calling_format,
                available_tools_list=available_tools_list,
                **kwargs
            )
            system_prompt += "\n\n" + tool_prompt
        
        return system_prompt.strip()
    
    def _build_tools_list(self, tools: List[Dict[str, Any]]) -> str:
        """构建工具列表描述"""
        if not tools:
            return "暂无可用工具"
        
        tools_list = []
        for tool in tools:
            tool_info = tool.get("function", {})
            name = tool_info.get("name", "未知工具")
            description = tool_info.get("description", "无描述")
            
            # 构建参数描述
            parameters = tool_info.get("parameters", {})
            param_desc = ""
            if parameters:
                props = parameters.get("properties", {})
                required = parameters.get("required", [])
                
                param_desc = "参数："
                for param_name, param_info in props.items():
                    param_type = param_info.get("type", "string")
                    param_desc_str = param_info.get("description", "")
                    
                    required_mark = "（必需）" if param_name in required else "（可选）"
                    param_desc += f"\n  - {param_name} ({param_type}){required_mark}: {param_desc_str}"
            
            tool_entry = f"- **{name}**: {description}"
            if param_desc:
                tool_entry += f"\n{param_desc}"
            
            tools_list.append(tool_entry)
        
        return "\n\n".join(tools_list)
    
    def select_prompt_strategy(
        self,
        has_tools: bool = False,
        is_group_chat: bool = False,
        **kwargs
    ) -> str:
        """
        选择提示词策略
        
        Args:
            has_tools: 是否有可用工具
            is_group_chat: 是否是群聊
            **kwargs: 额外参数
            
        Returns:
            构建好的系统提示词
        """
        # 基础提示词类型
        base_prompt_type = "default"
        
        # 群聊特殊处理
        if is_group_chat:
            kwargs["group_chat"] = True
            kwargs["mention_handling"] = f"当用户使用@{self.bot_name}或提到{', '.join(self.bot_aliases)}时，请回复"
        
        # 构建系统提示词
        system_prompt = self.build_system_prompt(
            base_prompt_type=base_prompt_type,
            include_io_format=False,
            include_tools=has_tools,
            **kwargs
        )
        
        return system_prompt
    
    def create_dynamic_prompt(
        self,
        user_message: str,
        conversation_history: List[Dict[str, str]],
        available_tools: List[Dict[str, Any]],
        **kwargs
    ) -> Dict[str, Any]:
        """
        创建动态提示词
        
        Args:
            user_message: 用户消息
            conversation_history: 对话历史
            available_tools: 可用工具列表
            **kwargs: 额外参数
            
        Returns:
            包含系统提示词和消息的字典
        """
        has_tools = len(available_tools) > 0
        
        # 选择提示词策略
        system_prompt = self.select_prompt_strategy(
            has_tools=has_tools,
            **kwargs
        )
        
        # 构建消息列表
        messages = []
        
        # 添加系统提示词
        messages.append({
            "role": "system",
            "content": system_prompt
        })
        
        # 添加对话历史
        messages.extend(conversation_history[-10:])  # 保留最近10条历史
        
        # 添加当前用户消息
        messages.append({
            "role": "user",
            "content": user_message
        })
        
        return {
            "messages": messages,
            "tools": available_tools if has_tools else None,
            "has_tools": has_tools
        }
    



class model:
    def __init__(self):
        self.default_model = ''
        self.default_vision_model = ''
        self.default_embedding_model = ''
        self.default_image_model = ''
        self.models: Dict[str, ModelConfig] = {}
        self._initialized = False
        self.prompt_manager: Optional[PromptManager] = None  # 提示词管理器
        
    def initialize(self):
        """初始化模型配置，从api_new.py加载配置"""
        if self._initialized:
            return
            
        try:
            if api is None:
                logger.error("无法导入api配置模块")
                return
            
            # 从api_new模块导入配置
            try:
                from TomatOS.bot.api import MODEL_CONFIGS, DEFAULT_MODELS, CHAT_OPTIONS, IMAGE_OPTIONS, EMBEDDING_OPTIONS, PROMPT_TEMPLATES, bot_name, bot_alliases
            except ImportError:
                # 如果绝对导入失败，尝试相对导入
                try:
                    from .api import MODEL_CONFIGS, DEFAULT_MODELS, CHAT_OPTIONS, IMAGE_OPTIONS, EMBEDDING_OPTIONS, PROMPT_TEMPLATES, bot_name, bot_alliases
                except ImportError:
                    # 如果相对导入也失败，直接导入
                    sys.path.append(os.path.dirname(os.path.abspath(__file__)))
                    from api import MODEL_CONFIGS, DEFAULT_MODELS, CHAT_OPTIONS, IMAGE_OPTIONS, EMBEDDING_OPTIONS, PROMPT_TEMPLATES, bot_name, bot_alliases
            
            # 初始化所有模型
            for model_name, config_dict in MODEL_CONFIGS.items():
                try:
                    # 创建ModelConfig对象
                    config = ModelConfig(
                        model_name=config_dict.get("model_name", model_name),
                        provider=config_dict.get("provider", ""),
                        api_key=config_dict.get("api_key", ""),
                        base_url=config_dict.get("base_url", ""),
                        model_type=config_dict.get("model_type", []),
                        cost_input_onCache=config_dict.get("cost_input_onCache", 0.0),
                        cost_input_offCache=config_dict.get("cost_input_offCache", 0.0),
                        cost_output=config_dict.get("cost_output", 0.0),
                        tpm=config_dict.get("tpm", 0),
                        rpm=config_dict.get("rpm", 0),
                        max_length=config_dict.get("max_length", 0),
                        thinking=config_dict.get("thinking", False),
                        thinking_string=config_dict.get("thinking_string", None),
                        temperature=config_dict.get("temperature", CHAT_OPTIONS.get("temperature", 0.7)),
                        top_p=config_dict.get("top_p", CHAT_OPTIONS.get("top_p", 1.0)),
                        max_tokens=config_dict.get("max_tokens", CHAT_OPTIONS.get("max_tokens", 2048)),
                        tool_usable=config_dict.get("tool_usable", False),
                        image_sizes=config_dict.get("image_sizes", []),
                        seed=config_dict.get("seed", IMAGE_OPTIONS.get("seed", None)),
                        image_nums=config_dict.get("image_nums", 1),
                        max_image_input=config_dict.get("max_image_input", 0),
                        steps=config_dict.get("steps", IMAGE_OPTIONS.get("num_inference_steps", 20)),
                        guidance_scale=config_dict.get("guidance_scale", IMAGE_OPTIONS.get("guidance_scale", 7.5)),
                        embedding_dimension=config_dict.get("embedding_dimension", 0),
                        embedding_format=config_dict.get("embedding_format", EMBEDDING_OPTIONS.get("encoding_format", "float"))
                    )
                    
                    self.models[model_name] = config
                    logger.info(f"已加载模型配置: {model_name}")
                    
                except Exception as e:
                    logger.error(f"加载模型配置失败 {model_name}: {e}")
            
            # 设置默认模型
            self.default_model = DEFAULT_MODELS.get("chat", "")
            self.default_vision_model = DEFAULT_MODELS.get("vision", "")
            self.default_embedding_model = DEFAULT_MODELS.get("embedding", "")
            self.default_image_model = DEFAULT_MODELS.get("image", "")
            
            # 初始化提示词管理器
            try:
                self.prompt_manager = PromptManager(
                    templates=PROMPT_TEMPLATES,
                    bot_name=bot_name,
                    bot_aliases=bot_alliases
                )
                logger.info("提示词管理器初始化完成")
            except Exception as e:
                logger.error(f"提示词管理器初始化失败: {e}")
                self.prompt_manager = None
            
            self._initialized = True
            logger.info("模型配置初始化完成")
            
        except Exception as e:
            logger.error(f"模型配置初始化失败: {e}")
    
    def get_model_config(self, model_name: str) -> Optional[ModelConfig]:
        """获取指定模型的配置"""
        if not self._initialized:
            self.initialize()
        return self.models.get(model_name)
    
    def get_default_model(self, model_type: str = "chat") -> Optional[ModelConfig]:
        """获取指定类型的默认模型配置"""
        if not self._initialized:
            self.initialize()
        
        model_name = ""
        if model_type == "chat":
            model_name = self.default_model
        elif model_type == "vision":
            model_name = self.default_vision_model
        elif model_type == "embedding":
            model_name = self.default_embedding_model
        elif model_type == "image":
            model_name = self.default_image_model
        
        return self.get_model_config(model_name) if model_name else None
    
    def list_models_by_type(self, model_type: str) -> List[str]:
        """列出指定类型的所有模型"""
        if not self._initialized:
            self.initialize()
        
        return [
            model_name for model_name, config in self.models.items()
            if model_type in config.model_type
        ]
    
    def get_prompt_manager(self) -> Optional[PromptManager]:
        """获取提示词管理器"""
        if not self._initialized:
            self.initialize()
        return self.prompt_manager
    
    def get_prompt(self, prompt_type: str, **kwargs) -> str:
        """获取指定类型的提示词（便捷方法）"""
        pm = self.get_prompt_manager()
        if pm is None:
            logger.warning("提示词管理器未初始化，返回空字符串")
            return ""
        return pm.get_prompt(prompt_type, **kwargs)
    
    def build_system_prompt(
        self,
        base_prompt_type: str = "default",
        include_io_format: bool = False,
        include_tools: bool = False,
        tools: Optional[List[Dict[str, Any]]] = None,
        **kwargs
    ) -> str:
        """构建系统提示词（便捷方法）"""
        pm = self.get_prompt_manager()
        if pm is None:
            logger.warning("提示词管理器未初始化，返回空字符串")
            return ""
        return pm.build_system_prompt(
            base_prompt_type=base_prompt_type,
            include_io_format=include_io_format,
            include_tools=include_tools,
            tools=tools,
            **kwargs
        )
    
    def create_dynamic_prompt(
        self,
        user_message: str,
        conversation_history: List[Dict[str, str]],
        available_tools: List[Dict[str, Any]],
        **kwargs
    ) -> Dict[str, Any]:
        """创建动态提示词（便捷方法）"""
        pm = self.get_prompt_manager()
        if pm is None:
            logger.warning("提示词管理器未初始化，返回空字典")
            return {"messages": [], "tools": None, "has_tools": False}
        return pm.create_dynamic_prompt(
            user_message=user_message,
            conversation_history=conversation_history,
            available_tools=available_tools,
            **kwargs
        )
    
    def get_thinking_content(self, response: Dict[str, Any]) -> str:
        """
        从响应中提取思维流内容
        
        Args:
            response: 聊天响应字典
            
        Returns:
            思维流内容，如果没有则返回空字符串
        """
        try:
            choices = response.get("choices", [])
            if not choices:
                return ""
            
            message = choices[0].get("message", {})
            return message.get("reasoning_content", "")
        except Exception as e:
            logger.warning(f"提取思维流内容失败: {e}")
            return ""

    async def chat_completion(
        self,
        messages: List[Dict[str, str]],
        model_name: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        stream: bool = False,
        thinking: bool = False,
        **kwargs
    ) -> Dict[str, Any]:
        """聊天补全接口"""
        if not self._initialized:
            self.initialize()
        
        # 获取模型配置
        if model_name is None:
            model_config = self.get_default_model("chat")
        else:
            model_config = self.get_model_config(model_name)
        
        if model_config is None:
            raise ValueError(f"未找到模型配置: {model_name or '默认聊天模型'}")
        
        # thinking = 
        
        # 准备请求参数
        params = {
            "model": model_config.model_name,
            "messages": messages,
            "temperature": temperature if temperature is not None else model_config.temperature,
            "max_tokens": max_tokens if max_tokens is not None else model_config.max_tokens,
            "stream": stream,
        }
        
        # 添加可选参数
        if model_config.top_p != 1.0:
            params["top_p"] = model_config.top_p
        if model_config.top_k != 0:
            params["top_k"] = model_config.top_k
        if model_config.n != 1:
            params["n"] = model_config.n
        
        # 添加额外的kwargs参数
        params.update(kwargs)
        
        # 根据提供商发送请求
        if model_config.provider in ["deepseek", "siliconflow"]:
            logger.debug(f"调用模型 {model_config.model_name}，提供商: {model_config.provider}")
            return await self._call_openai_api(model_config, params)
        elif model_config.provider == "local":
            logger.debug(f"调用本地模型 {model_config.model_name}，提供商: {model_config.provider}")
            return await self._call_ollama_api(model_config, params)
        else:
            raise ValueError(f"不支持的提供商: {model_config.provider}")
    
    async def generate_embeddings(
        self,
        texts: Union[str, List[str]],
        model_name: Optional[str] = None,
        **kwargs
    ) -> List[List[float]]:
        """生成文本嵌入向量"""
        if not self._initialized:
            self.initialize()
        
        # 获取模型配置
        if model_name is None:
            model_config = self.get_default_model("embedding")
        else:
            model_config = self.get_model_config(model_name)
        
        if model_config is None:
            raise ValueError(f"未找到模型配置: {model_name or '默认嵌入模型'}")
        
        # 准备请求参数
        if isinstance(texts, str):
            texts = [texts]
        
        params = {
            "model": model_config.model_name,
            "input": texts,
            "encoding_format": model_config.embedding_format,
        }
        
        if model_config.embedding_dimension > 0:
            params["dimensions"] = model_config.embedding_dimension
        
        # 添加额外的kwargs参数
        params.update(kwargs)
        
        # 根据提供商发送请求
        if model_config.provider in ["deepseek", "siliconflow"]:
            return await self._call_openai_embeddings_api(model_config, params)
        elif model_config.provider == "local":
            return await self._call_ollama_embeddings_api(model_config, params)
        else:
            raise ValueError(f"不支持的提供商: {model_config.provider}")
    
    async def generate_image(
        self,
        prompt: str,
        model_name: Optional[str] = None,
        size: Optional[tuple] = None,
        **kwargs
    ) -> List[str]:
        """生成图像"""
        if not self._initialized:
            self.initialize()
        
        # 获取模型配置
        if model_name is None:
            model_config = self.get_default_model("image")
        else:
            model_config = self.get_model_config(model_name)
        
        if model_config is None:
            raise ValueError(f"未找到模型配置: {model_name or '默认图像模型'}")
        
        # 准备请求参数
        params = {
            "model": model_config.model_name,
            "prompt": prompt,
            "n": model_config.image_nums,
            "size": size or (model_config.image_sizes[0] if model_config.image_sizes else (1024, 1024)),
            "steps": model_config.steps,
            "guidance_scale": model_config.guidance_scale,
        }
        
        if model_config.seed is not None:
            params["seed"] = model_config.seed
        
        # 添加额外的kwargs参数
        params.update(kwargs)
        
        # 根据提供商发送请求
        if model_config.provider in ["siliconflow"]:
            return await self._call_siliconflow_image_api(model_config, params)
        else:
            raise ValueError(f"不支持的提供商或功能: {model_config.provider}")
    
    @logger.logger_catch
    async def _call_openai_api(self, model_config: ModelConfig, params: Dict[str, Any]) -> Dict[str, Any]:
        """调用OpenAI兼容API，直接使用openai库"""
        
        # 尝试使用OpenAI库
        if OPENAI_AVAILABLE and model_config.provider in ["deepseek", "siliconflow"]:
            try:
                logger.info(f"使用openai库调用: {model_config.provider}/{model_config.model_name}")
                
                # 创建OpenAI客户端
                client = AsyncOpenAI(
                    api_key=model_config.api_key,
                    base_url=model_config.base_url,
                    timeout=60
                )
                
                # 准备参数
                openai_params = {
                    "model": model_config.model_name,
                    "messages": params.get("messages", []),
                    "temperature": params.get("temperature", 0.7),
                }
                
                if "max_tokens" in params:
                    openai_params["max_tokens"] = params["max_tokens"]
                
                if "tools" in params:
                    openai_params["tools"] = params["tools"]
                    if "tool_choice" in params:
                        openai_params["tool_choice"] = params["tool_choice"]
                
                # 调用聊天补全
                response = await client.chat.completions.create(**openai_params)
                
                # 解析响应
                choice = response.choices[0]
                message = choice.message
                # response = response.to_dict()
                
                # 转换为标准格式
                result = {
                    "id": f"chatcmpl-{int(time.time())}",
                    "object": "chat.completion",
                    "created": int(time.time()),
                    "model": model_config.model_name,
                    "choices": [
                        {
                            "index": 0,
                            "message": {
                                "role": message.role,
                                "content": message.content or ""
                            },
                            "finish_reason": response.to_dict().get("finish_reason", "stop")
                        }
                    ],
                }
                
                # 尝试提取思维流内容
                if hasattr(message, 'reasoning_content') and message.reasoning_content:
                    result["choices"][0]["message"]["reasoning_content"] = message.reasoning_content
                
                # 添加工具调用
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
                    result["choices"][0]["message"]["tool_calls"] = tool_calls
                
                # 添加使用情况
                if response.usage:
                    result["usage"] = {
                        "prompt_tokens": response.usage.prompt_tokens,
                        "completion_tokens": response.usage.completion_tokens,
                        "total_tokens": response.usage.total_tokens
                    }
                else:
                    result["usage"] = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
                
                logger.info(f"openai库调用成功: {model_config.provider}")
                return result
                
            except Exception as e:
                logger.warning(f"openai库调用失败，回退到HTTP请求: {e}")
                logger.exception(f"openai库调用失败: {e}")
                # 继续执行HTTP请求
        
        # 回退到HTTP请求
        logger.info(f"使用HTTP请求调用: {model_config.provider}")
        headers = {
            "Authorization": f"Bearer {model_config.api_key}",
            "Content-Type": "application/json"
        }
        
        # 构建URL
        if model_config.provider == "deepseek":
            url = f"{model_config.base_url}chat/completions"
        else:
            url = f"{model_config.base_url}chat/completions"
        
        async with aiohttp.ClientSession() as session:
            try:
                async with session.post(url, headers=headers, json=params) as response:
                    if response.status == 200:
                        return await response.json()
                    else:
                        error_text = await response.text()
                        raise Exception(f"API请求失败: {response.status} - {error_text}")
            except Exception as e:
                logger.error(f"OpenAI API调用失败: {e}")
                raise
    
    async def _call_ollama_api(self, model_config: ModelConfig, params: Dict[str, Any]) -> Dict[str, Any]:
        """调用Ollama API"""
        headers = {
            "Content-Type": "application/json"
        }
        
        url = f"{model_config.base_url}chat/completions"
        
        # 转换参数格式
        ollama_params = {
            "model": params["model"],
            "messages": params["messages"],
            "options": {}
        }
        
        if "temperature" in params:
            ollama_params["options"]["temperature"] = params["temperature"]
        if "max_tokens" in params:
            ollama_params["options"]["num_predict"] = params["max_tokens"]
        if "top_p" in params:
            ollama_params["options"]["top_p"] = params["top_p"]
        
        async with aiohttp.ClientSession() as session:
            try:
                async with session.post(url, headers=headers, json=ollama_params) as response:
                    if response.status == 200:
                        return await response.json()
                    else:
                        error_text = await response.text()
                        raise Exception(f"Ollama API请求失败: {response.status} - {error_text}")
            except Exception as e:
                logger.error(f"Ollama API调用失败: {e}")
                raise
    
    async def _call_openai_embeddings_api(self, model_config: ModelConfig, params: Dict[str, Any]) -> List[List[float]]:
        """调用OpenAI兼容的嵌入API"""
        headers = {
            "Authorization": f"Bearer {model_config.api_key}",
            "Content-Type": "application/json"
        }
        
        url = f"{model_config.base_url}embeddings"
        
        async with aiohttp.ClientSession() as session:
            try:
                async with session.post(url, headers=headers, json=params) as response:
                    if response.status == 200:
                        result = await response.json()
                        return [item["embedding"] for item in result["data"]]
                    else:
                        error_text = await response.text()
                        raise Exception(f"嵌入API请求失败: {response.status} - {error_text}")
            except Exception as e:
                logger.error(f"嵌入API调用失败: {e}")
                raise
    
    async def _call_ollama_embeddings_api(self, model_config: ModelConfig, params: Dict[str, Any]) -> List[List[float]]:
        """调用Ollama嵌入API"""
        headers = {
            "Content-Type": "application/json"
        }
        
        url = f"{model_config.base_url}embeddings"
        
        ollama_params = {
            "model": params["model"],
            "prompt": params["input"][0] if isinstance(params["input"], list) else params["input"]
        }
        
        async with aiohttp.ClientSession() as session:
            try:
                async with session.post(url, headers=headers, json=ollama_params) as response:
                    if response.status == 200:
                        result = await response.json()
                        return [result["embedding"]]
                    else:
                        error_text = await response.text()
                        raise Exception(f"Ollama嵌入API请求失败: {response.status} - {error_text}")
            except Exception as e:
                logger.error(f"Ollama嵌入API调用失败: {e}")
                raise
    
    async def _call_siliconflow_image_api(self, model_config: ModelConfig, params: Dict[str, Any]) -> List[str]:
        """调用SiliconFlow图像生成API"""
        headers = {
            "Authorization": f"Bearer {model_config.api_key}",
            "Content-Type": "application/json"
        }
        
        url = f"{model_config.base_url}images/generations"
        
        async with aiohttp.ClientSession() as session:
            try:
                async with session.post(url, headers=headers, json=params) as response:
                    if response.status == 200:
                        result = await response.json()
                        return [item["url"] for item in result["data"]]
                    else:
                        error_text = await response.text()
                        raise Exception(f"图像生成API请求失败: {response.status} - {error_text}")
            except Exception as e:
                logger.error(f"图像生成API调用失败: {e}")
                raise
    
    async def _process_chat_response(self, response: Dict[str, Any], model_config: ModelConfig) -> Dict[str, Any]:
        """处理聊天响应，计算成本"""
        try:
            usage = response.get("usage", {})
            prompt_tokens = usage.get("prompt_tokens", 0)
            completion_tokens = usage.get("completion_tokens", 0)
            
            # 计算成本（简化版本）
            input_cost = model_config.cost_input_offCache * (prompt_tokens / 1_000_000)
            output_cost = model_config.cost_output * (completion_tokens / 1_000_000)
            total_cost = input_cost + output_cost
            
            return {
                "content": response["choices"][0]["message"]["content"],
                "thinking_content": response["choices"][0]["message"].get("reasoning_content", ""),
                "usage": usage,
                "cost": total_cost,
                "model": model_config.model_name
            }
        except Exception as e:
            logger.error(f"处理聊天响应失败: {e}")
            return {
                "content": response.get("choices", [{}])[0].get("message", {}).get("content", ""),
                "thinking_content": "",
                "usage": {},
                "cost": 0.0,
                "model": model_config.model_name
            }
    
    async def _process_embedding_response(self, embeddings: List[List[float]], model_config: ModelConfig) -> Dict[str, Any]:
        """处理嵌入响应，计算成本"""
        try:
            # 计算成本（简化版本）
            # 假设每个嵌入请求有固定的token数
            estimated_tokens = 1000  # 简化估计
            cost = model_config.cost_input_offCache * (estimated_tokens / 1_000_000)
            
            return {
                "embeddings": embeddings,
                "dimension": len(embeddings[0]) if embeddings else 0,
                "count": len(embeddings),
                "cost": cost,
                "model": model_config.model_name
            }
        except Exception as e:
            logger.error(f"处理嵌入响应失败: {e}")
            return {
                "embeddings": embeddings,
                "dimension": 0,
                "count": len(embeddings),
                "cost": 0.0,
                "model": model_config.model_name
            }


# 创建全局模型实例
_model_instance = None

def get_model() -> model:
    """获取全局模型实例"""
    global _model_instance
    if _model_instance is None:
        _model_instance = model()
        _model_instance.initialize()
    return _model_instance


def get_prompt_manager() -> Optional[PromptManager]:
    """获取全局提示词管理器实例（向后兼容）"""
    model_instance = get_model()
    return model_instance.get_prompt_manager()


if __name__ == "__main__":
    # 测试代码
    async def test():
        model_instance = get_model()
        
        # 测试列出模型
        print("聊天模型:", model_instance.list_models_by_type("chat"))
        print("视觉模型:", model_instance.list_models_by_type("vision"))
        print("嵌入模型:", model_instance.list_models_by_type("embedding"))
        print("图像模型:", model_instance.list_models_by_type("image"))
        
        # 测试获取默认模型
        # default_chat = model_instance.get_default_model("chat")
        # if default_chat:
        #     print(f"默认聊天模型: {default_chat.model_name}")
        default_chat = "deepseek-reasoner"
        model_config = model_instance.get_model_config(default_chat)
        if model_config:
            print(f"默认聊天模型: {model_config.model_name}")
            print(f"是否启用思考模式: {model_config.thinking}")
        
        # 测试聊天功能
        try:
            messages = [
                # {"role": "system", "content": "你是一个有帮助的助手。"},
                {"role": "user", "content": "流体的流动性方程是怎样推导出来的？"}
            ]
            
            response = await model_instance.chat_completion(
                messages=messages,
                model_name=default_chat,
                temperature=0.7,
                max_tokens=500,
                stream=False,
                extra_body = {"thinking": {"type": "enabled"}} if model_config and model_config.thinking else None
            )
            print(f"聊天响应: {response}")
        except Exception as e:
            print(f"聊天测试失败: {e}")
            logger.exception(f"聊天测试失败: {e}")
    
    asyncio.run(test())