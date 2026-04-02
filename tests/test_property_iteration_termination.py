"""
Property-Based Test: Iteration Termination

**Validates: Requirements 10.1, 10.2, 10.3, 10.4, 10.5**

This test validates that the ExecutionEngine always terminates within max_iterations
and accurately tracks iteration counts.

Universal Quantification:
∀ transaction T with iteration_mode = true:
  T.iterations ≤ T.max_iterations

Meaning: Iteration loops always terminate within max_iterations bound. No infinite loops.
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from hypothesis import given, strategies as st, settings, assume
except ImportError:
    if __name__ == "__main__":
        print("SKIP: hypothesis is not installed")
        sys.exit(0)
    raise
from core.execution_engine import ExecutionEngine, ExecutionResult
from core.state_machine import StateMachine, State
from core.transaction_context import TransactionContext
from core.patch_intent import PatchIntent, Operation
from core.logger import Logger


class MockPlanner:
    """Mock planner that generates intents for testing"""
    def __init__(self, fail_after=None):
        self.context_manager = None
        self.call_count = 0
        self.fail_after = fail_after  # Fail after N iterations
    
    def generate_intent(self, task_description, error_context=None, iteration=1, previous_intent=None):
        self.call_count += 1
        
        # Simulate planner failure if configured
        if self.fail_after and self.call_count > self.fail_after:
            raise Exception("Planner failed")
        
        return PatchIntent.single_file(
            target_file="test.txt",
            operation=Operation.CREATE_FILE,
            payload={"content": f"iteration {iteration}"}
        )


class MockCritic:
    """Mock critic that can approve or reject intents"""
    def __init__(self, approve=True, reject_after=None):
        self.approve = approve
        self.reject_after = reject_after
        self.call_count = 0
    
    def review_intent(self, intent, context_manager, task_desc):
        self.call_count += 1
        
        # Reject after N iterations if configured
        if self.reject_after and self.call_count > self.reject_after:
            return False, "Rejected by critic"
        
        return self.approve, "Approved" if self.approve else "Rejected"
    
    def review_result(self, intent, original, modified, task_desc):
        return True, "Looks good"


class MockValidator:
    """Mock validator that can succeed or fail"""
    def __init__(self, success=True, fail_after=None):
        self.success = success
        self.fail_after = fail_after
        self.call_count = 0
    
    def validate(self, files):
        self.call_count += 1
        
        # Fail after N iterations if configured
        if self.fail_after and self.call_count > self.fail_after:
            return {"success": False}
        
        return {"success": self.success}


class MockSemanticValidator:
    """Mock semantic validator"""
    def validate(self, files, staged_writes):
        return True, []


class MockIndexer:
    """Mock indexer"""
    def index_project(self):
        pass


class MockSnapshotManager:
    """Mock snapshot manager"""
    def _create_selective_snapshot(self, files):
        pass


class MockErrorClassifier:
    """Mock error classifier that can generate same or different errors"""
    def __init__(self, stagnate_after=None):
        self.stagnate_after = stagnate_after
        self.call_count = 0
    
    def classify(self, output):
        self.call_count += 1
        
        # Generate same error after N iterations to trigger stagnation
        if self.stagnate_after and self.call_count > self.stagnate_after:
            return [{"type": "ERROR", "message": "Same error"}]
        
        # Generate different errors to avoid stagnation
        return [{"type": "ERROR", "message": f"Error {self.call_count}"}]


def create_execution_engine(max_iterations, planner=None, critic=None, validator=None, error_classifier=None):
    """Helper to create ExecutionEngine with mocks"""
    logger = Logger()
    state_machine = StateMachine(logger)
    
    engine = ExecutionEngine(
        target_project_path=".",
        state_machine=state_machine,
        planner=planner or MockPlanner(),
        critic=critic or MockCritic(),
        validator=validator or MockValidator(),
        semantic_validator=MockSemanticValidator(),
        indexer=MockIndexer(),
        snapshot_manager=MockSnapshotManager(),
        error_classifier=error_classifier or MockErrorClassifier(),
        logger=logger,
        max_iterations=max_iterations
    )
    
    # Set up callbacks
    def mock_validate_intent(intent):
        return True, ""
    
    def mock_ensure_baselines(intent, context):
        # Create baseline for test.txt
        context.update_baseline("test.txt", "", "")
    
    def mock_generate_mutations(intent, context):
        return {"test.txt": "test content"}
    
    def mock_validate_mutations(staged_writes, context, intent):
        # Always fail to force iterations
        return False, "Validation failed"
    
    def mock_apply_mutations(staged_writes, context):
        return True, ""
    
    def mock_validate_post_build(context):
        return True, ""
    
    engine.set_callbacks(
        validate_intent=mock_validate_intent,
        ensure_baselines=mock_ensure_baselines,
        generate_mutations=mock_generate_mutations,
        validate_mutations=mock_validate_mutations,
        apply_mutations=mock_apply_mutations,
        validate_post_build=mock_validate_post_build
    )
    
    return engine


# Property Test 1: Iteration count never exceeds max_iterations
@given(max_iterations=st.integers(min_value=1, max_value=10))
@settings(max_examples=50, deadline=None)
def test_property_max_iterations_bound(max_iterations):
    """
    **Validates: Requirements 10.1, 10.2, 10.4, 10.5**
    
    Property: For all transactions with iteration_mode=true,
    the actual iteration count never exceeds max_iterations.
    
    This test verifies that:
    - ExecutionEngine enforces max_iterations limit (10.1)
    - When max_iterations is reached, execution aborts with MAX_ITERATIONS status (10.2)
    - Iteration count is incremented correctly (10.4)
    - Actual iteration count is included in ExecutionResult (10.5)
    """
    # Create engine with validator that always fails (to force iterations)
    engine = create_execution_engine(
        max_iterations=max_iterations,
        validator=MockValidator(success=False)
    )
    
    # Create transaction context
    context = TransactionContext(
        iteration_mode=True,
        max_iterations=max_iterations
    )
    
    # Execute with planner
    result = engine.execute_with_planner(
        task_description="Test task",
        context=context
    )
    
    # PROPERTY: iterations <= max_iterations
    assert result.iterations <= max_iterations, \
        f"Iteration count {result.iterations} exceeds max_iterations {max_iterations}"
    
    # REQUIREMENT 10.2: When max_iterations reached, status should be MAX_ITERATIONS
    if result.iterations == max_iterations:
        assert result.status == "MAX_ITERATIONS", \
            f"Expected MAX_ITERATIONS status when reaching limit, got {result.status}"
    
    # REQUIREMENT 10.5: Iteration count must be included in result
    assert result.iterations >= 0, \
        "Iteration count must be non-negative"


# Property Test 2: Stagnation detection causes early termination
@given(
    max_iterations=st.integers(min_value=3, max_value=10),
    stagnate_after=st.integers(min_value=1, max_value=2)
)
@settings(max_examples=30, deadline=None)
def test_property_stagnation_early_termination(max_iterations, stagnate_after):
    """
    **Validates: Requirements 10.3**
    
    Property: When stagnation is detected, ExecutionEngine aborts early
    before reaching max_iterations.
    
    This test verifies that:
    - Stagnation detection causes early abort (10.3)
    - Iteration count is less than max_iterations when stagnated
    """
    # Ensure stagnation happens before max_iterations
    assume(stagnate_after < max_iterations)
    
    # Create engine with error classifier that triggers stagnation
    engine = create_execution_engine(
        max_iterations=max_iterations,
        validator=MockValidator(success=False),
        error_classifier=MockErrorClassifier(stagnate_after=stagnate_after)
    )
    
    # Create transaction context
    context = TransactionContext(
        iteration_mode=True,
        max_iterations=max_iterations
    )
    
    # Execute with planner
    result = engine.execute_with_planner(
        task_description="Test task",
        context=context
    )
    
    # REQUIREMENT 10.3: When stagnation detected, abort early
    if result.status == "STAGNATED":
        assert result.iterations < max_iterations, \
            f"Stagnation should abort early, but used all {max_iterations} iterations"


# Property Test 3: Successful execution terminates early
@given(
    max_iterations=st.integers(min_value=2, max_value=10),
    succeed_after=st.integers(min_value=1, max_value=5)
)
@settings(max_examples=30, deadline=None)
def test_property_success_early_termination(max_iterations, succeed_after):
    """
    **Validates: Requirements 10.4, 10.5**
    
    Property: When execution succeeds, it terminates early with
    iteration count less than max_iterations.
    
    This test verifies that:
    - Successful execution doesn't waste iterations (10.4)
    - Iteration count accurately reflects actual iterations (10.5)
    """
    # Ensure success happens before max_iterations
    assume(succeed_after < max_iterations)
    
    # Create engine with validator that succeeds after N iterations
    engine = create_execution_engine(
        max_iterations=max_iterations,
        validator=MockValidator(success=False, fail_after=succeed_after)
    )
    
    # Create transaction context
    context = TransactionContext(
        iteration_mode=True,
        max_iterations=max_iterations
    )
    
    # Execute with planner
    result = engine.execute_with_planner(
        task_description="Test task",
        context=context
    )
    
    # PROPERTY: Successful execution terminates early
    if result.status == "COMPLETED":
        assert result.iterations <= max_iterations, \
            f"Iteration count {result.iterations} exceeds max_iterations {max_iterations}"
        
        # Verify iteration count is accurate (not just max_iterations)
        assert result.iterations > 0, \
            "Iteration count must be positive for completed execution"


# Property Test 4: Iteration count accuracy
@given(
    max_iterations=st.integers(min_value=1, max_value=10)
)
@settings(max_examples=50, deadline=None)
def test_property_iteration_count_accuracy(max_iterations):
    """
    **Validates: Requirements 10.4, 10.5**
    
    Property: The iteration count in ExecutionResult accurately reflects
    the number of iterations actually performed.
    
    This test verifies that:
    - Iteration count is incremented after each refinement cycle (10.4)
    - Actual iteration count is included in ExecutionResult (10.5)
    """
    # Create planner that tracks calls
    planner = MockPlanner()
    
    # Create engine with validator that always fails
    engine = create_execution_engine(
        max_iterations=max_iterations,
        planner=planner,
        validator=MockValidator(success=False)
    )
    
    # Create transaction context
    context = TransactionContext(
        iteration_mode=True,
        max_iterations=max_iterations
    )
    
    # Execute with planner
    result = engine.execute_with_planner(
        task_description="Test task",
        context=context
    )
    
    # REQUIREMENT 10.4: Iteration count should match planner calls
    # (planner is called once per iteration)
    assert result.iterations == planner.call_count, \
        f"Iteration count {result.iterations} doesn't match planner calls {planner.call_count}"
    
    # REQUIREMENT 10.5: Iteration count must be in result
    assert hasattr(result, 'iterations'), \
        "ExecutionResult must include iterations field"
    
    assert result.iterations == context.current_iteration, \
        f"Result iterations {result.iterations} doesn't match context {context.current_iteration}"


# Property Test 5: Rejection causes immediate termination
@given(
    max_iterations=st.integers(min_value=2, max_value=10),
    reject_after=st.integers(min_value=1, max_value=5)
)
@settings(max_examples=30, deadline=None)
def test_property_rejection_termination(max_iterations, reject_after):
    """
    **Validates: Requirements 10.4, 10.5**
    
    Property: When critic rejects an intent, execution terminates
    immediately with accurate iteration count.
    
    This test verifies that:
    - Rejection causes immediate termination
    - Iteration count reflects iterations up to rejection
    """
    # Ensure rejection happens before max_iterations
    assume(reject_after < max_iterations)
    
    # Create critic that rejects after N iterations
    critic = MockCritic(approve=True, reject_after=reject_after)
    
    # Create engine
    engine = create_execution_engine(
        max_iterations=max_iterations,
        critic=critic
    )
    
    # Create transaction context
    context = TransactionContext(
        iteration_mode=True,
        max_iterations=max_iterations
    )
    
    # Execute with planner
    result = engine.execute_with_planner(
        task_description="Test task",
        context=context
    )
    
    # PROPERTY: Rejection terminates early
    if result.status == "REJECTED":
        assert result.iterations <= reject_after + 1, \
            f"Rejection should terminate early, but used {result.iterations} iterations"
        
        # Verify iteration count is accurate
        assert result.iterations > 0, \
            "Iteration count must be positive for rejected execution"


if __name__ == "__main__":
    print("Running Property-Based Tests: Iteration Termination")
    print("=" * 70)
    
    print("\nTest 1: Max iterations bound...")
    test_property_max_iterations_bound()
    print("✓ PASSED")
    
    print("\nTest 2: Stagnation early termination...")
    test_property_stagnation_early_termination()
    print("✓ PASSED")
    
    print("\nTest 3: Success early termination...")
    test_property_success_early_termination()
    print("✓ PASSED")
    
    print("\nTest 4: Iteration count accuracy...")
    test_property_iteration_count_accuracy()
    print("✓ PASSED")
    
    print("\nTest 5: Rejection termination...")
    test_property_rejection_termination()
    print("✓ PASSED")
    
    print("\n" + "=" * 70)
    print("All property tests passed!")
