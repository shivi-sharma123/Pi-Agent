"""
conftest.py for dashboard tests.
Adds the dashboard directory to sys.path so that `from api.xxx import` works.
"""
import sys
import os

# The dashboard directory must be on the path for 'from api...' imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
