#!/bin/bash

# Claude Code Telegram Bridge - Startup Script
# =============================================
#
# Usage:
#   ./scripts/start.sh              - Start bridge (default)
#   ./scripts/start.sh --new        - Create new tmux session + Claude, then start
#   ./scripts/start.sh --attach     - Attach to Claude tmux session
#   ./scripts/start.sh --detach     - Detach from tmux (run from another terminal)
#   ./scripts/start.sh --view       - View recent Claude output (without attaching)
#   ./scripts/start.sh --check      - Check configuration only
#   ./scripts/start.sh --setup-hook - Setup hook configuration
#   ./scripts/start.sh --sync       - Show how to sync desktop and Telegram
#   ./scripts/start.sh --help       - Show this help

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_DIR"

PORT=${PORT:-8080}
TMUX_SESSION=${TMUX_SESSION:-claude}
CHECK_ONLY=false
NEW_SESSION=false
SETUP_HOOK=false
SHOW_SYNC=false
SHOW_HELP=false
ATTACH_SESSION=false
VIEW_OUTPUT=false
DETACH_SESSION=false

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m'

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --check) CHECK_ONLY=true; shift ;;
        --new) NEW_SESSION=true; shift ;;
        --setup-hook) SETUP_HOOK=true; shift ;;
        --sync) SHOW_SYNC=true; shift ;;
        --help|-h) SHOW_HELP=true; shift ;;
        --attach) ATTACH_SESSION=true; shift ;;
        --detach) DETACH_SESSION=true; shift ;;
        --view) VIEW_OUTPUT=true; shift ;;
        *) shift ;;
    esac
done

print_status() { echo -e "${GREEN}✓${NC} $1"; }
print_error() { echo -e "${RED}✗${NC} $1"; }
print_warning() { echo -e "${YELLOW}!${NC} $1"; }
print_info() { echo -e "${BLUE}→${NC} $1"; }

# ============================================
# Help
# ============================================
show_help() {
    echo -e "${CYAN}Claude Code Telegram Bridge${NC}"
    echo ""
    echo "Usage: ./scripts/start.sh [OPTIONS]"
    echo ""
    echo "Options:"
    echo "  --new         Create new tmux session with Claude, then start bridge"
    echo "  --attach      Attach to Claude tmux session"
    echo "  --detach      Detach from tmux (run from another terminal)"
    echo "  --view        View recent Claude output (without attaching)"
    echo "  --check       Check configuration only (don't start)"
    echo "  --setup-hook  Setup Claude Stop hook for Telegram"
    echo "  --sync        Show how to sync desktop and Telegram sessions"
    echo "  --help, -h    Show this help"
    echo ""
    echo "Environment Variables:"
    echo "  TELEGRAM_BOT_TOKEN  (required) Bot token from @BotFather"
    echo "  TMUX_SESSION        tmux session name (default: claude)"
    echo "  PORT                Bridge port (default: 8080)"
    echo ""
    echo "Examples:"
    echo "  ./scripts/start.sh              # Start bridge"
    echo "  ./scripts/start.sh --new        # Create new session and start"
    echo "  ./scripts/start.sh --setup-hook # Configure hook first"
    echo ""
}

if $SHOW_HELP; then
    show_help
    exit 0
fi

# ============================================
# Sync Instructions
# ============================================
show_sync_instructions() {
    echo ""
    echo -e "${CYAN}========================================${NC}"
    echo -e "${CYAN}  Desktop & Telegram 同步对话指南${NC}"
    echo -e "${CYAN}========================================${NC}"
    echo ""
    echo -e "${YELLOW}原理：${NC}"
    echo "  - Claude Code 对话存储在 ~/.claude/projects/"
    echo "  - 每个 session 有唯一 ID"
    echo "  - Desktop 和 Telegram 通过 tmux 共享同一个 Claude 进程"
    echo "  - 使用 --resume 可以让不同客户端接入同一个对话"
    echo ""
    echo -e "${YELLOW}场景 1：桌面已有对话，Telegram 要加入${NC}"
    echo ""
    echo "  1. 在桌面 Claude Code 中查看 session ID"
    echo "     (标题栏或输入 /status)"
    echo ""
    echo "  2. 在 Telegram 发送 /resume"
    echo "     选择相同的 session"
    echo ""
    echo -e "${YELLOW}场景 2：Telegram 已有对话，桌面要加入${NC}"
    echo ""
    echo "  在桌面终端运行:"
    echo -e "  ${GREEN}claude --resume <session-id> --dangerously-skip-permissions${NC}"
    echo ""
    echo "  查找 session ID:"
    echo -e "  ${GREEN}ls -lt ~/.claude/projects/*/*.jsonl | head -5${NC}"
    echo ""
    echo -e "${YELLOW}场景 3：两边都要看到新对话${NC}"
    echo ""
    echo "  1. 在 Telegram 发送消息开始新对话"
    echo "  2. 在桌面运行: claude --continue --dangerously-skip-permissions"
    echo ""
    echo -e "${RED}注意事项：${NC}"
    echo "  - 桌面和 Telegram 不能同时发送消息，会造成冲突"
    echo "  - 建议：一方发送时，另一方只查看"
    echo "  - tmux session 是共享的，两边看到的是同一个终端输出"
    echo ""
    echo -e "${CYAN}========================================${NC}"
    echo ""
}

if $SHOW_SYNC; then
    show_sync_instructions
    exit 0
fi

# ============================================
# Attach to tmux session (with session selection)
# ============================================
if $ATTACH_SESSION; then
    if ! tmux has-session -t "$TMUX_SESSION" 2>/dev/null; then
        print_error "tmux session '$TMUX_SESSION' not found"
        echo "Run: ./scripts/start.sh --new"
        exit 1
    fi

    echo ""
    echo -e "${CYAN}=== Available Claude Sessions ===${NC}"
    echo ""

    # Find session files and list them
    SESSIONS_DIR=~/.claude/projects
    if [ -d "$SESSIONS_DIR" ]; then
        # Get session files sorted by modification time (newest first)
        SESSION_LIST=$(find "$SESSIONS_DIR" -name "*.jsonl" -type f -exec ls -t {} + 2>/dev/null | head -10)

        if [ -z "$SESSION_LIST" ]; then
            print_warning "No sessions found"
            echo ""
        else
            echo -e "  ${YELLOW}Recent sessions:${NC}"
            echo ""

            i=1
            declare -a SESSION_IDS
            while IFS= read -r file; do
                [ -z "$file" ] && continue
                # Extract session info
                session_id=$(basename "$file" .jsonl)
                SESSION_IDS+=("$session_id")
                project_dir=$(dirname "$file")
                project_name=$(basename "$project_dir")
                mod_time=$(stat -f "%Sm" -t "%Y-%m-%d %H:%M" "$file" 2>/dev/null || stat -c "%y" "$file" 2>/dev/null | cut -d'.' -f1)

                if [ $i -eq 1 ]; then
                    echo -e "  ${GREEN}[$i] $project_name${NC} (latest)"
                    echo -e "      ${BLUE}${session_id:0:36}...${NC}"
                    echo -e "      $mod_time"
                else
                    echo -e "  [$i] $project_name"
                    echo -e "      ${BLUE}${session_id:0:36}...${NC}"
                    echo -e "      $mod_time"
                fi
                echo ""
                ((i++))
            done <<< "$SESSION_LIST"

            total_sessions=$((i-1))
            echo -e "  [0] Just attach (no resume)"
            echo ""

            # Prompt for selection
            read -p "  Select session [1]: " selection
            selection=${selection:-1}

            if [ "$selection" = "0" ]; then
                print_info "Attaching without resume..."
            elif [ "$selection" -ge 1 ] && [ "$selection" -le $total_sessions ] 2>/dev/null; then
                selected_id="${SESSION_IDS[$((selection-1))]}"
                print_info "Resuming session: ${selected_id:0:36}..."
                echo ""
                # Send /resume command to Claude (works within Claude Code)
                tmux send-keys -t "$TMUX_SESSION" "/resume $selected_id" Enter
                sleep 1
            else
                print_warning "Invalid selection, attaching without resume"
            fi
        fi
    else
        print_warning "Sessions directory not found"
    fi

    echo ""
    echo -e "${CYAN}========================================${NC}"
    echo -e "${CYAN}  Attaching to tmux session '$TMUX_SESSION'${NC}"
    echo -e "${CYAN}========================================${NC}"
    echo ""
    echo -e "  ${YELLOW}To detach (from another terminal):${NC}"
    echo -e "    ${GREEN}./scripts/start.sh --detach${NC}"
    echo ""
    sleep 1
    tmux attach -t "$TMUX_SESSION"
    exit 0
fi

# ============================================
# View tmux output (without attaching)
# ============================================
if $VIEW_OUTPUT; then
    if ! tmux has-session -t "$TMUX_SESSION" 2>/dev/null; then
        print_error "tmux session '$TMUX_SESSION' not found"
        exit 1
    fi
    echo ""
    echo -e "${CYAN}=== Recent Claude Output (last 50 lines) ===${NC}"
    echo ""
    tmux capture-pane -t "$TMUX_SESSION" -p -S -50
    echo ""
    echo -e "${CYAN}=============================================${NC}"
    echo ""
    echo -e "  To attach: ${GREEN}./scripts/start.sh --attach${NC}"
    echo -e "  To detach: ${GREEN}./scripts/start.sh --detach${NC} (from another terminal)"
    echo ""
    exit 0
fi

# ============================================
# Detach from tmux (run from another terminal)
# ============================================
if $DETACH_SESSION; then
    if ! tmux has-session -t "$TMUX_SESSION" 2>/dev/null; then
        print_error "tmux session '$TMUX_SESSION' not found"
        exit 1
    fi
    # Detach all clients from the session
    tmux detach-client -s "$TMUX_SESSION" 2>/dev/null
    if [ $? -eq 0 ]; then
        print_status "Detached from tmux session '$TMUX_SESSION'"
    else
        print_warning "No clients attached to '$TMUX_SESSION'"
    fi
    exit 0
fi

# ============================================
# Hook Setup Function
# ============================================
setup_hook() {
    echo -e "\n${BLUE}=== Setting up Hook ===${NC}\n"

    # Check token
    if [ -z "$TELEGRAM_BOT_TOKEN" ]; then
        print_error "TELEGRAM_BOT_TOKEN not set"
        echo "Please run: export TELEGRAM_BOT_TOKEN='your_token'"
        exit 1
    fi

    # Create hooks directory
    mkdir -p ~/.claude/hooks

    # Copy hook scripts
    if [ -f "hooks/send-to-telegram.sh" ]; then
        cp hooks/send-to-telegram.sh ~/.claude/hooks/
        chmod +x ~/.claude/hooks/send-to-telegram.sh
        print_status "Hook script (response) copied"
    else
        print_error "hooks/send-to-telegram.sh not found"
        exit 1
    fi

    if [ -f "hooks/send-input-to-telegram.sh" ]; then
        cp hooks/send-input-to-telegram.sh ~/.claude/hooks/
        chmod +x ~/.claude/hooks/send-input-to-telegram.sh
        print_status "Hook script (input) copied"
    else
        print_error "hooks/send-input-to-telegram.sh not found"
        exit 1
    fi

    # Update token in hook scripts
    sed -i '' "s/YOUR_BOT_TOKEN_HERE/$TELEGRAM_BOT_TOKEN/" ~/.claude/hooks/send-to-telegram.sh 2>/dev/null || \
    sed -i "s/YOUR_BOT_TOKEN_HERE/$TELEGRAM_BOT_TOKEN/" ~/.claude/hooks/send-to-telegram.sh
    sed -i '' "s/YOUR_BOT_TOKEN_HERE/$TELEGRAM_BOT_TOKEN/" ~/.claude/hooks/send-input-to-telegram.sh 2>/dev/null || \
    sed -i "s/YOUR_BOT_TOKEN_HERE/$TELEGRAM_BOT_TOKEN/" ~/.claude/hooks/send-input-to-telegram.sh
    print_status "Token configured in hook scripts"

    # Update settings.json
    SETTINGS_FILE=~/.claude/settings.json
    HOOK_CONFIG='{
  "hooks": {
    "Stop": [
      {
        "matcher": "",
        "hooks": [
          {
            "type": "command",
            "command": "~/.claude/hooks/send-to-telegram.sh"
          }
        ]
      }
    ],
    "UserPromptSubmit": [
      {
        "matcher": "",
        "hooks": [
          {
            "type": "command",
            "command": "~/.claude/hooks/send-input-to-telegram.sh"
          }
        ]
      }
    ]
  }
}'

    if [ -f "$SETTINGS_FILE" ]; then
        if grep -q "send-to-telegram" "$SETTINGS_FILE" 2>/dev/null; then
            print_status "settings.json already has hook configured"
        else
            print_warning "settings.json exists, please manually add hooks config"
            echo ""
            echo "Add this to your ~/.claude/settings.json:"
            echo ""
            echo "$HOOK_CONFIG"
            echo ""
        fi
    else
        echo "$HOOK_CONFIG" > "$SETTINGS_FILE"
        print_status "settings.json created with hook config"
    fi

    echo -e "\n${GREEN}Hook setup complete!${NC}\n"
}

if $SETUP_HOOK; then
    setup_hook
    exit 0
fi

# ============================================
# Configuration Check
# ============================================
check_config() {
    echo -e "\n${BLUE}=== Configuration Check ===${NC}\n"

    local all_ok=true

    # Check TELEGRAM_BOT_TOKEN
    if [ -z "$TELEGRAM_BOT_TOKEN" ]; then
        print_error "TELEGRAM_BOT_TOKEN not set"
        all_ok=false
    else
        print_status "TELEGRAM_BOT_TOKEN is set"
    fi

    # Check tmux
    if command -v tmux &>/dev/null; then
        print_status "tmux installed"
    else
        print_error "tmux not installed (brew install tmux)"
        all_ok=false
    fi

    # Check cloudflared
    if command -v cloudflared &>/dev/null; then
        print_status "cloudflared installed"
    else
        print_error "cloudflared not installed (brew install cloudflared)"
        all_ok=false
    fi

    # Check jq
    if command -v jq &>/dev/null; then
        print_status "jq installed"
    else
        print_error "jq not installed (brew install jq)"
        all_ok=false
    fi

    # Check Python venv
    if [ -d ".venv" ]; then
        print_status "Python venv exists"
    else
        print_error "Python venv not found (run: uv venv && source .venv/bin/activate && uv pip install -e .)"
        all_ok=false
    fi

    # Check hook scripts
    if [ -f ~/.claude/hooks/send-to-telegram.sh ]; then
        print_status "Hook script (response) exists"
        if grep -q "YOUR_BOT_TOKEN_HERE" ~/.claude/hooks/send-to-telegram.sh; then
            print_warning "Hook script (response) has placeholder token - run: ./scripts/start.sh --setup-hook"
        else
            print_status "Hook script (response) token configured"
        fi
    else
        print_error "Hook script (response) not found - run: ./scripts/start.sh --setup-hook"
        all_ok=false
    fi

    if [ -f ~/.claude/hooks/send-input-to-telegram.sh ]; then
        print_status "Hook script (input) exists"
        if grep -q "YOUR_BOT_TOKEN_HERE" ~/.claude/hooks/send-input-to-telegram.sh; then
            print_warning "Hook script (input) has placeholder token - run: ./scripts/start.sh --setup-hook"
        else
            print_status "Hook script (input) token configured"
        fi
    else
        print_error "Hook script (input) not found - run: ./scripts/start.sh --setup-hook"
        all_ok=false
    fi

    # Check settings.json
    if [ -f ~/.claude/settings.json ]; then
        if grep -q "send-to-telegram" ~/.claude/settings.json; then
            print_status "settings.json has hook configured"
        else
            print_warning "settings.json missing hook config - run: ./scripts/start.sh --setup-hook"
        fi
    else
        print_error "settings.json not found - run: ./scripts/start.sh --setup-hook"
        all_ok=false
    fi

    # Check tmux session
    if tmux has-session -t "$TMUX_SESSION" 2>/dev/null; then
        print_status "tmux session '$TMUX_SESSION' running"
    else
        print_warning "tmux session '$TMUX_SESSION' not found"
        echo "         Start with: tmux new -s $TMUX_SESSION"
        echo "         Then run: claude --dangerously-skip-permissions"
        echo "         Or use: ./scripts/start.sh --new"
    fi

    echo ""
    if $all_ok; then
        print_status "All checks passed!"
    else
        print_error "Some checks failed - fix issues above"
    fi

    return 0
}

if $CHECK_ONLY; then
    check_config
    exit 0
fi

# ============================================
# Process Management
# ============================================
kill_port() {
    local pid=$(lsof -ti:$PORT 2>/dev/null)
    if [ -n "$pid" ]; then
        print_warning "Port $PORT occupied by PID $pid, killing..."
        kill -9 $pid 2>/dev/null
        sleep 1
    fi
}

kill_cloudflared() {
    local pids=$(pgrep -f "cloudflared tunnel" 2>/dev/null)
    if [ -n "$pids" ]; then
        print_warning "Killing existing cloudflared processes..."
        pkill -9 -f "cloudflared tunnel" 2>/dev/null
        sleep 1
    fi
}

kill_bridge() {
    local pids=$(pgrep -f "python bridge.py" 2>/dev/null)
    if [ -n "$pids" ]; then
        print_warning "Killing existing bridge processes..."
        pkill -9 -f "python bridge.py" 2>/dev/null
        sleep 1
    fi
}

cleanup() {
    echo -e "\n${YELLOW}Shutting down...${NC}"
    kill $BRIDGE_PID 2>/dev/null
    kill $TUNNEL_PID 2>/dev/null
    rm -f /tmp/tunnel_output.log
    rm -f ~/.claude/telegram_pending
    exit 0
}

# ============================================
# New Session Mode
# ============================================
if $NEW_SESSION; then
    echo -e "\n${BLUE}=== Creating New Session ===${NC}\n"

    if tmux has-session -t "$TMUX_SESSION" 2>/dev/null; then
        print_warning "Killing existing tmux session..."
        tmux kill-session -t "$TMUX_SESSION"
        sleep 1
    fi

    print_info "Creating tmux session and starting Claude..."
    tmux new-session -d -s "$TMUX_SESSION" "claude --dangerously-skip-permissions"
    sleep 2

    if tmux has-session -t "$TMUX_SESSION" 2>/dev/null; then
        print_status "tmux session '$TMUX_SESSION' created with Claude"
        print_info "To detach: run './scripts/start.sh --detach' from another terminal"
    else
        print_error "Failed to create tmux session"
        exit 1
    fi
fi

# ============================================
# Pre-flight Checks
# ============================================
echo -e "\n${BLUE}=== Pre-flight Checks ===${NC}\n"

# Check token
if [ -z "$TELEGRAM_BOT_TOKEN" ]; then
    print_error "TELEGRAM_BOT_TOKEN not set"
    echo "Run: export TELEGRAM_BOT_TOKEN='your_token'"
    exit 1
fi
print_status "TELEGRAM_BOT_TOKEN set"

# Check tmux session
if ! tmux has-session -t "$TMUX_SESSION" 2>/dev/null; then
    print_error "tmux session '$TMUX_SESSION' not found"
    echo ""
    echo "Option 1 - Create manually:"
    echo "  tmux new -s $TMUX_SESSION"
    echo "  claude --dangerously-skip-permissions"
    echo ""
    echo "Option 2 - Auto create:"
    echo "  ./scripts/start.sh --new"
    exit 1
fi
print_status "tmux session '$TMUX_SESSION' running"

# Check hook configuration
if [ ! -f ~/.claude/hooks/send-to-telegram.sh ] || [ ! -f ~/.claude/hooks/send-input-to-telegram.sh ]; then
    print_error "Hooks not configured"
    echo "Run: ./scripts/start.sh --setup-hook"
    exit 1
fi
print_status "Hook scripts exist"

# ============================================
# Cleanup Old Processes
# ============================================
echo -e "\n${BLUE}=== Cleaning Up ===${NC}\n"

kill_bridge
kill_port
kill_cloudflared

print_status "Old processes cleaned"

# ============================================
# Start Services
# ============================================
echo -e "\n${BLUE}=== Starting Services ===${NC}\n"

trap cleanup SIGINT SIGTERM

# Activate venv
source .venv/bin/activate

# Start bridge
print_info "Starting bridge server..."
python bridge.py &
BRIDGE_PID=$!
sleep 2

if ! kill -0 $BRIDGE_PID 2>/dev/null; then
    print_error "Bridge failed to start"
    exit 1
fi
print_status "Bridge running on :$PORT"

# Start tunnel
print_info "Starting cloudflared tunnel..."

TUNNEL_URL=""
TUNNEL_LOG="/tmp/tunnel_output.log"
rm -f "$TUNNEL_LOG"
touch "$TUNNEL_LOG"

# Start cloudflared and redirect output to log file
cloudflared tunnel --url http://localhost:$PORT >> "$TUNNEL_LOG" 2>&1 &
TUNNEL_PID=$!

print_info "Waiting for tunnel URL..."
for i in {1..20}; do
    sleep 1
    # Check if tunnel process is still running
    if ! kill -0 $TUNNEL_PID 2>/dev/null; then
        print_error "Cloudflared process died"
        cat "$TUNNEL_LOG"
        cleanup
        exit 1
    fi
    # Try to extract URL (format: https://xxx-xxx-xxx-xxx.trycloudflare.com)
    TUNNEL_URL=$(grep -oE 'https://[a-zA-Z0-9-]+\.trycloudflare\.com' "$TUNNEL_LOG" 2>/dev/null | head -1)
    if [ -n "$TUNNEL_URL" ]; then
        break
    fi
    echo -n "."
done
echo ""

if [ -z "$TUNNEL_URL" ]; then
    print_error "Failed to get tunnel URL after 20 seconds"
    echo "Tunnel log:"
    cat "$TUNNEL_LOG"
    cleanup
    exit 1
fi

print_status "Tunnel URL: $TUNNEL_URL"

# Wait for tunnel to be fully registered
print_info "Waiting for tunnel to be fully established..."
for i in {1..10}; do
    if grep -q "Registered tunnel connection" "$TUNNEL_LOG" 2>/dev/null; then
        break
    fi
    sleep 1
    echo -n "."
done
echo ""
print_status "Tunnel established"

# Wait for DNS propagation (cloudflare quick tunnels need time)
print_info "Waiting for DNS propagation (10 seconds)..."
sleep 10

# ============================================
# Set Webhook
# ============================================
echo -e "\n${BLUE}=== Setting Webhook ===${NC}\n"

# Retry webhook setup (DNS may take a moment to propagate)
for attempt in {1..5}; do
    print_info "Setting webhook (attempt $attempt)..."

    WEBHOOK_RESULT=$(curl -s "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/setWebhook?url=${TUNNEL_URL}")

    if echo "$WEBHOOK_RESULT" | jq -e '.ok == true' >/dev/null 2>&1; then
        print_status "Webhook set successfully"
        break
    else
        if [ $attempt -lt 5 ]; then
            print_warning "Webhook failed, retrying in 5 seconds..."
            sleep 5
        else
            print_error "Failed to set webhook after 5 attempts"
            echo "$WEBHOOK_RESULT" | jq .
            cleanup
            exit 1
        fi
    fi
done

# ============================================
# Running
# ============================================
echo ""
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}  Bridge is running!${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""
echo -e "  Tunnel:  ${BLUE}$TUNNEL_URL${NC}"
echo -e "  Bridge:  ${BLUE}http://localhost:$PORT${NC}"
echo -e "  tmux:    ${BLUE}$TMUX_SESSION${NC}"
echo ""
echo -e "  ${YELLOW}Send a message to your bot to test!${NC}"
echo ""
echo -e "  ${CYAN}Telegram Commands:${NC}"
echo -e "    /status     Check tmux status"
echo -e "    /stop       Interrupt Claude"
echo -e "    /clear      Clear conversation"
echo -e "    /resume     Resume a session"
echo ""
echo -e "  ${CYAN}tmux Controls (from another terminal):${NC}"
echo -e "    ${GREEN}./scripts/start.sh --detach${NC}  Detach from tmux"
echo -e "    ${GREEN}./scripts/start.sh --view${NC}    View Claude output"
echo -e "    ${GREEN}./scripts/start.sh --attach${NC}  Re-attach to tmux"
echo ""
echo -e "${GREEN}========================================${NC}"
echo ""
echo -e "  ${YELLOW}Attaching to tmux session in 3 seconds...${NC}"
echo -e "  ${YELLOW}To detach: run './scripts/start.sh --detach' from another terminal${NC}"
echo ""
sleep 3

# Attach to tmux session (bridge continues in background)
tmux attach -t "$TMUX_SESSION"

# After detaching, show status and wait for bridge processes
echo ""
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}  Detached from tmux. Bridge running.${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""
echo -e "  Tunnel:  ${BLUE}$TUNNEL_URL${NC}"
echo -e "  Bridge:  ${BLUE}http://localhost:$PORT${NC}"
echo ""
echo -e "  ${CYAN}Commands:${NC}"
echo -e "    ${GREEN}./scripts/start.sh --attach${NC}  Re-attach to Claude"
echo -e "    ${GREEN}./scripts/start.sh --view${NC}    View Claude output"
echo -e "    ${RED}Ctrl+C${NC}              Stop bridge"
echo ""

wait
