# backend/routers/roadmap.py
import sys
from pathlib import Path

# IMPORTANT: Ensure the 'backend' directory is on sys.path for local development
current_file_dir = Path(__file__).resolve().parent
backend_dir = current_file_dir.parent # Go up one level from 'routers' to 'backend'
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import Dict, Any, List

from core.db_core import DatabaseManager
from core.ai_core import generate_career_roadmap, get_tutor_explanation, get_chatbot_response
from dependencies import get_db_manager, get_current_user

router = APIRouter()

# --- Pydantic Models ---
class RoadmapRequest(BaseModel):
    current_skills_input: str
    current_level: str
    goal_input: str
    goal_level: str
    duration: str
    study_hours: str

class ChatbotRequest(BaseModel):
    query: str
    history: List[Dict[str, str]]
    career_plan: Dict[str, Any]

class TutorRequest(BaseModel):
    topic: str

class TaskStatusUpdateRequest(BaseModel):
    phase_title: str
    topic_name: str
    is_completed: bool

# --- Helper Function ---
def initialize_roadmap_progress(roadmap_data: Dict[str, Any]) -> Dict[str, Any]:
    """Ensures every topic in the detailed roadmap is a dictionary with progress."""
    if 'detailed_roadmap' in roadmap_data and isinstance(roadmap_data['detailed_roadmap'], list):
        for phase in roadmap_data['detailed_roadmap']:
            if 'topics' in phase and isinstance(phase['topics'], list):
                phase['topics'] = [
                    {"name": topic, "is_completed": False} if isinstance(topic, str) else topic
                    for topic in phase['topics']
                ]
    return roadmap_data

# --- API Endpoints ---

@router.post("/generate")
async def generate_roadmap_endpoint(request: RoadmapRequest, user: dict = Depends(get_current_user), db: DatabaseManager = Depends(get_db_manager)):
    uid = user['uid']
    try:
        roadmap_output_raw = generate_career_roadmap(request.dict())
        if not roadmap_output_raw:
            raise HTTPException(status_code=500, detail="AI failed to generate a career roadmap.")
        roadmap_output = initialize_roadmap_progress(roadmap_output_raw)
        await db.save_user_roadmap(uid, roadmap_output)
        db.record_roadmap_generation(uid)
        return roadmap_output
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"An internal server error occurred: {str(e)}")

@router.get("/latest")
async def get_latest_roadmap_endpoint(user: dict = Depends(get_current_user), db: DatabaseManager = Depends(get_db_manager)):
    uid = user['uid']
    try:
        roadmap = await db.get_user_roadmap(uid)
        if not roadmap:
            raise HTTPException(status_code=404, detail="No roadmap found for this user.")
        return initialize_roadmap_progress(roadmap)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"An internal server error occurred: {str(e)}")

@router.post("/update_task_status")
async def update_roadmap_task_status_endpoint(request: TaskStatusUpdateRequest, user: dict = Depends(get_current_user), db: DatabaseManager = Depends(get_db_manager)):
    uid = user['uid']
    try:
        success = await db.update_roadmap_task_status(uid, request.phase_title, request.topic_name, request.is_completed)
        if not success:
            raise HTTPException(status_code=404, detail="Task not found or could not be updated.")
        return {"message": "Task status updated successfully."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"An internal server error occurred: {str(e)}")

@router.post("/tutor")
async def get_tutor_response_endpoint(request: TutorRequest, user: dict = Depends(get_current_user)):
    try:
        tutor_response = get_tutor_explanation(request.topic)
        if not tutor_response:
            raise HTTPException(status_code=500, detail="AI tutor failed to provide an explanation.")
        return tutor_response
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"An internal server error occurred: {str(e)}")

# --- CHATBOT SECTION ---

def _summarize_career_plan(plan: Dict[str, Any]) -> str:
    """
    Converts the detailed roadmap JSON into a concise and error-proof string summary for the AI.
    This "bulletproof" version checks the type of each data section before processing it.
    """
    if not isinstance(plan, dict):
        return "Error: Career plan data is malformed."
    parts = []
    
    skills = plan.get('skills_to_learn_summary')
    if isinstance(skills, list) and skills: parts.append(f"**Priority Skills:** {', '.join(skills)}")
    
    detailed_roadmap = plan.get('detailed_roadmap')
    if isinstance(detailed_roadmap, list):
        parts.append("\n**Learning Phases:**")
        for phase in detailed_roadmap:
            if not isinstance(phase, dict): continue
            phase_title = phase.get('phase_title', 'Unnamed Phase')
            topic_names = []
            topics = phase.get('topics')
            if isinstance(topics, list):
                for topic in topics:
                    if isinstance(topic, dict): topic_names.append(topic.get('name', ''))
                    elif isinstance(topic, str): topic_names.append(topic)
            valid_topic_names = [name for name in topic_names if name]
            parts.append(f"- **{phase_title}**: Topics are {', '.join(valid_topic_names)}.")

    suggested_projects = plan.get('suggested_projects')
    if isinstance(suggested_projects, list):
        parts.append("\n**Suggested Projects:**")
        for proj in suggested_projects:
             if isinstance(proj, dict): parts.append(f"- {proj.get('project_title', 'Untitled Project')}")

    suggested_courses = plan.get('suggested_courses')
    if isinstance(suggested_courses, list):
        parts.append("\n**Recommended Courses:**")
        for course in suggested_courses:
            if isinstance(course, dict): parts.append(f"- '{course.get('course_name', 'Unnamed Course')}' on {course.get('platform', 'N/A')}.")
    
    return "\n".join(parts) if parts else "No career plan details are available."

@router.post("/chat")
async def get_chatbot_response_endpoint(request: ChatbotRequest, user: dict = Depends(get_current_user)):
    try:
        plan_summary_str = _summarize_career_plan(request.career_plan)
        
        # --- DIAGNOSTIC LOGGING ---
        print("\n--- Chatbot Pre-flight Check ---")
        print(f"Type of data being passed to AI Core: {type(plan_summary_str)}")
        print("This should be <class 'str'>.")
        print("------------------------------\n")
        
        chatbot_response = get_chatbot_response(request.query, request.history, plan_summary_str)
        
        if not chatbot_response:
            raise HTTPException(status_code=500, detail="AI chatbot failed to generate a response.")
        return chatbot_response
    except Exception as e:
        print(f"❌ Chatbot Endpoint Error: {e}")
        raise HTTPException(status_code=500, detail=f"An internal server error occurred: {str(e)}")