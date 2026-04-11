"""
Execution Engine - Handles task execution with planner iteration loops and direct execution.

This module extracts execution logic from the Controller, providing clean separation
between orchestration (Controller) and execution (ExecutionEngine). It coordinates
with the StateMachine for state transitions and implements stagnation detection.

Key Responsibilities:
- Execute tasks with planner iteration loops (execute_with_planner)
- Execute direct intents without planner (execute_direct)
- Detect stagnation when identical errors occur across iterations
- Enforce max_iterations limits
- Coordinate with StateMachine for state transitions
"""

import os
import hashlib
from datetime import datetime
from typing import Optional, Dict, Any, Set, cast
from dataclasses import dataclass, field

from core.state_machine import StateMachine, State
from core.transaction_context import TransactionContext
from core.patch_intent import PatchIntent


@dataclass
class ExecutionResult:
    """
    Result of task execution.
    
    Attributes:
        status: Execution status (COMPLETED, FAILED, REJECTED, STAGNATED, MAX_ITERATIONS)
        modified_files: List of files modified in this execution
        iterations: Number of iterations executed
        errors: List of error messages
        warnings: List of warning messages
        metadata: Additional metadata
        duration: Execution duration in seconds
    """
    status: str
    modified_files: list
    iterations: int
    errors: list = field(default_factory=list)
    warnings: list = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    duration: float = 0.0
    
    def is_success(self) -> bool:
        """Check if execution succeeded"""
        return self.status == "COMPLETED"
    
    def get_summary(self) -> str:
        """Get human-readable summary"""
        if self.is_success():
            return f"Completed successfully in {self.iterations} iteration(s), modified {len(self.modified_files)} file(s)"
        else:
            error_summary = "; ".join(self.errors[:3])
            return f"Failed with status {self.status}: {error_summary}"


class ExecutionEngine:
    """
    Execution engine for task execution with planner iteration loops.
    
    This class handles the core execution logic extracted from Controller,
    coordinating with planner, critic, validators, and state machine.
    """
    
    def __init__(
        self,
        target_project_path: str,
        state_machine: StateMachine,
        planner,
        critic,
        validator,
        semantic_validator,
        indexer,
        snapshot_manager,
        error_classifier,
        logger,
        max_iterations: int = 5,
        stagnation_detection_enabled: bool = True,
        semantic_validation_enabled: bool = False
    ):
        """
        Initialize ExecutionEngine.
        
        Args:
            target_project_path: Path to target project
            state_machine: State machine for state transitions
            planner: Planner for intent generation
            critic: Critic for intent/result review
            validator: Validator for build validation
            semantic_validator: Semantic validator for semantic checks
            indexer: Project indexer
            snapshot_manager: Snapshot manager for rollback
            error_classifier: Error classifier for structured errors
            logger: Logger instance
            max_iterations: Maximum iterations allowed
            stagnation_detection_enabled: Enable stagnation detection
            semantic_validation_enabled: Enable semantic validation
        """
        self.target_project_path = target_project_path
        self.state_machine = state_machine
        self.planner = planner
        self.critic = critic
        self.validator = validator
        self.semantic_validator = semantic_validator
        self.indexer = indexer
        self.snapshot_manager = snapshot_manager
        self.error_classifier = error_classifier
        self.logger = logger
        self.max_iterations = max_iterations
        self.stagnation_detection_enabled = stagnation_detection_enabled
        self.semantic_validation_enabled = semantic_validation_enabled
        
        # Callbacks for mutation operations (injected by Controller)
        self._validate_intent_callback = None
        self._ensure_baselines_callback = None
        self._generate_mutations_callback = None
        self._validate_mutations_callback = None
        self._apply_mutations_callback = None
        self._validate_post_build_callback = None
    
    def set_callbacks(
        self,
        validate_intent,
        ensure_baselines,
        generate_mutations,
        validate_mutations,
        apply_mutations,
        validate_post_build
    ):
        """
        Set callbacks for mutation operations.
        
        These callbacks delegate to Controller methods that handle
        the actual mutation logic (validation, generation, application).
        
        Args:
            validate_intent: Callback for intent validation
            ensure_baselines: Callback for baseline capture
            generate_mutations: Callback for mutation generation
            validate_mutations: Callback for mutation validation
            apply_mutations: Callback for mutation application
            validate_post_build: Callback for post-build validation
        """
        self._validate_intent_callback = validate_intent
        self._ensure_baselines_callback = ensure_baselines
        self._generate_mutations_callback = generate_mutations
        self._validate_mutations_callback = validate_mutations
        self._apply_mutations_callback = apply_mutations
        self._validate_post_build_callback = validate_post_build
    
    def execute_with_planner(
        self,
        task_description: str,
        context: TransactionContext
    ) -> ExecutionResult:
        """
        Execute task with planner iteration loop.
        
        This method implements the planner iteration loop with refinement,
        stagnation detection, and max_iterations enforcement.
        
        Args:
            task_description: Natural language task description
            context: Transaction context with execution state
            
        Returns:
            ExecutionResult with status and details
        """
        start_time = datetime.now()
        
        # Set planner context
        context.planner_context = {'task_description': task_description}
        
        # Iteration loop
        intent = None
        while context.should_continue():
            context.increment_iteration()
            
            # PLANNING - Generate/refine intent
            self.state_machine.transition_to(State.PLANNING)
            
            try:
                error_context = context.get_error_context()
                previous_intent = context.get_previous_intent()
                
                # Generate new intent for this iteration
                intent = self.planner.generate_intent(
                    task_description=task_description,
                    error_context=error_context,
                    iteration=context.current_iteration,
                    previous_intent=previous_intent
                )
                
                # Update snapshot if new files are targeted
                new_targets = self._get_target_files(intent)
                self.snapshot_manager._create_selective_snapshot(list(new_targets))
                
            except Exception as e:
                self.logger.log_event(
                    state=self.state_machine.get_state().name,
                    event="PLANNER_FAILED",
                    details={"error": str(e)}
                )
                # Check if max_iterations reached before returning FAILED
                status = "MAX_ITERATIONS" if context.current_iteration >= context.max_iterations else "FAILED"
                return ExecutionResult(
                    status=status,
                    modified_files=[],
                    iterations=context.current_iteration,
                    errors=[f"Planner failed: {e}"],
                    duration=(datetime.now() - start_time).total_seconds()
                )
            
            # Execute iteration
            result = self._execute_iteration(intent, context)
            
            # Check result
            if result.status == "COMPLETED":
                result.duration = (datetime.now() - start_time).total_seconds()
                return result
            elif result.status in ["STAGNATED", "MAX_ITERATIONS", "REJECTED"]:
                result.duration = (datetime.now() - start_time).total_seconds()
                return result
            
            # Continue to next iteration for refinement
        
        # Max iterations reached
        return ExecutionResult(
            status="MAX_ITERATIONS",
            modified_files=list(context.modified_files),
            iterations=context.current_iteration,
            errors=["Max iterations reached"],
            duration=(datetime.now() - start_time).total_seconds()
        )
    
    def execute_direct(
        self,
        intent: PatchIntent,
        context: TransactionContext
    ) -> ExecutionResult:
        """
        Execute direct intent without planner.
        
        This method executes a single intent without iteration or refinement.
        Used for direct patch intent execution.
        
        Args:
            intent: Patch intent to execute
            context: Transaction context with execution state
            
        Returns:
            ExecutionResult with status and details
        """
        start_time = datetime.now()
        
        # Single iteration
        context.increment_iteration()
        
        # Execute iteration
        result = self._execute_iteration(intent, context)
        result.duration = (datetime.now() - start_time).total_seconds()
        
        return result
    
    def _execute_iteration(
        self,
        intent: PatchIntent,
        context: TransactionContext
    ) -> ExecutionResult:
        """
        Execute a single iteration.
        
        This method handles the core execution logic for one iteration:
        - Validate intent
        - Capture baselines
        - Critic review
        - Generate mutations
        - Validate mutations
        - Apply mutations
        - Build validation
        - Post-build validation
        
        Args:
            intent: Patch intent to execute
            context: Transaction context
            
        Returns:
            ExecutionResult with status and details
        """
        # PLANNING state (for state machine consistency)
        # Only transition if not already in PLANNING state
        if self.state_machine.get_state() != State.PLANNING:
            self.state_machine.transition_to(State.PLANNING)
        
        # Validate intent
        valid, reason = self._validate_intent_callback(intent)
        if not valid:
            self.logger.log_event(
                state=self.state_machine.get_state().name,
                event="SEMANTIC_REJECT_INVALID_INTENT",
                details={"reason": reason}
            )
            return ExecutionResult(
                status="REJECTED",
                modified_files=[],
                iterations=context.current_iteration,
                errors=[f"Semantic rejection: {reason}"]
            )
        
        # Capture baselines
        self._ensure_baselines_callback(intent, context)
        
        # Log iteration summary
        self._log_iteration_summary(intent, context)
        
        # Compute intent fingerprint
        intent_hash = self._compute_intent_fingerprint(intent)
        self.logger.log_event(
            state=self.state_machine.get_state().name,
            event="INTENT_FINGERPRINT",
            details={"intent_hash": intent_hash[:16]}
        )
        
        # CRITIC REVIEW
        self.state_machine.transition_to(State.CRITIC_REVIEW)
        
        # Get file content for review
        target_file = intent.target_file if not intent.is_multi_file else intent.target_files[0]
        file_content = self._get_file_content(target_file, context)
        
        # Review intent
        task_desc = context.planner_context.get('task_description') if context.planner_context else None
        approved, feedback = self.critic.review_intent(
            intent,
            self.planner.context_manager,
            task_desc
        )
        
        self.logger.log_event(
            state=self.state_machine.get_state().name,
            event="CRITIC_REVIEW_COMPLETE",
            details={"approved": approved, "feedback": feedback[:100]}
        )
        
        if not approved:
            self.logger.log_event(
                state=self.state_machine.get_state().name,
                event="CRITIC_REJECTED",
                details={"reason": feedback[:500] if feedback else ""},
            )
            structured_errors = [
                {
                    "type": "CRITIC_REJECTED_INTENT",
                    "message": f"Critic rejected intent: {feedback}",
                }
            ]
            if not context.iteration_mode:
                return ExecutionResult(
                    status="REJECTED",
                    modified_files=[],
                    iterations=context.current_iteration,
                    errors=[structured_errors[0]["message"]],
                )
            pre_apply_hash = self._compute_content_fingerprint("")
            return self._refine_after_iteration_error(
                context, intent, intent_hash, pre_apply_hash, structured_errors
            )
        
        # PATCH READY
        self.state_machine.transition_to(State.PATCH_READY)
        
        # APPLYING
        self.state_machine.transition_to(State.APPLYING)
        
        # Generate mutations
        staged_writes = self._generate_mutations_callback(intent, context)
        original_contents = {
            file: context.baselines.get(file, {}).get("content", "")
            for file in staged_writes.keys()
        }
        
        # Compute content hash for stagnation detection
        all_content = ''.join(staged_writes[f] for f in sorted(staged_writes.keys()))
        content_hash = self._compute_content_fingerprint(all_content)
        
        # Check for stagnation (iteration 2+)
        if self.stagnation_detection_enabled and context.current_iteration > 1:
            stagnation_result = self._check_stagnation(
                intent_hash, content_hash, context
            )
            if stagnation_result:
                return stagnation_result
        
        # Validate mutations
        valid, reason = self._validate_mutations_callback(staged_writes, context, intent)
        if not valid:
            self.logger.log_event(
                state=self.state_machine.get_state().name,
                event="MUTATION_VALIDATION_FAILED",
                details={"reason": reason}
            )
            structured_errors = [{"type": "MUTATION_VALIDATION_FAILED", "message": reason}]
            if context.iteration_mode:
                return self._refine_after_iteration_error(
                    context, intent, intent_hash, content_hash, structured_errors
                )
            self.state_machine.transition_to(State.ABORT)
            self.state_machine.transition_to(State.IDLE)
            return ExecutionResult(
                status="FAILED",
                modified_files=[],
                iterations=context.current_iteration,
                errors=[reason],
            )
        
        # Apply mutations
        success, error = self._apply_mutations_callback(staged_writes, context)
        if not success:
            self.logger.log_event(
                state=self.state_machine.get_state().name,
                event="WRITE_FAILED",
                details={"error": error}
            )
            structured_errors = [{"type": "WRITE_FAILED", "message": error}]
            if context.iteration_mode:
                return self._refine_after_iteration_error(
                    context, intent, intent_hash, content_hash, structured_errors
                )
            self.state_machine.transition_to(State.ABORT)
            self.state_machine.transition_to(State.IDLE)
            return ExecutionResult(
                status="FAILED",
                modified_files=[],
                iterations=context.current_iteration,
                errors=[error],
            )
        
        # Re-index after apply
        try:
            self.indexer.index_project()
        except Exception as e:
            self.logger.log_event(
                state=self.state_machine.get_state().name,
                event="POST_WRITE_INDEX_FAILED",
                details={"error": str(e)}
            )
        
        # Update baselines for next iteration
        for file, content in staged_writes.items():
            file_hash = hashlib.sha256(content.encode('utf-8')).hexdigest()
            context.update_baseline(file, content, file_hash)
        
        # SEMANTIC VALIDATION
        if self.semantic_validation_enabled:
            semantic_result = self._run_semantic_validation(staged_writes, context)
            if semantic_result:
                return semantic_result
        
        # COMPILING
        self.state_machine.transition_to(State.COMPILING)
        result = self.validator.validate(list(staged_writes.keys()))
        
        if result.get("success", False):
            # SUCCESS PATH
            return self._handle_success(
                intent,
                staged_writes,
                context,
                intent_hash,
                content_hash,
                original_contents
            )
        else:
            # FAILURE PATH
            return self._handle_failure(result, context, intent, intent_hash, content_hash)
    
    def _handle_success(
        self,
        intent: PatchIntent,
        staged_writes: Dict[str, str],
        context: TransactionContext,
        intent_hash: str,
        content_hash: str,
        original_contents: Dict[str, str]
    ) -> ExecutionResult:
        """
        Handle successful build validation.
        
        Args:
            intent: Patch intent
            staged_writes: Staged file writes
            context: Transaction context
            intent_hash: Intent fingerprint
            content_hash: Content fingerprint
            
        Returns:
            ExecutionResult
        """
        self.state_machine.transition_to(State.FINAL_CRITIC)
        
        # Final critic review
        for file in staged_writes.keys():
            try:
                with open(os.path.join(self.target_project_path, file), 'r') as f:
                    modified_content = f.read()
                
                original_content = original_contents.get(file, "")
                task_desc = context.planner_context.get('task_description') if context.planner_context else None
                
                approved, feedback = self.critic.review_result(
                    intent,
                    original_content,
                    modified_content,
                    task_desc
                )
                
                self.logger.log_event(
                    state=self.state_machine.get_state().name,
                    event="FINAL_CRITIC_REVIEW",
                    details={"file": file, "approved": approved, "feedback": feedback[:100]}
                )
                
                if not approved:
                    self.logger.log_event(
                        state=self.state_machine.get_state().name,
                        event="FINAL_CRITIC_CONCERNS",
                        details={"file": file, "concerns": feedback}
                    )
            except Exception as e:
                self.logger.log_event(
                    state=self.state_machine.get_state().name,
                    event="FINAL_CRITIC_ERROR",
                    details={"error": str(e)}
                )
        
        # MODULE INTEGRITY CHECK
        self.state_machine.transition_to(State.MODULE_INTEGRITY_CHECK)
        
        valid, reason = self._validate_post_build_callback(context)
        if not valid:
            self.logger.log_event(
                state=self.state_machine.get_state().name,
                event="POST_BUILD_VALIDATION_FAILED",
                details={"reason": reason}
            )
            
            # In direct mode, fail immediately
            if not context.iteration_mode:
                return ExecutionResult(
                    status="FAILED",
                    modified_files=[],
                    iterations=context.current_iteration,
                    errors=[reason]
                )
            
            # In planner mode, treat as refinable error
            structured_errors = [{
                "type": "POST_BUILD_VALIDATION_FAILED",
                "message": reason
            }]
            error_hash = self._compute_error_fingerprint(structured_errors)
            
            # Check for error stagnation
            if context.last_error_hash and context.last_error_hash == error_hash:
                self.logger.log_event(
                    state=self.state_machine.get_state().name,
                    event="STAGNATION_DETECTED_IDENTICAL_ERRORS",
                    details={"iteration": context.current_iteration, "error_hash": error_hash[:16]}
                )
                return ExecutionResult(
                    status="STAGNATED",
                    modified_files=[],
                    iterations=context.current_iteration,
                    errors=[f"Stagnation detected: planner unable to resolve post-build validation errors"]
                )
            
            context.last_error_hash = error_hash
            
            # Check max iterations
            if context.current_iteration >= context.max_iterations:
                return ExecutionResult(
                    status="MAX_ITERATIONS",
                    modified_files=[],
                    iterations=context.current_iteration,
                    errors=["Max iterations reached"]
                )
            
            # Record iteration for refinement
            context.record_iteration({
                "iteration": context.current_iteration,
                "intent": intent,
                "intent_hash": intent_hash,
                "content_hash": content_hash,
                "errors": structured_errors,
                "error_hash": error_hash,
                "timestamp": datetime.now().isoformat()
            })
            
            # Continue to refinement
            self.state_machine.transition_to(State.REFINEMENT)
            return ExecutionResult(
                status="REFINEMENT",
                modified_files=[],
                iterations=context.current_iteration,
                errors=structured_errors
            )
        
        # SUCCESS - COMMIT
        return ExecutionResult(
            status="COMPLETED",
            modified_files=list(context.modified_files),
            iterations=context.current_iteration
        )
    
    def _handle_failure(
        self,
        result: Dict[str, Any],
        context: TransactionContext,
        intent: PatchIntent,
        intent_hash: str,
        content_hash: str
    ) -> ExecutionResult:
        """
        Handle build validation failure.
        
        Args:
            result: Validation result
            context: Transaction context
            intent: Patch intent
            intent_hash: Intent fingerprint
            content_hash: Content fingerprint
            
        Returns:
            ExecutionResult
        """
        self.state_machine.transition_to(State.ERROR_CLASSIFY)
        
        # Extract errors
        if 'errors' in result:
            structured_errors = result['errors']
        elif 'stderr' in result:
            combined_output = result.get("stdout", "") + "\n" + result.get("stderr", "")
            structured_errors = self.error_classifier.classify(combined_output)
        else:
            structured_errors = [{"type": "VALIDATION_FAILED", "message": str(result)}]
        
        error_hash = self._compute_error_fingerprint(structured_errors)
        
        self.logger.log_event(
            state=self.state_machine.get_state().name,
            event="STRUCTURED_ERRORS",
            details={"errors": structured_errors, "error_hash": error_hash[:16]}
        )
        
        # Check for error stagnation
        if self.stagnation_detection_enabled and context.last_error_hash and context.last_error_hash == error_hash:
            self.logger.log_event(
                state=self.state_machine.get_state().name,
                event="STAGNATION_DETECTED_IDENTICAL_ERRORS",
                details={"iteration": context.current_iteration, "error_hash": error_hash[:16]}
            )
            return ExecutionResult(
                status="STAGNATED",
                modified_files=[],
                iterations=context.current_iteration,
                errors=[f"Stagnation detected: {'planner unable to resolve' if context.iteration_mode else 'identical'} errors"]
            )
        
        context.last_error_hash = error_hash
        
        # If not iteration mode, fail immediately
        if not context.iteration_mode:
            return ExecutionResult(
                status="FAILED",
                modified_files=[],
                iterations=context.current_iteration,
                errors=[e.get("message", str(e)) for e in structured_errors]
            )
        
        # Check iteration limit
        if context.current_iteration >= context.max_iterations:
            return ExecutionResult(
                status="MAX_ITERATIONS",
                modified_files=[],
                iterations=context.current_iteration,
                errors=["Max iterations reached"]
            )
        
        # Record iteration for refinement
        context.record_iteration({
            'iteration': context.current_iteration,
            'intent': intent,
            'intent_hash': intent_hash,
            'content_hash': content_hash,
            'errors': structured_errors,
            'error_hash': error_hash,
            'timestamp': datetime.now().isoformat()
        })
        
        # Continue to refinement
        self.state_machine.transition_to(State.REFINEMENT)
        return ExecutionResult(
            status="REFINEMENT",
            modified_files=[],
            iterations=context.current_iteration,
            errors=structured_errors
        )

    def _refine_after_iteration_error(
        self,
        context: TransactionContext,
        intent: PatchIntent,
        intent_hash: str,
        content_hash: str,
        structured_errors: list,
    ) -> ExecutionResult:
        """
        Record structured errors so the planner receives them via TransactionContext,
        then return REFINEMENT for another pass (planner iteration mode only).
        """
        self.state_machine.transition_to(State.ERROR_CLASSIFY)

        error_hash = self._compute_error_fingerprint(structured_errors)

        self.logger.log_event(
            state=self.state_machine.get_state().name,
            event="PLANNER_REFINEMENT",
            details={"errors": structured_errors, "error_hash": error_hash[:16]},
        )

        critic_only = bool(structured_errors) and all(
            isinstance(e, dict) and e.get("type") == "CRITIC_REJECTED_INTENT"
            for e in structured_errors
        )
        if (
            self.stagnation_detection_enabled
            and not critic_only
            and context.last_error_hash
            and context.last_error_hash == error_hash
        ):
            self.logger.log_event(
                state=self.state_machine.get_state().name,
                event="STAGNATION_DETECTED_IDENTICAL_ERRORS",
                details={"iteration": context.current_iteration, "error_hash": error_hash[:16]},
            )
            return ExecutionResult(
                status="STAGNATED",
                modified_files=[],
                iterations=context.current_iteration,
                errors=["Stagnation detected: same refinement error as the previous iteration"],
            )

        context.last_error_hash = error_hash

        if context.current_iteration >= context.max_iterations:
            flat = [
                e.get("message", str(e)) if isinstance(e, dict) else str(e)
                for e in structured_errors
            ]
            return ExecutionResult(
                status="MAX_ITERATIONS",
                modified_files=[],
                iterations=context.current_iteration,
                errors=flat or ["Max iterations reached"],
            )

        context.record_iteration(
            {
                "iteration": context.current_iteration,
                "intent": intent,
                "intent_hash": intent_hash,
                "content_hash": content_hash,
                "errors": structured_errors,
                "error_hash": error_hash,
                "timestamp": datetime.now().isoformat(),
            }
        )
        self.state_machine.transition_to(State.REFINEMENT)
        return ExecutionResult(
            status="REFINEMENT",
            modified_files=[],
            iterations=context.current_iteration,
            errors=structured_errors,
        )

    def _run_semantic_validation(
        self,
        staged_writes: Dict[str, str],
        context: TransactionContext
    ) -> Optional[ExecutionResult]:
        """
        Run semantic validation on staged writes.
        
        Args:
            staged_writes: Staged file writes
            context: Transaction context
            
        Returns:
            ExecutionResult if validation fails, None if passes
        """
        self.logger.log_event(
            state=self.state_machine.get_state().name,
            event="SEMANTIC_VALIDATION_START",
            details={"files": list(staged_writes.keys())}
        )
        
        semantic_valid, semantic_issues = self.semantic_validator.validate(
            set(staged_writes.keys()),
            staged_writes
        )
        
        # Log and display issues
        if semantic_issues:
            errors = [i for i in semantic_issues if i.severity == "error"]
            warnings = [i for i in semantic_issues if i.severity == "warning"]
            
            if errors:
                print("\n[!] Semantic validation errors:")
                for error in errors:
                    print(f"  {error.file}:{error.line} - {error.message}")
                    if error.suggestion:
                        print(f"    Suggestion: {error.suggestion}")
            
            if warnings:
                print("\n[!] Semantic validation warnings:")
                for warning in warnings:
                    print(f"  {warning.file}:{warning.line} - {warning.message}")
                    if warning.suggestion:
                        print(f"    Suggestion: {warning.suggestion}")
        
        # Fail if semantic errors found
        if not semantic_valid:
            error_summary = f"{len([i for i in semantic_issues if i.severity == 'error'])} semantic error(s)"
            self.logger.log_event(
                state=self.state_machine.get_state().name,
                event="SEMANTIC_VALIDATION_FAILED",
                details={"error_summary": error_summary}
            )
            # Transition to ABORT then IDLE to allow next iteration
            self.state_machine.transition_to(State.ABORT)
            self.state_machine.transition_to(State.IDLE)
            
            # Check if max_iterations reached
            if context.current_iteration >= context.max_iterations:
                return ExecutionResult(
                    status="MAX_ITERATIONS",
                    modified_files=[],
                    iterations=context.current_iteration,
                    errors=[f"Semantic validation failed: {error_summary}"]
                )
            else:
                return ExecutionResult(
                    status="FAILED",
                    modified_files=[],
                    iterations=context.current_iteration,
                    errors=[f"Semantic validation failed: {error_summary}"]
                )
        
        return None
    
    def _check_stagnation(
        self,
        intent_hash: str,
        content_hash: str,
        context: TransactionContext
    ) -> Optional[ExecutionResult]:
        """
        Check for stagnation (identical content across iterations).
        
        Args:
            intent_hash: Intent fingerprint
            content_hash: Content fingerprint
            context: Transaction context
            
        Returns:
            ExecutionResult if stagnation detected, None otherwise
        """
        last_iteration = context.get_last_iteration()
        if not last_iteration:
            return None
        
        if (last_iteration['intent_hash'] == intent_hash and
            last_iteration['content_hash'] == content_hash):
            self.logger.log_event(
                state=self.state_machine.get_state().name,
                event="STAGNATION_DETECTED_IDENTICAL_CONTENT",
                details={
                    "iteration": context.current_iteration,
                    "intent_hash": intent_hash[:16],
                    "content_hash": content_hash[:16]
                }
            )
            return ExecutionResult(
                status="STAGNATED",
                modified_files=[],
                iterations=context.current_iteration,
                errors=[f"Stagnation detected: {'planner generated' if context.iteration_mode else ''} identical content"]
            )
        
        return None
    
    def _get_target_files(self, intent: PatchIntent) -> Set[str]:
        """Get target files from intent"""
        if intent.is_multi_file:
            return set(intent.target_files)
        return {intent.target_file}
    
    def _get_file_content(self, file: str, context: TransactionContext) -> str:
        """Get file content from baseline or disk"""
        baseline = context.get_baseline(file)
        if baseline and baseline.get("content") is not None:
            return baseline["content"]
        
        # Fallback to disk
        try:
            with open(os.path.join(self.target_project_path, file), 'r') as f:
                return f.read()
        except (FileNotFoundError, TypeError):
            return ""
    
    def _log_iteration_summary(self, intent: PatchIntent, context: TransactionContext):
        """Log iteration summary for user"""
        try:
            print("\n" + "=" * 70)
            print(f"ITERATION {context.current_iteration}")
            print("=" * 70)
            if intent.is_multi_file:
                print(f"Planned operation: multi-file intent")
            else:
                print(f"Planned operation: {intent.operation.value}")
            target_files = intent.target_files if intent.is_multi_file else [intent.target_file]
            print(f"Target file(s): {', '.join(target_files)}")
        except Exception:
            # Never let UI printing break core execution
            pass
    
    def _compute_intent_fingerprint(self, intent: PatchIntent) -> str:
        """Compute fingerprint for intent"""
        intent_str = str(intent.to_dict())
        return hashlib.sha256(intent_str.encode('utf-8')).hexdigest()
    
    def _compute_content_fingerprint(self, content: str) -> str:
        """Compute fingerprint for content"""
        return hashlib.sha256(content.encode('utf-8')).hexdigest()
    
    def _compute_error_fingerprint(self, errors: list) -> str:
        """Compute fingerprint for errors"""
        error_str = str(sorted([str(e) for e in errors]))
        return hashlib.sha256(error_str.encode('utf-8')).hexdigest()
