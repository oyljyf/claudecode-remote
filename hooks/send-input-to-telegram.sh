#!/bin/bash
# Claude Code UserPromptSubmit hook - sends user input to Telegram
# Always logs to file, only sends to Telegram if message is from desktop

TELEGRAM_BOT_TOKEN="${TELEGRAM_BOT_TOKEN:-YOUR_BOT_TOKEN_HERE}"
CHAT_ID_FILE=~/.claude/telegram_chat_id
PENDING_FILE=~/.claude/telegram_pending
LOG_DIR=~/.claude/logs
LOG_FILE="$LOG_DIR/cc_$(date +%d%m%y).log"

# Ensure log directory exists
mkdir -p "$LOG_DIR"

[ ! -f "$CHAT_ID_FILE" ] && exit 0

# Check if message came from Telegram
FROM_TELEGRAM=0
[ -f "$PENDING_FILE" ] && FROM_TELEGRAM=1

CHAT_ID=$(cat "$CHAT_ID_FILE")
INPUT=$(cat)
PROMPT=$(echo "$INPUT" | jq -r '.prompt // empty')

[ -z "$PROMPT" ] && exit 0

python3 - "$PROMPT" "$CHAT_ID" "$TELEGRAM_BOT_TOKEN" "$LOG_FILE" "$FROM_TELEGRAM" << 'PYEOF'
import sys, json, urllib.request
from datetime import datetime

prompt, chat_id, token, log_file, from_telegram = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4], sys.argv[5]

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
