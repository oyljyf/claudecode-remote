# 安装与卸载指南

## 系统要求

- **macOS**、**Linux** 或 **Windows (WSL)**
- [Claude Code CLI](https://docs.anthropic.com/en/docs/claude-code)
- Python 3.10+

## 快速安装（推荐）

### 1. 获取 Telegram Bot Token

1. 在 Telegram 找到 [@BotFather](https://t.me/BotFather)
2. 发送 `/newbot`
3. 按提示设置名称
4. 保存返回的 token（格式：`123456789:ABC-DEF...`）
5. 在 @BotFather 中输入 `/mybots`
6. 选择你的 bot
7. 点击 @username 跳转到 bot 聊天窗口
8. 点击 "Start" 按钮

### 2. 克隆并安装

```bash
git clone https://github.com/oyljyf/claudecode-remote
cd claudecode-remote
./scripts/install.sh YOUR_TELEGRAM_BOT_TOKEN
```

### 3. 启动

```bash
source ~/.zshrc  # 或重启终端
./scripts/start.sh --new
```

### 检查安装状态

```bash
./scripts/install.sh --check
```

### 重新安装

```bash
./scripts/install.sh --force YOUR_TELEGRAM_BOT_TOKEN
```

---

## 手动安装

如果自动安装失败，可以按以下步骤手动安装。

### 1. 安装系统依赖

```bash
brew install tmux cloudflared jq
```

### 2. 克隆项目

```bash
git clone https://github.com/oyljyf/claudecode-remote
cd claudecode-remote
```

### 3. 配置 Python 环境

```bash
uv venv && source .venv/bin/activate
uv pip install -e .
```

### 4. 设置环境变量

添加到 `~/.zshrc` 或 `~/.bashrc`：

```bash
export TELEGRAM_BOT_TOKEN="你的token"
```

然后执行 `source ~/.zshrc`

### 5. 配置 Hooks

Hooks 负责同步 Desktop 和 Telegram、本地提醒和远程权限：
- `send-to-telegram.sh` (Stop hook) - 将 Claude 的回复发送到 Telegram
- `send-input-to-telegram.sh` (UserPromptSubmit hook) - 将桌面用户输入同步到 Telegram
- `handle-permission.sh` (PermissionRequest hook) - 将权限请求转发到 Telegram，用户远程 Allow/Deny
- `play-alarm.sh` (Stop hook) - Claude 停止时播放提醒音

**方式一：使用 start.sh**

```bash
./scripts/start.sh --setup-hook
```

**方式二：手动配置**

```bash
# 复制公共库和脚本
mkdir -p ~/.claude/hooks/lib
cp hooks/lib/common.sh ~/.claude/hooks/lib/
cp hooks/send-to-telegram.sh ~/.claude/hooks/
cp hooks/send-input-to-telegram.sh ~/.claude/hooks/
cp hooks/handle-permission.sh ~/.claude/hooks/
cp hooks/play-alarm.sh ~/.claude/hooks/
chmod +x ~/.claude/hooks/send-to-telegram.sh
chmod +x ~/.claude/hooks/send-input-to-telegram.sh
chmod +x ~/.claude/hooks/handle-permission.sh
chmod +x ~/.claude/hooks/play-alarm.sh

# 复制声音文件
mkdir -p ~/.claude/sounds
cp -n sounds/* ~/.claude/sounds/ 2>/dev/null

# 设置 token（token 定义在公共库中）
sed -i '' "s/YOUR_BOT_TOKEN_HERE/$TELEGRAM_BOT_TOKEN/" ~/.claude/hooks/lib/common.sh
```

编辑 `~/.claude/settings.json`：

```json
{
  "hooks": {
    "Stop": [
      {
        "matcher": "",
        "hooks": [
          {
            "type": "command",
            "command": "~/.claude/hooks/send-to-telegram.sh"
          }
        ]
      },
      {
        "matcher": "",
        "hooks": [
          {
            "type": "command",
            "command": "~/.claude/hooks/play-alarm.sh"
          }
        ]
      }
    ],
    "UserPromptSubmit": [
      {
        "matcher": "",
        "hooks": [
          {
            "type": "command",
            "command": "~/.claude/hooks/send-input-to-telegram.sh"
          }
        ]
      }
    ],
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
  }
}
```

---

## 更新 Hooks

当项目代码更新后，只需重新安装 hook 脚本即可，无需重装整个项目：

```bash
./scripts/start.sh --setup-hook
```

然后重启 bridge 使新命令生效：

```bash
./scripts/start.sh
```

---

## 验证安装

```bash
./scripts/install.sh --check
# 或
./scripts/start.sh --check
```

---

## 卸载

### 命令选项

```bash
./scripts/uninstall.sh              # 交互式卸载（选择要移除的组件）
./scripts/uninstall.sh --telegram   # 仅移除 Telegram hooks 和 bridge
./scripts/uninstall.sh --alarm      # 仅移除 Alarm hook 和声音文件
./scripts/uninstall.sh --all        # 完全卸载（包括日志）
./scripts/uninstall.sh --keep-deps  # 保留系统依赖
./scripts/uninstall.sh --force      # 跳过确认提示
```

### 卸载内容

| 类别          | 文件/目录                                                                                                                               |
| ------------- | --------------------------------------------------------------------------------------------------------------------------------------- |
| Telegram Hooks | `~/.claude/hooks/send-to-telegram.sh`, `~/.claude/hooks/send-input-to-telegram.sh`, `~/.claude/hooks/handle-permission.sh`, `~/.claude/hooks/lib/` |
| Alarm Hook    | `~/.claude/hooks/play-alarm.sh`, `~/.claude/sounds/`, `~/.claude/alarm_disabled`                                                        |
| Hook 配置     | `settings.json` 中的 hooks 配置                                                                                                         |
| 状态文件      | `telegram_chat_id`, `telegram_pending`, `telegram_sync_disabled`, `telegram_sync_paused`, `current_session_id`, `session_chat_map.json`, `pending_permission.json`, `permission_response.json` |
| 环境变量      | `TELEGRAM_BOT_TOKEN`（从 `.zshrc`/`.bashrc` 移除）                                                                                      |
| Python 环境   | `.venv` 目录                                                                                                                            |
| 进程          | 运行中的 bridge、cloudflared、tmux session                                                                                              |
| 临时文件      | `/tmp/tunnel_output.log`                                                                                                                |

### `--all` 额外移除

- `~/.claude/logs/` 目录
- `history.jsonl`

### 保留的内容

- Claude Code 会话文件 (`~/.claude/projects/`)
- Claude Code 本身
- 系统依赖 (`tmux`, `cloudflared`, `jq`)（除非用户确认删除）

---

## 常见问题

### Q: Claude 回复但 Telegram 收不到

检查 hook 配置：
```bash
# 检查 token 是否已配置（token 定义在公共库中）
grep "TELEGRAM_BOT_TOKEN" ~/.claude/hooks/lib/common.sh
```

确保 hook 脚本和公共库都存在且 token 已配置。

> 更多连接和同步问题见 [启动指南 - 常见问题](start.md#常见问题)。
