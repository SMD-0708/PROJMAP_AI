"""LLM 服务模块

支持 DeepSeek API 进行代码语义理解。
设计原则：
1. 支持多种 LLM 后端（DeepSeek、OpenAI 兼容接口）
2. 实现五档信任梯度数据脱敏
3. 提供语义标注和功能推断能力
4. 完善的错误处理和重试机制
"""

import json
import logging
import os
import re
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional
import urllib.request
import urllib.error


logger = logging.getLogger(__name__)


@dataclass
class LLMConfig:
    api_key: str
    base_url: str = "https://api.deepseek.com/v1"
    model: str = "deepseek-chat"
    max_tokens: int = 4096
    temperature: float = 0.3
    timeout: int = 60
    max_retries: int = 3
    retry_delay: float = 1.0
    retry_backoff: float = 2.0

    @classmethod
    def from_env(cls) -> "LLMConfig":
        api_key = os.environ.get("DEEPSEEK_API_KEY", os.environ.get("OPENAI_API_KEY", ""))
        base_url = os.environ.get("DEEPSEEK_BASE_URL", os.environ.get("OPENAI_BASE_URL", "https://api.deepseek.com/v1"))
        model = os.environ.get("DEEPSEEK_MODEL", os.environ.get("OPENAI_MODEL", "deepseek-chat"))
        max_retries = int(os.environ.get("PROJMAP_MAX_RETRIES", "3"))
        retry_delay = float(os.environ.get("PROJMAP_RETRY_DELAY", "1.0"))
        retry_backoff = float(os.environ.get("PROJMAP_RETRY_BACKOFF", "2.0"))
        return cls(
            api_key=api_key,
            base_url=base_url,
            model=model,
            max_retries=max_retries,
            retry_delay=retry_delay,
            retry_backoff=retry_backoff,
        )


@dataclass
class LLMResponse:
    content: str
    model: str
    usage: dict
    finish_reason: str
    latency_ms: float
    retries: int = 0


class LLMError(Exception):
    def __init__(self, message: str, code: Optional[int] = None, retryable: bool = False):
        super().__init__(message)
        self.code = code
        self.retryable = retryable


class LLMService:
    RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}
    
    def __init__(self, config: Optional[LLMConfig] = None):
        self.config = config or LLMConfig.from_env()
        self._request_count = 0
        self._total_tokens = 0

    def _make_request(self, messages: list[dict], **kwargs) -> LLMResponse:
        url = f"{self.config.base_url}/chat/completions"
        
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.config.api_key}",
        }
        
        payload = {
            "model": kwargs.get("model", self.config.model),
            "messages": messages,
            "max_tokens": kwargs.get("max_tokens", self.config.max_tokens),
            "temperature": kwargs.get("temperature", self.config.temperature),
        }
        
        last_error = None
        retries = 0
        
        for attempt in range(self.config.max_retries + 1):
            start_time = datetime.now()
            
            req = urllib.request.Request(
                url,
                data=json.dumps(payload).encode("utf-8"),
                headers=headers,
                method="POST",
            )
            
            try:
                with urllib.request.urlopen(req, timeout=self.config.timeout) as response:
                    result = json.loads(response.read().decode("utf-8"))
                
                latency_ms = (datetime.now() - start_time).total_seconds() * 1000
                
                self._request_count += 1
                if "usage" in result:
                    self._total_tokens += result["usage"].get("total_tokens", 0)
                
                return LLMResponse(
                    content=result["choices"][0]["message"]["content"],
                    model=result.get("model", self.config.model),
                    usage=result.get("usage", {}),
                    finish_reason=result["choices"][0].get("finish_reason", "stop"),
                    latency_ms=latency_ms,
                    retries=retries,
                )
                
            except urllib.error.HTTPError as e:
                error_body = ""
                try:
                    error_body = e.read().decode("utf-8") if e.fp else ""
                except Exception:
                    pass
                
                retryable = e.code in self.RETRYABLE_STATUS_CODES
                
                if retryable and attempt < self.config.max_retries:
                    delay = self.config.retry_delay * (self.config.retry_backoff ** attempt)
                    logger.warning(
                        f"LLM API error {e.code}, retrying in {delay:.1f}s "
                        f"(attempt {attempt + 1}/{self.config.max_retries})"
                    )
                    time.sleep(delay)
                    retries += 1
                    continue
                
                raise LLMError(
                    f"LLM API error: {e.code} - {error_body}",
                    code=e.code,
                    retryable=retryable,
                )
                
            except urllib.error.URLError as e:
                if attempt < self.config.max_retries:
                    delay = self.config.retry_delay * (self.config.retry_backoff ** attempt)
                    logger.warning(
                        f"LLM API connection error: {e.reason}, retrying in {delay:.1f}s"
                    )
                    time.sleep(delay)
                    retries += 1
                    continue
                
                raise LLMError(
                    f"LLM API connection error: {e.reason}",
                    retryable=True,
                )
            
            except json.JSONDecodeError as e:
                raise LLMError(f"Invalid JSON response: {e}", retryable=False)
            
            except Exception as e:
                raise LLMError(f"Unexpected error: {e}", retryable=False)
        
        raise last_error or LLMError("Max retries exceeded")

    def chat(self, system_prompt: str, user_message: str, **kwargs) -> LLMResponse:
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ]
        return self._make_request(messages, **kwargs)

    def annotate_code(
        self,
        code_info: dict,
        trust_level: int = 2,
    ) -> dict:
        system_prompt = """你是一个代码分析专家。你的任务是分析代码文件并提取以下信息：
1. 功能标签：用2-4个词描述文件的主要功能（如"数据处理"、"模型训练"、"API接口"）
2. 任务名称：给这个文件起一个简洁的任务名（不超过10个字）
3. 功能描述：用一句话描述这个文件的作用
4. 入口判断：判断这是否可能是项目的入口文件

请以JSON格式返回结果，格式如下：
{
  "function_tags": ["标签1", "标签2"],
  "task_name": "任务名",
  "description": "功能描述",
  "is_entry": false
}"""

        user_message = self._format_code_for_llm(code_info, trust_level)
        
        try:
            response = self.chat(system_prompt, user_message)
            json_match = re.search(r'\{[\s\S]*\}', response.content)
            if json_match:
                return json.loads(json_match.group())
        except Exception as e:
            logger.warning(f"LLM annotation failed: {e}")
        
        return {
            "function_tags": [],
            "task_name": code_info.get("file_name", "未知"),
            "description": "",
            "is_entry": False,
        }

    def infer_dependencies(
        self,
        file_info: dict,
        all_files: list[str],
        trust_level: int = 2,
    ) -> list[str]:
        system_prompt = """你是一个代码依赖分析专家。根据代码内容，推断这个文件可能依赖哪些其他文件。
返回一个JSON数组，包含可能的依赖文件路径。例如：["data/loader.py", "utils/helper.py"]

如果无法确定依赖关系，返回空数组 []"""

        user_message = f"""文件信息：
{self._format_code_for_llm(file_info, trust_level)}

项目中所有文件：
{json.dumps(all_files[:50], ensure_ascii=False)}

请推断这个文件依赖哪些其他文件？"""

        try:
            response = self.chat(system_prompt, user_message)
            json_match = re.search(r'\[[\s\S]*?\]', response.content)
            if json_match:
                return json.loads(json_match.group())
        except Exception as e:
            logger.warning(f"LLM dependency inference failed: {e}")
        
        return []

    def _format_code_for_llm(self, code_info: dict, trust_level: int) -> str:
        parts = []
        
        if trust_level >= 1:
            parts.append(f"文件路径: {code_info.get('file_path', 'N/A')}")
            parts.append(f"文件名: {code_info.get('file_name', 'N/A')}")
        
        if trust_level >= 2:
            parts.append(f"语言: {code_info.get('language', 'N/A')}")
            if code_info.get("imports"):
                parts.append(f"导入: {json.dumps(code_info['imports'], ensure_ascii=False)}")
            if code_info.get("exports"):
                parts.append(f"导出: {json.dumps(code_info['exports'], ensure_ascii=False)}")
        
        if trust_level >= 3 and code_info.get("comments"):
            parts.append(f"注释:\n{code_info['comments']}")
        
        if trust_level >= 4 and code_info.get("parameters"):
            parts.append(f"关键参数:\n{json.dumps(code_info['parameters'], ensure_ascii=False, indent=2)}")
        
        if trust_level >= 5 and code_info.get("code_structure"):
            parts.append(f"代码结构:\n{code_info['code_structure']}")
        
        return "\n".join(parts)
    
    def get_stats(self) -> dict:
        return {
            "request_count": self._request_count,
            "total_tokens": self._total_tokens,
        }


def create_llm_service(api_key: Optional[str] = None) -> LLMService:
    if api_key:
        config = LLMConfig(api_key=api_key)
    else:
        config = LLMConfig.from_env()
    return LLMService(config)
