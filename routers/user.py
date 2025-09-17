# backend/routers/user.py
import sys
from pathlib import Path

# IMPORTANT: Ensure the 'backend' directory is on sys.path for local development
# This makes 'core' and 'dependencies' importable from this router.
current_file_dir = Path(__file__).resolve().parent
backend_dir = current_file_dir.parent # Go up one level from 'routers' to 'backend'
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import Dict, Any, Optional

from core.db_core import DatabaseManager # Import the class for type hinting
from dependencies import get_db_manager, get_current_user # CRITICAL: Import from dependencies (now relative)

router = APIRouter()

class ResumeDetailsUpdateRequest(BaseModel):
    parsed_data: Dict[str, Any]
    file_name: Optional[str] = "EditedResume.txt"

@router.get("/profile")
async def get_user_profile(
    user: dict = Depends(get_current_user),
    db: DatabaseManager = Depends(get_db_manager)
) -> Dict[str, Any]:
    try:
        uid = user['uid']
        
        resume_data = db.fetch_resume_relational(user_uid=uid, get_optimized=False)
        
        profile_response = {
            "uid": uid,
            "name": user.get("name") or (resume_data.get('personal_info', {}).get('name') if resume_data else None),
            "email": user.get("email") or (resume_data.get('personal_info', {}).get('email') if resume_data else None),
            "phone": resume_data.get('personal_info', {}).get('phone') if resume_data else None,
            "linkedin": resume_data.get('personal_info', {}).get('linkedin') if resume_data else None,
            "github": resume_data.get('personal_info', {}).get('github') if resume_data else None,
            "resume_content": resume_data or {}
        }
        
        return profile_response

    except Exception as e:
        print(f"Error fetching user profile or resume for UID {user.get('uid', 'N/A')}: {e}")
        raise HTTPException(status_code=500, detail=f"An internal server error occurred: {str(e)}")

# --- THIS IS THE CORRECTED ENDPOINT ---
@router.put("/profile/resume-details")
async def update_user_resume_details(
    request: ResumeDetailsUpdateRequest,
    user: dict = Depends(get_current_user),
    db: DatabaseManager = Depends(get_db_manager)
):
    """
    Receives structured resume data and updates it in the database.
    """
    uid = user['uid']
    try:
        # Get the main data dictionary from the request
        data_to_save = request.parsed_data

        # --- THE FIX ---
        # Before sending to the DB, we ensure the metadata field exists
        # and insert the file_name into it.
        if 'resume_metadata' not in data_to_save or data_to_save['resume_metadata'] is None:
            data_to_save['resume_metadata'] = {}
        
        data_to_save['resume_metadata']['file_name'] = request.file_name
        # --- END FIX ---

        # Now we call the database function with the correctly structured data.
        # It only expects uid and the data dictionary.
        success = db.update_resume_relational(uid, data_to_save)
        
        if not success:
            raise HTTPException(status_code=500, detail="Failed to update resume details in the database.")
        
        return {"message": "Resume details updated successfully."}

    except Exception as e:
        print(f"Error updating resume details for user {uid}: {e}")
        raise HTTPException(status_code=500, detail=f"An internal server error occurred: {str(e)}")


# NEW ENDPOINT: Get user-specific statistics
@router.get("/stats", response_model=Dict[str, int])
async def get_user_stats(
    user: Dict[str, Any] = Depends(get_current_user),
    db: DatabaseManager = Depends(get_db_manager)
):
    """Fetches dynamic statistics for the authenticated user."""
    uid = user['uid']
    user_doc = db.db.collection('users').document(uid).get()

    if not user_doc.exists:
        raise HTTPException(status_code=404, detail="User profile not found.")
    
    user_data = user_doc.to_dict()
    # Safely get stats, defaulting to 0 if not present
    stats = user_data.get('stats', {
        'roadmaps_generated': 0,
        'resumes_optimized': 0,
        'assessments_taken': 0,
        'jobs_matched': 0
    })

    return stats