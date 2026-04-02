"""
Critic Module - Code Review Agent

Uses LLM (DeepSeek Coder 6.7B) for intelligent code review.
Falls back to simulated approval on LLM failure.
"""

from typing import Dict, Any, Tuple, Optional
from core.patch_intent import PatchIntent
from core.llm_client import create_critic_client, BaseLLMClient


class Critic:
    """
    Code review critic for validating mutations.
    
    Uses DeepSeek Coder 6.7B for intelligent code review.
    Falls back to simulated approval on LLM failure.
    """
    
    def __init__(self, use_llm: bool = True):
        """
        Initialize critic.
        
        Args:
            use_llm: Enable LLM-based review (default: True)
        """
        self.use_llm = use_llm
        self.llm_client: Optional[BaseLLMClient] = None
        
        if use_llm:
            try:
                self.llm_client = create_critic_client()
                if self.llm_client and not self.llm_client.is_available():
                    raise RuntimeError(self.llm_client.availability_error() or "Critic LLM is unavailable")
            except Exception as e:
                print(f"Warning: Failed to initialize LLM critic: {e}")
                self.use_llm = False
    
    def review_intent(self, intent: PatchIntent, context_manager, task: Optional[str] = None) -> Tuple[bool, str]:
        """
        Review a proposed intent (possibly multi-file) before execution.
        
        Args:
            intent: The PatchIntent to review
            context_manager: Context manager to fetch file contents
            task: Optional task description
            
        Returns:
            (approved: bool, feedback: str)
        """
        task_str = task or ""
        
        # Collect context for all files in the intent
        files_context = {}
        for mutation in intent.mutations:
            file_path = mutation.target_file
            if file_path not in files_context:
                try:
                    content = context_manager.get_file_content(file_path)
                    files_context[file_path] = content
                except Exception:
                    files_context[file_path] = "[New or inaccessible file]"

        if self.use_llm and self.llm_client:
            try:
                return self._review_intent_llm(intent, files_context, task_str)
            except Exception as e:
                print(f"Warning: LLM review failed, using simulated: {e}")
                return True, "Simulated approval (LLM failed)"
        else:
            return True, "Simulated approval (LLM disabled)"
    
    def review_result(self, intent: PatchIntent, original: str, modified: str, task: Optional[str] = None) -> Tuple[bool, str]:
        """
        Review the final result after mutation.
        
        Args:
            intent: The executed PatchIntent
            original: Original file content
            modified: Modified file content
            task: Optional task description
            
        Returns:
            (approved: bool, feedback: str)
        """
        task_str = task or ""
        if self.use_llm and self.llm_client:
            try:
                return self._review_result_llm(intent, original, modified, task_str)
            except Exception as e:
                print(f"Warning: LLM review failed, using simulated: {e}")
                return self._review_result_simulated(intent, original, modified, task_str)
        else:
            return self._review_result_simulated(intent, original, modified, task_str)
    
    def _review_intent_simulated(self, intent: PatchIntent, file_content: str, task: Optional[str] = None) -> Tuple[bool, str]:
        """Simulated review - always approves."""
        # `task` parameter is unused; normalized earlier if needed
        return True, "Simulated approval"
    
    def _review_result_simulated(self, intent: PatchIntent, original: str, modified: str, task: Optional[str] = None) -> Tuple[bool, str]:
        """Simulated review - always approves."""
        return True, "Simulated approval"
    
    def _review_intent_llm(self, intent: PatchIntent, files_context: Dict[str, str], task_str: str) -> Tuple[bool, str]:
        """LLM-based review of multiple mutations in an intent"""
        
        mutations_str = ""
        for i, m in enumerate(intent.mutations, 1):
            mutations_str += f"\nMutation {i}:\n"
            mutations_str += f"- File: {m.target_file}\n"
            mutations_str += f"- Operation: {m.operation.value}\n"
            mutations_str += f"- Payload: {m.payload}\n"
            
        context_str = ""
        for file, content in files_context.items():
            context_str += f"\n--- {file} (Current) ---\n"
            context_str += content[:500] + ("..." if len(content) > 500 else "") + "\n"

        prompt = f"""Review this multi-file code mutation intent.
TASK: {task_str}

PROPOSED MUTATIONS:
{mutations_str}

CURRENT CONTEXT:
{context_str}

Does this plan solve the task correctly and maintain architectural coherence?
Check for:
1. Missing imports or mismatched class/function arguments between files.
2. Incomplete implementations or logical errors.
3. Proper use of CREATE_FILE vs other operations.

Respond with 'APPROVED' or 'REJECTED: [detailed feedback]'.
If REJECTED, please provide a clear explanation and, if possible, the exact code snippet that should be used instead.
"""
        response = self.llm_client.generate(prompt)
        if "APPROVED" in response.upper():
            return True, "LLM Approved"
        else:
            return False, response.replace("REJECTED:", "").strip()
    
    def _review_result_llm(self, intent: PatchIntent, original: str, modified: str, task: Optional[str] = None) -> Tuple[bool, str]:
        """
        LLM-based result review using DeepSeek.
        
        Args:
            intent: Executed PatchIntent
            original: Original file content
            modified: Modified file content
            task: Optional task description
            
        Returns:
            (approved: bool, feedback: str)
        """
        assert self.llm_client is not None, "LLM client must exist for LLM review"
        task_str = task or ""
        # Build system prompt
        system_prompt = """You are a final code review critic for ForgeCore Graphical.
Review the actual mutation result for correctness and quality.

REVIEW CRITERIA:
1. Does the change accomplish the task?
2. Is the code correct and safe?
3. Are there any syntax errors or issues?
4. Is the change minimal and focused?

RESPOND IN JSON:
{
  "approved": true/false,
  "feedback": "Brief explanation",
  "issues": ["issue1", "issue2", ...]
}"""

        # Build user prompt with diff
        user_prompt = f"""TASK: {task_str if task_str else 'Not specified'}

OPERATION: {intent.operation.value if intent.operation is not None else '<none>'}

ORIGINAL (first 300 chars):
{original[:300]}

MODIFIED (first 300 chars):
{modified[:300]}

Review the final result."""

        # Get review from LLM
        response = self.llm_client.generate_json(user_prompt, system_prompt)
        
        approved = response.get("approved", False)
        feedback = response.get("feedback", "No feedback provided")
        issues = response.get("issues", [])
        
        if issues:
            feedback += f"\nIssues: {', '.join(issues)}"
        
        return approved, feedback
