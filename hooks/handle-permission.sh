#!/bin/bash
# Claude Code PermissionRequest hook - forwards raw CC permission request to Telegram
# Does NOT make decisions - just notifies, then exits so CC falls back to terminal dialog
# User replies y/n/a in Telegram → bridge sends to tmux → CC reads it
# Install: copy to ~/.claude/hooks/ and add to ~/.claude/settings.json

source "$(dirname "$0")/lib/common.sh"

INPUT=$(cat)

# Extract tool_name for guard check only
TOOL_NAME=$(echo "$INPUT" | jq -r '.tool_name // empty')

if [ -z "$TOOL_NAME" ]; then
    exit 0
fi

# Extract session ID from current_session_id file
SESSION_ID=""
if [ -f "$CURRENT_SESSION_FILE" ]; then
    SESSION_ID=$(cat "$CURRENT_SESSION_FILE")
fi

CHAT_ID=$(get_chat_id "$SESSION_ID")

# If no chat_id or sync disabled, fall back silently
if [ -z "$CHAT_ID" ]; then
    exit 0
fi

if get_sync_disabled; then
    exit 0
fi

# Forward CC permission request to Telegram, then exit (no decision output)
# AskUserQuestion: formatted options + inline keyboard buttons
# Other tools: raw JSON dump
python3 - "$CHAT_ID" "$TELEGRAM_BOT_TOKEN" "$INPUT" << 'PYEOF'
import sys, json, urllib.request

chat_id = sys.argv[1]
token = sys.argv[2]
raw_input = sys.argv[3]

try:
    cc_data = json.loads(raw_input)
except (json.JSONDecodeError, TypeError):
    cc_data = {}

tool_name = cc_data.get("tool_name", "")
tool_input = cc_data.get("tool_input", {})

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

if tool_name == "AskUserQuestion":
    questions = tool_input.get("questions", [])
    if questions:
        q = questions[0]
        question_text = q.get("question", "Question")
        options = q.get("options", [])
        header = q.get("header", "")

        # Format message header
        if header:
            msg = f"❓ [{header}] {question_text}"
        else:
            msg = f"❓ {question_text}"

        # Format options with descriptions
        msg += "\n"
        for i, opt in enumerate(options):
            label = opt.get("label", f"Option {i+1}")
            desc = opt.get("description", "")
            msg += f"\n{i+1}. {label}"
            if desc:
                msg += f"\n   {desc}"

        # Build inline keyboard buttons
        kb = []
        for i, opt in enumerate(options):
            label = opt.get("label", f"Option {i+1}")
            btn_text = f"{i+1}. {label}"
            kb.append([{"text": btn_text, "callback_data": f"askq:{i}"}])

        send_telegram(msg, {"inline_keyboard": kb})
    else:
        raw_text = json.dumps(cc_data, indent=2, ensure_ascii=False)
        if len(raw_text) > 3000:
            raw_text = raw_text[:3000] + "\n..."
        send_telegram(f"🔐 Permission Request\n\n{raw_text}")
else:
    # Non-AskUserQuestion: send raw JSON
    raw_text = json.dumps(cc_data, indent=2, ensure_ascii=False)
    if len(raw_text) > 3000:
        raw_text = raw_text[:3000] + "\n..."
    send_telegram(f"🔐 Permission Request\n\n{raw_text}")

# Exit without output → CC falls back to terminal dialog
# User clicks button in Telegram → bridge sends keystrokes to tmux
PYEOF
