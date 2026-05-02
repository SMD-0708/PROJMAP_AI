"""LLM 提供商抽象接口

提供统一的 LLM 服务接口，支持多种后端。
设计原则：
- 接口抽象：所有 LLM 服务实现相同接口
- 配置驱动：通过配置切换提供商，无需修改代码
- 能力检测：运行时检查提供商可用性
- 降级策略：主提供商失败时自动切换

注意：此模块不包含任何 API 密钥，密钥通过环境变量或配置文件提供。
"""

import abc
import asyncio
import json
import logging
import os
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, AsyncGenerator, Optional, Protocol, runtime_checkable

logger = logging.getLogger(__name__)


class LLMProviderType(Enum):
    """LLM 提供商类型"""
    DEEPSEEK = "deepseek"
    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    GOOGLE = "google"
    AZURE = "azure"
    LOCAL = "local"  # 本地模型，如 Ollama
    CUSTOM = "custom"  # 自定义提供商


@dataclass
class LLMModelInfo:
    """LLM 模型信息"""
    id: str
    name: str
    provider: str
    context_length: int = 4096
    max_output_tokens: int = 2048
    supports_streaming: bool = True
    supports_functions: bool = False
    supports_vision: bool = False
    pricing_per_1k_input: float = 0.0  # 美元
    pricing_per_1k_output: float = 0.0  # 美元
    capabilities: list[str] = field(default_factory=list)


@dataclass
class LLMRequest:
    """LLM 请求"""
    prompt: str
    system_prompt: Optional[str] = None
    model: Optional[str] = None
    temperature: float = 0.7
    max_tokens: Optional[int] = None
    top_p: float = 1.0
    frequency_penalty: float = 0.0
    presence_penalty: float = 0.0
    stop_sequences: Optional[list[str]] = None
    metadata: dict = field(default_factory=dict)


@dataclass
class LLMResponse:
    """LLM 响应"""
    content: str
    model: str
    provider: str
    usage: dict = field(default_factory=dict)  # {prompt_tokens, completion_tokens, total_tokens}
    finish_reason: str = "stop"
    latency_ms: float = 0.0
    raw_response: Any = None


@dataclass
class LLMConfig:
    """LLM 配置"""
    provider: str
    model: str
    api_key: Optional[str] = None  # 从环境变量读取，这里可为空
    api_base: Optional[str] = None
    timeout: int = 60
    max_retries: int = 3
    retry_delay: float = 1.0
    default_temperature: float = 0.7
    default_max_tokens: int = 2048
    extra_headers: dict = field(default_factory=dict)
    extra_params: dict = field(default_factory=dict)


@runtime_checkable
class LLMProvider(Protocol):
    """LLM 提供商协议
    
    所有 LLM 提供商必须实现此协议。
    """
    
    @property
    def provider_type(self) -> LLMProviderType:
        """提供商类型"""
        ...
    
    @property
    def provider_name(self) -> str:
        """提供商名称"""
        ...
    
    def is_available(self) -> bool:
        """检查是否可用（API密钥是否配置）"""
        ...
    
    def get_model_list(self) -> list[LLMModelInfo]:
        """获取可用模型列表"""
        ...
    
    async def generate(self, request: LLMRequest) -> LLMResponse:
        """生成文本"""
        ...
    
    async def generate_stream(
        self, request: LLMRequest
    ) -> AsyncGenerator[str, None]:
        """流式生成文本"""
        ...
    
    def validate_config(self) -> tuple[bool, str]:
        """验证配置是否有效"""
        ...


class BaseLLMProvider(abc.ABC):
    """LLM 提供商基类
    
    所有具体提供商应继承此类。
    """
    
    def __init__(self, config: LLMConfig):
        self.config = config
        self._logger = logging.getLogger(f"projmap.llm.{self.provider_name}")
    
    @property
    @abc.abstractmethod
    def provider_type(self) -> LLMProviderType:
        """提供商类型"""
        pass
    
    @property
    @abc.abstractmethod
    def provider_name(self) -> str:
        """提供商名称"""
        pass
    
    def _get_api_key(self) -> Optional[str]:
        """获取 API 密钥
        
        优先从配置获取，其次从环境变量获取。
        """
        if self.config.api_key:
            return self.config.api_key
        
        # 环境变量映射
        env_var_map = {
            LLMProviderType.DEEPSEEK: "DEEPSEEK_API_KEY",
            LLMProviderType.OPENAI: "OPENAI_API_KEY",
            LLMProviderType.ANTHROPIC: "ANTHROPIC_API_KEY",
            LLMProviderType.GOOGLE: "GOOGLE_API_KEY",
            LLMProviderType.AZURE: "AZURE_OPENAI_API_KEY",
        }
        
        env_var = env_var_map.get(self.provider_type)
        if env_var:
            return os.getenv(env_var)
        
        return None
    
    def is_available(self) -> bool:
        """检查是否可用"""
        return self._get_api_key() is not None
    
    @abc.abstractmethod
    def get_model_list(self) -> list[LLMModelInfo]:
        """获取可用模型列表"""
        pass
    
    @abc.abstractmethod
    async def generate(self, request: LLMRequest) -> LLMResponse:
        """生成文本"""
        pass
    
    async def generate_stream(
        self, request: LLMRequest
    ) -> AsyncGenerator[str, None]:
        """流式生成文本
        
        默认实现为非流式，子类可覆盖。
        """
        response = await self.generate(request)
        yield response.content
    
    def validate_config(self) -> tuple[bool, str]:
        """验证配置"""
        if not self.is_available():
            return False, f"API 密钥未配置，请设置环境变量或配置文件"
        return True, ""
    
    def _prepare_request_body(self, request: LLMRequest) -> dict:
        """准备请求体（子类可覆盖）"""
        body = {
            "model": request.model or self.config.model,
            "messages": self._build_messages(request),
            "temperature": request.temperature,
            "max_tokens": request.max_tokens or self.config.default_max_tokens,
            "top_p": request.top_p,
            "frequency_penalty": request.frequency_penalty,
            "presence_penalty": request.presence_penalty,
        }
        
        if request.stop_sequences:
            body["stop"] = request.stop_sequences
        
        # 添加额外参数
        body.update(self.config.extra_params)
        
        return body
    
    def _build_messages(self, request: LLMRequest) -> list[dict]:
        """构建消息列表"""
        messages = []
        
        if request.system_prompt:
            messages.append({
                "role": "system",
                "content": request.system_prompt,
            })
        
        messages.append({
            "role": "user",
            "content": request.prompt,
        })
        
        return messages


# ========== 具体提供商实现 ==========

class DeepSeekProvider(BaseLLMProvider):
    """DeepSeek 提供商"""
    
    DEFAULT_API_BASE = "https://api.deepseek.com/v1"
    
    @property
    def provider_type(self) -> LLMProviderType:
        return LLMProviderType.DEEPSEEK
    
    @property
    def provider_name(self) -> str:
        return "deepseek"
    
    def get_model_list(self) -> list[LLMModelInfo]:
        return [
            LLMModelInfo(
                id="deepseek-chat",
                name="DeepSeek Chat",
                provider="deepseek",
                context_length=32768,
                max_output_tokens=4096,
                supports_streaming=True,
                supports_functions=False,
                pricing_per_1k_input=0.00014,
                pricing_per_1k_output=0.00028,
                capabilities=["chat", "code", "analysis"],
            ),
            LLMModelInfo(
                id="deepseek-coder",
                name="DeepSeek Coder",
                provider="deepseek",
                context_length=16384,
                max_output_tokens=4096,
                supports_streaming=True,
                supports_functions=False,
                pricing_per_1k_input=0.00014,
                pricing_per_1k_output=0.00028,
                capabilities=["code", "completion", "analysis"],
            ),
        ]
    
    async def generate(self, request: LLMRequest) -> LLMResponse:
        import aiohttp
        
        api_key = self._get_api_key()
        if not api_key:
            raise ValueError("DeepSeek API key not configured")
        
        api_base = self.config.api_base or self.DEFAULT_API_BASE
        url = f"{api_base}/chat/completions"
        
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        headers.update(self.config.extra_headers)
        
        body = self._prepare_request_body(request)
        
        import time
        start_time = time.time()
        
        async with aiohttp.ClientSession() as session:
            async with session.post(
                url, headers=headers, json=body, timeout=self.config.timeout
            ) as response:
                if response.status != 200:
                    error_text = await response.text()
                    raise RuntimeError(f"DeepSeek API error: {response.status} - {error_text}")
                
                data = await response.json()
        
        latency = (time.time() - start_time) * 1000
        
        return LLMResponse(
            content=data["choices"][0]["message"]["content"],
            model=data.get("model", request.model or self.config.model),
            provider=self.provider_name,
            usage=data.get("usage", {}),
            finish_reason=data["choices"][0].get("finish_reason", "stop"),
            latency_ms=latency,
            raw_response=data,
        )
    
    async def generate_stream(
        self, request: LLMRequest
    ) -> AsyncGenerator[str, None]:
        import aiohttp
        
        api_key = self._get_api_key()
        if not api_key:
            raise ValueError("DeepSeek API key not configured")
        
        api_base = self.config.api_base or self.DEFAULT_API_BASE
        url = f"{api_base}/chat/completions"
        
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        
        body = self._prepare_request_body(request)
        body["stream"] = True
        
        async with aiohttp.ClientSession() as session:
            async with session.post(
                url, headers=headers, json=body, timeout=self.config.timeout
            ) as response:
                async for line in response.content:
                    line = line.decode("utf-8").strip()
                    if line.startswith("data: "):
                        data_str = line[6:]
                        if data_str == "[DONE]":
                            break
                        try:
                            data = json.loads(data_str)
                            delta = data["choices"][0].get("delta", {})
                            if "content" in delta:
                                yield delta["content"]
                        except (json.JSONDecodeError, KeyError):
                            continue


class OpenAIProvider(BaseLLMProvider):
    """OpenAI 提供商"""
    
    DEFAULT_API_BASE = "https://api.openai.com/v1"
    
    @property
    def provider_type(self) -> LLMProviderType:
        return LLMProviderType.OPENAI
    
    @property
    def provider_name(self) -> str:
        return "openai"
    
    def get_model_list(self) -> list[LLMModelInfo]:
        return [
            LLMModelInfo(
                id="gpt-4o",
                name="GPT-4o",
                provider="openai",
                context_length=128000,
                max_output_tokens=4096,
                supports_streaming=True,
                supports_functions=True,
                supports_vision=True,
                pricing_per_1k_input=0.005,
                pricing_per_1k_output=0.015,
                capabilities=["chat", "code", "analysis", "vision"],
            ),
            LLMModelInfo(
                id="gpt-4o-mini",
                name="GPT-4o Mini",
                provider="openai",
                context_length=128000,
                max_output_tokens=4096,
                supports_streaming=True,
                supports_functions=True,
                supports_vision=True,
                pricing_per_1k_input=0.00015,
                pricing_per_1k_output=0.0006,
                capabilities=["chat", "code", "analysis", "vision"],
            ),
            LLMModelInfo(
                id="gpt-4-turbo",
                name="GPT-4 Turbo",
                provider="openai",
                context_length=128000,
                max_output_tokens=4096,
                supports_streaming=True,
                supports_functions=True,
                pricing_per_1k_input=0.01,
                pricing_per_1k_output=0.03,
                capabilities=["chat", "code", "analysis"],
            ),
        ]
    
    async def generate(self, request: LLMRequest) -> LLMResponse:
        import aiohttp
        
        api_key = self._get_api_key()
        if not api_key:
            raise ValueError("OpenAI API key not configured")
        
        api_base = self.config.api_base or self.DEFAULT_API_BASE
        url = f"{api_base}/chat/completions"
        
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        
        body = self._prepare_request_body(request)
        
        import time
        start_time = time.time()
        
        async with aiohttp.ClientSession() as session:
            async with session.post(
                url, headers=headers, json=body, timeout=self.config.timeout
            ) as response:
                if response.status != 200:
                    error_text = await response.text()
                    raise RuntimeError(f"OpenAI API error: {response.status} - {error_text}")
                
                data = await response.json()
        
        latency = (time.time() - start_time) * 1000
        
        return LLMResponse(
            content=data["choices"][0]["message"]["content"],
            model=data.get("model", request.model or self.config.model),
            provider=self.provider_name,
            usage=data.get("usage", {}),
            finish_reason=data["choices"][0].get("finish_reason", "stop"),
            latency_ms=latency,
            raw_response=data,
        )


class OllamaProvider(BaseLLMProvider):
    """Ollama 本地模型提供商"""
    
    DEFAULT_API_BASE = "http://localhost:11434"
    
    @property
    def provider_type(self) -> LLMProviderType:
        return LLMProviderType.LOCAL
    
    @property
    def provider_name(self) -> str:
        return "ollama"
    
    def is_available(self) -> bool:
        """检查 Ollama 服务是否运行"""
        import urllib.request
        try:
            api_base = self.config.api_base or self.DEFAULT_API_BASE
            urllib.request.urlopen(f"{api_base}/api/tags", timeout=2)
            return True
        except:
            return False
    
    def get_model_list(self) -> list[LLMModelInfo]:
        # 常用 Ollama 模型
        return [
            LLMModelInfo(
                id="llama3.1",
                name="Llama 3.1",
                provider="ollama",
                context_length=128000,
                max_output_tokens=4096,
                supports_streaming=True,
                pricing_per_1k_input=0.0,  # 本地免费
                pricing_per_1k_output=0.0,
                capabilities=["chat", "code"],
            ),
            LLMModelInfo(
                id="codellama",
                name="Code Llama",
                provider="ollama",
                context_length=16384,
                max_output_tokens=4096,
                supports_streaming=True,
                pricing_per_1k_input=0.0,
                pricing_per_1k_output=0.0,
                capabilities=["code", "completion"],
            ),
            LLMModelInfo(
                id="qwen2.5",
                name="Qwen 2.5",
                provider="ollama",
                context_length=32768,
                max_output_tokens=4096,
                supports_streaming=True,
                pricing_per_1k_input=0.0,
                pricing_per_1k_output=0.0,
                capabilities=["chat", "code", "analysis"],
            ),
        ]
    
    async def generate(self, request: LLMRequest) -> LLMResponse:
        import aiohttp
        
        api_base = self.config.api_base or self.DEFAULT_API_BASE
        url = f"{api_base}/api/generate"
        
        body = {
            "model": request.model or self.config.model,
            "prompt": request.prompt,
            "system": request.system_prompt or "",
            "stream": False,
            "options": {
                "temperature": request.temperature,
                "num_predict": request.max_tokens or self.config.default_max_tokens,
                "top_p": request.top_p,
            },
        }
        
        import time
        start_time = time.time()
        
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=body, timeout=self.config.timeout) as response:
                if response.status != 200:
                    error_text = await response.text()
                    raise RuntimeError(f"Ollama API error: {response.status} - {error_text}")
                
                data = await response.json()
        
        latency = (time.time() - start_time) * 1000
        
        return LLMResponse(
            content=data.get("response", ""),
            model=request.model or self.config.model,
            provider=self.provider_name,
            usage={
                "prompt_tokens": data.get("prompt_eval_count", 0),
                "completion_tokens": data.get("eval_count", 0),
                "total_tokens": data.get("prompt_eval_count", 0) + data.get("eval_count", 0),
            },
            finish_reason="stop",
            latency_ms=latency,
            raw_response=data,
        )


# ========== LLM 管理器 ==========

class LLMManager:
    """LLM 管理器
    
    管理多个 LLM 提供商，支持自动切换和负载均衡。
    """
    
    def __init__(self):
        self._providers: dict[str, LLMProvider] = {}
        self._configs: dict[str, LLMConfig] = {}
        self._default_provider: Optional[str] = None
        self._logger = logging.getLogger("projmap.llm_manager")
    
    def register_provider(self, name: str, provider: LLMProvider, config: LLMConfig):
        """注册提供商"""
        self._providers[name] = provider
        self._configs[name] = config
        
        if self._default_provider is None:
            self._default_provider = name
        
        self._logger.info(f"注册 LLM 提供商: {name}")
    
    def set_default_provider(self, name: str):
        """设置默认提供商"""
        if name not in self._providers:
            raise ValueError(f"未知的提供商: {name}")
        self._default_provider = name
        self._logger.info(f"设置默认 LLM 提供商: {name}")
    
    def get_available_providers(self) -> list[str]:
        """获取所有可用的提供商"""
        return [
            name for name, provider in self._providers.items()
            if provider.is_available()
        ]
    
    def get_provider(self, name: Optional[str] = None) -> LLMProvider:
        """获取提供商实例"""
        if name is None:
            name = self._default_provider
        
        if name not in self._providers:
            raise ValueError(f"未知的提供商: {name}")
        
        return self._providers[name]
    
    async def generate(
        self,
        prompt: str,
        provider: Optional[str] = None,
        **kwargs
    ) -> LLMResponse:
        """生成文本
        
        如果指定提供商失败，会自动尝试其他可用提供商。
        """
        providers_to_try = [provider] if provider else self._get_fallback_order()
        
        last_error = None
        
        for provider_name in providers_to_try:
            if provider_name not in self._providers:
                continue
            
            provider_instance = self._providers[provider_name]
            
            if not provider_instance.is_available():
                continue
            
            try:
                request = LLMRequest(prompt=prompt, **kwargs)
                response = await provider_instance.generate(request)
                self._logger.debug(f"使用 {provider_name} 生成成功")
                return response
            except Exception as e:
                self._logger.warning(f"提供商 {provider_name} 失败: {e}")
                last_error = e
                continue
        
        raise RuntimeError(f"所有 LLM 提供商都失败: {last_error}")
    
    def _get_fallback_order(self) -> list[str]:
        """获取回退顺序"""
        # 优先使用默认提供商，然后是其他可用提供商
        order = []
        if self._default_provider:
            order.append(self._default_provider)
        
        for name in self._providers:
            if name != self._default_provider:
                order.append(name)
        
        return order
    
    def get_all_models(self) -> list[LLMModelInfo]:
        """获取所有可用模型"""
        models = []
        for name, provider in self._providers.items():
            if provider.is_available():
                try:
                    models.extend(provider.get_model_list())
                except Exception as e:
                    self._logger.warning(f"获取 {name} 模型列表失败: {e}")
        return models
    
    def estimate_cost(
        self,
        prompt_tokens: int,
        completion_tokens: int,
        model: str,
    ) -> float:
        """估算成本（美元）"""
        for name, provider in self._providers.items():
            for model_info in provider.get_model_list():
                if model_info.id == model:
                    input_cost = (prompt_tokens / 1000) * model_info.pricing_per_1k_input
                    output_cost = (completion_tokens / 1000) * model_info.pricing_per_1k_output
                    return input_cost + output_cost
        return 0.0


# ========== 便捷函数 ==========

_llm_manager: Optional[LLMManager] = None


def get_llm_manager() -> LLMManager:
    """获取全局 LLM 管理器"""
    global _llm_manager
    if _llm_manager is None:
        _llm_manager = LLMManager()
        
        # 自动注册可用的提供商
        # DeepSeek
        deepseek_config = LLMConfig(
            provider="deepseek",
            model="deepseek-chat",
        )
        deepseek = DeepSeekProvider(deepseek_config)
        if deepseek.is_available():
            _llm_manager.register_provider("deepseek", deepseek, deepseek_config)
        
        # OpenAI
        openai_config = LLMConfig(
            provider="openai",
            model="gpt-4o-mini",
        )
        openai = OpenAIProvider(openai_config)
        if openai.is_available():
            _llm_manager.register_provider("openai", openai, openai_config)
        
        # Ollama (本地)
        ollama_config = LLMConfig(
            provider="ollama",
            model="llama3.1",
        )
        ollama = OllamaProvider(ollama_config)
        if ollama.is_available():
            _llm_manager.register_provider("ollama", ollama, ollama_config)
    
    return _llm_manager
