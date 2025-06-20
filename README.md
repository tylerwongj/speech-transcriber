# Speech Transcriber

Local speech-to-text for macOS that types transcribed text automatically.

## Features

- **F4 Trigger**: Press F4 to start/stop recording
- **Local Processing**: Uses OpenAI Whisper for 100% local transcription
- **Auto-Type**: Automatically types transcribed text at cursor position
- **Privacy First**: No cloud APIs, all processing happens locally
- **Simple**: Single Python file, minimal dependencies

## Setup

### 1. Install System Dependencies
```bash
brew install ffmpeg
```

### 2. Install Python Dependencies
```bash
pip3 install -r requirements.txt
```

### 3. Grant macOS Permissions

**Critical**: You must grant these permissions or the app won't work:

1. **Microphone Access**:
   - System Preferences → Security & Privacy → Privacy → Microphone
   - Click the lock and enter password
   - Add `/usr/bin/python3` to the list
   - Check the box to enable

2. **Accessibility Access**:
   - System Preferences → Security & Privacy → Privacy → Accessibility
   - Click the lock and enter password
   - Add `/usr/bin/python3` to the list
   - Check the box to enable

### 4. Run the Application
```bash
python3 transcribe.py
```

## Usage

1. Run the application: `python3 transcribe.py`
2. Press **F4** to start recording (you'll see "🎤 Recording started...")
3. Speak clearly into your microphone
4. Press **F4** again to stop recording and start transcription
5. The transcribed text will be automatically typed at your cursor position
6. Press **Ctrl+C** to quit the application

## Troubleshooting

### Silent Audio (max_volume=0.0000)
- **Problem**: App records but audio is silent
- **Solution**: Check microphone permissions for `/usr/bin/python3`

### F4 Key Not Working
- **Problem**: No "Recording started" message when pressing F4
- **Solution**: Check accessibility permissions for `/usr/bin/python3`

### ffmpeg Not Found
- **Problem**: Error about ffmpeg not being found
- **Solution**: Run `brew install ffmpeg`

### Permission Test
To test if microphone permissions are working:
```python
import sounddevice as sd
import numpy as np
recording = sd.rec(44100, samplerate=44100, channels=1)
sd.wait()
max_volume = np.max(np.abs(recording))
print(f"Max volume: {max_volume}")  # Should be > 0.01 if working
```

## Architecture

- **Whisper Model**: Uses "base" model for good balance of speed/accuracy
- **Audio Format**: 16kHz, mono, 32-bit float
- **Threading**: Non-blocking recording and processing
- **Permissions**: Requires microphone + accessibility access

## Notes

- First run will download the Whisper model (~140MB)
- Uses system Python to avoid virtual environment permission issues
- Designed for macOS - permissions and paths are macOS-specific