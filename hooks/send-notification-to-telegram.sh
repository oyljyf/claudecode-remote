#!/bin/bash
# Claude Code Notification hook - forwards AskUserQuestion options to Telegram as inline keyboard
# Triggers on: elicitation_dialog (AskUserQuestion, Plan Approval, etc.)
# Reads transcript JSONL to extract the last AskUserQuestion tool_use and its options
# Install: copy to ~/.claude/hooks/ and add to ~/.claude/settings.json

source "$(dirname "$0")/lib/common.sh"

INPUT=$(cat)

TRANSCRIPT_PATH=$(echo "$INPUT" | jq -r '.transcript_path // empty')

if [ -z "$TRANSCRIPT_PATH" ] || [ ! -f "$TRANSCRIPT_PATH" ]; then
    exit 0
fi

# Wait for transcript to be fully written
sleep 0.3

SESSION_ID=$(basename "$TRANSCRIPT_PATH" .jsonl)
CHAT_ID=$(get_chat_id "$SESSION_ID")

if [ -z "$CHAT_ID" ]; then
    exit 0
fi

if get_sync_disabled; then
    exit 0
fi

# Extract last AskUserQuestion from transcript and send to Telegram
python3 - "$TRANSCRIPT_PATH" "$CHAT_ID" "$TELEGRAM_BOT_TOKEN" << 'PYEOF'
import sys, json, urllib.request

transcript_path = sys.argv[1]
chat_id = sys.argv[2]
token = sys.argv[3]

def send_telegram(text, reply_markup=None):
    data = {"chat_id": chat_id, "text": text}
    if reply_markup:
        data["reply_markup"] = reply_markup
    try:
        req = urllib.request.Request(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json.dumps(data).encode(),
            {"Content-Type": "application/json"},
        )
        urllib.request.urlopen(req, timeout=10)
    except Exception:
        pass

# Read last 30 lines of transcript to find AskUserQuestion
try:
    with open(transcript_path) as f:
        lines = f.readlines()[-30:]
except Exception:
    sys.exit(0)

# Search backwards for the last AskUserQuestion tool_use
for line in reversed(lines):
    line = line.strip()
    if not line or '"AskUserQuestion"' not in line:
        continue
    try:
        entry = json.loads(line)
        if entry.get("type") != "assistant":
            continue
        for block in entry.get("message", {}).get("content", []):
            if block.get("type") != "tool_use" or block.get("name") != "AskUserQuestion":
                continue
            questions = block.get("input", {}).get("questions", [])
            if not questions:
                continue
            q = questions[0]
            question_text = q.get("question", "Question")
            options = q.get("options", [])
            header = q.get("header", "")

            if not options:
                continue

            # Format message
            if header:
                msg = f"❓ [{header}] {question_text}"
            else:
                msg = f"❓ {question_text}"

            msg += "\n"
            for i, opt in enumerate(options):
                label = opt.get("label", f"Option {i+1}")
                desc = opt.get("description", "")
                msg += f"\n{i+1}. {label}"
                if desc:
                    msg += f"\n   {desc}"

            # Build inline keyboard (askq: callback reuses bridge's Down+Enter navigation)
            kb = []
            for i, opt in enumerate(options):
                label = opt.get("label", f"Option {i+1}")
                btn_text = f"{i+1}. {label}"
                kb.append([{"text": btn_text, "callback_data": f"askq:{i}"}])

            send_telegram(msg, {"inline_keyboard": kb})
            sys.exit(0)
    except (json.JSONDecodeError, KeyError):
        continue
PYEOF
exit 0
