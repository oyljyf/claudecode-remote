# Development Roadmap

Created: 2025-02-02
Updated: 2025-02-02
Status: Planning

## Planned Features

### Slack Integration

Add Slack as an alternative messaging platform.

**Goals:**
- Support Slack Webhook for notifications
- Slack Bot for bidirectional messaging
- Channel-based routing (different projects → different channels)

**Tech Stack:**
- Slack Bolt SDK (Python)
- Slack Webhook API

**Status:** Planning

---

### Desktop Notifications

Add native macOS desktop notifications using `terminal-notifier`.

**Goals:**
- Notify when Claude completes a response
- Notify on errors or interruptions
- Configurable notification settings (sound, badge, etc.)

**Implementation:**
```bash
# Install
brew install terminal-notifier

# Usage in hooks
terminal-notifier -title "Claude Code" -message "Response complete" -sound default
```

**Integration points:**
- Add to Stop hook for response notifications
- Add to error handling in bridge.py

**Status:** Planning

---

## Backlog

- [ ] Discord integration
- [ ] Email notifications
- [ ] Web dashboard for session management
- [ ] Multi-user support with authentication
- [ ] Response caching for slow connections
