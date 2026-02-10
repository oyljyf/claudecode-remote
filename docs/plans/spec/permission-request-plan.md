# PermissionRequest Hook 实现计划

- Version: 1.0.0
- Updated at: 2026-02-10 07:46:53
- Status: ✅ Implemented

---

## Context

当 Claude Code 需要工具权限时（如执行 Bash 命令、写文件），用户必须在桌面终端操作。本功能通过 PermissionRequest hook 将权限请求转发到 Telegram，用户点击 Allow/Deny 按钮即可远程响应。

**前提**：此功能仅在 Claude 不使用 `--dangerously-skip-permissions` 时生效。

**通信机制**：Hook（同步 shell 脚本）与 Bridge（HTTP 服务器）通过文件 IPC 通信：
```
Claude → PermissionRequest hook → Telegram (buttons)
                ↕ (file IPC)
         Bridge ← Telegram callback → permission_response.json
```

## 修改文件

| 文件 | 操作 |
|------|------|
| `hooks/handle-permission.sh` | 新建 — PermissionRequest hook 脚本 |
| `bridge.py` | 新增常量、权限回调处理 |
| `hooks/lib/common.sh` | 新增 `PERM_PENDING_FILE`、`PERM_RESPONSE_FILE` |
| `scripts/lib/common.sh` | 同步新增相同变量 |
| `scripts/start.sh` | HOOK_CONFIG 新增 PermissionRequest、setup_hook() 复制脚本 |
| `scripts/install.sh` | 复制脚本、jq merge、heredoc 模板 |
| `scripts/uninstall.sh` | state_files 追加、删除脚本、jq 清理 |
| `tests/conftest.py` | monkeypatch 新增文件路径 |
| `tests/test_handler.py` | 新增 TestPermissionCallback 类（4 个测试） |
| `tests/test_shell_scripts.py` | 新增 TestPermissionHookIntegration 类（12 个测试） |

## settings.json 条目

```json
"PermissionRequest": [
  {
    "matcher": "",
    "hooks": [
      {
        "type": "command",
        "command": "~/.claude/hooks/handle-permission.sh",
        "timeout": 120
      }
    ]
  }
]
```

## Hook 工作流

1. Claude 触发 PermissionRequest → hook 脚本接收 stdin JSON（含 `tool_name`、`tool_input`）
2. 脚本格式化消息（Bash→命令、Write/Edit→文件路径、其他→JSON 摘要）
3. 发送 Telegram inline keyboard：`[✅ Allow] [❌ Deny]`
4. 写 `~/.claude/pending_permission.json`（含 id、tool_name、timestamp）
5. 轮询 `~/.claude/permission_response.json`（1 秒间隔，120 秒超时）
6. Bridge 收到用户点击 → 校验 pending id → 写 response 文件
7. Hook 读取 response → 输出 JSON 决策 → Claude 继续/拒绝
8. 超时 → 清理文件 → exit 0（回退到正常终端对话框）

## 关键文件

| 文件 | 用途 |
|------|------|
| `~/.claude/pending_permission.json` | Hook 写入，Bridge 校验 |
| `~/.claude/permission_response.json` | Bridge 写入，Hook 读取 |

## 验证步骤

1. `pytest tests/ -v` — 全部测试通过（156 tests）
2. `./scripts/start.sh --setup-hook` — hook 被复制且 settings.json 更新
3. 不使用 `--dangerously-skip-permissions` 启动 Claude → 触发权限请求 → Telegram 收到按钮 → 点击后 Claude 继续
