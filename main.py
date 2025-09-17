# main.py
import os
import json
import sys
from pathlib import Path
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import firebase_admin
from firebase_admin import credentials, initialize_app

# ------------------------------
# Firebase Admin SDK Initialization
# ------------------------------
if not firebase_admin._apps:
    try:
        firebase_creds = os.environ.get("FIREBASE_CREDENTIALS")
        if firebase_creds:
            # Load credentials from environment variable (Render/Production)
            cred_dict = json.loads(firebase_creds)
            cred = credentials.Certificate(cred_dict)
        else:
            # Fallback to local JSON file (for local dev)
            credentials_path = Path(__file__).parent / "firebase-credentials.json"
            if not credentials_path.exists():
                raise FileNotFoundError(
                    f"'firebase-credentials.json' not found at {credentials_path}"
                )
            cred = credentials.Certificate(credentials_path)
        
        initialize_app(cred)
        print("✅ Firebase Admin SDK initialized successfully.")
    except Exception as e:
        print(f"❌ Failed to initialize Firebase Admin SDK: {e}")
        sys.exit(1)
else:
    print("ℹ️ Firebase Admin SDK already initialized.")

# ------------------------------
# FastAPI App Setup
# ------------------------------
app = FastAPI(title="AI Career Coach API", version="2.0.0")

# CORS configuration
origins = [
    "http://localhost",
    "http://localhost:8080",
    "http://127.0.0.1",
    "http://127.0.0.1:8080",
    # --- ACTION: ADD YOUR GITHUB PAGES URL HERE ---
    "https://iqras-gif.github.io",
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ------------------------------
# Include Routers
# ------------------------------
# Make sure these exist and are importable
from routers import auth, resume, roadmap, user, joblisting, assessment, interview

app.include_router(auth.router, prefix="/api/auth", tags=["Authentication"])
app.include_router(resume.router, prefix="/api/resume", tags=["Resume and Optimization"])
app.include_router(roadmap.router, prefix="/api/roadmap", tags=["Career Roadmap"])
app.include_router(user.router, prefix="/api/user", tags=["User Profile"])
app.include_router(joblisting.router, prefix="/api/jobs", tags=["Job Listing and Matching"])
app.include_router(assessment.router, prefix="/api/assessment", tags=["Skill Assessment"])
app.include_router(interview.router, prefix="/api/interview", tags=["Mock Interview"])

# ------------------------------
# Root Endpoint
# ------------------------------
@app.get("/")
async def root():
    return {"message": "AI Career Coach Backend is running!"}

# ------------------------------
# Local Development Only
# ------------------------------
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)
