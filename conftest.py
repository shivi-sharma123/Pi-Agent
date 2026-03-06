"""
Root conftest.py — unified test discovery configuration.

This file makes the project root the pytest rootdir so that all tests
across `shared/`, `agents/`, `dashboard/` can be discovered from one command:

    pytest shared/ agents/ dashboard/ -v

Service tests (analytics-worker, notification-worker, search-service) must
still be run from their own directory since they use app-relative imports.
"""
import sys
import os

# Ensure the project root is always on sys.path
sys.path.insert(0, os.path.dirname(__file__))
