#!/usr/bin/env python3
"""
求知镜 MCP 服务器

这是一个基于 MCP (Model Context Protocol) 的服务器，
可以根据任务需求动态生成专家角色提示词。
"""

import logging
import sys
from pathlib import Path

from mcp.server.fastmcp import FastMCP

# 添加 src 到 Python 路径
src_path = Path(__file__).parent
if str(src_path) not in sys.path:
    sys.path.insert(0, str(src_path))

from mirror_of_wisdom.config import get_server_config

# 导入专家会话工具（Phase 2+4 核心功能）
# ⚠️ 规则引擎模式已删除，仅保留元提示词模式
from tools.expert_session import (
    create_expert_session,
    chat_with_expert,
    end_expert_session,
    CreateSessionInput,
    ChatInput,
    CloseSessionInput,
    CREATE_SESSION_ANNOTATIONS,
    CHAT_ANNOTATIONS,
    CLOSE_SESSION_ANNOTATIONS
)

# 配置日志
server_config = get_server_config()
logging.basicConfig(
    level=getattr(logging, server_config.log_level),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)

# 初始化 FastMCP 服务器
mcp = FastMCP("mirror_of_wisdom_mcp")


# ============================================================================
# Phase 2: 专家会话工具（基于上级AI顾问的架构指导）
# ============================================================================

@mcp.tool(
    name="create_expert_session",
    annotations=CREATE_SESSION_ANNOTATIONS
)
async def create_expert_session_tool(params: CreateSessionInput) -> str:
    """
    创建专家会话（阶段1：元提示词生成）

    这是求知镜Phase 2的核心工具，实现两阶段流程的第一步。

    **工作流程**：
    1. 接收本地AI的原始需求
    2. 使用元提示词（4D流程：Deconstruction, Diagnosis, Development, Delivery）
    3. 动态生成专家提示词
    4. 创建会话并存储专家提示词
    5. 返回会话ID

    **使用示例**：
    ```
    create_expert_session(
        requirement="我需要技术专家帮助优化MySQL数据库查询性能"
    )
    ```

    **返回内容**：
    - 会话ID（用于后续对话）
    - 专家确认信息
    - 准备开始对话提示

    **下一步**：
    使用返回的session_id调用 `chat_with_expert` 开始对话。

    Args:
        params: CreateSessionInput对象
            - requirement: 原始需求描述（5-5000字符）

    Returns:
        Markdown格式的会话创建确认信息
    """
    logger.info(f"调用 create_expert_session: {params.requirement[:50]}...")
    return await create_expert_session(params)


@mcp.tool(
    name="chat_with_expert",
    annotations=CHAT_ANNOTATIONS
)
async def chat_with_expert_tool(params: ChatInput) -> str:
    """
    与专家对话（阶段2：多轮对话）

    这是求知镜Phase 2的第二步，实现与专家的持续对话。

    **工作流程**：
    1. 根据session_id加载会话状态
    2. 加载专家提示词作为system message
    3. 加载对话历史（最近50条）
    4. 构建完整上下文并发送给LLM
    5. 获取专家回复并更新历史

    **特性**：
    - 信息颗粒度同步：由元提示词生成的专家提示词内部定义
    - 完整上下文保持：专家记住之前的所有对话
    - 自动历史管理：滑动窗口，最多保留100条消息
    - TTL自动清理：30分钟无活动自动过期

    **使用示例**：
    ```
    # 第一轮对话
    chat_with_expert(
        session_id="abc123...",
        message="我的订单表有5000万条数据，查询很慢"
    )

    # 第二轮对话（专家记得上下文）
    chat_with_expert(
        session_id="abc123...",
        message="能给出具体的SQL优化方案吗？"
    )
    ```

    **错误处理**：
    - 如果会话不存在或已过期，会提示重新创建会话

    Args:
        params: ChatInput对象
            - session_id: 会话ID（由create_expert_session返回）
            - message: 用户消息（1-10000字符）

    Returns:
        专家的回复内容
    """
    logger.info(f"调用 chat_with_expert: session_id={params.session_id}, message={params.message[:50]}...")
    return await chat_with_expert(params)


@mcp.tool(
    name="end_expert_session",
    annotations=CLOSE_SESSION_ANNOTATIONS
)
async def end_expert_session_tool(params: CloseSessionInput) -> str:
    """
    结束专家会话（Phase 4 重构版）

    关闭指定的专家会话，清理相关资源，并提供会话总结。

    **建议**：
    - 任务完成后主动结束会话
    - 未结束的会话会在30分钟后自动过期
    - 结束会话后，专家角色会被卸载

    **使用示例**：
    ```
    end_expert_session(session_id="abc123...")
    ```

    **返回内容**：
    - 结束确认信息
    - 会话总结（对话轮次、持续时间、专家类型等）
    - 专家角色卸载提示

    **Phase 4 变更**：
    - 提供详细的会话统计
    - 明确提示专家角色已卸载
    - 会话总结便于复盘和追踪

    Args:
        params: CloseSessionInput对象
            - session_id: 要结束的会话ID

    Returns:
        Markdown格式的结束确认信息和会话总结
    """
    logger.info(f"调用 end_expert_session: session_id={params.session_id}")
    return await end_expert_session(params)


def main():
    """
    启动 MCP 服务器

    这个服务器使用 stdio 传输协议，适合作为本地工具运行。
    """
    logger.info(f"启动 {server_config.name} v0.1.0")
    logger.info(f"日志级别: {server_config.log_level}")
    logger.info(f"质量检查: {'启用' if server_config.enable_quality_check else '禁用'}")
    logger.info(f"角色切换: {'启用' if server_config.enable_role_switching else '禁用'}")

    try:
        # 运行 MCP 服务器
        mcp.run()
    except KeyboardInterrupt:
        logger.info("服务器已停止（用户中断）")
    except Exception as e:
        logger.error(f"服务器错误: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
