#!/bin/bash
# Claude Code hook - plays sound when Claude stops or needs attention
# Usage: play-alarm.sh [done|alert]
#   done  — task completed (Stop hook, default)
#   alert — needs user action (Notification hook)
# Install: copy to ~/.claude/hooks/ and add to ~/.claude/settings.json

source "$(dirname "$0")/lib/common.sh"

# Check if alarm is enabled
[ -f ~/.claude/alarm_disabled ] && exit 0
[ "${ALARM_ENABLED:-true}" = "false" ] && exit 0

# Determine sound type from argument (default: done)
SOUND_TYPE="${1:-done}"

case "$SOUND_TYPE" in
    alert)  SOUND_FILE="$SOUND_DIR/$SOUND_ALERT" ;;
    *)      SOUND_FILE="$SOUND_DIR/$SOUND_DONE" ;;
esac

if [ ! -f "$SOUND_FILE" ]; then
    exit 0  # No sound file, silently skip
fi

VOLUME="$ALARM_VOLUME"

# Play in background (non-blocking, hook must return quickly)
if command -v afplay &>/dev/null; then
    # macOS
    afplay -v "$VOLUME" "$SOUND_FILE" &
elif command -v paplay &>/dev/null; then
    # Linux (PulseAudio)
    paplay "$SOUND_FILE" &
elif command -v aplay &>/dev/null; then
    # Linux (ALSA)
    aplay -q "$SOUND_FILE" &
fi

exit 0
