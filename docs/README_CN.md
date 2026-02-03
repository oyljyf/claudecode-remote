# Claude Code Telegram 远程控制

通过 Telegram 远程控制 Claude Code，实现手机与电脑的消息同步。

## 核心功能

当你需要远程操作时，运行：

```bash
./scripts/start.sh --new
```

这会：
1. 创建新的 tmux session（名为 `claude`）
2. 自动启动 Claude Code
3. 建立 Cloudflare 隧道
4. 连接 Telegram Bot

之后你可以通过 Telegram 发送消息，Claude 的回复也会同步到 Telegram。

## 安装

### 1. 获取 Telegram Bot Token

在 Telegram 中找 [@BotFather](https://t.me/BotFather)，发送 `/newbot` 创建机器人，获取 Token。

### 2. 一键安装

```bash
git clone https://github.com/oyljyf/claudecode-remote
cd claudecode-remote
./scripts/install.sh YOUR_TELEGRAM_BOT_TOKEN
```

### 3. 加载环境变量

```bash
source ~/.zshrc  # 或 source ~/.bashrc
```

## 启动

```bash
# 首次启动 / 创建新会话
./scripts/start.sh --new

# 重启 bridge（连接不稳定时）
./scripts/start.sh

# 查看 Claude 输出（不进入 tmux）
./scripts/start.sh --view

# 进入 tmux 会话
./scripts/start.sh --attach

# 退出 tmux（从另一个终端运行）
./scripts/start.sh --detach
```

## Telegram 命令

| 命令      | 说明         |
| --------- | ------------ |
| `/status` | 查看状态     |
| `/stop`   | 中断 Claude  |
| `/clear`  | 清空对话     |
| `/resume` | 恢复历史会话 |

## 常见问题

### 消息发不出去 / 连接断开

重启 bridge：

```bash
./scripts/start.sh
```

### 检查配置是否正确

```bash
./scripts/start.sh --check
```

### tmux session 不存在

```bash
./scripts/start.sh --new
```

### 日志位置

- 对话日志：`~/.claude/logs/cc_DDMMYY.log`
- 调试日志：`~/.claude/logs/debug.log`
- 清理日志：`./scripts/clean-logs.sh 7`（保留 7 天，无参数默认 30 天）
