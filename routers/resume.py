import sys
from pathlib import Path as PathlibPath 
import os
import io 
import json
import re 
from fastapi import APIRouter, File, UploadFile, HTTPException, Form, Depends
from pydantic import BaseModel
from fastapi.responses import StreamingResponse, JSONResponse
from fastapi import Path 
from typing import Dict, Any, Optional
from firebase_admin import firestore
from datetime import datetime # Correct import: datetime now refers to the datetime.datetime class
import logging 

# Configure logging (optional, but good practice for full traceback)
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# IMPORTANT: Ensure the 'backend' directory is on sys.path for local development
current_file_dir = PathlibPath(__file__).resolve().parent 
backend_dir = current_file_dir.parent 
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from core.db_core import DatabaseManager
from core.ai_core import (
    extract_text_auto,
    get_resume_structure,
    categorize_skills_from_text,
    optimize_resume_json,
    optimize_for_linkedin,
    save_resume_json_to_docx,
    generate_full_resume_analysis 
)

from dependencies import get_db_manager, get_current_user

router = APIRouter()

class OptimizeRequest(BaseModel):
    user_request: str
    job_description: Optional[str] = None # Add job_description to the request model

def _normalize_filename(filename: str) -> str:
    """Cleans a filename for safe use in file paths or HTTP headers."""
    filename = re.sub(r'[^\w\-. ]', '', filename)
    filename = filename.replace(' ', '_')
    return filename

@router.get("/{user_uid}")
async def get_user_optimized_resume(user_uid: str = Path(..., description="The UID of the user whose resume is to be fetched."),
                                    user: dict = Depends(get_current_user),
                                    db: DatabaseManager = Depends(get_db_manager)):
    if user_uid != user['uid']:
        raise HTTPException(status_code=403, detail="Not authorized to access this user's resume.")

    try:
        resume_data = db.fetch_resume_relational(user_uid, get_optimized=True)
        if not resume_data:
            raise HTTPException(status_code=404, detail="No resume data found for this user.")
        return JSONResponse(content=resume_data)
    except Exception as e:
        logger.error(f"Error fetching user optimized resume for UID {user_uid}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"An internal server error occurred: {str(e)}")


@router.post("/upload")
async def upload_and_process_resume(
    file: Optional[UploadFile] = File(None, description="The user's resume file (PDF/DOCX)."),
    use_saved_resume: bool = Form(False, description="Set to true to use the resume already saved in the user's profile."),
    job_description: Optional[str] = Form(None, description="Optional job description for ATS analysis."),
    user: Dict[str, Any] = Depends(get_current_user),
    db: DatabaseManager = Depends(get_db_manager)
) -> JSONResponse:
    """
    Uploads a new resume file, or uses a previously uploaded one, performs AI parsing/categorization,
    and saves/updates the comprehensive data to the authenticated user's document.
    Also performs a full resume analysis including ATS if a job description is provided.
    """
    uid = user['uid']
    print(f"DEBUG: User {uid} initiating resume upload/update process for Optimizer.")

    resume_text: Optional[str] = None
    file_name: Optional[str] = None
    file_content_bytes: Optional[bytes] = None 
    file_extension: Optional[str] = None      
    
    full_analysis_report: Optional[Dict[str, Any]] = None 
    final_structured_data_to_save: Optional[Dict[str, Any]] = None 
    
    # Flags to track if AI calls for structure/skills were made for a saved resume
    structure_ai_called = False
    skills_ai_called = False

    try:
        if file and file.filename: # User is uploading a NEW resume
            print(f"DEBUG: 'file' is present. Filename: {file.filename}, Content-Type: {file.content_type}")
            if not (file.filename.endswith(".pdf") or file.filename.endswith(".docx")):
                print(f"ERROR: Invalid file type detected: {file.content_type}")
                raise HTTPException(status_code=400, detail="Invalid file type. Only PDF and DOCX are allowed.")
            
            file_content_bytes = await file.read()
            file_name = file.filename
            file_extension = os.path.splitext(file.filename)[1].lower()

            print(f"DEBUG: Read {len(file_content_bytes)} bytes from uploaded file into memory.")
            if not file_content_bytes:
                print("ERROR: Uploaded file content is empty.")
                raise HTTPException(status_code=400, detail="Uploaded file is empty.")
            
            resume_text = extract_text_auto(file_content_bytes, file_extension)
            print(f"DEBUG: Text extracted, length: {len(resume_text) if resume_text else 0}")
            
            if not resume_text:
                print("ERROR: Could not extract text from the uploaded resume file.")
                raise HTTPException(status_code=400, detail="Could not extract text from the uploaded resume file.")
            
            final_structured_data_to_save = get_resume_structure(resume_text)
            structure_ai_called = True # AI call made for new upload
            print(f"DEBUG: Structured data generated: {bool(final_structured_data_to_save)}")
            if not final_structured_data_to_save:
                print("ERROR: AI failed to structure the resume.")
                raise HTTPException(status_code=500, detail="AI failed to structure the resume from the uploaded content.")

            categorized_skills = categorize_skills_from_text(resume_text)
            skills_ai_called = True # AI call made for new upload
            if categorized_skills:
                final_structured_data_to_save['skills'] = categorized_skills
            
            final_structured_data_to_save['raw_text'] = resume_text 
            final_structured_data_to_save['resume_metadata'] = {
                'file_name': _normalize_filename(file_name),
                'uploaded_at': firestore.SERVER_TIMESTAMP # Save as Firestore timestamp
            }
            # No 'finally' block for temp file cleanup in this branch anymore

        elif use_saved_resume: # User is reusing an already saved resume
            print(f"DEBUG: Attempting to use saved resume for user {uid} for Optimizer.")
            
            user_doc_ref = db.db.collection('users').document(uid)
            user_doc = user_doc_ref.get()
            if not user_doc.exists:
                raise HTTPException(status_code=404, detail="User profile not found.")
            
            user_data = user_doc.to_dict()
            
            saved_raw_text = user_data.get('raw_resume_text')
            saved_metadata = user_data.get('resume_metadata', {})
            saved_structured_resume_data = user_data.get('structured_resume_data') # Fetch existing structured data
            saved_categorized_skills = user_data.get('categorized_skills') # Fetch existing categorized skills

            if not saved_raw_text:
                raise HTTPException(status_code=404, detail="No raw resume text found in your profile. Please upload a new resume.")
            
            resume_text = saved_raw_text
            file_name = saved_metadata.get('file_name', 'saved_resume.pdf')
            print(f"DEBUG: Using stored raw_resume_text '{file_name}' for user {uid}.")

            # --- OPTIMIZED FLOW: Reuse saved structured data and skills ---
            if saved_structured_resume_data and isinstance(saved_structured_resume_data, dict) and \
               saved_categorized_skills and isinstance(saved_categorized_skills, dict):
                
                final_structured_data_to_save = saved_structured_resume_data.copy()
                final_structured_data_to_save['skills'] = saved_categorized_skills.copy()
                print("DEBUG: Reused pre-existing structured resume data and categorized skills from DB (no Gemini calls for these).")
                # structure_ai_called and skills_ai_called remain False
                
            else: # Fallback: If structured data or skills are missing/invalid, regenerate from raw_text
                print("DEBUG: Saved structured data or skills missing/invalid. Re-generating from raw text.")
                final_structured_data_to_save = get_resume_structure(resume_text)
                structure_ai_called = True # AI call made
                if not final_structured_data_to_save:
                    raise HTTPException(status_code=500, detail="AI failed to structure the saved resume from content.")
                
                categorized_skills = categorize_skills_from_text(resume_text)
                skills_ai_called = True # AI call made
                if categorized_skills:
                    final_structured_data_to_save['skills'] = categorized_skills
                print("DEBUG: Re-generated structured resume data and skills from raw text (Gemini calls made).")

            final_structured_data_to_save['raw_text'] = resume_text 
            final_structured_data_to_save['resume_metadata'] = saved_metadata 
            # When reusing, update the timestamp to reflect recent activity, but don't force a full DB write later
            final_structured_data_to_save['resume_metadata']['uploaded_at'] = firestore.SERVER_TIMESTAMP 

        else:
            print("ERROR: Neither file was provided nor 'use_saved_resume' was true.")
            raise HTTPException(status_code=400, detail="No resume file provided and 'use_saved_resume' was not set to true.")

        # --- Conditional Database Update ---
        # The database should only be updated if it's a new upload, or if saved data needed regeneration.
        # If it's a 'use saved' and data was successfully reused (no new AI calls for structure/skills),
        # we skip the heavy DB update.
        if file and file.filename: # This is a NEW upload, always perform full DB write
            print(f"DEBUG: Performing full db.update_resume_relational for new resume upload by user {uid}.")
            success = db.update_resume_relational(user_uid=uid, parsed_data=final_structured_data_to_save)
        elif structure_ai_called or skills_ai_called: # This is 'use saved', but data needed regeneration
            print(f"DEBUG: Performing full db.update_resume_relational for 'use saved' (data was regenerated) by user {uid}.")
            success = db.update_resume_relational(user_uid=uid, parsed_data=final_structured_data_to_save)
        else: # This is 'use saved', and data was fully reused (no AI calls needed)
            print(f"DEBUG: Skipping full db.update_resume_relational for 'use saved' (data fully reused). Only generating report.")
            success = True # Mark as successful operation as no DB error occurred
        
        if not success:
            print(f"ERROR: Failed to save processed resume data for user {uid}.")
            raise HTTPException(status_code=500, detail="Failed to save processed resume data.")
        

        # --- Generate Full Resume Analysis Report (always generated for frontend display) ---
        print(f"DEBUG: Generating full resume analysis report for user {uid}.")
        full_analysis_report = generate_full_resume_analysis(resume_text, job_description)
        if not full_analysis_report:
            logger.warning(f"WARNING: Full resume analysis returned empty results for user {uid}.")
            full_analysis_report = {
                "analysis_date": datetime.now().strftime("%B %d, %Y"),
                "job_role_context": job_description if job_description and job_description.strip() else "General Candidate",
                "ai_model": "Google Gemini",
                "overall_resume_score": 0,
                "overall_resume_grade": "N/A",
                "ats_optimization_score": 0,
                "professional_profile_analysis": {"title": "Profile Analysis", "summary": "Analysis failed."},
                "education_analysis": {"title": "Education Analysis", "summary": "Analysis failed."},
                "experience_analysis": {"title": "Experience Analysis", "summary": "Analysis failed."},
                "skills_analysis": {"title": "Skills Analysis", "summary": "Analysis failed."},
                "key_strengths": ["Could not generate report."],
                "areas_for_improvement": ["Could not generate report."],
                "overall_assessment": "Failed to generate a comprehensive analysis report."
            }

        print(f"DEBUG: Responding to frontend with full analysis report (Overall Score: {full_analysis_report.get('overall_resume_score')}).")
        return JSONResponse(content={
            "message": "Resume processed successfully!",
            "user_uid": uid,
            "full_analysis_report": full_analysis_report 
        })

    except HTTPException as e:
        logger.error(f"HTTPException in /upload for user {uid}: {e.detail}")
        raise
    except Exception as e:
        logger.error(f"Unexpected error in /upload for user {uid}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error during resume processing: {str(e)}")
    finally:
        pass 

@router.post("/optimize")
async def optimize_resume(request_data: OptimizeRequest, user: dict = Depends(get_current_user),
                          db: DatabaseManager = Depends(get_db_manager)):
    uid = user['uid']
    
    try:
        resume_to_optimize = db.fetch_resume_relational(uid, get_optimized=False)
        if not resume_to_optimize:
            raise HTTPException(status_code=404, detail="Resume not found for this user.")
        
        optimized_data = optimize_resume_json(resume_to_optimize, request_data.user_request, job_description=request_data.job_description)
        
        db.update_optimized_resume_relational(uid, optimized_data)
        db.record_resume_optimization(uid)
        
        return JSONResponse(content={
            "message": "Optimization successful",
            "download_url": f"/api/resume/download/{uid}"
        })
    except Exception as e:
        logger.error(f"Error during resume optimization for user {uid}: {e}", exc_info=True) 
        raise HTTPException(status_code=500, detail=f"An internal server error occurred during optimization: {str(e)}")


@router.post("/linkedin-optimize")
async def optimize_linkedin_profile(request_data: OptimizeRequest, user: dict = Depends(get_current_user),
                                   db: DatabaseManager = Depends(get_db_manager)):
    uid = user['uid']

    try:
        resume_data = db.fetch_resume_relational(uid, get_optimized=False)
        if not resume_data:
            raise HTTPException(status_code=404, detail="Resume not found for this user.")
        
        linkedin_content = optimize_for_linkedin(resume_data, request_data.user_request, job_description=request_data.job_description)
        if not linkedin_content:
            raise HTTPException(status_code=500, detail="AI failed to generate LinkedIn content.")
        
        return JSONResponse(content=linkedin_content)
    except Exception as e:
        logger.error(f"Error during LinkedIn optimization for user {uid}: {e}", exc_info=True) 
        raise HTTPException(status_code=500, detail=f"An internal server error occurred during LinkedIn optimization: {str(e)}")


@router.get("/download/{user_uid}")
async def download_resume(user_uid: str = Path(..., description="The UID of the user whose optimized resume is to be downloaded."),
                          user: dict = Depends(get_current_user),
                          db: DatabaseManager = Depends(get_db_manager)):
    if user_uid != user['uid']:
        raise HTTPException(status_code=403, detail="Not authorized to download this user's resume.")

    try:
        final_data_for_doc = db.fetch_resume_relational(user_uid, get_optimized=True)
        if not final_data_for_doc:
            raise HTTPException(status_code=404, detail="Could not find optimized resume data for this user.")
        
        doc = save_resume_json_to_docx(final_data_for_doc)
        
        buffer = io.BytesIO()
        doc.save(buffer)
        buffer.seek(0)
        
        resume_metadata = final_data_for_doc.get('resume_metadata', {})
        original_filename = resume_metadata.get('file_name', 'resume')
        base_name = os.path.splitext(original_filename)[0]
        
        return StreamingResponse(buffer, media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                                 headers={"Content-Disposition": f"attachment; filename=Optimized_{_normalize_filename(base_name)}.docx"})
    except Exception as e:
        logger.error(f"Error during resume DOCX generation for user {user_uid}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"An error occurred during file generation: {str(e)}")