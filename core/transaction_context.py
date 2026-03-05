"""
Transaction Context - Encapsulates all state for a single transaction execution.

This module provides the TransactionContext class which isolates transaction state
from controller state, enabling cleaner separation of concerns and better testability.
"""

from dataclasses import dataclass, field
from typing import Dict, Set, List, Optional, Any
from datetime import datetime


@dataclass
class TransactionContext:
    """
    Encapsulates all state for a single transaction execution.
    
    This class isolates transaction-specific state from the controller,
    providing clear boundaries and preventing state leakage across transactions.
    
    Attributes:
        iteration_mode: True for planner loop with refinement, False for direct execution
        planner_context: Optional context for planner (task_description, etc.)
        current_iteration: Current iteration number (1-indexed)
        max_iterations: Maximum iterations allowed
        baselines: Per-file baseline state (hash, content, size)
        modified_files: Files successfully modified in this transaction
        candidate_files: Files pending modification (not yet committed)
        iteration_history: History of iterations (for planner feedback)
        last_error_hash: Hash of last error (for stagnation detection)
        started_at: Transaction start timestamp
    """
    
    # Execution mode
    iteration_mode: bool
    planner_context: Optional[dict] = None
    
    # Iteration state
    current_iteration: int = 0
    max_iterations: int = 5
    
    # File tracking
    baselines: Dict[str, Dict] = field(default_factory=dict)
    modified_files: Set[str] = field(default_factory=set)
    candidate_files: Set[str] = field(default_factory=set)
    
    # History tracking
    iteration_history: List[dict] = field(default_factory=list)
    last_error_hash: Optional[str] = None
    
    # Metadata
    started_at: datetime = field(default_factory=datetime.now)
    
    def add_baseline(self, file: str, baseline: dict) -> None:
        """
        Add baseline for a file (idempotent).
        
        Args:
            file: File path
            baseline: Baseline dict with 'hash', 'content', 'size'
        """
        if file not in self.baselines:
            self.baselines[file] = baseline
    
    def get_baseline(self, file: str) -> Optional[dict]:
        """
        Get baseline for a file.
        
        Args:
            file: File path
            
        Returns:
            Baseline dict or None if not found
        """
        return self.baselines.get(file)
    
    def has_baseline(self, file: str) -> bool:
        """
        Check if baseline exists for file.
        
        Args:
            file: File path
            
        Returns:
            True if baseline exists
        """
        return file in self.baselines
    
    def get_missing_baselines(self, files: Set[str]) -> Set[str]:
        """
        Get files that don't have baselines yet.
        
        Args:
            files: Set of file paths
            
        Returns:
            Set of files without baselines
        """
        return files - self.baselines.keys()
    
    def mark_candidate(self, file: str) -> None:
        """
        Mark file as candidate for modification.
        Candidates are not yet committed to modified_files.
        
        Args:
            file: File path
        """
        self.candidate_files.add(file)
    
    def commit_candidates(self) -> None:
        """
        Promote candidate files to modified files.
        Called after successful write stage.
        """
        self.modified_files.update(self.candidate_files)
        self.candidate_files.clear()
    
    def clear_candidates(self) -> None:
        """
        Clear candidate files (on failure).
        Called when validation or write fails.
        """
        self.candidate_files.clear()
    
    def update_baseline(self, file: str, content: str, content_hash: str) -> None:
        """
        Update baseline after successful mutation.
        Used for file integrity guard across iterations.
        
        Args:
            file: File path
            content: New file content
            content_hash: SHA256 hash of content
        """
        if file in self.baselines:
            self.baselines[file]["hash"] = content_hash
            self.baselines[file]["content"] = content
            self.baselines[file]["size"] = len(content.splitlines())
    
    def record_iteration(self, iteration_data: dict) -> None:
        """
        Record iteration for history.
        Used for planner feedback and debugging.
        
        Args:
            iteration_data: Dict with iteration details
        """
        self.iteration_history.append(iteration_data)
    
    def get_last_iteration(self) -> Optional[dict]:
        """
        Get last iteration data.
        
        Returns:
            Last iteration dict or None if no history
        """
        return self.iteration_history[-1] if self.iteration_history else None
    
    def get_error_context(self) -> Optional[List[Dict[str, Any]]]:
        """
        Get error context from last iteration.
        Used for planner refinement.
        
        Returns:
            List of error dictionaries or None if no errors
        """
        last = self.get_last_iteration()
        return last.get('errors') if last else None
    
    def get_previous_intent(self):
        """
        Get intent from last iteration.
        Used for planner refinement.
        
        Returns:
            PatchIntent or None if no history
        """
        last = self.get_last_iteration()
        return last.get('intent') if last else None
    
    def should_continue(self) -> bool:
        """
        Check if iteration should continue.
        
        Returns:
            True if more iterations allowed
        """
        return self.current_iteration < self.max_iterations
    
    def increment_iteration(self) -> None:
        """Increment iteration counter"""
        self.current_iteration += 1
    
    def get_all_target_files(self) -> Set[str]:
        """
        Get all files targeted in this transaction.
        
        Returns:
            Union of modified_files and candidate_files
        """
        return self.modified_files | self.candidate_files
    
    def __repr__(self) -> str:
        """String representation for debugging"""
        return (
            f"TransactionContext("
            f"iteration={self.current_iteration}/{self.max_iterations}, "
            f"mode={'planner' if self.iteration_mode else 'direct'}, "
            f"baselines={len(self.baselines)}, "
            f"modified={len(self.modified_files)}, "
            f"candidates={len(self.candidate_files)})"
        )
