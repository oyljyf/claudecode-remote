# 启动指南

## 快速启动

```bash
./scripts/start.sh --new
```

这会自动：
1. 创建 tmux session 并启动 Claude
2. 启动 bridge 服务
3. 启动 cloudflared 隧道
4. 设置 Telegram webhook
5. 自动 attach 到 Claude 界面

成功后显示：
```
========================================
  Bridge is running!
========================================

  Tunnel:  https://xxx.trycloudflare.com
  Bridge:  http://localhost:8080
  tmux:    claude
```

---

## 命令选项

| 命令 | 说明 |
|------|------|
| `./scripts/start.sh` | 启动/重启 bridge（修复连接不稳定） |
| `./scripts/start.sh --new` | 创建 tmux + Claude + bridge，自动 attach |
| `./scripts/start.sh --attach` | 列出 sessions 供选择，然后 attach |
| `./scripts/start.sh --detach` | 从另一个终端脱离 tmux |
| `./scripts/start.sh --view` | 查看 Claude 最近输出（不 attach） |
| `./scripts/start.sh --check` | 检查配置状态 |
| `./scripts/start.sh --setup-hook` | 配置 Claude hook |
| `./scripts/start.sh --sync` | 显示桌面/Telegram 同步说明 |
| `./scripts/start.sh --help` | 显示帮助 |

---

## tmux 控制

由于 Claude Code 会捕获大部分快捷键，无法使用传统的 tmux 快捷键脱离。请使用以下命令（从另一个终端）：

```bash
./scripts/start.sh --detach   # 脱离 tmux
./scripts/start.sh --attach   # 重新 attach（可选择 session）
./scripts/start.sh --view     # 查看输出（不 attach）
```

---

## Telegram Bot 命令

| 命令 | 说明 |
|------|------|
| `/status` | 检查 tmux 状态 |
| `/stop` | 中断 Claude |
| `/clear` | 清空对话 |
| `/resume` | 恢复历史 session |

---

## 环境变量

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `TELEGRAM_BOT_TOKEN` | Bot token（必需） | - |
| `TMUX_SESSION` | tmux session 名称 | `claude` |
| `PORT` | Bridge 端口 | `8080` |

---

## 桌面 & Telegram 同步

运行 `./scripts/start.sh --sync` 查看详细说明。

**场景 1：桌面已有对话，Telegram 要加入**
- 在 Telegram 发送 `/resume`，选择相同的 session

**场景 2：Telegram 已有对话，桌面要加入**
```bash
./scripts/start.sh --attach  # 选择要恢复的 session
```

**注意：** 桌面和 Telegram 不能同时发送消息，会造成冲突。一方发送时，另一方只查看。

---

## 常见问题

### Telegram 无法发送消息到桌面

**症状：** 桌面可以发送到 Telegram，但 Telegram 发送的消息没有反应。

**原因：** tmux session 名称不匹配。Bridge 默认查找名为 `claude` 的 session。

**检查方法：**
```bash
# 查看现有 tmux sessions
tmux list-sessions

# 检查 bridge 状态
curl http://localhost:8080
```

**解决方案：**

方案 1：创建名为 `claude` 的 session
```bash
tmux new-session -d -s claude
tmux send-keys -t claude "claude --dangerously-skip-permissions" Enter
```

方案 2：修改 bridge 使用现有 session
```bash
# 假设你的 session 名为 "default"
TMUX_SESSION=default python3 bridge.py
```

### 连接不稳定 / 消息偶尔丢失

**症状：** Telegram 发送的消息有时停留在桌面输入框中没有发出，或者消息偶尔丢失。

**解决方案：** 重启 bridge

```bash
./scripts/start.sh
```

---

### 桌面无法发送到 Telegram

**症状：** Telegram 消息能到桌面，但桌面回复不会发送到 Telegram。

**检查方法：**
```bash
# 查看 hook 日志
tail -20 ~/.claude/logs/debug.log

# 检查 hook 配置
cat ~/.claude/settings.json | jq '.hooks'
```

**常见原因：**
1. Hook 未配置 - 运行 `./scripts/start.sh --setup-hook`
2. `TELEGRAM_BOT_TOKEN` 未设置
3. `~/.claude/telegram_chat_id` 文件不存在（需先从 Telegram 发送一条消息）

---

## 日志管理

对话记录保存在 `~/.claude/logs/` 目录：

| 文件 | 说明 |
|------|------|
| `cc_DDMMYY.log` | 每日对话记录（如 `cc_020226.log`） |
| `debug.log` | Hook 调试日志 |

**查看日志：**
```bash
# 查看今日对话
cat ~/.claude/logs/cc_$(date +%d%m%y).log

# 查看调试日志
tail -50 ~/.claude/logs/debug.log
```

**清理旧日志：**
```bash
./scripts/clean-logs.sh       # 删除 30 天前的日志
./scripts/clean-logs.sh 7     # 删除 7 天前的日志
```

---

## 停止服务

1. 先脱离 tmux：`./scripts/start.sh --detach`
2. 在 bridge 终端按 `Ctrl+C`

会自动清理所有进程。
