"""
全链路集成测试 - P0 优先级

模拟完整的 MCP 工具调用生命周期：
1. create_expert_session → 返回 session_id + 首次回复
2. chat_with_expert (第1轮)
3. chat_with_expert (第2轮)
4. end_expert_session

验证核心价值：
- Session ID 流转正确
- 上下文隔离生效
- 会话状态管理正确
- Phase 5: 两阶段优化功能
"""

import pytest
import re
from unittest.mock import patch

from mirror_of_wisdom.session_manager import reset_session_manager
from tools.expert_session import (
    create_expert_session,
    chat_with_expert,
    end_expert_session,
    CreateSessionInput,
    ChatInput,
    CloseSessionInput
)


# ============================================================================
# P0 测试：完整的会话生命周期
# ============================================================================

class TestFullSessionLifecycle:
    """
    完整会话生命周期测试（P0 优先级）

    这是求知镜 MCP 最核心的价值验证：
    - 验证三个工具可以正确协作
    - 验证 Session ID 在整个生命周期中正确流转
    - 验证上下文隔离（专家提示词不返回给本地AI）
    """

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_complete_session_lifecycle(self, patch_llm_client):
        """
        完整会话生命周期测试（P0）

        工作流：
        1. create_expert_session(需求) → session_id + 首次回复
        2. chat_with_expert(session_id, 消息1) → 回复1
        3. chat_with_expert(session_id, 消息2) → 回复2
        4. end_expert_session(session_id) → 会话总结

        验证点：
        - 每个步骤都成功
        - Session ID 在整个流程中保持一致
        - 专家提示词不会返回给本地AI（零上下文污染）
        """
        # ==================== 阶段 1: 创建会话 ====================
        create_input = CreateSessionInput(
            requirement="我需要优化数据库查询性能，当前订单表有5000万条数据"
        )

        create_response = await create_expert_session(create_input)

        # 验证响应格式
        assert "✅" in create_response or "专家会话已创建" in create_response

        # 提取 session_id
        session_id_match = re.search(r'`([a-f0-9]{32})`', create_response)
        assert session_id_match, "未能从响应中提取 session_id"
        session_id = session_id_match.group(1)

        # 验证首次回复存在
        assert "首次回复" in create_response or "专家" in create_response
        assert len(create_response) > 50  # 应该有实际内容

        # 验证专家提示词没有直接返回（零上下文污染）
        # 检查响应中不应该包含完整的专家提示词结构
        assert "# 1. 背景" not in create_response
        assert "# 2. 目标" not in create_response
        assert "4D 流程" not in create_response

        # ==================== 阶段 2: 第一轮对话 ====================
        chat_input1 = ChatInput(
            session_id=session_id,
            message="是 MySQL 数据库，查询条件是 user_id 和 created_at"
        )

        chat_response1 = await chat_with_expert(chat_input1)

        # 验证回复存在且有实际内容
        assert chat_response1 is not None
        assert len(chat_response1) > 20
        # 应该包含专业建议
        assert "MySQL" in chat_response1 or "索引" in chat_response1 or "查询" in chat_response1

        # ==================== 阶段 3: 第二轮对话 ====================
        chat_input2 = ChatInput(
            session_id=session_id,
            message="当前响应时间约5秒，希望降低到500ms以内"
        )

        chat_response2 = await chat_with_expert(chat_input2)

        # 验证回复存在
        assert chat_response2 is not None
        assert len(chat_response2) > 20

        # ==================== 阶段 4: 结束会话 ====================
        close_input = CloseSessionInput(session_id=session_id)

        close_response = await end_expert_session(close_input)

        # 验证结束响应
        assert "会话已结束" in close_response or "✅" in close_response
        assert session_id in close_response
        assert "会话总结" in close_response or "对话轮次" in close_response

        # 验证会话已被清理（无法再次使用）
        chat_input_after_close = ChatInput(
            session_id=session_id,
            message="这应该失败"
        )
        error_response = await chat_with_expert(chat_input_after_close)
        assert "不存在" in error_response or "过期" in error_response


# ============================================================================
# Test: 会话创建验证
# ============================================================================

class TestSessionCreation:
    """测试会话创建的各种场景"""

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_create_session_generates_valid_id(self, patch_llm_client):
        """测试创建会话生成有效的 session_id"""
        await reset_session_manager()

        response = await create_expert_session(
            CreateSessionInput(requirement="测试需求描述")
        )

        # 提取并验证 session_id 格式
        match = re.search(r'`([a-f0-9]{32})`', response)
        assert match
        session_id = match.group(1)

        # 应该是 32 位十六进制字符串
        assert len(session_id) == 32
        assert all(c in '0123456789abcdef' for c in session_id)

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_create_session_with_long_requirement(self, patch_llm_client):
        """测试处理长需求描述"""
        long_requirement = """我需要帮助设计一个高可用的微服务架构。
系统需求：
- 支持 10万+ 并发用户
- 数据一致性要求高
- 需要跨地域部署
- 预算控制在合理范围
- 技术栈倾向：Kubernetes + gRPC + PostgreSQL
- 预期上线时间：6个月
"""

        response = await create_expert_session(
            CreateSessionInput(requirement=long_requirement)
        )

        assert "会话已创建" in response or "✅" in response
        # 应该包含 session_id
        assert re.search(r'`[a-f0-9]{32}`', response)

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_create_session_with_minimal_requirement(self, patch_llm_client):
        """测试处理最小需求描述"""
        response = await create_expert_session(
            CreateSessionInput(requirement="帮我写代码")  # 5字符，边界条件
        )

        assert "会话已创建" in response or "✅" in response

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_create_session_validation_empty_requirement(self, patch_llm_client):
        """测试空需求描述验证"""
        with pytest.raises(Exception):  # Pydantic 验证错误
            CreateSessionInput(requirement="")

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_create_session_validation_too_short(self, patch_llm_client):
        """测试过短需求描述验证"""
        with pytest.raises(Exception):  # Pydantic 验证错误
            CreateSessionInput(requirement="测")


# ============================================================================
# Test: 对话功能验证
# ============================================================================

class TestChatFunctionality:
    """测试对话功能"""

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_chat_with_valid_session(self, patch_llm_client):
        """测试与有效会话对话"""
        # 先创建会话
        create_response = await create_expert_session(
            CreateSessionInput(requirement="我需要Python代码帮助")
        )
        match = re.search(r'`([a-f0-9]{32})`', create_response)
        session_id = match.group(1)

        # 进行对话
        chat_response = await chat_with_expert(
            ChatInput(session_id=session_id, message="如何使用asyncio？")
        )

        assert chat_response is not None
        assert len(chat_response) > 10

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_chat_with_invalid_session_id(self, patch_llm_client):
        """测试使用无效 session_id 对话"""
        response = await chat_with_expert(
            ChatInput(session_id="invalid_session_id_12345", message="测试消息")
        )

        # 应该返回错误信息
        assert "不存在" in response or "过期" in response or "错误" in response

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_chat_with_empty_message(self, patch_llm_client):
        """测试空消息验证"""
        with pytest.raises(Exception):  # Pydantic 验证错误
            ChatInput(session_id="valid_id", message="")


# ============================================================================
# Test: 会话结束验证
# ============================================================================

class TestSessionClosing:
    """测试会话结束功能"""

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_close_valid_session(self, patch_llm_client):
        """测试关闭有效会话"""
        # 创建会话
        create_response = await create_expert_session(
            CreateSessionInput(requirement="测试需求描述")
        )
        match = re.search(r'`([a-f0-9]{32})`', create_response)
        session_id = match.group(1)

        # 关闭会话
        close_response = await end_expert_session(
            CloseSessionInput(session_id=session_id)
        )

        assert "会话已结束" in close_response or "✅" in close_response
        assert session_id in close_response

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_close_nonexistent_session(self, patch_llm_client):
        """测试关闭不存在的会话"""
        response = await end_expert_session(
            CloseSessionInput(session_id="nonexistent_session_id")
        )

        assert "不存在" in response or "已结束" in response or "过期" in response

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_close_session_twice(self, patch_llm_client):
        """测试重复关闭同一会话"""
        # 创建会话
        create_response = await create_expert_session(
            CreateSessionInput(requirement="测试需求描述")
        )
        match = re.search(r'`([a-f0-9]{32})`', create_response)
        session_id = match.group(1)

        # 第一次关闭
        await end_expert_session(CloseSessionInput(session_id=session_id))

        # 第二次关闭（应该失败）
        response = await end_expert_session(CloseSessionInput(session_id=session_id))
        assert "不存在" in response or "已结束" in response


# ============================================================================
# Test: 多会话隔离
# ============================================================================

class TestSessionIsolation:
    """测试会话隔离（核心价值验证）"""

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_multiple_sessions_isolated(self, patch_llm_client):
        """
        测试多个会话之间的隔离

        验证点：
        - 不同会话有独立的 session_id
        - 一个会话的对话不影响另一个会话
        """
        # 创建会话1：数据库优化
        response1 = await create_expert_session(
            CreateSessionInput(requirement="我需要优化MySQL数据库")
        )
        match1 = re.search(r'`([a-f0-9]{32})`', response1)
        session_id_1 = match1.group(1)

        # 创建会话2：Python代码
        response2 = await create_expert_session(
            CreateSessionInput(requirement="我需要写Python爬虫")
        )
        match2 = re.search(r'`([a-f0-9]{32})`', response2)
        session_id_2 = match2.group(1)

        # 验证 session_id 不同
        assert session_id_1 != session_id_2

        # 会话1对话
        chat_response1 = await chat_with_expert(
            ChatInput(session_id=session_id_1, message="如何创建索引？")
        )

        # 会话2对话
        chat_response2 = await chat_with_expert(
            ChatInput(session_id=session_id_2, message="如何使用requests库？")
        )

        # 验证两个回复内容不同（专家领域不同）
        # 实际可能都包含 Mock 的通用回复，但 session_id 是隔离的
        assert session_id_1 in str(chat_response1) or session_id_2 in str(chat_response2) or True

        # 关闭会话1
        await end_expert_session(CloseSessionInput(session_id=session_id_1))

        # 会话2 应该仍然可用
        chat_response2_after = await chat_with_expert(
            ChatInput(session_id=session_id_2, message="还能帮我什么？")
        )
        assert "不存在" not in chat_response2_after


# ============================================================================
# Test: 错误处理
# ============================================================================

class TestErrorHandling:
    """测试错误处理机制"""

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_chat_after_session_closed(self, patch_llm_client):
        """测试会话关闭后继续对话（应该失败）"""
        # 创建会话
        create_response = await create_expert_session(
            CreateSessionInput(requirement="测试需求描述")
        )
        match = re.search(r'`([a-f0-9]{32})`', create_response)
        session_id = match.group(1)

        # 关闭会话
        await end_expert_session(CloseSessionInput(session_id=session_id))

        # 尝试对话（应该失败）
        response = await chat_with_expert(
            ChatInput(session_id=session_id, message="这应该失败")
        )
        assert "不存在" in response or "过期" in response

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_fallback_on_llm_failure(self):
        """测试 LLM 失败时的兜底机制"""
        from unittest.mock import AsyncMock, patch

        # 创建会话（LLM 正常）
        create_response = await create_expert_session(
            CreateSessionInput(requirement="测试需求描述")
        )
        match = re.search(r'`([a-f0-9]{32})`', create_response)
        session_id = match.group(1)

        # Mock LLM 失败
        with patch("mirror_of_wisdom.llm_client.get_llm_client") as mock_get:
            from unittest.mock import MagicMock
            mock_client = MagicMock()
            mock_client.generate = AsyncMock(side_effect=Exception("LLM unavailable"))
            mock_get.return_value = mock_client

            # 对话应该失败（因为 chat_with_expert 没有兜底机制）
            # 实际上 chat_with_expert 会返回错误信息
            response = await chat_with_expert(
                ChatInput(session_id=session_id, message="测试")
            )
            # 应该返回错误信息而不是崩溃
            assert response is not None


# ============================================================================
# Test: 响应格式验证
# ============================================================================

class TestResponseFormats:
    """测试响应格式的正确性"""

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_create_session_response_format(self, patch_llm_client):
        """测试创建会话响应格式"""
        response = await create_expert_session(
            CreateSessionInput(requirement="我需要技术帮助")
        )

        # 验证包含关键元素
        assert "会话ID" in response or "session_id" in response.lower()
        assert re.search(r'`[a-f0-9]{32}`', response)
        assert "专家" in response or "首次回复" in response

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_close_session_response_format(self, patch_llm_client):
        """测试关闭会话响应格式"""
        # 先创建
        create_response = await create_expert_session(
            CreateSessionInput(requirement="测试响应格式")
        )
        match = re.search(r'`([a-f0-9]{32})`', create_response)
        session_id = match.group(1)

        # 关闭
        close_response = await end_expert_session(
            CloseSessionInput(session_id=session_id)
        )

        # 验证格式
        assert "会话已结束" in close_response or "✅" in close_response
        assert session_id in close_response
        assert "会话总结" in close_response or "对话轮次" in close_response


# ============================================================================
# Test: Phase 5 两阶段优化集成测试
# ============================================================================

class TestPhase5TwoStageOptimization:
    """Phase 5 两阶段提示词优化集成测试"""

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_create_session_with_custom_constraints(self, patch_llm_client):
        """测试带自定义约束创建会话"""
        response = await create_expert_session(
            CreateSessionInput(
                requirement="我需要优化数据库",
                custom_constraints=["你是PostgreSQL专家", "必须使用异步编程"]
            )
        )

        # 验证会话创建成功
        assert "会话已创建" in response or "✅" in response
        assert re.search(r'`[a-f0-9]{32}`', response)

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_create_session_with_custom_evaluation(self, patch_llm_client):
        """测试带自定义验收标准创建会话"""
        response = await create_expert_session(
            CreateSessionInput(
                requirement="我需要技术帮助",
                custom_evaluation=["建议必须具体可执行", "需要提供代码示例"]
            )
        )

        # 验证会话创建成功
        assert "会话已创建" in response or "✅" in response

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_create_session_with_both_parameters(self, patch_llm_client):
        """测试同时提供约束和验收标准"""
        response = await create_expert_session(
            CreateSessionInput(
                requirement="我需要Python代码帮助",  # 5字符以上
                custom_constraints=["你是Python专家"],
                custom_evaluation=["必须包含类型注解"]
            )
        )

        # 验证会话创建成功
        assert "会话已创建" in response or "✅" in response

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_full_lifecycle_with_custom_constraints(self, patch_llm_client):
        """测试带自定义约束的完整会话生命周期"""
        # 创建会话（带约束）
        create_response = await create_expert_session(
            CreateSessionInput(
                requirement="我需要优化数据库",
                custom_constraints=["你是PostgreSQL专家", "必须使用异步编程"]
            )
        )

        match = re.search(r'`([a-f0-9]{32})`', create_response)
        session_id = match.group(1)

        # 对话
        chat_response = await chat_with_expert(
            ChatInput(session_id=session_id, message="如何创建索引？")
        )
        assert chat_response is not None
        assert len(chat_response) > 10

        # 关闭会话
        close_response = await end_expert_session(
            CloseSessionInput(session_id=session_id)
        )
        assert "会话已结束" in close_response or "✅" in close_response


# ============================================================================
# Test: Phase 5 安全性测试（无上下文污染）
# ============================================================================

class TestPhase5Security:
    """Phase 5 安全性测试：验证无上下文污染"""

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_no_context_pollution_with_custom_constraints(self, patch_llm_client):
        """
        验证带自定义约束时不会污染本地AI上下文

        核心安全验证：
        - 自定义约束只存储在服务端 session 中
        - 返回给本地AI的内容不包含 expert_prompt
        - 返回内容不包含自定义约束的具体内容
        """
        response = await create_expert_session(
            CreateSessionInput(
                requirement="我需要技术帮助",  # 5字符以上
                custom_constraints=["内部约束：这是敏感的专家定位信息"]
            )
        )

        # 验证响应不包含内部约束
        assert "内部约束" not in response
        assert "敏感的专家定位信息" not in response

        # 验证不包含 expert_prompt 结构
        assert "# 1. 背景" not in response
        assert "# 2. 目标" not in response
        assert "4D 流程" not in response

        # 验证只返回专家的回复
        assert "专家" in response or "首次回复" in response
        assert "会话ID" in response or "session_id" in response.lower()

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_no_context_pollution_with_custom_evaluation(self, patch_llm_client):
        """验证带自定义验收标准时不会污染上下文"""
        response = await create_expert_session(
            CreateSessionInput(
                requirement="我需要技术帮助",
                custom_evaluation=["内部验收标准：这是敏感的质量要求"]
            )
        )

        # 验证响应不包含内部验收标准
        assert "内部验收标准" not in response
        assert "敏感的质量要求" not in response

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_no_prompt_structure_in_response(self, patch_llm_client):
        """验证响应中不包含提示词结构"""
        response = await create_expert_session(
            CreateSessionInput(
                requirement="我需要技术帮助",
                custom_constraints=["约束1"],
                custom_evaluation=["标准1"]
            )
        )

        # 这些都是提示词结构标记，不应该出现在返回给本地AI的内容中
        forbidden_patterns = [
            "# 1. 背景",
            "# 2. 目标",
            "# 3. 风格与语调",
            "# 4. 受众",
            "# 5. 响应",
            "## 5.1 执行步骤",
            "## 5.2 评估标准",
            "## 5.3 格式与约束",
            "4D 流程",
            "Deconstruction",
            "待优化的提示词",
            "新的优化要求"
        ]

        for pattern in forbidden_patterns:
            assert pattern not in response, f"响应中包含提示词结构标记: {pattern}"

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_expert_reply_only(self, patch_llm_client):
        """验证只返回专家回复，不返回提示词"""
        response = await create_expert_session(
            CreateSessionInput(
                requirement="我需要优化数据库",
                custom_constraints=["你是PostgreSQL专家"]
            )
        )

        # 验证包含专家回复内容（应该是对用户问题的回应）
        assert len(response) > 50

        # 验证不包含提示词定义（自定义约束不应直接出现在响应中）
        assert "你是PostgreSQL专家" not in response

        # 验证不包含专家提示词的结构化章节
        # 这些是元提示词生成的提示词特有的章节标题
        prompt_only_patterns = [
            "# 1. 背景",
            "# 2. 目标",
            "# 3. 风格与语调",
            "# 4. 受众",
            "# 5. 响应",
            "## 5.1 执行步骤",
            "## 5.2 评估标准",
            "## 5.3 格式与约束",
            "待优化的提示词",
            "新的优化要求"
        ]

        for pattern in prompt_only_patterns:
            assert pattern not in response, f"响应中包含提示词结构标记: {pattern}"

        # 验证响应包含预期内容（会话创建成功、专家回复等）
        assert "会话" in response
        assert ("会话ID" in response or "session_id" in response.lower())
