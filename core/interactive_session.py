"""
Interactive Session - Semi-Autonomous User Approval System

Manages user interaction for semi-autonomous code generation:
1. AI generates plan
2. User approves/rejects plan
3. For each step:
   - AI generates patch
   - User approves/rejects/requests changes
   - If rejected: AI reworks and asks again
4. Apply approved patches
"""

import os
from typing import Dict, Any, List, Optional, Tuple
from core.patch_intent import PatchIntent, Operation
from core.planner import Planner
from core.critic import Critic


class InteractiveSession:
    """
    Manages interactive semi-autonomous code generation.
    
    Flow:
    1. User gives task
    2. AI creates plan → User approves
    3. For each step:
       - AI generates code → User approves
       - If rejected: AI reworks
    4. Execute approved changes
    """
    
    def __init__(self, planner: Planner, critic: Critic, logger):
        self.planner = planner
        self.critic = critic
        self.logger = logger
    
    def run_task(self, task_description: str, controller) -> Dict[str, Any]:
        """
        Run interactive task execution with multi-iteration support.
        
        Args:
            task_description: High-level task from user
            controller: Controller instance
            
        Returns:
            Execution results
        """
        print("\n" + "="*70)
        print("SEMI-AUTONOMOUS MODE")
        print("="*70)
        print(f"\nTask: {task_description}")
        
        self.project_path = controller.target_project_path
        
        iteration = 1
        error_context = []
        previous_intent = None
        all_results = []
        
        while iteration <= controller.max_iterations:
            print("\n" + "="*70)
            print(f"ITERATION {iteration}")
            print("="*70)
            
            # Step 1: Planning
            intent = self._generate_intent_with_approval(
                task_description,
                iteration=iteration,
                error_context=error_context,
                previous_intent=previous_intent
            )
            
            if not intent:
                return {"status": "cancelled", "reason": "User cancelled or max rework reached"}
            
            # Step 2: Execution
            print(f"\n[SYSTEM] Executing approved plan...")
            
            try:
                # Store task description in controller for critic context
                controller.current_task_description = task_description
                
                # Update planner context for the transaction if in iteration 1
                # This ensures the task description is available to the critic
                if iteration == 1:
                    controller.planner.context_manager.project_root = controller.target_project_path
                
                # Execute single intent via controller
                result_msg = controller.execute_patch_intent(intent)
                
                # Check for critic rejection in the result_msg
                is_critic_rejection = "Critic rejected intent" in result_msg
                
                print(f"\n[OK] Iteration {iteration} Result: {result_msg}")
                all_results.append(result_msg)
                
                # Check if task is finished
                if "completed successfully" in result_msg or "build succced" in result_msg:
                    return {
                        "status": "completed",
                        "result": "\n".join(all_results),
                        "iterations": iteration
                    }
                
                # If not finished, prepare for next iteration
                # Add the failure result to error context so planner can refine
                if not error_context:
                    error_context = []
                
                error_context.append({
                    "type": "CRITIC_REJECTION" if is_critic_rejection else "EXECUTION_FAILURE",
                    "message": result_msg,
                    "iteration": iteration
                })
                
                iteration += 1
                previous_intent = intent
                
            except Exception as e:
                print(f"\n[ERROR] Execution failed: {e}")
                error_context.append({
                    "type": "EXCEPTION",
                    "message": str(e),
                    "iteration": iteration
                })
                retry = input("Retry this iteration? (y/n): ").strip().lower()
                if retry != 'y':
                    return {"status": "failed", "reason": str(e)}
        
        return {
            "status": "failed",
            "reason": "Max iterations reached",
            "results": all_results
        }
    
    def _generate_intent_with_approval(
        self,
        task: str,
        iteration: int = 1,
        error_context: Optional[List] = None,
        previous_intent: Optional[PatchIntent] = None
    ) -> Optional[PatchIntent]:
        """
        Generate intent and get user approval with progress indicators.
        
        Returns:
            Approved PatchIntent or None if rejected
        """
        max_rework_attempts = 3
        
        for attempt in range(max_rework_attempts):
            print(f"\n[AI] Planning... (attempt {attempt + 1}/{max_rework_attempts})")
            
            # Show progress indicator
            import sys
            import time
            import threading
            
            # Progress spinner
            spinner_active = True
            spinner_success = False
            def show_spinner():
                spinner = ['|', '/', '-', '\\']
                idx = 0
                while spinner_active:
                    sys.stdout.write(f'\r  {spinner[idx % len(spinner)]} Generating plan...')
                    sys.stdout.flush()
                    time.sleep(0.1)
                    idx += 1
                
                if spinner_success:
                    sys.stdout.write('\r  [OK] Plan generated!     \n')
                else:
                    sys.stdout.write('\r  [X] Planning failed.     \n')
                sys.stdout.flush()
            
            spinner_thread = threading.Thread(target=show_spinner, daemon=True)
            spinner_thread.start()
            
            try:
                # Generate intent
                intent = self.planner.generate_intent(
                    task,
                    error_context,
                    iteration,
                    previous_intent
                )
                
                # Stop spinner with success
                spinner_success = True
                spinner_active = False
                spinner_thread.join(timeout=0.5)
                
                # Show intent to user
                approved, feedback = self._show_intent_for_approval(intent, task, iteration)
                
                if approved:
                    return intent
                
                # User rejected - add feedback to error context
                if not error_context:
                    error_context = []
                error_context.append({
                    "type": "USER_REJECTION",
                    "feedback": feedback,
                    "attempt": attempt + 1
                })
                
                print(f"\n[REWORK] AI will rework based on your feedback...")
                
            except Exception as e:
                # Stop spinner on error
                spinner_active = False
                spinner_thread.join(timeout=0.5)
                
                print(f"\n[ERROR] Planning failed: {e}")
                retry = input("\nRetry? (y/n): ").strip().lower()
                if retry != 'y':
                    return None
        
        print(f"\n[ERROR] Max rework attempts ({max_rework_attempts}) reached")
        return None
    
    def _show_intent_for_approval(
        self,
        intent: PatchIntent,
        task: str,
        iteration: int = 1
    ) -> Tuple[bool, str]:
        """
        Show intent to user and get approval with diff preview.
        
        Returns:
            (approved: bool, feedback: str)
        """
        print("\n" + "-"*70)
        print(f"PLAN GENERATED (Step {iteration})")
        print("-"*70)
        
        if intent.description:
            print(f"\nDescription: {intent.description}")
        
        # Show each mutation in the intent
        mutations = intent.mutations
        print(f"\nPlanned changes ({len(mutations)} file(s)):")
        
        # Track which files were created/modified
        for idx, mutation in enumerate(mutations, 1):
            op_val = mutation.operation.value
            file_path = mutation.target_file
            
            # Prepend project path if file_path is relative for validation
            full_path = file_path
            if not os.path.isabs(file_path) and hasattr(self, 'project_path'):
                full_path = os.path.join(self.project_path, file_path)
            
            status_tag = ""
            if os.path.exists(full_path):
                status_tag = "[EXISTING]"
            else:
                status_tag = "[NEW]"
                
            print(f"\n  {idx}. File: {file_path} {status_tag}")
            print(f"     Operation: {op_val}")
            
            # Explain what this specific mutation will do
            self._explain_mutation(mutation)
            
            # Show diff preview for this mutation
            self._show_mutation_diff_preview(mutation)
        
        print("\n" + "-"*70)
        print("APPROVAL REQUIRED")
        print("-"*70)
        
        while True:
            choice = input("\nApprove this plan? (y/n/m for modify): ").strip().lower()
            
            if choice == 'y':
                return True, ""
            
            elif choice == 'n':
                feedback = input("\nWhy reject? (AI will use this to improve): ").strip()
                return False, feedback if feedback else "User rejected without reason"
            
            elif choice == 'm':
                # Implement modify flow
                return self._handle_modify_flow(intent, task)
            
            else:
                print("Invalid choice. Please enter y, n, or m")

    def _explain_mutation(self, mutation):
        """Explain what a single mutation will do"""
        op = mutation.operation
        file = mutation.target_file
        payload = mutation.payload or {}
        
        if op == Operation.CREATE_FILE:
            lines = len((payload.get("content", "")).splitlines())
            print(f"     → Create new file '{file}' with {lines} lines")
        
        elif op == Operation.ADD_FUNCTION_STUB:
            func_name = payload.get("name", "unknown")
            print(f"     → Add function stub '{func_name}()' to '{file}'")
        
        elif op == Operation.APPEND_RAW:
            lines = len((payload.get("content", "")).splitlines())
            print(f"     → Append {lines} lines to end of '{file}'")
        
        elif op == Operation.REPLACE_FUNCTION:
            func_name = payload.get("name", "unknown")
            print(f"     → Replace function '{func_name}()' body in '{file}'")
        
        elif op == Operation.INSERT_BEFORE:
            anchor = payload.get("anchor", "unknown")
            print(f"     → Insert code before '{anchor}' in '{file}'")
        
        elif op == Operation.INSERT_AFTER:
            anchor = payload.get("anchor", "unknown")
            print(f"     → Insert code after '{anchor}' in '{file}'")
        
        elif op == Operation.ADD_INCLUDE:
            header = payload.get("header", "unknown")
            is_system = payload.get("system", False)
            bracket = "<>" if is_system else '""'
            print(f"     → Add #include {bracket[0]}{header}{bracket[1]} to '{file}'")
        
        elif op == Operation.REPLACE_CONTENT:
            old = (payload.get("old_content", ""))[:50]
            print(f"     → Replace '{old}...' in '{file}'")
        
        else:
            print(f"     → Perform {op.value} on '{file}'")

    def _show_mutation_diff_preview(self, mutation):
        """Show diff preview for a single mutation"""
        import difflib
        
        file_path = mutation.target_file
        # Prepend project path if file_path is relative
        full_path = file_path
        if not os.path.isabs(file_path) and hasattr(self, 'project_path'):
            full_path = os.path.join(self.project_path, file_path)
            
        op = mutation.operation
        payload = mutation.payload or {}
        
        try:
            # Handle CREATE_FILE separately (no old content)
            if op == Operation.CREATE_FILE:
                print(f"\n     DIFF PREVIEW (new file):")
                content = payload.get("content", "")
                lines = content.splitlines()
                for i, line in enumerate(lines[:10], 1):
                    print(f"     \033[32m+ {i:3d} | {line}\033[0m")
                if len(lines) > 10:
                    print(f"     \033[32m... ({len(lines) - 10} more lines)\033[0m")
                return

            if not os.path.exists(full_path):
                print(f"     [WARN] File not found on disk: {file_path}")
                return

            # Read current content
            with open(full_path, 'r', encoding='utf-8', errors='ignore') as f:
                old_content = f.read()
            
            # Generate new content for preview
            # We wrap mutation in a temp intent for the existing _preview_content helper
            from core.patch_intent import PatchIntent
            temp_intent = PatchIntent(
                operation=mutation.operation,
                target_file=mutation.target_file,
                payload=mutation.payload
            )
            new_content = self._preview_content(old_content, temp_intent)
            
            if new_content is None:
                print(f"     (No preview available for this operation)")
                return
            
            # Generate diff
            old_lines = old_content.splitlines(keepends=True)
            new_lines = new_content.splitlines(keepends=True)
            
            diff = list(difflib.unified_diff(
                old_lines,
                new_lines,
                fromfile=f"{file_path} (before)",
                tofile=f"{file_path} (after)",
                n=5,  # 5 lines of context
                lineterm=''
            ))
            
            if diff:
                print(f"\n     DIFF PREVIEW:")
                # Show full diff with better formatting and line numbers
                for line in diff:
                    if line.startswith('---') or line.startswith('+++'):
                        print(f"     \033[90m{line}\033[0m")
                    elif line.startswith('@@'):
                        print(f"     \033[36m{line}\033[0m")
                    elif line.startswith('+'):
                        print(f"     \033[32m{line}\033[0m")
                    elif line.startswith('-'):
                        print(f"     \033[31m{line}\033[0m")
                    else:
                        print(f"     {line}")
            else:
                print(f"\n     \033[93m[INFO] No logical changes detected in this operation\033[0m")
                
        except Exception as e:
            print(f"     [WARN] Could not generate diff: {e}")

    def _handle_modify_flow(self, intent: PatchIntent, task: str) -> Tuple[bool, str]:
        """Handle the user's request to modify the intent"""
        print("\n" + "="*70)
        print("MODIFY PLAN")
        print("="*70)
        
        mutations = list(intent.mutations)
        
        while True:
            print("\nWhat would you like to modify?")
            for idx, m in enumerate(mutations, 1):
                print(f"{idx}. {m.operation.value} on {m.target_file}")
            print(f"{len(mutations) + 1}. Cancel (back to approval)")
            
            try:
                choice_str = input(f"\nChoice (1-{len(mutations) + 1}): ").strip()
                if not choice_str:
                    continue
                choice = int(choice_str)
                
                if choice == len(mutations) + 1:
                    return False, "User cancelled modification"
                
                if 1 <= choice <= len(mutations):
                    mutation_idx = choice - 1
                    mutation = mutations[mutation_idx]
                    
                    print(f"\nModifying mutation {choice}: {mutation.operation.value} on {mutation.target_file}")
                    print("1. Change target file")
                    print("2. Change operation (e.g., replace_content, append_raw)")
                    print("3. Modify payload (AI feedback)")
                    print("4. Done modifying")
                    
                    mod_choice = input("\nChoice (1-4): ").strip()
                    
                    if mod_choice == '1':
                        new_file = input(f"New target file (current: {mutation.target_file}): ").strip()
                        if new_file:
                            # We can't easily modify the frozen mutation, so we ask for rework with this instruction
                            return False, f"User wants to change target file for mutation {choice} to: {new_file}"
                    
                    elif mod_choice == '2':
                        print("\nAvailable operations: append_raw, add_function_stub, replace_function, insert_before, insert_after, add_include, replace_content, create_file")
                        new_op = input(f"New operation (current: {mutation.operation.value}): ").strip()
                        if new_op:
                            return False, f"User wants to change operation for mutation {choice} to: {new_op}"
                    
                    elif mod_choice == '3':
                        feedback = input("\nProvide specific feedback for this mutation: ").strip()
                        if feedback:
                            return False, f"User modification feedback for mutation {choice}: {feedback}"
                    
                    elif mod_choice == '4':
                        continue
                else:
                    print("Invalid choice.")
            except ValueError:
                print("Please enter a number.")
        
        return False, "User cancelled modification"

    def _show_diff_preview(self, intent: PatchIntent):
        """Deprecated in favor of _show_mutation_diff_preview"""
        pass
    
    def _preview_content(self, old_content: str, intent: PatchIntent) -> Optional[str]:
        """
        Preview what the new content will look like (simplified).
        
        Returns:
            New content or None if can't preview
        """
        op = intent.operation
        payload = intent.payload or {}
        
        if op == Operation.CREATE_FILE:
            return payload.get("content", "")
        
        elif op == Operation.APPEND_RAW:
            content = payload.get("content", "")
            return old_content + "\n" + content + "\n"
        
        elif op == Operation.ADD_FUNCTION_STUB:
            func_name = payload.get("name", "unknown")
            return old_content + f"\nvoid {func_name}()\n{{\n}}\n"
        
        elif op == Operation.ADD_INCLUDE:
            header = payload.get("header", "")
            is_system = payload.get("system", False)
            if is_system:
                include_line = f"#include <{header}>"
            else:
                include_line = f'#include "{header}"'
            
            # Insert at top (simplified)
            return include_line + "\n" + old_content
        
        elif op == Operation.REPLACE_CONTENT:
            old = payload.get("old_content", "")
            new = payload.get("new_content", "")
            return old_content.replace(old, new, 1)
        
        elif op == Operation.REPLACE_FUNCTION:
            func_name = payload.get("name", "unknown")
            new_body = payload.get("body", "")
            
            # Simplified replacement for preview
            lines = old_content.split('\n')
            result_lines = []
            in_function = False
            brace_count = 0
            found_function = False
            
            for line in lines:
                if not in_function:
                    if func_name in line and '(' in line:
                        result_lines.append(line)
                        in_function = True
                        found_function = True
                        if '{' in line:
                            brace_count = line.count('{') - line.count('}')
                            result_lines.append(new_body)
                            if brace_count == 0:
                                in_function = False
                    else:
                        result_lines.append(line)
                else:
                    brace_count += line.count('{') - line.count('}')
                    if brace_count == 0:
                        result_lines.append('}')
                        in_function = False
            
            return '\n'.join(result_lines) if found_function else None
        
        elif op == Operation.INSERT_BEFORE:
            anchor = payload.get("anchor", "")
            content = payload.get("content", "")
            return old_content.replace(anchor, content + "\n" + anchor, 1)
            
        elif op == Operation.INSERT_AFTER:
            anchor = payload.get("anchor", "")
            content = payload.get("content", "")
            return old_content.replace(anchor, anchor + "\n" + content, 1)
        
        # For complex operations, return None
        return None
    
    def _explain_intent(self, intent: PatchIntent):
        """Deprecated in favor of _explain_mutation"""
        pass
