"""提示词生成器模块

仅支持元提示词模式（Phase 2）：使用4D流程生成专家提示词
两阶段优化（Phase 5）：支持自定义约束和验收标准

⚠️ 规则引擎模式已删除（Phase 4 架构重构）
"""

import json
import logging
from pathlib import Path
from typing import Literal, Optional

from .llm_client import get_llm_client
from .config import get_mirror_config, get_server_config

logger = logging.getLogger(__name__)


# ============================================================================
# 元提示词（Meta-Prompt）- Phase 2 核心功能
# ============================================================================

META_PROMPT = """# Role
你是一位精通提示工程的专家 AI（求知镜）。你的任务是接收我（本地ai）的原始需求，并将其转化为一个结构严谨、效果卓越的专家级提示词。

# Workflow (思维处理流程)
在生成最终提示词之前，请务必在后台严格执行以下 **4D 流程** 对我（本地ai）的需求进行处理：

1.  **Deconstruction (解构分析)**：提取核心意图、关键要素、背景信息；确定输出要求与限制。
2.  **Diagnosis (问题诊断)**：检查清晰度差距；验证具体性/完整性；评估结构需求与平台适配性。
3.  **Development (方案开发)**：选择最佳技术（COT/Few-Shot等）；分配合适角色；构建逻辑结构并注入约束。
4.  **Delivery (成果交付)**：格式化最终提示；进行逻辑与完整性校验；提供使用指导。

# Constraints (关键约束)
*   **E_2 规则**：在构建约束条件时，必须执行 "[E]xplicit constraints"，即明确包含否定约束（禁止项、排除条件）。
*   **输出格式**：不要解释 4D 流程的具体内容，直接输出优化后的提示词。最终输出必须严格遵守下方的 Markdown 模板。

# Output Template (输出模板)

```markdown
# 1. 背景 (Context)
[详细描述任务环境、当前遇到的问题及具体的输入数据]

# 2. 目标 (Objective)
[核心指令，包含预期达成的深度洞察和具体行动]

# 3. 风格与语调 (Style & Tone)
*   **风格**: [具体的写作/编码风格，设定内容的人格特征及吸引点]
*   **语调**: [情感色彩，包含心理距离及共情水平]

# 4. 受众 (Audience)
[受众画像，明确其核心痛点与心理预期]

# 5. 响应 (Response)
## 5.1 执行步骤 (Steps)

### 🔍 首次对话协议（必执行）
在首次对话时，你必须按以下格式回复：

**格式模板**：
"你好！我是[专家角色]，擅长[核心能力]。为了更准确地帮助你，我想先确认：
1. [根据任务类型生成第1个关键问题]
2. [根据任务类型生成第2个关键问题]
3. [根据任务类型生成第3个关键问题]

如果你已经提供了这些信息，我会直接开始分析。"

**提问指南**（根据任务类型动态选择）：
- **技术开发类**：技术栈版本、错误信息、预期效果
- **创意设计类**：目标受众、风格调性、使用场景
- **商业战略类**：行业背景、目标市场、核心资源
- **学习辅导类**：当前水平、学习目标、可用时间
- **其他类型**：根据具体任务灵活判断

### 📋 后续执行步骤
[逻辑清晰的执行路径]

## 5.2 评估标准 (Evaluation)
[可量化的质量验收指标]

## 5.3 格式与约束
[输出格式 + 明确包含否定约束（禁止项、排除条件）]
```

# Input (用户需求)
{user_input}

请严格按照上述模板生成专家提示词：
"""



class PromptGenerator:
    """提示词生成器（仅元提示词模式）"""

    def __init__(self):
        """初始化提示词生成器"""
        self.llm_client = get_llm_client()
        self.config = get_mirror_config()
        self.server_config = get_server_config()

    async def generate_expert_prompt_with_meta(
        self,
        user_requirement: str,
        custom_constraints: Optional[list[str]] = None,
        custom_evaluation: Optional[list[str]] = None,
    ) -> dict:
        """
        使用元提示词生成专家提示词（Phase 5 两阶段优化）

        这是求知镜的核心功能：
        1. 接收本地AI的原始需求
        2. 使用元提示词（4D流程）生成基础专家提示词
        3. （可选）根据自定义要求进行第二阶段优化
        4. 返回生成的专家提示词，用于后续会话

        Args:
            user_requirement: 本地AI的原始需求描述
            custom_constraints: 自定义约束条件列表（可选），用于指定专家定位或技术限制
            custom_evaluation: 自定义验收标准列表（可选），用于指定质量要求

        Returns:
            包含以下字段的字典：
            - expert_prompt: 生成的专家提示词（Markdown格式）
            - task_description: 原始任务描述
            - generation_method: "two_stage" 或 "meta_prompt"（生成方法标识）
            - quality_score: 质量评分
            - timestamp: 生成时间戳
        """
        logger.info(f"使用元提示词生成专家提示词: {len(user_requirement)} 字符")

        try:
            # ========== 第一阶段：生成基础专家提示词 ==========
            base_prompt = await self._generate_base_prompt(user_requirement)

            # ========== 第二阶段：优化整合（如果有额外要求） ==========
            if custom_constraints or custom_evaluation:
                logger.info("启用两阶段优化：整合自定义约束和验收标准")
                final_prompt = await self._optimize_with_custom_requirements(
                    base_prompt=base_prompt,
                    custom_constraints=custom_constraints,
                    custom_evaluation=custom_evaluation,
                )
                generation_method = "two_stage"
            else:
                final_prompt = base_prompt
                generation_method = "meta_prompt"

            # 记录生成的提示词长度
            prompt_length = len(final_prompt)
            logger.info(f"提示词生成完成: {prompt_length} 字符 (方法: {generation_method})")

            # 返回结果
            result = {
                "expert_prompt": final_prompt,
                "task_description": user_requirement,
                "generation_method": generation_method,
                "quality_score": 1.0,
                "timestamp": __import__("datetime").datetime.now().isoformat()
            }

            return result

        except Exception as e:
            logger.error(f"元提示词生成失败: {e}")
            # 回退到静态通用助手提示词
            logger.warning("回退到静态通用助手模式")

            # 静态兜底提示词（通用助手）
            fallback_prompt = f"""# 通用AI助手

## 任务背景
{user_requirement}

## 专家角色设定
你是一位知识渊博、乐于助人的AI助手。你具备：
- 跨学科知识整合能力
- 清晰的逻辑思维
- 友好耐心的沟通风格
- 灵活适应不同需求的能力

## 工作原则
1. 仔细理解用户的需求
2. 提供全面准确的回答
3. 承认知识的局限性
4. 引导用户深入思考

现在请以通用AI助手的身份，针对上述任务提供帮助。
"""

            return {
                "expert_prompt": fallback_prompt,
                "task_description": user_requirement,
                "generation_method": "static_fallback",
                "quality_score": 0.7,
                "timestamp": __import__("datetime").datetime.now().isoformat(),
                "fallback": True,
                "error": str(e)
            }

    async def _generate_base_prompt(self, user_requirement: str) -> str:
        """
        第一阶段：生成基础专家提示词

        Args:
            user_requirement: 用户的原始需求描述

        Returns:
            清理后的基础专家提示词（Markdown格式）
        """
        # 构建元提示词请求
        meta_prompt_request = META_PROMPT.format(user_input=user_requirement)

        # 调用LLM生成专家提示词
        response = await self.llm_client.generate(
            prompt=meta_prompt_request,
            response_format="text"
        )

        # 清理响应（移除可能的markdown代码块标记）
        return self._clean_markdown_blocks(response)

    async def _optimize_with_custom_requirements(
        self,
        base_prompt: str,
        custom_constraints: Optional[list[str]],
        custom_evaluation: Optional[list[str]],
    ) -> str:
        """
        第二阶段：优化整合额外要求（上下文拼接法）

        将基础提示词与用户的自定义要求整合，生成最终优化后的专家提示词。

        Args:
            base_prompt: 第一阶段生成的基础专家提示词
            custom_constraints: 自定义约束条件列表
            custom_evaluation: 自定义验收标准列表

        Returns:
            优化后的专家提示词（Markdown格式）
        """
        # 构建包含上下文的复合 Prompt（增强鲁棒性）
        optimization_request = f"""我需要你基于新的要求，优化以下已生成的提示词。

=== 待优化的提示词 ===
{base_prompt}
====================

=== 新的优化要求 ===
自定义验收标准：{self._format_list(custom_evaluation) or "无"}
自定义约束：{self._format_list(custom_constraints) or "无"}

## 重要指令

**当你接到优化任务后，要结合给定优化要求或条件，尽可能遵照，实现最优优化策略。**

请严格遵循以下原则：
1. **充分理解**：仔细分析待优化的提示词核心目标和结构
2. **冲突解决**：当新要求与原有内容冲突时，新要求优先级更高
3. **无缝整合**：将新要求自然融入提示词的合适位置，保持结构完整
4. **统一风格**：确保优化后的提示词格式、语调与原文保持一致
5. **增强而非替换**：在保留原有价值的基础上，用新要求增强提示词

请结合新要求，重写并优化上述提示词。仅返回优化后的内容，不要包含解释。"""

        # 正常调用 generate
        optimized = await self.llm_client.generate(
            prompt=optimization_request,
            response_format="text"
        )

        return self._clean_markdown_blocks(optimized)

    def _format_list(self, items: Optional[list[str]]) -> str:
        """
        格式化列表为字符串（辅助方法）

        Args:
            items: 字符串列表，可能为 None

        Returns:
            格式化后的字符串，如 "1. item1\\n2. item2"
        """
        if not items:
            return ""
        return "\\n".join(f"{i+1}. {item}" for i, item in enumerate(items))

    def _clean_markdown_blocks(self, text: str) -> str:
        """
        清理响应中的 markdown 代码块标记（辅助方法）

        移除可能存在的 ```markdown 或 ``` 标记。

        Args:
            text: 原始文本

        Returns:
            清理后的文本
        """
        text = text.strip()
        if text.startswith("```markdown"):
            text = text[11:]
        if text.startswith("```"):
            text = text[3:]
        if text.endswith("```"):
            text = text[:-3]
        return text.strip()


# 全局实例
_generator: PromptGenerator | None = None


def get_prompt_generator() -> PromptGenerator:
    """获取提示词生成器实例"""
    global _generator
    if _generator is None:
        _generator = PromptGenerator()
    return _generator


def reset_generator():
    """重置生成器（主要用于测试）"""
    global _generator
    _generator = None
