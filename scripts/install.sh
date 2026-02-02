#!/bin/bash

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
INSTALLED_MARKER="$PROJECT_DIR/.installed"

print_step() {
    echo -e "\n${BLUE}==>${NC} $1"
}

print_success() {
    echo -e "${GREEN}✓${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}!${NC} $1"
}

print_error() {
    echo -e "${RED}✗${NC} $1"
}

usage() {
    echo "Usage: $0 [OPTIONS] [TELEGRAM_BOT_TOKEN]"
    echo ""
    echo "Options:"
    echo "  -h, --help     Show this help message"
    echo "  -c, --check    Check installation status only"
    echo "  -f, --force    Force reinstall even if already installed"
    echo ""
    echo "Arguments:"
    echo "  TELEGRAM_BOT_TOKEN  Your Telegram bot token (format: 123456789:ABC-DEF...)"
    echo ""
    echo "Examples:"
    echo "  $0 123456789:ABC-DEF1234ghIkl-zyx57W2v1u123ew11"
    echo "  $0 --check"
    echo "  $0 --force 123456789:ABC-DEF1234ghIkl-zyx57W2v1u123ew11"
}

# Check installation status
check_status() {
    print_step "Checking installation status..."

    local all_good=true
    local missing=()

    # Check dependencies
    for cmd in tmux cloudflared jq uv; do
        if command -v "$cmd" &> /dev/null; then
            print_success "$cmd: $(command -v $cmd)"
        else
            print_error "$cmd: not found"
            missing+=("$cmd")
            all_good=false
        fi
    done

    # Check Python environment
    if [ -d "$PROJECT_DIR/.venv" ]; then
        print_success "Python venv: .venv exists"
    else
        print_error "Python venv: not found"
        missing+=("python-venv")
        all_good=false
    fi

    # Check Telegram token
    if [ -n "$TELEGRAM_BOT_TOKEN" ]; then
        print_success "TELEGRAM_BOT_TOKEN: set (env)"
    elif [ -f "$HOME/.claude/hooks/send-to-telegram.sh" ] && ! grep -q "YOUR_BOT_TOKEN_HERE" "$HOME/.claude/hooks/send-to-telegram.sh" 2>/dev/null; then
        print_success "TELEGRAM_BOT_TOKEN: set (in hook)"
    else
        print_warning "TELEGRAM_BOT_TOKEN: not set"
    fi

    # Check hooks
    if [ -f "$HOME/.claude/hooks/send-to-telegram.sh" ]; then
        print_success "Hook script (response): installed"
    else
        print_warning "Hook script (response): not installed"
    fi

    if [ -f "$HOME/.claude/hooks/send-input-to-telegram.sh" ]; then
        print_success "Hook script (input): installed"
    else
        print_warning "Hook script (input): not installed"
    fi

    # Check settings.json
    if [ -f "$HOME/.claude/settings.json" ] && grep -q "send-to-telegram.sh" "$HOME/.claude/settings.json" 2>/dev/null; then
        print_success "Hook config: configured"
    else
        print_warning "Hook config: not configured"
    fi

    echo ""
    if $all_good; then
        print_success "All components installed!"
        return 0
    else
        print_error "Missing components: ${missing[*]}"
        return 1
    fi
}

# Check if running on macOS
check_os() {
    if [[ "$OSTYPE" != "darwin"* ]]; then
        print_error "This script is designed for macOS. Please install dependencies manually."
        exit 1
    fi
}

# Check and install Homebrew
check_homebrew() {
    print_step "Checking Homebrew..."
    if ! command -v brew &> /dev/null; then
        print_warning "Homebrew not found. Installing..."
        /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
    else
        print_success "Homebrew is installed"
    fi
}

# Install system dependencies
install_dependencies() {
    print_step "Installing system dependencies..."

    local deps=("tmux" "cloudflared" "jq")

    for dep in "${deps[@]}"; do
        if command -v "$dep" &> /dev/null; then
            print_success "$dep is already installed"
        else
            print_warning "Installing $dep..."
            brew install "$dep"
            print_success "$dep installed"
        fi
    done
}

# Check and install uv
check_uv() {
    print_step "Checking uv (Python package manager)..."
    if ! command -v uv &> /dev/null; then
        print_warning "uv not found. Installing..."
        curl -LsSf https://astral.sh/uv/install.sh | sh
        export PATH="$HOME/.local/bin:$PATH"
    else
        print_success "uv is installed"
    fi
}

# Setup Python environment
setup_python_env() {
    print_step "Setting up Python environment..."

    cd "$PROJECT_DIR"

    if [ -d ".venv" ]; then
        print_success "Virtual environment already exists"
    else
        uv venv
        print_success "Virtual environment created"
    fi

    source .venv/bin/activate
    uv pip install -e .
    print_success "Python dependencies installed"
}

# Configure Telegram Bot token
configure_telegram() {
    local token="$1"

    print_step "Configuring Telegram Bot..."

    if [ -z "$token" ]; then
        print_error "Telegram bot token is required"
        echo ""
        echo "To create a Telegram bot:"
        echo "  1. Open Telegram and find @BotFather"
        echo "  2. Send /newbot and follow the prompts"
        echo "  3. Copy the token (format: 123456789:ABC-DEF...)"
        echo ""
        echo "Then run: $0 YOUR_BOT_TOKEN"
        exit 1
    fi

    # Detect shell config file
    if [ -f "$HOME/.zshrc" ]; then
        shell_rc="$HOME/.zshrc"
    elif [ -f "$HOME/.bashrc" ]; then
        shell_rc="$HOME/.bashrc"
    else
        shell_rc="$HOME/.zshrc"
    fi

    # Update or add token to shell config
    if grep -q "TELEGRAM_BOT_TOKEN" "$shell_rc" 2>/dev/null; then
        sed -i '' '/TELEGRAM_BOT_TOKEN/d' "$shell_rc"
    fi
    echo "export TELEGRAM_BOT_TOKEN=\"$token\"" >> "$shell_rc"
    print_success "Token added to $shell_rc"

    export TELEGRAM_BOT_TOKEN="$token"
}

# Setup Claude hooks
setup_hooks() {
    local token="$1"

    print_step "Setting up Claude hooks..."

    # Create hooks directory
    mkdir -p ~/.claude/hooks

    # Copy hook scripts
    if [ -f "$PROJECT_DIR/hooks/send-to-telegram.sh" ]; then
        cp "$PROJECT_DIR/hooks/send-to-telegram.sh" ~/.claude/hooks/
        chmod +x ~/.claude/hooks/send-to-telegram.sh

        # Replace token placeholder
        if [ -n "$token" ]; then
            sed -i '' "s/YOUR_BOT_TOKEN_HERE/$token/" ~/.claude/hooks/send-to-telegram.sh
        fi
        print_success "Hook script (response) installed"
    else
        print_error "hooks/send-to-telegram.sh not found"
        return 1
    fi

    if [ -f "$PROJECT_DIR/hooks/send-input-to-telegram.sh" ]; then
        cp "$PROJECT_DIR/hooks/send-input-to-telegram.sh" ~/.claude/hooks/
        chmod +x ~/.claude/hooks/send-input-to-telegram.sh

        # Replace token placeholder
        if [ -n "$token" ]; then
            sed -i '' "s/YOUR_BOT_TOKEN_HERE/$token/" ~/.claude/hooks/send-input-to-telegram.sh
        fi
        print_success "Hook script (input) installed"
    else
        print_error "hooks/send-input-to-telegram.sh not found"
        return 1
    fi

    # Configure settings.json
    settings_file="$HOME/.claude/settings.json"

    if [ -f "$settings_file" ]; then
        # Check if hooks already configured
        if grep -q "send-to-telegram.sh" "$settings_file" 2>/dev/null; then
            print_success "Hook already configured in settings.json"
            return
        fi

        # Backup existing settings
        cp "$settings_file" "$settings_file.backup"
        print_warning "Backed up existing settings.json"

        # Merge hooks into existing settings
        jq '.hooks.Stop = [{"matcher": "", "hooks": [{"type": "command", "command": "~/.claude/hooks/send-to-telegram.sh"}]}] | .hooks.UserPromptSubmit = [{"matcher": "", "hooks": [{"type": "command", "command": "~/.claude/hooks/send-input-to-telegram.sh"}]}]' "$settings_file" > "$settings_file.tmp" && mv "$settings_file.tmp" "$settings_file"
        print_success "Hook configuration added to settings.json"
    else
        # Create new settings.json
        mkdir -p ~/.claude
        cat > "$settings_file" << 'EOF'
{
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
}
EOF
        print_success "Created settings.json with hook configuration"
    fi
}

# Main installation flow
do_install() {
    local token="$1"

    echo "╔════════════════════════════════════════════╗"
    echo "║   Claude Code Telegram Bridge Installer    ║"
    echo "╚════════════════════════════════════════════╝"

    check_os
    check_homebrew
    install_dependencies
    check_uv
    setup_python_env
    configure_telegram "$token"
    setup_hooks "$token"

    # Mark as installed
    touch "$INSTALLED_MARKER"

    echo ""
    print_success "Installation complete!"
    echo ""
    echo "Next steps:"
    echo "  1. Run 'source ~/.zshrc' (or restart terminal)"
    echo "  2. Start the bridge: ./scripts/start.sh"
}

# Parse arguments
FORCE=false
CHECK_ONLY=false
TOKEN=""

while [[ $# -gt 0 ]]; do
    case $1 in
        -h|--help)
            usage
            exit 0
            ;;
        -c|--check)
            CHECK_ONLY=true
            shift
            ;;
        -f|--force)
            FORCE=true
            shift
            ;;
        -*)
            print_error "Unknown option: $1"
            usage
            exit 1
            ;;
        *)
            TOKEN="$1"
            shift
            ;;
    esac
done

# Main logic
if $CHECK_ONLY; then
    check_status
    exit $?
fi

if [ -f "$INSTALLED_MARKER" ] && ! $FORCE; then
    echo "╔════════════════════════════════════════════╗"
    echo "║   Claude Code Telegram Bridge - Status     ║"
    echo "╚════════════════════════════════════════════╝"
    echo ""
    print_warning "Already installed. Running status check..."
    echo ""
    check_status
    echo ""
    echo "To reinstall, run: $0 --force [TOKEN]"
    exit 0
fi

do_install "$TOKEN"
