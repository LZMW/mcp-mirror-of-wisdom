"""
PromptGenerator 单元测试

测试元提示词生成器的核心逻辑，包括：
- 正常生成流程
- 兜底机制
- 响应清理逻辑
- Phase 5: 两阶段优化逻辑
"""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from mirror_of_wisdom.prompt_generator import PromptGenerator, META_PROMPT, get_prompt_generator, reset_generator


# ============================================================================
# Test: PromptGenerator 基础功能
# ============================================================================

class TestPromptGeneratorBasics:
    """测试 PromptGenerator 基础功能"""

    def test_meta_prompt_exists(self):
        """验证 META_PROMPT 常量存在且包含必要内容"""
        assert META_PROMPT is not None
        assert len(META_PROMPT) > 100
        assert "4D 流程" in META_PROMPT or "Deconstruction" in META_PROMPT
        assert "Output Template" in META_PROMPT

    def test_meta_prompt_format_placeholder(self):
        """验证 META_PROMPT 包含用户输入占位符"""
        assert "{user_input}" in META_PROMPT

    def test_prompt_generator_initialization(self):
        """测试 PromptGenerator 初始化"""
        generator = PromptGenerator()
        assert generator is not None
        assert hasattr(generator, "llm_client")
        assert hasattr(generator, "config")


# ============================================================================
# Test: 元提示词生成逻辑
# ============================================================================

class TestMetaPromptGeneration:
    """测试元提示词生成逻辑"""

    @pytest.mark.asyncio
    async def test_generate_expert_prompt_success(self, patch_llm_client):
        """测试成功生成专家提示词"""
        generator = PromptGenerator()

        # Patch LLM client
        with patch.object(generator, "llm_client", patch_llm_client):
            result = await generator.generate_expert_prompt_with_meta(
                user_requirement="我需要优化数据库查询性能"
            )

        # 验证返回结构
        assert result is not None
        assert "expert_prompt" in result
        assert "task_description" in result
        assert "generation_method" in result
        assert "quality_score" in result
        assert "timestamp" in result

        # 验证内容
        assert result["generation_method"] == "meta_prompt"
        assert result["quality_score"] == 1.0
        assert result["task_description"] == "我需要优化数据库查询性能"
        assert len(result["expert_prompt"]) > 100

        # 验证包含4D流程的关键词
        expert_prompt = result["expert_prompt"]
        assert "背景" in expert_prompt or "Context" in expert_prompt
        assert "目标" in expert_prompt or "Objective" in expert_prompt

    @pytest.mark.asyncio
    async def test_generate_expert_prompt_with_long_requirement(self, patch_llm_client):
        """测试处理长需求描述"""
        generator = PromptGenerator()

        long_requirement = """我需要帮助优化大型分布式系统的数据库性能。
系统特征：
- 订单表：5000万条数据
- 用户表：1000万条数据
- 日均查询量：100万次
- 查询类型：复杂关联查询
- 当前问题：响应时间超过5秒
- 优化目标：降低到500ms以内
- 约束条件：不能停机，必须在线优化
- 技术栈：MySQL 8.0, Redis缓存
"""

        with patch.object(generator, "llm_client", patch_llm_client):
            result = await generator.generate_expert_prompt_with_meta(long_requirement)

        # 验证处理长文本
        assert result["task_description"] == long_requirement
        assert len(result["expert_prompt"]) > 100

    @pytest.mark.asyncio
    async def test_generate_expert_prompt_calls_llm(self, patch_llm_client):
        """测试生成提示词时正确调用了 LLM"""
        generator = PromptGenerator()

        with patch.object(generator, "llm_client", patch_llm_client):
            await generator.generate_expert_prompt_with_meta("测试需求")

        # 验证 LLM 被调用
        assert patch_llm_client.call_count >= 1

        # 验证调用历史
        history = patch_llm_client.call_history
        assert len(history) >= 1


# ============================================================================
# Test: 兜底机制
# ============================================================================

class TestFallbackMechanism:
    """测试兜底机制（LLM 失败时的降级逻辑）"""

    @pytest.mark.asyncio
    async def test_fallback_on_llm_error(self):
        """测试 LLM 调用失败时触发兜底机制"""
        generator = PromptGenerator()

        # 创建一个会抛出异常的 mock client
        mock_client = MagicMock()
        mock_client.generate = AsyncMock(side_effect=Exception("LLM service unavailable"))

        with patch.object(generator, "llm_client", mock_client):
            result = await generator.generate_expert_prompt_with_meta("测试需求")

        # 验证兜底机制被触发
        assert result is not None
        assert result["generation_method"] == "static_fallback"
        assert result["quality_score"] == 0.7
        assert result["fallback"] is True
        assert "error" in result

        # 验证兜底提示词包含基本要素
        fallback_prompt = result["expert_prompt"]
        assert "通用AI助手" in fallback_prompt or "助手" in fallback_prompt
        assert "测试需求" in fallback_prompt

    @pytest.mark.asyncio
    async def test_fallback_on_timeout(self):
        """测试超时时触发兜底机制"""
        generator = PromptGenerator()

        # 创建模拟超时的 mock client
        import asyncio
        mock_client = MagicMock()
        mock_client.generate = AsyncMock(
            side_effect=asyncio.TimeoutError("Request timeout")
        )

        with patch.object(generator, "llm_client", mock_client):
            result = await generator.generate_expert_prompt_with_meta("测试需求")

        # 验证兜底机制
        assert result["generation_method"] == "static_fallback"
        assert result["fallback"] is True

    @pytest.mark.asyncio
    async def test_fallback_includes_original_requirement(self):
        """测试兜底提示词包含原始需求"""
        generator = PromptGenerator()

        mock_client = MagicMock()
        mock_client.generate = AsyncMock(side_effect=Exception("API Error"))

        test_requirement = "我需要设计一个微服务架构"
        with patch.object(generator, "llm_client", mock_client):
            result = await generator.generate_expert_prompt_with_meta(test_requirement)

        # 验证原始需求被保留
        assert test_requirement in result["expert_prompt"]
        assert result["task_description"] == test_requirement


# ============================================================================
# Test: 响应清理逻辑
# ============================================================================

class TestResponseCleaning:
    """测试响应清理逻辑（移除 markdown 代码块标记）"""

    @pytest.mark.asyncio
    async def test_clean_response_with_markdown_blocks(self, patch_llm_client):
        """测试清理带 ```markdown 标记的响应"""
        generator = PromptGenerator()

        # 创建返回带标记的响应的 mock
        mock_client = MagicMock()
        mock_response = """```markdown
# 1. 背景
测试内容
```"""
        mock_client.generate = AsyncMock(return_value=mock_response)

        with patch.object(generator, "llm_client", mock_client):
            result = await generator.generate_expert_prompt_with_meta("测试")

        # 验证标记被移除
        expert_prompt = result["expert_prompt"]
        assert not expert_prompt.startswith("```markdown")
        assert not expert_prompt.startswith("```")
        assert not expert_prompt.endswith("```")
        assert "1. 背景" in expert_prompt or "测试内容" in expert_prompt

    @pytest.mark.asyncio
    async def test_clean_response_with_triple_backticks(self, patch_llm_client):
        """测试清理只带 ``` 标记的响应"""
        generator = PromptGenerator()

        mock_client = MagicMock()
        mock_response = """```
# 测试提示词
内容
```"""
        mock_client.generate = AsyncMock(return_value=mock_response)

        with patch.object(generator, "llm_client", mock_client):
            result = await generator.generate_expert_prompt_with_meta("测试")

        # 验证清理
        expert_prompt = result["expert_prompt"]
        assert not expert_prompt.startswith("```")
        assert not expert_prompt.endswith("```")

    @pytest.mark.asyncio
    async def test_clean_normal_response_unchanged(self, patch_llm_client):
        """测试正常响应不被修改"""
        generator = PromptGenerator()

        mock_client = MagicMock()
        mock_response = """# 专家提示词

这是一个正常的提示词内容。
"""
        mock_client.generate = AsyncMock(return_value=mock_response)

        with patch.object(generator, "llm_client", mock_client):
            result = await generator.generate_expert_prompt_with_meta("测试")

        # 验证内容保持一致
        expert_prompt = result["expert_prompt"]
        assert "专家提示词" in expert_prompt


# ============================================================================
# Test: 全局实例管理
# ============================================================================

class TestGlobalInstance:
    """测试全局 PromptGenerator 实例管理"""

    def test_get_prompt_generator_singleton(self):
        """测试 get_prompt_generator 返回单例"""
        reset_generator()  # 确保从干净状态开始

        gen1 = get_prompt_generator()
        gen2 = get_prompt_generator()

        assert gen1 is gen2  # 应该是同一个实例

    def test_reset_generator(self):
        """测试 reset_generator 重置实例"""
        gen1 = get_prompt_generator()
        reset_generator()
        gen2 = get_prompt_generator()

        assert gen1 is not gen2  # 重置后应该是新实例


# ============================================================================
# Test: 边界条件
# ============================================================================

class TestEdgeCases:
    """测试边界条件和特殊情况"""

    @pytest.mark.asyncio
    async def test_empty_requirement(self, patch_llm_client):
        """测试空需求描述"""
        generator = PromptGenerator()

        with patch.object(generator, "llm_client", patch_llm_client):
            result = await generator.generate_expert_prompt_with_meta("")

        # 应该仍然返回结果（LLM可能会生成通用提示词）
        assert result is not None
        assert "expert_prompt" in result

    @pytest.mark.asyncio
    async def test_very_short_requirement(self, patch_llm_client):
        """测试极短需求描述"""
        generator = PromptGenerator()

        with patch.object(generator, "llm_client", patch_llm_client):
            result = await generator.generate_expert_prompt_with_meta("测试")

        assert result is not None
        assert len(result["expert_prompt"]) > 50

    @pytest.mark.asyncio
    async def test_special_characters_in_requirement(self, patch_llm_client):
        """测试包含特殊字符的需求"""
        generator = PromptGenerator()

        special_requirement = "测试特殊字符：@#$%^&*()_+ 中文、English、日本語"
        with patch.object(generator, "llm_client", patch_llm_client):
            result = await generator.generate_expert_prompt_with_meta(special_requirement)

        # 验证特殊字符被保留
        assert result["task_description"] == special_requirement


# ============================================================================
# Test: 返回结构验证
# ============================================================================

class TestResponseStructure:
    """测试返回结构的完整性和正确性"""

    @pytest.mark.asyncio
    async def test_response_contains_all_required_fields(self, patch_llm_client):
        """测试响应包含所有必需字段"""
        generator = PromptGenerator()

        with patch.object(generator, "llm_client", patch_llm_client):
            result = await generator.generate_expert_prompt_with_meta("测试需求")

        required_fields = [
            "expert_prompt",
            "task_description",
            "generation_method",
            "quality_score",
            "timestamp"
        ]

        for field in required_fields:
            assert field in result, f"缺少必需字段: {field}"

    @pytest.mark.asyncio
    async def test_timestamp_format(self, patch_llm_client):
        """测试时间戳格式"""
        generator = PromptGenerator()

        with patch.object(generator, "llm_client", patch_llm_client):
            result = await generator.generate_expert_prompt_with_meta("测试")

        from datetime import datetime
        # 验证时间戳可以被解析
        try:
            datetime.fromisoformat(result["timestamp"])
        except ValueError:
            pytest.fail("时间戳格式不正确")

    @pytest.mark.asyncio
    async def test_quality_score_range(self, patch_llm_client):
        """测试质量评分在合理范围内"""
        generator = PromptGenerator()

        with patch.object(generator, "llm_client", patch_llm_client):
            result = await generator.generate_expert_prompt_with_meta("测试")

        score = result["quality_score"]
        assert 0.0 <= score <= 1.0, f"质量评分超出范围: {score}"


# ============================================================================
# Test: Phase 5 两阶段优化逻辑
# ============================================================================

class TestTwoStageOptimization:
    """测试 Phase 5 两阶段提示词优化功能"""

    @pytest.mark.asyncio
    async def test_two_stage_optimization_with_constraints(self, patch_llm_client):
        """测试带自定义约束的两阶段优化"""
        generator = PromptGenerator()

        # 创建 mock 客户端，第一次返回基础提示词，第二次返回优化后的提示词
        mock_client = MagicMock()
        base_prompt = "# 基础专家提示词\n\n这是一个基础的专家提示词。"

        # 第二次调用返回包含约束的优化提示词
        optimized_prompt = """# 优化后的专家提示词

## 自定义约束
1. 你是PostgreSQL专家
2. 必须使用异步编程

## 原始内容
这是一个基础的专家提示词，已整合自定义约束。
"""

        # 模拟两次调用：第一阶段生成基础，第二阶段优化
        call_count = [0]
        async def mock_generate(prompt, **kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                return base_prompt
            else:
                return optimized_prompt

        mock_client.generate = AsyncMock(side_effect=mock_generate)

        with patch.object(generator, "llm_client", mock_client):
            result = await generator.generate_expert_prompt_with_meta(
                user_requirement="我需要优化数据库",
                custom_constraints=["你是PostgreSQL专家", "必须使用异步编程"]
            )

        # 验证两阶段优化
        assert result["generation_method"] == "two_stage"
        assert result["quality_score"] == 1.0
        # 验证调用了两次 LLM（第一阶段 + 第二阶段）
        assert call_count[0] == 2

    @pytest.mark.asyncio
    async def test_two_stage_optimization_with_evaluation(self, patch_llm_client):
        """测试带自定义验收标准的两阶段优化"""
        generator = PromptGenerator()

        mock_client = MagicMock()
        call_count = [0]
        async def mock_generate(prompt, **kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                return "# 基础提示词"
            else:
                return "# 优化后提示词\n\n已整合验收标准：建议必须具体可执行"

        mock_client.generate = AsyncMock(side_effect=mock_generate)

        with patch.object(generator, "llm_client", mock_client):
            result = await generator.generate_expert_prompt_with_meta(
                user_requirement="测试需求",
                custom_evaluation=["建议必须具体可执行", "需要提供代码示例"]
            )

        # 验证
        assert result["generation_method"] == "two_stage"
        assert call_count[0] == 2

    @pytest.mark.asyncio
    async def test_no_custom_requirements_skips_second_stage(self, patch_llm_client):
        """测试无自定义要求时跳过第二阶段"""
        generator = PromptGenerator()

        call_count = [0]
        async def mock_generate(prompt, **kwargs):
            call_count[0] += 1
            return "# 基础专家提示词"

        mock_client = MagicMock()
        mock_client.generate = AsyncMock(side_effect=mock_generate)

        with patch.object(generator, "llm_client", mock_client):
            result = await generator.generate_expert_prompt_with_meta(
                user_requirement="测试需求"
            )

        # 验证只调用了一次（跳过第二阶段）
        assert result["generation_method"] == "meta_prompt"
        assert call_count[0] == 1

    @pytest.mark.asyncio
    async def test_both_constraints_and_evaluation(self, patch_llm_client):
        """测试同时提供约束和验收标准"""
        generator = PromptGenerator()

        call_count = [0]
        async def mock_generate(prompt, **kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                return "# 基础"
            else:
                return "# 优化后（包含约束和标准）"

        mock_client = MagicMock()
        mock_client.generate = AsyncMock(side_effect=mock_generate)

        with patch.object(generator, "llm_client", mock_client):
            result = await generator.generate_expert_prompt_with_meta(
                user_requirement="测试",
                custom_constraints=["约束1", "约束2"],
                custom_evaluation=["标准1", "标准2"]
            )

        assert result["generation_method"] == "two_stage"
        assert call_count[0] == 2


class TestTwoStageHelpers:
    """测试两阶段优化的辅助方法"""

    def test_format_list_with_valid_items(self):
        """测试格式化有效列表"""
        generator = PromptGenerator()
        items = ["约束1", "约束2", "约束3"]
        result = generator._format_list(items)
        assert "1. 约束1" in result
        assert "2. 约束2" in result
        assert "3. 约束3" in result

    def test_format_list_with_empty_list(self):
        """测试格式化空列表"""
        generator = PromptGenerator()
        result = generator._format_list([])
        assert result == ""

    def test_format_list_with_none(self):
        """测试格式化 None"""
        generator = PromptGenerator()
        result = generator._format_list(None)
        assert result == ""

    def test_clean_markdown_blocks_removes_markers(self):
        """测试清理 markdown 代码块标记"""
        generator = PromptGenerator()

        # 测试 ```markdown
        text1 = "```markdown\n# 内容\n```"
        result1 = generator._clean_markdown_blocks(text1)
        assert not result1.startswith("```")
        assert "# 内容" in result1

        # 测试 ```
        text2 = "```\n# 内容\n```"
        result2 = generator._clean_markdown_blocks(text2)
        assert not result2.startswith("```")

    def test_clean_markdown_blocks_preserves_content(self):
        """测试清理时保留内容"""
        generator = PromptGenerator()
        text = "# 专家提示词\n\n这是重要内容"
        result = generator._clean_markdown_blocks(text)
        assert "专家提示词" in result
        assert "重要内容" in result


# ============================================================================
# Test: Phase 6 专家思维系统
# ============================================================================

class TestPhase6ExpertThinkingSystem:
    """测试 Phase 6 专家思维系统功能"""

    def test_meta_prompt_contains_thinking_chain_rules(self):
        """验证元提示词包含思维链执行规则 (6.0)"""
        # 验证包含思维链相关内容
        assert "6.0" in META_PROMPT or "思维链" in META_PROMPT
        assert "始终展示思维过程" in META_PROMPT or "展示思考过程" in META_PROMPT

    def test_meta_prompt_contains_thinking_sections(self):
        """验证元提示词包含完整的思维系统章节 (6.1-6.6)"""
        # 验证包含各个思维系统子章节
        expected_sections = [
            "6.1",  # 知识对齐与背景深挖
            "6.2",  # 核心逻辑解构与方案构建
            "6.3",  # 交叉验证与迭代优化
            "6.4",  # 响应生成
            "6.5",  # 首次对话收敛规则
            "6.6",  # 思维链输出模板
        ]

        meta_content = META_PROMPT
        for section in expected_sections:
            assert section in meta_content, f"缺少章节: {section}"

    def test_meta_prompt_contains_first_dialogue_protocol(self):
        """验证元提示词包含首次对话协议 (5.1)"""
        assert "5.1" in META_PROMPT
        assert "首次对话协议" in META_PROMPT or "首次对话" in META_PROMPT

    def test_meta_prompt_contains_task_completion_mechanism(self):
        """验证元提示词包含任务完成与终止机制 (5.3)"""
        assert "5.3" in META_PROMPT
        assert "任务完成" in META_PROMPT or "终止" in META_PROMPT

    def test_meta_prompt_thinking_chain_output_template(self):
        """验证思维链输出模板格式正确"""
        # 验证包含思维链输出模板
        assert "思维过程" in META_PROMPT or "思维链" in META_PROMPT
        # 验证包含4步思维结构
        assert "知识对齐" in META_PROMPT
        assert "逻辑解构" in META_PROMPT or "核心逻辑" in META_PROMPT
        assert "交叉验证" in META_PROMPT
        assert "执行策略" in META_PROMPT or "最终响应" in META_PROMPT

    def test_meta_prompt_first_dialogue_convergence(self):
        """验证首次对话收敛规则 (6.5)"""
        # 验证首次对话时思维链精简
        assert "6.5" in META_PROMPT
        assert "首次对话收敛" in META_PROMPT or "精简" in META_PROMPT
        # 验证包含3个问题模式
        assert "问题" in META_PROMPT

    @pytest.mark.asyncio
    async def test_generated_prompt_contains_thinking_system(self, patch_llm_client):
        """测试生成的专家提示词包含思维系统"""
        generator = PromptGenerator()

        # 创建返回完整思维系统的 mock
        mock_client = MagicMock()
        mock_response = """# 1. 背景
用户需要技术专家帮助优化数据库查询性能。

# 2. 目标
作为资深数据库优化专家，提供专业的SQL查询优化方案。

# 3. 风格与语调
*   **风格**: 技术严谨，数据驱动
*   **语调**: 专业、客观

# 4. 受众
需要解决数据库性能问题的开发者

# 5. 响应规范

## 5.1 首次对话协议
在首次对话时，你必须按以下格式回复...

## 5.2 执行步骤
1. 分析慢查询日志
2. 检查现有索引

## 5.3 任务完成与终止
作为专家咨询，你的目标是**解决用户的问题**。

## 5.4 评估标准
- 查询响应时间降低50%以上

## 5.5 格式与约束
- 输出格式：Markdown
- **禁止**：不建议删除数据

# 6. 专家思维系统

## 6.0 思维链执行规则
**核心原则**：在生成任何响应前，必须执行以下思维链（内部强制执行），并且**始终展示思维过程**。

## 6.1 知识对齐与背景深挖
*   **核心概念召回**: 检索并确认关于任务主题的最新定义
*   **上下文关联验证**: 回顾"背景"中的信息

## 6.2 核心逻辑解构与方案构建
*   **任务本质识别**: 精准识别任务的核心挑战
*   **关键要素提取**: 提取并优先级排序所有关键要素

## 6.3 交叉验证与迭代优化
*   **漏洞与风险审查**: 对初步方案进行严苛审查
*   **创新与润色**: 提出更具创意的优化建议

## 6.4 响应生成
根据迭代优化后的最优方案，按照"## 5.2 执行步骤"的格式要求生成具体响应。

## 6.5 首次对话收敛规则
当检测到"首次对话"时，将思维链精简为"分析概述"。

## 6.6 思维链输出模板
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
"""
        mock_client.generate = AsyncMock(return_value=mock_response)

        with patch.object(generator, "llm_client", mock_client):
            result = await generator.generate_expert_prompt_with_meta(
                user_requirement="我需要优化数据库查询性能"
            )

        # 验证生成的提示词包含思维系统
        expert_prompt = result["expert_prompt"]
        assert "6. 专家思维系统" in expert_prompt or "思维系统" in expert_prompt
        assert "6.0" in expert_prompt or "思维链执行规则" in expert_prompt
        assert "6.6" in expert_prompt or "思维链输出模板" in expert_prompt

    @pytest.mark.asyncio
    async def test_generated_prompt_contains_task_completion(self, patch_llm_client):
        """测试生成的提示词包含任务完成机制"""
        generator = PromptGenerator()

        mock_client = MagicMock()
        mock_response = """# 专家提示词

## 5.3 任务完成与终止（重要）
作为专家咨询，你的目标是**解决用户的问题**，而非提供无限聊天服务。

**任务完成判断标准**：
- 用户表示问题已解决
- 你已给出完整的解决方案

**任务完成时的行为**：
1. 确认用户是否还有相关问题
2. 如果用户确认完成，输出以下终止声明

**重要原则**：
- **不要**像聊天机器人一样问"还有什么可以帮您的吗？"
- **不要**在会话中处理与原任务无关的新问题
"""
        mock_client.generate = AsyncMock(return_value=mock_response)

        with patch.object(generator, "llm_client", mock_client):
            result = await generator.generate_expert_prompt_with_meta("测试需求")

        # 验证包含任务完成机制
        expert_prompt = result["expert_prompt"]
        assert "任务完成" in expert_prompt
        assert "终止" in expert_prompt

    @pytest.mark.asyncio
    async def test_generated_prompt_contains_first_dialogue_protocol(self, patch_llm_client):
        """测试生成的提示词包含首次对话协议"""
        generator = PromptGenerator()

        mock_client = MagicMock()
        mock_response = """# 专家提示词

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
"""
        mock_client.generate = AsyncMock(return_value=mock_response)

        with patch.object(generator, "llm_client", mock_client):
            result = await generator.generate_expert_prompt_with_meta("测试需求")

        # 验证包含首次对话协议
        expert_prompt = result["expert_prompt"]
        assert "首次对话协议" in expert_prompt or "5.1" in expert_prompt
        assert "你好！我是" in expert_prompt or "专家角色" in expert_prompt
        # 验证包含3个问题模式
        assert "1." in expert_prompt and "2." in expert_prompt and "3." in expert_prompt


class TestPhase6ProductPositioning:
    """测试 Phase 6 产品定位相关功能"""

    def test_meta_prompt_expert_consultation_positioning(self):
        """验证元提示词体现专家咨询工具定位（非聊天机器人）"""
        # 验证包含"专家咨询"相关表述
        assert "专家咨询" in META_PROMPT or "咨询" in META_PROMPT
        # 验证包含任务导向（非无限聊天）
        assert "任务完成" in META_PROMPT or "解决问题" in META_PROMPT

    def test_meta_prompt_rejects_chatbot_behavior(self):
        """验证元提示词明确拒绝聊天机器人行为"""
        # 验证包含禁止聊天机器人模式的指令
        content = META_PROMPT
        # 检查是否包含"不要像聊天机器人"或类似表述
        has_reject_chatbot = (
            "不要像聊天机器人" in content or
            "不是聊天机器人" in content or
            "万能助手" in content and "不是" in content
        )
        # 或者检查是否有明确的专家咨询定位
        has_expert_positioning = (
            "专家咨询" in content or
            "解决问题" in content and "任务完成" in content
        )

        assert has_reject_chatbot or has_expert_positioning

    @pytest.mark.asyncio
    async def test_expert_prompt_terminates_after_completion(self, patch_llm_client):
        """测试专家提示词在任务完成后明确终止"""
        generator = PromptGenerator()

        mock_client = MagicMock()
        mock_response = """# 专家提示词

## 5.3 任务完成与终止
**任务完成判断标准**：
- 用户表示问题已解决
- 你已给出完整的解决方案

**任务完成时的行为**：
如果用户确认完成，输出以下终止声明：

```
---
【任务完成】
您的问题已得到解决。如果还有其他需求，请重新创建新的专家会话。

再次提醒：每次处理不同领域的问题时，请使用求知镜创建对应的专家会话，以获得最专业的指导。

感谢您的使用！
---
```
"""
        mock_client.generate = AsyncMock(return_value=mock_response)

        with patch.object(generator, "llm_client", mock_client):
            result = await generator.generate_expert_prompt_with_meta("测试需求")

        expert_prompt = result["expert_prompt"]
        # 验证包含终止声明
        assert "【任务完成】" in expert_prompt or "任务完成" in expert_prompt
        assert "重新创建新的专家会话" in expert_prompt or "创建对应的专家会话" in expert_prompt
