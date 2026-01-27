"""会话管理器 - 负责管理专家会话状态

基于上级AI顾问的架构指导：
- 显式生命周期管理
- 内存存储（MVP阶段）
- TTL自动清理机制
- 协程安全设计
"""

import asyncio
import logging
import uuid
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from dataclasses import dataclass, field
from enum import Enum

logger = logging.getLogger(__name__)


class SessionState(Enum):
    """会话状态枚举"""
    CREATED = "created"          # 已创建，等待首次对话
    SYNCHRONIZING = "sync"      # 信息颗粒度同步中
    IN_DIALOGUE = "dialogue"    # 对话中
    COMPLETED = "completed"     # 已完成


@dataclass
class Message:
    """对话消息"""
    role: str  # "user" or "assistant"
    content: str
    timestamp: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> dict:
        """转换为字典"""
        return {
            "role": self.role,
            "content": self.content,
            "timestamp": self.timestamp.isoformat()
        }


@dataclass
class Session:
    """会话对象"""
    session_id: str
    system_prompt: str  # 专家提示词（生成的）
    task_description: str  # 原始任务描述
    state: SessionState = SessionState.CREATED
    created_at: datetime = field(default_factory=datetime.now)
    last_activity: datetime = field(default_factory=datetime.now)
    message_count: int = 0
    history: List[Message] = field(default_factory=list)

    # 元数据
    expert_type: Optional[str] = None
    quality_score: float = 1.0

    def update_activity(self):
        """更新活动时间"""
        self.last_activity = datetime.now()

    def add_message(self, role: str, content: str) -> Message:
        """添加消息到历史"""
        msg = Message(role=role, content=content)
        self.history.append(msg)
        self.message_count += 1
        self.update_activity()
        return msg

    def is_expired(self, ttl_minutes: int = 30) -> bool:
        """检查会话是否过期"""
        expiry_time = self.last_activity + timedelta(minutes=ttl_minutes)
        return datetime.now() > expiry_time

    def get_conversation_context(self, max_messages: int = 50) -> List[dict]:
        """获取对话上下文（用于LLM调用）"""
        # 获取最近的N条消息
        recent_messages = self.history[-max_messages:]
        return [msg.to_dict() for msg in recent_messages]


class SessionManager:
    """会话管理器（单例模式）"""

    _instance: Optional['SessionManager'] = None
    _lock: asyncio.Lock = asyncio.Lock()

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        """初始化会话管理器"""
        if hasattr(self, '_initialized'):
            return

        self._sessions: Dict[str, Session] = {}
        self._ttl_minutes = 30  # 默认TTL 30分钟
        self._max_history = 100  # 最多保留100条历史
        self._cleanup_interval = 300  # 每5分钟清理一次过期会话
        self._initialized = True

        logger.info("会话管理器初始化完成")

    async def create_session(
        self,
        system_prompt: str,
        task_description: str,
        expert_type: Optional[str] = None,
        quality_score: float = 1.0
    ) -> str:
        """创建新会话

        Args:
            system_prompt: 专家提示词（生成的）
            task_description: 原始任务描述
            expert_type: 专家类型（可选）
            quality_score: 质量评分

        Returns:
            session_id: 会话ID
        """
        async with self._lock:
            session_id = uuid.uuid4().hex

            session = Session(
                session_id=session_id,
                system_prompt=system_prompt,
                task_description=task_description,
                expert_type=expert_type,
                quality_score=quality_score
            )

            self._sessions[session_id] = session

            logger.info(
                f"创建会话: {session_id} "
                f"(专家类型: {expert_type}, 质量评分: {quality_score})"
            )

            # 触发清理任务
            asyncio.create_task(self._cleanup_expired())

            return session_id

    async def get_session(self, session_id: str) -> Optional[Session]:
        """获取会话

        Args:
            session_id: 会话ID

        Returns:
            Session对象，如果不存在或已过期返回None
        """
        async with self._lock:
            session = self._sessions.get(session_id)

            if session is None:
                logger.warning(f"会话不存在: {session_id}")
                return None

            if session.is_expired(self._ttl_minutes):
                logger.info(f"会话已过期: {session_id}")
                del self._sessions[session_id]
                return None

            session.update_activity()
            return session

    async def update_session(
        self,
        session_id: str,
        user_message: str,
        assistant_response: str
    ) -> Optional[Session]:
        """更新会话（添加对话记录）

        Args:
            session_id: 会话ID
            user_message: 用户消息
            assistant_response: 助手回复

        Returns:
            更新后的Session对象，如果会话不存在返回None
        """
        async with self._lock:
            # 直接访问 sessions 避免死锁（get_session 也要获取锁）
            session = self._sessions.get(session_id)

            if session is None:
                logger.warning(f"更新会话失败，会话不存在: {session_id}")
                return None

            # 检查过期
            if session.is_expired(self._ttl_minutes):
                logger.info(f"更新会话失败，会话已过期: {session_id}")
                del self._sessions[session_id]
                return None

            # 添加消息到历史
            session.add_message("user", user_message)
            session.add_message("assistant", assistant_response)

            # 更新状态
            if session.state == SessionState.CREATED:
                session.state = SessionState.IN_DIALOGUE

            # 滑动窗口：限制历史记录数量
            if len(session.history) > self._max_history:
                # 保留最近的max_history条消息
                session.history = session.history[-self._max_history:]

            # 更新活动时间
            session.update_activity()

            logger.info(
                f"更新会话: {session_id} "
                f"(消息数: {session.message_count}, 状态: {session.state.value})"
            )

            return session

    async def close_session(self, session_id: str) -> bool:
        """关闭会话

        Args:
            session_id: 会话ID

        Returns:
            是否成功关闭
        """
        async with self._lock:
            session = self._sessions.get(session_id)

            if session is None:
                logger.warning(f"关闭会话失败，会话不存在: {session_id}")
                return False

            session.state = SessionState.COMPLETED
            del self._sessions[session_id]

            logger.info(f"关闭会话: {session_id}")
            return True

    async def _cleanup_expired(self):
        """清理过期会话（后台任务）"""
        now = datetime.now()
        expired_sessions = []

        async with self._lock:
            for session_id, session in self._sessions.items():
                if session.is_expired(self._ttl_minutes):
                    expired_sessions.append(session_id)

            for session_id in expired_sessions:
                del self._sessions[session_id]

        if expired_sessions:
            logger.info(f"清理过期会话: {len(expired_sessions)}个")

    async def get_session_info(self, session_id: str) -> Optional[dict]:
        """获取会话信息

        Args:
            session_id: 会话ID

        Returns:
            会话信息字典
        """
        session = await self.get_session(session_id)
        if session is None:
            return None

        return {
            "session_id": session.session_id,
            "state": session.state.value,
            "expert_type": session.expert_type,
            "task_description": session.task_description,
            "created_at": session.created_at.isoformat(),
            "last_activity": session.last_activity.isoformat(),
            "message_count": session.message_count,
            "quality_score": session.quality_score
        }

    async def list_sessions(self) -> List[dict]:
        """列出所有活跃会话

        Returns:
            会话信息列表
        """
        async with self._lock:
            sessions = []

            for session_id, session in self._sessions.items():
                if not session.is_expired(self._ttl_minutes):
                    sessions.append({
                        "session_id": session_id,
                        "state": session.state.value,
                        "expert_type": session.expert_type,
                        "message_count": session.message_count,
                        "created_at": session.created_at.isoformat()
                    })

            return sessions


# 全局实例
_session_manager: Optional[SessionManager] = None


def get_session_manager() -> SessionManager:
    """获取会话管理器实例"""
    global _session_manager
    if _session_manager is None:
        _session_manager = SessionManager()
    return _session_manager


async def reset_session_manager():
    """重置会话管理器（主要用于测试）"""
    global _session_manager
    _session_manager = None
    logger.info("会话管理器已重置")
