"""LLM 客户端模块 - 支持多种 AI 提供商

Phase 3 优化：
- 集成持久化缓存（规避 13s LLM 推理时间）
- 异步非阻塞（避免长耗时推理期间服务假死）
- 精细化重试策略（禁止对 Timeout 重试，仅对 ConnectionError/5xx 重试）
- 性能监控（收集 LLM 调用、缓存、响应时间等指标）
- 熔断器保护（防止级联故障）
"""

import asyncio
import logging
import time
from typing import Literal

from .config import get_mirror_config
from .llm_cache import get_llm_cache
from .metrics import get_metrics
from .circuit_breaker import get_circuit_breaker, CircuitBreakerError

# 导入 httpx 异常类型（用于精细化重试判断）
try:
    from httpx import TimeoutException, ConnectError
    HTTPX_AVAILABLE = True
except ImportError:
    HTTPX_AVAILABLE = False
    TimeoutException = None
    ConnectError = None

logger = logging.getLogger(__name__)


class MirrorLLMClient:
    """求知镜 LLM 客户端"""

    def __init__(self, provider: str | None = None):
        """
        初始化 LLM 客户端

        Args:
            provider: AI 服务提供商，默认从配置读取
        """
        config = get_mirror_config()
        self.provider = provider or config.provider
        self.config = config

        # 初始化对应提供商的客户端
        if self.provider == "openai":
            self._init_openai()
        elif self.provider == "anthropic":
            self._init_anthropic()
        elif self.provider == "zhipu":
            self._init_zhipu()
        elif self.provider == "gemini":
            self._init_gemini()
        elif self.provider == "custom":
            self._init_custom()
        else:
            raise ValueError(f"不支持的 AI 提供商: {self.provider}")

    def _init_openai(self):
        """初始化 OpenAI 客户端"""
        if not self.config.api_key:
            raise ValueError("未设置 MIRROR_API_KEY 环境变量")

        from openai import OpenAI
        import httpx

        # 创建带有超时配置的 HTTP 客户端
        http_client = httpx.Client(
            timeout=httpx.Timeout(self.config.timeout, connect=self.config.timeout)
        )

        # 如果有自定义 base_url，使用它；否则使用默认
        kwargs = {
            "api_key": self.config.api_key,
            "http_client": http_client
        }
        if self.config.base_url:
            kwargs["base_url"] = self.config.base_url

        self._client = OpenAI(**kwargs)
        logger.info(
            f"OpenAI 客户端已初始化，模型: {self.config.model}，"
            f"超时: {self.config.timeout}s，重试: {self.config.max_retries} 次"
        )

    def _init_anthropic(self):
        """初始化 Anthropic 客户端"""
        if not self.config.api_key:
            raise ValueError("未设置 MIRROR_API_KEY 环境变量")

        from anthropic import Anthropic

        self._client = Anthropic(
            api_key=self.config.api_key,
            timeout=self.config.timeout
        )
        logger.info(
            f"Anthropic 客户端已初始化，模型: {self.config.model}，"
            f"超时: {self.config.timeout}s"
        )

    def _init_zhipu(self):
        """初始化智谱 AI 客户端"""
        if not self.config.api_key:
            raise ValueError("未设置 MIRROR_API_KEY 环境变量")

        from zhipuai import ZhipuAI

        self._client = ZhipuAI(api_key=self.config.api_key)
        logger.info(f"智谱 AI 客户端已初始化，模型: {self.config.model}")

    def _init_gemini(self):
        """初始化 Google Gemini 客户端"""
        if not self.config.api_key:
            raise ValueError("未设置 MIRROR_API_KEY 环境变量")

        import google.generativeai as genai

        genai.configure(api_key=self.config.api_key)
        self._genai = genai
        logger.info(f"Gemini 客户端已初始化，模型: {self.config.model}")

    def _init_custom(self):
        """初始化自定义 OpenAI 兼容客户端"""
        if not self.config.api_key:
            raise ValueError("未设置 MIRROR_API_KEY 环境变量")
        if not self.config.base_url:
            raise ValueError("自定义提供商必须设置 MIRROR_BASE_URL 环境变量")

        from openai import OpenAI
        import httpx

        # 创建带有超时配置的 HTTP 客户端
        http_client = httpx.Client(
            timeout=httpx.Timeout(self.config.timeout, connect=self.config.timeout)
        )

        self._client = OpenAI(
            api_key=self.config.api_key,
            base_url=self.config.base_url,
            http_client=http_client
        )
        logger.info(
            f"自定义 OpenAI 兼容客户端已初始化，Base URL: {self.config.base_url}，"
            f"模型: {self.config.model}，超时: {self.config.timeout}s"
        )

    async def generate(
        self,
        prompt: str,
        system_prompt: str | None = None,
        response_format: Literal["text", "json_object"] = "text",
        use_cache: bool = True,
        expert_type: str | None = None,
    ) -> str:
        """
        生成文本（Phase 3 优化：集成缓存、性能监控、熔断器）

        Args:
            prompt: 用户提示词
            system_prompt: 系统提示词（可选）
            response_format: 响应格式（text 或 json_object）
            use_cache: 是否使用缓存（默认 True）
            expert_type: 专家类型（用于性能监控）

        Returns:
            生成的文本
        """
        metrics = get_metrics()
        start_time = time.time()

        # Phase 3 P2: 检查缓存（P0 优化：规避 13s 推理时间）
        cache = get_llm_cache()
        cache_key_suffix = f"|format:{response_format}"

        if use_cache:
            cache_start = time.time()
            cached_response = cache.get(prompt + cache_key_suffix, system_prompt)
            cache_duration = time.time() - cache_start

            if cached_response is not None:
                logger.info("缓存命中，跳过 LLM 调用")
                # Phase 3 P2: 记录缓存命中
                metrics.record_cache_hit(cache_duration)
                return cached_response
            else:
                logger.debug("缓存未命中，调用 LLM")
                metrics.record_cache_miss()

        # Phase 3 P2: 熔断器保护
        circuit_breaker = get_circuit_breaker()

        async def _do_llm_call() -> str:
            """执行 LLM 调用的内部函数"""
            # 带重试的请求
            last_error = None
            for attempt in range(self.config.max_retries + 1):
                try:
                    if self.provider in ["openai", "custom"]:
                        response = await self._generate_openai(prompt, system_prompt, response_format)
                    elif self.provider == "anthropic":
                        response = await self._generate_anthropic(prompt, system_prompt, response_format)
                    elif self.provider == "zhipu":
                        response = await self._generate_zhipu(prompt, system_prompt, response_format)
                    elif self.provider == "gemini":
                        response = await self._generate_gemini(prompt, system_prompt, response_format)
                    else:
                        raise ValueError(f"不支持的 provider: {self.provider}")

                    # Phase 3 P0: 保存到缓存
                    if use_cache:
                        cache.set(prompt + cache_key_suffix, response, system_prompt)
                        logger.info("响应已保存到缓存")

                    return response

                except Exception as e:
                    last_error = e

                    # Phase 3 P1: 精细化重试策略
                    should_retry = False
                    error_type = type(e).__name__

                    # 禁止对 Timeout 重试（避免服务端积压）
                    is_timeout = (
                        "timeout" in error_type.lower() or
                        "timed out" in str(e).lower() or
                        (HTTPX_AVAILABLE and isinstance(e, TimeoutException))
                    )

                    # 仅对 ConnectionError 和 HTTP 5xx 重试
                    is_retryable = (
                        (HTTPX_AVAILABLE and isinstance(e, ConnectError)) or
                        "ConnectionError" in error_type or
                        "connect" in str(e).lower() or
                        "5" in str(e)  # HTTP 5xx 错误
                    )

                    if is_timeout:
                        # 超时错误不重试，直接抛出
                        logger.warning(f"请求超时（不重试，避免服务端积压）: {e}")
                        raise

                    elif is_retryable:
                        # 可重试的错误
                        should_retry = True

                    # 其他错误也尝试重试（保持兼容性）
                    else:
                        should_retry = True

                    # 执行重试
                    if should_retry and attempt < self.config.max_retries:
                        logger.warning(
                            f"请求失败（尝试 {attempt + 1}/{self.config.max_retries + 1}）: {e}，"
                            f"{self.config.retry_delay} 秒后重试..."
                        )
                        # 使用异步睡眠，避免阻塞事件循环（P0 修复：长耗时推理期间服务假死）
                        await asyncio.sleep(self.config.retry_delay)
                    else:
                        logger.error(f"请求失败，已达最大重试次数: {e}")
                        break

            # 所有重试都失败
            raise Exception(f"LLM 请求失败: {last_error}")

        # 使用熔断器保护 LLM 调用
        try:
            response = await circuit_breaker.call_async(_do_llm_call)

            # Phase 3 P2: 记录成功调用
            response_time = time.time() - start_time
            metrics.record_llm_call(
                success=True,
                response_time=response_time,
                expert_type=expert_type
            )

            return response

        except CircuitBreakerError as e:
            # 熔断器开启，记录失败
            logger.error(f"熔断器错误: {e}")
            response_time = time.time() - start_time
            metrics.record_llm_call(
                success=False,
                response_time=response_time,
                error_type="CircuitBreakerError",
                expert_type=expert_type
            )
            raise

        except Exception as e:
            # LLM 调用失败，记录失败
            error_type = type(e).__name__
            response_time = time.time() - start_time
            metrics.record_llm_call(
                success=False,
                response_time=response_time,
                error_type=error_type,
                expert_type=expert_type
            )

            # 熔断器记录失败
            circuit_breaker.record_failure()
            raise

    async def chat(
        self,
        messages: list[dict],
        response_format: Literal["text", "json_object"] = "text",
        use_cache: bool = False,  # 聊天模式默认不使用缓存
        expert_type: str | None = None,
    ) -> str:
        """
        多轮对话（Phase 6 新增：支持传递对话历史）

        与 generate() 的区别：
        - generate(): 单轮对话，只接受 prompt + system_prompt
        - chat(): 多轮对话，接受完整的 messages 数组

        Args:
            messages: 消息数组，格式：[{"role": "user/assistant/system", "content": "..."}, ...]
            response_format: 响应格式（text 或 json_object）
            use_cache: 是否使用缓存（默认 False，因为对话历史动态变化）
            expert_type: 专家类型（用于性能监控）

        Returns:
            生成的文本

        Example:
            >>> messages = [
            ...     {"role": "system", "content": "你是专家..."},
            ...     {"role": "user", "content": "第1轮"},
            ...     {"role": "assistant", "content": "回复1"},
            ...     {"role": "user", "content": "第2轮"}
            ... ]
            >>> response = await llm_client.chat(messages)
        """
        metrics = get_metrics()
        start_time = time.time()

        # Phase 6: 聊天模式禁用缓存（因为对话历史动态变化）
        if use_cache:
            logger.warning("⚠️ 聊天模式建议禁用缓存（当前已启用）")

        # Phase 3 P2: 熔断器保护
        circuit_breaker = get_circuit_breaker()

        async def _do_llm_call() -> str:
            """执行 LLM 调用的内部函数"""
            # 带重试的请求
            last_error = None
            for attempt in range(self.config.max_retries + 1):
                try:
                    if self.provider in ["openai", "custom"]:
                        response = await self._chat_openai(messages, response_format)
                    elif self.provider == "anthropic":
                        response = await self._chat_anthropic(messages, response_format)
                    elif self.provider == "zhipu":
                        response = await self._chat_zhipu(messages, response_format)
                    elif self.provider == "gemini":
                        response = await self._chat_gemini(messages, response_format)
                    else:
                        raise ValueError(f"不支持的 provider: {self.provider}")

                    return response

                except Exception as e:
                    last_error = e

                    # Phase 3 P1: 精细化重试策略
                    should_retry = False
                    error_type = type(e).__name__

                    # 禁止对 Timeout 重试
                    is_timeout = (
                        "timeout" in error_type.lower() or
                        "timed out" in str(e).lower() or
                        (HTTPX_AVAILABLE and isinstance(e, TimeoutException))
                    )

                    # 仅对 ConnectionError 和 HTTP 5xx 重试
                    is_retryable = (
                        (HTTPX_AVAILABLE and isinstance(e, ConnectError)) or
                        "ConnectionError" in error_type or
                        "connect" in str(e).lower() or
                        "5" in str(e)
                    )

                    if is_timeout:
                        logger.warning(f"⏱️ 请求超时（不重试）: {e}")
                        raise
                    elif is_retryable:
                        should_retry = True
                    else:
                        should_retry = True

                    if should_retry and attempt < self.config.max_retries:
                        logger.warning(
                            f"请求失败（尝试 {attempt + 1}/{self.config.max_retries + 1}）: {e}，"
                            f"{self.config.retry_delay} 秒后重试..."
                        )
                        await asyncio.sleep(self.config.retry_delay)
                    else:
                        logger.error(f"请求失败，已达最大重试次数: {e}")
                        break

            raise Exception(f"LLM 请求失败: {last_error}")

        # 使用熔断器保护 LLM 调用
        try:
            response = await circuit_breaker.call_async(_do_llm_call)

            # 记录成功调用
            response_time = time.time() - start_time
            metrics.record_llm_call(
                success=True,
                response_time=response_time,
                expert_type=expert_type
            )

            return response

        except CircuitBreakerError as e:
            logger.error(f"🚨 {e}")
            response_time = time.time() - start_time
            metrics.record_llm_call(
                success=False,
                response_time=response_time,
                error_type="CircuitBreakerError",
                expert_type=expert_type
            )
            raise

        except Exception as e:
            error_type = type(e).__name__
            response_time = time.time() - start_time
            metrics.record_llm_call(
                success=False,
                response_time=response_time,
                error_type=error_type,
                expert_type=expert_type
            )

            circuit_breaker.record_failure()
            raise

    async def _generate_openai(
        self,
        prompt: str,
        system_prompt: str | None = None,
        response_format: Literal["text", "json_object"] = "text",
    ) -> str:
        """使用 OpenAI 或兼容 API 生成文本"""
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        logger.info(f"发送请求到 {self.provider}，消息数: {len(messages)}")

        # 构建请求参数
        kwargs = {
            "model": self.config.model,
            "messages": messages,
            "temperature": self.config.temperature,
            "max_tokens": self.config.max_tokens,
        }

        # 如果需要 JSON 格式
        if response_format == "json_object":
            kwargs["response_format"] = {"type": "json_object"}

        response = self._client.chat.completions.create(**kwargs)
        content = response.choices[0].message.content
        logger.info(f"收到响应，长度: {len(content)}")

        return content

    async def _generate_anthropic(
        self,
        prompt: str,
        system_prompt: str | None = None,
        response_format: Literal["text", "json_object"] = "text",
    ) -> str:
        """使用 Anthropic API 生成文本"""
        messages = [{"role": "user", "content": prompt}]

        # Anthropic 要求 max_tokens 在 1-8192 之间
        max_tokens = min(self.config.max_tokens, 8192)

        logger.info(f"发送请求到 Anthropic，模型: {self.config.model}")

        kwargs = {
            "model": self.config.model,
            "max_tokens": max_tokens,
            "temperature": self.config.temperature,
            "messages": messages,
        }

        if system_prompt:
            kwargs["system"] = system_prompt

        response = self._client.messages.create(**kwargs)

        # 提取文本内容
        content = ""
        for block in response.content:
            if block.type == "text":
                content += block.text

        logger.info(f"收到响应，长度: {len(content)}")
        return content

    async def _generate_zhipu(
        self,
        prompt: str,
        system_prompt: str | None = None,
        response_format: Literal["text", "json_object"] = "text",
    ) -> str:
        """使用智谱 AI 生成文本"""
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        logger.info(f"发送请求到智谱 AI，消息数: {len(messages)}")

        response = self._client.chat.completions.create(
            model=self.config.model,
            messages=messages,
            temperature=self.config.temperature,
            max_tokens=self.config.max_tokens,
        )

        content = response.choices[0].message.content
        logger.info(f"收到响应，长度: {len(content)}")

        return content

    async def _generate_gemini(
        self,
        prompt: str,
        system_prompt: str | None = None,
        response_format: Literal["text", "json_object"] = "text",
    ) -> str:
        """使用 Google Gemini 生成文本"""
        import google.generativeai as genai

        # 构建完整提示词
        full_prompt = f"{system_prompt or ''}\n\n{prompt}".strip()

        logger.info(f"发送请求到 Gemini，模型: {self.config.model}")

        model = self._genai.GenerativeModel(self.config.model)
        response = await model.generate_content_async(full_prompt)
        content = response.text

        logger.info(f"收到响应，长度: {len(content)}")
        return content


# 全局客户端实例
_client: MirrorLLMClient | None = None


def get_llm_client() -> MirrorLLMClient:
    """获取 LLM 客户端实例"""
    global _client
    if _client is None:
        _client = MirrorLLMClient()
    return _client


def reset_client():
    """重置客户端（主要用于测试）"""
    global _client
    _client = None
