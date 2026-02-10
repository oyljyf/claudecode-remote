#!/bin/bash

# Claude Code Telegram Bridge - Uninstaller
# ==========================================
#
# Usage:
#   ./scripts/uninstall.sh           - Interactive uninstall
#   ./scripts/uninstall.sh --all     - Remove everything (including logs)
#   ./scripts/uninstall.sh --keep-deps  - Keep system dependencies (tmux, cloudflared, jq)
#   ./scripts/uninstall.sh --help    - Show help

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

source "$SCRIPT_DIR/lib/common.sh"

# Options
REMOVE_ALL=false
KEEP_DEPS=false
SHOW_HELP=false
FORCE=false

usage() {
    echo -e "${CYAN}Claude Code Telegram Bridge - Uninstaller${NC}"
    echo ""
    echo "Usage: $0 [OPTIONS]"
    echo ""
    echo "Options:"
    echo "  --all        Remove everything including logs and session data"
    echo "  --keep-deps  Keep system dependencies (tmux, cloudflared, jq)"
    echo "  --force      Skip confirmation prompts"
    echo "  --help, -h   Show this help"
    echo ""
    echo "What gets removed:"
    echo "  - Hook scripts (~/.claude/hooks/send-*-telegram.sh)"
    echo "  - Hook config from settings.json"
    echo "  - TELEGRAM_BOT_TOKEN from shell config"
    echo "  - Python virtual environment (.venv)"
    echo "  - Bridge state files (~/.claude/telegram_*, session_chat_map.json)"
    echo "  - Running bridge/tunnel processes"
    echo ""
    echo "With --all:"
    echo "  - Conversation logs (~/.claude/logs/)"
    echo "  - Session mapping files"
    echo ""
    echo "NOT removed (use --keep-deps to preserve):"
    echo "  - System dependencies (tmux, cloudflared, jq, uv)"
    echo "  - Claude Code itself"
    echo "  - Claude Code sessions (~/.claude/projects/)"
}

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --all) REMOVE_ALL=true; shift ;;
        --keep-deps) KEEP_DEPS=true; shift ;;
        --force) FORCE=true; shift ;;
        --help|-h) SHOW_HELP=true; shift ;;
        *) shift ;;
    esac
done

if $SHOW_HELP; then
    usage
    exit 0
fi

echo ""
echo -e "${RED}╔════════════════════════════════════════════╗${NC}"
echo -e "${RED}║   Claude Code Telegram Bridge Uninstaller  ║${NC}"
echo -e "${RED}╚════════════════════════════════════════════╝${NC}"
echo ""

# Confirmation
if ! $FORCE; then
    echo -e "${YELLOW}This will remove the Telegram bridge installation.${NC}"
    echo ""
    read -p "Continue? [y/N] " confirm
    if [[ ! "$confirm" =~ ^[Yy]$ ]]; then
        echo "Aborted."
        exit 0
    fi
    echo ""
fi

# ============================================
# Stop Running Processes
# ============================================
echo -e "${BLUE}=== Stopping Processes ===${NC}\n"

kill_bridge
kill_cloudflared

# Remove webhook
if [ -n "$TELEGRAM_BOT_TOKEN" ]; then
    print_info "Removing Telegram webhook..."
    curl -s "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/deleteWebhook" > /dev/null 2>&1 || true
    print_status "Webhook removed"
fi

# Kill tmux session
TMUX_SESSION=${TMUX_SESSION:-claude}
if tmux has-session -t "$TMUX_SESSION" 2>/dev/null; then
    print_info "Killing tmux session '$TMUX_SESSION'..."
    tmux kill-session -t "$TMUX_SESSION" 2>/dev/null || true
    print_status "tmux session killed"
else
    print_info "No tmux session '$TMUX_SESSION' running"
fi

# Clean up temporary files
rm -f /tmp/tunnel_output.log

# ============================================
# Remove Hook Scripts
# ============================================
echo -e "\n${BLUE}=== Removing Hooks ===${NC}\n"

if [ -f ~/.claude/hooks/send-to-telegram.sh ]; then
    rm -f ~/.claude/hooks/send-to-telegram.sh
    print_status "Removed send-to-telegram.sh"
else
    print_info "send-to-telegram.sh not found"
fi

if [ -f ~/.claude/hooks/send-input-to-telegram.sh ]; then
    rm -f ~/.claude/hooks/send-input-to-telegram.sh
    print_status "Removed send-input-to-telegram.sh"
else
    print_info "send-input-to-telegram.sh not found"
fi

# Remove hooks lib directory
if [ -d ~/.claude/hooks/lib ]; then
    rm -rf ~/.claude/hooks/lib
    print_status "Removed hooks/lib directory"
fi

# Remove hooks directory if empty
if [ -d ~/.claude/hooks ] && [ -z "$(ls -A ~/.claude/hooks 2>/dev/null)" ]; then
    rmdir ~/.claude/hooks
    print_status "Removed empty hooks directory"
fi

# ============================================
# Remove Hook Config from settings.json
# ============================================
echo -e "\n${BLUE}=== Updating settings.json ===${NC}\n"

SETTINGS_FILE=~/.claude/settings.json
if [ -f "$SETTINGS_FILE" ]; then
    if grep -q "send-to-telegram" "$SETTINGS_FILE" 2>/dev/null; then
        # Check if there's a backup
        if [ -f "$SETTINGS_FILE.backup" ]; then
            print_info "Restoring settings.json from backup..."
            mv "$SETTINGS_FILE.backup" "$SETTINGS_FILE"
            print_status "settings.json restored"
        else
            # Remove hook entries using jq if available
            if command -v jq &>/dev/null; then
                print_info "Removing hook config from settings.json..."
                jq 'del(.hooks.Stop) | del(.hooks.UserPromptSubmit) | if .hooks == {} then del(.hooks) else . end' "$SETTINGS_FILE" > "$SETTINGS_FILE.tmp" 2>/dev/null && mv "$SETTINGS_FILE.tmp" "$SETTINGS_FILE"
                print_status "Hook config removed from settings.json"
            else
                print_warning "jq not found, please manually remove hooks from settings.json"
            fi
        fi
    else
        print_info "No hook config in settings.json"
    fi
else
    print_info "settings.json not found"
fi

# ============================================
# Remove Bridge State Files
# ============================================
echo -e "\n${BLUE}=== Removing State Files ===${NC}\n"

state_files=(
    "$CHAT_ID_FILE"
    "$PENDING_FILE"
    "$SYNC_DISABLED_FILE"
    "$SYNC_PAUSED_FILE"
    "$CURRENT_SESSION_FILE"
    "$SESSION_CHAT_MAP_FILE"
)

for f in "${state_files[@]}"; do
    if [ -f "$f" ]; then
        rm -f "$f"
        print_status "Removed $(basename $f)"
    fi
done

# ============================================
# Remove TELEGRAM_BOT_TOKEN from Shell Config
# ============================================
echo -e "\n${BLUE}=== Removing Environment Variables ===${NC}\n"

for rc_file in ~/.zshrc ~/.bashrc ~/.bash_profile; do
    if [ -f "$rc_file" ] && grep -q "TELEGRAM_BOT_TOKEN" "$rc_file" 2>/dev/null; then
        sed -i '' '/TELEGRAM_BOT_TOKEN/d' "$rc_file" 2>/dev/null || \
        sed -i '/TELEGRAM_BOT_TOKEN/d' "$rc_file" 2>/dev/null || true
        print_status "Removed TELEGRAM_BOT_TOKEN from $(basename $rc_file)"
    fi
done

# ============================================
# Remove Python Virtual Environment
# ============================================
echo -e "\n${BLUE}=== Removing Python Environment ===${NC}\n"

if [ -d "$PROJECT_DIR/.venv" ]; then
    rm -rf "$PROJECT_DIR/.venv"
    print_status "Removed .venv"
else
    print_info ".venv not found"
fi

# Remove installed marker
if [ -f "$PROJECT_DIR/.installed" ]; then
    rm -f "$PROJECT_DIR/.installed"
    print_status "Removed .installed marker"
fi

# ============================================
# Remove Logs (if --all)
# ============================================
if $REMOVE_ALL; then
    echo -e "\n${BLUE}=== Removing Logs ===${NC}\n"

    if [ -d ~/.claude/logs ]; then
        rm -rf ~/.claude/logs
        print_status "Removed ~/.claude/logs/"
    else
        print_info "No logs directory found"
    fi

    # Remove history.jsonl
    if [ -f ~/.claude/history.jsonl ]; then
        rm -f ~/.claude/history.jsonl
        print_status "Removed history.jsonl"
    fi
fi

# ============================================
# Remove System Dependencies (unless --keep-deps)
# ============================================
if ! $KEEP_DEPS; then
    echo -e "\n${BLUE}=== System Dependencies ===${NC}\n"

    if ! $FORCE; then
        echo -e "${YELLOW}Remove system dependencies (tmux, cloudflared, jq)?${NC}"
        echo "These may be used by other applications."
        read -p "Remove? [y/N] " remove_deps
        echo ""
    else
        remove_deps="n"
    fi

    if [[ "$remove_deps" =~ ^[Yy]$ ]]; then
        if command -v brew &>/dev/null; then
            for dep in cloudflared; do
                if brew list "$dep" &>/dev/null; then
                    brew uninstall "$dep" 2>/dev/null || true
                    print_status "Uninstalled $dep"
                fi
            done
            print_warning "Kept tmux and jq (commonly used by other tools)"
        else
            print_warning "Homebrew not found, skipping dependency removal"
        fi
    else
        print_info "Keeping system dependencies"
    fi
fi

# ============================================
# Summary
# ============================================
echo ""
echo -e "${GREEN}════════════════════════════════════════════${NC}"
echo -e "${GREEN}  Uninstallation Complete${NC}"
echo -e "${GREEN}════════════════════════════════════════════${NC}"
echo ""
echo -e "  ${YELLOW}Removed:${NC}"
echo "    - Hook scripts"
echo "    - Hook configuration"
echo "    - Bridge state files"
echo "    - Environment variables"
echo "    - Python virtual environment"
if $REMOVE_ALL; then
echo "    - Conversation logs"
fi
echo ""
echo -e "  ${CYAN}Preserved:${NC}"
echo "    - Claude Code sessions (~/.claude/projects/)"
echo "    - Claude Code settings (except hooks)"
if $KEEP_DEPS || ! [[ "$remove_deps" =~ ^[Yy]$ ]]; then
echo "    - System dependencies (tmux, cloudflared, jq)"
fi
echo ""
echo -e "  ${BLUE}To reinstall:${NC}"
echo "    ./scripts/install.sh YOUR_BOT_TOKEN"
echo ""
