#!/usr/bin/env python3
"""
Simple Speech Transcriber
Usage: python3 transcribe.py
Hold Right Option key to record, release to transcribe
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
from logging.handlers import TimedRotatingFileHandler
import uuid
import argparse
import sys

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

# Ensure ffmpeg is available
if '/opt/homebrew/bin' not in os.environ.get('PATH', ''):
    os.environ['PATH'] = '/opt/homebrew/bin:' + os.environ.get('PATH', '')

# Create logs directory if it doesn't exist
os.makedirs('logs', exist_ok=True)

# Configure logging with file handler
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# Console handler - only show warnings and errors to avoid interfering with status display
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.WARNING)
console_formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
console_handler.setFormatter(console_formatter)

# File handler with daily rotation
log_filename = os.path.join('logs', f'transcriber_{datetime.now().strftime("%Y-%m-%d")}.log')
file_handler = TimedRotatingFileHandler(
    filename=log_filename,
    when='midnight',
    interval=1,
    backupCount=7  # Keep 7 days of logs
)
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
        
    def update(self, status):
        with self.lock:
            # Clear the current line and update status
            sys.stdout.write('\r' + ' ' * 80 + '\r')  # Clear line
            sys.stdout.write(status)
            sys.stdout.flush()
            self.current_status = status
    
    def clear_line(self):
        sys.stdout.write('\r' + ' ' * 80 + '\r')
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
        self.min_duration = 0.5  # Minimum recording duration in seconds
        self.status_update_thread = None

class SpeechTranscriber:
    def __init__(self, model_size='small'):
        self.recording_sessions = {}  # {session_id: RecordingSession}
        self.session_counter = 0
        self.processing_queue = queue.Queue()
        self._whisper_model = None
        self.model_size = model_size
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

    def stop_recording(self, key):
        sessions_to_stop = []
        
        with self.sessions_lock:
            for session_id, session in list(self.recording_sessions.items()):
                if session.key == key and session.is_recording:
                    sessions_to_stop.append(session_id)
        
        for session_id in sessions_to_stop:
            self._stop_session(session_id)

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
                    status_display.update(f"✅ Transcribed: {text}")
                    self.keyboard_controller.type(text)
                    # After typing, go back to ready state
                    time.sleep(1.5)  # Show the transcription briefly
                    status_display.update("Ready...")
                else:
                    session_logger.info("No text detected (empty recording)")
                    status_display.update("❌ No speech detected")
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
    parser = argparse.ArgumentParser(description='Speech Transcriber - Hold Right Option key to record, release to transcribe')
    parser.add_argument('--model', 
                       choices=['tiny', 'base', 'small', 'medium', 'large'],
                       default='small',
                       help='Whisper model size (default: small). Larger models are more accurate but slower.')
    args = parser.parse_args()
    
    print("🎤 Speech Transcriber")
    print(f"Using Whisper model: {args.model}")
    print("Hold Right Option key to record, release to transcribe")
    print("Press Ctrl+C to quit")
    print(f"Logs are saved to: logs/")
    print("-" * 50)
    
    transcriber = SpeechTranscriber(model_size=args.model)
    active_sessions = {}  # Track which keys have active sessions
    
    # Show initial ready status
    status_display.update("Ready...")
    
    def on_key_press(key):
        # Use Right Option/Alt key
        if key == Key.alt_r and key not in active_sessions:
            session_id = transcriber.start_recording(key)
            active_sessions[key] = session_id
            logger.info(f"⌥ Right Option key pressed (session: {session_id})")

    def on_key_release(key):
        if key in active_sessions:
            session_id = active_sessions.pop(key)
            transcriber.stop_recording(key)
            logger.info(f"⌥ Right Option key released (session: {session_id})")

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