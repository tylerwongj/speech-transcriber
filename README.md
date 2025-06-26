# Speech Transcriber

Local speech-to-text for macOS that types transcribed text automatically.

## Features

- **Ctrl+Space Trigger**: Press Ctrl+Space to start/stop recording
- **Local Processing**: Uses OpenAI Whisper for 100% local transcription
- **Auto-Type**: Automatically types transcribed text at cursor position
- **Privacy First**: No cloud APIs, all processing happens locally
- **Simple**: Single Python file, minimal dependencies

## Quick Setup

### Automated Setup (Recommended)
```bash
chmod +x init.sh
./init.sh
```

The `init.sh` script will:
- Install system dependencies (Homebrew, ffmpeg)
- Create a Python virtual environment
- Install all Python dependencies
- **Pre-download the Whisper model (~140MB)**
- Create a permission checker script
- Guide you through setting up macOS permissions

### Manual Setup

1. **Install System Dependencies**
```bash
brew install ffmpeg
```

2. **Setup Python Environment**
```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

3. **Pre-download Whisper Model** (Optional but recommended)
```bash
python3 -c "import whisper; whisper.load_model('base')"
```
This downloads ~140MB and prevents delays on first use.

4. **Grant macOS Permissions** (Critical!)

You MUST grant these permissions:

**Microphone Access:**
- System Preferences → Security & Privacy → Privacy → Microphone
- Add both: `/usr/bin/python3` AND `[project-path]/venv/bin/python3`
- Check ✅ both boxes

**Accessibility Access:**
- System Preferences → Security & Privacy → Privacy → Accessibility  
- Add: `/usr/bin/python3`, `[project-path]/venv/bin/python3`, and your Terminal app
- Check ✅ all boxes

5. **Test Permissions**
```bash
source venv/bin/activate
python3 check_permissions.py
```

6. **Run the Application**
```bash
source venv/bin/activate
python3 transcribe.py
```

## Usage

1. **Activate environment**: `source venv/bin/activate`
2. **Run the app**: `python3 transcribe.py`
3. **Record**: Press **Ctrl+Space** to start recording (you'll see "🎤 Recording started...")
4. **Speak clearly** into your microphone
5. **Stop**: Press **Ctrl+Space** again to stop recording and start transcription
6. **Auto-type**: The transcribed text will be automatically typed at your cursor position
7. **Quit**: Press **Ctrl+C** to quit the application

### Pro Tip: Create an Alias
Add to your `~/.zshrc` or `~/.bash_profile`:
```bash
alias transcribe='cd /path/to/speech-transcriber3 && source venv/bin/activate && python3 transcribe.py'
```

## Auto-Start on Login (Recommended)

For the best experience, set up the speech transcriber to automatically start when you log into your Mac.

### Setup Auto-Start

The project includes a `start-on-login.sh` script that launches the transcriber in the background:

```bash
#!/bin/bash
cd /Users/tyler/p2/speech-transcriber
source venv/bin/activate
nohup python3 transcribe.py > /dev/null 2>&1 &
```

**To enable auto-start:**

1. **Test the script first** (make sure it works):
   ```bash
   ./start-on-login.sh
   ```

2. **Add to Login Items**:
   - Open **System Preferences** → **Users & Groups**
   - Click your username
   - Click **"Login Items"** tab
   - Click the **"+"** button
   - Navigate to and select: `/path/to/your/speech-transcriber/start-on-login.sh`
   - Click **"Add"**

3. **Done!** The transcriber will now automatically start every time you log in

### Benefits of Auto-Start
- ✅ Always available - no manual startup needed
- ✅ Runs silently in background
- ✅ Survives computer restarts
- ✅ Uses same permissions as manual setup

### Manual Start Alternative
If you prefer to start manually when needed:
```bash
cd /path/to/speech-transcriber && source venv/bin/activate && nohup python3 transcribe.py &
```

## Troubleshooting

### Use the Permission Checker
First, always run the permission checker:
```bash
source venv/bin/activate
python3 check_permissions.py
```

### Common Issues

**Silent Audio (max_volume=0.0000)**
- Check microphone permissions for both Python executables
- Test with: `python3 check_permissions.py`

**Ctrl+Space Not Working** 
- Add Terminal app to Accessibility permissions
- Add both Python executables to Accessibility permissions

**SSL Certificate Error**
- Fixed automatically in the updated code
- Uses `certifi` for proper certificate handling

**Module Not Found Errors**
- Always activate the virtual environment first: `source venv/bin/activate`
- Reinstall if needed: `pip install -r requirements.txt`

**"Not Trusted" Error**
- Add your Terminal app to Accessibility permissions
- Restart Terminal after granting permissions

**Auto-Start Not Working**
- Verify the script is executable: `chmod +x start-on-login.sh`
- Test the script manually: `./start-on-login.sh`
- Check Login Items in System Preferences → Users & Groups
- Make sure the full path to the script is correct in Login Items

**Multiple Instances Running**
- Check running processes: `ps aux | grep transcribe.py`
- Kill extra processes: `pkill -f transcribe.py`
- The auto-start script uses `nohup` so it runs in background

## Architecture

- **Whisper Model**: Uses "base" model for good balance of speed/accuracy
- **Audio Format**: 16kHz, mono, 32-bit float
- **Threading**: Non-blocking recording and processing
- **Permissions**: Requires microphone + accessibility access

## File Structure

```
speech-transcriber/
├── transcribe.py           # Main application
├── start.sh               # Manual start script
├── start-on-login.sh      # Auto-start script for Login Items
├── init.sh                # Automated setup script
├── check_permissions.py   # Permission verification tool
├── requirements.txt       # Python dependencies
├── venv/                  # Python virtual environment
├── logs/                  # Application logs
└── legacy/                # Legacy files (not needed for normal use)
    └── launchd/          # Old LaunchAgent approach files
        ├── com.tyler.speech-transcriber.plist
        ├── update-plist.sh
        ├── launchd.error
        └── launchd.log
```

## Scripts Reference

### `start-on-login.sh` (Recommended)
Auto-starts transcriber in background when you log in. Add to Login Items for best experience.

### `start.sh` 
Simple manual start script:
```bash
#!/bin/bash
cd /Users/tyler/p2/speech-transcriber
source venv/bin/activate && python3 transcribe.py
```

### `init.sh`
One-time setup script that installs dependencies and sets up the environment.

### Legacy Files
The `legacy/launchd/` folder contains files from a previous LaunchAgent setup approach. These files are kept for reference but are not needed for normal operation. The Login Items approach is much simpler and more reliable.

## Important Notes

- **First-time setup**: The `init.sh` script pre-downloads the Whisper model (~140MB) to avoid delays
- **Manual setup**: If you skip the automated setup, the first recording will trigger a ~140MB download
- **Virtual environment**: Always activate with `source venv/bin/activate` before running
- **macOS specific**: Permissions and paths are designed for macOS only
- **Auto-start recommended**: Use `start-on-login.sh` + Login Items for the best experience