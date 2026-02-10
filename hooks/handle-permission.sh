#!/bin/bash
# Claude Code PermissionRequest hook - forwards permission requests to Telegram
# User can Allow/Deny via inline keyboard buttons in Telegram
# Uses file IPC to communicate with bridge.py
# Install: copy to ~/.claude/hooks/ and add to ~/.claude/settings.json

source "$(dirname "$0")/lib/common.sh"

INPUT=$(cat)

# Extract tool info from stdin JSON
TOOL_NAME=$(echo "$INPUT" | jq -r '.tool_name // empty')
TOOL_INPUT=$(echo "$INPUT" | jq -r '.tool_input // empty')

if [ -z "$TOOL_NAME" ]; then
    exit 0  # No tool name, fall back to normal dialog
fi

# Extract session ID from current_session_id file
SESSION_ID=""
if [ -f "$CURRENT_SESSION_FILE" ]; then
    SESSION_ID=$(cat "$CURRENT_SESSION_FILE")
fi

CHAT_ID=$(get_chat_id "$SESSION_ID")

# If no chat_id or sync disabled, fall back to normal dialog
if [ -z "$CHAT_ID" ]; then
    exit 0
fi

if get_sync_disabled; then
    exit 0
fi

python3 - "$TOOL_NAME" "$TOOL_INPUT" "$CHAT_ID" "$TELEGRAM_BOT_TOKEN" "$PERM_PENDING_FILE" "$PERM_RESPONSE_FILE" << 'PYEOF'
import sys, json, time, hashlib, urllib.request, os

tool_name = sys.argv[1]
tool_input_raw = sys.argv[2]
chat_id = sys.argv[3]
token = sys.argv[4]
pending_file = sys.argv[5]
response_file = sys.argv[6]

POLL_INTERVAL = 1
POLL_TIMEOUT = 120

# Generate short permission ID
perm_id = hashlib.md5(f"{tool_name}{time.time()}".encode()).hexdigest()[:8]

# Format message based on tool type
try:
    tool_input = json.loads(tool_input_raw) if tool_input_raw else {}
except (json.JSONDecodeError, TypeError):
    tool_input = {}

if tool_name == "Bash":
    cmd = tool_input.get("command", str(tool_input))
    if len(cmd) > 300:
        cmd = cmd[:300] + "..."
    detail = f"$ {cmd}"
elif tool_name in ("Write", "Edit"):
    fp = tool_input.get("file_path", str(tool_input))
    detail = fp
elif tool_name == "NotebookEdit":
    fp = tool_input.get("notebook_path", str(tool_input))
    detail = fp
else:
    detail = json.dumps(tool_input, ensure_ascii=False)
    if len(detail) > 300:
        detail = detail[:300] + "..."

msg = f"🔐 Permission Request\n\nTool: {tool_name}\n{detail}"

# Send to Telegram with inline keyboard
kb = {
    "inline_keyboard": [
        [
            {"text": "✅ Allow", "callback_data": f"perm_allow:{perm_id}"},
            {"text": "❌ Deny", "callback_data": f"perm_deny:{perm_id}"},
        ]
    ]
}

data = {
    "chat_id": chat_id,
    "text": msg,
    "reply_markup": kb,
}

try:
    req = urllib.request.Request(
        f"https://api.telegram.org/bot{token}/sendMessage",
        json.dumps(data).encode(),
        {"Content-Type": "application/json"},
    )
    urllib.request.urlopen(req, timeout=10)
except Exception:
    sys.exit(0)  # Failed to send, fall back to normal dialog

# Write pending permission file
try:
    with open(pending_file, "w") as f:
        json.dump({"id": perm_id, "tool_name": tool_name, "timestamp": time.time()}, f)
except OSError:
    sys.exit(0)

# Poll for response
start = time.time()
while time.time() - start < POLL_TIMEOUT:
    time.sleep(POLL_INTERVAL)
    if os.path.exists(response_file):
        try:
            with open(response_file) as f:
                resp = json.load(f)
            if resp.get("id") == perm_id:
                # Clean up files
                try:
                    os.remove(response_file)
                except OSError:
                    pass
                try:
                    os.remove(pending_file)
                except OSError:
                    pass
                behavior = resp.get("behavior", "deny")
                if behavior == "allow":
                    output = {
                        "hookSpecificOutput": {
                            "hookEventName": "PermissionRequest",
                            "decision": {"behavior": "allow"},
                        }
                    }
                else:
                    output = {
                        "hookSpecificOutput": {
                            "hookEventName": "PermissionRequest",
                            "decision": {
                                "behavior": "deny",
                                "message": "Denied via Telegram",
                            },
                        }
                    }
                print(json.dumps(output))
                sys.exit(0)
        except (json.JSONDecodeError, OSError):
            pass

# Timeout: clean up and fall back to normal dialog
try:
    os.remove(pending_file)
except OSError:
    pass

# Notify timeout
try:
    timeout_data = {"chat_id": chat_id, "text": "⏰ Permission request timed out (120s). Falling back to terminal."}
    req = urllib.request.Request(
        f"https://api.telegram.org/bot{token}/sendMessage",
        json.dumps(timeout_data).encode(),
        {"Content-Type": "application/json"},
    )
    urllib.request.urlopen(req, timeout=10)
except Exception:
    pass

sys.exit(0)
PYEOF
