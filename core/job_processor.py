# backend/core/job_processor.py

import os
import re
import json
from typing import List, Dict, Any, Optional
from collections import defaultdict

import google.generativeai as genai
from dotenv import load_dotenv

# Load environment variables for AI key
load_dotenv()

# Configure the Gemini API (assuming setup_gemini_api is called in ai_core or directly here)
GEMINI_API_KEY = os.getenv("GOOGLE_API_KEY")
if not GEMINI_API_KEY:
    print("❌ CRITICAL ERROR: GOOGLE_API_KEY not found in .env file for job_processor.py.")
    _GEMINI_MODEL_NAME = None # So subsequent calls fail safely
    # In a real app, you might want to raise an exception or handle this more gracefully.
else:
    genai.configure(api_key=GEMINI_API_KEY)
    _GEMINI_MODEL_NAME = 'gemini-1.5-flash' # Or 'gemini-pro' depending on preference


def extract_skills_from_text(text: str) -> List[str]:
    """
    Extracts a predefined set of technical and soft skills from a given text.
    This is a simplified extractor; for better results, integrate with AI_core's categorize_skills_from_text.
    """
    # A more comprehensive list could be dynamically updated or AI-generated
    skills_list = [
        "Python", "Java", "C++", "JavaScript", "TypeScript", "Go", "Rust", "C#",
        "SQL", "NoSQL", "MongoDB", "PostgreSQL", "MySQL", "Redis", "Elasticsearch",
        "React", "Angular", "Vue.js", "Node.js", "Express.js", "Django", "Flask", "Spring Boot",
        "AWS", "Azure", "Google Cloud", "GCP", "Docker", "Kubernetes", "Git", "Jenkins", "Terraform",
        "Machine Learning", "Deep Learning", "NLP", "Computer Vision", "Data Analysis", "Data Science",
        "Cloud Computing", "DevOps", "Cybersecurity", "Blockchain", "Agile", "Scrum",
        "Communication", "Teamwork", "Leadership", "Problem Solving", "Critical Thinking", "Adaptability",
        "Project Management", "UI/UX Design", "Frontend", "Backend", "Fullstack"
    ]
    
    found = []
    # Using regex to find whole words, case-insensitive
    for skill in skills_list:
        if re.search(r"\b" + re.escape(skill) + r"\b", text, re.IGNORECASE):
            found.append(skill)
            
    return list(set(found)) # Return unique skills


def get_job_ratings_in_one_call(jobs: List[Dict[str, Any]], skills: List[str]) -> List[Dict[str, Any]]:
    """
    Rates and summarizes a list of jobs based on user skills in a single API call to Gemini.
    Adds 'rating' (1-10) and 'reason' to each job dictionary.
    """
    if not jobs or not skills:
        return jobs
    if not _GEMINI_MODEL_NAME:
        print("Gemini API not configured for job rating. Returning jobs with default rating.")
        for job in jobs: job.update({'rating': 0, 'reason': "AI not configured."})
        return jobs

    model = genai.GenerativeModel(_GEMINI_MODEL_NAME)

    prompt_parts = [
        f"Based on the following skills from a user's resume: {', '.join(skills)}.",
        "Please evaluate the list of job descriptions below.",
        "For each job, provide a rating from 1 to 10 on how well it matches the skills, and a single sentence reason.",
        "IMPORTANT: You MUST respond with ONLY a valid JSON array of objects. Do not include any other text, explanations, or code markers.",
        "Each JSON object must have exactly three keys: 'id' (the original job index as an integer), 'rating' (an integer 1-10), and 'reason' (a string).",
        "CRITICAL: Ensure every object in the array is separated by a comma (except for the last one).",
        "\nHere are the jobs:\n"
    ]

    # Dynamically build the prompt with job descriptions
    for i, job in enumerate(jobs):
        # Sanitize description to avoid breaking prompt or JSON parsing
        description = job.get('description', 'No description available.').replace('---', '-').replace('```', "'") # Added replace('```', "'")
        prompt_parts.append(
            f"--- Job {i} ---\n"
            f"Title: {job.get('title', 'N/A')}\n"
            f"Company: {job.get('company', {}).get('display_name', 'N/A')}\n"
            f"Description: {description}\n"
        )
    
    final_prompt = "\n".join(prompt_parts)

    try:
        safety_settings = {'HARM_CATEGORY_HARASSMENT': 'BLOCK_NONE','HARM_CATEGORY_HATE_SPEECH': 'BLOCK_NONE','HARM_CATEGORY_SEXUALLY_EXPLICIT': 'BLOCK_NONE','HARM_CATEGORY_DANGEROUS_CONTENT': 'BLOCK_NONE'}
        response = model.generate_content(final_prompt, safety_settings=safety_settings)
        raw_text = response.text
        
        # Robust JSON extraction from markdown format like ```json[...]```
        json_match = re.search(r'\[\s*{.*?}\s*(?:,\s*{.*?}\s*)*\]', raw_text, re.DOTALL)
        if not json_match:
            print("Error: Gemini did not return a valid JSON array structure.")
            print("GEMINI RESPONSE (for debugging):", raw_text)
            # Default all jobs to 0 rating if AI response is unparseable
            for job in jobs: job.update({'rating': 0, 'reason': "Error: Invalid response format from AI."})
            return jobs

        json_str = json_match.group(0)

        try:
            ratings_data = json.loads(json_str)
        except json.JSONDecodeError as e:
            print(f"JSON parsing failed: {e}. Attempting to fix common JSON issues...")
            # Attempt to fix common JSON issues like missing commas between objects
            fixed_json_str = re.sub(r'}\s*{', '},{', json_str)
            try:
                ratings_data = json.loads(fixed_json_str)
            except json.JSONDecodeError as e_fixed:
                print(f"JSON parsing failed again after attempting a fix: {e_fixed}")
                # If still fails, default all jobs to 0 rating
                for job in jobs: job.update({'rating': 0, 'reason': "Error: Could not parse AI response."})
                return jobs

        for rating_info in ratings_data:
            job_id = rating_info.get('id')
            if job_id is not None and isinstance(job_id, int) and 0 <= job_id < len(jobs):
                jobs[job_id]['rating'] = rating_info.get('rating', 0)
                jobs[job_id]['reason'] = rating_info.get('reason', 'N/A')

    except Exception as e:
        print(f"A critical error occurred while processing jobs with Gemini: {e}")
        # Default all jobs to 0 rating on critical AI error
        for job in jobs:
            job['rating'] = 0
            job['reason'] = "Error during AI rating process."

    return jobs