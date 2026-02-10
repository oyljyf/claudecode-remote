#!/bin/bash
# Claude Code Stop hook - plays alarm sound when Claude stops
# Alerts user when Claude finishes a task or needs input
# Install: copy to ~/.claude/hooks/ and add to ~/.claude/settings.json

source "$(dirname "$0")/lib/common.sh"

# Check if alarm is enabled
[ -f ~/.claude/alarm_disabled ] && exit 0
[ "${ALARM_ENABLED:-true}" = "false" ] && exit 0

SOUND_DIR=~/.claude/sounds
VOLUME="${ALARM_VOLUME:-0.5}"

# Find sound file
SOUND_FILE="$SOUND_DIR/alarm.mp3"
if [ ! -f "$SOUND_FILE" ]; then
    exit 0  # No sound file, silently skip
fi

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
