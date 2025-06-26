#!/bin/bash

echo "🛑 Stopping speech transcriber..."

# Find transcriber processes more specifically
PIDS=$(ps aux | grep -E "(transcribe\.py|speech_transcriber\.py)" | grep -v grep | awk '{print $2}')

if [ -z "$PIDS" ]; then
    echo "❌ No running transcriber found"
else
    echo "🔍 Found transcriber process(es): $PIDS"
    
    # Show what we're about to kill
    echo "📋 Processes to stop:"
    ps aux | grep -E "(transcribe\.py|speech_transcriber\.py)" | grep -v grep
    
    # Kill each process
    for PID in $PIDS; do
        echo "🔨 Killing process $PID"
        kill $PID 2>/dev/null
    done
    
    # Wait a moment and check if processes are really stopped
    sleep 2
    REMAINING=$(ps aux | grep -E "(transcribe\.py|speech_transcriber\.py)" | grep -v grep | awk '{print $2}')
    
    if [ -z "$REMAINING" ]; then
        echo "✅ All transcriber processes stopped successfully"
    else
        echo "⚠️  Force killing remaining processes..."
        for PID in $REMAINING; do
            echo "💀 Force killing process $PID"
            kill -9 $PID 2>/dev/null
        done
        echo "✅ All transcriber processes forcefully stopped"
    fi
fi