import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pathlib import Path
import firebase_admin
from firebase_admin import credentials, initialize_app
import sys


# --- CRITICAL: Firebase Admin SDK Initialization (GLOBAL AND ONCE) ---
if not firebase_admin._apps:
    try:
        backend_dir = Path(__file__).resolve().parent
        credentials_path = backend_dir / "firebase-credentials.json"
        
        if not credentials_path.exists():
            raise FileNotFoundError(f"CRITICAL: 'firebase-credentials.json' not found at {credentials_path}")
        
        cred = credentials.Certificate(credentials_path)
        initialize_app(cred)
        print("✅ Firebase Admin SDK initialized successfully in main.py.")
    except Exception as e:
        print(f"❌ CRITICAL ERROR: Failed to initialize Firebase Admin SDK: {e}")
        sys.exit(1)
else:
    print("ℹ️ Firebase Admin SDK already initialized (likely during reload).")
# --- END Firebase Admin SDK Initialization ---

# Now import routers. They will use their own sys.path adjustments and import from dependencies.py.
# Use direct imports for folders at the same level as main.py
from routers import auth, resume, roadmap, user, joblisting, assessment, interview

# =========================
# FastAPI Application Setup
# =========================
app = FastAPI(
    title="AI Career Coach API",
    version="2.0.0"
)

# --- CORS Configuration ---
origins = [
    "http://localhost", "http://localhost:8080", "http://127.0.0.1", "http://127.0.0.1:8080", "null",
    "http://127.0.0.1:5500",
    "http://localhost:5500",
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins, allow_credentials=True,
    allow_methods=["*"], allow_headers=["*"],
)

# --- Include API Routers ---
app.include_router(auth.router, prefix="/api/auth", tags=["Authentication"])
app.include_router(resume.router, prefix="/api/resume", tags=["Resume and Optimization"])
app.include_router(roadmap.router, prefix="/api/roadmap", tags=["Career Roadmap"])
app.include_router(user.router, prefix="/api/user", tags=["User Profile"])
app.include_router(joblisting.router, prefix="/api/jobs", tags=["Job Listing and Matching"])
app.include_router(assessment.router, prefix="/api/assessment", tags=["Skill Assessment"])
app.include_router(interview.router, prefix="/api/interview", tags=["Mock Interview"])

@app.get("/")
async def root():
    return {"message": "AI Career Coach Backend is running!"}

# =========================
# Main Execution Block
# =========================
if __name__ == "__main__":
    print("Starting AI Career Coach API server...")
    # Run uvicorn from the 'backend' directory
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)
