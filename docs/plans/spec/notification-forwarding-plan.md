# CC 交互对话转发计划（PermissionRequest + Notification）

- Version: 2.0.0
- Updated at: 2026-02-11 08:39:05
- Status: ✅ Implemented

---

## 概述

CC 的交互对话走两条不同的 hook 路径，需要两个 hook 协作处理：

| 场景 | Hook 事件 | 处理脚本 | 方式 |
|------|-----------|----------|------|
| Bash/Write/Edit 权限 | PermissionRequest | `handle-permission.sh` | 发工具信息，exit 0，CC 回退终端 y/n/a |
| AskUserQuestion | Notification (`elicitation_dialog`) | `send-notification-to-telegram.sh` | 读 transcript → inline keyboard |

## 事件流

```
PermissionRequest (Bash/Edit/Write):
  → handle-permission.sh：jq 提取 tool_name + tool_input → 格式化 → 发 Telegram
  → exit 0（无决策输出）→ CC 显示终端 y/n/a 对话框
  → 用户在 Telegram 回复 y/n/a → bridge 发到 tmux → CC 读取

AskUserQuestion:
  → CC 自动允许（不走 PermissionRequest）
  → CC 显示 TUI 选项对话框 → Notification (elicitation_dialog) 触发
  → send-notification-to-telegram.sh：读 transcript 最后 30 行
  → 找到 AskUserQuestion tool_use → 提取 questions/options
  → 发 Telegram inline keyboard (askq:0, askq:1, ...)
  → 用户点按钮 → bridge Down+Enter 导航 CC TUI 选中对应项
```

## 文件清单

| 文件 | 职责 |
|------|------|
| `hooks/handle-permission.sh` | PermissionRequest → 发工具信息到 Telegram |
| `hooks/send-notification-to-telegram.sh` | Notification → 读 transcript → AskUserQuestion inline keyboard |
| `hooks/play-alarm.sh` | 播放提示音（Stop: done, Notification: alert） |
| `bridge.py` | `askq:` 回调 → Down+Enter 导航 CC TUI |

## settings.json

```json
"PermissionRequest": [
  { "matcher": "", "hooks": [{ "type": "command", "command": "~/.claude/hooks/handle-permission.sh", "timeout": 120 }] }
],
"Notification": [
  { "matcher": "permission_prompt|elicitation_dialog", "hooks": [
    { "type": "command", "command": "~/.claude/hooks/play-alarm.sh alert" },
    { "type": "command", "command": "~/.claude/hooks/send-notification-to-telegram.sh" }
  ]}
]
```

## 设计决策

1. **不用文件 IPC**：handle-permission.sh 直接 exit 0，让 CC 回退到终端对话框，用户通过 Telegram 文本回复（bridge 转发到 tmux）
2. **不读 tmux 屏幕**：send-notification-to-telegram.sh 从 transcript JSONL 读取结构化数据，比 tmux capture-pane 更可靠
3. **复用 askq: 回调**：bridge.py 已有 Down+Enter 导航逻辑，Notification hook 直接复用
4. **bridge.py 已清理**：移除了 CB_PERM、PERM_PENDING_FILE、PERM_RESPONSE_FILE 等不再使用的代码
