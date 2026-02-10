# Claude Code Telegram 远程控制

通过 Telegram 远程控制 Claude Code，实现手机与电脑的双向消息同步。

## 核心功能

- **双向同步**：桌面 Claude 回复和用户输入自动同步到 Telegram；Telegram 消息自动注入桌面 Claude
- **自动绑定**：首条消息自动绑定 session，无需手动 `/bind`
- **跨项目切换**：从 Telegram 浏览不同项目并切换 session，bridge 自动处理 `cd` + 重启
- **三态同步**：Active（活跃）/ Paused（暂停）/ Terminated（断开），日志始终记录
- **tmux 滚动**：支持鼠标滚动和 10000 行历史记录
- **远程权限控制**：Claude 请求工具权限时，CC 原始请求直接转发到 Telegram，在 Telegram 回复即可
- **本地提醒音**：Claude 停止时（任务完成或等待输入）播放声音，切到其他窗口也不会错过

## 安装

### 1. 获取 Telegram Bot Token

在 Telegram 中找 [@BotFather](https://t.me/BotFather)，发送 `/newbot` 创建机器人，获取 Token。

### 2. 一键安装

```bash
git clone https://github.com/oyljyf/claudecode-remote
cd claudecode-remote
./scripts/install.sh YOUR_TELEGRAM_BOT_TOKEN
```

### 3. 加载环境变量并启动

```bash
source ~/.zshrc  # 或 source ~/.bashrc
./scripts/start.sh --new
```

## 卸载

```bash
./scripts/uninstall.sh              # 交互式卸载（选择要移除的组件）
./scripts/uninstall.sh --telegram   # 仅移除 Telegram hooks 和 bridge
./scripts/uninstall.sh --alarm      # 仅移除 Alarm hook 和声音文件
./scripts/uninstall.sh --all        # 完全卸载（包括日志）
./scripts/uninstall.sh --keep-deps  # 保留系统依赖
./scripts/uninstall.sh --force      # 跳过确认提示
```

详细安装说明：[安装指南](install.md)

## 命令参考

### 桌面端

```bash
./scripts/start.sh              # 启动/重启 bridge（tmux 需已存在）
./scripts/start.sh --new        # 创建 tmux + Claude + bridge
./scripts/start.sh --new <path> # 为指定项目目录创建 session
./scripts/start.sh --attach     # 列出 sessions 供选择，然后 attach
./scripts/start.sh --detach     # 从另一个终端脱离 tmux
./scripts/start.sh --view       # 查看 Claude 最近输出（不 attach）
./scripts/start.sh --terminate  # 终止所有进程并禁用同步
```

### Telegram 端

```bash
/start         # 新建 Claude 对话
/stop          # 暂停同步（用 /start、/resume 或 /continue 恢复）
/escape        # 中断 Claude（发送 Escape 键）
/terminate     # 彻底断开（需 /start 重连）
/resume        # 恢复 session（显示选择列表）
/continue      # 继续最近的 session
/projects      # 浏览项目并选择 session
/bind          # 绑定当前 session 到聊天
/clear         # 清空对话
/status        # 查看 tmux、同步、绑定状态
/loop <prompt> # Ralph Loop：自动迭代模式
```

完整命令说明见 [启动指南](start.md)。

## 附加工具

### 远程权限控制

当 Claude 请求工具权限时（如执行命令、写文件），CC 原始请求内容直接转发到 Telegram。Hook 不做决定，CC 回退到终端对话框，你在 Telegram 回复 y/n/a 即可。

> **注意**：仅在 Claude **不使用** `--dangerously-skip-permissions` 时生效。默认的 `start.sh --new` 使用 skip-permissions，因此权限 hook 不会触发。

安装：`./scripts/start.sh --setup-hook`（随其他 hooks 一起安装）。

---

### 日志管理

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
bash ./scripts/clean-logs.sh 7     # 保留 7 天
bash ./scripts/clean-logs.sh       # 默认保留 30 天
```

---

### 本地提醒音

当 Claude 需要你关注时会播放声音提醒，即使你在其他窗口或 tmux session 也不会错过。

提醒音触发场景：

| Hook 事件      | 触发时机                              |
| -------------- | ------------------------------------- |
| `Stop`         | Claude 完成回复（任务完成或需要输入） |
| `Notification` | Claude 提问或请求工具权限             |

将声音文件放在项目目录的 `sounds/alarm.mp3`，然后运行 `./scripts/start.sh --setup-hook` 安装。

```bash
touch ~/.claude/alarm_disabled     # 禁用提醒音
rm ~/.claude/alarm_disabled        # 启用提醒音
export ALARM_VOLUME=0.3            # 调节音量 (0.0-1.0)
```

## 环境变量

| 变量                 | 说明              | 默认值   |
| -------------------- | ----------------- | -------- |
| `TELEGRAM_BOT_TOKEN` | Bot token（必填） | -        |
| `TMUX_SESSION`       | tmux session 名称 | `claude` |
| `PORT`               | Bridge 端口       | `8080`   |
| `ALARM_VOLUME`       | 提醒音音量        | `0.5`    |
| `ALARM_ENABLED`      | 启用/禁用提醒音   | `true`   |

自定义端口：

```bash
export PORT=9090
./scripts/start.sh
```

重启后 bridge、cloudflared tunnel 和 Telegram webhook 会自动使用新端口。

## 详细文档

- [安装指南](install.md) - 安装与卸载
- [启动指南](start.md) - 启动选项与故障排除
- [使用场景](usage.md) - Telegram 和桌面端的完整使用场景

## 常见问题

连接断开或消息不同步时，重启 bridge：`./scripts/start.sh`。发送 `/status` 检查状态。

更多问题排查见 [启动指南 - 常见问题](start.md#常见问题)。
