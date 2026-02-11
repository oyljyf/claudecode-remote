# claudecode-remote

English | [中文文档](docs/README_CN.md)

> Forked from [hanxiao/claudecode-telegram](https://github.com/hanxiao/claudecode-telegram)

Telegram bot bridge for Claude Code. Full bidirectional sync between desktop and mobile.

![demo](demo.gif)

## Features

- **Bidirectional sync** — Desktop Claude responses + user input synced to Telegram via hooks; Telegram messages injected into desktop Claude via bridge
- **Auto-binding** — First Telegram message auto-binds the session, no manual `/bind` needed
- **Cross-project switching** — Browse projects from Telegram, bridge handles `cd` + Claude restart automatically
- **Three-state sync** — Active / Paused / Terminated, with local logs always recording regardless of sync state
- **tmux integration** — Mouse scrollback, 10000-line history, reliable session tracking
- **Remote permission** — When Claude requests tool permission, formatted info is forwarded to Telegram; CC dialog options (plan approval, questions) auto-forwarded as clickable buttons
- **Local alarm** — Plays different sounds for task completion (`done.mp3`) and user action needed (`alert.mp3`), so you never miss it while in another window

## Requirements

- **macOS**, **Linux**, or **Windows (WSL)**
- [Claude Code CLI](https://docs.anthropic.com/en/docs/claude-code)
- Python 3.10+

## Install

### 1. Get a Telegram Bot Token

1. Open Telegram, find [@BotFather](https://t.me/BotFather)
2. Send `/newbot`, follow the prompts
3. Copy the token (format: `123456789:ABC-DEF...`)
4. Click your bot's @username to open the chat, press **Start**

### 2. Clone and install

```bash
git clone https://github.com/oyljyf/claudecode-remote
cd claudecode-remote
./scripts/install.sh YOUR_TELEGRAM_BOT_TOKEN
```

This auto-installs dependencies (`tmux`, `cloudflared`, `jq`, `uv`), creates a Python venv, configures hooks, and saves the token.

### 3. Load env and start

```bash
source ~/.zshrc   # or restart terminal
./scripts/start.sh --new
```

This creates a tmux session, starts Claude, launches the bridge + cloudflare tunnel, sets the Telegram webhook, and attaches you to the Claude terminal.

### Verify installation

```bash
./scripts/install.sh --check
```

### Reinstall

```bash
./scripts/install.sh --force YOUR_TELEGRAM_BOT_TOKEN
```

### Manual hook setup

If you only need to install/update hooks (e.g. after a code update):

```bash
./scripts/start.sh --setup-hook
./scripts/start.sh   # restart bridge to register new commands
```

## Usage

### Concepts

- **Session** — Each Claude conversation has a unique ID, stored in `~/.claude/projects/<project>/<id>.jsonl`
- **Shared terminal** — Desktop and Telegram share the same tmux terminal. Messages from either side are visible to both.
- **Sync direction** — Desktop-to-Telegram via hooks (automatic); Telegram-to-desktop via bridge

### Use from Telegram

1. Make sure the bridge is running on desktop (`./scripts/start.sh` or `--new`)
2. Open the Telegram bot chat, send any message
3. Bridge auto-detects and binds the current session

### Switch sessions

```
/resume      Show recent sessions, pick one
/continue    Resume the most recent session
```

### Switch projects

```
/projects    Browse projects → pick session or create new
```

Cross-project switches auto-handle `cd` + Claude restart (1-2 second delay).

### Pause / Resume / Terminate

```
/stop        Pause sync (logs still recorded, desktop Claude unaffected)
/escape      Interrupt Claude (like pressing Escape), sync stays active
/terminate   Fully disconnect, need /start to reconnect
```

Resume with `/start`, `/resume`, or `/continue` — all clear the paused/terminated state.

### Use from desktop

```bash
./scripts/start.sh              # start bridge (tmux must exist)
./scripts/start.sh --new        # create tmux + Claude + bridge
./scripts/start.sh --new <path> # start in a specific project directory
./scripts/start.sh --attach     # attach to tmux (with session picker)
./scripts/start.sh --detach     # detach from tmux (run from another terminal)
./scripts/start.sh --view       # view recent Claude output without attaching
./scripts/start.sh --terminate  # stop all processes and disable sync
./scripts/start.sh --stop-sync  # pause sync locally (no bridge needed)
./scripts/start.sh --resume-sync # resume sync locally
```

> Since Claude Code captures most keybindings, use `--detach` from another terminal instead of the tmux prefix key.

## Three-State Sync Control

| State                     | Hook Behavior          | Bridge Behavior               |
| ------------------------- | ---------------------- | ----------------------------- |
| Active                    | Send to Telegram + log | Forward messages              |
| Paused (`/stop`)          | Log only               | Reject with "paused" hint     |
| Terminated (`/terminate`) | Log only               | Reject with "terminated" hint |

Logs **always** record to `~/.claude/logs/` regardless of sync state.

## Telegram Commands

| Command          | Description                                          |
| ---------------- | ---------------------------------------------------- |
| `/start`         | Start new Claude session                             |
| `/stop`          | Pause sync (recover with /start, /resume, /continue) |
| `/escape`        | Interrupt Claude (send Escape key)                   |
| `/terminate`     | Disconnect completely (need /start to reconnect)     |
| `/resume`        | Resume session (shows picker)                        |
| `/continue`      | Continue most recent session                         |
| `/projects`      | Browse projects and sessions                         |
| `/bind`          | Bind current session to this chat                    |
| `/clear`         | Clear conversation                                   |
| `/status`        | Check tmux, sync, and binding status                 |
| `/loop <prompt>` | Ralph Loop: auto-iteration mode                      |
| `/report`        | Token usage report with cost estimation, bars, trend |

## Remote Permission Control

When Claude requests tool permission, the PermissionRequest hook formats the request by tool type and sends it to Telegram with an inline keyboard:

- **Edit / Write**: shows file path + Yes / Yes to all / No buttons
- **Bash**: shows command (truncated) + Yes / Yes to all / No buttons
- **AskUserQuestion**: shows question + option buttons
- **Other tools**: shows tool name + Yes / Yes to all / No buttons

Tap a button to select — the bridge navigates the CC terminal dialog via Down+Enter keystrokes.

> **Note**: This only works when Claude is started **without** `--dangerously-skip-permissions`. The default `start.sh --new` uses skip-permissions, so permission hooks won't trigger in that mode.

How it works:

```
Claude needs permission → PermissionRequest hook → formats tool info + buttons to Telegram
  → User taps button → bridge sends Down+Enter to tmux → CC selects option
```

Setup: `./scripts/start.sh --setup-hook` (included automatically with other hooks).

## Logs
Keep logging even stop or terminate telegram sync.

| Log Type  | Path                             | Description         |
| --------- | -------------------------------- | ------------------- |
| Chat logs | `~/.claude/logs/cc_MMDDYYYY.log` | Daily conversations |
| Debug log | `~/.claude/logs/debug.log`       | Hook debug info     |

```bash
cat ~/.claude/logs/cc_$(date +%m%d%Y).log   # today's chat log
tail -f ~/.claude/logs/debug.log              # live debug log
bash ./scripts/clean-logs.sh                  # clean logs older than 30 days
bash ./scripts/clean-logs.sh 7                # clean logs older than 7 days
```

## Local Alarm

Different sounds play depending on the event, so you can tell what happened without switching windows.

| Hook Event     | Sound File  | When it fires                                         |
| -------------- | ----------- | ----------------------------------------------------- |
| `Stop`         | `done.mp3`  | Claude finishes a response (task done or needs input) |
| `Notification` | `alert.mp3` | Claude asks a question or requests tool permission    |

Place your sound files in the project's `sounds/` directory (`done.mp3` and `alert.mp3`), then run `./scripts/start.sh --setup-hook` to install them to `~/.claude/sounds/`.

```bash
touch ~/.claude/alarm_disabled     # disable alarm
rm ~/.claude/alarm_disabled        # enable alarm
export ALARM_VOLUME=0.3            # adjust volume (0.0-1.0, default 0.5)
```

Sound configuration in `config.env`:

```env
DEFAULT_SOUND_DIR=~/.claude/sounds
DEFAULT_SOUND_DONE=done.mp3
DEFAULT_SOUND_ALERT=alert.mp3
DEFAULT_ALARM_VOLUME=0.5
```

Override at runtime via environment variables: `SOUND_DIR`, `SOUND_DONE`, `SOUND_ALERT`, `ALARM_VOLUME`.

## Uninstall

```bash
./scripts/uninstall.sh              # interactive uninstall (choose components)
./scripts/uninstall.sh --telegram   # remove only Telegram hooks and bridge
./scripts/uninstall.sh --alarm      # remove only alarm hook and sounds
./scripts/uninstall.sh --all        # remove everything including logs
./scripts/uninstall.sh --keep-deps  # keep system dependencies (tmux, cloudflared, jq)
./scripts/uninstall.sh --force      # skip confirmation prompts
```

**What gets removed:**

| Component | Files removed                                                                                                   |
| --------- | --------------------------------------------------------------------------------------------------------------- |
| Telegram  | hooks (`send-*-telegram.sh`, `handle-permission.sh`), bridge state files, env vars, webhook, processes, `.venv` |
| Alarm     | hook (`play-alarm.sh`), `~/.claude/sounds/` (`done.mp3`, `alert.mp3`), `alarm_disabled`                         |
| Shared    | `hooks/lib/` (when both removed), `settings.json` hook config                                                   |

**What stays:** Claude Code sessions (`~/.claude/projects/`), Claude Code itself, system deps (unless confirmed).

## Environment Variables

| Variable             | Description          | Default  |
| -------------------- | -------------------- | -------- |
| `TELEGRAM_BOT_TOKEN` | Bot token (required) | -        |
| `TMUX_SESSION`       | tmux session name    | `claude` |
| `PORT`               | Bridge port          | `8080`   |
| `ALARM_VOLUME`       | Alarm sound volume   | `0.5`    |
| `ALARM_ENABLED`      | Enable/disable alarm | `true`   |

Custom port:

```bash
export PORT=9090
./scripts/start.sh
```

After restart, bridge, cloudflared tunnel, and Telegram webhook will automatically use the new port.

## Troubleshooting

**Telegram messages not reaching desktop:**
1. Check bridge is running: `./scripts/start.sh`
2. Check tmux session exists: `./scripts/start.sh --new`
3. Send `/status` to check state

**Desktop responses not reaching Telegram:**
1. Check hooks: `./scripts/start.sh --setup-hook`
2. Check token: `grep TELEGRAM_BOT_TOKEN ~/.claude/hooks/lib/common.sh`
3. Check debug log: `tail -20 ~/.claude/logs/debug.log`

**Connection unstable:** Restart bridge: `./scripts/start.sh`

**tmux can't scroll:** Old session — recreate with `./scripts/start.sh --new`

## Tech Stack

| Component          | Technology                                                    |
| ------------------ | ------------------------------------------------------------- |
| Bridge Server      | Python (stdlib only)                                          |
| Tunnel             | Cloudflare Quick Tunnels                                      |
| Session Management | tmux                                                          |
| Hooks              | Claude Code Stop / UserPromptSubmit / Notification / PermissionRequest hooks |
| Bot API            | Telegram Bot API                                              |

## Documentation

- [Installation Guide](docs/install.md) — Install, hooks, and manual setup (Chinese)
- [Startup Guide](docs/start.md) — Startup options, tmux control, and troubleshooting (Chinese)
- [Usage Guide](docs/usage.md) — Scenario-based usage for Telegram and desktop (English)


## License

Same as upstream. See [original repository](https://github.com/hanxiao/claudecode-telegram) for details.
