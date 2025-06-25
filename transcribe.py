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
from pynput import keyboard
from pynput.keyboard import Key, Listener as KeyboardListener

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Ensure ffmpeg is available
if '/opt/homebrew/bin' not in os.environ.get('PATH', ''):
    os.environ['PATH'] = '/opt/homebrew/bin:' + os.environ.get('PATH', '')

class State(Enum):
    IDLE = "idle"
    RECORDING = "recording"
    PROCESSING = "processing"

class SpeechTranscriber:
    def __init__(self):
        self.state = State.IDLE
        self.audio_data = []
        self.is_recording = False
        self._whisper_model = None
        self.keyboard_controller = keyboard.Controller()
        self.push_to_talk_active = False
        self.processing_threads = []
        self.state_lock = threading.Lock()

    @property
    def whisper_model(self):
        if self._whisper_model is None:
            logger.info("Loading Whisper model...")
            self._whisper_model = whisper.load_model("base")
        return self._whisper_model

    def push_to_talk_start(self):
        # Allow starting new recording immediately
        if not self.push_to_talk_active:
            self.push_to_talk_active = True
            self.start_recording()
    
    def push_to_talk_stop(self):
        if self.state == State.RECORDING and self.push_to_talk_active:
            self.push_to_talk_active = False
            self.stop_recording()

    def start_recording(self):
        # Always allow starting a new recording
        with self.state_lock:
            # Reset for new recording
            self.state = State.RECORDING
            self.audio_data = []
            self.is_recording = True
        threading.Thread(target=self._record_audio, daemon=True).start()
        logger.info("🎤 Recording started...")

    def stop_recording(self):
        with self.state_lock:
            if self.state != State.RECORDING:
                return

            self.is_recording = False
            if not self.audio_data:
                self.state = State.IDLE
                return

            # Copy audio data for processing
            audio_to_process = self.audio_data.copy()
            self.state = State.IDLE  # Immediately go to IDLE to allow new recordings

        logger.info("🔄 Processing...")
        # Start processing in a new thread with the copied audio data
        process_thread = threading.Thread(target=self._transcribe_and_type, args=(audio_to_process,), daemon=True)
        process_thread.start()
        self.processing_threads.append(process_thread)

    def _record_audio(self):
        with sd.InputStream(samplerate=16000, channels=1, dtype=np.float32,
                           callback=self._audio_callback) as stream:
            while self.is_recording:
                time.sleep(0.1)

    def _audio_callback(self, indata, frames, time, status):
        if self.is_recording:
            self.audio_data.extend(indata.flatten())

    def _transcribe_and_type(self, audio_data):
        try:
            # Convert to audio file
            audio_array = np.array(audio_data, dtype=np.float32)
            with tempfile.NamedTemporaryFile(suffix='.wav', delete=True) as temp_file:
                audio_int16 = (audio_array * 32767).astype(np.int16)
                write(temp_file.name, 16000, audio_int16)

                # Transcribe
                result = self.whisper_model.transcribe(temp_file.name)
                text = result["text"].strip()

                if text:
                    logger.info(f"✅ Transcribed: {text}")
                    self.keyboard_controller.type(text)
                else:
                    logger.warning("❌ No text detected")

        except Exception as e:
            logger.error(f"❌ Error: {e}")

        finally:
            logger.info("Processing complete")

def main():
    print("🎤 Speech Transcriber")
    print("Hold Right Option key to record, release to transcribe")
    print("Press Ctrl+C to quit")

    transcriber = SpeechTranscriber()
    
    # Track which key is being used for push-to-talk
    active_ptt_key = None

    def on_key_press(key):
        nonlocal active_ptt_key
        
        # Only start recording if no key is currently active
        if active_ptt_key is None:
            # Use Right Option/Alt key
            if key == Key.alt_r:
                active_ptt_key = key
                transcriber.push_to_talk_start()
                logger.info("⌥ Right Option key detected")

    def on_key_release(key):
        nonlocal active_ptt_key
        
        # Only stop if this is the key that started recording
        if active_ptt_key is not None:
            if (hasattr(key, 'vk') and hasattr(active_ptt_key, 'vk') and key.vk == active_ptt_key.vk) or \
               (key == active_ptt_key):
                transcriber.push_to_talk_stop()
                active_ptt_key = None

    listener = KeyboardListener(on_press=on_key_press, on_release=on_key_release)
    listener.start()

    try:
        while True:
            time.sleep(0.1)
    except KeyboardInterrupt:
        print("\n👋 Goodbye!")
    finally:
        listener.stop()

if __name__ == "__main__":
    main()