# PermissionRequest Hook 实现计划

- Version: 2.0.0
- Updated at: 2026-02-11 10:13:36
- Status: ✅ Implemented

---

## 概述

将所有 PermissionRequest 转发到 Telegram inline keyboard，而不仅仅是 AskUserQuestion。

## 背景

之前 `handle-permission.sh` 只转发 `AskUserQuestion` 工具的权限请求到 Telegram，其他工具（Edit、Bash、Write 等）静默退出（`exit 0`），CC 回退到终端 TUI 对话框（y/n/a）。用户无法从 Telegram 远程响应这些权限请求。

## 实现方案

### 修改 `hooks/handle-permission.sh`

移除非 AskUserQuestion 工具的 `exit 0` 提前退出。根据工具类型格式化消息并发送 3 按钮 inline keyboard：

**AskUserQuestion**：保持原有行为不变（问题 + 选项按钮）

**其他工具**：格式化工具信息 + 3 按钮键盘（askq: callbacks）

| 工具 | 消息格式 |
|------|----------|
| Edit | `🔐 Edit: {file_path}` |
| Write | `🔐 Write: {file_path}` |
| Bash | `🔐 Bash:\n{command}` (截断到 300 字符) |
| 其他 | `🔐 Permission: {tool_name}` |

3 按钮：
- `askq:0` → "Yes"（第一个选项）
- `askq:1` → "Yes to all"（第二个选项）
- `askq:2` → "No"（第三个选项）

### 无需修改 bridge.py

现有的 `askq:` callback handler（Down+Enter 导航）已支持任何 TUI 选项菜单。

## 修改文件

1. `hooks/handle-permission.sh` — 主要修改
2. `tests/test_shell_scripts.py` — 更新测试
3. `CLAUDE.md` — 更新文档
4. `README.md` — 更新文档
5. `docs/README_CN.md` — 更新文档

## 测试验证

- 23 个权限相关测试全部通过
- 全部 248 个测试通过
- 手动验证：`--setup-hook` 后在 CC 中触发 Edit 权限 → Telegram 显示 inline keyboard
