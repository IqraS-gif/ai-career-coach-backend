# backend/core/job_processor.py (FINAL - WITH API KEY FALLBACK)

import os
import re
import json
from typing import List, Dict, Any, Optional


try:
    from .ai_core import _call_gemini_with_fallback
except ImportError:
    # This fallback is for local testing if the script is run directly
    from ai_core import _call_gemini_with_fallback
# --- END MODIFIED SECTION ---


def extract_skills_from_text(text: str) -> List[str]:
    """
    Extracts a predefined set of technical and soft skills from a given text.
    This is a simplified extractor; for better results, integrate with AI_core's categorize_skills_from_text.
    """
    # This function does not use an API and remains UNCHANGED.
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
    for skill in skills_list:
        if re.search(r"\b" + re.escape(skill) + r"\b", text, re.IGNORECASE):
            found.append(skill)
            
    return list(set(found))


def get_job_ratings_in_one_call(jobs: List[Dict[str, Any]], skills: List[str]) -> List[Dict[str, Any]]:
    """
    Rates and summarizes a list of jobs based on user skills in a single API call to Gemini.
    Adds 'rating' (1-10) and 'reason' to each job dictionary.
    NOW USES THE RESILIENT FALLBACK MECHANISM.
    """
    if not jobs or not skills:
        return jobs

    # --- MODIFIED SECTION ---
    # This entire block is refactored for clarity and resilience.

    prompt_parts = [
        f"Based on the following skills from a user's resume: {', '.join(skills)}.",
        "Please evaluate the list of job descriptions below.",
        "For each job, provide a rating from 1 to 10 on how well it matches the skills, and a single sentence reason.",
        "IMPORTANT: You MUST respond with ONLY a valid JSON array of objects. Do not include any other text, explanations, or code markers.",
        "Each JSON object must have exactly three keys: 'id' (the original job index as an integer), 'rating' (an integer 1-10), and 'reason' (a string).",
        "CRITICAL: Ensure every object in the array is separated by a comma (except for the last one).",
        "\nHere are the jobs:\n"
    ]

    for i, job in enumerate(jobs):
        description = job.get('description', 'No description available.').replace('---', '-').replace('```', "'")
        prompt_parts.append(
            f"--- Job {i} ---\n"
            f"Title: {job.get('title', 'N/A')}\n"
            f"Company: {job.get('company', {}).get('display_name', 'N/A')}\n"
            f"Description: {description}\n"
        )
    
    final_prompt = "\n".join(prompt_parts)

    # Call our central, resilient API function from ai_core
    response = _call_gemini_with_fallback(final_prompt)

    # If the response is None, it means all API keys failed.
    if not response or not response.text:
        print("A critical error occurred while processing jobs: All API keys failed.")
        for job in jobs:
            job['rating'] = 0
            job['reason'] = "Error: AI service is currently unavailable."
        return jobs

    # The rest of the logic is for parsing the successful response, similar to before.
    raw_text = response.text
    json_str = None
    json_match = re.search(r'\[\s*{.*?}\s*(?:,\s*{.*?}\s*)*\]', raw_text, re.DOTALL)
    
    if json_match:
        json_str = json_match.group(0)
    else:
        print("Error: Gemini did not return a valid JSON array structure.")
        print("GEMINI RESPONSE (for debugging):", raw_text)
        for job in jobs: job.update({'rating': 0, 'reason': "Error: Invalid response format from AI."})
        return jobs

    try:
        ratings_data = json.loads(json_str)
        for rating_info in ratings_data:
            job_id = rating_info.get('id')
            if job_id is not None and isinstance(job_id, int) and 0 <= job_id < len(jobs):
                jobs[job_id]['rating'] = rating_info.get('rating', 0)
                jobs[job_id]['reason'] = rating_info.get('reason', 'N/A')
    except json.JSONDecodeError as e:
        print(f"JSON parsing failed: {e}. Raw text from AI: {json_str}")
        for job in jobs: job.update({'rating': 0, 'reason': "Error: Could not parse AI response."})

    return jobs
    # --- END MODIFIED SECTION ---
