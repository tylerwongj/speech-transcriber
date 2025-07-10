"""
Speech Transcriber Settings
Modify these values to customize the behavior of the speech transcriber.
"""

from pynput.keyboard import Key

# =============================================================================
# USER SETTINGS - Modify these to customize behavior
# =============================================================================

# Recording key - choose from common options:
# Key.alt_r        - Right Option/Alt key (default)
# Key.f1           - F1 function key
# Key.caps_lock    - Caps Lock key
# Key.cmd          - Left Command key (Mac) / Windows key
# Key.cmd_r        - Right Command key (Mac)
# Key.ctrl         - Left Control key
# Key.tab          - Tab key
# Key.space        - Space bar
RECORDING_KEY = Key.alt_r

# Recording mode:
# True  = Push-to-talk (hold key to record, release to transcribe)
# False = Toggle mode (press once to start, press again to stop)
PUSH_TO_TALK = True

# Whisper model size - affects accuracy vs speed:
# 'tiny'   - Fastest, least accurate, smallest download
# 'base'   - Good balance of speed and accuracy
# 'small'  - More accurate than base, slower (recommended since base not accurate enough)
# 'medium' - Very accurate, noticeably slower
# 'large'  - Most accurate, slowest
MODEL_SIZE = 'small'

# =============================================================================