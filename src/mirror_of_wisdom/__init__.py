"""求知镜 MCP - 动态专家角色生成与对话系统

这个 MCP 服务器根据任务需求动态变换为任何需要的专家或智者角色。
"""

__version__ = "0.1.0"
__author__ = "Mirror of Wisdom Team"

from .config import (
    get_mirror_config,
    get_server_config,
    get_feature_config,
    reset_config,
)

__all__ = [
    "get_mirror_config",
    "get_server_config",
    "get_feature_config",
    "reset_config",
]
