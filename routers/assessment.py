# backend/routers/assessment.py
import sys
from pathlib import Path
import firebase_admin # Ensure this is imported if used elsewhere, or remove if not.
from firebase_admin import firestore # Ensure this is imported if used elsewhere, or remove if not.

# IMPORTANT: Ensure the 'backend' directory is on sys.path for local development
current_file_dir = Path(__file__).resolve().parent
backend_dir = current_file_dir.parent # Go up one level from 'routers' to 'backend'
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field
from typing import Dict, Any, Optional, List, Union

from core.db_core import DatabaseManager
from core.ai_core import generate_assessment_questions, evaluate_assessment_answers # NEW AI CORE FUNCTIONS

from dependencies import get_db_manager, get_current_user

router = APIRouter()

# Pydantic models for assessment setup
class AssessmentSetupRequest(BaseModel):
    assessment_type: str # e.g., "software_developer", "data_scientist", "custom"
    skills: List[str] # List of skills the user wants to be assessed on
    target_role: Optional[str] = None # Optional target role for context

# Pydantic model for individual answer submission
class UserAnswer(BaseModel):
    question_id: str
    answer: Union[str, List[str], None] # Can be a string for short answer/coding, list for multi-choice, or None

# Pydantic model for full assessment submission
class AssessmentSubmissionRequest(BaseModel):
    assessment_id: str # This could be the user's UID or a session ID
    answers: List[UserAnswer]

@router.post("/start")
async def start_assessment_endpoint(
    request: AssessmentSetupRequest,
    user: dict = Depends(get_current_user),
    db: DatabaseManager = Depends(get_db_manager)
):
    uid = user['uid']
    print(f"User {uid} requesting assessment start for type: {request.assessment_type}, skills: {request.skills}")
    
    try:
        # Generate questions using AI_CORE
        questions_output = generate_assessment_questions(
            assessment_type=request.assessment_type,
            skills=request.skills,
            target_role=request.target_role,
            user_id=uid # Pass user ID for potential personalization/history
        )
        if not questions_output or not questions_output.get('questions'):
            raise HTTPException(status_code=500, detail="AI failed to generate assessment questions.")
        
        # Optional: Save generated questions to Firestore for later reference/grading
        # For simplicity, we're assuming stateless for now, but in a real app, you'd save this.
        # assessment_doc_ref = db.db.collection('users').document(uid).collection('assessments').add({
        #     'setup_request': request.dict(),
        #     'questions': questions_output['questions'],
        #     'status': 'started',
        #     'created_at': firestore.SERVER_TIMESTAMP
        # })
        # return {"assessment_session_id": assessment_doc_ref.id, "questions": questions_output['questions']}
        db.record_assessment_taken(uid)
        return {"questions": questions_output['questions']}
        
    except Exception as e:
        print(f"Error starting assessment for user {uid}: {e}")
        raise HTTPException(status_code=500, detail=f"An internal server error occurred: {str(e)}")

@router.post("/submit")
async def submit_assessment_endpoint(
    request: AssessmentSubmissionRequest,
    user: dict = Depends(get_current_user),
    db: DatabaseManager = Depends(get_db_manager)
):
    uid = user['uid']
    print(f"User {uid} submitting assessment {request.assessment_id}")

    try:
        # Convert List[UserAnswer] to List[Dict] for ai_core function
        submitted_answers_as_dicts = [ans.dict() for ans in request.answers] # <--- CRITICAL FIX HERE

        results_output = evaluate_assessment_answers(
            user_id=uid,
            submitted_answers=submitted_answers_as_dicts, # Pass the list of dictionaries
            # original_questions=original_assessment_data.get('questions') # Pass if needed for evaluation
        )
        if not results_output:
            raise HTTPException(status_code=500, detail="AI failed to evaluate assessment answers.")
        
        # Optional: Save the results to Firestore
        # db.db.collection('users').document(uid).collection('assessments').document(request.assessment_id).update({
        #     'status': 'completed',
        #     'submitted_answers': [ans.dict() for ans in request.answers], # Still convert here if saving original pydantic models
        #     'results': results_output,
        #     'completed_at': firestore.SERVER_TIMESTAMP
        # })
        
        return results_output
    except Exception as e:
        print(f"Error submitting assessment for user {uid}: {e}")
        raise HTTPException(status_code=500, detail=f"An internal server error occurred: {str(e)}")