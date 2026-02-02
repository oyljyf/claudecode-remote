# 安装指南

## 快速安装（推荐）

### 1. 获取 Telegram Bot Token

1. 在 Telegram 找到 [@BotFather](https://t.me/BotFather)
2. 发送 `/newbot`
3. 按提示设置名称
4. 保存返回的 token（格式：`123456789:ABC-DEF...`）
5. 在@BotFather中输入 `/mybots`
6. 选择你的 bot
7. 点击@username跳转到bot聊天窗口
8. 点击“Start”按钮


### 2. 克隆并安装

```bash
git clone https://github.com/oyljyf/claudecode-remote
cd claudecode-remote
./scripts/install.sh YOUR_TELEGRAM_BOT_TOKEN
```

### 3. 启动

```bash
source ~/.zshrc  # 或重启终端
./scripts/start.sh
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

Hooks 负责同步 Desktop 和 Telegram：
- `send-to-telegram.sh` (Stop hook) - 将 Claude 的回复发送到 Telegram
- `send-input-to-telegram.sh` (UserPromptSubmit hook) - 将桌面用户输入同步到 Telegram

**方式一：使用 start.sh**

```bash
./scripts/start.sh --setup-hook
```

**方式二：手动配置**

```bash
# 复制脚本
mkdir -p ~/.claude/hooks
cp hooks/send-to-telegram.sh ~/.claude/hooks/
cp hooks/send-input-to-telegram.sh ~/.claude/hooks/
chmod +x ~/.claude/hooks/send-to-telegram.sh
chmod +x ~/.claude/hooks/send-input-to-telegram.sh

# 设置 token
sed -i '' "s/YOUR_BOT_TOKEN_HERE/$TELEGRAM_BOT_TOKEN/" ~/.claude/hooks/send-to-telegram.sh
sed -i '' "s/YOUR_BOT_TOKEN_HERE/$TELEGRAM_BOT_TOKEN/" ~/.claude/hooks/send-input-to-telegram.sh
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
    ]
  }
}
```

---

## 验证安装

```bash
./scripts/install.sh --check
# 或
./scripts/start.sh --check
```

---

## 附加工具

### 日志清理

对话记录保存在 `~/.claude/logs/`，使用以下命令清理旧日志：

```bash
./scripts/clean-logs.sh       # 删除 30 天前的日志
./scripts/clean-logs.sh 7     # 删除 7 天前的日志
```

---

## 常见问题

### Q: Claude 回复但 Telegram 收不到

检查 hook 配置：
```bash
grep "TELEGRAM_BOT_TOKEN" ~/.claude/hooks/send-to-telegram.sh
grep "TELEGRAM_BOT_TOKEN" ~/.claude/hooks/send-input-to-telegram.sh
```

确保两个文件都存在且 token 已配置。

### Q: Telegram 发消息但 Claude 无反应

发送 `/status` 检查 tmux 状态，确保 webhook 已设置。

### Q: 提示 tmux session not found

```bash
tmux new -s claude
claude --dangerously-skip-permissions
```
