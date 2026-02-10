#!/bin/bash
# Common utilities for claudecode-remote scripts
# Source this file: source "$SCRIPT_DIR/lib/common.sh"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m'

# Load shared defaults from config.env
_COMMON_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-${(%):-%x}}")" && pwd)"
_CONFIG_ENV="$_COMMON_DIR/../../config.env"
if [ -f "$_CONFIG_ENV" ]; then
    source "$_CONFIG_ENV"
else
    # Fallback if config.env not found
    DEFAULT_PORT=8080
    DEFAULT_TMUX_SESSION=claude
fi

# Shared paths
CHAT_ID_FILE=~/.claude/telegram_chat_id
PENDING_FILE=~/.claude/telegram_pending
SESSION_CHAT_MAP_FILE=~/.claude/session_chat_map.json
CURRENT_SESSION_FILE=~/.claude/current_session_id
SYNC_DISABLED_FILE=~/.claude/telegram_sync_disabled
SYNC_PAUSED_FILE=~/.claude/telegram_sync_paused
LOG_DIR=~/.claude/logs
LOG_FILE="$LOG_DIR/cc_$(date +%m%d%Y).log"

print_status() { echo -e "${GREEN}✓${NC} $1"; }
print_error() { echo -e "${RED}✗${NC} $1"; }
print_warning() { echo -e "${YELLOW}!${NC} $1"; }
print_info() { echo -e "${BLUE}→${NC} $1"; }

kill_bridge() {
    local pids
    pids=$(pgrep -f "python.*bridge.py" 2>/dev/null || true)
    if [ -n "$pids" ]; then
        print_warning "Killing bridge processes..."
        pkill -9 -f "python.*bridge.py" 2>/dev/null || true
        sleep 1
        print_status "Bridge processes killed"
    else
        print_info "No bridge processes running"
    fi
}

kill_cloudflared() {
    local pids
    pids=$(pgrep -f "cloudflared tunnel" 2>/dev/null || true)
    if [ -n "$pids" ]; then
        print_warning "Killing cloudflared processes..."
        pkill -9 -f "cloudflared tunnel" 2>/dev/null || true
        sleep 1
        print_status "Cloudflared processes killed"
    else
        print_info "No cloudflared processes running"
    fi
}
