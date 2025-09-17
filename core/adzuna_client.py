# backend/core/adzuna_client.py

import os
import requests
from dotenv import load_dotenv
from typing import List, Dict, Any, Optional
import sys # For sys.exit on critical config error
import json

# Load environment variables
load_dotenv()

ADZUNA_APP_ID = os.getenv("ADZUNA_APP_ID")
ADZUNA_APP_KEY = os.getenv("ADZUNA_APP_KEY")

if not ADZUNA_APP_ID or not ADZUNA_APP_KEY:
    print("❌ CRITICAL ERROR: Adzuna API credentials (ADZUNA_APP_ID, ADZUNA_APP_KEY) not found in .env file. Please configure them.")
    sys.exit(1) # Critical configuration, exit if not set

def fetch_jobs(query: str, location: str = "India", results_per_page: int = 10) -> List[Dict[str, Any]]:
    """
    Fetches job listings from the Adzuna API based on a query and location.
    
    Args:
        query (str): The search query (e.g., skill, job title).
        location (str): The geographical location for the job search (e.g., "USA", "London", "India").
        results_per_page (int): Number of results to fetch per page.
        
    Returns:
        List[Dict[str, Any]]: A list of dictionaries, where each dictionary represents a job.
    """
    
    # Adzuna uses different endpoints for different countries/regions
    # Simple mapping, can be expanded for more countries
    country_code_map = {
        "india": "in", "usa": "us", "united states": "us", "uk": "gb", 
        "united kingdom": "gb", "canada": "ca", "australia": "au", "germany": "de",
        "france": "fr", "spain": "es", "italy": "it", "brazil": "br"
    }
    # Normalize location to find country code, default to 'in'
    lower_location = location.lower()
    country_code = "in" # Default
    for key, code in country_code_map.items():
        if key in lower_location or lower_location.startswith(key):
            country_code = code
            break
            
    url = f"https://api.adzuna.com/v1/api/jobs/{country_code}/search/1"
    params = {
        "app_id": ADZUNA_APP_ID,
        "app_key": ADZUNA_APP_KEY,
        "results_per_page": results_per_page,
        "what": query,
        "where": location, # Adzuna can often use the location name for more specific searches
        "full_time": "1" # Example: Only full-time jobs. Adjust as needed.
    }

    try:
        response = requests.get(url, params=params, timeout=15) # Increased timeout
        response.raise_for_status() # Raise HTTPError for bad responses (4xx or 5xx)
        return response.json().get("results", [])
    except requests.exceptions.HTTPError as http_err:
        print(f"Adzuna API HTTP Error for '{query}' in '{location}': {http_err} - {response.text}")
    except requests.exceptions.ConnectionError as conn_err:
        print(f"Adzuna API Connection Error for '{query}' in '{location}': {conn_err}")
    except requests.exceptions.Timeout as timeout_err:
        print(f"Adzuna API Timeout Error for '{query}' in '{location}': {timeout_err}")
    except requests.exceptions.RequestException as req_err:
        print(f"Adzuna API Request Error for '{query}' in '{location}': {req_err}")
    except json.JSONDecodeError:
        print(f"Adzuna API: Failed to decode JSON response for '{query}' in '{location}'. Response: {response.text}")
        
    return []