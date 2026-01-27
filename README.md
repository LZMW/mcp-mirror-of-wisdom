# 求知镜 MCP (Mirror of Wisdom)

> **本地 AI 的专家咨询工具** - 动态生成专家角色，提供问题-解决-结束的专业服务

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![MCP](https://img.shields.io/badge/MCP-compatible-green.svg)](https://modelcontextprotocol.io/)
[![License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Version](https://img.shields.io/badge/version-0.7.2-brightgreen.svg)](https://github.com/your-org/mcp-mirror-of-wisdom)

---

## 🌟 产品简介

求知镜 MCP 是一个基于 MCP (Model Context Protocol) 的**专家咨询工具**，根据用户需求动态生成专业的专家角色，提供从问题分析到解决方案的完整咨询服务。

### 核心特性

- 🧠 **元提示词驱动** - 使用 4D 流程动态生成专业专家提示词
- 💭 **思维链展示** - 专家展示完整思考过程（知识对齐、逻辑解构、交叉验证、执行策略）
- 🎯 **信息粒度对齐** - 首次对话主动提问，确保理解用户真实需求
- ✅ **任务完成导向** - 问题解决后明确终止，非无限聊天
- 🔄 **多领域支持** - 技术、设计、商业、教育等任意领域
- 🛡️ **质量保证** - 自动回退机制，确保服务稳定性

### 产品定位

| 维度 | 不是 | 而是 |
|------|------|------|
| **核心定位** | 聊天机器人、万能助手 | **专家咨询工具** |
| **使用模式** | 无限多轮对话 | **问题-解决-结束** |
| **专家切换** | 复用 session_id（会错位） | **每个任务创建新会话** |
| **价值主张** | 一个"万能"但平庸的助手 | **每个领域都有最专业的专家** |

---

## 🚀 快速开始

### 安装

**方式 1: 使用可视化配置工具（推荐）**

```bash
# 进入项目目录
cd mcp-mirror-of-wisdom

# 安装依赖
pip install -e .

# 运行可视化配置工具
python tools/mirror_config_tool.py
```

**方式 2: 手动配置**

```bash
# 进入项目目录
cd mcp-mirror-of-wisdom

# 安装依赖
pip install -e .

# 配置环境变量
cp .env.example .env
# 编辑 .env 文件，设置 MIRROR_API_KEY
```

**详细安装教程**: 查看 [INSTALLATION.md](INSTALLATION.md) 获取完整的用户级安装指南

### 运行

```bash
# 启动 MCP 服务器
python -m mirror_of_wisdom.server

# 或使用 MCP Inspector 测试
npx @modelcontextprotocol/inspector python -m mirror_of_wisdom.server
```

### 使用示例

```python
# 1. 创建专家会话
session_id = await create_expert_session(
    requirement="我需要优化数据库查询性能"
)

# 2. 专家首次回复（主动提问对齐信息粒度）
# 专家会问 3 个关键问题

# 3. 用户提供详细信息
response = await chat_with_expert(
    session_id=session_id,
    message="我的订单表有5000万条数据，SQL 是..."
)

# 4. 专家深度分析（展示完整思维链）
# 知识对齐 → 逻辑解构 → 交叉验证 → 执行策略

# 5. 问题解决后，专家自动终止对话
# 提示重新创建新会话处理其他问题
```

---

## 💡 使用场景

```
💡 技术问题
   → 创建技术专家会话
   → 展示思维链分析
   → 提供具体解决方案
   → 问题解决后终止

🎨 设计问题
   → 创建设计专家会话（新会话）
   → 分析设计需求
   → 提供专业设计方案
   → 完成后终止

📈 商业问题
   → 创建商业专家会话（新会话）
   → 商业模式分析
   → 战略建议
   → 完成后终止
```

**重要提示**：每次处理不同领域的问题时，请创建新的专家会话，以获得最专业的指导。

---

## 📖 详细文档

- **[INSTALLATION.md](INSTALLATION.md)** - 完整安装教程（用户级安装）
- **[QUICKSTART.md](QUICKSTART.md)** - 5分钟快速上手指南
- **[DEVELOPMENT.md](DEVELOPMENT.md)** - 完整开发指南
- **[说明文档.md](说明文档.md)** - 项目全生命周期文档

---

## 🏗️ 项目结构

```
mcp-mirror-of-wisdom/
├── 说明文档.md              # 项目主文档
├── README.md               # 本文件
├── INSTALLATION.md         # 安装教程
├── QUICKSTART.md           # 快速开始
├── DEVELOPMENT.md          # 开发指南
├── pyproject.toml          # 项目配置
│
├── src/
│   ├── mirror_of_wisdom/   # 核心包
│   │   ├── config.py       # 配置管理
│   │   ├── prompt_generator.py  # 元提示词生成器
│   │   ├── llm_client.py   # 多提供商 LLM 客户端
│   │   ├── session_manager.py  # 会话状态管理
│   │   ├── llm_cache.py    # 持久化缓存
│   │   ├── circuit_breaker.py # 熔断器保护
│   │   └── metrics.py      # 性能监控
│   ├── tools/              # MCP 工具
│   │   └── expert_session.py  # 3个核心工具
│   └── server.py           # MCP 服务器入口
│
├── tools/                  # 配置工具
│   └── mirror_config_tool.py  # 可视化配置工具
│
├── tests/                  # 测试
│   ├── unit/               # 单元测试
│   └── scenarios/          # 场景测试
│
└── .ai_temp/               # 临时文件（演示脚本等）
```

---

## 🛠️ 核心 MCP 工具

### 1. create_expert_session
创建专家会话，生成专家提示词，并立即返回专家首次回复（主动提问）。

### 2. chat_with_expert
与专家对话，展示完整思维链，提供专业建议。

### 3. end_expert_session
结束专家会话，清理资源，并提供会话统计。

---

## 📊 项目状态

### 当前版本：v0.7.2 (Phase 6)

**已完成功能**：
- ✅ 元提示词驱动（4D 流程）
- ✅ 思维链展示（始终展示思考过程）
- ✅ 首次对话协议（分析概述 + 3个问题）
- ✅ 任务完成与终止机制
- ✅ 多领域专家动态生成
- ✅ 会话状态管理（TTL 30分钟）
- ✅ 持久化缓存（规避重复推理）
- ✅ 熔断器保护（防止级联故障）
- ✅ 性能监控（LLM 调用统计）
- ✅ 多提供商支持（OpenAI/Anthropic/智谱/Gemini/自定义）

**测试覆盖**：
- ✅ 94 个单元测试通过
- ✅ 真实 LLM 端到端演示验证
- ✅ 极端情况测试通过

---

## 🔗 相关链接

- **[MCP 官方文档](https://modelcontextprotocol.io)**
- **[FastMCP 框架](https://github.com/jlowin/fastmcp)**
- **[Claude Desktop](https://claude.ai/download)**

---

## 📝 更新日志

### v0.7.2 (2025-01-25)

**Phase 6 完成**：
- ✨ 元提示词优化（专家思维系统）
- 💭 始终展示思维链（首次收敛为概述+3问题，后续完整4步）
- ✅ 任务完成与终止机制（问题-解决-结束模式）
- 📝 产品定位明确（专家咨询工具，非聊天机器人）
- ✅ 端到端真实 LLM 演示验证
- ✅ Phase 6 单元测试（9个新测试）

### v0.7.1 (2025-01-23)

**Phase 5 完成**：
- ✨ 两阶段提示词优化
- 🎯 自定义约束和验收标准
- 📦 配置文件预设支持

### v0.7.0 (2025-01-23)

**Phase 4 完成**：
- 🔄 会话管理重构（显式生命周期）
- 💬 首次对话信息粒度对齐
- 🛡️ 质量检查与兜底机制

### v0.6.0 (2025-01-22)

**Phase 3 完成**：
- ⚡ 持久化缓存（规避 13s LLM 推理时间）
- 🛡️ 熔断器保护（防止级联故障）
- 📊 性能监控（LLM 调用统计）

---

## 🤝 贡献

欢迎贡献！请查看 [DEVELOPMENT.md](DEVELOPMENT.md) 了解开发指南。

---

## 📄 许可证

MIT License

---

## 💬 联系方式

- **Issues**: [GitHub Issues](https://github.com/your-org/mcp-mirror-of-wisdom/issues)
- **Discussions**: [GitHub Discussions](https://github.com/your-org/mcp-mirror-of-wisdom/discussions)

---

**需要帮助？** 查看 [QUICKSTART.md](QUICKSTART.md) 或 [DEVELOPMENT.md](DEVELOPMENT.md)
