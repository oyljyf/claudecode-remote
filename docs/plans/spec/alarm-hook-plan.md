# Alarm Hook 实现计划

- Version: 1.0.1
- Updated at: 2026-02-10 14:51:01
- Status: ✅ Implemented

---

## Context

当 Claude 完成任务或需要用户输入时，用户可能不在当前窗口（切到其他 app 或其他 tmux session）。本功能通过 Claude Code hooks 播放本地声音提醒用户。

**参考**: [RedAlert2-Claude](https://github.com/op7418/RedAlert2-Claude) — 使用 Claude Code hooks + `afplay` 播放声音

## 双声音设计（v1.0.1）

两种场景需要不同的声音提示：

| 场景 | 声音文件 | 传参 | 含义 |
|------|---------|------|------|
| 任务完成 | `done.mp3` | `play-alarm.sh done` | Claude 完成回复，可查看结果 |
| 需要操作 | `alert.mp3` | `play-alarm.sh alert` | 权限请求、输入提问等，需用户介入 |

声音文件路径和名称集中配置在 `config.env`：

```bash
DEFAULT_SOUND_DIR=~/.claude/sounds
DEFAULT_SOUND_DONE=done.mp3
DEFAULT_SOUND_ALERT=alert.mp3
DEFAULT_ALARM_VOLUME=0.5
```

`hooks/lib/common.sh` 提供运行时变量（支持环境变量覆盖）：

```bash
SOUND_DIR="${SOUND_DIR:-$HOME/.claude/sounds}"
SOUND_DONE="${SOUND_DONE:-done.mp3}"
SOUND_ALERT="${SOUND_ALERT:-alert.mp3}"
ALARM_VOLUME="${ALARM_VOLUME:-0.5}"
```

## 触发事件

| Hook 事件      | Matcher                                  | 触发时机                         | 声音 |
| -------------- | ---------------------------------------- | -------------------------------- | ---- |
| `Stop`         | （空，匹配所有）                          | Claude 完成回复（任务完成或等待输入） | `done` |
| `Notification` | `permission_prompt\|elicitation_dialog`  | Claude 提问或请求权限            | `alert` |

**排除**: `idle_prompt`（会频繁打扰）、`auth_success`（无需提醒）

## 修改文件

| 文件                   | 操作                                  |
| ---------------------- | ------------------------------------- |
| `config.env`           | 更新 — 添加 4 个 DEFAULT_SOUND_* 变量 |
| `hooks/play-alarm.sh`  | 更新 — 支持 $1 参数选择声音文件       |
| `hooks/lib/common.sh`  | 更新 — 添加 SOUND_DIR/DONE/ALERT/VOLUME |
| `sounds/done.mp3`      | 任务完成提示音                        |
| `sounds/alert.mp3`     | 需要操作提示音                        |
| `scripts/install.sh`   | 更新 — settings.json 中加参数         |
| `scripts/start.sh`     | 更新 — settings.json 中加参数         |
| `scripts/uninstall.sh` | 无需改动 — 已有逻辑兼容              |

## Hook 逻辑（play-alarm.sh）

```bash
#!/bin/bash
# Usage: play-alarm.sh [done|alert]
source "$(dirname "$0")/lib/common.sh"

# Check if alarm is enabled
[ -f ~/.claude/alarm_disabled ] && exit 0
[ "${ALARM_ENABLED:-true}" = "false" ] && exit 0

# Determine sound type from argument (default: done)
SOUND_TYPE="${1:-done}"

case "$SOUND_TYPE" in
    alert)  SOUND_FILE="$SOUND_DIR/$SOUND_ALERT" ;;
    *)      SOUND_FILE="$SOUND_DIR/$SOUND_DONE" ;;
esac

if [ ! -f "$SOUND_FILE" ]; then
    exit 0  # No sound file, silently skip
fi

VOLUME="$ALARM_VOLUME"

# Play in background (non-blocking, hook must return quickly)
if command -v afplay &>/dev/null; then
    afplay -v "$VOLUME" "$SOUND_FILE" &
elif command -v paplay &>/dev/null; then
    paplay "$SOUND_FILE" &
elif command -v aplay &>/dev/null; then
    aplay -q "$SOUND_FILE" &
fi

exit 0
```

## settings.json 条目

```json
"Stop": [
  { "matcher": "", "hooks": [{ "type": "command", "command": "~/.claude/hooks/send-to-telegram.sh" }] },
  { "matcher": "", "hooks": [{ "type": "command", "command": "~/.claude/hooks/play-alarm.sh done" }] }
],
"Notification": [
  { "matcher": "permission_prompt|elicitation_dialog", "hooks": [{ "type": "command", "command": "~/.claude/hooks/play-alarm.sh alert" }] }
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
    cp -n sounds/*.mp3 ~/.claude/sounds/ 2>/dev/null || true
    print_status "Sound files copied"
fi
```

settings.json 中 `play-alarm.sh` 引用需带参数：
- Stop hook: `play-alarm.sh done`
- Notification hook: `play-alarm.sh alert`

### install.sh setup_hooks() 变更

同 start.sh 逻辑。settings.json 配置中所有 `play-alarm.sh` 引用加参数。

### uninstall.sh

无需改动。已有逻辑兼容：
- `rm -rf ~/.claude/sounds` 删除整个目录
- jq filter 用 `contains("play-alarm")` 匹配，不受参数影响

## 幂等性保证

- `cp -n` 确保不覆盖用户自定义的声音文件
- settings.json: 检测 `play-alarm` 是否已存在，避免重复追加
- 无声音文件时 hook 静默跳过，不报错

## 控制方式

- 禁用: `touch ~/.claude/alarm_disabled`
- 启用: `rm ~/.claude/alarm_disabled`
- 调音量: `export ALARM_VOLUME=0.3`
- 自定义声音: `export SOUND_DONE=my-done.mp3` 或 `export SOUND_ALERT=my-alert.mp3`
- 自定义目录: `export SOUND_DIR=/path/to/sounds`

## 验证步骤

1. `pytest tests/ -v -k alarm` — 全部测试通过
2. `./scripts/start.sh --setup-hook` — hook 被复制且 settings.json 更新
3. Claude 停止时播放 `done.mp3`
4. Claude 提问/请求权限时播放 `alert.mp3`
5. `touch ~/.claude/alarm_disabled` 后不再响
6. `bash hooks/play-alarm.sh` (无参数) → 默认播放 done.mp3
7. `bash hooks/play-alarm.sh alert` → 播放 alert.mp3
