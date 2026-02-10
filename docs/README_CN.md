# Claude Code Telegram 远程控制

通过 Telegram 远程控制 Claude Code，实现手机与电脑的双向消息同步。

## 核心功能

- **双向同步**：桌面 Claude 回复和用户输入自动同步到 Telegram；Telegram 消息自动注入桌面 Claude
- **自动绑定**：首条消息自动绑定 session，无需手动 `/bind`
- **跨项目切换**：从 Telegram 浏览不同项目并切换 session，bridge 自动处理 `cd` + 重启
- **三态同步**：Active（活跃）/ Paused（暂停）/ Terminated（断开），日志始终记录
- **tmux 滚动**：支持鼠标滚动和 10000 行历史记录

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

详细安装说明：[安装指南](install.md)

## 卸载

```bash
./scripts/uninstall.sh              # 交互式卸载
./scripts/uninstall.sh --all        # 完全卸载（包括日志）
./scripts/uninstall.sh --keep-deps  # 保留系统依赖
```

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

## 详细文档

- [安装指南](install.md) - 安装与卸载
- [启动指南](start.md) - 启动选项与故障排除
- [使用场景](usage.md) - Telegram 和桌面端的完整使用场景

## 常见问题

连接断开或消息不同步时，重启 bridge：`./scripts/start.sh`。发送 `/status` 检查状态。

更多问题排查见 [启动指南 - 常见问题](start.md#常见问题)。
