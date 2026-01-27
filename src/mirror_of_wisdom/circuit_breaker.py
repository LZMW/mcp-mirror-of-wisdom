"""熔断器模块 - Phase 3 P2 任务

实现熔断器模式，防止级联故障
"""

import asyncio
import logging
from enum import Enum
from threading import Lock
from time import time
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)


class CircuitState(Enum):
    """熔断器状态"""
    CLOSED = "closed"       # 关闭状态：正常工作
    OPEN = "open"           # 开启状态：熔断中，拒绝请求
    HALF_OPEN = "half_open"  # 半开状态：尝试恢复


class CircuitBreakerError(Exception):
    """熔断器异常：熔断器开启，请求被拒绝"""
    pass


class CircuitBreaker:
    """
    熔断器

    状态机转换：
    CLOSED → OPEN: 失败次数达到阈值
    OPEN → HALF_OPEN: 超时后进入半开状态
    HALF_OPEN → CLOSED: 探测成功，恢复正常
    HALF_OPEN → OPEN: 探测失败，重新熔断
    """

    def __init__(
        self,
        failure_threshold: int = 5,
        timeout: float = 60.0,
        success_threshold: int = 2
    ):
        """
        初始化熔断器

        Args:
            failure_threshold: 失败次数阈值（默认 5 次）
            timeout: 熔断超时时间（秒，默认 60 秒）
            success_threshold: 半开状态成功次数阈值（默认 2 次）
        """
        self.failure_threshold = failure_threshold
        self.timeout = timeout
        self.success_threshold = success_threshold

        # 状态
        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._success_count = 0
        self._last_failure_time: Optional[float] = None
        self._lock = Lock()

        logger.info(
            f"熔断器初始化: failure_threshold={failure_threshold}, "
            f"timeout={timeout}s, success_threshold={success_threshold}"
        )

    @property
    def state(self) -> CircuitState:
        """获取当前状态"""
        return self._state

    def _can_attempt_reset(self) -> bool:
        """
        检查是否可以尝试重置熔断器

        Returns:
            如果超时时间已过，返回 True
        """
        if self._last_failure_time is None:
            return False

        return (time() - self._last_failure_time) >= self.timeout

    def record_success(self) -> None:
        """记录成功调用"""
        with self._lock:
            if self._state == CircuitState.HALF_OPEN:
                self._success_count += 1
                logger.info(
                    f"熔断器 [HALF_OPEN] 成功计数: {self._success_count}/"
                    f"{self.success_threshold}"
                )

                # 半开状态下，成功次数达到阈值，切换到关闭状态
                if self._success_count >= self.success_threshold:
                    self._state = CircuitState.CLOSED
                    self._failure_count = 0
                    self._success_count = 0
                    self._last_failure_time = None
                    logger.info("🔧 熔断器 [HALF_OPEN → CLOSED] 已恢复正常")
            else:
                # 关闭状态下，重置失败计数
                self._failure_count = 0

    def record_failure(self) -> None:
        """记录失败调用"""
        with self._lock:
            self._failure_count += 1
            self._last_failure_time = time()

            if self._state == CircuitState.HALF_OPEN:
                # 半开状态下失败，立即回到开启状态
                self._state = CircuitState.OPEN
                self._success_count = 0
                logger.warning("⚠️ 熔断器 [HALF_OPEN → OPEN] 探测失败，重新熔断")
            elif self._failure_count >= self.failure_threshold:
                # 失败次数达到阈值，切换到开启状态
                if self._state != CircuitState.OPEN:
                    self._state = CircuitState.OPEN
                    logger.warning(
                        f"🚨 熔断器 [CLOSED → OPEN] 失败次数达到阈值 "
                        f"({self._failure_count}/{self.failure_threshold})"
                    )

    def call(self, func: Callable[[], Any]) -> Any:
        """
        同步调用保护

        Args:
            func: 要保护的函数

        Returns:
            函数执行结果

        Raises:
            CircuitBreakerError: 熔断器开启时抛出
        """
        # 检查熔断器状态
        if self._state == CircuitState.OPEN:
            if self._can_attempt_reset():
                # 超时后进入半开状态
                with self._lock:
                    if self._state == CircuitState.OPEN:  # 双重检查
                        self._state = CircuitState.HALF_OPEN
                        self._success_count = 0
                        logger.info("🔧 熔断器 [OPEN → HALF_OPEN] 尝试恢复")
            else:
                # 熔断中，拒绝请求
                raise CircuitBreakerError(
                    f"熔断器开启，请求被拒绝（将在 {self.timeout - (time() - self._last_failure_time):.1f}s 后尝试恢复）"
                )

        try:
            # 执行函数
            result = func()
            self.record_success()
            return result
        except Exception as e:
            self.record_failure()
            raise e

    async def call_async(self, func: Callable[[], Any]) -> Any:
        """
        异步调用保护

        Args:
            func: 要保护的异步函数

        Returns:
            函数执行结果

        Raises:
            CircuitBreakerError: 熔断器开启时抛出
        """
        # 检查熔断器状态
        if self._state == CircuitState.OPEN:
            if self._can_attempt_reset():
                # 超时后进入半开状态
                with self._lock:
                    if self._state == CircuitState.OPEN:  # 双重检查
                        self._state = CircuitState.HALF_OPEN
                        self._success_count = 0
                        logger.info("🔧 熔断器 [OPEN → HALF_OPEN] 尝试恢复")
            else:
                # 熔断中，拒绝请求
                raise CircuitBreakerError(
                    f"熔断器开启，请求被拒绝（将在 {self.timeout - (time() - self._last_failure_time):.1f}s 后尝试恢复）"
                )

        try:
            # 执行异步函数
            if asyncio.iscoroutinefunction(func):
                result = await func()
            else:
                result = func()

            self.record_success()
            return result
        except Exception as e:
            self.record_failure()
            raise e

    def get_state_info(self) -> dict[str, Any]:
        """
        获取熔断器状态信息

        Returns:
            包含状态信息的字典
        """
        with self._lock:
            remaining_time = 0
            if self._state == CircuitState.OPEN and self._last_failure_time:
                remaining_time = max(0, self.timeout - (time() - self._last_failure_time))

            return {
                "state": self._state.value,
                "failure_count": self._failure_count,
                "failure_threshold": self.failure_threshold,
                "success_count": self._success_count,
                "success_threshold": self.success_threshold,
                "last_failure_time": self._last_failure_time,
                "remaining_time_until_half_open": round(remaining_time, 2),
            }

    def reset(self) -> None:
        """重置熔断器"""
        with self._lock:
            self._state = CircuitState.CLOSED
            self._failure_count = 0
            self._success_count = 0
            self._last_failure_time = None
            logger.info("🔧 熔断器已重置")


# 全局熔断器实例
_circuit_breaker: CircuitBreaker | None = None


def get_circuit_breaker(
    failure_threshold: int = 5,
    timeout: float = 60.0,
    success_threshold: int = 2
) -> CircuitBreaker:
    """
    获取熔断器实例

    Args:
        failure_threshold: 失败次数阈值
        timeout: 熔断超时时间（秒）
        success_threshold: 半开状态成功次数阈值

    Returns:
        熔断器实例
    """
    global _circuit_breaker
    if _circuit_breaker is None:
        _circuit_breaker = CircuitBreaker(
            failure_threshold=failure_threshold,
            timeout=timeout,
            success_threshold=success_threshold
        )
    return _circuit_breaker


def reset_circuit_breaker():
    """重置熔断器（主要用于测试）"""
    global _circuit_breaker
    _circuit_breaker = None
