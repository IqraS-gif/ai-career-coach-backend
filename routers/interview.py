from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List, Dict

# --- We now need TWO functions from ai_core ---
from core.ai_core import get_interview_chat_response, get_interview_summary

router = APIRouter(
    tags=["Mock Interview"]
)

# ==========================================================
# Pydantic Models
# ==========================================================
class ChatMessage(BaseModel):
    role: str
    content: str

class ChatRequest(BaseModel):
    job_description: str
    chat_history: List[ChatMessage]
    difficulty: str

class ChatResponse(BaseModel):
    reply: str

class SummarizeRequest(BaseModel):
    job_description: str
    chat_history: List[ChatMessage]

class SummaryResponse(BaseModel):
    overall_score: int
    strengths: List[str]
    areas_for_improvement: List[str]
    overall_feedback: str

# ==========================================================
# Endpoints
# ==========================================================

@router.post("/chat", response_model=ChatResponse, summary="Conduct the AI Mock Interview")
async def conduct_interview_chat(request: ChatRequest):
    if not request.job_description or not request.job_description.strip():
        raise HTTPException(status_code=400, detail="Job description cannot be empty.")

    response_data = get_interview_chat_response(
        job_description=request.job_description,
        history=[msg.dict() for msg in request.chat_history],
        difficulty=request.difficulty
    )
    
    if not response_data or "reply" not in response_data:
        raise HTTPException(status_code=500, detail="AI failed to generate a chat response.")
        
    return response_data

@router.post("/summarize", response_model=SummaryResponse, summary="Summarize the interview performance")
async def summarize_interview(request: SummarizeRequest):
    if not request.chat_history:
        raise HTTPException(status_code=400, detail="Chat history cannot be empty.")

    summary_data = get_interview_summary(
        job_description=request.job_description,
        history=[msg.dict() for msg in request.chat_history]
    )
    
    if not summary_data:
        raise HTTPException(status_code=500, detail="AI failed to generate an interview summary.")
        
    return summary_data