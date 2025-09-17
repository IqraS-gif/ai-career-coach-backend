import os
import sys
import json
import re
from typing import Optional, Tuple, Dict, Any, List
from datetime import datetime

from fastapi.params import Query
import firebase_admin
from firebase_admin import firestore

def _stringify_list_content(content: Any) -> str:
    """Safely converts a list of strings or dicts into a single newline-separated string."""
    if not isinstance(content, list): return str(content or "")
    string_parts = []
    for item in content:
        if isinstance(item, str): string_parts.append(item)
        elif isinstance(item, dict):
            string_parts.append(", ".join([f"{k.replace('_', ' ').title()}: {v}" for k, v in item.items()]))
        else: string_parts.append(str(item))
    return "\n".join(string_parts)

def _convert_firestore_timestamps(obj: Any) -> Any:
    """
    Recursively converts Firestore DatetimeWithNanoseconds objects (and standard datetime objects)
    to ISO 8601 strings to make them JSON serializable.
    """
    if isinstance(obj, dict):
        return {k: _convert_firestore_timestamps(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [_convert_firestore_timestamps(elem) for elem in obj]
    elif isinstance(obj, datetime): # Corrected: Changed from datetime.datetime to just datetime
        return obj.isoformat()
    # If it's not a dict, list, or datetime object, return it as is
    return obj


class DatabaseManager:
    """
    Handles all interactions with the Firebase Firestore database.
    Assumes Firebase Admin SDK has already been initialized by main.py.
    """

    _standard_to_db_collections_map = {
        'work_experience': 'work_experiences',
        'education': 'education',
        'projects': 'projects',
        'internships': 'internships',
        'certifications': 'certifications',
        'skills': 'skills',
        'additional_sections': 'additional_sections'
    }

    _ai_key_to_standard_map = {
        'personal_info': ['personal_info'],
        'summary': ['summary'],
        'work_experience': ['work_experience', 'professional_experience', 'experience', 'work_history'],
        'education': ['education', 'academic_background'],
        'projects': ['projects', 'personal_projects'],
        'internships': ['internships', 'internship_experience'],
        'certifications': ['certifications', 'licenses_&_certifications'],
        'skills': ['skills'],
    }

    def __init__(self):
        """
        Initializes the DatabaseManager.
        It expects firebase_admin.initialize_app() to have been called already by main.py.
        """
        try:
            self.db = firestore.client()
        except Exception as e:
            print(f"❌ ERROR: DatabaseManager failed to get Firestore client. Is Firebase Admin SDK initialized? {e}")
            raise 

    def _map_ai_section_to_standard_key(self, ai_key: str) -> Optional[str]:
        normalized_key = ai_key.lower().replace(" ", "_").replace("-", "_")
        for standard_key, variations in self._ai_key_to_standard_map.items():
            if normalized_key in variations: return standard_key
        return None
    
    def fetch_resume_relational(self, user_uid: str, get_optimized: bool = False) -> Optional[Dict[str, Any]]:
        user_doc_ref = self.db.collection('users').document(user_uid)
        user_doc = user_doc_ref.get()

        if not user_doc.exists:
            print(f"User document with UID {user_uid} not found.")
            return None

        user_data = user_doc.to_dict()
        
        # Apply the conversion to the entire user_data dictionary once, immediately after fetching.
        user_data = _convert_firestore_timestamps(user_data) 

        resume_data: Dict[str, Any] = {}

        # Fetch top-level personal info
        personal_info = {
            'name': user_data.get('name'),
            'email': user_data.get('email'),
            'phone': user_data.get('phone'),
            'linkedin': user_data.get('linkedin'),
            'github': user_data.get('github')
        }
        if any(v for v in personal_info.values() if v is not None and v != ''):
            resume_data['personal_info'] = personal_info

        # Fetch the stored raw text and metadata
        raw_resume_text = user_data.get('raw_resume_text')
        if raw_resume_text:
            resume_data['raw_text'] = raw_resume_text

        resume_metadata = user_data.get('resume_metadata')
        if resume_metadata:
            resume_data['resume_metadata'] = resume_metadata

        # NEW: Fetch saved structured_resume_data and categorized_skills directly
        structured_resume_data = user_data.get('structured_resume_data')
        categorized_skills = user_data.get('categorized_skills')

        if structured_resume_data:
            resume_data.update(structured_resume_data) # Add all structured fields
            if categorized_skills:
                resume_data['skills'] = categorized_skills # Override with categorized skills if present

        # Get summary, prioritizing optimized if requested and available (from legacy 'resume' map or current 'summary' field)
        summary_to_use = None
        if get_optimized:
            # Check current structured data first
            if resume_data.get('optimized_summary'):
                summary_to_use = resume_data['optimized_summary']
            elif user_data.get('resume', {}).get('optimized_summary'): # Fallback to legacy field
                summary_to_use = user_data.get('resume', {}).get('optimized_summary')
        
        if not summary_to_use: # If no optimized summary, use the base summary
            if resume_data.get('summary'):
                summary_to_use = resume_data['summary']
            elif user_data.get('resume', {}).get('summary'): # Fallback to legacy field
                summary_to_use = user_data.get('resume', {}).get('summary')

        if summary_to_use:
            resume_data['summary'] = summary_to_use


        # --- Fetch sub-collection data ---
        # This part ensures that if structured_resume_data (above) didn't fully capture
        # all sub-collection details (e.g., if you only store a summary of projects there),
        # these individual documents are still fetched. However, if structured_resume_data
        # already contains the full list for a section, this might be redundant or require
        # careful merging. For now, it overrides with sub-collection details.
        for standard_key, collection_name in self._standard_to_db_collections_map.items():
            if standard_key in ['skills', 'additional_sections']:
                continue 
            
            docs = user_doc_ref.collection(collection_name).stream()
            data_list = []
            for doc in docs:
                item_data = doc.to_dict()
                item_data = _convert_firestore_timestamps(item_data) # Apply conversion to each sub-collection item

                desc_to_use = (
                    item_data.get('optimized_description')
                    if get_optimized and item_data.get('optimized_description')
                    else item_data.get('description')
                )
                
                item = {k: v for k, v in item_data.items() if k not in ['optimized_description', 'description']}
                
                if desc_to_use:
                    item['description'] = desc_to_use.split('\n') if isinstance(desc_to_use, str) else desc_to_use
                
                data_list.append(item)
            if data_list:
                resume_data[standard_key] = data_list

        # Skills (explicitly fetched from sub-collection even if top-level exists, for optimized_data view)
        # Note: This will override any 'skills' key from structured_resume_data fetched earlier if present.
        # This prioritizes the detailed sub-collection for the optimized view.
        docs = user_doc_ref.collection(self._standard_to_db_collections_map['skills']).stream()
        skills_dict: Dict[str, Any] = {}
        for doc in docs:
            item = doc.to_dict()
            item = _convert_firestore_timestamps(item) # Apply conversion
            category = item.get('category')
            skill_name = item.get('skill_name')
            if category and skill_name:
                if category not in skills_dict:
                    skills_dict[category] = []
                skills_dict[category].append(skill_name)
        if skills_dict:
            resume_data['skills'] = skills_dict;

        # Additional sections
        docs = user_doc_ref.collection(self._standard_to_db_collections_map['additional_sections']).stream()
        for doc in docs:
            item = doc.to_dict()
            item = _convert_firestore_timestamps(item) # Apply conversion
            desc_to_use = (
                item.get('optimized_description')
                if get_optimized and item.get('optimized_description')
                else item.get('description')
            )
            section_name = item.get('section_name')
            if section_name and desc_to_use:
                resume_data[section_name] = desc_to_use.split('\n') if isinstance(desc_to_use, str) else desc_to_use

        return {k: v for k, v in resume_data.items() if v}

    def update_resume_relational(self, user_uid: str, parsed_data: Dict[str, Any]) -> bool:
        """
        Updates resume data and clears/re-inserts sub-collections.
        Intended for initial uploads or when structured data needs full refresh.
        """
        try:
            user_doc_ref = self.db.collection('users').document(user_uid)
            
            user_doc_ref.set({'lastUpdatedAt': firestore.SERVER_TIMESTAMP}, merge=True)
            print(f" -> Ensured user document exists for {user_uid}")

            collections_to_delete = list(self._standard_to_db_collections_map.values())
            for coll_name in collections_to_delete:
                docs = user_doc_ref.collection(coll_name).stream()
                for doc in docs:
                    doc.reference.delete()
            print(f" -> Cleared old resume sub-collections for user {user_uid}")

            p_info = parsed_data.get('personal_info', {})
            
            update_fields = {
                'name': p_info.get('name'),
                'email': p_info.get('email'),
                'phone': p_info.get('phone'),
                'linkedin': p_info.get('linkedin'),
                'github': p_info.get('github'),
                'raw_resume_text': parsed_data.get('raw_text'),
                'resume_metadata': parsed_data.get('resume_metadata'),
                'structured_resume_data': {k:v for k,v in parsed_data.items() if k not in ['skills', 'raw_text', 'resume_metadata']}, # Save core structured data
                'categorized_skills': parsed_data.get('skills'), # Save categorized skills
                'resume.summary': parsed_data.get('summary'), # Keep for backwards compatibility
                'resume.optimized_summary': None, # Reset optimized summary
                'lastUpdatedAt': firestore.SERVER_TIMESTAMP
            }

            filtered_update_fields = {k: v for k, v in update_fields.items() if v is not None}
            if 'resume' in filtered_update_fields and isinstance(filtered_update_fields['resume'], dict):
                filtered_update_fields['resume'] = {k: v for k, v in filtered_update_fields['resume'].items() if v is not None}
            
            user_doc_ref.update(filtered_update_fields)
            print(f" -> Updated main user document for {user_uid} with personal info, raw text, metadata, structured data, and summary.")

            for ai_section_key, section_content in parsed_data.items():
                if ai_section_key in ['personal_info', 'summary', 'skills', 'resume_metadata', 'raw_text', 'optimized_summary']:
                    continue
                
                standard_key = self._map_ai_section_to_standard_key(ai_section_key)
                
                if standard_key and standard_key in self._standard_to_db_collections_map:
                    collection_name = self._standard_to_db_collections_map[standard_key]
                    if isinstance(section_content, list):
                        for item in section_content:
                            if isinstance(item, dict):
                                item_to_save = item.copy()
                                if 'description' in item_to_save:
                                    item_to_save['description'] = _stringify_list_content(item_to_save['description'])
                                item_to_save['optimized_description'] = None
                                user_doc_ref.collection(collection_name).add(item_to_save)
                else: # For custom/additional sections
                    description = _stringify_list_content(section_content)
                    user_doc_ref.collection(self._standard_to_db_collections_map['additional_sections']).add({
                        'section_name': ai_section_key,
                        'description': description,
                        'optimized_description': None
                    })
            
            # Skills are saved as a top-level field 'categorized_skills', no longer separate sub-collection
            # if 'skills' in parsed_data and isinstance(parsed_data['skills'], dict):
            #     for category, skill_list in parsed_data['skills'].items():
            #         if isinstance(skill_list, list):
            #             for skill_name in skill_list:
            #                 user_doc_ref.collection(self._standard_to_db_collections_map['skills']).add({'category': category, 'skill_name': skill_name})
            
            print(f" -> Successfully re-inserted new resume sub-collection data for user {user_uid}.")
            return True

        except Exception as e:
            print(f"Error updating resume for user {user_uid}: {e}")
            return False

    # REMOVED: update_resume_metadata function (no longer needed)

    def update_optimized_resume_relational(self, user_uid: str, optimized_data: Dict[str, Any]):
        user_doc_ref = self.db.collection('users').document(user_uid)

        # Update the summary field in the top-level structured_resume_data
        if 'summary' in optimized_data:
            user_doc_ref.update({'structured_resume_data.summary': optimized_data['summary']})
            user_doc_ref.update({'structured_resume_data.optimized_summary': optimized_data['summary']}) # Store optimized summary directly

        # This part iterates sub-collections and updates 'optimized_description'
        def update_item_optimized_description(collection_name: str, items: list, match_keys: list):
            for item_to_match in items:
                optimized_desc_str = _stringify_list_content(item_to_match.get('description', []))
                
                query = user_doc_ref.collection(collection_name)
                for key in match_keys:
                    if item_to_match.get(key):
                        query = query.where(key, '==', item_to_match.get(key))
                
                docs = query.limit(1).stream()
                for doc in docs:
                    doc.reference.update({'optimized_description': optimized_desc_str})

        if 'work_experience' in optimized_data: update_item_optimized_description(self._standard_to_db_collections_map['work_experience'], optimized_data['work_experience'], ['role', 'company'])
        if 'education' in optimized_data: update_item_optimized_description(self._standard_to_db_collections_map['education'], optimized_data['education'], ['institution', 'degree'])
        if 'projects' in optimized_data: update_item_optimized_description(self._standard_to_db_collections_map['projects'], optimized_data['projects'], ['title'])
        if 'internships' in optimized_data: update_item_optimized_description(self._standard_to_db_collections_map['internships'], optimized_data['internships'], ['role', 'company'])
        if 'certifications' in optimized_data: update_item_optimized_description(self._standard_to_db_collections_map['certifications'], optimized_data['certifications'], ['name'])

        for key, content in optimized_data.items():
            if self._map_ai_section_to_standard_key(key) is None and key not in ['personal_info', 'summary', 'skills', 'resume_metadata', 'raw_text', 'structured_resume_data', 'categorized_skills', 'optimized_summary']:
                optimized_desc_str = _stringify_list_content(content)
                docs = user_doc_ref.collection(self._standard_to_db_collections_map['additional_sections']).where('section_name', '==', key).limit(1).stream()
                for doc in docs:
                    doc.reference.update({'optimized_description': optimized_desc_str})
        
        user_doc_ref.update({'lastUpdatedAt': firestore.SERVER_TIMESTAMP})
        print(f" -> Optimized data for user UID {user_uid} has been fully updated in Firestore.")

    def close_connection(self):
        pass


    # NEW/MODIFIED: Function to safely increment user statistics
    def increment_user_stat(self, uid: str, stat_name: str, increment_by: int = 1):
        user_doc_ref = self.db.collection('users').document(uid)
        try:
            # Check if 'stats' map exists and is a dictionary
            user_doc = user_doc_ref.get()
            if not user_doc.exists:
                # If document doesn't exist, create it with initial stats
                print(f"ℹ️ User document for {uid} does not exist. Creating with initial stats.")
                user_doc_ref.set({
                    'stats': {
                        'roadmaps_generated': 0,
                        'resumes_optimized': 0,
                        'assessments_taken': 0,
                        'jobs_matched': 0,
                        stat_name: firestore.Increment(increment_by) # Include current increment
                    }
                })
            else:
                user_data = user_doc.to_dict()
                if 'stats' not in user_data or not isinstance(user_data['stats'], dict):
                    # If 'stats' is missing or not a dict, initialize it safely
                    print(f"ℹ️ 'stats' field missing or malformed for {uid}. Initializing and setting stat.")
                    user_doc_ref.update({
                        'stats': {
                            'roadmaps_generated': 0,
                            'resumes_optimized': 0,
                            'assessments_taken': 0,
                            'jobs_matched': 0,
                            stat_name: firestore.Increment(increment_by) # Include current increment
                        }
                    })
                else:
                    # 'stats' map exists, proceed with incrementing the specific field
                    user_doc_ref.update({
                        f'stats.{stat_name}': firestore.Increment(increment_by)
                    })
            print(f"✅ Incremented stat '{stat_name}' for user {uid} by {increment_by}.")
        except Exception as e:
            print(f"❌ Critical Error incrementing stat '{stat_name}' for user {uid}: {e}")
            raise # Re-raise to ensure error is propagated

    # NEW: Helper methods to call increment_user_stat for specific actions
    def record_resume_optimization(self, uid: str):
        self.increment_user_stat(uid, 'resumes_optimized', 1)

    def record_roadmap_generation(self, uid: str):
        self.increment_user_stat(uid, 'roadmaps_generated', 1)

    def record_assessment_taken(self, uid: str):
        self.increment_user_stat(uid, 'assessments_taken', 1)

    def record_jobs_matched(self, uid: str, num_jobs: int = 1):
        self.increment_user_stat(uid, 'jobs_matched', num_jobs)




    # MODIFIED LOGIC: This function now deletes all previous roadmaps before creating the new one.
    async def save_user_roadmap(self, user_uid: str, new_roadmap_data: Dict[str, Any]) -> bool:
        """
        Ensures only one roadmap exists by deleting all previous roadmap documents
        for the user before creating the new one.
        """
        try:
            roadmaps_collection = self.db.collection('users').document(user_uid).collection('roadmaps')
            
            # Step 1: Find and delete all existing documents in the sub-collection.
            existing_docs = roadmaps_collection.stream()
            for doc in existing_docs:
                print(f"  -> Deleting old roadmap document: {doc.id}")
                doc.reference.delete()

            # Step 2: Create the new roadmap document.
            data_to_add = {
                'createdAt': firestore.SERVER_TIMESTAMP,
                **new_roadmap_data
            }
            roadmaps_collection.add(data_to_add)
            
            print(f"✅ New roadmap created after clearing previous for user {user_uid}.")
            return True
        except Exception as e:
            print(f"❌ Error during delete-then-create for roadmap (user: {user_uid}): {e}")
            raise

    # This function now correctly finds the one and only roadmap document.
    async def get_user_roadmap(self, user_uid: str) -> Optional[Dict[str, Any]]:
        """Retrieves the single roadmap document for a user."""
        try:
            roadmaps_collection = self.db.collection('users').document(user_uid).collection('roadmaps')
            # Since there's only one, we can just get the first result from the stream.
            docs = roadmaps_collection.limit(1).stream()
            the_only_roadmap_doc = next(docs, None)

            if the_only_roadmap_doc:
                return the_only_roadmap_doc.to_dict()
            else:
                return None
        except Exception as e:
            print(f"❌ Error fetching the roadmap for user {user_uid}: {e}")
            raise

    # This function also correctly finds and updates the one and only roadmap document.
    async def update_roadmap_task_status(self, user_uid: str, phase_title: str, topic_name: str, is_completed: bool) -> bool:
        """Finds the single roadmap document and updates a task's status."""
        try:
            roadmaps_collection = self.db.collection('users').document(user_uid).collection('roadmaps')
            docs = roadmaps_collection.limit(1).stream()
            the_only_roadmap_doc = next(docs, None)

            if not the_only_roadmap_doc:
                print(f"❌ No roadmap document found for user {user_uid}. Cannot update.")
                return False

            roadmap_content = the_only_roadmap_doc.to_dict()
            doc_ref = the_only_roadmap_doc.reference

            if 'detailed_roadmap' not in roadmap_content: return False

            updated_detailed_roadmap = roadmap_content['detailed_roadmap']
            task_found_and_updated = False
            for phase in updated_detailed_roadmap:
                if phase.get('phase_title') == phase_title and isinstance(phase.get('topics'), list):
                    for topic in phase['topics']:
                        if isinstance(topic, dict) and topic.get('name') == topic_name:
                            topic['is_completed'] = is_completed
                            task_found_and_updated = True
                            break
                if task_found_and_updated:
                    break

            if task_found_and_updated:
                doc_ref.update({'detailed_roadmap': updated_detailed_roadmap})
                print(f"✅ Task '{topic_name}' updated for user {user_uid}.")
                return True
            else:
                return False
        except Exception as e:
            print(f"❌ Error updating roadmap task status for user {user_uid}: {e}")
            raise