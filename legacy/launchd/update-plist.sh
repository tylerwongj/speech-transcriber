#!/bin/bash

# Update launchd plist script for Speech Transcriber

echo "Updating plist..."

# Change to the script directory
cd "$(dirname "$0")"

# Copy updated plist file
cp com.tyler.speech-transcriber.plist ~/Library/LaunchAgents/

# Unload and reload the service
launchctl unload ~/Library/LaunchAgents/com.tyler.speech-transcriber.plist 2>/dev/null
launchctl load ~/Library/LaunchAgents/com.tyler.speech-transcriber.plist

echo "Done!"