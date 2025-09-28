#!/usr/bin/env python3
"""
Environment Loader Utility
=========================

Utility to ensure .env is loaded properly in all test scripts.
Import this before any src imports.

Usage:
    from env_loader import ensure_env_loaded
    ensure_env_loaded()
"""

import os
from dotenv import load_dotenv

def ensure_env_loaded():
    """Ensures .env file is loaded"""
    
    # Check if already loaded
    if os.getenv('USE_REDIS_CACHE') is not None:
        print("Environment already loaded")
        return True
    
    # Try to load .env
    env_paths = ['.env', '../.env', '../../.env']
    
    for path in env_paths:
        if os.path.exists(path):
            print(f"Loading environment from: {path}")
            load_dotenv(path)
            
            # Verify loading
            if os.getenv('USE_REDIS_CACHE') is not None:
                print("Environment loaded successfully")
                return True
    
    print("Could not load .env file")
    return False

if __name__ == "__main__":
    ensure_env_loaded()
