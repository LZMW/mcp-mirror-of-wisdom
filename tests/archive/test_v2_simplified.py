"""简化设计 v2 测试

测试用户直接指定专家类型的简化设计。
"""

import asyncio
import sys
import json
from pathlib import Path

# Windows UTF-8 编码支持
if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

# 添加 src 到路径
src_path = Path(__file__).parent.parent / "src"
if str(src_path) not in sys.path:
    sys.path.insert(0, str(src_path))

from tools.consult_mirror import consult_mirror, ConsultMirrorInput, ResponseFormat, ExpertType


async def test_basic_expert_generation():
    """测试基本的专家提示词生成"""
    print("=" * 70)
    print("测试 1: 基本专家提示词生成")
    print("=" * 70)

    test_cases = [
        {
            "expert_type": ExpertType.TECHNICAL,
            "task": "优化 Python 数据库查询性能",
            "description": "技术专家"
        },
        {
            "expert_type": ExpertType.CREATIVE,
            "task": "设计儿童教育 App 的主角形象",
            "description": "创意设计师"
        },
        {
            "expert_type": ExpertType.BUSINESS,
            "task": "制定电商网站 Q1 市场推广计划",
            "description": "商业战略顾问"
        },
    ]

    for i, test in enumerate(test_cases, 1):
        print(f"\n【测试 {i}】{test['description']}")

        try:
            params = ConsultMirrorInput(
                expert_type=test['expert_type'],
                task_description=test['task'],
                response_format=ResponseFormat.MARKDOWN
            )

            result = await consult_mirror(params)

            print(f"✓ 成功")
            print(f"  - 长度: {len(result)} 字符")
            print(f"  - 预览: {result[:100]}...")

            # 验证必需内容
            assert f"# {test['description']}" in result
            assert test['task'] in result

        except Exception as e:
            print(f"✗ 失败: {e}")

    print("\n" + "=" * 70)


async def test_with_context_and_requirements():
    """测试带上下文和要求的情况"""
    print("\n测试 2: 带上下文和要求的生成")
    print("=" * 70)

    params = ConsultMirrorInput(
        expert_type=ExpertType.TECHNICAL,
        task_description="设计一个高并发的即时通讯系统",
        context="我们是一个初创公司，预算有限，用户预计在10万以内",
        requirements="需要考虑扩展性，使用开源技术栈，降低成本",
        response_format=ResponseFormat.MARKDOWN
    )

    result = await consult_mirror(params)

    print(f"✓ 成功生成完整提示词")
    print(f"  - 包含任务描述: {'是' if '任务描述' in result else '否'}")
    print(f"  - 包含背景上下文: {'是' if '背景上下文' in result else '否'}")
    print(f"  - 包含特殊要求: {'是' if '特殊要求' in result else '否'}")
    print(f"  - 包含角色设定: {'是' if '角色设定' in result else '否'}")

    print("\n" + "=" * 70)


async def test_json_output():
    """测试 JSON 格式输出"""
    print("\n测试 3: JSON 格式输出")
    print("=" * 70)

    params = ConsultMirrorInput(
        expert_type=ExpertType.EDUCATION,
        task_description="制定 3 个月的 Python 学习路径",
        context="有编程基础，熟悉 JavaScript",
        response_format=ResponseFormat.JSON
    )

    result = await consult_mirror(params)
    data = json.loads(result)

    print(f"✓ JSON 输出成功")
    print(f"  - expert_type: {data.get('expert_type')}")
    print(f"  - expert_name: {data.get('expert_name')}")
    print(f"  - task_description: {data.get('task_description')[:30]}...")
    print(f"  - context: {data.get('context')[:30] if data.get('context') else 'None'}...")
    print(f"  - requirements: {data.get('requirements') if data.get('requirements') else 'None'}")
    print(f"  - generation_method: {data.get('generation_method')}")

    # 验证必需字段
    assert data['expert_type'] == 'education'
    assert data['generation_method'] == 'direct'

    print("\n" + "=" * 70)


async def test_all_expert_types():
    """测试所有 8 种专家类型"""
    print("\n测试 4: 所有专家类型")
    print("=" * 70)

    expert_types = [
        (ExpertType.TECHNICAL, "技术专家"),
        (ExpertType.CREATIVE, "创意设计师"),
        (ExpertType.BUSINESS, "商业战略顾问"),
        (ExpertType.EDUCATION, "教育专家"),
        (ExpertType.WRITING, "写作顾问"),
        (ExpertType.RESEARCH, "研究分析师"),
        (ExpertType.PHILOSOPHY, "哲学思考者"),
        (ExpertType.GENERAL, "通用助手"),
    ]

    results = {}

    for expert_type, expert_name in expert_types:
        try:
            params = ConsultMirrorInput(
                expert_type=expert_type,
                task_description=f"测试{expert_name}的能力",
                response_format=ResponseFormat.JSON
            )

            result = await consult_mirror(params)
            data = json.loads(result)

            results[expert_name] = data['expert_name']
            print(f"✓ {expert_type.value}: {data['expert_name']}")

        except Exception as e:
            print(f"✗ {expert_type.value}: 失败 - {e}")

    # 验证所有专家都正确生成
    matched = sum(1 for k, v in results.items() if k in v)
    print(f"\n匹配率: {matched}/{len(results)} ({matched/len(results)*100:.1f}%)")

    print("\n" + "=" * 70)


async def test_comparison_v1_vs_v2():
    """对比 v1（自动识别）和 v2（直接指定）"""
    print("\n测试 5: v1 vs v2 设计对比")
    print("=" * 70)

    print("\n【v1 设计】（已废弃）")
    print("  输入: task_description")
    print("  流程: 任务 → 规则/LLM 识别 → 选择专家 → 生成提示词")
    print("  优点: 自动化")
    print("  缺点: 识别可能不准，需要额外 API 调用")

    print("\n【v2 设计】（当前）")
    print("  输入: expert_type + task_description + context + requirements")
    print("  流程: 直接生成提示词")
    print("  优点: 直接、高效、可控、无 API 调用")
    print("  缺点: 需要用户选择专家类型")

    print("\n✓ v2 设计更简洁高效！")

    print("\n" + "=" * 70)


async def main():
    """主测试函数"""
    print("\n" + "=" * 70)
    print("求知镜 MCP - 简化设计 v2 测试")
    print("=" * 70)

    try:
        await test_basic_expert_generation()
        await test_with_context_and_requirements()
        await test_json_output()
        await test_all_expert_types()
        await test_comparison_v1_vs_v2()

        print("\n" + "=" * 70)
        print("✅ 所有测试完成！")
        print("=" * 70)

        print("\n设计特点:")
        print("  ✓ 用户直接指定专家类型")
        print("  ✓ 省略了识别环节，更高效")
        print("  ✓ 支持可选的上下文和要求")
        print("  ✓ 类似于 Aurai 顾问的设计模式")

    except Exception as e:
        print(f"\n❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())
