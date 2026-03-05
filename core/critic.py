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
            except Exception as e:
                print(f"Warning: Failed to initialize LLM critic: {e}")
                self.use_llm = False
    
    def review_intent(self, intent: PatchIntent, file_content: str, task: Optional[str] = None) -> Tuple[bool, str]:
        """
        Review a proposed mutation before execution.
        
        Args:
            intent: The PatchIntent to review
            file_content: Current content of target file
            task: Optional task description
            
        Returns:
            (approved: bool, feedback: str)
        """
        # normalize task to avoid passing None further
        task_str = task or ""
        if self.use_llm and self.llm_client:
            try:
                return self._review_intent_llm(intent, file_content, task_str)
            except Exception as e:
                print(f"Warning: LLM review failed, using simulated: {e}")
                return self._review_intent_simulated(intent, file_content, task_str)
        else:
            return self._review_intent_simulated(intent, file_content, task_str)
    
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
    
    def _review_intent_llm(self, intent: PatchIntent, file_content: str, task: Optional[str] = None) -> Tuple[bool, str]:
        """
        LLM-based intent review using DeepSeek.
        
        Args:
            intent: Proposed PatchIntent
            file_content: Current file content
            task: Optional task description
            
        Returns:
            (approved: bool, feedback: str)
        """
        assert self.llm_client is not None, "LLM client must exist for LLM review"
        task_str = task or ""
        # Build system prompt
        system_prompt = """You are a code review critic for ForgeCore.
Review the proposed mutation for safety and correctness.

REVIEW CRITERIA:
1. Does this mutation accomplish the task?
2. Is it safe (no undefined behavior, memory issues)?
3. Does it respect tier restrictions (no tier2 modifications)?
4. Is the scope appropriate (not too broad)?

RESPOND IN JSON:
{
  "approved": true/false,
  "feedback": "Brief explanation",
  "concerns": ["concern1", "concern2", ...]
}"""

        # Build user prompt
        user_prompt = f"""TASK: {task_str if task_str else 'Not specified'}

PROPOSED INTENT:
- Operation: {intent.operation.value if intent.operation is not None else '<none>'}
- Target File: {intent.target_file}
- Payload: {intent.payload}

CURRENT FILE CONTENT (first 500 chars):
{file_content[:500]}

Review this mutation."""

        # Get review from LLM
        response = self.llm_client.generate_json(user_prompt, system_prompt)
        
        approved = response.get("approved", False)
        feedback = response.get("feedback", "No feedback provided")
        concerns = response.get("concerns", [])
        
        if concerns:
            feedback += f"\nConcerns: {', '.join(concerns)}"
        
        return approved, feedback
    
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
        system_prompt = """You are a final code review critic for ForgeCore.
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
