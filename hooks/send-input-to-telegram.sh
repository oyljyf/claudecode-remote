#!/bin/bash
# Claude Code UserPromptSubmit hook - sends user input to Telegram
# Always logs to file, only sends to Telegram if message is from desktop

source "$(dirname "$0")/lib/common.sh"

# Check if sync is disabled (terminated) or paused - still log to file but skip Telegram
SYNC_DISABLED=0
if get_sync_disabled; then
    SYNC_DISABLED=1
fi

# Check if message came from Telegram
FROM_TELEGRAM=0
[ -f "$PENDING_FILE" ] && FROM_TELEGRAM=1

# Try to get chat ID from session-chat mapping first
CHAT_ID=""
if [ -f "$CURRENT_SESSION_FILE" ]; then
    SESSION_ID=$(cat "$CURRENT_SESSION_FILE")
    CHAT_ID=$(get_chat_id "$SESSION_ID")
else
    CHAT_ID=$(get_chat_id)
fi

[ -z "$CHAT_ID" ] && exit 0
INPUT=$(cat)
PROMPT=$(echo "$INPUT" | jq -r '.prompt // empty')

[ -z "$PROMPT" ] && exit 0

python3 - "$PROMPT" "$CHAT_ID" "$TELEGRAM_BOT_TOKEN" "$LOG_FILE" "$FROM_TELEGRAM" "$SYNC_DISABLED" << 'PYEOF'
import sys, json, urllib.request
from datetime import datetime

prompt, chat_id, token, log_file, from_telegram, sync_disabled = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4], sys.argv[5], sys.argv[6]

if not prompt:
    sys.exit(0)

if len(prompt) > 4000:
    prompt = prompt[:4000] + "..."

def log_message(text, role="You"):
    try:
        time_str = datetime.now().strftime("%H:%M")
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(f"\n[{time_str}] {role}:\n{text}\n")
            f.write("-" * 40 + "\n")
    except:
        pass

# Always log to file
log_message(prompt)

# Skip Telegram if sync is disabled
if sync_disabled == "1":
    sys.exit(0)

# Send to Telegram if from desktop, show notification if from Telegram
if from_telegram == "0":
    # From desktop: send to Telegram
    text = f"📝 You:\n{prompt}"
    data = {"chat_id": chat_id, "text": text}
    try:
        req = urllib.request.Request(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json.dumps(data).encode(),
            {"Content-Type": "application/json"}
        )
        urllib.request.urlopen(req, timeout=10)
    except:
        pass
PYEOF

exit 0
