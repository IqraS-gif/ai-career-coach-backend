import os
import json
import firebase_admin
from firebase_admin import credentials, initialize_app
import sys

# --- CRITICAL: Firebase Admin SDK Initialization (GLOBAL AND ONCE) ---
if not firebase_admin._apps:
    try:
        firebase_json = os.environ.get("FIREBASE_CREDENTIALS")
        if not firebase_json:
            raise ValueError("CRITICAL: FIREBASE_CREDENTIALS environment variable not set!")

        cred_dict = json.loads(firebase_json)
        cred = credentials.Certificate(cred_dict)
        initialize_app(cred)
        print("✅ Firebase Admin SDK initialized successfully from environment variable.")
    except Exception as e:
        print(f"❌ CRITICAL ERROR: Failed to initialize Firebase Admin SDK: {e}")
        sys.exit(1)
else:
    print("ℹ️ Firebase Admin SDK already initialized (likely during reload).")
# --- END Firebase Admin SDK Initialization ---
