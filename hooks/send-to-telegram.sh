#!/bin/bash
# Claude Code Stop hook - sends response back to Telegram
# Install: copy to ~/.claude/hooks/ and add to ~/.claude/settings.json

TELEGRAM_BOT_TOKEN="${TELEGRAM_BOT_TOKEN:-YOUR_BOT_TOKEN_HERE}"
INPUT=$(cat)
TRANSCRIPT_PATH=$(echo "$INPUT" | jq -r '.transcript_path')
CHAT_ID_FILE=~/.claude/telegram_chat_id
PENDING_FILE=~/.claude/telegram_pending
LOG_DIR=~/.claude/logs
LOG_FILE="$LOG_DIR/cc_$(date +%d%m%y).log"

# Ensure log directory exists
mkdir -p "$LOG_DIR"
DEBUG_LOG="$LOG_DIR/debug.log"

log_debug() {
    echo "[$(date '+%H:%M:%S')] $1" >> "$DEBUG_LOG"
}

log_debug "=== Hook triggered ==="
log_debug "TRANSCRIPT_PATH: $TRANSCRIPT_PATH"

# Wait for transcript to be fully written
sleep 0.3

# Check required files
if [ ! -f "$CHAT_ID_FILE" ]; then
    log_debug "EXIT: CHAT_ID_FILE not found"
    exit 0
fi
if [ ! -f "$TRANSCRIPT_PATH" ]; then
    log_debug "EXIT: TRANSCRIPT_PATH not found"
    exit 0
fi

CHAT_ID=$(cat "$CHAT_ID_FILE")
log_debug "CHAT_ID: $CHAT_ID"

LAST_USER_LINE=$(grep -n '"type":"user"' "$TRANSCRIPT_PATH" | tail -1 | cut -d: -f1)
if [ -z "$LAST_USER_LINE" ]; then
    log_debug "EXIT: No user message found"
    rm -f "$PENDING_FILE"
    exit 0
fi
log_debug "LAST_USER_LINE: $LAST_USER_LINE"

TMPFILE=$(mktemp)
tail -n "+$LAST_USER_LINE" "$TRANSCRIPT_PATH" | \
  grep '"type":"assistant"' | \
  jq -rs '[.[].message.content[] | select(.type == "text") | .text] | join("\n\n")' > "$TMPFILE" 2>/dev/null

if [ ! -s "$TMPFILE" ]; then
    log_debug "EXIT: No text content extracted"
    rm -f "$TMPFILE" "$PENDING_FILE"
    exit 0
fi
log_debug "Text extracted, size: $(wc -c < "$TMPFILE") bytes"

python3 - "$TMPFILE" "$CHAT_ID" "$TELEGRAM_BOT_TOKEN" "$LOG_FILE" "$DEBUG_LOG" << 'PYEOF'
import sys, re, json, urllib.request
from datetime import datetime

tmpfile, chat_id, token, log_file, debug_log = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4], sys.argv[5]

def log_debug(msg):
    try:
        with open(debug_log, "a") as f:
            f.write(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}\n")
    except:
        pass

with open(tmpfile) as f:
    text = f.read().strip()

if not text or text == "null":
    log_debug("EXIT: Empty text in Python")
    sys.exit(0)

# Save original text for logging
original_text = text

if len(text) > 4000:
    text = text[:4000] + "\n..."

def esc(s):
    return s.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')

blocks, inlines = [], []
text = re.sub(r'```(\w*)\n?(.*?)```', lambda m: (blocks.append((m.group(1) or '', m.group(2))), f"\x00B{len(blocks)-1}\x00")[1], text, flags=re.DOTALL)
text = re.sub(r'`([^`\n]+)`', lambda m: (inlines.append(m.group(1)), f"\x00I{len(inlines)-1}\x00")[1], text)
text = esc(text)
text = re.sub(r'\*\*(.+?)\*\*', r'<b>\1</b>', text)
text = re.sub(r'(?<!\*)\*([^*]+)\*(?!\*)', r'<i>\1</i>', text)

for i, (lang, code) in enumerate(blocks):
    text = text.replace(f"\x00B{i}\x00", f'<pre><code class="language-{lang}">{esc(code.strip())}</code></pre>' if lang else f'<pre>{esc(code.strip())}</pre>')
for i, code in enumerate(inlines):
    text = text.replace(f"\x00I{i}\x00", f'<code>{esc(code)}</code>')

def send(txt, mode=None):
    data = {"chat_id": chat_id, "text": txt}
    if mode:
        data["parse_mode"] = mode
    try:
        req = urllib.request.Request(f"https://api.telegram.org/bot{token}/sendMessage", json.dumps(data).encode(), {"Content-Type": "application/json"})
        return json.loads(urllib.request.urlopen(req, timeout=10).read()).get("ok")
    except:
        return False

def log_message(text, role="Claude"):
    try:
        time_str = datetime.now().strftime("%H:%M")
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(f"\n[{time_str}] {role}:\n{text}\n")
            f.write("-" * 40 + "\n")
    except:
        pass

log_debug(f"Sending message, length: {len(text)}")
sent = send(text, "HTML")
if not sent:
    log_debug("HTML send failed, trying plain text")
    with open(tmpfile) as f:
        sent = send(f.read()[:4096])

# Log the message after sending
if sent:
    log_debug("Message sent successfully")
    log_message(original_text)
else:
    log_debug("ERROR: Failed to send message")
PYEOF

rm -f "$TMPFILE" "$PENDING_FILE"
exit 0
