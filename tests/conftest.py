"""
求知镜 MCP 测试配置文件

提供 Mock LLM Client 和其他测试 fixtures
"""

import asyncio
import sys
from pathlib import Path
from typing import Literal, Optional
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# 添加 src 到 Python 路径
src_path = Path(__file__).parent.parent / "src"
if str(src_path) not in sys.path:
    sys.path.insert(0, str(src_path))


# ============================================================================
# Mock LLM Client - 核心测试基础设施
# ============================================================================

class MockLLMClient:
    """
    Mock LLM 客户端

    提供稳定的、零成本的测试环境，避免真实 LLM 调用
    """

    def __init__(self):
        """初始化 Mock 客户端"""
        self.provider = "mock"
        self.call_count = 0
        self.call_history = []

        # 预定义的响应模板
        self._responses = {
            "meta_prompt_success": """# 1. 背景 (Context)
用户需要技术专家帮助优化数据库查询性能，当前订单表有5000万条数据，查询速度缓慢。

# 2. 目标 (Objective)
作为资深数据库优化专家，提供专业的SQL查询优化方案，包括索引设计、查询重写和架构优化建议。

# 3. 风格与语调 (Style & Tone)
*   **风格**: 技术严谨，数据驱动，注重实践
*   **语调**: 专业、客观、建设性

# 4. 受众 (Audience)
需要解决数据库性能问题的开发者和DBA

# 5. 响应 (Response)
## 5.1 执行步骤 (Steps)
1. 分析慢查询日志
2. 检查现有索引
3. 设计优化方案
4. 实施并验证效果

## 5.2 评估标准 (Evaluation)
- 查询响应时间降低50%以上
- 避免全表扫描
- 索引维护成本可控

## 5.3 格式与约束
- 输出格式：Markdown
- **禁止**：不建议删除数据或修改表结构的危险操作
- **排除**：不考虑更换数据库系统的方案
""",

            "chat_response": """感谢您提供的详细信息。针对订单表查询慢的问题，我建议从以下几个方面入手：

## 1. 索引优化
首先检查现有索引覆盖情况：
```sql
EXPLAIN SELECT * FROM orders WHERE user_id = ? AND created_at > ?;
```

## 2. 查询重写
避免使用 SELECT *，只查询必要字段。

需要您提供更多信息：
- 当前具体的慢查询SQL语句是什么？
- 表结构是怎样的（字段、现有索引）？
- 查询频率和数据增长速度如何？""",
        }

    async def generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        response_format: Literal["text", "json_object"] = "text",
        use_cache: bool = True,
        expert_type: Optional[str] = None,
    ) -> str:
        """
        Mock generate 方法

        根据输入返回预定义的响应，确保测试稳定性

        Args:
            prompt: 用户提示词
            system_prompt: 系统提示词（忽略）
            response_format: 响应格式（忽略）
            use_cache: 是否使用缓存（忽略）
            expert_type: 专家类型（忽略）

        Returns:
            预定义的响应内容
        """
        self.call_count += 1

        # 记录调用历史
        self.call_history.append({
            "call_count": self.call_count,
            "prompt_length": len(prompt),
            "has_system_prompt": system_prompt is not None,
            "response_format": response_format,
        })

        # 模拟异步延迟（可选，模拟真实场景）
        await asyncio.sleep(0.001)

        # 根据prompt内容返回相应响应
        if "4D 流程" in prompt or "Deconstruction" in prompt:
            # 元提示词生成请求
            return self._responses["meta_prompt_success"]
        else:
            # 普通对话请求
            return self._responses["chat_response"]

    def reset(self):
        """重置 Mock 客户端状态"""
        self.call_count = 0
        self.call_history = []

    def get_call_summary(self) -> dict:
        """获取调用摘要"""
        return {
            "total_calls": self.call_count,
            "recent_calls": self.call_history[-5:] if self.call_history else []
        }


# ============================================================================
# Pytest Fixtures
# ============================================================================

@pytest.fixture
def mock_llm_client():
    """
    Mock LLM Client fixture

    使用方法：
    ```python
    async def test_something(mock_llm_client):
        response = await mock_llm_client.generate("test prompt")
        assert response is not None
    ```
    """
    client = MockLLMClient()
    yield client
    # 清理
    client.reset()


@pytest.fixture
async def mock_llm_client_with_reset(mock_llm_client):
    """
    每次测试后自动重置的 Mock LLM Client

    适用于需要隔离状态的测试场景
    """
    yield mock_llm_client
    mock_llm_client.reset()


@pytest.fixture
def patch_llm_client():
    """
    Patch 全局 LLM Client

    使用方法：
    ```python
    async def test_with_patch(patch_llm_client):
        # 这里 get_llm_client() 会返回 Mock 实例
        from mirror_of_wisdom.llm_client import get_llm_client
        client = get_llm_client()
        assert isinstance(client, MockLLMClient)
    ```
    """
    mock_client = MockLLMClient()

    with patch("mirror_of_wisdom.llm_client.get_llm_client", return_value=mock_client):
        with patch("mirror_of_wisdom.prompt_generator.get_llm_client", return_value=mock_client):
            yield mock_client


# ============================================================================
# 测试辅助函数
# ============================================================================

def create_test_requirement(text: str = "我需要优化数据库查询性能") -> str:
    """创建测试用的需求描述"""
    return text


def create_test_message(text: str = "我的订单表有5000万条数据") -> str:
    """创建测试用的消息"""
    return text


def verify_mock_called(mock_client: MockLLMClient, expected_calls: int = 1) -> bool:
    """验证 Mock 客户端被调用指定次数"""
    return mock_client.call_count == expected_calls


# ============================================================================
# Pytest 配置
# ============================================================================

def pytest_configure(config):
    """Pytest 配置钩子"""
    config.addinivalue_line(
        "markers", "unit: 单元测试标记"
    )
    config.addinivalue_line(
        "markers", "integration: 集成测试标记"
    )
    config.addinivalue_line(
        "markers", "scenario: 场景测试标记"
    )
    config.addinivalue_line(
        "markers", "slow: 慢速测试标记"
    )


@pytest.fixture(scope="session")
def event_loop():
    """
    创建事件循环 fixture（适用于异步测试）

    Python 3.10+ 可能需要显式创建事件循环
    """
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()
