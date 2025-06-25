#!/usr/bin/env python3
"""Test script to detect Globe/Fn key presses"""

from pynput import keyboard
import sys

print("Globe/Fn Key Detection Test")
print("Press various keys to see what's detected")
print("Press ESC to exit")
print("-" * 40)

def on_press(key):
    try:
        if hasattr(key, 'char'):
            print(f"Pressed: {key.char}")
        else:
            print(f"Special key pressed: {key}")
            if key == keyboard.Key.esc:
                return False
    except Exception as e:
        print(f"Error: {e}")

def on_release(key):
    try:
        if hasattr(key, 'char'):
            print(f"Released: {key.char}")
        else:
            print(f"Special key released: {key}")
    except Exception as e:
        print(f"Error: {e}")

with keyboard.Listener(on_press=on_press, on_release=on_release) as listener:
    listener.join()

print("\nTest complete!")