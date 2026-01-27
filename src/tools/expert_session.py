"""求知镜专家会话工具（基于上级AI顾问的架构指导）

实现三个核心工具：
1. create_expert_session - 创建专家会话（阶段1：元提示词生成）
2. chat_with_expert - 与专家对话（阶段2：多轮对话）
3. close_session - 关闭会话

设计原则：
- 显式生命周期管理
- 会话状态服务端管理
- 信息颗粒度同步（通过元提示词定义）
- TTL自动清理机制
- Phase 5: 两阶段提示词优化（支持自定义约束和验收标准）
"""

import logging
from typing import Literal, Optional
from pydantic import BaseModel, Field, field_validator, ConfigDict

from mirror_of_wisdom.session_manager import get_session_manager
from mirror_of_wisdom.prompt_generator import get_prompt_generator
from mirror_of_wisdom.llm_client import get_llm_client
from mirror_of_wisdom.config import get_mirror_config

logger = logging.getLogger(__name__)


# ============================================================================
# Pydantic 模型 - 输入验证
# ============================================================================

class CreateSessionInput(BaseModel):
    """创建会话的输入模型（Phase 5: 支持两阶段优化）"""
    model_config = ConfigDict(
        str_strip_whitespace=True,
        validate_assignment=True,
        extra='forbid'
    )

    requirement: str = Field(
        ...,
        description="本地AI的原始需求描述",
        min_length=5,
        max_length=5000
    )

    # ========== Phase 5: 两阶段优化参数 ==========
    custom_constraints: Optional[list[str]] = Field(
        None,
        description="自定义约束条件列表（可选），用于指定专家定位或技术限制"
    )

    custom_evaluation: Optional[list[str]] = Field(
        None,
        description="自定义验收标准列表（可选），用于指定质量要求"
    )

    @field_validator('requirement')
    @classmethod
    def validate_requirement(cls, v: str) -> str:
        """验证需求描述"""
        if not v.strip():
            raise ValueError("需求描述不能为空")
        return v.strip()


class ChatInput(BaseModel):
    """对话的输入模型"""
    model_config = ConfigDict(
        str_strip_whitespace=True,
        validate_assignment=True,
        extra='forbid'
    )

    session_id: str = Field(
        ...,
        description="会话ID（由create_expert_session返回）"
    )

    message: str = Field(
        ...,
        description="用户消息内容",
        min_length=1,
        max_length=10000
    )

    @field_validator('message')
    @classmethod
    def validate_message(cls, v: str) -> str:
        """验证消息内容"""
        if not v.strip():
            raise ValueError("消息内容不能为空")
        return v.strip()


class CloseSessionInput(BaseModel):
    """关闭会话的输入模型"""
    model_config = ConfigDict(
        str_strip_whitespace=True,
        validate_assignment=True,
        extra='forbid'
    )

    session_id: str = Field(
        ...,
        description="要关闭的会话ID"
    )


# ============================================================================
# 工具实现
# ============================================================================

async def create_expert_session(params: CreateSessionInput) -> str:
    """
    创建专家会话（Phase 5: 两阶段优化版）

    **功能说明**：
    这是求知镜的第一阶段（Phase 5 重构后），负责：
    1. 接收本地AI的原始需求和可选的自定义要求
    2. 使用元提示词（4D流程）生成基础专家提示词
    3. （可选）根据自定义要求进行第二阶段优化
    4. 创建会话并存储专家提示词作为 system prompt
    5. 立即生成专家首次回复（信息粒度对齐）
    6. 返回会话ID + 专家首次回复

    **工作流程**：
    ```
    本地AI → create_expert_session(需求, 自定义约束?, 自定义验收标准?)
      ↓
    合并配置预设和请求参数（请求参数优先）
      ↓
    元提示词处理（4D流程）→ 基础专家提示词
      ↓
    【有额外要求】→ 第二阶段优化（上下文拼接法）
    【无额外要求】→ 直接使用基础提示词
      ↓
    创建会话（SessionManager，system_prompt=expert_prompt）
      ↓
    LLM生成首次回复（信息粒度对齐）
      ↓
    更新会话历史
      ↓
    返回 session_id + expert_reply（✅ 零上下文污染）
    ```

    **Args**:
        params: CreateSessionInput对象
            - requirement: 本地AI的原始需求描述
            - custom_constraints: 自定义约束条件列表（可选）
            - custom_evaluation: 自定义验收标准列表（可选）

    **Returns**:
        Markdown格式的响应，包含：
        - 会话ID
        - 专家首次回复（信息粒度对齐问题）
        - 生成方法和质量评分
        - 两阶段优化标识（如适用）

    **Example**:
        ```python
        # 基础用法
        result = await create_expert_session(
            CreateSessionInput(requirement="我需要技术专家帮助优化数据库")
        )

        # Phase 5: 带自定义约束
        result = await create_expert_session(
            CreateSessionInput(
                requirement="我需要技术专家帮助优化数据库",
                custom_constraints=["你是PostgreSQL专家", "必须使用异步编程"]
            )
        )

    **Errors**:
        - ValueError: 需求描述为空或格式错误
        - RuntimeError: 元提示词生成失败且回退也失败

    **Design Notes** (Phase 5):
        - 专家提示词作为 system prompt 在求知镜内部使用
        - System prompt 不返回给本地AI，避免上下文污染
        - 支持配置文件预设全局默认约束和验收标准
        - 请求参数优先于配置预设（合并逻辑）
        - 两阶段优化使用上下文拼接法，无污染风险
    """
    try:
        logger.info(f"接收到创建会话请求: {len(params.requirement)} 字符")

        # ========== Phase 5: 合并配置预设和请求参数 ==========
        config = get_mirror_config()
        merged_constraints = config.get_merged_constraints(params.custom_constraints)
        merged_evaluation = config.get_merged_evaluation(params.custom_evaluation)

        if merged_constraints:
            logger.info(f"使用自定义约束: {len(merged_constraints)} 条")
        if merged_evaluation:
            logger.info(f"使用自定义验收标准: {len(merged_evaluation)} 条")

        # 1. 使用元提示词生成专家提示词（Phase 5: 支持两阶段优化）
        prompt_generator = get_prompt_generator()
        generation_result = await prompt_generator.generate_expert_prompt_with_meta(
            user_requirement=params.requirement,
            custom_constraints=merged_constraints,
            custom_evaluation=merged_evaluation
        )

        expert_prompt = generation_result["expert_prompt"]
        generation_method = generation_result["generation_method"]
        quality_score = generation_result["quality_score"]

        logger.info(
            f"专家提示词生成成功: "
            f"方法={generation_method}, "
            f"质量={quality_score:.2f}, "
            f"长度={len(expert_prompt)}"
        )

        # 2. 创建会话
        session_manager = get_session_manager()
        session_id = await session_manager.create_session(
            system_prompt=expert_prompt,
            task_description=params.requirement,
            expert_type=None,  # 元提示词模式不需要预定义类型
            quality_score=quality_score
        )

        logger.info(f"会话创建成功: {session_id}")

        # 3. 【Phase 4】生成专家首次回复（信息粒度对齐）
        logger.info("正在生成专家首次回复...")
        llm_client = get_llm_client()

        # 构建用户提示（system prompt 通过参数传递）
        user_prompt = f"用户需求：{params.requirement}\n\n请主动询问细节以对齐信息粒度，然后提供专业指导。"

        # 调用 LLM 生成首次回复
        expert_reply = await llm_client.generate(
            prompt=user_prompt,
            system_prompt=expert_prompt
        )

        logger.info(f"专家首次回复生成成功，长度: {len(expert_reply)} 字符")

        # 4. 【Phase 4】更新会话历史（记录首次对话）
        await session_manager.update_session(
            session_id=session_id,
            user_message=params.requirement,
            assistant_response=expert_reply
        )

        logger.info(f"会话历史已更新: {session_id}")

        # 5. 构建响应（包含专家首次回复）
        response = f"""✅ **专家会话已创建**

**会话ID**: `{session_id}`

**任务描述**: {params.requirement[:100]}{'...' if len(params.requirement) > 100 else ''}

---

## 📣 专家的首次回复

{expert_reply}

---

## 下一步

使用 `chat_with_expert` 工具继续与专家对话：

```python
chat_with_expert(session_id="{session_id}", message="你的回复")
```

**专家已加载并准备好为您服务。**
"""

        return response

    except ValueError as e:
        # 输入验证错误
        logger.error(f"输入验证错误: {e}")
        return f"**错误**: {str(e)}\n\n请检查你的需求描述并重试。"

    except Exception as e:
        # 未预期的错误
        logger.error(f"创建会话失败: {e}", exc_info=True)
        return f"""**求知镜暂时无法创建会话**

错误信息: {str(e)}

建议：
1. 检查需求描述是否清晰
2. 如果问题持续，请查看日志了解详情

技术细节（用于调试）:
- 错误类型: {type(e).__name__}
- 错误信息: {str(e)}
"""


async def chat_with_expert(params: ChatInput) -> str:
    """
    与专家对话（阶段2：多轮对话）

    **功能说明**：
    这是求知镜的第二阶段，负责：
    1. 加载会话状态和专家提示词
    2. 构建对话上下文（system prompt + history）
    3. 调用LLM生成专家回复
    4. 更新对话历史
    5. 处理信息颗粒度同步（通过元提示词定义）

    **工作流程**：
    ```
    本地AI → chat_with_expert(session_id, message)
      ↓
    SessionManager加载会话
      ↓
    构建LLM请求：
      - System: 专家提示词
      - History: 对话历史
      - User: 新消息
      ↓
    LLM生成回复
      ↓
    更新会话历史
      ↓
    返回专家回复
    ```

    **Args**:
        params: ChatInput对象
            - session_id: 会话ID
            - message: 用户消息

    **Returns**:
        专家的回复内容

    **Example**:
        ```python
        response = await chat_with_expert(
            ChatInput(session_id="abc123", message="如何优化索引？")
        )
        # 返回专家的详细建议
        ```

    **Errors**:
        - ValueError: session_id无效或会话已过期
        - RuntimeError: LLM调用失败

    **Design Notes**:
        - 每次对话都将专家提示词作为system message注入
        - 信息颗粒度同步由元提示词生成的专家提示词内部定义
        - 对话历史自动管理（滑动窗口，最多100条）
        - 会话TTL 30分钟无活动自动清理
    """
    try:
        logger.info(f"接收到对话请求: session_id={params.session_id}")

        # 1. 加载会话
        session_manager = get_session_manager()
        session = await session_manager.get_session(params.session_id)

        if session is None:
            return f"""**错误**: 会话不存在或已过期

会话ID: `{params.session_id}`

可能的原因：
1. 会话ID输入错误
2. 会话已过期（30分钟无活动）
3. 会话已被关闭

**解决方案**：使用 `create_expert_session` 重新创建会话
"""

        logger.info(
            f"会话已加载: "
            f"状态={session.state.value}, "
            f"历史消息数={session.message_count}"
        )

        # 2. 构建LLM请求
        llm_client = get_llm_client()

        # 【快速修复】由于现有 LLM 客户端不支持对话模式，
        # 我们暂时只传递 system prompt + 当前消息（不包含历史）
        # TODO: 未来需要增强 LLM 客户端以支持真正的多轮对话

        # 构建用户提示
        user_prompt = f"用户消息：{params.message}"

        # 调用 LLM
        logger.info("调用LLM生成专家回复...")
        response = await llm_client.generate(
            prompt=user_prompt,
            system_prompt=session.system_prompt
        )

        # 4. 更新会话历史
        await session_manager.update_session(
            session_id=params.session_id,
            user_message=params.message,
            assistant_response=response
        )

        logger.info(f"对话完成: session_id={params.session_id}")

        # 5. 返回专家回复
        return response

    except ValueError as e:
        # 输入验证错误
        logger.error(f"输入验证错误: {e}")
        return f"**错误**: {str(e)}"

    except Exception as e:
        # 未预期的错误
        logger.error(f"对话失败: {e}", exc_info=True)
        return f"""**求知镜暂时无法处理你的请求**

错误信息: {str(e)}

建议：
1. 检查会话ID是否正确
2. 如果问题持续，请重新创建会话

技术细节（用于调试）:
- 错误类型: {type(e).__name__}
- 错误信息: {str(e)}
"""


async def end_expert_session(params: CloseSessionInput) -> str:
    """
    结束专家会话并清理资源（Phase 4 重构版）

    **功能说明**：
    结束指定的专家会话，卸载专家角色，并提供详细的会话总结。

    **工作流程**：
    ```
    本地AI → end_expert_session(session_id)
      ↓
    SessionManager标记会话为COMPLETED
      ↓
    卸载专家system prompt
      ↓
    清理会话数据
      ↓
    返回关闭确认 + 会话总结
    ```

    **Phase 4 变更**：
    - 提供详细的会话统计（轮次、持续时间、专家类型）
    - 明确提示专家角色已卸载
    - 会话总结便于复盘和追踪

    **Args**:
        params: CloseSessionInput对象
            - session_id: 要结束的会话ID

    **Returns**:
        结束确认信息和详细会话总结

    **Example**:
        ```python
        result = await end_expert_session(CloseSessionInput(session_id="abc123"))
        # 返回会话关闭确认和详细统计信息
        ```

    **Design Notes**:
        - 结束后会话数据立即删除
        - 专家system prompt被卸载，恢复默认联系工具身份
        - 未结束的会话会在30分钟后自动过期
        - 建议在任务完成后主动结束会话
    """
    try:
        logger.info(f"接收到结束会话请求: session_id={params.session_id}")

        # 1. 获取会话信息（用于统计）
        session_manager = get_session_manager()
        session_info = await session_manager.get_session_info(params.session_id)

        if session_info is None:
            return f"""**会话不存在或已结束**

会话ID: `{params.session_id}`

该会话可能：
1. 从未创建过
2. 已经被结束
3. 已过期（30分钟无活动自动清理）

**解决方案**：使用 `start_expert_session` 或 `create_expert_session` 创建新会话。
"""

        # 2. 结束会话
        success = await session_manager.close_session(params.session_id)

        if not success:
            return f"**结束失败**: 无法结束会话 {params.session_id}"

        # 3. 【Phase 4 增强】计算会话统计
        from datetime import datetime

        # 计算持续时间（分钟）
        created_at = datetime.fromisoformat(session_info['created_at'])
        last_activity = datetime.fromisoformat(session_info['last_activity'])
        duration_minutes = int((last_activity - created_at).total_seconds() / 60)

        # 计算对话轮次（每轮=用户消息+助手回复=2条）
        dialogue_rounds = session_info['message_count'] // 2

        # 推断专家类型
        expert_type = session_info.get('expert_type', '未知')
        expert_type_map = {
            'technical': '技术专家',
            'creative': '创意设计师',
            'business': '商业顾问',
            'education': '教育专家',
            'writing': '写作顾问',
            'research': '研究分析师',
            'philosophy': '哲学思考者',
            'general': '通用助手',
            None: '动态专家'
        }
        expert_name = expert_type_map.get(expert_type, f"{expert_type}专家")

        # 推断问题解决状态（基于对话轮次）
        resolved_status = "✅ 已解决" if dialogue_rounds >= 2 else "⏳ 进行中"

        # 4. 构建响应（包含详细统计）
        response = f"""✅ **专家会话已结束**

**会话ID**: `{params.session_id}`

---

## 📊 会话总结

**基础信息**:
- 专家类型: {expert_name}
- 对话轮次: {dialogue_rounds} 轮
- 持续时间: {duration_minutes} 分钟
- 状态: {resolved_status}

**时间信息**:
- 创建时间: {session_info['created_at'][:19]}
- 最后活动: {session_info['last_activity'][:19]}

**质量信息**:
- 质量评分: {session_info.get('quality_score', 'N/A')}

---

## 💡 提示

**专家角色已卸载**：求知镜已恢复默认联系工具身份。

**创建新会话**：使用 `start_expert_session` 或 `create_expert_session` 创建新会话继续工作。

**感谢使用求知镜！**
"""

        logger.info(f"会话已结束: {params.session_id}, rounds={dialogue_rounds}, duration={duration_minutes}min")
        return response

    except Exception as e:
        logger.error(f"结束会话失败: {e}", exc_info=True)
        return f"""**结束会话失败**

错误信息: {str(e)}

建议：
1. 检查会话ID是否正确
2. 如果问题持续，请重新创建会话

技术细节（用于调试）:
- 错误类型: {type(e).__name__}
"""


# ============================================================================
# 工具 Annotations（MCP最佳实践）
# ============================================================================

CREATE_SESSION_ANNOTATIONS = {
    "title": "Create Expert Session",
    "description": "创建专家会话（Phase 5: 支持两阶段提示词优化）",
    "readOnlyHint": False,
    "destructiveHint": False,
    "idempotentHint": False,
    "openWorldHint": True
}

CHAT_ANNOTATIONS = {
    "title": "Chat with Expert",
    "description": "与专家对话（阶段2：多轮对话）",
    "readOnlyHint": True,
    "destructiveHint": False,
    "idempotentHint": False,
    "openWorldHint": True
}

CLOSE_SESSION_ANNOTATIONS = {
    "title": "Close Session",
    "description": "关闭会话并清理资源",
    "readOnlyHint": False,
    "destructiveHint": True,
    "idempotentHint": True,
    "openWorldHint": False
}
