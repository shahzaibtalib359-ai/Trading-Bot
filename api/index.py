import os
import sys
from pathlib import Path

# Add root directory to sys.path so backend imports work correctly
ROOT = Path(__file__).resolve().parent.parent
sys.path.append(str(ROOT))

# Import the FastAPI app
from backend.main import app

# Vercel Serverless Function expects the handler to be named 'app'
# which we just imported directly
