# Usage Guide

## Concepts

### Session
Each Claude conversation has a unique session ID (UUID), stored at `~/.claude/projects/<project>/<session-id>.jsonl`.

### Sync Direction
- **Desktop → Telegram**: Sent automatically via hook scripts (triggered on every Claude response and user input)
- **Telegram → Desktop**: Forwarded by bridge to the Claude process in tmux

### Shared Terminal
Desktop and Telegram share the same tmux terminal. Messages sent from Telegram are visible on desktop; Claude's desktop responses are also sent to Telegram.

### Auto-binding
The bridge auto-binds sessions:
- If the current session is not bound to any chat, the first Telegram message auto-binds it
- A background session poller detects new sessions every 5 seconds and auto-binds
- No need to manually run `/bind` (unless you need to force re-bind)

---

# Telegram Scenarios

## Scenario 1: First Telegram Connection

**Prerequisite**: Bridge is running on desktop (`./scripts/start.sh --new` or `./scripts/start.sh`)

1. Open the Telegram bot chat
2. Send any message

The bridge auto-detects the current session and binds it. If you see a prompt to bind, send `/bind`.

---

## Scenario 2: Continue Working from Telegram While Away

**Goal**: Send messages to desktop Claude from Telegram

**Prerequisite**: Bridge is running on desktop

1. Open the Telegram bot chat
2. Send your message

> Messages are injected into Claude in the desktop tmux session. Claude's responses sync back to Telegram.

If you see "Not bound":
- Send `/bind` to bind the current session
- Or send `/continue` to connect to the most recent session

---

## Scenario 3: Switch Sessions from Telegram

**Goal**: Switch Claude conversations (desktop follows automatically)

### Method A: Session Picker
```
/resume
```
Shows a list of recent sessions (full UUID + timestamp) for the current project. Tap to select.

### Method B: Quick Resume
```
/continue
```
Resumes the most recently modified session.

> **Note**: When switching sessions, desktop Claude briefly restarts (1-2 seconds). Cross-project switches auto-`cd` to the target project directory.

---

## Scenario 4: Switch Projects from Telegram

**Goal**: Browse different projects and select a session

```
/projects
```

1. Shows project list (full paths, sorted by recent activity)
2. Tap a project → shows its session list
3. Tap a session to resume, or tap "New session"

> Only shows sessions that are active within 30 days, non-empty, and properly formatted.

Cross-project operations automatically:
1. Exit current Claude
2. `cd` to the target project directory
3. Start Claude and resume/create session

---

## Scenario 5: Pause Sync from Telegram

**Goal**: Temporarily stop bidirectional sync (without disconnecting)

```
/stop
```

Effects:
- Telegram messages no longer forwarded to desktop
- Desktop Claude responses no longer sent to Telegram
- **Logs still recorded** (continue writing to `~/.claude/logs/`)
- Desktop Claude works normally, unaffected

To resume:
```
/start      ← start new conversation and resume
/resume     ← pick a session and resume
/continue   ← continue most recent session and resume
```

---

## Scenario 6: Interrupt Claude from Telegram

**Goal**: Claude is running a long task and you want to stop it

```
/escape
```

Equivalent to pressing `Escape` on desktop. Claude stops the current operation and waits for new input. **Sync state is unchanged**.

> `/escape` vs `/stop`: `/escape` only interrupts Claude's current operation, sync stays active; `/stop` pauses the entire sync channel.

---

## Scenario 7: Fully Disconnect from Telegram

**Goal**: Completely stop sync

```
/terminate
```

Effects:
- Sync fully stopped
- Need `/start` or `/resume` to reconnect
- Logs still recorded

---

## Scenario 8: Approve Permission Requests from Telegram

**Goal**: Claude needs tool permission (Bash, Write, etc.) and you're away from the desktop

**Prerequisite**: Claude started **without** `--dangerously-skip-permissions`, bridge running

When Claude requests permission, the raw CC JSON is forwarded to Telegram. The hook exits without making a decision, so CC falls back to its terminal dialog (y/n/a). You reply in Telegram and the bridge sends your response to tmux.

**Special case — AskUserQuestion**: When Claude asks a question with multiple choice options, Telegram shows formatted options with inline keyboard buttons:

```
❓ [Next step] How do you want to proceed?

1. Setup hook + restart bridge
   Run --setup-hook and restart bridge to apply changes now
2. Update docs + commit
   Update CLAUDE.md/README docs to reflect the new behavior, then commit

[1. Setup hook + restart bridge]   ← tap to select
[2. Update docs + commit]          ← tap to select
```

Tap a button to select — the bridge sends the corresponding keystrokes (Down arrow + Enter) to the CC terminal TUI via tmux.

For other permission requests (Bash, Write, Edit, etc.), the raw JSON is forwarded as-is:

```
🔐 Permission Request

{
  "tool_name": "Bash",
  "tool_input": {"command": "npm install"},
  ...
}
```

CC shows its terminal dialog — reply `y`/`n`/`a` in Telegram to respond.

> **Note**: Default `start.sh --new` uses `--dangerously-skip-permissions`, which skips all permission checks. To use remote permission, start Claude without that flag.

---

## Scenario 9: Reconnect from Telegram

### Start New Conversation
```
/start
```

### Resume Existing Session
```
/resume
```

### Quick Resume Most Recent Session
```
/continue
```

All commands above auto-clear paused/terminated state and restore sync.

---

## Scenario 10: Check Status

```
/status
```

Shows:
- tmux session state (running / not found)
- Sync state (active / paused / terminated)
- Current session ID
- Binding state (whether bound to current chat)

---

# Desktop Scenarios

## Scenario 11: First Launch

**Goal**: Create tmux session + start Claude + start bridge + connect Telegram

```bash
# 1. Make sure env var is set
echo $TELEGRAM_BOT_TOKEN

# 2. Install hooks (first time only)
./scripts/start.sh --setup-hook

# 3. Create new session and start all services
./scripts/start.sh --new

# Or specify a project directory
./scripts/start.sh --new ~/Projects/my-app
```

After launch, it auto-attaches to tmux. Send a Telegram message to test sync.

---

## Scenario 12: Daily Use (Desktop-first)

**Goal**: Use Claude Code on desktop, Telegram auto-receives notifications

```bash
# Start bridge (tmux session must already exist)
./scripts/start.sh
```

- Use Claude Code on desktop as normal
- Your inputs and Claude's responses auto-sync to Telegram
- No action needed on Telegram

---

## Scenario 13: Restart Bridge

**Goal**: Fix unstable connection or out-of-sync messages

```bash
./scripts/start.sh
```

Automatically:
1. Stops old bridge and tunnel processes
2. Starts new bridge
3. Creates new cloudflared tunnel
4. Sets Telegram webhook
5. Registers latest bot command list

---

## Scenario 14: View Claude Output

**Goal**: Quickly view recent Claude output without entering tmux

```bash
./scripts/start.sh --view
```

To enter interactive mode:

```bash
./scripts/start.sh --attach
```

To exit tmux (from another terminal):

```bash
./scripts/start.sh --detach
```

---

## Scenario 15: Create Session for a Different Project

**Goal**: Start a new Claude session in a specific project directory

```bash
./scripts/start.sh --new ~/Projects/another-project
```

The tmux session working directory is set to the specified path, and Claude starts in that directory.

---

## Scenario 16: Disconnect Sync from Desktop

**Goal**: Stop desktop → Telegram sync

```bash
./scripts/start.sh --terminate
```

Same effect as Telegram `/terminate`. Fully stops sync. Restart bridge to resume.

---

## Scenario 17: Update Hook Scripts

**Goal**: Reinstall hooks after a code update

```bash
# Update hook scripts
./scripts/start.sh --setup-hook

# Restart bridge (registers latest commands)
./scripts/start.sh
```

No need to reinstall the entire project.

---

## Scenario 18: Fully Stop All Services

**Goal**: Stop all related processes

```bash
# Method 1:
./scripts/start.sh --terminate

# Method 2: Press Ctrl+C in the bridge terminal
```

Or manually clean up:

```bash
./scripts/start.sh --detach     # detach from tmux first
./scripts/start.sh --terminate  # terminate all processes
```

---

## Quick Reference

Full command tables in [Startup Guide](start.md).

---

## FAQ

> For install issues see [Installation Guide](install.md#faq). For connection/log issues see [Startup Guide](start.md#troubleshooting).

### Q: Desktop Claude disconnected after switching session?
A: This is expected. When switching sessions from Telegram, Claude briefly exits and restarts (1-2 seconds). The bridge handles this automatically. Cross-project switches `cd` to the target project directory first.

### Q: "Not bound" when sending a message?
A: Send `/bind` to bind the current session, or just send another message (auto-binds).

### Q: What's the difference between `/stop` and `/escape`?
A: `/stop` **pauses the entire sync channel** — bidirectional messages stop, need `/start`, `/resume`, or `/continue` to resume. `/escape` **only interrupts Claude's current operation** (like pressing Escape) — sync stays active.

### Q: "Session not found" when switching to another project's session?
A: Use `/projects` to browse projects and select a session. The bridge auto-detects cross-project switches and handles `cd` + restart.

### Q: Telegram commands not updated (can't see new commands)?
A: Restart the bridge. It auto-registers the latest command list with the Telegram API on startup.

### Q: How to update bot commands without reinstalling?
A: Run `./scripts/start.sh --setup-hook` to update hook scripts, then `./scripts/start.sh` to restart bridge and register new commands.
