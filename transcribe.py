#!/usr/bin/env python3
"""
Simple Speech Transcriber
Usage: python3 transcribe.py
Configurable key and recording mode - see USER SETTINGS section below
"""

import threading
import time
import logging
import tempfile
import os
import ssl
import certifi
from enum import Enum
import queue
from datetime import datetime
import uuid
import argparse
import sys
import warnings

# Suppress FP16 warning from Whisper
warnings.filterwarnings("ignore", message="FP16 is not supported on CPU; using FP32 instead")

# Fix SSL certificate verification
os.environ['SSL_CERT_FILE'] = certifi.where()
os.environ['REQUESTS_CA_BUNDLE'] = certifi.where()

import urllib.request
ssl_context = ssl.create_default_context(cafile=certifi.where())
https_handler = urllib.request.HTTPSHandler(context=ssl_context)
opener = urllib.request.build_opener(https_handler)
urllib.request.install_opener(opener)

import sounddevice as sd
import whisper
import numpy as np
from scipy.io.wavfile import write
from scipy import signal
from pynput import keyboard
from pynput.keyboard import Key, Listener as KeyboardListener
import noisereduce as nr

# Import user settings
from settings import RECORDING_KEY, PUSH_TO_TALK, MODEL_SIZE

# Ensure ffmpeg is available
if '/opt/homebrew/bin' not in os.environ.get('PATH', ''):
    os.environ['PATH'] = '/opt/homebrew/bin:' + os.environ.get('PATH', '')

# Create logs directory if it doesn't exist
os.makedirs('logs', exist_ok=True)

# Configure logging with file handler
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# Console handler - redirect to stderr to avoid interfering with status display
console_handler = logging.StreamHandler(sys.stderr)
console_handler.setLevel(logging.WARNING)
console_formatter = logging.Formatter('\n%(asctime)s - %(levelname)s - %(message)s')
console_handler.setFormatter(console_formatter)

# Global log filename for session
session_timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
log_filename = os.path.join('logs', f'transcriber_{session_timestamp}.log')

# File handler with session-based naming
file_handler = logging.FileHandler(log_filename)
file_handler.setLevel(logging.DEBUG)
file_formatter = logging.Formatter('%(asctime)s - %(levelname)s - [%(session_id)s] %(message)s')
file_handler.setFormatter(file_formatter)

logger.addHandler(console_handler)
logger.addHandler(file_handler)

# Add session_id to log records
class SessionLoggerAdapter(logging.LoggerAdapter):
    def process(self, msg, kwargs):
        return msg, {**kwargs, 'extra': {**kwargs.get('extra', {}), 'session_id': self.extra.get('session_id', 'GLOBAL')}}

# Create global logger adapter
logger = SessionLoggerAdapter(logger, {'session_id': 'GLOBAL'})

class StatusDisplay:
    def __init__(self):
        self.current_status = "Ready..."
        self.lock = threading.Lock()
        self.last_length = 0
        
    def update(self, status):
        with self.lock:
            # Truncate status if too long to prevent line wrapping
            max_width = 70
            if len(status) > max_width:
                status = status[:max_width-3] + "..."
            
            # Clear previous status completely
            sys.stdout.write('\r' + ' ' * self.last_length + '\r')
            sys.stdout.write(status)
            sys.stdout.flush()
            
            self.last_length = len(status)
            self.current_status = status
    
    def clear_line(self):
        sys.stdout.write('\r' + ' ' * self.last_length + '\r')
        sys.stdout.flush()

# Global status display
status_display = StatusDisplay()

class RecordingSession:
    def __init__(self, session_id, key):
        self.session_id = session_id
        self.key = key
        self.audio_data = []
        self.start_time = time.time()
        self.is_recording = True
        self.stream = None
        self.logger = SessionLoggerAdapter(logger.logger, {'session_id': session_id})
        self.min_duration = 0.5  # Default, will be updated by transcriber
        self.status_update_thread = None

class SpeechTranscriber:
    def __init__(self, model_size=MODEL_SIZE, min_duration=0.5):
        self.recording_sessions = {}  # {session_id: RecordingSession}
        self.session_counter = 0
        self.processing_queue = queue.Queue()
        self._whisper_model = None
        self.model_size = model_size
        self.min_duration = min_duration
        self.keyboard_controller = keyboard.Controller()
        self.sessions_lock = threading.Lock()
        
        # Log audio device info
        try:
            devices = sd.query_devices()
            default_input = sd.query_devices(kind='input')
            logger.info(f"Default input device: {default_input['name']} (index: {default_input['index']})")
            logger.debug(f"Available devices: {[d['name'] for d in devices if d['max_input_channels'] > 0]}")
        except Exception as e:
            logger.error(f"Error querying audio devices: {e}")
        
        # Start processing thread
        self.processing_thread = threading.Thread(target=self._process_queue, daemon=True)
        self.processing_thread.start()
        
        logger.info("Speech transcriber initialized")

    @property
    def whisper_model(self):
        if self._whisper_model is None:
            logger.info(f"Loading Whisper model: {self.model_size}")
            self._whisper_model = whisper.load_model(self.model_size)
            logger.info(f"Whisper model '{self.model_size}' loaded")
        return self._whisper_model

    def start_recording(self, key):
        session_id = str(uuid.uuid4())[:8]  # Short session ID
        
        with self.sessions_lock:
            session = RecordingSession(session_id, key)
            session.min_duration = self.min_duration  # Set the configured min duration
            self.recording_sessions[session_id] = session
            
        session.logger.info(f"Recording started (key: {key})")
        
        # Start status update thread
        def update_recording_status():
            while session.is_recording:
                elapsed = time.time() - session.start_time
                status_display.update(f"🔴 Recording... ({elapsed:.1f}s)")
                time.sleep(0.1)
        
        session.status_update_thread = threading.Thread(target=update_recording_status, daemon=True)
        session.status_update_thread.start()
        
        # Start recording in new thread
        threading.Thread(target=self._record_audio, args=(session,), daemon=True).start()
        
        return session_id

    def finish_recording(self, key):
        """Stop recording and transcribe the audio"""
        sessions_to_finish = []
        
        with self.sessions_lock:
            for session_id, session in list(self.recording_sessions.items()):
                if session.key == key and session.is_recording:
                    sessions_to_finish.append(session_id)
        
        for session_id in sessions_to_finish:
            self._stop_session(session_id)
    
    def cancel_recording(self, key):
        """Cancel recording without transcribing"""
        sessions_to_cancel = []
        
        with self.sessions_lock:
            for session_id, session in list(self.recording_sessions.items()):
                if session.key == key and session.is_recording:
                    sessions_to_cancel.append(session_id)
        
        for session_id in sessions_to_cancel:
            self._cancel_session(session_id)
    
    def _cancel_session(self, session_id):
        """Cancel a session without transcribing"""
        with self.sessions_lock:
            session = self.recording_sessions.get(session_id)
            if not session:
                return
                
            session.is_recording = False
            duration = time.time() - session.start_time
            audio_length = len(session.audio_data)
            
            session.logger.info(f"Recording cancelled (duration: {duration:.2f}s, samples: {audio_length})")
            
            # Remove from active sessions without queuing for processing
            del self.recording_sessions[session_id]

    def _stop_session(self, session_id):
        with self.sessions_lock:
            session = self.recording_sessions.get(session_id)
            if not session:
                return
                
            # Check if we've met minimum duration
            duration = time.time() - session.start_time
            if duration < session.min_duration:
                # Continue recording until minimum duration is met
                remaining = session.min_duration - duration
                session.logger.debug(f"Extending recording by {remaining:.2f}s to meet minimum duration")
                
                # Schedule delayed stop
                threading.Timer(remaining, lambda: self._stop_session(session_id)).start()
                return
                
            session.is_recording = False
            audio_length = len(session.audio_data)
            
            session.logger.info(f"Recording stopped (duration: {duration:.2f}s, samples: {audio_length})")
            
            if audio_length > 0:
                # Queue for processing
                self.processing_queue.put({
                    'session_id': session_id,
                    'audio_data': session.audio_data.copy(),
                    'logger': session.logger
                })
                session.logger.info("Queued for processing")
            else:
                session.logger.warning("No audio data recorded, skipping")
                
            # Remove from active sessions
            del self.recording_sessions[session_id]

    def _record_audio(self, session):
        try:
            # Create and start the stream immediately
            with sd.InputStream(
                samplerate=16000,
                channels=1,
                dtype=np.float32,
                callback=lambda indata, frames, time, status: self._audio_callback(session, indata, status),
                blocksize=1024  # Explicit blocksize
            ) as stream:
                session.stream = stream
                session.logger.debug(f"Audio stream created: {stream.active}")
                
                # Wait for stream to be active
                start_time = time.time()
                while not stream.active and time.time() - start_time < 1.0:
                    time.sleep(0.01)
                
                if not stream.active:
                    session.logger.error("Audio stream failed to activate")
                else:
                    session.logger.debug("Audio stream is active")
                
                while session.is_recording:
                    time.sleep(0.1)
                    
        except Exception as e:
            session.logger.error(f"Recording error: {e}")

    def _audio_callback(self, session, indata, status):
        if status:
            session.logger.warning(f"Audio callback status: {status}")
            
        if session.is_recording and indata is not None:
            audio_chunk = indata.flatten()
            if len(audio_chunk) > 0:
                session.audio_data.extend(audio_chunk)
                # Log first callback to confirm audio is flowing
                if len(session.audio_data) == len(audio_chunk):
                    session.logger.debug(f"First audio chunk received: {len(audio_chunk)} samples")

    def _process_queue(self):
        while True:
            try:
                # Wait for items in queue
                item = self.processing_queue.get(timeout=1)
                self._transcribe_and_type(
                    item['session_id'],
                    item['audio_data'],
                    item['logger']
                )
            except queue.Empty:
                continue
            except Exception as e:
                logger.error(f"Processing queue error: {e}")

    def _transcribe_and_type(self, session_id, audio_data, session_logger):
        try:
            session_logger.info("Starting transcription")
            status_display.update("⏳ Processing...")
            
            # Convert to audio array
            audio_array = np.array(audio_data, dtype=np.float32)
            
            # Audio preprocessing
            session_logger.debug("Applying audio preprocessing")
            
            # 1. Normalize audio to prevent clipping
            max_val = np.max(np.abs(audio_array))
            if max_val > 0:
                audio_array = audio_array / max_val * 0.95
            
            # 2. Apply noise reduction
            try:
                audio_array = nr.reduce_noise(y=audio_array, sr=16000)
                session_logger.debug("Noise reduction applied")
            except Exception as e:
                session_logger.warning(f"Noise reduction failed: {e}")
            
            # 3. Apply high-pass filter to remove low-frequency noise
            nyquist_freq = 16000 / 2
            low_cutoff = 80  # Hz
            normalized_cutoff = low_cutoff / nyquist_freq
            b, a = signal.butter(3, normalized_cutoff, btype='high')
            audio_array = signal.filtfilt(b, a, audio_array)
            session_logger.debug("High-pass filter applied")
            
            with tempfile.NamedTemporaryFile(suffix='.wav', delete=True) as temp_file:
                audio_int16 = (audio_array * 32767).astype(np.int16)
                write(temp_file.name, 16000, audio_int16)
                
                # Log audio file details
                file_size = os.path.getsize(temp_file.name)
                session_logger.debug(f"Audio file size: {file_size} bytes")
                
                # Transcribe
                result = self.whisper_model.transcribe(temp_file.name)
                text = result["text"].strip()
                
                if text:
                    session_logger.info(f"Transcribed: {text}")
                    # Clear status line and print transcription to new line
                    status_display.clear_line()
                    print(f"✅ Transcribed: {text}")
                    self.keyboard_controller.type(text)
                    # After typing, go back to ready state
                    time.sleep(1.5)  # Show the transcription briefly
                    status_display.update("Ready...")
                else:
                    session_logger.info("No text detected (empty recording)")
                    # Clear status line and print message to new line
                    status_display.clear_line()
                    print("❌ No speech detected")
                    time.sleep(1.5)
                    status_display.update("Ready...")
                    
        except Exception as e:
            session_logger.error(f"Transcription error: {e}", exc_info=True)
            status_display.update(f"❌ Error: {str(e)[:50]}")
            time.sleep(2)
            status_display.update("Ready...")
        finally:
            session_logger.info("Processing complete")

def main():
    # Parse command line arguments
    parser = argparse.ArgumentParser(description='Speech Transcriber - Configurable key and recording mode')
    parser.add_argument('--model', 
                       choices=['tiny', 'base', 'small', 'medium', 'large'],
                       default=MODEL_SIZE,
                       help=f'Whisper model size (default: {MODEL_SIZE}). Larger models are more accurate but slower.')
    parser.add_argument('--min-duration', 
                       type=float,
                       default=0.5,
                       help='Minimum recording duration in seconds (default: 0.5)')
    args = parser.parse_args()
    
    print("🎤 Speech Transcriber")
    print(f"Model: {MODEL_SIZE} | Min duration: {args.min_duration}s")
    
    # Show current key and mode
    key_name = str(RECORDING_KEY).replace('Key.', '').replace('_', ' ').title()
    mode_text = "Hold to record, release to transcribe" if PUSH_TO_TALK else "Press once to start, press again to stop"
    print(f"Key: {key_name} | Mode: {mode_text}")
    
    print("Press Ctrl+C to quit")
    print(f"Session log: {log_filename}")
    print("-" * 50)
    
    transcriber = SpeechTranscriber(model_size=MODEL_SIZE, min_duration=args.min_duration)
    active_sessions = {}  # Track which keys have active sessions
    is_recording_active = False  # Track toggle state for non-push-to-talk mode
    
    # Show initial ready status
    status_display.update("Ready...")
    
    def on_key_press(key):
        nonlocal is_recording_active
        
        # Check for ESC cancellation first (works in both toggle and push-to-talk modes)
        if key == Key.esc:
            # Cancel recording if any active session exists
            if active_sessions:
                # Cancel all active sessions
                for recording_key in list(active_sessions.keys()):
                    transcriber.cancel_recording(recording_key)
                    active_sessions.pop(recording_key)
                
                # Reset toggle mode state if applicable
                if not PUSH_TO_TALK:
                    is_recording_active = False
                    
                status_display.update("❌ Recording cancelled")
                time.sleep(1)
                status_display.update("Ready...")
                return
        
        # Check if recording is active for toggle mode logic
        if is_recording_active:
            # Recording key pressed while recording - finish and transcribe
            if key == RECORDING_KEY:
                if RECORDING_KEY in active_sessions:
                    transcriber.finish_recording(RECORDING_KEY)
                    active_sessions.pop(RECORDING_KEY)
                    is_recording_active = False
                return
        
        # Start recording when not currently recording
        if key == RECORDING_KEY:
            if PUSH_TO_TALK:
                # Traditional push-to-talk mode - start recording on key press
                if key not in active_sessions:
                    session_id = transcriber.start_recording(key)
                    active_sessions[key] = session_id
            else:
                # Toggle mode - only start recording (stop is handled above when is_recording_active)
                if not is_recording_active:
                    # Start recording
                    session_id = transcriber.start_recording(key)
                    active_sessions[key] = session_id
                    is_recording_active = True

    def on_key_release(key):
        if PUSH_TO_TALK and key in active_sessions:
            # Only finish on key release in push-to-talk mode (transcribes)
            transcriber.finish_recording(key)
            active_sessions.pop(key)

    listener = KeyboardListener(on_press=on_key_press, on_release=on_key_release)
    listener.start()

    try:
        while True:
            time.sleep(0.1)
    except KeyboardInterrupt:
        print("\n👋 Goodbye!")
        logger.info("Application shutting down")
    finally:
        listener.stop()

if __name__ == "__main__":
    main()