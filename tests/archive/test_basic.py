"""基础测试脚本

测试求知镜 MCP 的核心功能。
"""

import asyncio
import sys
import os
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

from mirror_of_wisdom.prompt_generator import get_prompt_generator
from mirror_of_wisdom.config import get_mirror_config, get_server_config


async def test_prompt_generator():
    """测试提示词生成器"""
    print("=" * 60)
    print("测试 1: 提示词生成器")
    print("=" * 60)

    generator = get_prompt_generator()

    # 测试场景
    test_cases = [
        {
            "name": "技术问题",
            "task": "我需要优化我的 Python 代码性能，特别是数据库查询部分"
        },
        {
            "name": "创意设计",
            "task": "为一个儿童教育 App 设计主角形象，3-6岁目标用户"
        },
        {
            "name": "商业规划",
            "task": "帮我制定一个电商网站的 Q1 市场推广计划"
        },
        {
            "name": "教育学习",
            "task": "我想学习机器学习，有 Python 基础，请制定学习路径"
        }
    ]

    for i, test_case in enumerate(test_cases, 1):
        print(f"\n【测试 {i}】{test_case['name']}")
        print(f"任务: {test_case['task'][:60]}...")

        try:
            # 生成专家提示词
            result = generator.generate_expert_prompt(test_case['task'])

            print(f"✓ 成功")
            print(f"  - 任务类型: {result['task_type']}")
            print(f"  - 专家名称: {result['expert_name']}")
            print(f"  - 生成方法: {result['generation_method']}")
        except Exception as e:
            print(f"✗ 失败: {e}")

    print("\n" + "=" * 60)


async def test_config():
    """测试配置加载"""
    print("\n测试 2: 配置加载")
    print("=" * 60)

    try:
        mirror_config = get_mirror_config()
        server_config = get_server_config()

        print(f"✓ LLM 配置:")
        print(f"  - 提供商: {mirror_config.provider}")
        print(f"  - 模型: {mirror_config.model}")
        print(f"  - 温度: {mirror_config.temperature}")
        print(f"  - 最大 Tokens: {mirror_config.max_tokens}")

        print(f"\n✓ 服务器配置:")
        print(f"  - 名称: {server_config.name}")
        print(f"  - 日志级别: {server_config.log_level}")
        print(f"  - 质量检查: {'启用' if server_config.enable_quality_check else '禁用'}")
        print(f"  - 角色切换: {'启用' if server_config.enable_role_switching else '禁用'}")

    except Exception as e:
        print(f"✗ 配置加载失败: {e}")

    print("=" * 60)


async def test_expert_library():
    """测试专家库"""
    print("\n测试 3: 专家库")
    print("=" * 60)

    from mirror_of_wisdom.prompt_generator import EXPERT_LIBRARY

    print(f"✓ 专家库总数: {len(EXPERT_LIBRARY)}")

    for category, info in EXPERT_LIBRARY.items():
        print(f"\n  [{category}] {info['name']}")
        print(f"    关键词: {', '.join(info['keywords'][:3])}...")

    print("\n" + "=" * 60)


async def main():
    """主测试函数"""
    print("\n" + "=" * 60)
    print("求知镜 MCP - 基础测试")
    print("=" * 60)

    try:
        # 测试配置
        await test_config()

        # 测试专家库
        await test_expert_library()

        # 测试提示词生成器
        await test_prompt_generator()

        print("\n✅ 所有测试完成！")
        print("\n下一步:")
        print("1. 配置 .env 文件（填入 API Key）")
        print("2. 安装依赖: pip install -e .")
        print("3. 运行服务器: python -m mirror_of_wisdom.server")
        print("4. 使用 MCP Inspector 测试")

    except Exception as e:
        print(f"\n❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())
