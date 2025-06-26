#!/bin/bash
cd /Users/tyler/p2/speech-transcriber
source venv/bin/activate
nohup python3 transcribe.py > /dev/null 2>&1 &