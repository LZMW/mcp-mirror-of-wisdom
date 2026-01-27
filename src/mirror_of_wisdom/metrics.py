"""性能监控与指标收集模块

Phase 3 P2 任务：收集 LLM 调用、缓存、响应时间等关键指标
"""

import json
import logging
import time
from datetime import datetime
from pathlib import Path
from threading import Lock
from typing import Any, Literal, Optional

logger = logging.getLogger(__name__)


class MetricsCollector:
    """
    性能指标收集器

    收集的指标：
    1. LLM 调用指标：调用次数、成功率、失败率、降级率
    2. 缓存指标：命中次数、未命中次数、命中率
    3. 性能指标：响应时间（P50, P95, P99）
    4. 错误指标：错误类型分布
    """

    def __init__(self):
        """初始化指标收集器"""
        self._lock = Lock()

        # LLM 调用指标
        self.llm_calls = 0
        self.llm_successes = 0
        self.llm_failures = 0
        self.llm_fallbacks = 0  # 降级到规则引擎的次数

        # 缓存指标
        self.cache_hits = 0
        self.cache_misses = 0

        # 响应时间记录（用于计算 P50, P95, P99）
        self.llm_response_times = []  # LLM 调用响应时间
        self.cache_response_times = []  # 缓存命中响应时间
        self.total_response_times = []  # 总体响应时间

        # 错误统计
        self.error_counts = {}  # 错误类型 -> 次数

        # 专家类型使用统计
        self.expert_type_usage = {}

        # 开始时间
        self.start_time = time.time()

        logger.info("性能监控已启动")

    def record_llm_call(
        self,
        success: bool,
        response_time: float,
        error_type: Optional[str] = None,
        expert_type: Optional[str] = None
    ) -> None:
        """
        记录 LLM 调用

        Args:
            success: 是否成功
            response_time: 响应时间（秒）
            error_type: 错误类型（如果失败）
            expert_type: 专家类型
        """
        with self._lock:
            self.llm_calls += 1

            if success:
                self.llm_successes += 1
            else:
                self.llm_failures += 1
                if error_type:
                    self.error_counts[error_type] = self.error_counts.get(error_type, 0) + 1

            # 记录响应时间
            self.llm_response_times.append(response_time)
            self.total_response_times.append(response_time)

            # 记录专家类型使用
            if expert_type:
                self.expert_type_usage[expert_type] = \
                    self.expert_type_usage.get(expert_type, 0) + 1

    def record_cache_hit(self, response_time: float) -> None:
        """
        记录缓存命中

        Args:
            response_time: 缓存查询响应时间（秒）
        """
        with self._lock:
            self.cache_hits += 1
            self.cache_response_times.append(response_time)
            self.total_response_times.append(response_time)

    def record_cache_miss(self) -> None:
        """记录缓存未命中"""
        with self._lock:
            self.cache_misses += 1

    def record_fallback(self) -> None:
        """记录降级到规则引擎"""
        with self._lock:
            self.llm_fallbacks += 1

    def _calculate_percentiles(self, data: list[float]) -> dict[str, float]:
        """
        计算百分位数

        Args:
            data: 数据列表

        Returns:
            包含 P50, P95, P99 的字典
        """
        if not data:
            return {"p50": 0, "p95": 0, "p99": 0}

        sorted_data = sorted(data)
        n = len(sorted_data)

        def get_percentile(p: float) -> float:
            """获取百分位数"""
            index = int(n * p / 100)
            return sorted_data[min(index, n - 1)]

        return {
            "p50": get_percentile(50),
            "p95": get_percentile(95),
            "p99": get_percentile(99),
            "min": min(sorted_data),
            "max": max(sorted_data),
            "avg": sum(sorted_data) / n,
        }

    def get_report(self) -> dict[str, Any]:
        """
        生成性能报告

        Returns:
            包含所有指标的字典
        """
        with self._lock:
            # 计算 LLM 响应时间百分位数
            llm_percentiles = self._calculate_percentiles(self.llm_response_times)

            # 计算缓存响应时间百分位数
            cache_percentiles = self._calculate_percentiles(self.cache_response_times)

            # 计算总体响应时间百分位数
            total_percentiles = self._calculate_percentiles(self.total_response_times)

            # 计算缓存命中率
            total_cache_requests = self.cache_hits + self.cache_misses
            cache_hit_rate = (
                self.cache_hits / total_cache_requests
                if total_cache_requests > 0
                else 0
            )

            # 计算 LLM 成功率
            llm_success_rate = (
                self.llm_successes / self.llm_calls
                if self.llm_calls > 0
                else 0
            )

            # 计算降级率
            fallback_rate = (
                self.llm_fallbacks / self.llm_calls
                if self.llm_calls > 0
                else 0
            )

            # 计算运行时长
            uptime = time.time() - self.start_time

            return {
                "summary": {
                    "uptime_seconds": round(uptime, 2),
                    "uptime_formatted": self._format_uptime(uptime),
                    "total_requests": self.llm_calls + self.cache_hits,
                },
                "llm_metrics": {
                    "total_calls": self.llm_calls,
                    "successes": self.llm_successes,
                    "failures": self.llm_failures,
                    "success_rate": round(llm_success_rate * 100, 2),
                    "fallbacks": self.llm_fallbacks,
                    "fallback_rate": round(fallback_rate * 100, 2),
                    "response_times": {
                        "avg_ms": round(llm_percentiles.get("avg", 0) * 1000, 2),
                        "p50_ms": round(llm_percentiles.get("p50", 0) * 1000, 2),
                        "p95_ms": round(llm_percentiles.get("p95", 0) * 1000, 2),
                        "p99_ms": round(llm_percentiles.get("p99", 0) * 1000, 2),
                        "min_ms": round(llm_percentiles.get("min", 0) * 1000, 2),
                        "max_ms": round(llm_percentiles.get("max", 0) * 1000, 2),
                    },
                },
                "cache_metrics": {
                    "hits": self.cache_hits,
                    "misses": self.cache_misses,
                    "total_requests": total_cache_requests,
                    "hit_rate": round(cache_hit_rate * 100, 2),
                    "response_times": {
                        "avg_ms": round(cache_percentiles.get("avg", 0) * 1000, 2),
                        "p50_ms": round(cache_percentiles.get("p50", 0) * 1000, 2),
                        "p95_ms": round(cache_percentiles.get("p95", 0) * 1000, 2),
                        "p99_ms": round(cache_percentiles.get("p99", 0) * 1000, 2),
                    },
                },
                "total_metrics": {
                    "response_times": {
                        "avg_ms": round(total_percentiles.get("avg", 0) * 1000, 2),
                        "p50_ms": round(total_percentiles.get("p50", 0) * 1000, 2),
                        "p95_ms": round(total_percentiles.get("p95", 0) * 1000, 2),
                        "p99_ms": round(total_percentiles.get("p99", 0) * 1000, 2),
                    },
                },
                "error_metrics": {
                    "total_errors": sum(self.error_counts.values()),
                    "error breakdown": dict(sorted(
                        self.error_counts.items(),
                        key=lambda x: x[1],
                        reverse=True
                    )),
                },
                "expert_type_usage": dict(sorted(
                    self.expert_type_usage.items(),
                    key=lambda x: x[1],
                    reverse=True
                )),
            }

    def export_to_json(
        self,
        output_path: str | Path | None = None
    ) -> Path:
        """
        导出指标为 JSON 文件

        Args:
            output_path: 输出文件路径，默认为 .cache/metrics_report.json

        Returns:
            导出文件的路径
        """
        if output_path is None:
            output_path = Path.cwd() / ".cache" / f"metrics_report_{int(time.time())}.json"
        else:
            output_path = Path(output_path)

        # 确保目录存在
        output_path.parent.mkdir(parents=True, exist_ok=True)

        # 生成报告
        report = self.get_report()

        # 添加元数据
        report["metadata"] = {
            "generated_at": datetime.now().isoformat(),
            "version": "0.3.0",
            "phase": "Phase 3 P2",
        }

        # 写入文件
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(report, f, ensure_ascii=False, indent=2)

        logger.info(f"性能报告已导出: {output_path}")
        return output_path

    def print_report(self) -> None:
        """打印格式化的性能报告"""
        try:
            report = self.get_report()
        except Exception as e:
            logger.error(f"生成报告失败: {e}")
            return

        print("\n" + "="*60)
        print("📊 性能监控报告")
        print("="*60)

        # 摘要
        summary = report.get('summary', {})
        print(f"\n📈 摘要")
        print(f"  运行时长: {summary.get('uptime_formatted', 'N/A')}")
        print(f"  总请求数: {summary.get('total_requests', 0)}")

        # LLM 指标
        llm_metrics = report.get('llm_metrics', {})
        if llm_metrics.get('total_calls', 0) > 0:
            print(f"\n🤖 LLM 调用指标")
            print(f"  总调用次数: {llm_metrics.get('total_calls', 0)}")
            print(f"  成功: {llm_metrics.get('successes', 0)}")
            print(f"  失败: {llm_metrics.get('failures', 0)}")
            print(f"  成功率: {llm_metrics.get('success_rate', 0)}%")
            print(f"  降级次数: {llm_metrics.get('fallbacks', 0)}")
            print(f"  降级率: {llm_metrics.get('fallback_rate', 0)}%")
            response_times = llm_metrics.get('response_times', {})
            if response_times:
                print(f"  响应时间:")
                print(f"    平均: {response_times.get('avg_ms', 0)} ms")
                print(f"    P50: {response_times.get('p50_ms', 0)} ms")
                print(f"    P95: {response_times.get('p95_ms', 0)} ms")
                print(f"    P99: {response_times.get('p99_ms', 0)} ms")

        # 缓存指标
        cache_metrics = report.get('cache_metrics', {})
        if cache_metrics.get('hits', 0) > 0 or cache_metrics.get('misses', 0) > 0:
            print(f"\n💾 缓存指标")
            print(f"  命中次数: {cache_metrics.get('hits', 0)}")
            print(f"  未命中次数: {cache_metrics.get('misses', 0)}")
            print(f"  命中率: {cache_metrics.get('hit_rate', 0)}%")
            if cache_metrics.get('hits', 0) > 0:
                response_times = cache_metrics.get('response_times', {})
                if response_times:
                    print(f"  响应时间:")
                    print(f"    平均: {response_times.get('avg_ms', 0)} ms")
                    print(f"    P50: {response_times.get('p50_ms', 0)} ms")
                    print(f"    P95: {response_times.get('p95_ms', 0)} ms")

        # 总体指标
        total_metrics = report.get('total_metrics', {})
        if summary.get('total_requests', 0) > 0:
            print(f"\n⏱️  总体响应时间")
            response_times = total_metrics.get('response_times', {})
            if response_times:
                print(f"  平均: {response_times.get('avg_ms', 0)} ms")
                print(f"  P50: {response_times.get('p50_ms', 0)} ms")
                print(f"  P95: {response_times.get('p95_ms', 0)} ms")
                print(f"  P99: {response_times.get('p99_ms', 0)} ms")

        # 错误统计
        error_metrics = report.get('error_metrics', {})
        if error_metrics.get('total_errors', 0) > 0:
            print(f"\n❌ 错误统计")
            print(f"  总错误数: {error_metrics.get('total_errors', 0)}")
            error_breakdown = error_metrics.get('error breakdown', {})
            if error_breakdown:
                print(f"  错误分布:")
                for error_type, count in error_breakdown.items():
                    print(f"    {error_type}: {count}")

        # 专家类型使用
        expert_type_usage = report.get('expert_type_usage', {})
        if expert_type_usage:
            print(f"\n👥 专家类型使用")
            for expert_type, count in expert_type_usage.items():
                print(f"  {expert_type}: {count}")

        print("\n" + "="*60)

    def _format_uptime(self, seconds: float) -> str:
        """
        格式化运行时长

        Args:
            seconds: 秒数

        Returns:
            格式化后的字符串（如 1h 23m 45s）
        """
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)

        parts = []
        if hours > 0:
            parts.append(f"{hours}h")
        if minutes > 0:
            parts.append(f"{minutes}m")
        if secs > 0 or not parts:
            parts.append(f"{secs}s")

        return " ".join(parts)

    def reset(self) -> None:
        """重置所有指标"""
        with self._lock:
            self.llm_calls = 0
            self.llm_successes = 0
            self.llm_failures = 0
            self.llm_fallbacks = 0
            self.cache_hits = 0
            self.cache_misses = 0
            self.llm_response_times = []
            self.cache_response_times = []
            self.total_response_times = []
            self.error_counts = {}
            self.expert_type_usage = {}
            self.start_time = time.time()

        logger.info("性能指标已重置")


# 全局指标收集器实例
_metrics: MetricsCollector | None = None


def get_metrics() -> MetricsCollector:
    """获取指标收集器实例"""
    global _metrics
    if _metrics is None:
        _metrics = MetricsCollector()
    return _metrics


def reset_metrics():
    """重置指标收集器（主要用于测试）"""
    global _metrics
    _metrics = None
