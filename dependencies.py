# backend/dependencies.py
import sys
from pathlib import Path

# IMPORTANT: Ensure the backend directory is on sys.path for local development
# This makes 'core' and other top-level modules importable.
# This workaround is often necessary with uvicorn --reload.
current_file_dir = Path(__file__).resolve().parent
backend_dir = current_file_dir
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from fastapi import Depends, HTTPException
from fastapi.security import OAuth2PasswordBearer
from firebase_admin import auth
from typing import Dict, Any, Optional

from core.db_core import DatabaseManager # Now can import directly
import firebase_admin

# --- DatabaseManager Dependency ---
_db_manager_instance: Optional[DatabaseManager] = None

def get_db_manager() -> DatabaseManager:
    global _db_manager_instance
    if _db_manager_instance is None:
        if not firebase_admin._apps:
            raise RuntimeError("Firebase Admin SDK not initialized. Ensure firebase_admin.initialize_app() is called in main.py first.")
        _db_manager_instance = DatabaseManager()
    return _db_manager_instance

# --- Authentication Dependency ---
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/token") 

async def get_current_user(token: str = Depends(oauth2_scheme)) -> Dict[str, Any]:
    """A dependency that verifies the Firebase ID token on protected endpoints."""
    try:
        decoded_token = auth.verify_id_token(token)
        return decoded_token
    except Exception as e:
        print(f"Auth error in get_current_user: {e}")
        raise HTTPException(
            status_code=401,
            detail="Invalid authentication credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )