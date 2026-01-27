# Claude Code 安装指南

> **mirror-of-wisdom (求知镜) MCP 服务器** - Claude Code 专用安装指南

---

## 📋 快速安装（5分钟）

### 1. 环境准备

```bash
# 检查 Python 版本（需要 3.10+）
python --version

# 检查 Claude Code
claude --version
```

### 2. 安装依赖

> **重要**：必须先创建虚拟环境并安装项目，否则 MCP 无法启动。

```bash
# 进入项目目录
cd F:\path\to\mcp-mirror-of-wisdom

# 创建虚拟环境
python -m venv venv

# 安装项目（使用虚拟环境的 Python）
venv\Scripts\python.exe -m pip install -e .
```

### 3. 配置 Claude Code MCP

> **关键**：使用 `--scope user` 确保在所有项目中都可用。

```bash
# 替换环境变量为你的实际值
claude mcp add --scope user --transport stdio mirror-of-wisdom \
  --env MIRROR_API_KEY="your-api-key" \
  --env MIRROR_PROVIDER="custom" \
  --env MIRROR_BASE_URL="https://api.example.com/v1" \
  --env MIRROR_MODEL="your-model-name" \
  -- "C:\path\to\your\project\venv\Scripts\python.exe" \
  "C:\path\to\your\project\src\server.py"
```

**注意**：`server.py` 位于 `src/` 目录，不在包内，所以必须用完整路径。

### 4. 验证安装

```bash
# 检查 MCP 状态
claude mcp list

# 预期输出包含：
# mirror-of-wisdom: ... - ✓ Connected
```

### 5. 测试工具

在 Claude Code 对话中：

```
请帮我创建一个技术专家会话，我需要优化数据库查询性能
```

---

## 🔧 配置模板

### 智谱 AI

```bash
claude mcp add --scope user --transport stdio mirror-of-wisdom \
  --env MIRROR_API_KEY="your-key" \
  --env MIRROR_PROVIDER="zhipu" \
  --env MIRROR_MODEL="glm-4-flash" \
  -- "F:\path\to\mcp-mirror-of-wisdom\venv\Scripts\python.exe" \
  "F:\path\to\mcp-mirror-of-wisdom\src\server.py"
```

### 自定义中转站

```bash
claude mcp add --scope user --transport stdio mirror-of-wisdom \
  --env MIRROR_API_KEY="your-key" \
  --env MIRROR_PROVIDER="custom" \
  --env MIRROR_BASE_URL="https://your-proxy.com/v1" \
  --env MIRROR_MODEL="your-model" \
  -- "F:\path\to\mcp-mirror-of-wisdom\venv\Scripts\python.exe" \
  "F:\path\to\mcp-mirror-of-wisdom\src\server.py"
```

### OpenAI 官方

```bash
claude mcp add --scope user --transport stdio mirror-of-wisdom \
  --env MIRROR_API_KEY="sk-..." \
  --env MIRROR_PROVIDER="openai" \
  --env MIRROR_MODEL="gpt-4o" \
  -- "F:\path\to\mcp-mirror-of-wisdom\venv\Scripts\python.exe" \
  "F:\path\to\mcp-mirror-of-wisdom\src\server.py"
```

---

## 🐛 常见问题

### ModuleNotFoundError

**原因**：虚拟环境未创建或项目未安装。

**解决方案**：
```bash
cd F:\path\to\mcp-mirror-of-wisdom
python -m venv venv
venv\Scripts\python.exe -m pip install -e .
```

### Connection failed

**排查步骤**：
```bash
# 1. 验证 Python 路径
venv\Scripts\python.exe --version

# 2. 验证服务器可运行
venv\Scripts\python.exe src\server.py
```

---

## 📁 项目结构说明

```
mcp-mirror-of-wisdom/
├── src/
│   ├── server.py          # ← MCP 服务器入口（不在包内）
│   ├── mirror_of_wisdom/  # Python 包
│   └── tools/             # 工具模块
├── venv/                  # ← 虚拟环境（需创建）
├── .env                   # 环境变量配置
└── pyproject.toml         # 项目配置
```

---

## 🎯 可用工具

| 工具 | 用途 |
|------|------|
| `create_expert_session` | 创建专家会话 |
| `chat_with_expert` | 与专家多轮对话 |
| `end_expert_session` | 结束会话 |

---

## 📞 获取 API 密钥

| 提供商 | 获取地址 |
|--------|----------|
| 智谱 AI | https://open.bigmodel.cn/usercenter/apikeys |
| OpenAI | https://platform.openai.com/api-keys |
| Anthropic | https://console.anthropic.com/settings/keys |
| Gemini | https://makersuite.google.com/app/apikey |

---

**完成！** 🎉 重启 Claude Code 后即可使用。
