"""
SessionManager 单元测试

测试会话管理器的核心功能，包括：
- 会话创建、获取、更新、关闭
- 对话历史管理
- TTL 自动清理
- 协程安全
"""

import pytest
import asyncio
from datetime import datetime, timedelta

from mirror_of_wisdom.session_manager import (
    SessionManager,
    Session,
    SessionState,
    Message,
    get_session_manager,
    reset_session_manager
)


# ============================================================================
# Test Fixtures
# ============================================================================

@pytest.fixture
async def session_manager():
    """创建干净的 SessionManager 实例用于测试"""
    await reset_session_manager()
    manager = SessionManager()
    # 手动清空所有现有会话
    manager._sessions.clear()
    yield manager
    await reset_session_manager()


@pytest.fixture
def sample_system_prompt():
    """示例系统提示词"""
    return """# 数据库优化专家

你是一位资深的数据库优化专家，精通SQL性能调优。

## 任务
帮助用户优化数据库查询性能。

## 约束
- 不要建议删除数据
- 不要建议修改表结构
"""


@pytest.fixture
def sample_task_description():
    """示例任务描述"""
    return "我需要优化订单表查询性能，当前有5000万条数据"


# ============================================================================
# Test: 会话创建
# ============================================================================

class TestSessionCreation:
    """测试会话创建功能"""

    @pytest.mark.asyncio
    async def test_create_session_basic(self, session_manager, sample_system_prompt, sample_task_description):
        """测试基本会话创建"""
        session_id = await session_manager.create_session(
            system_prompt=sample_system_prompt,
            task_description=sample_task_description,
            expert_type="database_expert"
        )

        # 验证 session_id 格式
        assert session_id is not None
        assert len(session_id) == 32  # UUID hex 格式
        assert isinstance(session_id, str)

    @pytest.mark.asyncio
    async def test_create_session_retrievable(self, session_manager, sample_system_prompt, sample_task_description):
        """测试创建的会话可以被获取"""
        session_id = await session_manager.create_session(
            system_prompt=sample_system_prompt,
            task_description=sample_task_description
        )

        session = await session_manager.get_session(session_id)

        assert session is not None
        assert session.session_id == session_id
        assert session.system_prompt == sample_system_prompt
        assert session.task_description == sample_task_description
        assert session.state == SessionState.CREATED

    @pytest.mark.asyncio
    async def test_create_session_with_metadata(self, session_manager, sample_system_prompt):
        """测试创建带元数据的会话"""
        session_id = await session_manager.create_session(
            system_prompt=sample_system_prompt,
            task_description="测试任务",
            expert_type="technical",
            quality_score=0.95
        )

        session = await session_manager.get_session(session_id)

        assert session.expert_type == "technical"
        assert session.quality_score == 0.95

    @pytest.mark.asyncio
    async def test_create_session_initial_state(self, session_manager, sample_system_prompt, sample_task_description):
        """测试会话初始状态"""
        session_id = await session_manager.create_session(
            system_prompt=sample_system_prompt,
            task_description=sample_task_description
        )

        session = await session_manager.get_session(session_id)

        assert session.state == SessionState.CREATED
        assert session.message_count == 0
        assert len(session.history) == 0
        assert session.created_at is not None
        assert session.last_activity is not None


# ============================================================================
# Test: 会话获取
# ============================================================================

class TestSessionRetrieval:
    """测试会话获取功能"""

    @pytest.mark.asyncio
    async def test_get_existing_session(self, session_manager, sample_system_prompt, sample_task_description):
        """测试获取存在的会话"""
        session_id = await session_manager.create_session(
            system_prompt=sample_system_prompt,
            task_description=sample_task_description
        )

        session = await session_manager.get_session(session_id)

        assert session is not None
        assert session.session_id == session_id

    @pytest.mark.asyncio
    async def test_get_nonexistent_session(self, session_manager):
        """测试获取不存在的会话"""
        session = await session_manager.get_session("nonexistent_id")
        assert session is None

    @pytest.mark.asyncio
    async def test_get_expired_session(self, session_manager, sample_system_prompt):
        """测试获取已过期会话"""
        # 创建会话
        session_id = await session_manager.create_session(
            system_prompt=sample_system_prompt,
            task_description="测试"
        )

        # 获取会话对象并手动修改 last_activity 使其过期
        session = await session_manager.get_session(session_id)
        session.last_activity = datetime.now() - timedelta(minutes=31)

        # 再次获取应该返回 None（已过期）
        expired_session = await session_manager.get_session(session_id)
        assert expired_session is None


# ============================================================================
# Test: 会话更新
# ============================================================================

class TestSessionUpdate:
    """测试会话更新功能"""

    @pytest.mark.asyncio
    async def test_update_session_adds_messages(self, session_manager, sample_system_prompt, sample_task_description):
        """测试更新会话添加消息"""
        session_id = await session_manager.create_session(
            system_prompt=sample_system_prompt,
            task_description=sample_task_description
        )

        user_msg = "我的查询很慢"
        assistant_msg = "请提供具体的SQL语句"

        updated_session = await session_manager.update_session(
            session_id=session_id,
            user_message=user_msg,
            assistant_response=assistant_msg
        )

        assert updated_session is not None
        assert updated_session.message_count == 2
        assert len(updated_session.history) == 2

        # 验证消息内容
        assert updated_session.history[0].role == "user"
        assert updated_session.history[0].content == user_msg
        assert updated_session.history[1].role == "assistant"
        assert updated_session.history[1].content == assistant_msg

    @pytest.mark.asyncio
    async def test_update_session_changes_state(self, session_manager, sample_system_prompt):
        """测试更新会话改变状态"""
        session_id = await session_manager.create_session(
            system_prompt=sample_system_prompt,
            task_description="测试"
        )

        session = await session_manager.get_session(session_id)
        assert session.state == SessionState.CREATED

        # 更新会话
        await session_manager.update_session(
            session_id=session_id,
            user_message="测试消息",
            assistant_response="测试回复"
        )

        updated_session = await session_manager.get_session(session_id)
        assert updated_session.state == SessionState.IN_DIALOGUE

    @pytest.mark.asyncio
    async def test_update_nonexistent_session(self, session_manager):
        """测试更新不存在的会话"""
        result = await session_manager.update_session(
            session_id="nonexistent",
            user_message="测试",
            assistant_response="测试"
        )

        assert result is None

    @pytest.mark.asyncio
    async def test_update_session_updates_activity(self, session_manager, sample_system_prompt):
        """测试更新会话刷新活动时间"""
        session_id = await session_manager.create_session(
            system_prompt=sample_system_prompt,
            task_description="测试"
        )

        session = await session_manager.get_session(session_id)
        original_activity = session.last_activity

        # 等待一小段时间
        await asyncio.sleep(0.01)

        # 更新会话
        await session_manager.update_session(
            session_id=session_id,
            user_message="测试",
            assistant_response="回复"
        )

        updated_session = await session_manager.get_session(session_id)
        assert updated_session.last_activity > original_activity


# ============================================================================
# Test: 会话关闭
# ============================================================================

class TestSessionClose:
    """测试会话关闭功能"""

    @pytest.mark.asyncio
    async def test_close_existing_session(self, session_manager, sample_system_prompt):
        """测试关闭存在的会话"""
        session_id = await session_manager.create_session(
            system_prompt=sample_system_prompt,
            task_description="测试"
        )

        success = await session_manager.close_session(session_id)

        assert success is True

        # 验证会话已被删除
        session = await session_manager.get_session(session_id)
        assert session is None

    @pytest.mark.asyncio
    async def test_close_nonexistent_session(self, session_manager):
        """测试关闭不存在的会话"""
        success = await session_manager.close_session("nonexistent")
        assert success is False


# ============================================================================
# Test: 对话历史管理
# ============================================================================

class TestConversationHistory:
    """测试对话历史管理"""

    @pytest.mark.asyncio
    async def test_message_timestamp(self, session_manager, sample_system_prompt):
        """测试消息时间戳"""
        session_id = await session_manager.create_session(
            system_prompt=sample_system_prompt,
            task_description="测试"
        )

        await session_manager.update_session(
            session_id=session_id,
            user_message="消息1",
            assistant_response="回复1"
        )

        session = await session_manager.get_session(session_id)
        msg = session.history[0]

        assert msg.timestamp is not None
        assert isinstance(msg.timestamp, datetime)

    @pytest.mark.asyncio
    async def test_get_conversation_context(self, session_manager, sample_system_prompt):
        """测试获取对话上下文"""
        session_id = await session_manager.create_session(
            system_prompt=sample_system_prompt,
            task_description="测试"
        )

        # 添加多条消息
        await session_manager.update_session(
            session_id=session_id,
            user_message="问题1",
            assistant_response="回答1"
        )
        await session_manager.update_session(
            session_id=session_id,
            user_message="问题2",
            assistant_response="回答2"
        )

        session = await session_manager.get_session(session_id)
        context = session.get_conversation_context(max_messages=10)

        assert len(context) == 4  # 2轮对话 = 4条消息
        assert context[0]["role"] == "user"
        assert context[0]["content"] == "问题1"

    @pytest.mark.asyncio
    async def test_conversation_context_max_messages_limit(self, session_manager, sample_system_prompt):
        """测试对话上下文消息数量限制"""
        session_id = await session_manager.create_session(
            system_prompt=sample_system_prompt,
            task_description="测试"
        )

        # 添加超过限制的消息（5轮 = 10条消息）
        for i in range(5):
            await session_manager.update_session(
                session_id=session_id,
                user_message=f"问题{i+1}",
                assistant_response=f"回答{i+1}"
            )

        session = await session_manager.get_session(session_id)
        context = session.get_conversation_context(max_messages=4)

        # 应该只返回最近4条（最后2轮对话）
        assert len(context) == 4
        # 顺序应该是：问题4、回答4、问题5、回答5
        assert context[0]["content"] == "问题4"  # 倒数第4条

    @pytest.mark.asyncio
    async def test_sliding_window_history_limit(self, session_manager, sample_system_prompt):
        """测试滑动窗口历史记录限制"""
        # 临时修改限制以加快测试
        session_manager._max_history = 5

        session_id = await session_manager.create_session(
            system_prompt=sample_system_prompt,
            task_description="测试"
        )

        # 添加超过限制的消息（6轮 = 12条消息）
        for i in range(6):
            await session_manager.update_session(
                session_id=session_id,
                user_message=f"问题{i+1}",
                assistant_response=f"回答{i+1}"
            )

        session = await session_manager.get_session(session_id)

        # 应该只保留最近5条消息（滑动窗口）
        assert len(session.history) <= 5


# ============================================================================
# Test: Session 对象
# ============================================================================

class TestSessionObject:
    """测试 Session 对象方法"""

    def test_message_to_dict(self):
        """测试消息转换为字典"""
        msg = Message(role="user", content="测试消息")
        msg_dict = msg.to_dict()

        assert msg_dict["role"] == "user"
        assert msg_dict["content"] == "测试消息"
        assert "timestamp" in msg_dict

    def test_session_is_expired_true(self):
        """测试会话过期检测（已过期）"""
        session = Session(
            session_id="test",
            system_prompt="测试",
            task_description="测试"
        )
        # 手动设置过期时间
        session.last_activity = datetime.now() - timedelta(minutes=31)

        assert session.is_expired(ttl_minutes=30) is True

    def test_session_is_expired_false(self):
        """测试会话过期检测（未过期）"""
        session = Session(
            session_id="test",
            system_prompt="测试",
            task_description="测试"
        )

        assert session.is_expired(ttl_minutes=30) is False

    def test_session_add_message(self):
        """测试添加消息到会话"""
        session = Session(
            session_id="test",
            system_prompt="测试",
            task_description="测试"
        )

        msg = session.add_message("user", "测试消息")

        assert msg.role == "user"
        assert msg.content == "测试消息"
        assert session.message_count == 1
        assert len(session.history) == 1


# ============================================================================
# Test: 会话信息
# ============================================================================

class TestSessionInfo:
    """测试会话信息获取"""

    @pytest.mark.asyncio
    async def test_get_session_info(self, session_manager, sample_system_prompt, sample_task_description):
        """测试获取会话信息"""
        session_id = await session_manager.create_session(
            system_prompt=sample_system_prompt,
            task_description=sample_task_description,
            expert_type="technical",
            quality_score=0.9
        )

        info = await session_manager.get_session_info(session_id)

        assert info is not None
        assert info["session_id"] == session_id
        assert info["expert_type"] == "technical"
        assert info["task_description"] == sample_task_description
        assert info["quality_score"] == 0.9
        assert "created_at" in info
        assert "last_activity" in info
        assert "message_count" in info

    @pytest.mark.asyncio
    async def test_get_session_info_nonexistent(self, session_manager):
        """测试获取不存在会话的信息"""
        info = await session_manager.get_session_info("nonexistent")
        assert info is None

    @pytest.mark.asyncio
    async def test_list_sessions(self, session_manager, sample_system_prompt):
        """测试列出所有会话"""
        # 创建多个会话
        session_id1 = await session_manager.create_session(
            system_prompt=sample_system_prompt,
            task_description="任务1"
        )
        session_id2 = await session_manager.create_session(
            system_prompt=sample_system_prompt,
            task_description="任务2"
        )

        sessions = await session_manager.list_sessions()

        assert len(sessions) == 2
        session_ids = [s["session_id"] for s in sessions]
        assert session_id1 in session_ids
        assert session_id2 in session_ids


# ============================================================================
# Test: 全局实例管理
# ============================================================================

class TestGlobalInstance:
    """测试全局 SessionManager 实例"""

    def test_get_session_manager_singleton(self):
        """测试单例模式"""
        manager1 = get_session_manager()
        manager2 = get_session_manager()

        assert manager1 is manager2


# ============================================================================
# Test: 协程安全
# ============================================================================

class TestConcurrencySafety:
    """测试协程安全性"""

    @pytest.mark.asyncio
    async def test_concurrent_session_creation(self, session_manager, sample_system_prompt):
        """测试并发创建会话"""
        tasks = []
        for i in range(10):
            task = session_manager.create_session(
                system_prompt=sample_system_prompt,
                task_description=f"任务{i}"
            )
            tasks.append(task)

        session_ids = await asyncio.gather(*tasks)

        # 验证所有 session_id 都是唯一的
        assert len(set(session_ids)) == 10

    @pytest.mark.asyncio
    async def test_concurrent_session_updates(self, session_manager, sample_system_prompt):
        """测试并发更新会话"""
        session_id = await session_manager.create_session(
            system_prompt=sample_system_prompt,
            task_description="测试"
        )

        # 并发更新
        tasks = []
        for i in range(5):
            task = session_manager.update_session(
                session_id=session_id,
                user_message=f"问题{i}",
                assistant_response=f"回答{i}"
            )
            tasks.append(task)

        results = await asyncio.gather(*tasks)

        # 验证所有更新都成功
        assert all(r is not None for r in results)

        # 验证消息数量
        session = await session_manager.get_session(session_id)
        assert session.message_count == 10  # 5轮 * 2条消息
