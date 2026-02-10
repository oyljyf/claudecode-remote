# Alarm Hook 实现计划

- Version: 1.0.0
- Updated at: 2026-02-10 07:56:29
- Status: ✅ Implemented

---

## Context

当 Claude 完成任务或需要用户输入时，用户可能不在当前窗口（切到其他 app 或其他 tmux session）。本功能通过 Claude Code hooks 播放本地声音提醒用户。

**参考**: [RedAlert2-Claude](https://github.com/op7418/RedAlert2-Claude) — 使用 Claude Code hooks + `afplay` 播放声音

## 触发事件

| Hook 事件      | Matcher                                  | 触发时机                         |
| -------------- | ---------------------------------------- | -------------------------------- |
| `Stop`         | （空，匹配所有）                          | Claude 完成回复（任务完成或等待输入） |
| `Notification` | `permission_prompt\|elicitation_dialog`  | Claude 提问或请求权限            |

**排除**: `idle_prompt`（会频繁打扰）、`auth_success`（无需提醒）

## 修改文件

| 文件                   | 操作                                  |
| ---------------------- | ------------------------------------- |
| `hooks/play-alarm.sh`  | 新建 — alarm hook 脚本                |
| `sounds/`              | 新建目录 — 预留声音文件位置           |
| `sounds/alarm.mp3`     | 待用户提供                            |
| `scripts/install.sh`   | 更新 — 复制 alarm hook + sounds       |
| `scripts/start.sh`     | 更新 — `--setup-hook` 注册 alarm hook |
| `scripts/uninstall.sh` | 更新 — 清理 alarm 相关文件            |

## Hook 逻辑（play-alarm.sh）

```bash
#!/bin/bash
source "$(dirname "$0")/lib/common.sh"

# Check if alarm is enabled
[ -f ~/.claude/alarm_disabled ] && exit 0
[ "${ALARM_ENABLED:-true}" = "false" ] && exit 0

SOUND_DIR=~/.claude/sounds
VOLUME="${ALARM_VOLUME:-0.5}"

# Find sound file
SOUND_FILE="$SOUND_DIR/alarm.mp3"
if [ ! -f "$SOUND_FILE" ]; then
    exit 0  # No sound file, silently skip
fi

# Play in background (non-blocking, hook must return quickly)
if command -v afplay &>/dev/null; then
    afplay -v "$VOLUME" "$SOUND_FILE" &
elif command -v aplay &>/dev/null; then
    aplay -q "$SOUND_FILE" &
elif command -v paplay &>/dev/null; then
    paplay "$SOUND_FILE" &
fi

exit 0
```

## settings.json 条目

```json
"Stop": [
  { "matcher": "", "hooks": [{ "type": "command", "command": "~/.claude/hooks/send-to-telegram.sh" }] },
  { "matcher": "", "hooks": [{ "type": "command", "command": "~/.claude/hooks/play-alarm.sh" }] }
],
"Notification": [
  { "matcher": "permission_prompt|elicitation_dialog", "hooks": [{ "type": "command", "command": "~/.claude/hooks/play-alarm.sh" }] }
]
```

## setup-hook 集成

两个入口都需要更新：`start.sh --setup-hook` 和 `install.sh setup_hooks()`

### start.sh setup_hook() 变更

```bash
# Copy alarm hook
if [ -f "hooks/play-alarm.sh" ]; then
    cp hooks/play-alarm.sh ~/.claude/hooks/
    chmod +x ~/.claude/hooks/play-alarm.sh
    print_status "Hook script (alarm) copied"
fi

# Copy sounds directory
if [ -d "sounds" ]; then
    mkdir -p ~/.claude/sounds
    cp -n sounds/* ~/.claude/sounds/ 2>/dev/null  # -n = no clobber
    print_status "Sound files copied"
fi
```

settings.json 检测逻辑：如果已存在但缺少 `play-alarm`，用 `jq` 追加到 Stop 数组并创建 Notification 数组。

### install.sh setup_hooks() 变更

```bash
# Copy alarm hook
if [ -f "$PROJECT_DIR/hooks/play-alarm.sh" ]; then
    cp "$PROJECT_DIR/hooks/play-alarm.sh" ~/.claude/hooks/
    chmod +x ~/.claude/hooks/play-alarm.sh
    print_success "Hook script (alarm) installed"
fi

# Copy sounds directory
if [ -d "$PROJECT_DIR/sounds" ]; then
    mkdir -p ~/.claude/sounds
    cp -n "$PROJECT_DIR/sounds/"* ~/.claude/sounds/ 2>/dev/null
    print_success "Sound files installed"
fi
```

### uninstall.sh 变更

- 清理列表追加: `~/.claude/hooks/play-alarm.sh`, `~/.claude/sounds/`, `~/.claude/alarm_disabled`
- settings.json 清理: 移除 `play-alarm.sh` 相关 hook entry（Stop 中的 alarm + 整个 Notification 数组）

## 幂等性保证

- `cp -n` 确保不覆盖用户自定义的声音文件
- settings.json: 检测 `play-alarm` 是否已存在，避免重复追加
- 无 `sounds/alarm.mp3` 时 hook 静默跳过，不报错

## 控制方式

- 禁用: `touch ~/.claude/alarm_disabled`
- 启用: `rm ~/.claude/alarm_disabled`
- 调音量: `export ALARM_VOLUME=0.3`

## 验证步骤

1. `pytest tests/ -v` — 全部测试通过
2. `./scripts/start.sh --setup-hook` — hook 被复制且 settings.json 更新
3. Claude 停止时播放提醒音
4. Claude 提问/请求权限时播放提醒音
5. `touch ~/.claude/alarm_disabled` 后不再响
