# claudecode-telegram

> Forked from [hanxiao/claudecode-telegram](https://github.com/hanxiao/claudecode-telegram)

Telegram bot bridge for Claude Code. Send messages from Telegram, get responses back.

![demo](demo.gif)

## What's New in This Fork

### Simplified Setup Scripts

Added `install.sh` and `start.sh` scripts to automate the installation and startup process.

- [Installation Guide](docs/install.md) - One-command setup with automatic dependency installation
- [Startup Guide](docs/start.md) - Flexible startup options with tmux session management

### Bidirectional Sync

Full bidirectional sync between Desktop and Telegram:

- **Desktop → Telegram**: User input synced via UserPromptSubmit hook, responses synced via Stop hook
- **Telegram → Claude Code**: Messages injected into tmux session via bridge
- **Claude Code → Telegram**: Responses sent back via Stop hook

### Log Management

Conversation logs are saved daily for easy review:

- Daily logs: `~/.claude/logs/cc_DDMMYY.log`
- Debug logs: `~/.claude/logs/debug.log`
- Cleanup tool: `./scripts/clean-logs.sh [days]`

## Commands Reference

### Install Commands

| Command                      | Description                               |
| ---------------------------- | ----------------------------------------- |
| `./scripts/install.sh TOKEN` | Install with bot token                    |
| `--check`                    | Check installation status only            |
| `--force`                    | Force reinstall even if already installed |

### Start Commands

| Command        | Description                                          |
| -------------- | ---------------------------------------------------- |
| *(no args)*    | Start/restart bridge (fix unstable connection)       |
| `--new`        | Create new tmux session with Claude and start bridge |
| `--attach`     | Attach to Claude tmux session                        |
| `--detach`     | Detach from tmux (run from another terminal)         |
| `--view`       | View recent Claude output without attaching          |
| `--check`      | Check configuration status                           |
| `--setup-hook` | Setup Claude hooks for Telegram                      |
| `--sync`       | Show desktop/Telegram sync instructions              |

### Telegram Commands

| Command      | Description                    |
| ------------ | ------------------------------ |
| `/status`    | Check tmux status              |
| `/stop`      | Interrupt Claude (Escape)      |
| `/clear`     | Clear conversation             |
| `/resume`    | Resume session (shows picker)  |
| `/continue_` | Continue most recent session   |
| `/loop`      | Ralph Loop: `/loop <prompt>`   |

## Quick Start

```bash
# 1. Get bot token from @BotFather on Telegram

# 2. Clone and install
git clone https://github.com/oyljyf/claudecode-remote
cd claudecode-remote
./scripts/install.sh YOUR_TELEGRAM_BOT_TOKEN

# 3. Start
source ~/.zshrc
./scripts/start.sh --new
```

## Hotfix Connection Issue

If connection is unstable or messages are not delivered, restart the bridge:

```bash
./scripts/start.sh
```

## License

Same as upstream. See [original repository](https://github.com/hanxiao/claudecode-telegram) for details.
