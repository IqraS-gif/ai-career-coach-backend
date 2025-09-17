# backend/routers/joblisting.py
import sys
from pathlib import Path
from collections import defaultdict
import os
import json
import tempfile

# IMPORTANT: Local sys.path adjustment for local development imports
current_file_dir = Path(__file__).resolve().parent
backend_dir = current_file_dir.parent # Go up one level from 'routers' to 'backend'
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))
    print(f"DEBUG: Added {backend_dir} to sys.path from routers/joblisting.py") # DIAGNOSTIC PRINT

from fastapi import APIRouter, File, Form, UploadFile, Query, HTTPException, Depends
from fastapi.responses import JSONResponse
from typing import List, Dict, Any, Optional

# Import job-related core logic from new modules
from core.adzuna_client import fetch_jobs
from core.job_processor import extract_skills_from_text, get_job_ratings_in_one_call
from core.ai_core import extract_text_auto # Re-use existing text extractor from ai_core
from core.db_core import DatabaseManager

# Import dependencies for authentication and database interaction
from dependencies import get_current_user
from dependencies import get_db_manager
from routers.user import get_user_profile # Reuse user profile fetching to get resume content

router = APIRouter()

@router.post("/find_jobs/") # Endpoint for frontend to hit
async def upload_resume_and_find_jobs(
    file: Optional[UploadFile] = File(None, description="The user's resume in PDF or DOCX format."),
    # CORRECTED: Keep use_saved_resume as Form(False) to match FormData sending from frontend
    use_saved_resume: bool = Form(False, description="Set to true to use the resume already saved in the user's profile."), 
    location: str = Query("India", description="The country or city to search for jobs in (e.g., 'USA', 'London')"),
    user: Dict[str, Any] = Depends(get_current_user),
    db: DatabaseManager = Depends(get_db_manager)
) -> JSONResponse:
    """
    Uploads a user's resume, or uses a saved one, extracts skills, fetches relevant job listings from Adzuna,
    rates them using Gemini AI, and returns a sorted list of top job matches (max 7).
    """
    uid = user['uid']
    print(f"DEBUG: User {uid} initiating job search in {location}.")

    resume_text: Optional[str] = None
    tmp_file_path: Optional[str] = None # To manage temporary file cleanup

    try:
        if file:
            if not (file.filename.endswith(".pdf") or file.filename.endswith(".docx")): # Allow DOCX too
                raise HTTPException(status_code=400, detail="Only PDF or DOCX files are supported for resume upload.")

            file_content_bytes = await file.read()
            file_extension = os.path.splitext(file.filename)[1].lower()
            
            # Use ai_core's extract_text_auto which handles both PDF and DOCX
            resume_text = extract_text_auto(file_content_bytes, file_extension)
            if not resume_text:
                raise HTTPException(status_code=400, detail="Could not extract text from the uploaded resume file.")
        elif use_saved_resume:
            # Fetch resume text from the database if use_saved_resume is true
            print(f"DEBUG: Attempting to use saved resume for user {uid} for job search.")
            user_profile_data = await get_user_profile(user=user, db=db) # Reuse user profile fetching logic
            resume_content = user_profile_data.get('resume_content', {})
            
            if not resume_content or not resume_content.get('summary'): # Assuming summary is always present for a "saved" resume
                 raise HTTPException(status_code=404, detail="No previously uploaded resume found in your profile to use for job search.")
            
            # Reconstruct resume text from stored structured data for AI processing
            reconstructed_text_parts = []
            if resume_content.get('summary'):
                reconstructed_text_parts.append(resume_content['summary'])
            if resume_content.get('skills'):
                for category, skill_list in resume_content['skills'].items():
                    reconstructed_text_parts.append(f"{category}: {', '.join(skill_list)}")
            
            # Add projects too, to make the 'resume_text' richer for skill extraction
            if resume_content.get('projects'):
                for project in resume_content['projects']:
                    if project.get('title'):
                        reconstructed_text_parts.append(f"Project: {project['title']}")
                    if project.get('description') and isinstance(project['description'], list):
                        reconstructed_text_parts.extend(project['description'])

            resume_text = "\n\n".join(reconstructed_text_parts)
            if not resume_text:
                raise HTTPException(status_code=404, detail="Could not retrieve comprehensive content from your saved resume for job search.")
        else:
            raise HTTPException(status_code=400, detail="No resume file provided and 'use_saved_resume' was not set to true.")


        user_skills = extract_skills_from_text(resume_text)
        print(f"DEBUG: Extracted skills: {user_skills}")

        if not user_skills:
            return JSONResponse(content={"skills": [], "jobs": [], "message": "No relevant skills found in your resume to search for jobs."})

        # Fetch jobs for each skill and deduplicate
        unique_jobs_dict = {}
        # Fetch up to 50 jobs in total to have a good pool for rating, adjust results_per_page
        adzuna_results_per_skill = max(1, 50 // (len(user_skills) if user_skills else 1)) 
        
        for skill in user_skills:
            job_results = fetch_jobs(skill, location=location, results_per_page=adzuna_results_per_skill)
            for job in job_results:
                job_identifier = (job.get("title"), job.get("company", {}).get("display_name"), job.get("location", {}).get("display_name"))
                if job_identifier not in unique_jobs_dict:
                    job['match_skill'] = skill
                    unique_jobs_dict[job_identifier] = job
        
        unique_jobs_list = list(unique_jobs_dict.values())
        print(f"DEBUG: Found {len(unique_jobs_list)} unique jobs from Adzuna.")

        if not unique_jobs_list:
            return JSONResponse(content={"skills": user_skills, "jobs": [], "message": f"No jobs found for your skills in {location}."})

        rated_jobs = get_job_ratings_in_one_call(unique_jobs_list, user_skills)
        print(f"DEBUG: Rated {len(rated_jobs)} jobs with AI.")

        # --- START: MODIFIED JOB SELECTION LOGIC ---
        # Consolidate and select top N unique jobs (max 7)
        
        # Use a dict to store the best version of each unique job (by identifier)
        # This prevents taking a lower-rated duplicate if a higher-rated one exists.
        all_unique_rated_jobs = {} # Key: (title, company, location), Value: job_dict
        
        for job in rated_jobs:
            job_identifier = (
                job.get("title"),
                job.get("company", {}).get("display_name"),
                job.get("location", {}).get("display_name")
            )
            
            # If job not seen, or if this instance has a higher rating, update it
            if job_identifier not in all_unique_rated_jobs or \
               job.get('rating', 0) > all_unique_rated_jobs[job_identifier].get('rating', 0):
                all_unique_rated_jobs[job_identifier] = job

        # Sort all uniquely identified jobs by rating in descending order
        sorted_final_jobs_candidates = sorted(
            list(all_unique_rated_jobs.values()),
            key=lambda x: x.get('rating', 0),
            reverse=True
        )
        
        # Select exactly the top 7
        final_top_jobs_selected = sorted_final_jobs_candidates[:7]
        
        print(f"DEBUG: Selected {len(final_top_jobs_selected)} final top jobs.")
        # --- END: MODIFIED JOB SELECTION LOGIC ---

        # Reformat the final job list for the frontend
        formatted_jobs = []
        for job in final_top_jobs_selected: # Use the *selected* list
            formatted_job = {
                "title": job.get("title", "N/A"),
                "company": job.get("company", {}).get("display_name", "N/A"),
                "location": job.get("location", {}).get("display_name", "N/A"),
                "url": job.get("redirect_url", "#"),
                "match_skill": job.get("match_skill", "N/A"), # The skill that originally matched this job
                "rating": job.get("rating", 0),
                "reason": job.get("reason", "No reason provided by AI.")
            }
            formatted_jobs.append(formatted_job)
        
        print(f"DEBUG: Returning {len(formatted_jobs)} formatted jobs to frontend.")
        db.record_jobs_matched(uid)
        return JSONResponse(content={"skills": user_skills, "jobs": formatted_jobs})

    except HTTPException as e:
        print(f"HTTPException in /find_jobs/ for user {uid}: {e.detail}")
        raise
    except Exception as e:
        print(f"Unexpected error in /find_jobs/ for user {uid}: {e}")
        raise HTTPException(status_code=500, detail=f"Internal server error during job search: {str(e)}")
    finally:
        if tmp_file_path and os.path.exists(tmp_file_path):
            os.remove(tmp_file_path)
            print(f"DEBUG: Cleaned up temporary file: {tmp_file_path}")