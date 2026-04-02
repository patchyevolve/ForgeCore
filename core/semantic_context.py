"""
Semantic Context Manager - Codebase understanding using LLM
"""

import json
import time
from typing import Dict, Any, List, Optional
from core.llm_client import create_planner_client, BaseLLMClient

class SemanticContextManager:
    """
    Generates and manages high-level semantic understanding of the codebase.
    """
    
    def __init__(self, db_conn):
        self.db_conn = db_conn
        self.llm_client: Optional[BaseLLMClient] = None
        self._client_attempted = False
        
    def _ensure_client(self):
        if self.llm_client or self._client_attempted:
            return
        self._client_attempted = True
        try:
            self.llm_client = create_planner_client()
            if self.llm_client and not self.llm_client.is_available():
                raise RuntimeError(self.llm_client.availability_error() or "Semantic context LLM is unavailable")
        except Exception as e:
            self.llm_client = None
            print(f"Warning: Failed to initialize LLM for semantic context: {e}")
                
    def generate_file_summary(self, file_path: str, content: str) -> str:
        """
        Generate a semantic summary for a file using LLM.
        The LLM client's _post_with_retry will handle exponential backoff for 429 errors.
        """
        self._ensure_client()
        if not self.llm_client:
            return "LLM unavailable for summary generation."
            
        print(f"[INFO] Generating semantic summary for {file_path}...")
        
        system_prompt = """You are a technical architect. Provide a concise, high-level semantic summary of the following source file.
Focus on:
1. Primary responsibility of the file.
2. Key classes/functions and their roles.
3. Important dependencies and how they are used.
4. Architectural patterns used.

Respond with a single paragraph (max 150 words)."""

        user_prompt = f"FILE: {file_path}\n\nCONTENT:\n{content[:5000]}" # Limit content size
        
        try:
            summary = self.llm_client.generate(user_prompt, system_prompt)
            print(f"[OK] Summary generated for {file_path}")
            return summary.strip()
        except Exception as e:
            print(f"[WARN] Failed to generate summary for {file_path}: {e}")
            return f"Error generating summary: {str(e)}"

    def update_file_context(self, file_path: str, content: str):
        """
        Generate and store summary in the database.
        """
        summary = self.generate_file_summary(file_path, content)
        cursor = self.db_conn.cursor()
        cursor.execute(
            "UPDATE files SET semantic_context = ? WHERE path = ?",
            (summary, file_path)
        )
        # Removed manual commit to preserve global transaction/savepoint state.
        # The caller (Indexer or Controller) is responsible for committing.

    def get_project_understanding(self, relevant_files: Optional[List[str]] = None) -> str:
        """
        Fetch semantic contexts for a subset of files to provide targeted understanding.
        If relevant_files is None, it returns everything (use with caution).
        """
        cursor = self.db_conn.cursor()
        
        if relevant_files:
            # Construct query for specific files
            placeholders = ', '.join(['?'] * len(relevant_files))
            query = f"SELECT path, semantic_context FROM files WHERE path IN ({placeholders}) AND semantic_context IS NOT NULL"
            cursor.execute(query, relevant_files)
        else:
            cursor.execute("SELECT path, semantic_context FROM files WHERE semantic_context IS NOT NULL")
            
        rows = cursor.fetchall()
        
        if not rows:
            return "No semantic context available for the requested files yet."
            
        understanding = "PROJECT SEMANTIC UNDERSTANDING:\n"
        for path, context in rows:
            understanding += f"- {path}: {context}\n"
        return understanding
