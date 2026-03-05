"""
Planner Module
Generates patch intents using LLM (Qwen) with rule-based fallback
"""

import json
from typing import Optional, Dict, Any, List, cast
from core.patch_intent import PatchIntent, Operation
from core.llm_client import create_planner_client, BaseLLMClient


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
        
        # Initialize context manager
        from core.context_manager import ContextManager
        self.context_manager = ContextManager(indexer)
        
        if use_llm:
            try:
                self.llm_client = create_planner_client()
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
        Generate a patch intent based on task and error context
        
        Args:
            task_description: High-level task description
            error_context: Structured errors from previous iteration
            iteration: Current iteration number
            previous_intent: Intent from previous iteration (for refinement)
        
        Returns:
            PatchIntent to execute
        
        Raises:
            PlannerError if unable to generate valid intent
        """
        
        self.logger.log_event(
            state="PLANNING",
            event="PLANNER_INVOKED",
            details={
                "iteration": iteration,
                "has_error_context": error_context is not None,
                "has_previous_intent": previous_intent is not None
            }
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
                previous_intent
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
    
    def _parse_task_description(self, task: str) -> PatchIntent:
        """
        Parse task description into initial intent
        
        Phase 1: Simple keyword matching with intelligent defaults
        Future: LLM-based semantic understanding
        """
        
        task_lower = task.lower()
        
        # Check for file creation first
        if "create file" in task_lower or "create " in task_lower and any(ext in task_lower for ext in ['.cpp', '.h', '.hpp']):
            # Extract filename
            import re
            # Look for filename pattern
            filename_match = re.search(r'create\s+(?:file\s+)?(\w+\.(cpp|h|hpp))', task_lower)
            if filename_match:
                filename = filename_match.group(1)
                
                # Extract content hint from task
                content = f"// {task}\n// TODO: Implement\n\n"
                
                return PatchIntent(
                    operation=Operation.CREATE_FILE,
                    target_file=filename,
                    payload={"content": content}
                )
        
        # Check for include operations before generic "add"
        if "include" in task_lower:
            # Extract header name
            words = task.split()
            header = None
            is_system = False
            
            for i, word in enumerate(words):
                if word.lower() == "include" and i + 1 < len(words):
                    header = words[i + 1].strip("'\"<>(),")
                    # Check if it was in angle brackets
                    if '<' in task and '>' in task:
                        is_system = True
                    break
            
            if header:
                target_file = "main.cpp"
                if "in" in task_lower or "to" in task_lower:
                    for i, word in enumerate(words):
                        if word.lower() in ["in", "to"] and i + 1 < len(words):
                            potential_file = words[i + 1].strip("'\"(),")
                            if potential_file.endswith(('.cpp', '.h', '.hpp')):
                                target_file = potential_file
                                break
                
                return PatchIntent(
                    operation=Operation.ADD_INCLUDE,
                    target_file=target_file,
                    payload={"header": header, "system": is_system}
                )
        
        # Generic "create" pattern - create a function with descriptive name
        if "create" in task_lower or "add" in task_lower:
            # Try to extract a meaningful function name from the task
            import re
            
            # Look for patterns like "create a X" or "add X"
            # Extract the main concept (e.g., "factorial calculating model" -> "factorial")
            words = task_lower.replace("create", "").replace("add", "").strip().split()
            
            # Filter out common words
            stop_words = {"a", "an", "the", "to", "for", "in", "on", "at", "function", "model", "module"}
            meaningful_words = [w for w in words if w not in stop_words and w.isalpha()]
            
            if meaningful_words:
                # Use first meaningful word as function name
                function_name = meaningful_words[0]
                
                # Determine target file
                target_file = "main.cpp"
                if "in" in task_lower:
                    task_words = task.split()
                    for i, word in enumerate(task_words):
                        if word.lower() == "in" and i + 1 < len(task_words):
                            potential_file = task_words[i + 1].strip("'\"(),")
                            if potential_file.endswith(('.cpp', '.h', '.hpp')):
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
            
            # Determine target file (default to main.cpp for Phase 1)
            target_file = "main.cpp"
            if "in" in task_lower:
                words = task.split()
                for i, word in enumerate(words):
                    if word.lower() == "in" and i + 1 < len(words):
                        potential_file = words[i + 1].strip("'\"(),")
                        if potential_file.endswith(('.cpp', '.h', '.hpp')):
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
                if word.lower() == "function" and i + 1 < len(words):
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
                body = "    // TODO: Implement\n"
            
            target_file = "main.cpp"
            if "in" in task_lower:
                words = task.split()
                for i, word in enumerate(words):
                    if word.lower() == "in" and i + 1 < len(words):
                        potential_file = words[i + 1].strip("'\"(),")
                        if potential_file.endswith(('.cpp', '.h', '.hpp')):
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
                content = "// Inserted content\n"
            
            target_file = "main.cpp"
            
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
                content = "// Inserted content\n"
            
            target_file = "main.cpp"
            
            return PatchIntent(
                operation=Operation.INSERT_AFTER,
                target_file=target_file,
                payload={"anchor": anchor, "content": content}
            )
        
        elif "add include" in task_lower or "include" in task_lower:
            # Extract header name
            words = task.split()
            header = None
            is_system = False
            
            for i, word in enumerate(words):
                if word.lower() == "include" and i + 1 < len(words):
                    header = words[i + 1].strip("'\"<>(),")
                    # Check if it was in angle brackets
                    if '<' in task and '>' in task:
                        is_system = True
                    break
            
            if not header:
                raise PlannerError("Could not extract header name from task")
            
            target_file = "main.cpp"
            if "in" in task_lower or "to" in task_lower:
                words = task.split()
                for i, word in enumerate(words):
                    if word.lower() in ["in", "to"] and i + 1 < len(words):
                        potential_file = words[i + 1].strip("'\"(),")
                        if potential_file.endswith(('.cpp', '.h', '.hpp')):
                            target_file = potential_file
                            break
            
            return PatchIntent(
                operation=Operation.ADD_INCLUDE,
                target_file=target_file,
                payload={"header": header, "system": is_system}
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
            
            target_file = "main.cpp"
            
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
                content = "// Generated by planner\n"
            
            target_file = "main.cpp"
            if "to" in task_lower:
                words = task.split()
                for i, word in enumerate(words):
                    if word.lower() == "to" and i + 1 < len(words):
                        potential_file = words[i + 1].strip("'\"(),")
                        if potential_file.endswith(('.cpp', '.h', '.hpp')):
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
        
        # Phase 1: Simple refinement strategies
        
        # If duplicate symbol error, try different name
        if any('duplicate' in str(e).lower() for e in errors):
            if previous_intent and previous_intent.operation == Operation.ADD_FUNCTION_STUB:
                old_name = previous_intent.payload["name"] if previous_intent and previous_intent.payload else None
                new_name = f"{old_name}_v2"
                
                return PatchIntent(
                    operation=Operation.ADD_FUNCTION_STUB,
                    target_file=previous_intent.target_file,
                    payload={"name": new_name}
                )
        
        # If undefined symbol, try adding stub
        if any('undefined' in str(e).lower() or 'undeclared' in str(e).lower() for e in errors):
            # Extract symbol name from error (simple heuristic)
            for error in errors:
                error_str = str(error)
                if 'undefined' in error_str.lower():
                    # Try to extract symbol name
                    # This is a placeholder - real implementation would parse error properly
                    words = error_str.split()
                    for i, word in enumerate(words):
                        if word.lower() in ['undefined', 'undeclared'] and i + 1 < len(words):
                            symbol = words[i + 1].strip("'\"():,")
                            if symbol.isidentifier():
                                return PatchIntent(
                                    operation=Operation.ADD_FUNCTION_STUB,
                                    target_file="main.cpp",
                                    payload={"name": symbol}
                                )
        
        # Default: Return original intent (will trigger stagnation detection)
        if previous_intent:
            return previous_intent
        
        # Fallback: Try to parse task again
        return self._parse_task_description(task)
    
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
            Operation.REPLACE_CONTENT
        ]
        
        if intent.operation not in supported_ops:
            return False
        
        return True
    
    def _generate_intent_llm(
        self,
        task: str,
        error_context: Optional[List[Dict[str, Any]]],
        iteration: int,
        previous_intent: Optional[PatchIntent]
    ) -> PatchIntent:
        """
        Generate intent using LLM (Qwen) with smart context management.
        
        Args:
            task: Task description
            error_context: Errors from previous iteration
            iteration: Current iteration number
            previous_intent: Previous intent (for refinement)
            
        Returns:
            Generated PatchIntent
        """
        # Build system prompt with constraints
        system_prompt = """You are a code mutation planner for ForgeCore.
Generate PatchIntent in JSON format.

CONSTRAINTS:
- Max 5 files per transaction
- Max 200 lines per file
- Max 50% rewrite ratio per file
- No modifications to tier2 directories (crypto/, network/protocol/)

AVAILABLE OPERATIONS:
- CREATE_FILE: Create new file with content
- ADD_FUNCTION_STUB: Add function stub to existing file
- APPEND_RAW: Append content to existing file
- REPLACE_FUNCTION: Replace function body in existing file
- INSERT_BEFORE: Insert before anchor in existing file
- INSERT_AFTER: Insert after anchor in existing file
- ADD_INCLUDE: Add include directive to existing file
- REPLACE_CONTENT: Replace text content in existing file

MULTI-FILE SUPPORT:
You can create/modify multiple files in one transaction for coordinated changes.

RESPOND WITH VALID JSON ONLY."""

        # Build user prompt with smart context
        user_prompt = f"TASK: {task}\n\n"
        
        # Add project context (existing files and symbols)
        project_context = self._get_project_context()
        if project_context:
            user_prompt += "PROJECT CONTEXT:\n"
            user_prompt += f"Existing files: {', '.join(project_context['files'][:10])}\n"
            if len(project_context['files']) > 10:
                user_prompt += f"... and {len(project_context['files']) - 10} more\n"
            user_prompt += f"Existing symbols: {', '.join(project_context['symbols'][:20])}\n"
            if len(project_context['symbols']) > 20:
                user_prompt += f"... and {len(project_context['symbols']) - 20} more\n"
            user_prompt += "\n"
        
        # Add error context with smart summarization
        if error_context and iteration > 1:
            user_prompt += "PREVIOUS ERRORS:\n"
            for err in error_context[:3]:  # Limit to 3 errors
                user_prompt += f"- {err}\n"
            user_prompt += "\n"
        
        # Add previous intent context
        if previous_intent:
            user_prompt += f"PREVIOUS INTENT:\n"
            if previous_intent and previous_intent.operation is not None:
                user_prompt += f"- Operation: {previous_intent.operation.value}\n"
            user_prompt += f"- File: {previous_intent.target_file}\n"
            user_prompt += f"- Payload: {previous_intent.payload}\n\n"
            
            # Add file context using context manager (smart summarization)
            if previous_intent.target_file:
                try:
                    context_dict = self.context_manager.get_smart_context(
                        files=[previous_intent.target_file],
                        focus_file=previous_intent.target_file
                    )
                    if previous_intent.target_file in context_dict:
                        file_context = context_dict[previous_intent.target_file]
                        # Truncate if too long
                        if len(file_context) > 2000:
                            file_context = file_context[:2000] + "\n... [truncated]"
                        user_prompt += f"CURRENT FILE CONTENT ({previous_intent.target_file}):\n"
                        user_prompt += f"```\n{file_context}\n```\n\n"
                except Exception as e:
                    self.logger.log_event(
                        state="PLANNING",
                        event="CONTEXT_MANAGER_ERROR",
                        details={"error": str(e)}
                    )
        
        user_prompt += """Generate PatchIntent JSON:
{
  "operation": "OPERATION_NAME",
  "target_file": "file.cpp",
  "payload": {...}
}

Examples:
- CREATE_FILE: {"content": "#include <iostream>\\n\\nint main() { return 0; }"}
- ADD_FUNCTION_STUB: {"name": "function_name"}
- APPEND_RAW: {"content": "// comment\\n"}
- REPLACE_FUNCTION: {"name": "func", "body": "return 0;"}
- INSERT_BEFORE: {"anchor": "int main", "content": "// comment\\n"}
- ADD_INCLUDE: {"header": "iostream", "system": true}

For multi-file projects, you can generate multiple intents in sequence."""

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
        response_json = cast(Dict[str, Any], response_json)
        
        # Parse into PatchIntent
        operation_str = response_json.get("operation", "").upper()
        target_file = response_json.get("target_file", "main.cpp")
        payload = response_json.get("payload", {})
        
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
        
        if operation_str not in operation_map:
            raise PlannerError(f"Invalid operation from LLM: {operation_str}")
        
        operation = operation_map[operation_str]
        
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
            payload=payload
        )
    
    def _get_project_context(self) -> Dict[str, Any]:
        """
        Get project context from database for context-aware planning.
        
        Returns:
            Dict with 'files' and 'symbols' lists
        """
        try:
            conn = self.indexer.conn
            cursor = conn.cursor()
            
            # Get all indexed files
            cursor.execute("SELECT path FROM files")
            files = [row[0] for row in cursor.fetchall()]
            
            # Get all symbols
            cursor.execute("SELECT DISTINCT name FROM symbols")
            symbols = [row[0] for row in cursor.fetchall()]
            
            return {
                'files': files,
                'symbols': symbols
            }
        except Exception as e:
            self.logger.log_event(
                state="PLANNING",
                event="PROJECT_CONTEXT_ERROR",
                details={"error": str(e)}
            )
            return {'files': [], 'symbols': []}

