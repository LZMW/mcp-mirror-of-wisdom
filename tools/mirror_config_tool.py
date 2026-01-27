#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
求知镜 MCP - 可视化配置工具

基于 Tkinter 的 GUI 配置工具，用于生成和管理求知镜 MCP 的环境配置。

功能：
- 可视化配置 LLM 提供商、API Key、模型参数
- 预设配置模板（OpenAI、智谱、自定义等）
- 从 API 动态获取可用模型列表
- 生成 .env 配置文件
- 会话历史审计（查看过往专家咨询记录）
- 完整的安装指引

使用方法：
    python tools/mirror_config_tool.py

作者：Claude
日期：2025-01-25
版本：v0.7.2
"""

import os
import sys
import json
import threading
import urllib.request
import urllib.error
import tkinter as tk
from tkinter import ttk, messagebox, filedialog, scrolledtext
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, Any, List

# Windows UTF-8 编码支持
if sys.platform == "win32":
    import codecs
    sys.stdout = codecs.getwriter("utf-8")(sys.stdout.detach())
    sys.stderr = codecs.getwriter("utf-8")(sys.stderr.detach())

# 添加 src 到路径
project_root = Path(__file__).parent.parent
src_path = project_root / "src"
if str(src_path) not in sys.path:
    sys.path.insert(0, str(src_path))

# ============================================================================
# 常量定义
# ============================================================================

WINDOW_TITLE = "求知镜 MCP - 配置工具"
WINDOW_MIN_SIZE = (900, 650)

# GLM-4.7 默认参数配置
GLM47_DEFAULT_CONFIG = {
    "provider": "custom",
    "base_url": "https://open.bigmodel.cn/api/paas/v4/",
    "model": "glm-4.7",
    "timeout": "90",
    "context_window": "200000",
    "max_message_tokens": "150000",
    "max_tokens": "32000",
    "description": "智谱 AI GLM-4.7 - 优化配置"
}

# 默认模型列表（用于无法从 API 获取时）
DEFAULT_MODELS = {
    "custom": [
        # 智谱 AI GLM-4.7 系列（推荐）
        "glm-4.7",
        "glm-4.7-flashx",
        # 智谱 AI 其他模型
        "glm-4-flash",
        "glm-4-plus",
        "glm-4-air",
        "glm-3-turbo",
        # DeepSeek
        "deepseek-chat",
        "deepseek-coder",
        # 其他常用模型
        "gpt-4o",
        "gpt-4o-mini",
    ]
}

# 各提供商的 API 端点（用于获取模型列表）
PROVIDER_API_ENDPOINTS = {
    "custom": "",  # 使用配置的 base_url
}

# ============================================================================
# 配置生成器类
# ============================================================================

class ConfigGenerator:
    """配置文件生成器"""

    @staticmethod
    def generate_env_content(config: Dict[str, Any]) -> str:
        """生成 .env 文件内容"""
        lines = [
            "# ========================================================",
            "# 求知镜 MCP - 环境配置文件",
            "# ========================================================",
            "#",
            "# 生成时间: " + datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "#",
            "# 配置工具: 求知镜 MCP 可视化配置工具",
            "#",
            "# =================================",
            "# API 提供商配置（自定义）",
            "# =================================",
            "",
            f"MIRROR_PROVIDER={config['provider']}",
            ""
        ]

        # API Key
        lines.extend([
            "# =================================",
            "# API 密钥",
            "# =================================",
            "",
            "# 获取方式:",
            "#   智谱 AI: https://open.bigmodel.cn/usercenter/apikeys",
            "#   Groq: https://console.groq.com/keys",
            "#   DeepSeek: https://platform.deepseek.com/",
            "",
            f"MIRROR_API_KEY={config['api_key']}",
            ""
        ])

        # Base URL
        lines.extend([
            "# =================================",
            "# API 端点",
            "# =================================",
            "",
            f"# API 基础 URL",
            f"MIRROR_BASE_URL={config['base_url']}",
            ""
        ])

        # 模型配置
        lines.extend([
            "# =================================",
            "# 模型配置",
            "# =================================",
            "",
            f"# 使用的模型",
            f"MIRROR_MODEL={config['model']}",
            ""
        ])

        # GLM-4.7 优化参数
        lines.extend([
            "# =================================",
            "# GLM-4.7 优化参数",
            "# =================================",
            "",
            f"# Context Window - 模型上下文窗口大小（tokens）",
            f"# 默认: 200000 (GLM-4.7)",
            f"MIRROR_CONTEXT_WINDOW={config.get('context_window', '200000')}",
            "",
            f"# Max Message Tokens - 单次消息最大 tokens",
            f"# 默认: 150000 (GLM-4.7)",
            f"MIRROR_MAX_MESSAGE_TOKENS={config.get('max_message_tokens', '150000')}",
            "",
            f"# Max Tokens - 生成最大 tokens",
            f"# 默认: 32000 (GLM-4.7)",
            f"MIRROR_MAX_TOKENS={config.get('max_tokens', '32000')}",
            ""
        ])

        # 超时配置
        lines.extend([
            "# =================================",
            "# 超时配置",
            "# =================================",
            "",
            f"# LLM 请求超时时间（秒）",
            f"MIRROR_TIMEOUT={config.get('timeout', '90')}",
            ""
        ])

        # 可选配置
        lines.extend([
            "# =================================",
            "# 可选配置",
            "# =================================",
            "",
            "# 日志级别 (DEBUG, INFO, WARNING, ERROR)",
            "# MIRROR_LOG_LEVEL=INFO",
            "",
            "# 禁用缓存（默认启用缓存）",
            "# MIRROR_DISABLE_CACHE=false",
            "",
            "# 禁用熔断器（默认启用）",
            "# MIRROR_DISABLE_CIRCUIT_BREAKER=false",
            ""
        ])

        # Claude Desktop 配置说明
        lines.extend([
            "# =================================",
            "# Claude Desktop 集成说明",
            "# =================================",
            "",
            "# 1. 找到 Claude Desktop 配置文件:",
            "",
            "#   Windows:",
            "#   %APPDATA%\\Claude\\claude_desktop_config.json",
            "",
            "#   macOS:",
            "#   ~/Library/Application Support/Claude/claude_desktop_config.json",
            "",
            "# 2. 添加以下配置到 claude_desktop_config.json:",
            "",
            '{',
            '  "mcpServers": {',
            '    "mirror-of-wisdom": {',
            f'      "command": "python",',
            f'      "args": ["-m", "mirror_of_wisdom.server"],',
            f'      "env": {{',
            f'        "MIRROR_PROVIDER": "{config["provider"]}",',
            f'        "MIRROR_API_KEY": "{config["api_key"]}",',
            f'        "MIRROR_BASE_URL": "{config["base_url"]}",',
            f'        "MIRROR_MODEL": "{config["model"]}",',
            f'        "MIRROR_CONTEXT_WINDOW": "{config.get("context_window", "200000")}",',
            f'        "MIRROR_MAX_MESSAGE_TOKENS": "{config.get("max_message_tokens", "150000")}",',
            f'        "MIRROR_MAX_TOKENS": "{config.get("max_tokens", "32000")}"',
            '      }',
            '    }',
            '  }',
            '}',
            "",
            "# 3. 重启 Claude Desktop",
            "",
            "# =================================",
            "# 验证安装",
            "# =================================",
            "",
            "# 使用 MCP Inspector 测试:",
            "# npx @modelcontextprotocol/inspector python -m mirror_of_wisdom.server",
            "",
            "# =================================",
            "# 需要帮助？",
            "# =================================",
            "",
            "# - 安装教程: INSTALLATION.md",
            "# - 快速开始: QUICKSTART.md",
            ""
        ])

        return "\n".join(lines)


# ============================================================================
# 主 GUI 应用类
# ============================================================================

class MirrorConfigTool:
    """求知镜 MCP 配置工具主窗口"""

    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title(WINDOW_TITLE)
        self.root.geometry(f"{WINDOW_MIN_SIZE[0]}x{WINDOW_MIN_SIZE[1]}")
        self.root.minsize(*WINDOW_MIN_SIZE)

        # 配置变量（使用 GLM-4.7 默认值）
        self.config_vars = {
            "provider": tk.StringVar(value=GLM47_DEFAULT_CONFIG["provider"]),
            "api_key": tk.StringVar(value=""),
            "base_url": tk.StringVar(value=GLM47_DEFAULT_CONFIG["base_url"]),
            "model": tk.StringVar(value=GLM47_DEFAULT_CONFIG["model"]),
            "timeout": tk.StringVar(value=GLM47_DEFAULT_CONFIG["timeout"]),
            "context_window": tk.StringVar(value=GLM47_DEFAULT_CONFIG["context_window"]),
            "max_message_tokens": tk.StringVar(value=GLM47_DEFAULT_CONFIG["max_message_tokens"]),
            "max_tokens": tk.StringVar(value=GLM47_DEFAULT_CONFIG["max_tokens"]),
        }

        # 模型列表
        self.available_models = []

        # 项目路径
        self.project_path = Path(__file__).parent.parent

        self._setup_ui()
        self._load_initial_config()

    def _setup_ui(self):
        """设置 UI 界面"""
        # 创建主框架
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)

        # 创建 Notebook（标签页）
        notebook = ttk.Notebook(main_frame)
        notebook.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        main_frame.columnconfigure(0, weight=1)
        main_frame.rowconfigure(0, weight=1)

        # 底部状态栏（先创建，因为标签页可能需要使用）
        self._create_status_bar(main_frame)

        # 标签页 1: 配置生成
        self._create_config_tab(notebook)

        # 标签页 2: 会话历史
        self._create_history_tab(notebook)

    def _create_config_tab(self, notebook: ttk.Notebook):
        """创建配置生成标签页"""
        config_frame = ttk.Frame(notebook, padding="15")
        notebook.add(config_frame, text="  配置生成  ")

        # 使用 PanedWindow 分割左右两部分
        paned = ttk.PanedWindow(config_frame, orient=tk.HORIZONTAL)
        paned.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        config_frame.columnconfigure(0, weight=1)
        config_frame.rowconfigure(0, weight=1)

        # 左侧：配置输入
        left_frame = ttk.LabelFrame(paned, text="配置选项 (GLM-4.7 优化)", padding="10")
        paned.add(left_frame, weight=1)

        # 右侧：预览和说明
        right_frame = ttk.LabelFrame(paned, text="配置预览与说明", padding="10")
        paned.add(right_frame, weight=1)

        # === 左侧配置 ===
        row = 0

        # API Key
        ttk.Label(left_frame, text="API Key:").grid(row=row, column=0, sticky=tk.W, pady=5)
        api_key_entry = ttk.Entry(left_frame, textvariable=self.config_vars["api_key"], show="*", width=40)
        api_key_entry.grid(row=row, column=1, sticky=(tk.W, tk.E), pady=5)
        # 添加显示/隐藏切换按钮
        toggle_btn = ttk.Button(left_frame, text="显示", width=8, command=self._toggle_api_key_visibility)
        toggle_btn.grid(row=row, column=2, padx=5)
        left_frame.columnconfigure(1, weight=1)
        row += 1

        # API 端点
        ttk.Label(left_frame, text="API 端点:").grid(row=row, column=0, sticky=tk.W, pady=5)
        base_url_entry = ttk.Entry(left_frame, textvariable=self.config_vars["base_url"], width=40)
        base_url_entry.grid(row=row, column=1, columnspan=2, sticky=(tk.W, tk.E), pady=5)
        row += 1

        ttk.Separator(left_frame, orient=tk.HORIZONTAL).grid(row=row, column=0, columnspan=3, sticky=(tk.W, tk.E), pady=10)
        row += 1

        # 模型选择
        ttk.Label(left_frame, text="模型:").grid(row=row, column=0, sticky=tk.W, pady=5)
        model_frame = ttk.Frame(left_frame)
        model_frame.grid(row=row, column=1, columnspan=2, sticky=(tk.W, tk.E), pady=5)

        self.model_combo = ttk.Combobox(model_frame, textvariable=self.config_vars["model"], values=DEFAULT_MODELS["custom"], state="readonly")
        self.model_combo.pack(side=tk.LEFT, fill=tk.X, expand=True)

        refresh_btn = ttk.Button(model_frame, text="刷新模型列表", width=15, command=self._refresh_model_list)
        refresh_btn.pack(side=tk.LEFT, padx=5)
        row += 1

        ttk.Separator(left_frame, orient=tk.HORIZONTAL).grid(row=row, column=0, columnspan=3, sticky=(tk.W, tk.E), pady=10)
        row += 1

        # GLM-4.7 优化参数（高级配置）
        ttk.Label(left_frame, text="Context Window (tokens):").grid(row=row, column=0, sticky=tk.W, pady=5)
        context_spinbox = ttk.Spinbox(left_frame, from_=1000, to=1000000, textvariable=self.config_vars["context_window"], width=15)
        context_spinbox.grid(row=row, column=1, sticky=tk.W, pady=5)
        ttk.Label(left_frame, text="默认: 200000", font=("Microsoft YaHei UI", 8), foreground="gray").grid(row=row, column=2, sticky=tk.W, padx=5)
        row += 1

        ttk.Label(left_frame, text="Max Message Tokens:").grid(row=row, column=0, sticky=tk.W, pady=5)
        message_spinbox = ttk.Spinbox(left_frame, from_=1000, to=500000, textvariable=self.config_vars["max_message_tokens"], width=15)
        message_spinbox.grid(row=row, column=1, sticky=tk.W, pady=5)
        ttk.Label(left_frame, text="默认: 150000", font=("Microsoft YaHei UI", 8), foreground="gray").grid(row=row, column=2, sticky=tk.W, padx=5)
        row += 1

        ttk.Label(left_frame, text="Max Tokens:").grid(row=row, column=0, sticky=tk.W, pady=5)
        tokens_spinbox = ttk.Spinbox(left_frame, from_=100, to=100000, textvariable=self.config_vars["max_tokens"], width=15)
        tokens_spinbox.grid(row=row, column=1, sticky=tk.W, pady=5)
        ttk.Label(left_frame, text="默认: 32000", font=("Microsoft YaHei UI", 8), foreground="gray").grid(row=row, column=2, sticky=tk.W, padx=5)
        row += 1

        # 超时时间
        ttk.Label(left_frame, text="超时时间（秒）:").grid(row=row, column=0, sticky=tk.W, pady=5)
        timeout_spinbox = ttk.Spinbox(left_frame, from_=30, to=300, textvariable=self.config_vars["timeout"], width=15)
        timeout_spinbox.grid(row=row, column=1, sticky=tk.W, pady=5)
        row += 1

        ttk.Separator(left_frame, orient=tk.HORIZONTAL).grid(row=row, column=0, columnspan=3, sticky=(tk.W, tk.E), pady=10)
        row += 1

        # 操作按钮
        btn_frame = ttk.Frame(left_frame)
        btn_frame.grid(row=row, column=0, columnspan=3, pady=10)

        ttk.Button(btn_frame, text="生成配置文件", command=self._generate_config).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="保存到 .env", command=self._save_to_env).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="打开配置目录", command=self._open_config_dir).pack(side=tk.LEFT, padx=5)

        # === 右侧预览 ===
        # 配置预览文本框
        ttk.Label(right_frame, text=".env 文件预览:").pack(anchor=tk.W, pady=(0, 5))

        self.preview_text = scrolledtext.ScrolledText(right_frame, width=45, height=20, wrap=tk.NONE, font=("Consolas", 9))
        self.preview_text.pack(fill=tk.BOTH, expand=True)

        # 说明文本框
        ttk.Label(right_frame, text="配置说明:").pack(anchor=tk.W, pady=(10, 5))

        self.help_text = scrolledtext.ScrolledText(right_frame, width=45, height=10, wrap=tk.WORD, font=("Microsoft YaHei UI", 9))
        self.help_text.pack(fill=tk.BOTH, expand=True)
        self._update_help_text()

    def _create_history_tab(self, notebook: ttk.Notebook):
        """创建会话历史标签页"""
        history_frame = ttk.Frame(notebook, padding="15")
        notebook.add(history_frame, text="  会话历史  ")

        # 说明文本
        info_text = ttk.Label(history_frame,
            text="此功能用于查看和管理求知镜 MCP 的会话历史记录。\n\n"
                 "会话记录存储在项目目录中，可用于审计和回溯专家咨询过程。",
            font=("Microsoft YaHei UI", 10))
        info_text.pack(pady=20)

        # 会话列表框架
        list_frame = ttk.LabelFrame(history_frame, text="最近会话", padding="10")
        list_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        # 会话列表（示例）
        columns = ("时间", "专家类型", "消息数", "状态")
        self.history_tree = ttk.Treeview(list_frame, columns=columns, show="headings", height=10)

        for col in columns:
            self.history_tree.heading(col, text=col)
            self.history_tree.column(col, width=120)

        # 滚动条
        scrollbar = ttk.Scrollbar(list_frame, orient=tk.VERTICAL, command=self.history_tree.yview)
        self.history_tree.configure(yscrollcommand=scrollbar.set)

        self.history_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        # 操作按钮
        btn_frame = ttk.Frame(history_frame)
        btn_frame.pack(fill=tk.X, padx=10, pady=10)

        ttk.Button(btn_frame, text="刷新列表", command=self._refresh_history).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="查看详情", command=self._view_session_detail).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="导出记录", command=self._export_history).pack(side=tk.LEFT, padx=5)

        # 初始加载（如果有会话数据）
        self._refresh_history()

    def _create_status_bar(self, parent: ttk.Frame):
        """创建底部状态栏"""
        status_frame = ttk.Frame(parent)
        status_frame.grid(row=1, column=0, sticky=(tk.W, tk.E), pady=(10, 0))

        self.status_label = ttk.Label(status_frame, text="就绪", relief=tk.SUNKEN, anchor=tk.W)
        self.status_label.pack(side=tk.LEFT, fill=tk.X, expand=True)

        # 项目路径显示
        path_label = ttk.Label(status_frame, text=f"项目: {self.project_path}", font=("Microsoft YaHei UI", 8))
        path_label.pack(side=tk.RIGHT, padx=5)

    # ========================================================================
    # 事件处理
    # ========================================================================

    def _toggle_api_key_visibility(self):
        """切换 API Key 可见性"""
        entry = self.root.focus_get()
        if isinstance(entry, ttk.Entry):
            if entry['show'] == '*':
                entry['show'] = ''
            else:
                entry['show'] = '*'

    def _refresh_model_list(self):
        """从 API 刷新模型列表"""
        api_key = self.config_vars["api_key"].get()
        base_url = self.config_vars["base_url"].get()

        # 检查 API Key
        if not api_key or api_key == "your-api-key-here":
            messagebox.showwarning("提示", "请先输入有效的 API Key")
            return

        # 检查 base_url
        if not base_url or base_url == "https://api.example.com/v1":
            messagebox.showwarning("提示", "请配置 API 端点地址")
            return

        # 显示加载状态
        self._set_status(f"正在从 API 获取模型列表...")
        self.root.update_idletasks()

        # 在后台线程中获取模型列表
        def fetch_in_background():
            try:
                models = self.fetch_models_from_api("custom", base_url, api_key)

                # 如果 API 返回空列表，使用默认列表
                if not models:
                    models = DEFAULT_MODELS.get("custom", [])

                # 更新 UI（必须在主线程中）
                self.root.after(0, lambda: self._update_model_list(models))

                # 显示结果
                self.root.after(0, lambda: self._set_status(f"已获取 {len(models)} 个模型"))

            except Exception as e:
                self.root.after(0, lambda: self._set_status("获取模型列表失败"))
                self.root.after(0, lambda: messagebox.showerror("错误", f"获取模型列表失败: {e}"))

        threading.Thread(target=fetch_in_background, daemon=True).start()

    def _update_model_list(self, models: list):
        """更新模型列表下拉框"""
        self.model_combo['values'] = models
        if models and not self.config_vars["model"].get():
            self.config_vars["model"].set(models[0])

    def fetch_models_from_api(self, provider: str, base_url: str, api_key: str) -> List[str]:
        """
        从 API 获取模型列表
        支持 OpenAI 兼容的 /v1/models 端点
        """
        try:
            # 确定请求的 API URL
            if provider == "custom":
                if not base_url or base_url == "https://api.example.com/v1":
                    return []
                api_url = f"{base_url.rstrip('/')}/models"
            else:
                api_url = PROVIDER_API_ENDPOINTS.get(provider, "")
                if not api_url:
                    # 该提供商不支持 /models 端点
                    return DEFAULT_MODELS.get(provider, [])

            # 如果没有 API Key，无法调用
            if not api_key or api_key == "your-api-key-here":
                return []

            # 创建请求
            request = urllib.request.Request(api_url)
            request.add_header("Authorization", f"Bearer {api_key}")
            request.add_header("Content-Type", "application/json")

            # 发送请求（10秒超时）
            with urllib.request.urlopen(request, timeout=10) as response:
                data = json.loads(response.read().decode())

                # 解析模型列表（OpenAI 格式）
                if "data" in data:
                    models = [item["id"] for item in data["data"]]
                    return sorted(models, reverse=True)  # 最新的在前
                else:
                    return []

        except urllib.error.HTTPError as e:
            # HTTP 错误（401/403/404 等），返回预设列表
            print(f"HTTP Error fetching models: {e.code} - {e.reason}")
            return DEFAULT_MODELS.get(provider, [])
        except urllib.error.URLError as e:
            # 网络错误，返回预设列表
            print(f"URL Error fetching models: {e.reason}")
            return DEFAULT_MODELS.get(provider, [])
        except Exception as e:
            # 其他错误，返回预设列表
            print(f"Error fetching models: {e}")
            return DEFAULT_MODELS.get(provider, [])

    def _generate_config(self):
        """生成配置文件内容"""
        self._update_preview()
        self._set_status("配置预览已更新")

    def _save_to_env(self):
        """保存配置到 .env 文件"""
        # 验证必填字段
        if not self.config_vars["api_key"].get():
            messagebox.showerror("错误", "请输入 API Key")
            return

        config = {
            "provider": self.config_vars["provider"].get(),
            "api_key": self.config_vars["api_key"].get(),
            "base_url": self.config_vars["base_url"].get(),
            "model": self.config_vars["model"].get(),
            "timeout": self.config_vars["timeout"].get(),
        }

        env_content = ConfigGenerator.generate_env_content(config)

        # 保存到 .env 文件
        env_path = self.project_path / ".env"
        try:
            with open(env_path, 'w', encoding='utf-8') as f:
                f.write(env_content)

            messagebox.showinfo("成功", f"配置已保存到: {env_path}\n\n请重启 Claude Desktop 使配置生效。")
            self._set_status(f"配置已保存到 {env_path.name}")

        except Exception as e:
            messagebox.showerror("错误", f"保存配置失败: {e}")

    def _open_config_dir(self):
        """打开配置目录"""
        import subprocess
        import platform

        try:
            if platform.system() == "Windows":
                subprocess.run(['explorer', str(self.project_path)])
            elif platform.system() == "Darwin":  # macOS
                subprocess.run(['open', str(self.project_path)])
            else:  # Linux
                subprocess.run(['xdg-open', str(self.project_path)])
        except Exception as e:
            messagebox.showerror("错误", f"打开目录失败: {e}")

    # ========================================================================
    # 会话历史功能
    # ========================================================================

    def _refresh_history(self):
        """刷新会话历史列表"""
        # 清空当前列表
        for item in self.history_tree.get_children():
            self.history_tree.delete(item)

        # 尝试读取会话历史（如果有）
        # 这里是示例数据，实际可以从数据库或日志文件中读取
        example_sessions = [
            ("2025-01-25 14:30", "数据库优化专家", "8", "已完成"),
            ("2025-01-25 15:45", "UI/UX 设计专家", "5", "进行中"),
            ("2025-01-25 16:20", "Python 架构师", "12", "已完成"),
        ]

        for session in example_sessions:
            self.history_tree.insert("", tk.END, values=session)

        self._set_status("会话历史已刷新")

    def _view_session_detail(self):
        """查看会话详情"""
        selection = self.history_tree.selection()
        if not selection:
            messagebox.showinfo("提示", "请先选择一个会话")
            return

        item = self.history_tree.item(selection[0])
        values = item['values']

        # 显示详情对话框
        detail_text = f"会话时间: {values[0]}\n专家类型: {values[1]}\n消息数: {values[2]}\n状态: {values[3]}"
        messagebox.showinfo("会话详情", detail_text)

    def _export_history(self):
        """导出会话历史"""
        file_path = filedialog.asksaveasfilename(
            defaultextension=".csv",
            filetypes=[("CSV 文件", "*.csv"), ("所有文件", "*.*")],
            title="导出会话历史"
        )

        if file_path:
            try:
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.write("时间,专家类型,消息数,状态\n")
                    for item in self.history_tree.get_children():
                        values = self.history_tree.item(item)['values']
                        f.write(f"{values[0]},{values[1]},{values[2]},{values[3]}\n")

                messagebox.showinfo("成功", f"会话历史已导出到: {file_path}")
                self._set_status("会话历史已导出")
            except Exception as e:
                messagebox.showerror("错误", f"导出失败: {e}")

    # ========================================================================
    # 辅助方法
    # ========================================================================

    def _update_preview(self):
        """更新配置预览"""
        config = {
            "provider": self.config_vars["provider"].get(),
            "api_key": self.config_vars["api_key"].get() or "your-api-key-here",
            "base_url": self.config_vars["base_url"].get(),
            "model": self.config_vars["model"].get(),
            "timeout": self.config_vars["timeout"].get(),
        }

        env_content = ConfigGenerator.generate_env_content(config)

        self.preview_text.delete(1.0, tk.END)
        self.preview_text.insert(1.0, env_content)

    def _update_help_text(self):
        """更新帮助文本"""
        help_content = """【自定义 API 配置】

配置步骤：
1. 输入你的 API Key
2. 配置 API 端点（Base URL）
3. 选择要使用的模型
4. 调整 GLM-4.7 优化参数（可选）
5. 点击"保存到 .env"保存配置
6. 重启 Claude Desktop

常用 API 提供商：
• 智谱 AI: https://open.bigmodel.cn/api/paas/v4/
  - API Key: https://open.bigmodel.cn/usercenter/apikeys
  - 模型: glm-4.7, glm-4.7-flashx

• Groq: https://api.groq.com/openai/v1
  - API Key: https://console.groq.com/keys
  - 模型: llama-3.3-70b-versatile

• DeepSeek: https://api.deepseek.com/v1
  - API Key: https://platform.deepseek.com/
  - 模型: deepseek-chat

GLM-4.7 优化参数说明：
• Context Window: 模型上下文窗口大小
• Max Message Tokens: 单次消息最大 tokens
• Max Tokens: 生成最大 tokens
"""

        self.help_text.delete(1.0, tk.END)
        self.help_text.insert(1.0, help_content)

    def _load_initial_config(self):
        """加载现有配置（如果存在）"""
        env_path = self.project_path / ".env"
        if env_path.exists():
            try:
                with open(env_path, 'r', encoding='utf-8') as f:
                    for line in f:
                        line = line.strip()
                        if line.startswith('MIRROR_API_KEY='):
                            self.config_vars["api_key"].set(line.split('=', 1)[1])
                        elif line.startswith('MIRROR_BASE_URL='):
                            self.config_vars["base_url"].set(line.split('=', 1)[1])
                        elif line.startswith('MIRROR_MODEL='):
                            self.config_vars["model"].set(line.split('=', 1)[1])
                        elif line.startswith('MIRROR_TIMEOUT='):
                            self.config_vars["timeout"].set(line.split('=', 1)[1])
                        elif line.startswith('MIRROR_CONTEXT_WINDOW='):
                            self.config_vars["context_window"].set(line.split('=', 1)[1])
                        elif line.startswith('MIRROR_MAX_MESSAGE_TOKENS='):
                            self.config_vars["max_message_tokens"].set(line.split('=', 1)[1])
                        elif line.startswith('MIRROR_MAX_TOKENS='):
                            self.config_vars["max_tokens"].set(line.split('=', 1)[1])

                self._set_status("已加载现有 .env 配置")
            except Exception as e:
                self._set_status(f"加载配置失败: {e}")

        self._update_preview()

    def _set_status(self, message: str):
        """设置状态栏消息（带防御性检查）"""
        if hasattr(self, 'status_label') and self.status_label:
            self.status_label.config(text=message)


# ============================================================================
# 主程序入口
# ============================================================================

def main():
    """主程序入口"""
    root = tk.Tk()

    # 设置高分屏支持（Windows）
    try:
        from ctypes import windll
        windll.shcore.SetProcessDpiAwareness(1)
    except:
        pass

    # 应用样式
    style = ttk.Style()
    style.theme_use('clam')

    # 创建主窗口
    app = MirrorConfigTool(root)

    # 启动主循环
    root.mainloop()


if __name__ == "__main__":
    main()
