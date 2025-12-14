import openai
import api
import asyncio
from logger import logger
import json
import traceback

def test_tool_calling():
    """测试工具调用"""
    def answer():
        return "114514"
    prompt = """帮我运行一个工具函数, 并返回结果。"""
    model = "deepseek-reasoner"
    
    # 查找模型配置
    if model not in api.MODEL_CONFIGS:
        print(f"❌ 模型 '{model}' 未在配置中找到")
        return False
        
    provider = api.MODEL_CONFIGS[model]["provider"]
    
    # 查找提供商配置
    if provider not in api.API_CONFIGS:
        print(f"❌ 提供商 '{provider}' 未在API配置中找到")
        return False
        
    api_config = api.API_CONFIGS[provider]
    api_key = api_config.get("token", "")
    base_url = api_config.get("api_base", "")
    
    # 验证API密钥
    if not api_key:
        print(f"❌ 提供商 '{provider}' 的API密钥未配置")
        return False
        
    logger.info("测试工具调用...\n")

    tool = {
        "type": "function",
        "function": {
            "name": "get_answer",
            "description": "获取一个答案",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": []
            }
        }
    }
    try:
        messages = [
            {"role": "system", "content": "你是一个有帮助的助手。"},
            {"role": "user", "content": prompt}
        ]
        while True:
            client = openai.AsyncOpenAI(api_key=api_key, base_url=base_url)
            response = asyncio.run(
                client.chat.completions.create(
                    model=model,
                    messages=messages,
                    tools=[tool],
                    max_tokens=1024,
                    temperature=0.2,
                    stream=False
                )
            )
            print(response)
            response = response.to_dict()
            stop_reason = response.get("stop_reason", "")
            if stop_reason == "tool_call":
                messages.append(response["choices"][0]["message"])
                function_call = response["choices"][0]["message"].get("function_call", {})
                if function_call.get("name") == "get_answer":
                    result = answer()
                    print(f"✅ 工具调用成功, 结果: {result}")
                    return True
                else:
                    print(f"❌ 未识别的工具调用: {function_call.get('name')}")
                    return False
            else:
                finish_reason = response["choices"][0].get("finish_reason", "")
                if finish_reason == "tool_calls":
                    messages.append(response["choices"][0]["message"])
                    tool_calls = response["choices"][0]["message"].get("tool_calls", [])
                    if tool_calls and tool_calls[0]["function"].get("name") == "get_answer":
                        result = answer()
                        print(f"✅ 工具调用成功, 结果: {result}")
                        messages.append({"role": "tool", "tool_call_id": tool_calls[0]["id"], "name": "get_answer", "content": result})
                    else:
                        print(f"❌ 未识别的工具调用")
                else:
                    break
        print("❌ 未触发工具调用")

    except Exception as e:
        print(f"❌ 工具调用测试失败: {e}")

        traceback.print_exc()
        return False
    

if __name__ == "__main__":
    test_tool_calling()