import os
import difflib
import hashlib
import json
from datetime import datetime
from typing import Optional
from core.state_machine import StateMachine, State
from core.snapshot import SnapshotManager
from tools.smart_validator import SmartValidator
from tools.build_system_monitor import BuildSystemMonitor
from tools.dispatcher import TierViolationError, ToolDispatcher
from tools.error_classifier import BuildErrorClassifier
from core.indexer import ProjectIndexer
from core.patch_intent import PatchIntent
from core.patch_intent import Operation
from core.dependency_validator import DependencyValidator
from core.planner import Planner, PlannerError
from core.symbol_validator import SymbolValidator, UndefinedSymbolError
from core.call_graph_analyzer import CallGraphAnalyzer
from core.transaction_context import TransactionContext


class Controller:

    SUPPORTED_OPERATIONS = {
        Operation.APPEND_RAW,
        Operation.ADD_FUNCTION_STUB,
        Operation.REPLACE_FUNCTION,
        Operation.INSERT_BEFORE,
        Operation.INSERT_AFTER,
        Operation.ADD_INCLUDE,
        Operation.REPLACE_CONTENT,
        Operation.CREATE_FILE
    }

    def __init__ (self, target_project_path, logger):
        self.logger = logger
        self.target_project_path = target_project_path
        
        # Load invariants from policy file
        invariants_path = "policy/invariants.json"
        with open(invariants_path, 'r') as f:
            invariants = json.load(f)
        
        # Execution constraints
        self.max_iterations = invariants["execution"]["max_iterations"]
        self.max_files_per_patch = invariants["execution"]["max_files_per_patch"]
        self.max_lines_per_file = invariants["execution"]["max_lines_per_file"]
        self.rewrite_ratio_threshold = invariants["execution"]["rewrite_ratio_threshold"]
        self.stagnation_detection_enabled = invariants["execution"]["stagnation_detection_enabled"]
        
        # Validation flags
        self.file_integrity_guard_enabled = invariants["validation"]["file_integrity_guard_enabled"]
        self.tier_enforcement_enabled = invariants["validation"]["tier_enforcement_enabled"]
        self.module_integrity_check_enabled = invariants["validation"]["module_integrity_check_enabled"]
        self.symbol_validation_enabled = invariants["validation"]["symbol_validation_enabled"]
        self.call_graph_validation_enabled = invariants["validation"]["call_graph_validation_enabled"]
        self.path_traversal_check_enabled = invariants["validation"]["path_traversal_check_enabled"]
        
        # Safety flags
        self.snapshot_before_mutation = invariants["safety"]["snapshot_before_mutation"]
        self.rollback_on_failure = invariants["safety"]["rollback_on_failure"]
        self.atomic_multi_file_commits = invariants["safety"]["atomic_multi_file_commits"]
        self.baseline_tracking_enabled = invariants["safety"]["baseline_tracking_enabled"]
        
        # Optional strictness profile (low / medium / high) to tune behaviour
        strictness_cfg = invariants.get("strictness", {})
        self.strictness_level = strictness_cfg.get("level", "medium").lower()
        if self.strictness_level not in {"low", "medium", "high"}:
            self.strictness_level = "medium"
        
        # Apply strictness profile overrides (non-destructive defaults)
        if self.strictness_level == "low":
            # More permissive: relax validations and rewrite limits
            self.symbol_validation_enabled = False
            self.call_graph_validation_enabled = False
            self.rewrite_ratio_threshold = max(self.rewrite_ratio_threshold, 0.8)
        elif self.strictness_level == "high":
            # Stricter: tighten rewrite ratio and keep all validations on
            self.rewrite_ratio_threshold = min(self.rewrite_ratio_threshold, 0.3)
        
        # Store full invariants for reference
        self.invariants = invariants
        
        # State tracking (backward compatibility with tests)
        self.current_iteration = 0
        self.modified_files = set()
        self.iteration_history = []
        self.last_error_hash = None
        self.current_task_description = None

        self.state_machine = StateMachine(logger)
        self.snapshot_manager = SnapshotManager(target_project_path)
        self.dispatcher = ToolDispatcher(target_project_path)
        self.validator = SmartValidator(target_project_path, logger)
        self.build_monitor = BuildSystemMonitor(target_project_path, logger)
        self.error_classifier = BuildErrorClassifier()
        self.indexer = ProjectIndexer(target_project_path)
        
        # Load tier policy for dependency validation
        tier_policy_path = "policy/tier_policy.json"
        with open(tier_policy_path, 'r') as f:
            tier_policy = json.load(f)
        self.dependency_validator = DependencyValidator(self.indexer, tier_policy)
        
        # Initialize symbol validator
        self.symbol_validator = SymbolValidator(self.indexer)
        
        # Initialize call graph analyzer
        self.call_graph_analyzer = CallGraphAnalyzer(self.symbol_validator)
        
        # Initialize planner
        self.planner = Planner(logger, self.indexer)
        
        # Initialize critic
        from core.critic import Critic
        self.critic = Critic(use_llm=True)

    def _compute_intent_fingerprint(self, intent: PatchIntent) -> str:
        """Compute deterministic hash of intent for stagnation detection"""
        import json
        intent_dict = intent.to_dict()
        intent_json = json.dumps(intent_dict, sort_keys=True)
        return hashlib.sha256(intent_json.encode('utf-8')).hexdigest()

    def _compute_content_fingerprint(self, content: str) -> str:
        """Compute hash of generated content"""
        return hashlib.sha256(content.encode('utf-8')).hexdigest()
    
    def _compute_error_fingerprint(self, errors: list) -> str:
        """Compute hash of error set for progress detection"""
        import json
        error_json = json.dumps(errors, sort_keys=True)
        return hashlib.sha256(error_json.encode('utf-8')).hexdigest()

    def _line_diff_count(self, original, new):
        original_lines = original.splitlines()
        new_lines = new.splitlines()

        diff = difflib.ndiff(original_lines, new_lines)

        changed = 0
        for line in diff:
            if line.startswith("+ ") or line.startswith("- "):
                changed += 1

        return changed

    def _symbol_exists(self, symbol_name):
        conn = self.indexer.conn
        cursor = conn.cursor()
        cursor.execute(
            "SELECT file FROM symbols WHERE name = ?",
            (symbol_name,)
            )
        return cursor.fetchall()

    def _file_indexed(self, relative_path):
        conn = self.indexer.conn
        cursor = conn.cursor()
        cursor.execute(
            "SELECT path FROM files WHERE path = ?",
            (relative_path,)
            )
        return cursor.fetchone() is not None

    def _snapshot_exists(self):
        return (
        self.snapshot_manager.snapshot_path is not None and
        os.path.exists(self.snapshot_manager.snapshot_path)
    )

    def _generate_content(self, original_content, intent: PatchIntent):
        """Generate new file content based on intent operation"""
        
        if intent.operation == Operation.CREATE_FILE:
            # For CREATE_FILE, return the content directly
            return intent.payload["content"]
        
        if intent.operation == Operation.APPEND_RAW:
            return original_content + "\n" + intent.payload["content"] + "\n"

        if intent.operation == Operation.ADD_FUNCTION_STUB:
            function_name = intent.payload["name"]
            return original_content + f"\nvoid {function_name}()\n{{\n}}\n"
        
        if intent.operation == Operation.REPLACE_FUNCTION:
            function_name = intent.payload["name"]
            new_body = intent.payload["body"]
            
            # Simple pattern matching for function replacement
            # Find function definition and replace body
            lines = original_content.split('\n')
            result_lines = []
            in_function = False
            brace_count = 0
            found_function = False
            
            for line in lines:
                if not in_function:
                    # Look for function definition
                    if function_name in line and '(' in line:
                        # Found function signature
                        result_lines.append(line)
                        in_function = True
                        found_function = True
                        # Check if opening brace is on same line
                        if '{' in line:
                            brace_count = line.count('{') - line.count('}')
                            # Replace with new body
                            result_lines.append(new_body)
                            if brace_count == 0:
                                in_function = False
                    else:
                        result_lines.append(line)
                else:
                    # Inside function, count braces to find end
                    brace_count += line.count('{') - line.count('}')
                    if brace_count == 0:
                        # End of function, add closing brace
                        result_lines.append('}')
                        in_function = False
                    # Skip old function body
            
            if not found_function:
                raise ValueError(f"Function '{function_name}' not found in file")
            
            return '\n'.join(result_lines)
        
        if intent.operation == Operation.INSERT_BEFORE:
            anchor = intent.payload["anchor"]
            content = intent.payload["content"]
            
            lines = original_content.split('\n')
            result_lines = []
            inserted = False
            
            for line in lines:
                if not inserted and anchor in line:
                    result_lines.append(content)
                    inserted = True
                result_lines.append(line)
            
            if not inserted:
                raise ValueError(f"Anchor '{anchor}' not found in file")
            
            return '\n'.join(result_lines)
        
        if intent.operation == Operation.INSERT_AFTER:
            anchor = intent.payload["anchor"]
            content = intent.payload["content"]
            
            lines = original_content.split('\n')
            result_lines = []
            inserted = False
            
            for line in lines:
                result_lines.append(line)
                if not inserted and anchor in line:
                    result_lines.append(content)
                    inserted = True
            
            if not inserted:
                raise ValueError(f"Anchor '{anchor}' not found in file")
            
            return '\n'.join(result_lines)
        
        if intent.operation == Operation.ADD_INCLUDE:
            header = intent.payload["header"]
            is_system = intent.payload.get("system", False)
            
            # Format include directive
            if is_system:
                include_line = f"#include <{header}>"
            else:
                include_line = f'#include "{header}"'
            
            # Check if include already exists
            if include_line in original_content:
                return original_content  # Already included
            
            # Insert after existing includes or at top
            lines = original_content.split('\n')
            result_lines = []
            inserted = False
            last_include_idx = -1
            
            # Find last include directive
            for i, line in enumerate(lines):
                if line.strip().startswith('#include'):
                    last_include_idx = i
            
            if last_include_idx >= 0:
                # Insert after last include
                for i, line in enumerate(lines):
                    result_lines.append(line)
                    if i == last_include_idx:
                        result_lines.append(include_line)
                        inserted = True
            else:
                # No includes found, insert at top (after any header comments)
                skip_comments = True
                for line in lines:
                    if skip_comments and (line.strip().startswith('//') or 
                                         line.strip().startswith('/*') or
                                         line.strip() == ''):
                        result_lines.append(line)
                    else:
                        if not inserted:
                            result_lines.append(include_line)
                            result_lines.append('')
                            inserted = True
                        result_lines.append(line)
                        skip_comments = False
            
            return '\n'.join(result_lines)
        
        if intent.operation == Operation.REPLACE_CONTENT:
            old_content = intent.payload["old_content"]
            new_content = intent.payload["new_content"]
            
            if old_content not in original_content:
                raise ValueError(f"Content to replace not found in file")
            
            # Replace first occurrence
            return original_content.replace(old_content, new_content, 1)

        raise ValueError(f"Unsupported operation: {intent.operation}")

    def _validate_intent(self, intent: PatchIntent):
        """Validate intent (supports both single and multi-file)"""
        
        # Validate all mutations
        for mutation in intent.mutations:
            # Check operation support
            if mutation.operation not in self.SUPPORTED_OPERATIONS:
                return False, f"Unsupported operation: {mutation.operation}"
            
            # Check file indexed (skip for CREATE_FILE)
            if mutation.operation != Operation.CREATE_FILE:
                if not self._file_indexed(mutation.target_file):
                    return False, f"Target file not indexed: {mutation.target_file}"
            
            # Operation-specific validation
            if mutation.operation == Operation.ADD_FUNCTION_STUB:
                function_name = mutation.payload["name"]
                if self._symbol_exists_in_file(function_name, mutation.target_file):
                    return False, f"duplicate Symbol '{function_name}' in {mutation.target_file}"
        
        return True, None

    def _symbol_exists_in_file(self, symbol_name, relative_path):
        cursor = self.indexer.conn.cursor()
        cursor.execute(
            "SELECT 1 FROM symbols WHERE name = ? AND file = ?",
            (symbol_name, relative_path)
        )
        return cursor.fetchone() is not None

    def _get_target_files(self, intent: PatchIntent) -> set:
        """Extract target files from intent (supports both single and multi-file)"""
        return set(intent.target_files)
    
    def _capture_baselines(self, files: set) -> dict:
        """Capture baseline state for files"""
        baselines = {}
        for file in files:
            content = self.dispatcher.read_file(file)
            baselines[file] = {
                "hash": hashlib.sha256(content.encode('utf-8')).hexdigest(),
                "content": content,
                "size": len(content.splitlines())
            }
        return baselines
    
    def _capture_baseline(self, file: str) -> dict:
        """
        Capture baseline state for a single file
        
        Args:
            file: File path
            
        Returns:
            Baseline dict with hash, content, size
        """
        content = self.dispatcher.read_file(file)
        return {
            "hash": hashlib.sha256(content.encode('utf-8')).hexdigest(),
            "content": content,
            "size": len(content.splitlines())
        }
    
    def _ensure_baselines(self, intent: PatchIntent, context: TransactionContext) -> None:
        """
        Ensure baselines exist for all files in intent.
        Captures baselines for new files dynamically (per-iteration expansion).
        
        This is critical for multi-iteration planner execution where the planner
        may introduce new files across iterations.
        
        For CREATE_FILE operations, creates empty baseline for non-existent files.
        
        Args:
            intent: Current intent
            context: Transaction context
        """
        target_files = self._get_target_files(intent)
        new_files = context.get_missing_baselines(target_files)
        
        if new_files:
            self.logger.log_event(
                state=self.state_machine.get_state().name,
                event="DYNAMIC_BASELINE_CAPTURE",
                details={
                    "new_files": list(new_files),
                    "iteration": context.current_iteration,
                    "total_baselines": len(context.baselines) + len(new_files)
                }
            )
            
            for file in new_files:
                # Check if this is a CREATE_FILE operation
                is_create_file = any(
                    m.operation == Operation.CREATE_FILE and m.target_file == file
                    for m in intent.mutations
                )
                
                if is_create_file:
                    # For CREATE_FILE, create empty baseline
                    baseline = {"hash": "", "content": "", "size": 0}
                    self.logger.log_event(
                        state=self.state_machine.get_state().name,
                        event="CREATE_FILE_EMPTY_BASELINE",
                        details={"file": file}
                    )
                else:
                    # For existing files, capture actual baseline
                    baseline = self._capture_baseline(file)
                
                context.add_baseline(file, baseline)
    
    def _generate_mutations(self, intent: PatchIntent, context: TransactionContext) -> dict:
        """
        Generate content for all file mutations (supports both single and multi-file)
        
        Args:
            intent: Patch intent
            context: Transaction context
            
        Returns:
            Dict of file -> new content
        """
        staged_writes = {}
        
        # Use the mutations property which works for both single and multi-file
        for mutation in intent.mutations:
            baseline = context.get_baseline(mutation.target_file)
            if not baseline:
                raise ValueError(f"No baseline for {mutation.target_file}")
            
            original_content = baseline["content"]
            
            # Create a temporary single-file intent for _generate_content
            # This maintains backward compatibility with existing _generate_content method
            temp_intent = PatchIntent(
                operation=mutation.operation,
                target_file=mutation.target_file,
                payload=mutation.payload
            )
            
            new_content = self._generate_content(original_content, temp_intent)
            staged_writes[mutation.target_file] = new_content
        
        return staged_writes
    
    def _validate_mutations(self, staged_writes: dict, context: TransactionContext) -> tuple:
        """
        Validate staged mutations with cross-file awareness
        
        Checks:
        - Per-file rewrite ratio
        - Cross-file total rewrite ratio
        - Line limits per file
        - File count limits
        - File existence and path traversal
        - File integrity guards
        - Tier enforcement
        - Build system file warnings
        
        Args:
            staged_writes: Dict of file -> new content
            context: Transaction context
            
        Returns:
            (valid, reason) tuple
        """
        total_baseline_lines = 0
        total_changed_lines = 0
        
        # Check for build system file modifications
        requires_confirmation, build_warnings = self.build_monitor.check_modifications(
            list(staged_writes.keys())
        )
        
        if build_warnings:
            for warning in build_warnings:
                self.logger.log_event(
                    state=self.state_machine.get_state().name,
                    event="BUILD_SYSTEM_WARNING",
                    details={"warning": warning}
                )
                print(f"\n{warning}")
        
        # Check for new build targets and API changes
        for file, new_content in staged_writes.items():
            baseline = context.get_baseline(file)
            if baseline and baseline.get("content"):
                old_content = baseline["content"]
                
                # Detect new build targets
                target_warnings = self.build_monitor.detect_new_targets(
                    file, old_content, new_content
                )
                for warning in target_warnings:
                    self.logger.log_event(
                        state=self.state_machine.get_state().name,
                        event="BUILD_TARGET_WARNING",
                        details={"warning": warning}
                    )
                    print(f"\n{warning}")
                
                # Check for public API changes
                api_warnings = self.build_monitor.check_public_api_changes(
                    file, old_content, new_content
                )
                for warning in api_warnings:
                    self.logger.log_event(
                        state=self.state_machine.get_state().name,
                        event="API_CHANGE_WARNING",
                        details={"warning": warning}
                    )
                    print(f"\n{warning}")
        
        # Mark files as candidates (not yet committed to modified_files)
        for file in staged_writes.keys():
            context.mark_candidate(file)
        
        # Per-file validation
        print("\nPlanned file changes this iteration:")
        
        for file, new_content in staged_writes.items():
            baseline = context.get_baseline(file)
            if not baseline:
                context.clear_candidates()
                return False, f"Internal error: no baseline for {file}"
            
            # Check if this is a CREATE_FILE operation (empty baseline)
            is_new_file = baseline.get("hash") == ""
            
            line_diff = self._line_diff_count(baseline["content"], new_content)
            
            # User-facing summary of per-file impact
            try:
                if is_new_file:
                    print(f"  [create] {file}  (~{line_diff} lines)")
                else:
                    size = baseline["size"]
                    print(f"  [modify] {file}  (~{line_diff} changed lines out of {size})")
            except Exception:
                # Never let UI printing break validation
                pass
            
            # Track totals for cross-file validation
            total_baseline_lines += baseline["size"]
            total_changed_lines += line_diff
            
            # Skip rewrite ratio check for new files (CREATE_FILE)
            if not is_new_file:
                # Per-file rewrite ratio check (only for existing files)
                if baseline["size"] > 0:
                    change_ratio = line_diff / baseline["size"]
                else:
                    change_ratio = 1
                
                if change_ratio > self.rewrite_ratio_threshold:
                    context.clear_candidates()
                    return False, f"Patch rejected: excessive rewrite in {file} (ratio: {change_ratio:.2%})"
            
            # Per-file line limit check
            if line_diff > self.max_lines_per_file:
                context.clear_candidates()
                return False, f"Patch rejected: line modification limit exceeded for {file}"
        
        # Cross-file rewrite ratio check (for multi-file mutations)
        if len(staged_writes) > 1:
            if total_baseline_lines > 0:
                cross_file_ratio = total_changed_lines / total_baseline_lines
                if cross_file_ratio > self.rewrite_ratio_threshold:
                    self.logger.log_event(
                        state=self.state_machine.get_state().name,
                        event="CROSS_FILE_REWRITE_RATIO_VIOLATION",
                        details={
                            "files": list(staged_writes.keys()),
                            "total_baseline_lines": total_baseline_lines,
                            "total_changed_lines": total_changed_lines,
                            "ratio": cross_file_ratio
                        }
                    )
                    context.clear_candidates()
                    return False, f"Patch rejected: excessive cross-file rewrite (ratio: {cross_file_ratio:.2%}, files: {len(staged_writes)})"
        
        # File count check (use candidate files for check)
        # NOTE: This enforces max_files_per_patch across the ENTIRE TRANSACTION.
        # If planner modifies 5 different files across 5 iterations, it will hit this limit.
        # This is intentional: max_files_per_patch = per transaction, not per iteration.
        total_files = len(context.modified_files) + len(context.candidate_files)
        if total_files > self.max_files_per_patch:
            context.clear_candidates()
            return False, f"Patch rejected: file modification limit exceeded ({total_files} > {self.max_files_per_patch})"
        
        # File existence and path traversal checks
        for file in staged_writes.keys():
            full_path = os.path.join(self.target_project_path, file)
            
            # Check if this is a CREATE_FILE operation
            baseline = context.get_baseline(file)
            is_new_file = baseline and baseline.get("hash") == ""
            
            if not is_new_file:
                # For existing files, verify they exist
                if not os.path.isfile(full_path):
                    context.clear_candidates()
                    return False, f"Semantic rejection: {file} not found on disk"
            
            # Path traversal check (applies to all files)
            project_root = os.path.abspath(self.target_project_path)
            normalized = os.path.abspath(full_path)
            if os.path.commonpath([project_root, normalized]) != project_root:
                context.clear_candidates()
                return False, f"Semantic rejection: path traversal detected in {file}"
        
        # File integrity guard - verify files unchanged since baseline
        for file in staged_writes.keys():
            baseline = context.get_baseline(file)
            is_new_file = baseline and baseline.get("hash") == ""
            
            if not is_new_file:
                # Only check integrity for existing files
                current_disk_content = self.dispatcher.read_file(file)
                current_hash = hashlib.sha256(current_disk_content.encode('utf-8')).hexdigest()
                
                if current_hash != baseline["hash"]:
                    context.clear_candidates()
                    return False, f"Abort: {file} was modified externally during execution"
        
        # Tier check (cross-file aware)
        tier_violations = []
        for file in staged_writes.keys():
            tier = self.dispatcher._get_tier(file)
            if tier == "tier2":
                tier_violations.append(file)
        
        if tier_violations:
            context.clear_candidates()
            return False, f"Tier violation detected in files: {', '.join(tier_violations)}"
        
        return True, ""
    
    def _apply_mutations(self, staged_writes: dict, context: TransactionContext) -> tuple:
        """
        Apply all writes atomically and commit candidates to modified_files
        
        Args:
            staged_writes: Dict of file -> new content
            context: Transaction context
            
        Returns:
            (success, error) tuple
        """
        self.logger.log_event(
            state=self.state_machine.get_state().name,
            event="APPLYING_STAGED_WRITES",
            details={"files": list(staged_writes.keys())}
        )
        
        for file_path, content in staged_writes.items():
            try:
                # Check if this is a CREATE_FILE operation
                baseline = context.get_baseline(file_path)
                is_new_file = baseline and baseline.get("hash") == ""
                
                if is_new_file:
                    # Use create_file for new files
                    self.dispatcher.create_file(file_path, content, allow_tier1=True)
                else:
                    # Use overwrite_file for existing files
                    self.dispatcher.overwrite_file(file_path, content, allow_tier1=True)
            except Exception as e:
                # Clear candidates on write failure
                context.clear_candidates()
                return False, f"Write failed for {file_path}: {e}"
        
        # All writes succeeded - commit candidates to modified_files
        context.commit_candidates()
        
        return True, ""
    
    def _validate_post_build(self, context: TransactionContext) -> tuple:
        """
        Post-build validation with cross-file awareness
        
        Validates:
        - Module integrity (file-level dependencies)
        - Symbol usage (cross-file symbol resolution)
        - Call graph integrity (cross-file call relationships)
        
        Args:
            context: Transaction context
            
        Returns:
            (valid, reason) tuple
        """
        modified_files = context.modified_files
        
        # Log cross-file validation start for multi-file mutations
        if len(modified_files) > 1:
            self.logger.log_event(
                state=self.state_machine.get_state().name,
                event="CROSS_FILE_VALIDATION_START",
                details={
                    "files": list(modified_files),
                    "file_count": len(modified_files)
                }
            )
        
        # Reindex modified files
        self.indexer.reindex_files(modified_files)
        
        # File-level dependency validation (cross-file aware)
        is_valid, issues = self.dependency_validator.validate_module_integrity(modified_files)
        if not is_valid:
            return False, f"Module integrity check failed: {'; '.join(issues)}"
        
        # Symbol-level validation (cross-file symbol resolution)
        symbol_issues = []
        if self.symbol_validation_enabled:
            symbol_valid, symbol_issues = self.symbol_validator.validate_symbol_usage(
                modified_files,
                check_undefined=True,
                check_unused=False
            )
            
            if not symbol_valid:
                # Log cross-file symbol issues
                if len(modified_files) > 1:
                    self.logger.log_event(
                        state=self.state_machine.get_state().name,
                        event="CROSS_FILE_SYMBOL_VALIDATION_FAILED",
                        details={
                            "files": list(modified_files),
                            "issues": symbol_issues
                        }
                    )
                return False, f"Symbol validation failed: {'; '.join(symbol_issues)}"
            
            # Log symbol warnings
            warnings = [issue for issue in symbol_issues if issue.startswith("Warning:")]
            if warnings:
                self.logger.log_event(
                    state=self.state_machine.get_state().name,
                    event="SYMBOL_VALIDATION_WARNINGS",
                    details={"warnings": warnings}
                )
        
        # Call graph integrity validation (cross-file call relationships)
        graph_issues = []
        if self.call_graph_validation_enabled:
            graph_valid, graph_issues = self.call_graph_analyzer.validate_call_graph_integrity(
                modified_files,
                check_dead_code=False,
                check_recursion=True,
                check_unreachable=False
            )
            
            if not graph_valid:
                # Log cross-file call graph issues
                if len(modified_files) > 1:
                    self.logger.log_event(
                        state=self.state_machine.get_state().name,
                        event="CROSS_FILE_CALL_GRAPH_FAILED",
                        details={
                            "files": list(modified_files),
                            "issues": graph_issues
                        }
                    )
                return False, f"Call graph validation failed: {'; '.join(graph_issues)}"
            
            # Log call graph warnings
            graph_warnings = [issue for issue in graph_issues if issue.startswith("Warning:")]
            if graph_warnings:
                self.logger.log_event(
                    state=self.state_machine.get_state().name,
                    event="CALL_GRAPH_WARNINGS",
                    details={"warnings": graph_warnings}
                )
        
        # Log successful cross-file validation
        if len(modified_files) > 1:
            self.logger.log_event(
                state=self.state_machine.get_state().name,
                event="CROSS_FILE_VALIDATION_PASSED",
                details={
                    "files": list(modified_files),
                    "file_count": len(modified_files)
                }
            )
        
        self.logger.log_event(
            state=self.state_machine.get_state().name,
            event="MODULE_INTEGRITY_PASSED",
            details={"modified_files": list(modified_files)}
        )
        
        return True, ""
    
    def _handle_commit(self, context: TransactionContext) -> str:
        """
        Commit changes and cleanup
        
        Args:
            context: Transaction context
            
        Returns:
            Success message
        """
        self.state_machine.transition_to(State.COMMIT)
        self.snapshot_manager.cleanup_snapshot()
        self.state_machine.transition_to(State.IDLE)
        # Return different messages based on execution mode
        if context.planner_context is not None:
            return f"Task completed successfully after {context.current_iteration} iteration(s)"
        else:
            return f"build succced after {context.current_iteration} iteration(s)."
    
    def _handle_abort(self, reason: str) -> str:
        """Rollback changes and cleanup"""
        self.state_machine.transition_to(State.ABORT)
        if self._snapshot_exists():
            self.snapshot_manager.rollback()
        self.indexer.index_project()
        self.snapshot_manager.cleanup_snapshot()
        self.state_machine.transition_to(State.IDLE)
        return reason

    def _execute_intent_core(self, intent: Optional[PatchIntent], context: TransactionContext) -> str:
        """
        Single mutation spine for both execution paths with dynamic baseline management
        
        Args:
            intent: Initial PatchIntent (None for planner mode - planner generates first intent)
            context: Transaction context with all execution state
        
        Returns:
            Result message
        """
        # Index project
        self.indexer.index_project()
        
        # Create snapshot
        self.snapshot_manager.create_snapshot()
        
        if not self._snapshot_exists():
            return self._handle_abort("Snapshot creation failed unexpectedly")
        
        # Iteration loop
        while context.should_continue():
            context.increment_iteration()
            
            # PLANNING - Generate/refine intent if planner mode
            self.state_machine.transition_to(State.PLANNING)
            
            if context.iteration_mode and context.planner_context:
                # Planner mode: generate intent from task
                try:
                    error_context = context.get_error_context()
                    previous_intent = context.get_previous_intent()
                    
                    # Generate new intent for this iteration
                    intent = self.planner.generate_intent(
                        task_description=context.planner_context['task_description'],
                        error_context=error_context,
                        iteration=context.current_iteration,
                        previous_intent=previous_intent
                    )
                    
                except Exception as e:
                    self.logger.log_event(
                        state=self.state_machine.get_state().name,
                        event="PLANNER_FAILED",
                        details={"error": str(e)}
                    )
                    # Sync state before abort
                    self._sync_state_from_context(context)
                    return self._handle_abort(f"Planner failed: {e}")
            
            # DYNAMIC BASELINE EXPANSION - Capture baselines for new files
            # This is critical for multi-iteration planner execution
            self._ensure_baselines(intent, context)
            
            # High-level iteration summary for user
            try:
                print("\n" + "=" * 70)
                print(f"ITERATION {context.current_iteration}")
                print("=" * 70)
                if intent.is_multi_file:
                    print(f"Planned operation: multi-file intent")
                else:
                    print(f"Planned operation: {intent.operation.value}")
                target_files = intent.target_files
                print(f"Target file(s): {', '.join(target_files)}")
            except Exception:
                # Never let UI printing break core execution
                pass
            
            # Validate intent
            valid, reason = self._validate_intent(intent)
            if not valid:
                self.logger.log_event(
                    state=self.state_machine.get_state().name,
                    event="SEMANTIC_REJECT_INVALID_INTENT",
                    details={"reason": reason}
                )
                # Sync state before abort
                self._sync_state_from_context(context)
                return self._handle_abort(f"Semantic rejection: {reason}")
            
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
            target_file = intent.target_file
            try:
                with open(os.path.join(self.target_project_path, target_file), 'r') as f:
                    file_content = f.read()
            except FileNotFoundError:
                # File doesn't exist yet (CREATE_FILE operation)
                file_content = ""
            
            # Review intent with critic
            approved, feedback = self.critic.review_intent(
                intent,
                file_content,
                context.planner_context.get('task_description') if context.planner_context else None
            )
            
            self.logger.log_event(
                state=self.state_machine.get_state().name,
                event="CRITIC_REVIEW_COMPLETE",
                details={
                    "approved": approved,
                    "feedback": feedback[:100]
                }
            )
            
            if not approved:
                self.logger.log_event(
                    state=self.state_machine.get_state().name,
                    event="CRITIC_REJECTED",
                    details={"reason": feedback}
                )
                # For now, continue anyway (critic is advisory)
                # Future: Could abort or request refinement
            
            # PATCH READY
            self.state_machine.transition_to(State.PATCH_READY)
            
            # APPLYING
            self.state_machine.transition_to(State.APPLYING)
            
            # Generate mutations
            staged_writes = self._generate_mutations(intent, context)
            
            # Compute content hash (for stagnation detection)
            # For multi-file, hash all content together
            all_content = ''.join(staged_writes[f] for f in sorted(staged_writes.keys()))
            content_hash = self._compute_content_fingerprint(all_content)
            
            # Check for stagnation (iteration 2+)
            if context.current_iteration > 1:
                last_iteration = context.get_last_iteration()
                
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
                    # Sync state before abort
                    self._sync_state_from_context(context)
                    return self._handle_abort(
                        f"Stagnation detected: {'planner generated' if context.iteration_mode else ''} identical content in iteration {context.current_iteration}"
                    )
            
            # Validate mutations (marks files as candidates)
            valid, reason = self._validate_mutations(staged_writes, context)
            if not valid:
                self.logger.log_event(
                    state=self.state_machine.get_state().name,
                    event="MUTATION_VALIDATION_FAILED",
                    details={"reason": reason}
                )
                # Sync state before abort
                self._sync_state_from_context(context)
                return self._handle_abort(reason)
            
            # Apply mutations (commits candidates to modified_files on success)
            success, error = self._apply_mutations(staged_writes, context)
            if not success:
                self.logger.log_event(
                    state=self.state_machine.get_state().name,
                    event="WRITE_FAILED",
                    details={"error": error}
                )
                # Sync state before abort
                self._sync_state_from_context(context)
                return self._handle_abort(error)
            
            # Update baselines for next iteration (file integrity guard)
            for file, content in staged_writes.items():
                file_hash = hashlib.sha256(content.encode('utf-8')).hexdigest()
                context.update_baseline(file, content, file_hash)
            
            # COMPILING
            self.state_machine.transition_to(State.COMPILING)
            result = self.validator.validate(list(staged_writes.keys()))
            
            if result.get("success", False):
                # SUCCESS PATH
                self.state_machine.transition_to(State.FINAL_CRITIC)
                
                # Final critic review of the result
                for file in staged_writes.keys():
                    try:
                        with open(os.path.join(self.target_project_path, file), 'r') as f:
                            modified_content = f.read()
                        
                        original_content = context.baselines.get(file, {}).get('content', '')
                        
                        approved, feedback = self.critic.review_result(
                            intent,
                            original_content,
                            modified_content,
                            context.planner_context.get('task_description') if context.planner_context else None
                        )
                        
                        self.logger.log_event(
                            state=self.state_machine.get_state().name,
                            event="FINAL_CRITIC_REVIEW",
                            details={
                                "file": file,
                                "approved": approved,
                                "feedback": feedback[:100]
                            }
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
                
                self.logger.log_event(
                    state=self.state_machine.get_state().name,
                    event="FINAL_CRITIC_APPROVED",
                    details={"iteration": context.current_iteration}
                )
                
                # MODULE INTEGRITY CHECK
                self.state_machine.transition_to(State.MODULE_INTEGRITY_CHECK)
                
                valid, reason = self._validate_post_build(context)
                if not valid:
                    # Always log the post-build failure
                    self.logger.log_event(
                        state=self.state_machine.get_state().name,
                        event="POST_BUILD_VALIDATION_FAILED",
                        details={"reason": reason}
                    )
                    
                    # In direct (non-iteration) mode, abort immediately as before
                    if not context.iteration_mode:
                        self._sync_state_from_context(context)
                        return self._handle_abort(reason)
                    
                    # In planner iteration mode, treat post-build validation failures
                    # as refinable errors, similar to compiler/validation failures.
                    structured_errors = [{
                        "type": "POST_BUILD_VALIDATION_FAILED",
                        "message": reason
                    }]
                    error_hash = self._compute_error_fingerprint(structured_errors)
                    
                    self.logger.log_event(
                        state=self.state_machine.get_state().name,
                        event="STRUCTURED_ERRORS",
                        details={"errors": structured_errors, "error_hash": error_hash[:16]}
                    )
                    
                    # Check for error stagnation across iterations
                    if context.last_error_hash and context.last_error_hash == error_hash:
                        self.logger.log_event(
                            state=self.state_machine.get_state().name,
                            event="STAGNATION_DETECTED_IDENTICAL_ERRORS",
                            details={"iteration": context.current_iteration, "error_hash": error_hash[:16]}
                        )
                        self._sync_state_from_context(context)
                        return self._handle_abort(
                            f"Stagnation detected: planner unable to resolve post-build validation errors after iteration {context.current_iteration}"
                        )
                    
                    context.last_error_hash = error_hash
                    
                    # Respect max-iterations guardrail
                    if context.current_iteration >= context.max_iterations:
                        self._sync_state_from_context(context)
                        return self._handle_abort("Max iterations reached. Rolled back")
                    
                    # Record iteration for planner error context
                    context.record_iteration({
                        "iteration": context.current_iteration,
                        "intent": intent,
                        "intent_hash": intent_hash,
                        "content_hash": content_hash,
                        "errors": structured_errors,
                        "error_hash": error_hash,
                        "timestamp": datetime.now().isoformat()
                    })
                    
                    # Allow planner to refine based on post-build validation issues
                    self.state_machine.transition_to(State.REFINEMENT)
                    continue
                
                # COMMIT - Sync state before commit
                self._sync_state_from_context(context)
                return self._handle_commit(context)
            
            # FAILURE PATH
            self.state_machine.transition_to(State.ERROR_CLASSIFY)
            
            # Extract errors from validation result
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
            if context.last_error_hash and context.last_error_hash == error_hash:
                self.logger.log_event(
                    state=self.state_machine.get_state().name,
                    event="STAGNATION_DETECTED_IDENTICAL_ERRORS",
                    details={"iteration": context.current_iteration, "error_hash": error_hash[:16]}
                )
                # Sync state before abort
                self._sync_state_from_context(context)
                return self._handle_abort(
                    f"Stagnation detected: {'planner unable to resolve' if context.iteration_mode else 'identical'} errors after iteration {context.current_iteration}"
                )
            
            context.last_error_hash = error_hash
            
            # If not iteration mode, abort on first failure
            if not context.iteration_mode:
                # Sync state before abort
                self._sync_state_from_context(context)
                return self._handle_abort("Build failed")
            
            # Check iteration limit
            if context.current_iteration >= context.max_iterations:
                # Sync state before abort
                self._sync_state_from_context(context)
                return self._handle_abort("Max iterations reached. Rolled back")
            
            # RECORD ITERATION for planner feedback
            context.record_iteration({
                'iteration': context.current_iteration,
                'intent': intent,
                'intent_hash': intent_hash,
                'content_hash': content_hash,
                'errors': structured_errors,
                'error_hash': error_hash,
                'timestamp': datetime.now().isoformat()
            })
            
            # REFINEMENT - Loop back to planning
            self.state_machine.transition_to(State.REFINEMENT)
        
        # Safety fallback - sync state before abort
        self._sync_state_from_context(context)
        return self._handle_abort("Unexpected termination. Rolled back")
    
    def _sync_state_from_context(self, context: TransactionContext) -> None:
        """
        Sync controller instance variables from transaction context.
        This maintains backward compatibility with tests that check controller state.
        
        Args:
            context: Transaction context
        """
        self.current_iteration = context.current_iteration
        self.modified_files = context.modified_files.copy()
        self.iteration_history = context.iteration_history.copy()
        self.last_error_hash = context.last_error_hash

    def execute_task(self, task_description: str):
        """
        Execute a task using planner-generated intents

        This is the primary entry point for planner-driven execution.
        The planner generates and refines intents across iterations.

        Args:
            task_description: High-level task description

        Returns:
            Result string describing outcome
        """
        try:
            # Store task description for planner context
            self.current_task_description = task_description

            # Create transaction context for planner mode
            # No dummy intent needed - planner generates first real intent
            context = TransactionContext(
                iteration_mode=True,
                planner_context={'task_description': task_description},
                max_iterations=self.max_iterations
            )

            # Use core execution spine with planner mode
            return self._execute_intent_core(
                intent=None,  # Planner generates first intent
                context=context
            )

        except Exception as e:
            self.logger.log_event(
                state=self.state_machine.get_state().name,
                event="EXCEPTION",
                details={"error": str(e)}
            )

            try:
                if self._snapshot_exists():
                    self.snapshot_manager.rollback()
                    self.indexer.index_project()
                    self.snapshot_manager.cleanup_snapshot()
            finally:
                self.state_machine.current_state = State.IDLE

            raise


    def execute_patch_intent(self, intent: PatchIntent):
        """
        Execute a single patch intent directly (no planner)
        
        This is for direct intent execution without planner refinement.
        Useful for testing and direct API usage.
        
        Args:
            intent: PatchIntent to execute
        
        Returns:
            Result string describing outcome
        """
        try:
            # Create transaction context for direct mode
            context = TransactionContext(
                iteration_mode=False,
                planner_context=None,
                max_iterations=1
            )
            
            # Use core execution spine without planner mode
            return self._execute_intent_core(
                intent=intent,
                context=context
            )
            
        except Exception as e:
            self.logger.log_event(
                state=self.state_machine.get_state().name,
                event="EXCEPTION",
                details={"error": str(e)}
            )

            try:
                if self._snapshot_exists():
                    self.snapshot_manager.rollback()
                    self.indexer.index_project()
                    self.snapshot_manager.cleanup_snapshot()
            finally:
                self.state_machine.current_state = State.IDLE

            raise

