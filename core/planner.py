"""
Planner Module
Generates patch intents using LLM (Qwen) with rule-based fallback
"""

import json
import os
from typing import Optional, Dict, Any, List, cast
from core.patch_intent import PatchIntent, Operation, FileMutation
from core.llm_client import create_planner_client, BaseLLMClient
from core.semantic_context import SemanticContextManager


class PlannerError(Exception):
    """Raised when planner fails to generate valid intent"""
    pass


class Planner:
    """
    Generates patch intents for the controller
    
    Uses LLM (Qwen 2.5 Coder 7B) for intelligent intent generation.
    Falls back to rule-based on LLM failure.
    """
    
    def __init__(self, logger, indexer, use_llm: bool = True):
        self.logger = logger
        self.indexer = indexer
        self.use_llm = use_llm
        self.llm_client: Optional[BaseLLMClient] = None
        self.enable_reasoning_pass = os.getenv("FORGECORE_ENABLE_REASONING_PASS", "false").lower() == "true"
        
        # Initialize context manager
        from core.context_manager import ContextManager
        self.context_manager = ContextManager(indexer)
        self.semantic_context = SemanticContextManager(self.indexer.conn)
        
        if use_llm:
            try:
                self.llm_client = create_planner_client()
                if self.llm_client and not self.llm_client.is_available():
                    raise RuntimeError(self.llm_client.availability_error() or "Planner LLM is unavailable")
                # model attribute may not exist on abstract base class
                model_name = getattr(self.llm_client, "model", None)
                self.logger.log_event(
                    state="INIT",
                    event="LLM_PLANNER_ENABLED",
                    details={"model": model_name}
                )
            except Exception as e:
                self.logger.log_event(
                    state="INIT",
                    event="LLM_PLANNER_FAILED",
                    details={"error": str(e)}
                )
                self.use_llm = False
                print(f"Warning: LLM planner failed to initialize, using rule-based: {e}")
    
    def generate_intent(
        self,
        task_description: str,
        error_context: Optional[List[Dict[str, Any]]] = None,
        iteration: int = 1,
        previous_intent: Optional[PatchIntent] = None
    ) -> PatchIntent:
        """
        Generate or refine a code mutation intent based on the task and context.
        """
        # Lazy semantic summarization for relevant files
        relevant_files = self._prepare_semantic_context(task_description)

        self.logger.log_event(
            state="PLANNING",
            event="PLANNER_INVOKED",
            details={
                "iteration": iteration,
                "has_error_context": error_context is not None,
                "has_previous_intent": previous_intent is not None
            }
        )
        
        # Phase 1: Reasoning (Thinking)
        # We do reasoning in iteration 1, OR if there's error context (meaning a previous attempt failed)
        if self.enable_reasoning_pass and (iteration == 1 or error_context) and self.use_llm and self.llm_client:
            reasoning_type = "Analyzing codebase context" if iteration == 1 else "Rethinking approach based on feedback"
            print(f"\n\033[94m[THINKING]\033[0m {reasoning_type} for: '{task_description}'...")
            reasoning = self._generate_reasoning_llm(task_description, relevant_files, error_context)
            if reasoning:
                print(f"\n\033[96m[PLANNING STEPS]\033[0m")
                # Indent reasoning for better look
                indented_reasoning = "\n".join([f"  {line}" for line in reasoning.splitlines()])
                print(f"{indented_reasoning}\n")
                self.logger.log_event(
                    state="PLANNING",
                    event="AI_REASONING",
                    details={"reasoning": reasoning, "iteration": iteration}
                )

        # Check if LLM is required but not available
        if not self.use_llm or not self.llm_client:
            self.logger.log_event(
                state="PLANNING",
                event="LLM_FALLBACK_RULE_BASED",
                details={"reason": "LLM not enabled or initialization failed"}
            )
            
            if error_context and iteration > 1:
                return self._refine_intent(task_description, error_context, previous_intent)
            else:
                return self._parse_task_description(task_description)
        
        # Use LLM for planning
        try:
            intent = self._generate_intent_llm(
                task_description,
                error_context,
                iteration,
                previous_intent,
                relevant_files
            )
        except Exception as e:
            self.logger.log_event(
                state="PLANNING",
                event="LLM_GENERATION_FAILED",
                details={"error": str(e)}
            )
            raise PlannerError(f"LLM generation failed: {e}")
        
        self.logger.log_event(
            state="PLANNING",
            event="INTENT_GENERATED",
            details={
                "iteration": iteration,
                # operation may be None in multi-file mode (unlikely here)
                "operation": intent.operation.value if intent.operation is not None else None,
                "target_file": intent.target_file
            }
        )
        
        return intent

    def _generate_reasoning_llm(self, task: str, relevant_files: List[str], error_context: Optional[List[Dict[str, Any]]] = None) -> Optional[str]:
        """Generate high-level reasoning and planning steps for the task."""
        if not self.llm_client:
            return None

        project_context = self._get_project_context()
        understanding = self.semantic_context.get_project_understanding(relevant_files)
        
        # Analyze project state for prompt
        is_empty = len(project_context.get('files', [])) == 0
        state_description = "The project is CURRENTLY EMPTY." if is_empty else f"The project contains {len(project_context['files'])} files."

        system_prompt = f"""You are a senior reasoning engine for ForgeCore Graphical. 
{state_description}

Your goal is to analyze the user's task against the current codebase and produce a multi-step logical plan.

Analyze:
1. CODEBASE STATE: Is the project empty, partial, or unrelated? If empty, identify the starting boilerplate needed.
2. RELEVANCE: Are the existing files related to the task? Identify if they should be modified or if new files are better.
3. STEPS: What specific files need to be created or modified? 
4. LOGIC: What are the edge cases or structural needs?

Format:
- [Analysis]: Current state analysis.
- [Steps]: Numbered steps for execution.
- [Decision]: Why this approach was chosen.

Keep it concise but thorough."""

        user_prompt = f"TASK: {task}\n\n"
        
        if error_context:
            user_prompt += "!!! PREVIOUS ATTEMPT FAILED !!!\n"
            user_prompt += "Your previous intent was REJECTED by the critic or user.\n"
            user_prompt += "You MUST RETHINK your strategy. DO NOT repeat the same mistake.\n"
            user_prompt += "REASON FOR FAILURE:\n"
            for err in error_context[-3:]:
                user_prompt += f"- {err.get('message', str(err))}\n"
            user_prompt += "\n"

        user_prompt += f"UNDERSTANDING:\n{understanding}\n\n"
        user_prompt += f"PROJECT CONTEXT:\n{project_context}\n\n"
        
        try:
            # We use generate() instead of generate_json() for free-form reasoning
            reasoning = self.llm_client.generate(user_prompt, system_prompt)
            return reasoning
        except Exception as e:
            print(f"Warning: Reasoning failed: {e}")
            return None

    def _prepare_semantic_context(self, task: str) -> List[str]:
        """
        Identify relevant files and ensure they have semantic summaries.
        Returns the list of relevant files.
        """
        if os.getenv("FORGECORE_DISABLE_SEMANTIC_PREP", "false").lower() == "true":
            return []

        try:
            prep_cap = int(os.getenv("FORGECORE_SEMANTIC_PREP_MAX_FILES", "3").strip() or "3")
        except ValueError:
            prep_cap = 3
        prep_cap = max(0, prep_cap)

        relevant_files = []
        try:
            # 1. Identify files mentioned in task
            words = task.lower().split()
            cursor = self.indexer.conn.cursor()
            cursor.execute("SELECT path FROM files")
            all_files = [row[0] for row in cursor.fetchall()]
            
            for file_path in all_files:
                basename = os.path.basename(file_path).lower()
                if basename in words or file_path.lower() in task.lower():
                    relevant_files.append(file_path)
            
            # 2. Identify files containing symbols mentioned in task
            cursor.execute("SELECT name, file FROM symbols")
            all_symbols = cursor.fetchall()
            for sym_name, sym_file in all_symbols:
                if sym_name.lower() in task.lower():
                    if sym_file not in relevant_files:
                        relevant_files.append(sym_file)
            
            # 3. Summarize missing or outdated summaries for these files
            # Limit file count to avoid stacking many LLM calls before the main planner request
            for file_path in relevant_files[:prep_cap]:
                cursor.execute("SELECT semantic_context FROM files WHERE path = ?", (file_path,))
                row = cursor.fetchone()
                if not row or not row[0] or "Error generating summary" in str(row[0]):
                    try:
                        full_path = os.path.join(self.indexer.project_root, file_path)
                        if os.path.exists(full_path):
                            with open(full_path, "r", encoding="utf-8", errors="ignore") as f:
                                content = f.read()
                                
                            # Cooldown is now handled globally in llm_client.py
                            self.semantic_context.update_file_context(file_path, content)
                    except Exception as e:
                        print(f"Warning: Failed to summarize {file_path} during planning: {e}")
        except Exception as e:
            print(f"Warning: Semantic context preparation failed: {e}")
            
        return relevant_files
    
    def _get_default_file(self) -> str:
        """Get a sensible default file based on project language"""
        try:
            # Try to get primary language from indexer stats
            cursor = self.indexer.conn.cursor()
            cursor.execute("SELECT path FROM files LIMIT 10")
            files = [row[0] for row in cursor.fetchall()]
            
            py_count = sum(1 for f in files if f.endswith('.py'))
            cpp_count = sum(1 for f in files if f.endswith(('.cpp', '.h', '.hpp')))
            
            if py_count > cpp_count:
                # Check if main.py exists
                cursor.execute("SELECT path FROM files WHERE path = 'main.py'")
                if cursor.fetchone():
                    return "main.py"
                # If any python files exist, return the first one
                cursor.execute("SELECT path FROM files WHERE path LIKE '%.py' LIMIT 1")
                row = cursor.fetchone()
                return row[0] if row else "main.py"
            else:
                # Default to main.cpp for C++ or unknown
                return "main.cpp"
        except Exception:
            return "main.cpp"

    def _parse_task_description(self, task: str) -> PatchIntent:
        """
        Parse task description into initial intent
        
        Phase 1: Simple keyword matching with intelligent defaults
        Future: LLM-based semantic understanding
        """
        
        task_lower = task.lower()
        default_file = self._get_default_file()
        
        # Check for file creation first
        if "create file" in task_lower or "create " in task_lower and any(ext in task_lower for ext in ['.cpp', '.h', '.hpp', '.py']):
            # Extract filename
            import re
            # Look for filename pattern
            filename_match = re.search(r'create\s+(?:file\s+)?([\w\.\-/]+\.(cpp|h|hpp|py))', task_lower)
            if filename_match:
                filename = filename_match.group(1)
                
                # Extract content hint from task
                comment_style = "#" if filename.endswith('.py') else "//"
                content = f"{comment_style} {task}\n{comment_style} TODO: Implement\n\n"
                
                return PatchIntent(
                    operation=Operation.CREATE_FILE,
                    target_file=filename,
                    payload={"content": content}
                )
        
        # Check for include/import operations
        if "include" in task_lower or "import" in task_lower:
            # Extract header/module name
            words = task.split()
            item = None
            is_system = False
            
            for i, word in enumerate(words):
                if word.lower() in ["include", "import"] and i + 1 < len(words):
                    item = words[i + 1].strip("'\"<>(),")
                    # Check if it was in angle brackets (C++)
                    if '<' in task and '>' in task:
                        is_system = True
                    break
            
            if item:
                target_file = default_file
                if "in" in task_lower or "to" in task_lower:
                    for i, word in enumerate(words):
                        if word.lower() in ["in", "to"] and i + 1 < len(words):
                            potential_file = words[i + 1].strip("'\"(),")
                            if potential_file.endswith(('.cpp', '.h', '.hpp', '.py')):
                                target_file = potential_file
                                break
                
                # Use ADD_INCLUDE for both C++ includes and Python imports for now
                return PatchIntent(
                    operation=Operation.ADD_INCLUDE,
                    target_file=target_file,
                    payload={"header": item, "system": is_system}
                )
        
        # Generic "create" or "add" pattern - create a function with descriptive name
        if "create" in task_lower or "add" in task_lower:
            # Try to extract a meaningful function name from the task
            import re
            
            # Look for patterns like "create a X" or "add X"
            # Extract the main concept (e.g., "factorial calculating model" -> "factorial")
            words = task_lower.replace("create", "").replace("add", "").strip().split()
            
            # Filter out common words
            stop_words = {"a", "an", "the", "to", "for", "in", "on", "at", "function", "model", "module", "file"}
            meaningful_words = [w for w in words if w not in stop_words and w.isalpha()]
            
            if meaningful_words:
                # Use first meaningful word as function name
                function_name = meaningful_words[0]
                
                # Determine target file
                target_file = default_file
                if "in" in task_lower or "to" in task_lower:
                    task_words = task.split()
                    for i, word in enumerate(task_words):
                        if word.lower() in ["in", "to"] and i + 1 < len(task_words):
                            potential_file = task_words[i + 1].strip("'\"(),")
                            if potential_file.endswith(('.cpp', '.h', '.hpp', '.py')):
                                target_file = potential_file
                                break
                
                return PatchIntent(
                    operation=Operation.ADD_FUNCTION_STUB,
                    target_file=target_file,
                    payload={"name": function_name}
                )
        
        # Simple pattern matching for Phase 1
        if "add function" in task_lower or "create function" in task_lower:
            # Extract function name (simple heuristic)
            words = task.split()
            function_name = None
            
            for i, word in enumerate(words):
                if word.lower() in ["function", "func"]:
                    if i + 1 < len(words):
                        function_name = words[i + 1].strip("'\"(),")
                        break
            
            if not function_name:
                raise PlannerError("Could not extract function name from task")
            
            # Determine target file
            target_file = default_file
            if "in" in task_lower or "to" in task_lower:
                words = task.split()
                for i, word in enumerate(words):
                    if word.lower() in ["in", "to"] and i + 1 < len(words):
                        potential_file = words[i + 1].strip("'\"(),")
                        if potential_file.endswith(('.cpp', '.h', '.hpp', '.py')):
                            target_file = potential_file
                            break
            
            return PatchIntent(
                operation=Operation.ADD_FUNCTION_STUB,
                target_file=target_file,
                payload={"name": function_name}
            )
        
        elif "replace function" in task_lower:
            # Extract function name and body
            words = task.split()
            function_name = None
            
            for i, word in enumerate(words):
                if word.lower() in ["function", "func"] and i + 1 < len(words):
                    function_name = words[i + 1].strip("'\"(),")
                    break
            
            if not function_name:
                raise PlannerError("Could not extract function name from task")
            
            # Extract body (everything after "with:" or "body:")
            body = ""
            if "with:" in task or "body:" in task:
                parts = task.split("with:" if "with:" in task else "body:")
                if len(parts) > 1:
                    body = parts[1].strip()
            
            if not body:
                body = "    # TODO: Implement\n" if default_file.endswith('.py') else "    // TODO: Implement\n"
            
            target_file = default_file
            if "in" in task_lower or "to" in task_lower:
                words = task.split()
                for i, word in enumerate(words):
                    if word.lower() in ["in", "to"] and i + 1 < len(words):
                        potential_file = words[i + 1].strip("'\"(),")
                        if potential_file.endswith(('.cpp', '.h', '.hpp', '.py')):
                            target_file = potential_file
                            break
            
            return PatchIntent(
                operation=Operation.REPLACE_FUNCTION,
                target_file=target_file,
                payload={"name": function_name, "body": body}
            )
        
        elif "insert before" in task_lower:
            # Extract anchor and content
            parts = task.split("insert before", 1)
            if len(parts) < 2:
                raise PlannerError("Could not parse insert before task")
            
            remainder = parts[1].strip()
            
            # Try to extract anchor (first quoted string or word)
            anchor = None
            content = ""
            
            if '"' in remainder:
                quote_parts = remainder.split('"')
                if len(quote_parts) >= 2:
                    anchor = quote_parts[1]
                    if len(quote_parts) >= 4:
                        content = quote_parts[3]
            elif ":" in remainder:
                colon_parts = remainder.split(":", 1)
                anchor = colon_parts[0].strip()
                if len(colon_parts) > 1:
                    content = colon_parts[1].strip()
            
            if not anchor:
                raise PlannerError("Could not extract anchor from task")
            
            if not content:
                content = "# Inserted content\n" if default_file.endswith('.py') else "// Inserted content\n"
            
            target_file = default_file
            if "in" in task_lower or "to" in task_lower:
                words = task.split()
                for i, word in enumerate(words):
                    if word.lower() in ["in", "to"] and i + 1 < len(words):
                        potential_file = words[i + 1].strip("'\"(),")
                        if potential_file.endswith(('.cpp', '.h', '.hpp', '.py')):
                            target_file = potential_file
                            break
            
            return PatchIntent(
                operation=Operation.INSERT_BEFORE,
                target_file=target_file,
                payload={"anchor": anchor, "content": content}
            )
        
        elif "insert after" in task_lower:
            # Similar to insert before
            parts = task.split("insert after", 1)
            if len(parts) < 2:
                raise PlannerError("Could not parse insert after task")
            
            remainder = parts[1].strip()
            
            anchor = None
            content = ""
            
            if '"' in remainder:
                quote_parts = remainder.split('"')
                if len(quote_parts) >= 2:
                    anchor = quote_parts[1]
                    if len(quote_parts) >= 4:
                        content = quote_parts[3]
            elif ":" in remainder:
                colon_parts = remainder.split(":", 1)
                anchor = colon_parts[0].strip()
                if len(colon_parts) > 1:
                    content = colon_parts[1].strip()
            
            if not anchor:
                raise PlannerError("Could not extract anchor from task")
            
            if not content:
                content = "# Inserted content\n" if default_file.endswith('.py') else "// Inserted content\n"
            
            target_file = default_file
            if "in" in task_lower or "to" in task_lower:
                words = task.split()
                for i, word in enumerate(words):
                    if word.lower() in ["in", "to"] and i + 1 < len(words):
                        potential_file = words[i + 1].strip("'\"(),")
                        if potential_file.endswith(('.cpp', '.h', '.hpp', '.py')):
                            target_file = potential_file
                            break
            
            return PatchIntent(
                operation=Operation.INSERT_AFTER,
                target_file=target_file,
                payload={"anchor": anchor, "content": content}
            )
        
        elif "replace" in task_lower and "with" in task_lower:
            # Extract old and new content
            parts = task.split("with", 1)
            if len(parts) < 2:
                raise PlannerError("Could not parse replace task")
            
            old_part = parts[0].replace("replace", "").strip()
            new_part = parts[1].strip()
            
            # Try to extract quoted strings
            old_content = old_part.strip("'\"")
            new_content = new_part.strip("'\"")
            
            if not old_content or not new_content:
                raise PlannerError("Could not extract content to replace")
            
            target_file = default_file
            if "in" in task_lower or "to" in task_lower:
                words = task.split()
                for i, word in enumerate(words):
                    if word.lower() in ["in", "to"] and i + 1 < len(words):
                        potential_file = words[i + 1].strip("'\"(),")
                        if potential_file.endswith(('.cpp', '.h', '.hpp', '.py')):
                            target_file = potential_file
                            break
            
            return PatchIntent(
                operation=Operation.REPLACE_CONTENT,
                target_file=target_file,
                payload={"old_content": old_content, "new_content": new_content}
            )
        
        elif "append" in task_lower or "add comment" in task_lower:
            # Extract content
            if ":" in task:
                content = task.split(":", 1)[1].strip()
            else:
                content = "# Generated by planner\n" if default_file.endswith('.py') else "// Generated by planner\n"
            
            target_file = default_file
            if "to" in task_lower:
                words = task.split()
                for i, word in enumerate(words):
                    if word.lower() == "to" and i + 1 < len(words):
                        potential_file = words[i + 1].strip("'\"(),")
                        if potential_file.endswith(('.cpp', '.h', '.hpp', '.py')):
                            target_file = potential_file
                            break
            
            return PatchIntent(
                operation=Operation.APPEND_RAW,
                target_file=target_file,
                payload={"content": content}
            )
        
        else:
            raise PlannerError(f"Could not parse task: {task}")
    
    def _refine_intent(
        self,
        task: str,
        errors: List[Dict[str, Any]],
        previous_intent: Optional[PatchIntent]
    ) -> PatchIntent:
        """
        Refine intent based on error feedback
        
        Phase 1: Simple error-based refinement
        Future: LLM-based semantic refinement
        """
        
        # Analyze errors
        error_types = [e.get('type', 'UNKNOWN') for e in errors]
        default_file = self._get_default_file()
        
        self.logger.log_event(
            state="PLANNING",
            event="REFINING_INTENT",
            details={
                "error_types": error_types,
                "previous_operation": (
                    previous_intent.operation.value
                    if previous_intent and previous_intent.operation is not None
                    else None
                )
            }
        )
        
        # Strategy 1: Check for user feedback/rejection
        user_feedback = ""
        for err in errors:
            if err.get('type') == 'USER_REJECTION':
                user_feedback = err.get('feedback', '').lower()
                break
        
        if user_feedback:
            # If user provided specific instructions in feedback, try to incorporate them
            # For example, if they mentioned a filename
            import re
            file_match = re.search(r'([\w\.\-/]+\.(cpp|h|hpp|py))', user_feedback)
            if file_match:
                new_file = file_match.group(1)
                # Try to re-parse task but override the target file
                try:
                    intent = self._parse_task_description(task)
                    # Create new intent with modified target file
                    return PatchIntent(
                        operation=intent.operation,
                        target_file=new_file,
                        payload=intent.payload
                    )
                except Exception:
                    pass

        # Strategy 2: If duplicate symbol error, try different name
        if any('duplicate' in str(e).lower() for e in errors):
            if previous_intent and previous_intent.operation == Operation.ADD_FUNCTION_STUB:
                old_name = previous_intent.payload["name"] if previous_intent and previous_intent.payload else None
                new_name = f"{old_name}_v2"
                
                return PatchIntent(
                    operation=Operation.ADD_FUNCTION_STUB,
                    target_file=previous_intent.target_file,
                    payload={"name": new_name}
                )
        
        # Strategy 3: If undefined symbol, try adding stub
        if any('undefined' in str(e).lower() or 'undeclared' in str(e).lower() for e in errors):
            # Extract symbol name from error
            for error in errors:
                error_str = str(error)
                if 'undefined' in error_str.lower() or 'undeclared' in error_str.lower():
                    words = error_str.split()
                    for i, word in enumerate(words):
                        if word.lower() in ['undefined', 'undeclared', 'symbol'] and i + 1 < len(words):
                            symbol = words[i + 1].strip("'\"():,")
                            if symbol.isidentifier():
                                return PatchIntent(
                                    operation=Operation.ADD_FUNCTION_STUB,
                                    target_file=default_file,
                                    payload={"name": symbol}
                                )
        
        # Strategy 4: If target file not indexed/found, try to find a better one or create it
        if any('not indexed' in str(e).lower() or 'not found' in str(e).lower() for e in errors):
            if previous_intent and previous_intent.operation != Operation.CREATE_FILE:
                # If we were trying to modify a file that doesn't exist, maybe we should create it?
                return PatchIntent(
                    operation=Operation.CREATE_FILE,
                    target_file=previous_intent.target_file,
                    payload={"content": f"# {task}\n# Created because previous attempt failed\n"}
                )

        # Default: If we have previous intent, and no specific refinement worked, 
        # try to re-parse the task. If it's the same, it will trigger stagnation.
        # But we'll try to be a bit smarter by changing the default file if possible.
        try:
            intent = self._parse_task_description(task)
            if previous_intent and intent.target_file == previous_intent.target_file and intent.operation == previous_intent.operation:
                # Stagnation likely. Try to find ANOTHER file if possible?
                # For now, just return it and let the controller handle stagnation.
                return intent
            return intent
        except Exception:
            if previous_intent:
                return previous_intent
            raise PlannerError(f"Could not refine or parse task: {task}")
    
    def validate_intent(self, intent: PatchIntent) -> bool:
        """
        Validate that generated intent is safe and reasonable
        
        Returns:
            True if valid, False otherwise
        """
        
        # Basic validation (more checks in controller)
        if not intent.target_file:
            return False
        
        # Check operation is supported
        supported_ops = [
            Operation.APPEND_RAW,
            Operation.ADD_FUNCTION_STUB,
            Operation.REPLACE_FUNCTION,
            Operation.INSERT_BEFORE,
            Operation.INSERT_AFTER,
            Operation.ADD_INCLUDE,
            Operation.REPLACE_CONTENT,
            Operation.CREATE_FILE
        ]
        
        if intent.operation not in supported_ops:
            return False
        
        return True
    
    def _generate_intent_llm(
        self,
        task: str,
        error_context: Optional[List[Dict[str, Any]]],
        iteration: int,
        previous_intent: Optional[PatchIntent],
        relevant_files: Optional[List[str]] = None
    ) -> PatchIntent:
        """
        Generate intent using LLM (Qwen) with smart context management.
        """
        # Get project context and understanding
        project_context = self._get_project_context()
        understanding = self.semantic_context.get_project_understanding(relevant_files)
        
        # Build system prompt with constraints
        system_prompt = """You are a senior autonomous architect for ForgeCore Graphical.
Your goal is to solve the user's task with high-quality, production-ready code in as few iterations as possible.

CRITICAL ARCHITECTURAL CONSTRAINTS:
1. MULTI-FILE ATOMICITY: You MUST perform ALL necessary file changes (creating, modifying, connecting files) in a SINGLE intent if possible. Do not wait for a second iteration to "fix" what you missed.
2. COHERENCE: Ensure all files work together. If you create a class in one file, make sure the imports and constructor arguments match in the other files.
3. OPERATION SELECTION (STRICT): 
   - FOR EXISTING FILES: You MUST use modification operations (REPLACE_FUNCTION, REPLACE_CONTENT, INSERT_BEFORE, INSERT_AFTER, APPEND_RAW, ADD_INCLUDE) whenever possible. This preserves file history and context.
   - FOR NEW FILES: Use CREATE_FILE.
   - OVERWRITE TRICK: ONLY use CREATE_FILE on an existing file if you are performing a total architectural overhaul (> 80% change). Explain this clearly in the description.
4. CRITIC FEEDBACK: If you see "CRITIC FEEDBACK" in the prompt, it means your previous attempt failed. YOU MUST address every point raised by the critic. If the critic provided a code snippet, USE IT or adapt it to fix the issue.

AVAILABLE OPERATIONS:
- REPLACE_CONTENT: Replace an exact text match. USE THIS for small targeted edits.
- REPLACE_FUNCTION: Replace a specific function body. USE THIS for logic updates.
- INSERT_BEFORE / INSERT_AFTER: Add code relative to an anchor string. USE THIS for adding new methods or fields.
- APPEND_RAW: Append to end of file.
- ADD_INCLUDE: Add #include or import.
- CREATE_FILE: Create a NEW file OR completely OVERWRITE an existing file (last resort).

JSON FORMAT (Strictly follow this):
{
  "description": "Comprehensive explanation of how these changes solve the task across all affected files",
  "mutations": [
    {
      "target_file": "path/to/file.py",
      "operation": "operation_name",
      "payload": { ... operation specific fields ... }
    }
  ]
}

RESPOND WITH VALID JSON ONLY."""

        # Build user prompt with smart context
        user_prompt = ""
        
        # Add error context with smart summarization at the VERY TOP
        if error_context and iteration > 1:
            user_prompt += "\n" + "!" * 60 + "\n"
            user_prompt += "CRITICAL: YOUR PREVIOUS ATTEMPT FAILED OR WAS REJECTED!\n"
            user_prompt += "YOU MUST READ THE FEEDBACK BELOW AND FIX YOUR APPROACH.\n"
            user_prompt += "DO NOT REPEAT THE SAME MISTAKE. ADDRESS ALL CRITIC CONCERNS.\n"
            user_prompt += "!" * 60 + "\n\n"
            
            for err in error_context[-3:]:
                msg = err.get('message', str(err))
                err_type = str(err.get('type', ''))
                
                if (
                    "CRITIC_REJECTION" in err_type
                    or "CRITIC_REJECTED" in err_type
                    or "Critic rejected" in msg
                ):
                    user_prompt += f"CRITIC FEEDBACK (FIX THIS): {msg}\n"
                elif "USER_REJECTION" in err_type:
                    user_prompt += f"USER FEEDBACK: {err.get('feedback')}\n"
                else:
                    user_prompt += f"EXECUTION ERROR: {msg}\n"
            user_prompt += "\n" + "-" * 60 + "\n\n"

        user_prompt += f"PROJECT UNDERSTANDING:\n{understanding}\n\n"
        user_prompt += f"TASK: {task}\n\n"
        
        # Add project context (existing files and symbols)
        if project_context:
            user_prompt += "PROJECT CONTEXT:\n"
            user_prompt += f"Primary Language: {project_context.get('language', 'unknown')}\n"
            user_prompt += "Existing files (ALREADY ON DISK):\n"
            
            for f in project_context['files']:
                user_prompt += f"  - {f['path']} ({f['lines']} lines)\n"
            
            user_prompt += "REMINDER: For the existing files above, prefer using modification operations like REPLACE_FUNCTION or REPLACE_CONTENT instead of CREATE_FILE.\n\n"
        
        # Add previous intent context
        if previous_intent:
            user_prompt += f"FAILED PREVIOUS INTENT (DO NOT REPEAT EXACTLY):\n"
            if previous_intent and previous_intent.operation is not None:
                user_prompt += f"- Operation: {previous_intent.operation.value}\n"
            user_prompt += f"- File: {previous_intent.target_file}\n"
            user_prompt += f"- Payload: {previous_intent.payload}\n\n"
            
            # Add file content context (if possible)
            if previous_intent.target_file:
                try:
                    context_dict = self.context_manager.get_smart_context(
                        files=[previous_intent.target_file],
                        focus_file=previous_intent.target_file
                    )
                    if previous_intent.target_file in context_dict:
                        file_context = context_dict[previous_intent.target_file]
                        user_prompt += f"CURRENT CONTENT OF {previous_intent.target_file} (Total lines: {len(file_context.splitlines())}):\n"
                        user_prompt += f"```\n{file_context}\n```\n\n"
                except Exception:
                    pass
        
        user_prompt += """Generate PatchIntent JSON:
{
  "operation": "OPERATION_NAME",
  "target_file": "file.py",
  "payload": {"content": "..."}
}"""

        # Generate JSON
        assert self.llm_client is not None
        # llm_client is guaranteed non-null here
        response_json: Any = self.llm_client.generate_json(user_prompt, system_prompt)
        
        # Handle if LLM returns array instead of single object
        if isinstance(response_json, list):
            if len(response_json) > 0:
                # response_json may be list-like; if not, leave as is
                if isinstance(response_json, list) and response_json:
                    response_json = response_json[0]  # Take first intent
            else:
                raise PlannerError("LLM returned empty array")
        # after this point we expect a dict
        data = cast(Dict[str, Any], response_json)
        
        # Handle new multi-file format (mutations list)
        if "mutations" in data:
            from core.patch_intent import FileMutation
            file_mutations = []
            for m_data in data["mutations"]:
                # Map operation string to enum (handling both names and values)
                op_str = m_data.get("operation", "").upper()
                try:
                    if op_str in Operation.__members__:
                        op = Operation[op_str]
                    else:
                        op = Operation(op_str.lower())
                except (KeyError, ValueError):
                    op = Operation.REPLACE_CONTENT

                file_mutations.append(FileMutation(
                    target_file=m_data.get("target_file", "main.cpp"),
                    operation=op,
                    payload=m_data.get("payload", {})
                ))
            
            return PatchIntent(
                file_mutations=file_mutations,
                description=data.get("description", "")
            )
        
        # Backward compatibility for single intent format
        operation_str = data.get("operation", "").upper()
        
        # Map operation string to enum
        operation_map = {
            "CREATE_FILE": Operation.CREATE_FILE,
            "ADD_FUNCTION_STUB": Operation.ADD_FUNCTION_STUB,
            "APPEND_RAW": Operation.APPEND_RAW,
            "REPLACE_FUNCTION": Operation.REPLACE_FUNCTION,
            "INSERT_BEFORE": Operation.INSERT_BEFORE,
            "INSERT_AFTER": Operation.INSERT_AFTER,
            "ADD_INCLUDE": Operation.ADD_INCLUDE,
            "REPLACE_CONTENT": Operation.REPLACE_CONTENT
        }
        
        operation = operation_map.get(operation_str, Operation.REPLACE_CONTENT)
        target_file = data.get("target_file", "main.cpp")
        payload = data.get("payload", {})
        
        self.logger.log_event(
            state="PLANNING",
            event="LLM_INTENT_GENERATED",
            details={
                "operation": operation.value,
                "target_file": target_file,
                "iteration": iteration
            }
        )
        
        return PatchIntent(
            operation=operation,
            target_file=target_file,
            payload=payload,
            description=data.get("description", "")
        )
    
    def _get_project_context(self) -> Dict[str, Any]:
        """
        Get project context from database for context-aware planning.
        
        Returns:
            Dict with 'files' (list of dicts with path and lines), 'symbols' lists
        """
        try:
            conn = self.indexer.conn
            cursor = conn.cursor()
            
            # Get all indexed files
            cursor.execute("SELECT path FROM files")
            paths = [row[0] for row in cursor.fetchall()]
            
            # Print debug for database status
            if not paths:
                self.logger.log_event(
                    state="PLANNING",
                    event="EMPTY_CONTEXT_DB",
                    details={"project_root": self.indexer.project_root}
                )
            
            files_context = []
            # Increase limit to 50 for better context awareness
            for path in paths[:50]:
                try:
                    # Get actual line count from disk for accuracy
                    from tools.dispatcher import ToolDispatcher
                    dispatcher = ToolDispatcher(self.indexer.project_root)
                    content = dispatcher.read_file(path)
                    files_context.append({
                        "path": path,
                        "lines": len(content.splitlines())
                    })
                except Exception:
                    files_context.append({"path": path, "lines": 0})
            
            # Get all symbols
            cursor.execute("SELECT DISTINCT name FROM symbols")
            symbols = [row[0] for row in cursor.fetchall()]
            
            # Get primary language
            default_file = self._get_default_file()
            language = "python" if default_file.endswith(".py") else "cpp"
            
            return {
                'files': files_context,
                'symbols': symbols,
                'language': language
            }
        except Exception as e:
            self.logger.log_event(
                state="PLANNING",
                event="CONTEXT_FETCH_FAILED",
                details={"error": str(e)}
            )
            return {'files': [], 'symbols': [], 'language': 'unknown'}
    
    def _get_file_includes_recursive(self, file_path: str) -> List[str]:
        """
        Get all files included by a file, recursively.
        """
        included_files = []
        cursor = self.indexer.conn.cursor()
        cursor.execute(
            "SELECT included_file FROM includes WHERE source_file = ?",
            (file_path,)
        )
        for row in cursor.fetchall():
            included_file = row[0]
            if included_file not in included_files:
                included_files.append(included_file)
                included_files.extend(self._get_file_includes_recursive(included_file))
        return included_files
