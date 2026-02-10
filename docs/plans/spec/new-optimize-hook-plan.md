# Hook 嵌入 Python 提取 & 优化计划

- Version: 1.0.0
- Updated at: 2026-02-10 10:01:45
- Status: 📝 Planning

---

## 背景

当前 3 个 hook shell 脚本中嵌入了大量 Python heredoc 代码（共 ~255 行），存在以下问题：

| 问题       | 影响                                                                      |
| ---------- | ------------------------------------------------------------------------- |
| 代码重复   | `send_telegram()`、`log_message()`、`log_debug()` 在 3 个 hook 中各写一遍 |
| 不可测试   | heredoc 嵌入的 Python 无法被 pytest 单元测试覆盖                          |
| 可读性差   | Shell 和 Python 混排，IDE 无法提供语法高亮和补全                          |
| 维护成本高 | 修改 Telegram API 调用方式需要改 3 个文件                                 |

### 现状统计

| Hook 脚本                   | 嵌入 Python 行数  | 功能                                              |
| --------------------------- | ----------------- | ------------------------------------------------- |
| `send-to-telegram.sh`       | ~78 行 (L68-145)  | Markdown→HTML 转换 + Telegram 发送 + 日志         |
| `send-input-to-telegram.sh` | ~43 行 (L32-74)   | Telegram 发送 + 日志                              |
| `handle-permission.sh`      | ~134 行 (L36-169) | Telegram 发送(含 inline keyboard) + 文件 IPC 轮询 |

---

## 架构设计

### 目标结构

```
hooks/lib/
├── common.sh              # (已有) Shell 共享变量和函数
├── telegram_utils.py      # (新增) 共享 Python 模块
├── send_response.py       # (新增) send-to-telegram 的 Python 逻辑
├── send_input.py          # (新增) send-input-to-telegram 的 Python 逻辑
└── handle_perm.py         # (新增) handle-permission 的 Python 逻辑
```

### 调用关系

```
send-to-telegram.sh ──────► python3 "$(dirname "$0")/lib/send_response.py" [args...]
                                    └── import telegram_utils

send-input-to-telegram.sh ► python3 "$(dirname "$0")/lib/send_input.py" [args...]
                                    └── import telegram_utils

handle-permission.sh ──────► python3 "$(dirname "$0")/lib/handle_perm.py" [args...]
                                    └── import telegram_utils
```

### Shell 脚本职责变化

**重构前** (send-to-telegram.sh):
```
Shell: source common.sh → jq 提取数据 → 构造参数
Python heredoc: Markdown 转换 → Telegram 发送 → 日志记录
Shell: 清理临时文件
```

**重构后** (send-to-telegram.sh):
```
Shell: source common.sh → jq 提取数据 → 构造参数
Shell: python3 "$(dirname "$0")/lib/send_response.py" [args...]
Shell: 清理临时文件
```

---

## Phase 1: 创建共享 Python 模块

**文件**: `hooks/lib/telegram_utils.py`

提取 3 个 hook 中的公共函数：

```python
# telegram_utils.py — 共享工具函数（仅 stdlib 依赖）

def send_telegram(token, chat_id, text, parse_mode=None, reply_markup=None):
    """发送消息到 Telegram Bot API，返回 bool 表示成功/失败"""

def log_message(log_file, text, role="Claude"):
    """追加到日志文件，格式: [HH:MM] Role:\ntext\n---"""

def log_debug(debug_log, msg):
    """追加到 debug 日志，格式: [HH:MM:SS] msg"""

def html_escape(s):
    """转义 HTML 特殊字符: & < >"""

def markdown_to_telegram_html(text):
    """Markdown → Telegram HTML（代码块、内联代码、加粗、斜体）"""

def truncate(text, max_len=4000):
    """截断文本并添加省略号"""
```

### 设计要点

- **零外部依赖**：仅使用 `sys`, `os`, `json`, `re`, `urllib.request`, `hashlib`, `time`, `datetime`
- **每个函数独立**：不依赖全局状态，所有依赖通过参数传入
- **错误处理**：网络错误返回 `False` 而非抛异常，保持 hook 快速退出的特性

---

## Phase 2: 创建 3 个 Hook Python 入口脚本

### 2a. `hooks/lib/send_response.py`

从 `send-to-telegram.sh` 提取的逻辑：

```python
#!/usr/bin/env python3
"""Stop hook: 提取 Claude 响应，Markdown→HTML，发送到 Telegram"""
# 参数: tmpfile chat_id token log_file debug_log sync_disabled

import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from telegram_utils import (
    send_telegram, log_message, log_debug,
    markdown_to_telegram_html, truncate
)

def main():
    tmpfile, chat_id, token, log_file, debug_log, sync_disabled = sys.argv[1:7]
    # ... 主逻辑 ...

if __name__ == "__main__":
    main()
```

### 2b. `hooks/lib/send_input.py`

从 `send-input-to-telegram.sh` 提取的逻辑：

```python
#!/usr/bin/env python3
"""UserPromptSubmit hook: 同步桌面输入到 Telegram"""
# 参数: prompt chat_id token log_file from_telegram sync_disabled
```

### 2c. `hooks/lib/handle_perm.py`

从 `handle-permission.sh` 提取的逻辑：

```python
#!/usr/bin/env python3
"""PermissionRequest hook: 转发权限请求到 Telegram，轮询响应"""
# 参数: tool_name tool_input chat_id token pending_file response_file
```

### import 机制

所有入口脚本通过 `sys.path.insert(0, ...)` 导入同目录的 `telegram_utils.py`，无需 `__init__.py` 或 pip 安装：

```python
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from telegram_utils import send_telegram, log_message
```

---

## Phase 3: 重构 3 个 Hook Shell 脚本

将 heredoc Python 替换为 `python3` 调用：

### send-to-telegram.sh (重构后)

```bash
# 替换 L68-145 的 heredoc 为:
HOOK_LIB="$(dirname "$0")/lib"
python3 "$HOOK_LIB/send_response.py" \
    "$TMPFILE" "$CHAT_ID" "$TELEGRAM_BOT_TOKEN" \
    "$LOG_FILE" "$DEBUG_LOG" "$SYNC_DISABLED"
```

### send-input-to-telegram.sh (重构后)

```bash
# 替换 L32-74 的 heredoc 为:
HOOK_LIB="$(dirname "$0")/lib"
python3 "$HOOK_LIB/send_input.py" \
    "$PROMPT" "$CHAT_ID" "$TELEGRAM_BOT_TOKEN" \
    "$LOG_FILE" "$FROM_TELEGRAM" "$SYNC_DISABLED"
```

### handle-permission.sh (重构后)

```bash
# 替换 L36-169 的 heredoc 为:
HOOK_LIB="$(dirname "$0")/lib"
python3 "$HOOK_LIB/handle_perm.py" \
    "$TOOL_NAME" "$TOOL_INPUT" "$CHAT_ID" "$TELEGRAM_BOT_TOKEN" \
    "$PERM_PENDING_FILE" "$PERM_RESPONSE_FILE"
```

---

## Phase 4: 更新安装脚本

### install.sh & start.sh (`--setup-hook`)

当前只复制 `hooks/lib/common.sh` → `~/.claude/hooks/lib/common.sh`。需要同时复制 `*.py` 文件：

```bash
# 现有逻辑
cp -f "$SCRIPT_DIR/hooks/lib/common.sh" "$HOOKS_LIB_DIR/common.sh"

# 新增
cp -f "$SCRIPT_DIR/hooks/lib/"*.py "$HOOKS_LIB_DIR/"
```

### uninstall.sh

确认 `~/.claude/hooks/lib/` 目录删除时包含 `.py` 文件（当前 `rm -rf` 已覆盖）。

---

## Phase 5: 新增单元测试

**文件**: `tests/test_telegram_utils.py`

### 5a. telegram_utils.py 测试

```python
class TestHtmlEscape:
    # 测试 &, <, > 转义
    # 测试空字符串、纯文本

class TestMarkdownToHtml:
    # 测试代码块 ```python ... ```
    # 测试内联代码 `code`
    # 测试加粗 **bold** → <b>bold</b>
    # 测试斜体 *italic* → <i>italic</i>
    # 测试嵌套: 代码块内的 <> 不被二次转义
    # 测试超长文本截断

class TestSendTelegram:
    # Mock urllib.request, 验证请求 URL/payload
    # 测试 parse_mode=HTML
    # 测试 reply_markup (inline keyboard)
    # 测试网络超时返回 False
    # 测试无效 token 返回 False

class TestLogMessage:
    # 测试写入格式 [HH:MM] Role:\ntext\n---
    # 测试 append 模式（不覆盖）
    # 测试 log_file 目录不存在时不报错

class TestLogDebug:
    # 测试写入格式 [HH:MM:SS] msg
```

### 5b. 入口脚本测试

```python
class TestSendResponse:
    # 测试正常 Markdown 文本处理
    # 测试空文本提前退出
    # 测试 sync_disabled=1 仅日志不发送
    # 测试 HTML 发送失败降级为纯文本

class TestSendInput:
    # 测试桌面输入(from_telegram=0)发送到 Telegram
    # 测试 Telegram 输入(from_telegram=1)不发送
    # 测试 sync_disabled=1 仅日志

class TestHandlePerm:
    # 测试 Bash 工具格式化 ($ command)
    # 测试 Write/Edit 工具格式化 (file_path)
    # 测试 inline keyboard 构造
    # 测试轮询响应 allow → 输出 allow JSON
    # 测试轮询响应 deny → 输出 deny JSON
    # 测试超时 → 清理文件 + 通知
```

### 5c. Shell 脚本静态测试更新

更新 `tests/test_shell_scripts.py` 中的相关测试：

```python
class TestHookScriptsRefactored:
    # 验证 shell 脚本不再包含 heredoc (python3 - ... << 'PYEOF')
    # 验证 shell 脚本调用 python3 "$HOOK_LIB/xxx.py"
    # 验证 hooks/lib/ 目录包含所有 .py 文件
```

---

## Phase 6: 更新文档

### CLAUDE.md

- 更新 Key Components 表格，添加 `hooks/lib/*.py` 文件说明
- 更新 Message Flow 部分，反映新的调用链

### README.md / README_CN.md

- 更新项目结构说明（如有涉及）

---

## 其他优化建议（本次不实施）

以下是分析过程中发现的其他可改进点，留作后续参考：

### 1. Markdown→HTML 转换增强

当前 regex 方案的已知缺陷：
- 不支持有序/无序列表（`- item`、`1. item`）
- 不支持链接 `[text](url)`
- 嵌套格式（如代码块内的加粗）可能出问题
- 建议：后续可考虑用 `mistune`（轻量 Markdown 解析器），但需引入外部依赖

### 2. Telegram 发送大消息优化

当前截断到 4000 字符直接丢弃后续内容。改进方案：
- 分片发送（4096 字符为 Telegram 限制，按段落/代码块边界切分）
- 超长输出改为发送文件（`sendDocument`）

### 3. Bridge.py 模块化

`bridge.py` 当前是单文件 ~800+ 行，可拆分为：
- `bridge/server.py` — HTTP handler
- `bridge/telegram.py` — Telegram API
- `bridge/tmux.py` — tmux 操作
- `bridge/session.py` — Session 管理
- 但这是更大的重构，应单独规划

### 4. 错误处理改进

当前 hook 中的 `except: pass` 吞掉所有异常。改进：
- 至少记录异常到 debug log（`except Exception as e: log_debug(str(e))`）
- 区分网络超时和其他错误

### 5. 权限轮询优化

当前 `handle_perm.py` 使用 `time.sleep(1)` 轮询，120 次循环。可优化：
- macOS: 使用 `kqueue` 监听文件变化（零 CPU）
- Linux: 使用 `inotify`
- 但增加平台分支逻辑，收益有限（1 秒轮询 CPU 开销极低）

### 6. Hook 配置外部化

当前超时（120s）、轮询间隔（1s）、截断长度（4000/300）都是硬编码。可通过 `config.env` 外部化：
```bash
PERM_POLL_TIMEOUT=120
PERM_POLL_INTERVAL=1
MSG_MAX_LENGTH=4000
```

---

## 实施顺序

```
Phase 1 ─► Phase 2 ─► Phase 3 ─► Phase 4 ─► Phase 5 ─► Phase 6
共享模块    入口脚本    重构shell    安装脚本    测试       文档
```

各 Phase 依次执行，每个 Phase 完成后可独立验证。
