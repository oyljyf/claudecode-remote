# 启动指南

## 快速启动

```bash
./scripts/start.sh --new
```

这会自动：
1. 创建 tmux session（交互式 shell，支持鼠标滚动）
2. 在 shell 中启动 Claude Code
3. 启动 bridge 服务
4. 启动 cloudflared 隧道
5. 设置 Telegram webhook
6. 自动 attach 到 Claude 界面

> 首次使用前需要运行 `./scripts/install.sh` 或 `./scripts/start.sh --setup-hook` 配置 hooks

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

| 命令                              | 说明                                     |
| --------------------------------- | ---------------------------------------- |
| `./scripts/start.sh`              | 启动/重启 bridge（tmux 需已存在）        |
| `./scripts/start.sh --new`        | 创建 tmux + Claude + bridge，自动 attach |
| `./scripts/start.sh --new <path>` | 为指定项目目录创建 session               |
| `./scripts/start.sh --attach`     | 列出 sessions 供选择，然后 attach        |
| `./scripts/start.sh --detach`     | 从另一个终端脱离 tmux                    |
| `./scripts/start.sh --view`       | 查看 Claude 最近输出（不 attach）        |
| `./scripts/start.sh --check`      | 检查配置状态                             |
| `./scripts/start.sh --setup-hook` | 安装/更新 Hook 脚本                      |
| `./scripts/start.sh --sync`       | 显示桌面/Telegram 同步说明               |
| `./scripts/start.sh --terminate`  | 终止所有进程并禁用同步                   |
| `./scripts/start.sh --help`       | 显示帮助                                 |

---

## tmux 控制

由于 Claude Code 会捕获大部分快捷键，无法使用传统的 tmux 快捷键脱离。请使用以下命令（从另一个终端）：

```bash
./scripts/start.sh --detach   # 脱离 tmux
./scripts/start.sh --attach   # 重新 attach（可选择 session）
./scripts/start.sh --view     # 查看输出（不 attach）
```

### tmux 滚动

tmux session 创建时自动配置：
- `mouse on` — 支持鼠标滚动查看历史
- `history-limit 10000` — 保留 10000 行历史
- `allow-rename off` — 防止 shell 覆盖窗口标题

如果是旧 session 不支持滚动，需要 `./scripts/start.sh --new` 重新创建。

---

## Telegram Bot 命令

| 命令             | 说明                                      |
| ---------------- | ----------------------------------------- |
| `/start`         | 新建 Claude 对话                          |
| `/stop`          | 暂停同步（用 `/start`、`/resume` 或 `/continue` 恢复） |
| `/escape`        | 中断 Claude（发送 Escape 键）             |
| `/terminate`     | 彻底断开（需 `/start` 重连）              |
| `/resume`        | 恢复 session（显示选择列表）              |
| `/continue`      | 继续最近的 session                        |
| `/projects`      | 浏览项目并选择 session                    |
| `/bind`          | 绑定当前 session 到聊天                   |
| `/clear`         | 清空对话                                  |
| `/status`        | 查看 tmux、同步、绑定状态                 |
| `/loop <prompt>` | Ralph Loop：自动迭代模式                  |

---

## 环境变量

| 变量                 | 说明              | 默认值   |
| -------------------- | ----------------- | -------- |
| `TELEGRAM_BOT_TOKEN` | Bot token（必需） | -        |
| `TMUX_SESSION`       | tmux session 名称 | `claude` |
| `PORT`               | Bridge 端口       | `8080`   |

自定义端口：

```bash
export PORT=9090
./scripts/start.sh
```

重启后 bridge、cloudflared tunnel、Telegram webhook 会自动使用新端口，无需额外操作。

---

## 桌面 & Telegram 同步

运行 `./scripts/start.sh --sync` 查看详细说明。

**场景 1：桌面已有对话，Telegram 要加入**
- 在 Telegram 直接发消息（自动绑定）
- 或发送 `/resume` 选择相同的 session

**场景 2：Telegram 已有对话，桌面要加入**
```bash
./scripts/start.sh --attach
```

**场景 3：从 Telegram 切换到不同项目**
```
/projects
```
选择项目 → 选择 session 或新建。Bridge 自动处理跨项目 `cd` 和 Claude 重启。

> 桌面和 Telegram 共享同一 tmux 终端。一方发消息时，另一方可以看到。

---

## 三态同步控制

### 暂停同步（保持连接）

Telegram 发送 `/stop`，或桌面继续使用 Claude 不受影响。

恢复：`/start` 或 `/resume`

### 中断 Claude 当前操作

Telegram 发送 `/escape`，等同于桌面按 Escape 键。同步状态不变。

### 彻底断开

Telegram 发送 `/terminate`，或桌面运行：
```bash
./scripts/start.sh --terminate
```

需要 `/start` 或 `/resume` 才能重连。

---

## 常见问题

### Telegram 无法发送消息到桌面

```bash
tmux list-sessions          # 查看 tmux sessions
./scripts/start.sh --check  # 检查配置
```

1. 确保 bridge 已启动：`./scripts/start.sh`
2. 确保 tmux session 存在：`./scripts/start.sh --new`
3. 发送 `/status` 检查状态

### 桌面无法发送到 Telegram

```bash
tail -20 ~/.claude/logs/debug.log
```

1. Hook 未配置 — 运行 `./scripts/start.sh --setup-hook`
2. `TELEGRAM_BOT_TOKEN` 未设置 — 检查 `~/.claude/hooks/lib/common.sh` 中的 token
3. `~/.claude/telegram_chat_id` 不存在 — 需先从 Telegram 发送一条消息

### 连接不稳定 / 消息偶尔丢失

重启 bridge：`./scripts/start.sh`

### tmux 无法滚动

tmux session 创建时自动启用 `mouse on` 和 `history-limit 10000`。如果是旧 session，需要 `./scripts/start.sh --new` 重新创建。

### Bridge 显示 "python: command not found"

确保 `.venv` 已创建且 `python3` 可用。

---

## 日志管理

| 日志类型 | 路径                             | 说明            |
| -------- | -------------------------------- | --------------- |
| 对话日志 | `~/.claude/logs/cc_MMDDYYYY.log` | 每日对话记录    |
| 调试日志 | `~/.claude/logs/debug.log`       | Bridge 调试信息 |

日志在 Paused 和 Terminated 状态下仍然记录。

```bash
# 查看今天的对话日志
cat ~/.claude/logs/cc_$(date +%m%d%Y).log

# 实时查看调试日志
tail -f ~/.claude/logs/debug.log

# 清理旧日志
./scripts/clean-logs.sh 7     # 保留 7 天
./scripts/clean-logs.sh       # 默认保留 30 天
```

---

## 完全停止服务

1. 脱离 tmux：`./scripts/start.sh --detach`
2. 终止所有进程：`./scripts/start.sh --terminate`

或者在 bridge 终端按 `Ctrl+C`，会自动清理所有进程。
