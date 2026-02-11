#!/bin/bash
# Claude Code PermissionRequest hook
# All tools: formats tool info + 3-button inline keyboard (Yes/Yes to all/No)
# AskUserQuestion: formats options as Telegram inline keyboard (askq: callbacks)
# Install: copy to ~/.claude/hooks/ and add to ~/.claude/settings.json

source "$(dirname "$0")/lib/common.sh"

INPUT=$(cat)

# Extract tool info from stdin JSON (jq for reliable extraction)
TOOL_NAME=$(echo "$INPUT" | jq -r '.tool_name // empty')
TOOL_INPUT=$(echo "$INPUT" | jq -c '.tool_input // {}')

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

if [ "$TOOL_NAME" = "AskUserQuestion" ]; then
    # Format AskUserQuestion as Telegram inline keyboard
    python3 - "$TOOL_INPUT" "$CHAT_ID" "$TELEGRAM_BOT_TOKEN" << 'PYEOF'
import sys, json, urllib.request

tool_input_raw = sys.argv[1]
chat_id = sys.argv[2]
token = sys.argv[3]

try:
    tool_input = json.loads(tool_input_raw) if tool_input_raw else {}
except (json.JSONDecodeError, TypeError):
    tool_input = {}

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

questions = tool_input.get("questions", [])
option_index = 0
for q in questions:
    question_text = q.get("question", "")
    header = q.get("header", "")
    options = q.get("options", [])
    msg = f"❓ {header}\n\n{question_text}\n" if header else f"❓ {question_text}\n"
    for i, opt in enumerate(options):
        label = opt.get("label", f"Option {i+1}")
        desc = opt.get("description", "")
        msg += f"\n{i+1}. {label}"
        if desc:
            msg += f"\n   {desc}"
    buttons = []
    for i, opt in enumerate(options):
        label = opt.get("label", f"Option {i+1}")
        buttons.append([{"text": f"{i+1}. {label}", "callback_data": f"askq:{option_index + i}"}])
    option_index += len(options)
    kb = {"inline_keyboard": buttons} if buttons else None
    send_telegram(msg, reply_markup=kb)
PYEOF
else
    # Format non-AskUserQuestion tools as permission request with 3-button keyboard
    python3 - "$TOOL_NAME" "$TOOL_INPUT" "$CHAT_ID" "$TELEGRAM_BOT_TOKEN" << 'PYEOF'
import sys, json, urllib.request

tool_name = sys.argv[1]
tool_input_raw = sys.argv[2]
chat_id = sys.argv[3]
token = sys.argv[4]

try:
    tool_input = json.loads(tool_input_raw) if tool_input_raw else {}
except (json.JSONDecodeError, TypeError):
    tool_input = {}

# Format message based on tool type
if tool_name in ("Edit", "Write"):
    file_path = tool_input.get("file_path", "unknown")
    msg = f"\U0001f510 {tool_name}: {file_path}"
elif tool_name == "Bash":
    command = tool_input.get("command", "")
    if len(command) > 300:
        command = command[:300] + "..."
    msg = f"\U0001f510 Bash:\n{command}"
else:
    msg = f"\U0001f510 Permission: {tool_name}"

# 3-button inline keyboard: Yes / Yes to all / No
buttons = [
    [{"text": "Yes", "callback_data": "askq:0"}],
    [{"text": "Yes to all", "callback_data": "askq:1"}],
    [{"text": "No", "callback_data": "askq:2"}],
]
kb = {"inline_keyboard": buttons}

data = {"chat_id": chat_id, "text": msg, "reply_markup": kb}
try:
    req = urllib.request.Request(
        f"https://api.telegram.org/bot{token}/sendMessage",
        json.dumps(data).encode(),
        {"Content-Type": "application/json"},
    )
    urllib.request.urlopen(req, timeout=10)
except Exception:
    pass
PYEOF
fi
