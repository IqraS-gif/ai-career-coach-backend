from datetime import datetime
import os
import io
import sys
import json
import re
from typing import Optional, Tuple, List, Dict, Any, Union

# Required libraries (ensure they are installed via requirements.txt)
import fitz  # PyMuPDF
import google.generativeai as genai
from dotenv import load_dotenv
from docx import Document
from docx.shared import Pt
from docx.enum.text import WD_ALIGN_PARAGRAPH
from google.api_core import exceptions as google_exceptions

# =========================
# Setup (MODIFIED FOR FALLBACK)
# =========================

API_KEYS = []
MODEL_NAME = "gemini-1.5-flash-latest"

def setup_api_keys():
    """Loads all available Gemini API keys from environment variables."""
    global API_KEYS
    load_dotenv()
    
    i = 1
    while True:
        key = os.getenv(f"GEMINI_API_KEY_{i}")
        if i == 1 and not key:
             key = os.getenv("GOOGLE_API_KEY") # Backward compatibility for the first key

        if key:
            API_KEYS.append(key)
            i += 1
        else:
            break
    
    if not API_KEYS:
        print("CRITICAL ERROR: No 'GEMINI_API_KEY_1' or 'GOOGLE_API_KEY' found. Application cannot start.")
        sys.exit(1)
        
    print(f"✅ Successfully loaded {len(API_KEYS)} Gemini API key(s).")

# Initialize the keys when the module is loaded
setup_api_keys()

# =========================
# NEW: Central API Call Function with Fallback Logic
# =========================
def _call_gemini_with_fallback(prompt: str, is_chat: bool = False, history: List = None) -> Optional[Any]:
    """
    Calls the Gemini API, automatically trying the next API key if the current one fails.
    Handles both standard generation and chat sessions.
    """
    safety_settings = {
        'HARM_CATEGORY_HARASSMENT': 'BLOCK_NONE', 'HARM_CATEGORY_HATE_SPEECH': 'BLOCK_NONE',
        'HARM_CATEGORY_SEXUALLY_EXPLICIT': 'BLOCK_NONE', 'HARM_CATEGORY_DANGEROUS_CONTENT': 'BLOCK_NONE'
    }

    for i, key in enumerate(API_KEYS):
        try:
            print(f"DEBUG(ai_core): Attempting API call with key #{i + 1}")
            genai.configure(api_key=key)
            model = genai.GenerativeModel(MODEL_NAME)
            
            if is_chat:
                chat_session = model.start_chat(history=history or [])
                response = chat_session.send_message(prompt)
            else:
                response = model.generate_content(prompt, safety_settings=safety_settings)

            print(f"DEBUG(ai_core): API call successful with key #{i + 1}")
            return response
        
        except (google_exceptions.ResourceExhausted, google_exceptions.PermissionDenied, google_exceptions.InternalServerError) as e:
            print(f"⚠️ WARNING: API Key #{i + 1} failed. Trying next key. Error: {type(e).__name__}")
        except Exception as e:
            print(f"⚠️ WARNING: An unexpected error occurred with API Key #{i + 1}. Trying next key. Error: {type(e).__name__}")
    
    print("❌ CRITICAL ERROR: All available Gemini API keys failed. The request could not be completed.")
    return None

# =========================
# JSON Schema Constants (Your code - UNCHANGED)
# =========================
ASSESSMENT_QUESTIONS_SCHEMA = """
[
  {
    "question_id": "string",
    "question_text": "string",
    "question_type": "single_choice" | "multiple_choice" | "short_answer" | "coding_challenge",
    "options": ["string option 1", "string option 2", "string option 3", "string option 4"],
    "correct_answer_keys": ["string option 1"]
  }
]
"""
ASSESSMENT_EVALUATION_SCHEMA = """
{
  "overall_score": 75,
  "skills_mastered": 3,
  "areas_to_improve": 2,
  "skill_scores": { "Python": 80, "SQL": 60, "Data Analysis": 75 },
  "strengths": ["Demonstrated strong foundational knowledge in Python.", "Understood basic SQL queries."],
  "weaknesses": ["Struggled with complex data manipulation in SQL.", "Limited understanding of advanced data analysis concepts."],
  "recommendations": [
    "Focus on SQL subqueries and window functions for data manipulation.",
    "Practice implementing machine learning algorithms from scratch.",
    "Explore advanced data visualization techniques and tools."
  ]
}
"""
FULL_RESUME_ANALYSIS_SCHEMA = """
{
  "analysis_date": "September 05, 2025",
  "job_role_context": "string",  # CORRECTED: Changed default to 'string' to indicate it's dynamic
  "ai_model": "Google Gemini",
  "overall_resume_score": 68,
  "overall_resume_grade": "Good",
  "ats_optimization_score": 60,
  "professional_profile_analysis": {
    "title": "Professional Profile Analysis",
    "summary": "The candidate presents a clear trajectory of learning and project involvement, demonstrating foundational skills relevant to the target role. However, the profile could benefit from a more concise and impact-driven summary statement tailored directly to a 'Frontend Developer' role, immediately highlighting key value propositions."
  },
  "education_analysis": {
    "title": "Education Analysis",
    "summary": "The education section is concise but could be enhanced. Adding the expected graduation date would be helpful. Listing relevant development coursework (e.g., 'Web Development I & II', 'Data Structures and Algorithms') would reinforce technical expertise. Emphasize any honors or significant academic achievements."
  },
  "experience_analysis": {
    "title": "Experience Analysis",
    "summary": "The projects section is informative but overwhelming. The descriptions are too long and lack quantifiable achievements. Instead of lengthy descriptions, focus on impactful results using numbers and action verbs. For instance, 'Developed a responsive e-commerce platform that increased user engagement by 15%.'"
  },
  "skills_analysis": {
    "title": "Skills Analysis",
    "summary": "The current skills section is adequate but could be structured more effectively for ATS scanning. Consider grouping related skills (e.g., 'Languages: JavaScript, Python', 'Frameworks: React, Angular'). Ensure all frontend-specific skills (e.g., HTML5, CSS3, SASS, Webpack) are explicitly listed and visible."
  },
  "key_strengths": [
    "Diverse Project Portfolio: The candidate has undertaken a wide variety of projects, showcasing initiative and a broad skillset.",
    "Clear Learning Trajectory: Demonstrates continuous learning and application of new technologies.",
    "Foundational Technical Acumen: Possesses a solid understanding of core computer science principles applicable to development."
  ],
  "areas_for_improvement": [
    "Target Role Focus: The resume needs to be sharply focused on the frontend developer role. De-emphasize or remove projects that don't directly showcase relevant frontend skills.",
    "Quantify Achievements: Introduce more quantifiable results (numbers, percentages) in project and experience descriptions.",
    "ATS Keyword Optimization: Integrate common frontend developer keywords (e.g., 'Responsive Design', 'API Integration', 'Version Control', 'TypeScript') more strategically.",
    "Concise Descriptions: Shorten lengthy project/experience descriptions to impactful bullet points.",
    "Consistent Formatting: Ensure consistent formatting across all sections, especially dates and bullet points, for better readability and ATS parsing."
  ],
  "overall_assessment": "This resume demonstrates a strong foundation in computer engineering and relevant project involvement. With targeted refinement to highlight frontend development skills, quantify achievements, and optimize for ATS, the candidate can significantly enhance their chances of securing interviews."
}
"""

# =========================
# Helper Functions (Your code - UNCHANGED)
# =========================
def _safe_json_loads(s: str, fallback=None):
    if not s: return fallback
    s = s.strip()
    if s.startswith("```json"): s = s[7:]
    if s.endswith("```"): s = s[:-3]
    s = s.strip()
    try:
        return json.loads(s)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", s, flags=re.DOTALL)
        if m:
            try: return json.loads(m.group(0))
            except json.JSONDecodeError: return fallback
    return fallback

def _norm(s: Optional[str]) -> bool:
    return bool(s and s.strip())

def _smart_join(parts: List[Optional[str]]) -> str:
    return " | ".join([str(p) for p in parts if _norm(p)])

def _best_section_key(target_key: str, available_keys: List[str]) -> Optional[str]:
    if not target_key: return None
    t = target_key.strip().lower().replace(" ", "_").replace("-", "_")
    for k in available_keys:
        k_norm = k.lower().replace(" ", "_")
        if t == k_norm or t in k_norm or k_norm in t: return k
    return None

def parse_user_optimization_input(inp: str) -> Tuple[Optional[str], Optional[str]]:
    val = (inp or "").strip()
    if not val: return None, None
    if ":" in val:
        left, right = val.split(":", 1); return _norm(left), _norm(right)
    if len(val.split()) == 1:
        return val, None
    return None, val

def _stringify_list_content(content: Any) -> str:
    if not isinstance(content, list): return str(content or "")
    string_parts = []
    for item in content:
        if isinstance(item, str): string_parts.append(item)
        elif isinstance(item, dict):
            string_parts.append(", ".join([f"{k.replace('_', ' ').title()}: {v}" for k, v in item.items()]))
        else: string_parts.append(str(item))
    return "\n".join(string_parts)

def extract_text_auto(file_content: bytes, file_extension: str) -> Optional[str]:
    print(f"DEBUG(ai_core): extract_text_auto called for in-memory content (Type: {file_extension})")
    try:
        if file_extension == ".pdf":
            with fitz.open(stream=file_content, filetype="pdf") as doc: 
                return "\n".join([page.get_text() for page in doc])
        elif file_extension == ".docx":
            doc = Document(io.BytesIO(file_content))
            chunks = [p.text for p in doc.paragraphs if _norm(p.text)]
            if doc.tables:
                for table in doc.tables:
                    for row in table.rows:
                        cells_for_chunk = [cell.text for cell in row.cells if _norm(cell.text)]
                        if cells_for_chunk: chunks.append(" | ".join(cells_for_chunk))
            return "\n".join(chunks)
        else:
            return None
    except Exception as e:
        print(f"ERROR(ai_core): Failed to read file content. Exception: {e}", exc_info=True)
        return None

# ============================================
# API Functions (MODIFIED TO USE FALLBACK)
# ============================================

def get_resume_structure(resume_text: str) -> Optional[Dict[str, Any]]:
    prompt = f"""
You are an expert HR Technology engineer specializing in resume data extraction. Your task is to convert the raw text of a resume into a structured, valid JSON object, capturing ALL information with high fidelity.
**Instructions:**
1.  **Use the Base Schema:** For common sections, use the following schema.
2.  **Capture Everything Else:** If you find other sections that do not fit the schema (e.g., "Achievements", "Leadership"), create a new top-level key for them (e.g., "achievements").
3.  **IGNORE THE SKILLS SECTION:** Do not parse the skills section in this step. It will be handled by a different process. Omit the 'skills' key from your output.
**Base Schema:**
{{
  "personal_info": {{ "name": "string", "email": "string", "phone": "string", "linkedin": "string", "github": "string" }},
  "summary": "string",
  "work_experience": [ {{ "role": "string", "company": "string", "duration": "string", "description": ["string", ...] }} ],
  "internships": [ {{ "role": "string", "company": "string", "duration": "string", "description": ["string", ...] }} ],
  "education": [ {{ "institution": "string", "degree": "string", "duration": "string", "description": ["string", ...] }} ],
  "projects": [ {{ "title": "string", "description": ["string", ...] }} ],
  "certifications": [ {{ "name": "string", "description": "string" }} ]
}}
**Critical Rules:**
- If a section from the base schema is NOT in the resume, YOU MUST OMIT ITS KEY from the final JSON. Do not create empty sections.
- Your final output must be a single, valid JSON object starting with `{{` and ending with `}}`. Do not include markdown.
--- RESUME TEXT ---
{resume_text}
--- END RESUME TEXT ---
"""
    response = _call_gemini_with_fallback(prompt)
    if not response: return None
    data = _safe_json_loads(response.text, fallback=None)
    if not data:
        print("\n--- ERROR: GEMINI API FAILED TO RETURN VALID JSON (STRUCTURE) ---")
        return None
    return data

def categorize_skills_from_text(resume_text: str) -> Optional[Dict[str, List[str]]]:
    prompt = f"""
You are an expert technical recruiter and data analyst.
Your sole job is to scan the entire resume text provided and identify all skills, both technical and soft.
**Instructions:**
1.  Extract skills from *anywhere* in the text: summaries, project descriptions, a dedicated skills section, etc.
2.  Categorize the skills into the predefined keys in the JSON schema below.
3.  Place each skill only in the most appropriate category.
4.  If a category has no skills, you can omit the key from the output.
**JSON Output Schema:**
{{
    "Programming Languages": ["Python", "JavaScript", "Java", "C++", ...],
    "Frameworks and Libraries": ["TensorFlow", "PyTorch", "React", "Node.js", "Pandas", ...],
    "Databases": ["MySQL", "PostgreSQL", "MongoDB", ...],
    "Tools and Platforms": ["Git", "Docker", "AWS", "Jira", "Linux", ...],
    "Data Science": ["Machine Learning", "NLP", "Data Visualization", "Predictive Modeling", ...],
    "Soft Skills": ["Leadership", "Teamwork", "Communication", "Problem Solving", ...]
}}
**Critical Rules:**
- Your output must be ONLY the valid JSON object described above.
- Do not add any explanation or markdown.
--- RESUME TEXT ---
{resume_text}
--- END RESUME TEXT ---
"""
    response = _call_gemini_with_fallback(prompt)
    if not response: return None
    data = _safe_json_loads(response.text, fallback=None)
    if not data:
        print("\n--- ERROR: GEMINI FAILED TO INFER SKILLS ---")
        return None
    return data

def optimize_resume_json(resume_json: Dict[str, Any], user_input: str, job_description: Optional[str] = None) -> Dict[str, Any]:
    section_req, instruction = parse_user_optimization_input(user_input)
    keys_present = list(resume_json.keys())
    
    job_desc_context = ""
    if job_description and job_description.strip():
        job_desc_context = f"""
        **Job Description Context:**
        Below is the job description for which the resume is being optimized. Incorporate keywords, desired skills, and align the achievements to the requirements of this role.
        ```
        {job_description}
        ```
        """
    base_prompt_context = f"""
CONTEXT: You are an elite career strategist and executive resume writer. Your task is to transform a resume from a passive list of duties into a compelling narrative of achievements that will impress top-tier recruiters.
**Your Transformation Checklist (Apply to every relevant bullet point):**
1.  **Lead with a Powerful Action Verb:** Replace weak verbs with strong, specific verbs (e.g., "Engineered," "Architected," "Spearheaded").
2.  **Quantify Metrics Relentlessly:** Add concrete numbers to show scale and achievement.
3.  **Showcase Impact and Scope:** If a number isn't available, describe the tangible impact or business outcome.
4.  **Integrate Technical Skills Naturally:** Weave technologies into the story of the achievement.
5.  **Ensure Brevity and Clarity:** Remove filler words. Each bullet point should be a single, powerful line.

{job_desc_context} 

**Critical Rules:**
- **Do not modify, add, or delete any titles, names, companies, institutions, or skill names.** This is a strict rule. Only rewrite descriptions.
- DO NOT invent facts or skills.
- DO NOT invent specific numbers.
- Preserve the original data structure.
- Do not modify personal information (name, email, phone).
- Your final output must be only the requested, valid JSON. Do not include markdown.
"""
    if section_req:
        mapped = _best_section_key(section_req, keys_present)
        if not mapped: return resume_json
        sec_data = resume_json.get(mapped)
        prompt = f"""
{base_prompt_context}
TASK: Apply your full transformation checklist to optimize ONLY the following JSON section, named "{mapped}".
--- INPUT JSON SECTION ---
{json.dumps(sec_data, indent=2)}
--- END INPUT JSON ---
"""
    else:
        prompt = f"""
{base_prompt_context}
TASK: Apply your full transformation checklist to optimize all sections of the following resume JSON.
--- FULL INPUT JSON ---
{json.dumps(resume_json, indent=2)}
--- END INPUT JSON ---
"""
    response = _call_gemini_with_fallback(prompt)
    if not response: return resume_json
        
    optimized_data = _safe_json_loads(response.text, fallback=None)
    if not optimized_data:
        print("\n--- ERROR: GEMINI API FAILED TO RETURN VALID JSON (OPTIMIZE) ---")
        return resume_json
            
    if section_req and optimized_data:
        resume_json[mapped] = optimized_data
    elif optimized_data:
        for key, value in optimized_data.items():
            if key in resume_json: resume_json[key] = value

    return resume_json


def optimize_for_linkedin(resume_json: Dict[str, Any], user_input: str, job_description: Optional[str] = None) -> Optional[Dict[str, Any]]:
    context_text = []
    if 'summary' in resume_json: context_text.append(f"Summary:\n{resume_json['summary']}")
    
    all_experiences = resume_json.get('work_experience', []) + resume_json.get('internships', [])
    if all_experiences:
        context_text.append("\nProfessional Experience & Internships:")
        for job in all_experiences:
            description_str = ' '.join(job.get('description', []) if isinstance(job.get('description'), list) else [str(job.get('description', ''))])
            context_text.append(f"- {job.get('role')} at {job.get('company')}: {description_str}")
    
    if 'projects' in resume_json:
        context_text.append("\nProjects:")
        for project in resume_json['projects']:
            description_str = ' '.join(project.get('description', []) if isinstance(project.get('description'), list) else [str(project.get('description', ''))])
            context_text.append(f"- {project.get('title')}: {description_str}")
    
    if 'skills' in resume_json and isinstance(resume_json['skills'], dict):
        skills_summary = ", ".join([f"{cat}: {', '.join(skills)}" for cat, skills in resume_json['skills'].items()])
        context_text.append(f"\nSkills: {skills_summary}")
    
    for key, value in resume_json.items():
        if key not in ['personal_info', 'summary', 'work_experience', 'internships', 'projects', 'skills', 'education', 'certifications', 'resume_metadata', 'raw_text']:
            if isinstance(value, str):
                context_text.append(f"\n{key.replace('_', ' ').title()}:\n{value}")
            elif isinstance(value, list):
                context_text.append(f"\n{key.replace('_', ' ').title()}:\n" + "\n".join([str(item) for item in value]))

    resume_context = "\n".join(context_text)
    section_req, instruction = parse_user_optimization_input(user_input)

    job_desc_context = ""
    if job_description and job_description.strip():
        job_desc_context = f"""
        **Job Description Context:**
        Below is the job description for which the LinkedIn profile is being optimized. Align the content with the keywords, requirements, and tone of this role.
        ```
        {job_description}
        ```
        """
    
    base_prompt_context = f"""
You are an expert LinkedIn profile strategist and personal branding coach.
Your task is to generate compelling, optimized text for a user's LinkedIn profile based on the provided resume content.
**Instructions:**
1.  **Headlines:** Create 2-3 powerful, keyword-rich headline options.
2.  **About (Summary):** Write a compelling, first-person "About" section.
3.  **Experiences:** For EACH job/internship in the context, rewrite the bullet points to be concise and results-oriented.
4.  **Projects:** For EACH project in the context, rewrite its description to be engaging for a LinkedIn audience.

{job_desc_context}
**JSON Output Schema:**
{{
    "headlines": ["string option 1", ...],
    "about_section": "string",
    "optimized_experiences": [ {{ "title": "Role at Company", "description": "string" }} ],
    "optimized_projects": [ {{ "title": "Project Title", "description": "string" }} ]
}}

**Critical Rules:**
- Generate content ONLY from the provided resume context.
- Keep the tone professional but approachable.
- Your final output must be ONLY the valid JSON object that matches the requested task.
"""
    if section_req:
        instr_text = instruction or f"Make the {section_req} section more compelling and professional."
        prompt = f"""
{base_prompt_context}
TASK: Based on the resume context, optimize ONLY the '{section_req}' portion of a LinkedIn profile.
--- RESUME CONTEXT ---
{resume_context}
--- END RESUME CONTEXT ---
"""
    else:
        instr_text = instruction or "Optimize the entire LinkedIn profile, processing every experience and project."
        prompt = f"""
{base_prompt_context}
TASK: Based on the resume context, perform a full optimization of a LinkedIn profile.
--- RESUME CONTEXT ---
{resume_context}
--- END RESUME CONTEXT ---
"""

    response = _call_gemini_with_fallback(prompt)
    if not response: return None
    data = _safe_json_loads(response.text, fallback=None)
    if not data:
        print("\n--- ERROR: GEMINI FAILED TO INFER LINKEDIN CONTENT ---")
        return None
    return data

def generate_career_roadmap(user_profile: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    prompt = f"""
    Act as a world-class AI Career Strategist and Technical Project Manager. Your task is to generate a deeply personalized, multi-faceted career action plan.

    **STEP 1: ANALYZE THE USER'S PROFILE**
    - **User's Current State (from resume or manual input):** ```{user_profile.get('current_skills_input')}```
    - **Stated Current Proficiency:** {user_profile.get('current_level')}
    - **User's Stated Goal (Job Description or Desired Skills):** ```{user_profile.get('goal_input')}```
    - **Desired Goal Proficiency:** {user_profile.get('goal_level')}
    - **Time Commitment:** Plan for a duration of **{user_profile.get('duration')}**, assuming **{user_profile.get('study_hours')}** study hours per month.

    **STEP 2: GENERATE THE ACTION PLAN AS A SINGLE, VALID JSON OBJECT**
    The JSON output must be perfectly structured with the following keys. Do not include any explanatory text outside of the JSON object.

    1.  "domain": A single string representing the most relevant domain inferred from the goal input (e.g., "Data Science", "Cybersecurity"). This is a new, crucial key.
    2.  "extracted_skills_and_projects": A JSON object with "skills" (array of strings) and "projects" (array of strings).
    3.  "job_match_score": A JSON object with "score" (number) and "summary" (string).
    4.  "skills_to_learn_summary": An array of strings.
    5.  "timeline_chart_data": A JSON object with "labels" (array of strings) and "durations" (array of numbers in weeks) ans also the total weeks counts must be equal to users specified duration.
    6.  "detailed_roadmap": An array of "phase" objects, each with "phase_title", "phase_duration", and "topics" (array of strings).
    7.  "suggested_projects": An array of 2 "project" objects, each with "project_title", "project_level", "skills_mapped", "what_you_will_learn", and a multi-step "implementation_plan".
    8.  "suggested_courses": THIS IS A CRITICAL SECTION.
        - You MUST generate an array of 2-3 "course" objects.
        - Each object MUST contain the following FOUR keys: "course_name", "platform", "url", and "mapping".
        - The "platform" MUST be a string like "Coursera", "edX", "Pluralsight", etc.
        - The "url" MUST be a direct, fully-qualified, and workable hyperlink.
        - The "mapping" MUST be a concise sentence explaining how the course helps the roadmap.
        - **Follow this example format precisely:**
          `{{ "course_name": "Google Data Analytics Certificate", "platform": "Coursera", "url": "https://www.coursera.org/professional-certificates/google-data-analytics", "mapping": "This certificate covers the foundational skills in Phase 1 and 2." }}`
    """
    response = _call_gemini_with_fallback(prompt)
    if not response: return None
    cleaned_response_text = response.text.replace('```json', '').replace('```', '').strip()
    try:
        return json.loads(cleaned_response_text)
    except Exception as e:
        print(f"An error occurred during AI roadmap generation: {e}"); return None

def get_tutor_explanation(topic: str) -> Optional[Dict[str, Any]]:
    prompt = f"""
    Act as a friendly and encouraging expert tutor. A user is currently working through a personalized learning plan and is stuck on the following topic: **"{topic}"**

    Your task is to provide a clear, helpful explanation in a structured JSON format. The JSON object must have the following keys:

    1.  **"analogy"**: A simple, real-world analogy to help the user understand the core concept intuitively.
    2.  **"technical_definition"**: A concise, technically accurate definition. If the topic involves code, provide a short, well-commented code snippet in the appropriate language (e.g., Python, JavaScript).
    3.  **"prerequisites"**: An array of 1-3 prerequisite concepts the user might need to review. This helps them identify foundational knowledge gaps.

    Generate the JSON object and nothing else.
    """

    response = _call_gemini_with_fallback(prompt)
    if not response: return None
    cleaned_response_text = response.text.replace('```json', '').replace('```', '').strip()
    try:
        return json.loads(cleaned_response_text)
    except Exception as e:
        print(f"An error occurred in AI Tutor: {e}"); return None

def get_chatbot_response(query: str, history: list, career_plan_summary: str) -> dict:
    """
    Generates a chatbot response using the pre-summarized career plan string as context.
    
    Args:
        query: The user's latest question.
        history: The previous conversation history.
        career_plan_summary: A PRE-SUMMARIZED STRING of the user's career plan.
    """
    print("AI Core: Received request. The career plan context is a string.")
    
    system_prompt = (
        f"You are an AI career strategist and tutor. Your purpose is to provide concise, point-to-point, and beginner-friendly guidance to the user, strictly based on the career plan provided below.\n\n"
        f"**Career Plan Details:**\n{career_plan_summary}\n\n"
        f"**Your Instructions:**\n"
        f"1. Keep responses brief, beginner-friendly, and to the point.\n"
        f"2. You can answer questions related to the provided career plan, including the **job match score, priority skills, timeline, detailed roadmap, projects, and courses**.\n"
        f"3. If the user asks a question that is **outside the scope** of the career plan's domain or is not directly related to the provided plan data, you must respond with a polite refusal. For example, 'That question seems to be outside the scope of your current career plan. Is there anything I can help you with related to your career plan?'\n\n"
        f"Let's begin."
    )
    model_history = []
    for message in history:
        role = 'user' if message.get('role') == 'user' else 'model'
        content = message.get('content', '')
        if content: model_history.append({'role': role, 'parts': [content]})

    full_prompt = f"{system_prompt}\n\nUSER QUESTION: {query}"
    response = _call_gemini_with_fallback(prompt=full_prompt, is_chat=True, history=model_history)

    if not response or not response.text:
        raise Exception("AI response failed after trying all API keys.")
    return {"response": response.text}

def generate_assessment_questions(assessment_type: str, skills: List[str], target_role: Optional[str] = None, num_questions: int = 5, user_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """
    Generates a set of assessment questions based on selected skills and target role.
    Uses Gemini Flash.
    """
    
    skills_str = ", ".join(skills)
    role_context = f" for a {target_role}" if target_role else ""

    difficulty_hint = "medium difficulty"
    normalized_role = (target_role or "").lower()
    if "junior" in normalized_role:
        difficulty_hint = "beginner to medium difficulty"
    elif "senior" in normalized_role or "lead" in normalized_role:
        difficulty_hint = "medium to advanced difficulty"


    prompt = f"""
    You are an expert technical interviewer and AI assessment designer.
    Your task is to generate a concise, focused skill assessment with exactly {num_questions} questions.
    The assessment should cover the following skills: **{skills_str}**.
    The target context is {assessment_type.replace('_', ' ').title()} role{role_context}, at a {difficulty_hint} level.

    **Instructions for Question Generation:**
    1.  Generate a mix of question types:
        -   **Single-choice (radio buttons):** ~50% of questions. Provide 4 distinct options.
        -   **Multiple-choice (checkboxes):** ~20% of questions. Provide 4 distinct options, clearly indicating ALL correct answers.
        -   **Short-answer:** ~20% of questions. Requires a concise text response.
        -   **Coding challenge:** ~10% of questions. Provide a clear problem statement and expected output/logic. (If this is too complex for 1.5-flash to reliably generate, favor more short-answer).
    2.  Ensure questions cover both theoretical understanding and practical application of the skills.
    3.  Assign a unique `question_id` (e.g., "q1", "q2") to each question.
    4.  For each multiple/single choice question, you MUST provide the `correct_answer_keys` (a list of option values that are correct). This is CRITICAL for automated grading.
    
    **JSON Output Schema (List of Question Objects):**
{ASSESSMENT_QUESTIONS_SCHEMA.strip()}
    **Critical Rules:**
    - Your final output MUST be a JSON array containing exactly {num_questions} question objects.
    - DO NOT include any introductory or concluding text outside the JSON.
    - Ensure `correct_answer_keys` is always a LIST, even if only one answer.
    """

    response = _call_gemini_with_fallback(prompt)
    if not response: return None
    questions = _safe_json_loads(response.text, fallback=None)
    if not questions or not isinstance(questions, list):
        print("\n--- ERROR: GEMINI FAILED TO GENERATE VALID ASSESSMENT QUESTIONS ---")
        return None
    return {"questions": questions}

def evaluate_assessment_answers(user_id: str, submitted_answers: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """
    Evaluates user's assessment answers using Gemini Flash and provides structured results.
    """

    answers_summary = []
    for ans in submitted_answers:
        q_id = ans.get("question_id", "N/A")
        user_response = ans.get("answer")
        
        if isinstance(user_response, list):
            user_response_str = ", ".join(user_response)
        elif user_response is None:
            user_response_str = "No answer provided"
        else:
            user_response_str = str(user_response)
        
        answers_summary.append(f"Question ID: {q_id}\nUser Answer: ```{user_response_str}```\n---")

    answers_text = "\n".join(answers_summary)

    prompt = f"""
    You are an expert technical interviewer and AI grader.
    Your task is to evaluate a user's submitted answers for a skill assessment.
    Provide a comprehensive, structured evaluation based on the answers provided.

    **Instructions for Evaluation:**
    1.  **Calculate Overall Score:** Assign an overall percentage score (0-100%) for the assessment.
    2.  **Identify Skills Mastered/Areas to Improve (Counts):** Based on the questions and answers, estimate how many distinct skills were demonstrated proficiently and how many need significant improvement.
    3.  **List Strengths:** Provide 2-3 specific bullet points highlighting what the user did well.
    4.  **List Weaknesses:** Provide 2-3 specific bullet points highlighting areas where the user struggled or demonstrated gaps.
    5.  **Personalized Recommendations:** Provide 2-3 actionable, general recommendations for improvement. These should be text-based recommendations, not URLs.

    **User's Submitted Answers:**
    {'-'*30}
    {answers_text}
    {'-'*30}

    **JSON Output Schema:**
{ASSESSMENT_EVALUATION_SCHEMA.strip()}
    **Critical Rules:**
    - Your final output MUST be a single, valid JSON object following the schema.
    - DO NOT include any introductory or concluding text outside the JSON.
    - The `skill_scores` should be an object mapping skill names (e.g., Python, SQL) to a proficiency score (0-100). Infer these skills from the context of the assessment.
    """
    response = _call_gemini_with_fallback(prompt)
    if not response: return None
    results = _safe_json_loads(response.text, fallback=None)
    if not results or not isinstance(results, dict):
        print("\n--- ERROR: GEMINI FAILED TO EVALUATE ASSESSMENT ANSWERS ---")
        return None
    return results

def generate_full_resume_analysis(resume_text: str, job_description: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """
    Generates a comprehensive resume analysis report, including overall score,
    ATS score, strengths, areas for improvement, and section-wise feedback.
    """
    job_desc_context = ""
    job_role_hint = "General Candidate"  # Default value

    # --- MODIFIED SECTION ---
    # This block now uses the robust fallback function to get the job role.
    if job_description and job_description.strip():
        job_desc_context = f"""
    The user has provided a job description. Analyze the resume specifically against this job description
    to provide highly tailored feedback, especially for ATS optimization, strengths, and areas for improvement.
    Infer the primary 'Job Role' from this description.

    **Job Description:**
    ```
    {job_description}
    ```
    """
        # A simple AI call to infer job role, now using the fallback mechanism.
        role_prompt = f"Extract the primary job role from the following job description. Respond with only the job role text (e.g., 'Software Engineer', 'Data Scientist', 'Frontend Developer').\n\nJob Description: {job_description}"
        
        role_response = _call_gemini_with_fallback(role_prompt) # Using the new fallback function here.
        
        if role_response and role_response.text:
            inferred_role = role_response.text.strip()
            if inferred_role and len(inferred_role.split()) < 5:  # Basic check for validity
                job_role_hint = inferred_role
        else:
             print(f"Warning: Could not infer job role from JD. Using default.")
    # --- END MODIFIED SECTION ---


    # This is your original main prompt, it remains unchanged.
    prompt = f"""
    You are an expert HR consultant and AI resume analyst. Your task is to provide a comprehensive analysis of the given resume.
    Generate a detailed report covering overall assessment, specific section analyses, key strengths, areas for improvement,
    and a dedicated ATS optimization score, all in a single JSON object.

    **Instructions:**
    1.  **Analysis Date:** Current date (e.g., "September 05, 2025").
    2.  **Job Role Context:** Infer a primary job role from the provided job description (if any) or from the resume itself. Default to "General Candidate" if unclear.
    3.  **AI Model:** "Google Gemini"
    4.  **Overall Resume Score:** A percentage (0-100) reflecting general quality, clarity, and effectiveness.
    5.  **Overall Resume Grade:** A concise word (e.g., "Excellent", "Good", "Fair", "Needs Improvement") corresponding to the score.
    6.  **ATS Optimization Score:** A percentage (0-100) reflecting compatibility with Applicant Tracking Systems, especially considering the job description.
    7.  **Section-wise Analysis:** Provide a 'title' and 'summary' for:
        -   `professional_profile_analysis`: For the summary/objective section.
        -   `education_analysis`: For the education section.
        -   `experience_analysis`: For work experience and projects.
        -   `skills_analysis`: For the skills section.
    8.  **Key Strengths:** 2-3 bullet points highlighting positive aspects.
    9.  **Areas for Improvement:** 3-5 bullet points covering general resume improvements AND specific ATS issues (e.g., keyword gaps, formatting problems).
    10. **Overall Assessment:** A concluding paragraph summarizing the findings and potential for improvement.

    {job_desc_context}

    **Resume Text:**
    ```
    {resume_text}
    ```

    **JSON Output Schema:**
{FULL_RESUME_ANALYSIS_SCHEMA.strip()}
    **Critical Rules:**
    - Your final output MUST be a single, valid JSON object following the schema.
    - DO NOT include any introductory or concluding text outside the JSON.
    - Ensure all scores are integers (0-100).
    - If no job description is provided, make reasonable general assumptions for the 'Job Role Context' and ATS analysis.
    - For `analysis_date`, always use the current date in 'Month DD, YYYY' format.
    - For section summaries, be direct and actionable, similar to the provided examples.
    """
    
    # --- MODIFIED SECTION ---
    # The main API call for the analysis also uses the fallback function now.
    response = _call_gemini_with_fallback(prompt)
    if not response:
        return None # Return None if all API keys fail.
    
    analysis_data = _safe_json_loads(response.text, fallback=None)
    
    if not analysis_data or not isinstance(analysis_data, dict):
        print("\n--- ERROR: GEMINI FAILED TO GENERATE VALID FULL RESUME ANALYSIS ---")
        print("API Response Text:", response.text)
        try: print("API Prompt Feedback:", response.prompt_feedback)
        except ValueError: pass
        print("------------------------------------------------------------------\n")
        return None
    
    # Override job_role_context with the one we inferred earlier.
    if job_role_hint != "General Candidate": 
        analysis_data['job_role_context'] = job_role_hint
    
    # Ensure analysis_date is always current, regardless of what the AI generates.
    analysis_data['analysis_date'] = datetime.now().strftime("%B %d, %Y")

    return analysis_data
    # --- END MODIFIED SECTION ---

def get_interview_chat_response(job_description: str, history: List[Dict[str, str]], difficulty: str) -> Optional[Dict[str, str]]:
    """
    Acts as an AI Interviewer with adjustable difficulty, now with API key fallback.
    """
    # This is your original logic to determine the AI's personality based on difficulty.
    # It remains completely unchanged.
    if difficulty == 'easy':
        personality_prompt = """
        Your Persona: You are a friendly and encouraging hiring manager for an entry-level role.
        Your Goal: Understand the candidate's basic knowledge and potential. Ask foundational, single-topic conceptual questions (e.g., "In Python, what is the difference between a list and a tuple?").
        Your Tone: Supportive and patient.
        Your First Action: Start with a simple, welcoming question like "Thanks for coming in. To start, could you tell me about a project you're proud of that's relevant to this role?"
        """
    elif difficulty == 'hard':
        personality_prompt = """
        Your Persona: You are a sharp, direct senior engineer conducting a final-round interview.
        Your Goal: Rigorously test the candidate's deep technical expertise, problem-solving, and system design skills. Ask challenging, multi-part, or scenario-based questions (e.g., "Given the requirements in the job description, walk me through how you would design a scalable, resilient API for our service. What bottlenecks would you anticipate and how would you mitigate them?").
        Your Tone: Critical, professional, and expecting detailed answers. You will ask tough follow-up questions.
        Your First Action: Start directly with a challenging technical question based on a core skill from the job description.
        """
    else: # Default to Medium
        personality_prompt = """
        Your Persona: You are a professional team lead for a mid-level role.
        Your Goal: Assess the candidate's practical skills and real-world project experience. Ask behavioral and technical questions that require specific examples (e.g., "Tell me about a time you had to deal with significant technical debt. How did you handle it and what was the outcome?").
        Your Tone: Objective and focused.
        Your First Action: Start with a question about the candidate's most relevant experience from their resume, tying it to the job description.
        """

    # This is your original logic for preparing the chat history.
    # It also remains completely unchanged.
    formatted_history = [{'role': msg['role'], 'parts': [{'text': msg['content']}]} for msg in history]
    system_instruction = f"""
    {personality_prompt}
    
    CRITICAL RULE: You are the INTERVIEWER. The user is the CANDIDATE. You must conduct a realistic interview.
    Base ALL of your questions and analysis strictly on the provided job description context below. Do not ask about skills not mentioned.

    --- JOB DESCRIPTION CONTEXT ---
    {job_description}
    --- END CONTEXT ---
    """
    full_history = [
        {'role': 'user', 'parts': [{'text': system_instruction}]},
        {'role': 'model', 'parts': [{'text': "Understood. I am ready to begin the interview."}]}
    ] + formatted_history
    
    # --- MODIFIED SECTION ---
    # Instead of the try/except block, we now prepare the arguments for our new fallback function.
    
    # The 'prompt' is the newest message from the user.
    last_user_message = full_history[-1]['parts'][0]['text']
    
    # The 'history' is everything that came before the user's newest message.
    chat_history_for_api = full_history[:-1]
    
    # Call our resilient fallback function with the chat parameters.
    response = _call_gemini_with_fallback(
        prompt=last_user_message, 
        is_chat=True, 
        history=chat_history_for_api
    )

    # Check the result and return the appropriate response.
    if not response or not response.text:
        print(f"An error occurred in the interview chat endpoint after all fallbacks.")
        return None # Return None on total failure

    return {"reply": response.text}
    # --- END MODIFIED SECTION ---

def get_interview_summary(job_description: str, history: List[Dict[str, str]]) -> Optional[Dict[str, Any]]:
    """
    Analyzes the full interview transcript and provides a performance summary,
    now with API key fallback.
    """
    # This is your original logic for creating the transcript. It remains unchanged.
    transcript = "\n".join([f"{msg['role']}: {msg['content']}" for msg in history])

    # This is your original, detailed prompt for the AI. It also remains unchanged.
    prompt = f"""
    You are an expert career coach and technical recruiter. Your task is to analyze the following mock interview transcript and provide a performance summary.
    
    **Job Description Context:**
    ```
    {job_description}
    ```

    **Interview Transcript:**
    ```
    {transcript}
    ```

    **Your Analysis Task:**
    Based on the job description and the transcript, provide a detailed analysis in a valid JSON object. The JSON must have the following keys:
    1.  `"overall_score"`: An integer from 0 to 100 representing the candidate's overall performance.
    2.  `"strengths"`: A list of 2-3 specific, positive points about the candidate's performance, citing examples from the transcript.
    3.  `"areas_for_improvement"`: A list of 2-3 specific, constructive points for improvement, citing examples.
    4.  `"overall_feedback"`: A concise paragraph summarizing the performance and providing a final recommendation.

    **Critical Rules:**
    - Your final output must be ONLY the valid JSON object. Do not include markdown or any other text.
    - Be honest and constructive in your feedback.
    """
    # 1. Call the API using our new fallback function.
    response = _call_gemini_with_fallback(prompt)

    # 2. Handle the case where all API keys failed.
    if not response or not response.text:
        print("Error generating interview summary after all fallbacks.")
        return None

    # 3. Process the successful response just like before.
    summary_data = _safe_json_loads(response.text, fallback=None)
    
    if not summary_data:
        print("\n--- ERROR: GEMINI FAILED TO GENERATE VALID INTERVIEW SUMMARY (even with a successful API call) ---")
        print("API Response Text:", response.text)
        return None

    return summary_data
    # --- END MODIFIED SECTION ---```


def save_resume_json_to_docx(resume_json: Dict[str, Any]) -> Document:
    doc = Document()
    def add_heading(text: Optional[str], level: int = 1):
        t = (text or "").strip(); 
        if t: h = doc.add_heading(t, level=level); h.alignment = WD_ALIGN_PARAGRAPH.LEFT
    def add_para(text: Optional[str], bold: bool = False, style: Optional[str] = None):
        t = (text or "").strip() 
        if t:
            p = doc.add_paragraph(style=style)
            run = p.add_run(t)
            run.bold = bold
            run.font.size = Pt(11)
            if style == "List Bullet": p.paragraph_format.left_indent = Pt(36)
            
    print_order = ['personal_info', 'summary', 'skills', 'work_experience', 'internships', 'projects', 'education', 'certifications']
    
    name_for_title = resume_json.get('personal_info', {}).get('name', '')
    if name_for_title:
        doc.add_heading(name_for_title, level=0)

    contact_info_parts = []
    p_info = resume_json.get('personal_info', {})
    if p_info.get('email'): contact_info_parts.append(p_info['email'])
    if p_info.get('phone'): contact_info_parts.append(p_info['phone'])
    if p_info.get('linkedin'): contact_info_parts.append(p_info['linkedin'])
    if p_info.get('github'): contact_info_parts.append(p_info['github'])
    if contact_info_parts:
        add_para(_smart_join(contact_info_parts))
    
    for section in print_order:
        if section in resume_json:
            content = resume_json[section]
            if section == 'personal_info':
                continue
            
            add_heading(section.replace("_", " ").title(), level=2)
            
            if section == 'summary' and isinstance(content, str):
                add_para(content)
            elif section == 'skills' and isinstance(content, dict):
                for category, skill_list in content.items():
                    if isinstance(skill_list, list) and skill_list:
                        p = doc.add_paragraph();
                        run = p.add_run(category.replace("_", " ").title() + ': '); run.bold = True
                        p.add_run(", ".join(skill_list)); 
            elif isinstance(content, list):
                for item in content:
                    if isinstance(item, str):
                        add_para(item, style="List Bullet")
                    elif isinstance(item, dict):
                        # Ensure any dates/timestamps within item are converted to string before joining/displaying
                        item_copy = item.copy()
                        for k, v in item_copy.items():
                            if isinstance(v, datetime): # CORRECTED: Check for datetime.datetime objects
                                item_copy[k] = v.strftime("%b %d, %Y") # Format as readable string
                        
                        header_parts = [item_copy.get("title"), item_copy.get("name"), item_copy.get("role"), item_copy.get("degree"), item_copy.get("institution")]
                        header = _smart_join(header_parts)
                        if header: add_para(header, bold=True)
                        
                        sub_header_parts = [item_copy.get("company"), item_copy.get("duration")]
                        sub_header = _smart_join(sub_header_parts)
                        if sub_header: add_para(sub_header)
                        
                        desc = item_copy.get("description", [])
                        if isinstance(desc, list):
                            for bullet in desc:
                                if _norm(bullet): add_para(str(bullet), style="List Bullet")
                        elif isinstance(desc, str) and _norm(desc):
                            add_para(str(desc), style="List Bullet")

            elif isinstance(content, str):
                add_para(content)
            
    for section, content in resume_json.items():
        if section not in print_order and section not in ['resume_metadata', 'raw_text','optimized_summary']:
            add_heading(section.replace("_", " ").title(), level=2)
            if isinstance(content, list):
                for item in content: add_para(str(item), style="List Bullet")
            else: add_para(str(content))
            
    print("\n✅ DOCX document generated in memory.")
    return doc
