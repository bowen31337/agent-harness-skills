"""Root conftest — adds project root to sys.path for pytest discovery."""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
