import firebase_admin
from firebase_admin import credentials, initialize_app
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pathlib import Path
import sys

# ------------------------------
# Firebase Admin SDK Initialization
# ------------------------------
if not firebase_admin._apps:
    try:
        backend_dir = Path(__file__).resolve().parent
        credentials_path = backend_dir / "firebase-credentials.json"
        
        if not credentials_path.exists():
            raise FileNotFoundError(f"'firebase-credentials.json' not found at {credentials_path}")
        
        cred = credentials.Certificate(credentials_path)
        initialize_app(cred)
        print("✅ Firebase Admin SDK initialized successfully from main.py")
    except Exception as e:
        print(f"❌ Failed to initialize Firebase Admin SDK: {e}")
        sys.exit(1)
else:
    print("ℹ️ Firebase Admin SDK already initialized.")

# ------------------------------
# FastAPI App Setup
# ------------------------------
app = FastAPI(title="AI Career Coach API", version="2.0.0")

# CORS
origins = [
    "http://localhost", "http://localhost:8080", "http://127.0.0.1", "http://127.0.0.1:8080",
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins, allow_credentials=True,
    allow_methods=["*"], allow_headers=["*"],
)

# Routers
from routers import auth, resume, roadmap, user, joblisting, assessment, interview

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

# ------------------------------
# NOTE: Remove __main__ uvicorn block for Render
# ------------------------------
