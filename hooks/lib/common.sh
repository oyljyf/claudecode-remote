#!/bin/bash
# Common utilities for claudecode-remote hooks
# Source this file: source "$(dirname "$0")/lib/common.sh"

TELEGRAM_BOT_TOKEN="${TELEGRAM_BOT_TOKEN:-YOUR_BOT_TOKEN_HERE}"
CHAT_ID_FILE=~/.claude/telegram_chat_id
PENDING_FILE=~/.claude/telegram_pending
SESSION_CHAT_MAP_FILE=~/.claude/session_chat_map.json
CURRENT_SESSION_FILE=~/.claude/current_session_id
SYNC_DISABLED_FILE=~/.claude/telegram_sync_disabled
SYNC_PAUSED_FILE=~/.claude/telegram_sync_paused
LOG_DIR=~/.claude/logs
LOG_FILE="$LOG_DIR/cc_$(date +%m%d%Y).log"

# Ensure log directory exists
mkdir -p "$LOG_DIR"

get_chat_id() {
    # Try session-chat mapping first, then fall back to global file
    # Args: $1 = session_id (optional)
    local chat_id=""
    local session_id="$1"

    if [ -n "$session_id" ] && [ -f "$SESSION_CHAT_MAP_FILE" ]; then
        chat_id=$(jq -r --arg sid "$session_id" '.[$sid] // empty' "$SESSION_CHAT_MAP_FILE" 2>/dev/null)
    fi

    if [ -z "$chat_id" ] && [ -f "$CHAT_ID_FILE" ]; then
        chat_id=$(cat "$CHAT_ID_FILE")
    fi

    echo "$chat_id"
}

get_sync_disabled() {
    # Returns 0 (true) if sync is disabled/paused, 1 (false) otherwise
    [ -f "$SYNC_DISABLED_FILE" ] && return 0
    [ -f "$SYNC_PAUSED_FILE" ] && return 0
    return 1
}
