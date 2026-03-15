"""Vercel serverless entry point — exposes the Dash app as a WSGI application."""
import sys
import os

# Add project root to Python path so mideast_dashboard can be imported
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from mideast_dashboard import server as app
