#!/bin/bash

# init.sh - Complete setup script for Speech Transcriber
# This script sets up everything needed to run the speech transcriber

set -e  # Exit on any error

echo "🧶 Speech Transcriber Setup (init.sh)"
echo "======================================"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

print_step() {
    echo -e "${BLUE}📋 $1${NC}"
}

print_success() {
    echo -e "${GREEN}✅ $1${NC}"
}

print_warning() {
    echo -e "${YELLOW}⚠️  $1${NC}"
}

print_error() {
    echo -e "${RED}❌ $1${NC}"
}

# Check if running on macOS
if [[ "$OSTYPE" != "darwin"* ]]; then
    print_error "This script is designed for macOS only"
    exit 1
fi

print_step "Checking system dependencies..."

# Check for Homebrew
if ! command -v brew &> /dev/null; then
    print_warning "Homebrew not found. Installing Homebrew..."
    /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
else
    print_success "Homebrew is installed"
fi

# Check for ffmpeg
if ! command -v ffmpeg &> /dev/null; then
    print_step "Installing ffmpeg..."
    brew install ffmpeg
else
    print_success "ffmpeg is installed"
fi

# Check for Python 3
if ! command -v python3 &> /dev/null; then
    print_error "Python 3 is required but not installed"
    print_warning "Please install Python 3: brew install python"
    exit 1
else
    PYTHON_VERSION=$(python3 --version 2>&1)
    print_success "Python is installed: $PYTHON_VERSION"
fi

print_step "Setting up Python virtual environment..."

# Create virtual environment if it doesn't exist
if [ ! -d "venv" ]; then
    python3 -m venv venv
    print_success "Virtual environment created"
else
    print_success "Virtual environment already exists"
fi

# Activate virtual environment and install dependencies
print_step "Installing Python dependencies..."
source venv/bin/activate

# Upgrade pip first
pip install --upgrade pip

# Install requirements
pip install -r requirements.txt

print_success "Python dependencies installed"

print_step "Testing installation..."

# Test imports
python3 -c "
import ssl
import certifi
import sounddevice as sd
import whisper
import numpy as np
from pynput import keyboard
print('✅ All Python modules imported successfully')
"

print_success "Installation test passed"

print_step "Pre-downloading Whisper model (this may take a few minutes)..."
print_warning "Downloading ~140MB Whisper 'base' model - please be patient..."

# Pre-download the whisper model
python3 -c "
import whisper
print('Downloading Whisper base model...')
model = whisper.load_model('base')
print('✅ Whisper model downloaded and cached!')
"

print_success "Whisper model ready!"

echo
echo "🎯 PERMISSIONS REQUIRED"
echo "======================"
print_warning "You MUST grant these macOS permissions or the app won't work:"
echo

# Get the current Python path
PYTHON_PATH=$(which python3)
VENV_PYTHON_PATH="$(pwd)/venv/bin/python3"

echo "1. 🎤 MICROPHONE ACCESS:"
echo "   • System Preferences → Security & Privacy → Privacy → Microphone"
echo "   • Click the lock 🔒 and enter your password"
echo "   • Add these Python executables:"
echo "     - $PYTHON_PATH"
echo "     - $VENV_PYTHON_PATH"
echo "   • Check ✅ both boxes to enable"
echo

echo "2. ♿ ACCESSIBILITY ACCESS:"
echo "   • System Preferences → Security & Privacy → Privacy → Accessibility"
echo "   • Click the lock 🔒 and enter your password"
echo "   • Add these items:"
echo "     - $PYTHON_PATH"
echo "     - $VENV_PYTHON_PATH"
echo "     - Your Terminal app (Terminal.app or iTerm.app)"
echo "   • Check ✅ all boxes to enable"
echo

echo "3. 🔒 FULL DISK ACCESS (if needed):"
echo "   • System Preferences → Security & Privacy → Privacy → Full Disk Access"
echo "   • Add your Terminal app if prompted"
echo

print_step "Creating permission checker script..."

cat > check_permissions.py << 'EOF'
#!/usr/bin/env python3
"""
Permission checker for Speech Transcriber
"""

import sounddevice as sd
import numpy as np
from pynput import keyboard
import time

def check_microphone():
    print("🎤 Testing microphone access...")
    try:
        # Record 1 second of audio
        recording = sd.rec(44100, samplerate=44100, channels=1, dtype=np.float32)
        sd.wait()
        max_volume = np.max(np.abs(recording))
        
        if max_volume > 0.001:
            print(f"✅ Microphone working! Max volume: {max_volume:.4f}")
            return True
        else:
            print(f"❌ Microphone silent! Max volume: {max_volume:.4f}")
            print("   → Check microphone permissions in System Preferences")
            return False
    except Exception as e:
        print(f"❌ Microphone error: {e}")
        return False

def check_keyboard():
    print("⌨️  Testing keyboard access...")
    try:
        controller = keyboard.Controller()
        # Don't actually type anything, just test the controller creation
        print("✅ Keyboard controller created successfully")
        
        # Test key listener (this will fail without accessibility permissions)
        def on_press(key):
            pass
        
        def on_release(key):
            pass
            
        listener = keyboard.Listener(on_press=on_press, on_release=on_release)
        listener.start()
        time.sleep(0.1)
        listener.stop()
        
        print("✅ Keyboard listener working!")
        return True
    except Exception as e:
        print(f"❌ Keyboard error: {e}")
        if "not trusted" in str(e).lower():
            print("   → Add Python/Terminal to Accessibility permissions")
        return False

def main():
    print("🔍 Speech Transcriber Permission Checker")
    print("=" * 40)
    
    mic_ok = check_microphone()
    kbd_ok = check_keyboard()
    
    print("\n📊 RESULTS:")
    print(f"Microphone: {'✅ OK' if mic_ok else '❌ NEEDS PERMISSION'}")
    print(f"Keyboard:   {'✅ OK' if kbd_ok else '❌ NEEDS PERMISSION'}")
    
    if mic_ok and kbd_ok:
        print("\n🎉 All permissions are working! You can run the transcriber.")
    else:
        print("\n⚠️  Some permissions need to be fixed.")
        print("Run this script again after granting permissions.")

if __name__ == "__main__":
    main()
EOF

chmod +x check_permissions.py
print_success "Permission checker created: check_permissions.py"

echo
echo "🚀 NEXT STEPS"
echo "============="
echo "1. Grant the permissions listed above"
echo "2. Test permissions: source venv/bin/activate && python3 check_permissions.py"
echo "3. Run the app: source venv/bin/activate && python3 transcribe.py"
echo
echo "💡 TIP: Create an alias in your ~/.zshrc or ~/.bash_profile:"
echo "alias transcribe='cd $(pwd) && source venv/bin/activate && python3 transcribe.py'"
echo

print_success "Setup complete! 🎉"
echo
print_warning "Remember to grant the required permissions before running the app!"