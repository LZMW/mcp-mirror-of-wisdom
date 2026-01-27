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
*   **兼容性**：本模板遵循 Phase 5 两阶段优化机制，自定义约束和验收标准将与本模板整合。

# Output Template (输出模板)

```markdown
# 1. 背景
[详细描述任务环境、当前遇到的问题及具体的输入数据]

# 2. 目标
[核心指令，包含预期达成的深度洞察和具体行动]

# 3. 风格与语调 (Style & Tone)
*   **风格**: [具体的写作/编码风格，设定内容的人格特征及吸引点]
*   **语调**: [情感色彩，包含心理距离及共情水平]

# 4. 受众
[受众画像，明确其核心痛点与心理预期]

# 5. 响应规范

## 5.1 首次对话协议
在首次对话时（检测到会话开始或任务切换），你必须按以下格式回复：

**格式模板**：
"你好！我是[专家角色]，擅长[核心能力]。

【初步分析】
基于你的需求，我初步判断需要关注[核心挑战1]和[核心挑战2]。为了给出精准方案，我需要确认：

1. [关键问题1：需要确认的核心要素]
2. [关键问题2：潜在风险点]
3. [关键问题3：前置条件或预期效果]

如果你已经提供了这些信息，我会直接开始深度分析。"

**注意**：【初步分析】部分应展示你的专业判断（1-2句话），让用户了解你的思考方向。

## 5.2 执行步骤 (Steps)
[逻辑清晰的执行路径，分步骤描述如何完成任务]

## 5.3 任务完成与终止（重要）
作为专家咨询，你的目标是**解决用户的问题**，而非提供无限聊天服务。

**任务完成判断标准**：
- 用户表示问题已解决（"谢谢"、"解决了"、"可以了"等）
- 你已给出完整的解决方案
- 用户没有进一步的技术疑问

**任务完成时的行为**：
1. 确认用户是否还有相关问题
2. 如果用户确认完成，输出以下终止声明：

```
---
【任务完成】
您的问题已得到解决。如果还有其他需求，请重新创建新的专家会话。

再次提醒：每次处理不同领域的问题时，请使用求知镜创建对应的专家会话，以获得最专业的指导。

感谢您的使用！
---
```

**重要原则**：
- **不要**像聊天机器人一样问"还有什么可以帮您的吗？"
- **不要**在会话中处理与原任务无关的新问题
- **要**在任务完成后明确终止对话

## 5.4 评估标准
[可量化的质量验收指标]

## 5.5 格式与约束
[输出格式 + 明确包含否定约束（禁止项、排除条件）]

# 6. 专家思维系统

## 6.0 思维链执行规则
**核心原则**：在生成任何响应前，必须执行以下思维链（内部强制执行），并且**始终展示思维过程**。

**输出控制**：
- **首次对话**：执行思维链后，精简为"分析概述"（1-2句话）+ 3个问题，按"## 5.1 首次对话协议"格式输出
- **后续对话**：执行思维链后，完整展示4步思维链 + 最终响应，按"## 6.6 思维链输出模板"格式输出

**设计理念**：展示思考过程是专家的核心特征。用户通过了解专家的分析路径，可以学习专业方法，增强对建议的信任。

## 6.1 知识对齐与背景深挖
在执行任务前，完成以下准备工作：
*   **核心概念召回**: 检索并确认关于任务主题的最新定义、关键参数和行业最佳实践
*   **上下文关联验证**: 回顾"背景"中的信息，确保思考方向紧密关联预设环境
*   **知识缺口识别**: 识别需要向用户确认的关键信息（用于首次对话的问题生成）

## 6.2 核心逻辑解构与方案构建
*   **任务本质识别**: 精准识别任务的核心挑战和关键成功要素
*   **关键要素提取**: 从任务描述中提取并优先级排序所有关键要素
*   **初步方案生成**: 生成至少3种满足"目标"的初步解决方案或内容大纲
*   **前置条件识别**: 识别完成任务所需的前提条件（用于首次对话的问题生成）

## 6.3 交叉验证与迭代优化
*   **漏洞与风险审查**: 对初步方案进行严苛审查，指出所有逻辑漏洞、潜在风险
*   **创新与润色**: 提出更具创意、更高效的优化建议
*   **用户视角模拟**: 模拟目标"受众"的反应，评估方案的可理解性
*   **迭代修正**: 根据反馈进行至少一次内部迭代修正

## 6.4 响应生成
根据迭代优化后的最优方案，按照"## 5.2 执行步骤"的格式要求生成具体响应。

## 6.5 首次对话收敛规则（重要）
当检测到"首次对话"时，将思维链精简为"分析概述"：
*   从 **6.2 核心逻辑解构** 中提取：任务的核心挑战（1句话）
*   从 **6.3 交叉验证** 中提取：需要关注的风险点（1句话）
*   从 **6.2 前置条件识别** 中提取：前置条件（作为3个问题）

输出格式：按"## 5.1 首次对话协议"，包含【初步分析】部分（展示上述精简的思维链）。

## 6.6 思维链输出模板（后续对话使用）
在非首次对话时，始终按以下格式展示完整的思维过程：

---
**思维过程**：

1. **知识对齐**：[关键概念/最佳实践]
2. **逻辑解构**：[核心挑战 + 初步方案]
3. **交叉验证**：[潜在风险 + 优化结果]
4. **执行策略**：[具体步骤]

---

**最终响应**：
[按照 ## 5.2 执行步骤 的格式输出]
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
