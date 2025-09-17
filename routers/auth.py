# backend/routers/auth.py
import sys
from pathlib import Path

# IMPORTANT: Ensure the 'backend' directory is on sys.path for local development
# This makes 'core' and 'dependencies' importable from this router.
current_file_dir = Path(__file__).resolve().parent
backend_dir = current_file_dir.parent # Go up one level from 'routers' to 'backend'
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, EmailStr
import firebase_admin
from firebase_admin import auth, firestore
from fastapi import Header
from typing import Optional, Dict, Any

from core.db_core import DatabaseManager # Import the class for type hinting
from dependencies import get_db_manager, get_current_user # CRITICAL: Import from dependencies (now relative)

router = APIRouter()

class UserLogin(BaseModel):
    id_token: str

class UserCreate(BaseModel):
    email: EmailStr
    password: str
    name: str
    phone: Optional[str] = None
    linkedin: Optional[str] = None
    github: Optional[str] = None

class UserEmailLogin(BaseModel):
    email: EmailStr
    password: str

@router.post("/signup")
async def signup_with_email(user_data: UserCreate, db: DatabaseManager = Depends(get_db_manager)):
    """Handles new user registration with email and password."""
    try:
        user = auth.create_user(
            email=user_data.email,
            password=user_data.password,
            display_name=user_data.name
        )
        uid = user.uid
        print(f"Successfully created new user: {user_data.name} ({uid})")

        users_ref = db.db.collection('users')
        users_ref.document(uid).set({
            'uid': uid,
            'email': user_data.email,
            'name': user_data.name,
            'phone': user_data.phone,
            'linkedin': user_data.linkedin,
            'github': user_data.github,
            'resume': {
                'file_name': None,
                'summary': None,
                'optimized_summary': None
            },
            'createdAt': firestore.SERVER_TIMESTAMP
        })
        print(f"User profile created in Firestore for {uid}")

        return {"status": "success", "uid": uid, "message": "User created successfully."}
    
    except auth.EmailAlreadyExistsError:
        raise HTTPException(status_code=400, detail="An account with this email already exists.")
    except Exception as e:
        print(f"An error occurred during signup: {e}")
        raise HTTPException(status_code=500, detail="An internal server error occurred.")

@router.post("/login")
async def login_with_google(user_data: UserLogin, db: DatabaseManager = Depends(get_db_manager)):
    try:
        decoded_token = auth.verify_id_token(user_data.id_token)
        uid = decoded_token['uid']
        email = decoded_token.get('email')
        name = decoded_token.get('name', 'Anonymous')

        users_ref = db.db.collection('users')
        user_doc = users_ref.document(uid).get()

        if not user_doc.exists:
            users_ref.document(uid).set({
                'uid': uid,
                'email': email,
                'name': name,
                'phone': None,
                'linkedin': None,
                'github': None,
                'resume': {
                    'file_name': None,
                    'summary': None,
                    'optimized_summary': None
                },
                'createdAt': firestore.SERVER_TIMESTAMP
            })
            print(f"New user created in Firestore via Google: {name} ({uid})")
        else:
            print(f"User already exists: {name} ({uid})")

        return {"status": "success", "uid": uid}

    except auth.InvalidIdTokenError:
        raise HTTPException(status_code=401, detail="Invalid Firebase ID token.")
    except Exception as e:
        print(f"An error occurred during login: {e}")
        raise HTTPException(status_code=500, detail="An internal server error occurred.")