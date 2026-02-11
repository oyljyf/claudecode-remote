#!/bin/bash

# Claude Code Remote - Uninstaller
# ==========================================
#
# Usage:
#   ./scripts/uninstall.sh              - Interactive uninstall (remove all components)
#   ./scripts/uninstall.sh --telegram   - Remove only Telegram hooks and bridge
#   ./scripts/uninstall.sh --alarm      - Remove only alarm hook and sounds
#   ./scripts/uninstall.sh --all        - Remove everything (including logs)
#   ./scripts/uninstall.sh --keep-deps  - Keep system dependencies (tmux, cloudflared, jq)
#   ./scripts/uninstall.sh --help       - Show help

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

source "$SCRIPT_DIR/lib/common.sh"

# Options
REMOVE_ALL=false
REMOVE_TELEGRAM=false
REMOVE_ALARM=false
KEEP_DEPS=false
SHOW_HELP=false
FORCE=false

usage() {
    echo -e "${CYAN}Claude Code Remote - Uninstaller${NC}"
    echo ""
    echo "Usage: $0 [OPTIONS]"
    echo ""
    echo "Component options:"
    echo "  --telegram   Remove only Telegram hooks and bridge"
    echo "  --alarm      Remove only alarm hook and sounds"
    echo "  (default)    Remove both Telegram and alarm components"
    echo ""
    echo "Other options:"
    echo "  --all        Remove everything including logs and session data"
    echo "  --keep-deps  Keep system dependencies (tmux, cloudflared, jq)"
    echo "  --force      Skip confirmation prompts"
    echo "  --help, -h   Show this help"
    echo ""
    echo "What gets removed:"
    echo "  Telegram: hooks (send-*-telegram.sh), bridge state, env vars, webhook, processes, venv"
    echo "  Alarm:    hook (play-alarm.sh), sounds (~/.claude/sounds/), alarm_disabled"
    echo "  Shared:   hooks/lib/ (when both removed), settings.json hook config"
    echo ""
    echo "With --all:"
    echo "  - Conversation logs (~/.claude/logs/)"
    echo "  - Session mapping files"
    echo ""
    echo "NOT removed:"
    echo "  - System dependencies (tmux, cloudflared, jq, uv) -- unless confirmed"
    echo "  - Claude Code itself"
    echo "  - Claude Code sessions (~/.claude/projects/)"
}

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --all) REMOVE_ALL=true; shift ;;
        --telegram) REMOVE_TELEGRAM=true; shift ;;
        --alarm) REMOVE_ALARM=true; shift ;;
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
echo -e "${RED}║      Claude Code Remote Uninstaller        ║${NC}"
echo -e "${RED}╚════════════════════════════════════════════╝${NC}"
echo ""

# Interactive component selection (when no --telegram/--alarm flags specified)
if ! $REMOVE_TELEGRAM && ! $REMOVE_ALARM; then
    if ! $FORCE; then
        echo -e "${YELLOW}What would you like to uninstall?${NC}"
        echo ""
        echo "  1) Telegram only  — hooks, bridge, state files, env vars"
        echo "  2) Alarm only     — alarm hook, sounds, alarm_disabled"
        echo "  3) Both           — remove all components"
        echo ""
        read -p "Choose [1/2/3] (default: 3): " choice
        echo ""
        case "$choice" in
            1) REMOVE_TELEGRAM=true ;;
            2) REMOVE_ALARM=true ;;
            *) REMOVE_TELEGRAM=true; REMOVE_ALARM=true ;;
        esac
    else
        # --force without component flags: remove both
        REMOVE_TELEGRAM=true
        REMOVE_ALARM=true
    fi
fi

# Show what will be removed
echo -e "${YELLOW}Components to remove:${NC}"
$REMOVE_TELEGRAM && echo "  - Telegram hooks and bridge"
$REMOVE_ALARM && echo "  - Alarm hook and sounds"
echo ""

# Confirmation
if ! $FORCE; then
    read -p "Continue? [y/N] " confirm
    if [[ ! "$confirm" =~ ^[Yy]$ ]]; then
        echo "Aborted."
        exit 0
    fi
    echo ""
fi

# ============================================
# Stop Running Processes (Telegram-specific)
# ============================================
if $REMOVE_TELEGRAM; then
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
fi

# ============================================
# Remove Telegram Hooks
# ============================================
if $REMOVE_TELEGRAM; then
    echo -e "\n${BLUE}=== Removing Telegram Hooks ===${NC}\n"

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

    if [ -f ~/.claude/hooks/handle-permission.sh ]; then
        rm -f ~/.claude/hooks/handle-permission.sh
        print_status "Removed handle-permission.sh"
    else
        print_info "handle-permission.sh not found"
    fi

    if [ -f ~/.claude/hooks/send-notification-to-telegram.sh ]; then
        rm -f ~/.claude/hooks/send-notification-to-telegram.sh
        print_status "Removed send-notification-to-telegram.sh"
    else
        print_info "send-notification-to-telegram.sh not found"
    fi
fi

# ============================================
# Remove Alarm Hook
# ============================================
if $REMOVE_ALARM; then
    echo -e "\n${BLUE}=== Removing Alarm Hook ===${NC}\n"

    if [ -f ~/.claude/hooks/play-alarm.sh ]; then
        rm -f ~/.claude/hooks/play-alarm.sh
        print_status "Removed play-alarm.sh"
    else
        print_info "play-alarm.sh not found"
    fi

    if [ -d ~/.claude/sounds ]; then
        rm -rf ~/.claude/sounds
        print_status "Removed sounds directory"
    else
        print_info "sounds directory not found"
    fi

    rm -f ~/.claude/alarm_disabled
fi

# Remove hooks lib directory (only when both components removed)
if $REMOVE_TELEGRAM && $REMOVE_ALARM; then
    if [ -d ~/.claude/hooks/lib ]; then
        rm -rf ~/.claude/hooks/lib
        print_status "Removed hooks/lib directory"
    fi
fi

# Remove hooks directory if empty
if [ -d ~/.claude/hooks ] && [ -z "$(ls -A ~/.claude/hooks 2>/dev/null)" ]; then
    rmdir ~/.claude/hooks
    print_status "Removed empty hooks directory"
fi

# ============================================
# Update settings.json
# ============================================
echo -e "\n${BLUE}=== Updating settings.json ===${NC}\n"

SETTINGS_FILE=~/.claude/settings.json
if [ -f "$SETTINGS_FILE" ] && command -v jq &>/dev/null; then
    if $REMOVE_TELEGRAM && $REMOVE_ALARM; then
        # Remove all hook config
        if grep -q "send-to-telegram\|play-alarm" "$SETTINGS_FILE" 2>/dev/null; then
            if [ -f "$SETTINGS_FILE.backup" ]; then
                mv "$SETTINGS_FILE.backup" "$SETTINGS_FILE"
                print_status "settings.json restored from backup"
            else
                jq 'del(.hooks.Stop) | del(.hooks.Notification) | del(.hooks.UserPromptSubmit) | del(.hooks.PermissionRequest) | if .hooks == {} then del(.hooks) else . end' "$SETTINGS_FILE" > "$SETTINGS_FILE.tmp" 2>/dev/null && mv "$SETTINGS_FILE.tmp" "$SETTINGS_FILE"
                print_status "All hook config removed from settings.json"
            fi
        else
            print_info "No hook config in settings.json"
        fi
    elif $REMOVE_TELEGRAM; then
        # Remove telegram entries, keep alarm
        if grep -q "send-to-telegram" "$SETTINGS_FILE" 2>/dev/null; then
            jq '.hooks.Stop = [.hooks.Stop[]? | select(.hooks[0]?.command | contains("send-to-telegram") | not)] | del(.hooks.UserPromptSubmit) | del(.hooks.PermissionRequest) | if .hooks.Notification then .hooks.Notification = [.hooks.Notification[]? | .hooks = [.hooks[]? | select(.command | contains("send-notification-to-telegram") | not)] | select(.hooks | length > 0)] else . end | if (.hooks.Notification // []) == [] then del(.hooks.Notification) else . end | if .hooks.Stop == [] then del(.hooks.Stop) else . end | if .hooks == {} then del(.hooks) else . end' "$SETTINGS_FILE" > "$SETTINGS_FILE.tmp" 2>/dev/null && mv "$SETTINGS_FILE.tmp" "$SETTINGS_FILE"
            print_status "Telegram hook config removed from settings.json"
        else
            print_info "No Telegram hook config in settings.json"
        fi
    elif $REMOVE_ALARM; then
        # Remove alarm entries, keep telegram
        if grep -q "play-alarm" "$SETTINGS_FILE" 2>/dev/null; then
            jq '.hooks.Stop = [.hooks.Stop[]? | select(.hooks[0]?.command | contains("play-alarm") | not)] | if .hooks.Notification then .hooks.Notification = [.hooks.Notification[]? | .hooks = [.hooks[]? | select(.command | contains("play-alarm") | not)] | select(.hooks | length > 0)] else . end | if (.hooks.Notification // []) == [] then del(.hooks.Notification) else . end | if .hooks.Stop == [] then del(.hooks.Stop) else . end | if .hooks == {} then del(.hooks) else . end' "$SETTINGS_FILE" > "$SETTINGS_FILE.tmp" 2>/dev/null && mv "$SETTINGS_FILE.tmp" "$SETTINGS_FILE"
            print_status "Alarm hook config removed from settings.json"
        else
            print_info "No alarm hook config in settings.json"
        fi
    fi
elif [ -f "$SETTINGS_FILE" ]; then
    print_warning "jq not found, please manually remove hooks from settings.json"
else
    print_info "settings.json not found"
fi

# ============================================
# Remove Bridge State Files (Telegram-specific)
# ============================================
if $REMOVE_TELEGRAM; then
    echo -e "\n${BLUE}=== Removing State Files ===${NC}\n"

    state_files=(
        "$CHAT_ID_FILE"
        "$PENDING_FILE"
        "$SYNC_DISABLED_FILE"
        "$SYNC_PAUSED_FILE"
        "$CURRENT_SESSION_FILE"
        "$SESSION_CHAT_MAP_FILE"
        "$HOME/.claude/pending_permission.json"
        "$HOME/.claude/permission_response.json"
    )

    for f in "${state_files[@]}"; do
        if [ -f "$f" ]; then
            rm -f "$f"
            print_status "Removed $(basename $f)"
        fi
    done
fi

# ============================================
# Remove TELEGRAM_BOT_TOKEN from Shell Config (Telegram-specific)
# ============================================
if $REMOVE_TELEGRAM; then
    echo -e "\n${BLUE}=== Removing Environment Variables ===${NC}\n"

    for rc_file in ~/.zshrc ~/.bashrc ~/.bash_profile; do
        if [ -f "$rc_file" ] && grep -q "TELEGRAM_BOT_TOKEN" "$rc_file" 2>/dev/null; then
            sed -i '' '/TELEGRAM_BOT_TOKEN/d' "$rc_file" 2>/dev/null || \
            sed -i '/TELEGRAM_BOT_TOKEN/d' "$rc_file" 2>/dev/null || true
            print_status "Removed TELEGRAM_BOT_TOKEN from $(basename $rc_file)"
        fi
    done
fi

# ============================================
# Remove Python Virtual Environment (Telegram-specific)
# ============================================
if $REMOVE_TELEGRAM; then
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
if $REMOVE_TELEGRAM && ! $KEEP_DEPS; then
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
if $REMOVE_TELEGRAM; then
echo "    - Telegram hooks (send-to-telegram, send-input-to-telegram)"
echo "    - Bridge state files"
echo "    - Environment variables"
echo "    - Python virtual environment"
fi
if $REMOVE_ALARM; then
echo "    - Alarm hook (play-alarm, sounds)"
fi
echo "    - Hook configuration (settings.json)"
if $REMOVE_ALL; then
echo "    - Conversation logs"
fi
echo ""
echo -e "  ${CYAN}Preserved:${NC}"
echo "    - Claude Code sessions (~/.claude/projects/)"
echo "    - Claude Code settings (except removed hooks)"
if ! $REMOVE_TELEGRAM; then
echo "    - Telegram hooks and bridge"
fi
if ! $REMOVE_ALARM; then
echo "    - Alarm hook and sounds"
fi
if $KEEP_DEPS || ! $REMOVE_TELEGRAM || ! [[ "${remove_deps:-n}" =~ ^[Yy]$ ]]; then
echo "    - System dependencies (tmux, cloudflared, jq)"
fi
echo ""
echo -e "  ${BLUE}To reinstall:${NC}"
echo "    ./scripts/install.sh YOUR_BOT_TOKEN"
echo ""
