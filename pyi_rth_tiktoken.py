# PyInstaller runtime hook for tiktoken
# Sets TIKTOKEN_CACHE_DIR to bundled cache files
import os
import sys

if getattr(sys, 'frozen', False):
    # Running as PyInstaller executable
    cache_dir = os.path.join(sys._MEIPASS, 'tiktoken_cache')
    os.environ['TIKTOKEN_CACHE_DIR'] = cache_dir
