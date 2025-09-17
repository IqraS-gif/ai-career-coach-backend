import os, json
import firebase_admin
from firebase_admin import credentials, initialize_app

if not firebase_admin._apps:
    try:
        firebase_creds = os.environ.get("FIREBASE_CREDENTIALS")
        if firebase_creds:
            cred_dict = json.loads(firebase_creds)
            cred = credentials.Certificate(cred_dict)
        else:
            # fallback to local JSON file
            from pathlib import Path
            credentials_path = Path(__file__).parent / "firebase-credentials.json"
            cred = credentials.Certificate(credentials_path)
        
        initialize_app(cred)
        print("✅ Firebase Admin SDK initialized successfully.")
    except Exception as e:
        print(f"❌ Failed to initialize Firebase Admin SDK: {e}")
        sys.exit(1)
