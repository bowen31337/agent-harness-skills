"""Root conftest — adds project root to sys.path for pytest discovery."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
