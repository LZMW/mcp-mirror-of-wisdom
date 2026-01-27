"""配置管理模块"""

import os
import ast
import re
from pathlib import Path
from typing import Literal
from pydantic import BaseModel, Field, field_validator
from dotenv import load_dotenv

# 加载环境变量
load_dotenv()


class MirrorConfig(BaseModel):
    """求知镜 LLM 配置"""

    # API 提供商
    provider: Literal["openai", "anthropic", "zhipu", "gemini", "custom"] = Field(
        default_factory=lambda: os.getenv("MIRROR_PROVIDER", "openai"),
        description="AI 服务提供商"
    )

    # API 密钥
    api_key: str = Field(
        default_factory=lambda: os.getenv("MIRROR_API_KEY", ""),
        description="API 密钥"
    )

    # API 基础 URL（可选，用于代理或自定义端点）
    base_url: str | None = Field(
        default_factory=lambda: os.getenv("MIRROR_BASE_URL"),
        description="API 基础 URL"
    )

    # 模型名称
    model: str = Field(
        default_factory=lambda: os.getenv("MIRROR_MODEL", "gpt-4o-mini"),
        description="模型名称"
    )

    # 温度参数
    temperature: float = Field(
        default_factory=lambda: float(os.getenv("MIRROR_TEMPERATURE", "0.7")),
        ge=0.0,
        le=2.0,
        description="温度参数"
    )

    # 最大 tokens
    max_tokens: int = Field(
        default_factory=lambda: int(os.getenv("MIRROR_MAX_TOKENS", "4096")),
        ge=1,
        description="最大生成 tokens"
    )

    # 请求超时时间（秒）
    # Phase 3 优化：从 30s 延长到 90s，覆盖 72s 的异常值
    timeout: int = Field(
        default_factory=lambda: int(os.getenv("MIRROR_TIMEOUT", "90")),
        ge=1,
        description="请求超时时间（秒）"
    )

    # 最大重试次数
    max_retries: int = Field(
        default_factory=lambda: int(os.getenv("MIRROR_MAX_RETRIES", "3")),
        ge=0,
        description="最大重试次数"
    )

    # 重试延迟（秒）
    retry_delay: int = Field(
        default_factory=lambda: int(os.getenv("MIRROR_RETRY_DELAY", "1")),
        ge=0,
        description="重试延迟（秒）"
    )

    # ========== Phase 5: 两阶段优化配置 ==========
    # 合并模式：priority（优先级模式）或 merge（叠加模式）
    constraint_merge_mode: Literal["priority", "merge"] = Field(
        default_factory=lambda: os.getenv("MIRROR_CONSTRAINT_MERGE_MODE", "priority"),
        description="约束合并模式：priority=请求参数优先，merge=配置+请求叠加"
    )

    # 全局默认约束（可被请求参数覆盖或合并）
    default_constraints: list[str] = Field(
        default_factory=lambda: MirrorConfig._parse_list_env(
            os.getenv("MIRROR_DEFAULT_CONSTRAINTS")
        ),
        description="全局默认约束条件列表"
    )

    # 全局默认验收标准（可被请求参数覆盖或合并）
    default_evaluation: list[str] = Field(
        default_factory=lambda: MirrorConfig._parse_list_env(
            os.getenv("MIRROR_DEFAULT_EVALUATION")
        ),
        description="全局默认验收标准列表"
    )

    @staticmethod
    def _parse_list_env(env_value: str | None) -> list[str]:
        """
        解析环境变量中的列表类型

        支持格式：["item1", "item2"] 或 JSON 数组

        Args:
            env_value: 环境变量值

        Returns:
            解析后的列表，解析失败返回空列表
        """
        if not env_value:
            return []

        try:
            # 使用 ast.literal_eval 安全解析
            result = ast.literal_eval(env_value.strip())
            if isinstance(result, list):
                # 确保所有元素都是字符串
                return [str(item) for item in result]
            return []
        except (ValueError, SyntaxError):
            # 解析失败时记录警告并返回空列表
            import logging
            logging.warning(f"无法解析环境变量为列表: {env_value}")
            return []

    def get_merged_constraints(
        self,
        request_constraints: list[str] | None
    ) -> list[str]:
        """
        合并配置预设约束和请求约束

        Args:
            request_constraints: 请求中的约束参数

        Returns:
            合并后的约束列表
            - priority 模式：请求参数优先，无请求时使用配置
            - merge 模式：配置 + 请求合并（去重）
        """
        if request_constraints is not None:
            if self.constraint_merge_mode == "merge":
                # 叠加模式：合并配置和请求，去重
                return list(dict.fromkeys(self.default_constraints + request_constraints))
            else:
                # 优先级模式（默认）：只使用请求参数
                return request_constraints
        return self.default_constraints

    def get_merged_evaluation(
        self,
        request_evaluation: list[str] | None
    ) -> list[str]:
        """
        合并配置预设验收标准和请求验收标准

        Args:
            request_evaluation: 请求中的验收标准参数

        Returns:
            合并后的验收标准列表
            - priority 模式：请求参数优先，无请求时使用配置
            - merge 模式：配置 + 请求合并（去重）
        """
        if request_evaluation is not None:
            if self.constraint_merge_mode == "merge":
                # 叠加模式：合并配置和请求，去重
                return list(dict.fromkeys(self.default_evaluation + request_evaluation))
            else:
                # 优先级模式（默认）：只使用请求参数
                return request_evaluation
        return self.default_evaluation

    @field_validator('api_key')
    @classmethod
    def validate_api_key(cls, v: str) -> str:
        """验证 API 密钥格式"""
        if not v or not v.strip():
            raise ValueError("API 密钥不能为空")

        v = v.strip()

        # 基本长度验证
        if len(v) < 10:
            raise ValueError("API 密钥长度不能少于 10 个字符")

        # 基本格式验证
        if re.search(r'[\s\n\r\t]', v):
            raise ValueError("API 密钥不能包含空格或控制字符")

        return v

    @field_validator('base_url')
    @classmethod
    def validate_base_url(cls, v: str | None) -> str | None:
        """验证 Base URL 格式"""
        if v is None or not v.strip():
            return None

        v = v.strip()

        # 基本URL格式验证
        if not v.startswith(('http://', 'https://')):
            raise ValueError("Base URL 必须以 http:// 或 https:// 开头")

        # 简单的 URL 格式检查
        url_pattern = re.compile(
            r'^https?://'
            r'(?:(?:[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?\.)+[A-Z]{2,6}\.?|'
            r'localhost|'
            r'\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})'
            r'(?::\d+)?'
            r'(?:/?|[/?]\S+)$', re.IGNORECASE
        )

        if not url_pattern.match(v):
            raise ValueError(f"Base URL 格式无效: {v}")

        return v


class ServerConfig(BaseModel):
    """服务器配置"""

    # 服务器名称
    name: str = "Mirror of Wisdom MCP"

    # 日志级别
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = Field(
        default_factory=lambda: os.getenv("MIRROR_LOG_LEVEL", "INFO"),
        description="日志级别"
    )

    # 启用对话历史持久化
    enable_persistence: bool = Field(
        default_factory=lambda: os.getenv("MIRROR_ENABLE_PERSISTENCE", "true").lower() == "true",
        description="是否启用对话历史持久化到文件"
    )

    # 对话历史文件路径
    history_path: str = Field(
        default_factory=lambda: os.getenv(
            "MIRROR_HISTORY_PATH",
            str(Path.home() / ".mirror-of-wisdom" / "history.json")
        ),
        description="对话历史文件路径"
    )

    # 对话历史最大保存数
    max_history: int = Field(
        default_factory=lambda: int(os.getenv("MIRROR_MAX_HISTORY", "50")),
        ge=1,
        le=200,
        description="对话历史最大保存数"
    )

    # 启用角色切换功能
    enable_role_switching: bool = Field(
        default_factory=lambda: os.getenv("MIRROR_ENABLE_ROLE_SWITCHING", "true").lower() == "true",
        description="是否启用角色切换功能"
    )

    # 启用配置热重载
    enable_config_reload: bool = Field(
        default_factory=lambda: os.getenv("MIRROR_ENABLE_CONFIG_RELOAD", "false").lower() == "true",
        description="是否启用配置热重载"
    )

    # 启用质量自检
    enable_quality_check: bool = Field(
        default_factory=lambda: os.getenv("MIRROR_ENABLE_QUALITY_CHECK", "true").lower() == "true",
        description="是否启用质量自检"
    )

    # 质量阈值
    quality_threshold: float = Field(
        default_factory=lambda: float(os.getenv("MIRROR_QUALITY_THRESHOLD", "0.8")),
        ge=0.0,
        le=1.0,
        description="质量阈值"
    )


class FeatureConfig(BaseModel):
    """功能配置"""

    # 最大会话时长（小时）
    max_session_duration_hours: int = Field(
        default=24,
        ge=1,
        description="会话最大时长（小时）"
    )

    # 最大对话历史条数
    max_conversation_history: int = Field(
        default=50,
        ge=1,
        description="最大对话历史条数"
    )

    # 启用上下文压缩
    enable_context_compression: bool = Field(
        default=True,
        description="启用上下文压缩"
    )


# 全局配置实例
_mirror_config: MirrorConfig | None = None
_server_config: ServerConfig | None = None
_feature_config: FeatureConfig | None = None


def get_mirror_config() -> MirrorConfig:
    """获取求知镜 LLM 配置"""
    global _mirror_config
    if _mirror_config is None:
        _mirror_config = MirrorConfig()
    return _mirror_config


def get_server_config() -> ServerConfig:
    """获取服务器配置"""
    global _server_config
    if _server_config is None:
        _server_config = ServerConfig()
    return _server_config


def get_feature_config() -> FeatureConfig:
    """获取功能配置"""
    global _feature_config
    if _feature_config is None:
        _feature_config = FeatureConfig()
    return _feature_config


def reset_config():
    """重置配置（主要用于测试）"""
    global _mirror_config, _server_config, _feature_config
    _mirror_config = None
    _server_config = None
    _feature_config = None
