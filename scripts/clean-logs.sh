#!/bin/bash
# Clean old Claude Code Telegram logs
# Usage: ./scripts/clean-logs.sh [days] # Default is 30 days
# Example: ./scripts/clean-logs.sh 7  # Delete logs older than 7 days

DAYS=${1:-30}
LOG_DIR=~/.claude/logs

if [ ! -d "$LOG_DIR" ]; then
    echo "Log directory not found: $LOG_DIR"
    exit 0
fi

echo "Cleaning logs older than $DAYS days in $LOG_DIR"

# Find and delete old log files
count=0
while IFS= read -r file; do
    if [ -n "$file" ]; then
        echo "Deleting: $(basename "$file")"
        rm -f "$file"
        ((count++))
    fi
done < <(find "$LOG_DIR" -name "cc_*.log" -type f -mtime +$DAYS 2>/dev/null)

# Also clean debug.log if older than specified days
if [ -f "$LOG_DIR/debug.log" ]; then
    if [ $(find "$LOG_DIR" -name "debug.log" -mtime +$DAYS 2>/dev/null | wc -l) -gt 0 ]; then
        echo "Deleting: debug.log"
        rm -f "$LOG_DIR/debug.log"
        ((count++))
    fi
fi

echo "Deleted $count file(s)"
