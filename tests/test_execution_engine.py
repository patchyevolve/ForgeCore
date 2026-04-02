"""Test ExecutionEngine extraction"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.execution_engine import ExecutionEngine, ExecutionResult
from core.state_machine import StateMachine, State
from core.transaction_context import TransactionContext
from core.patch_intent import PatchIntent, Operation
from core.logger import Logger

class MockPlanner:
    def __init__(self):
        self.context_manager = None
    
    def generate_intent(self, task_description, error_context=None, iteration=1, previous_intent=None):
        # Return a simple intent
        return PatchIntent.create_single_file(
            target_file="test.txt",
            operation=Operation.CREATE_FILE,
            payload={"content": "test content"}
        )

class MockCritic:
    def __init__(self, approve=True):
        self.approve = approve
    
    def review_intent(self, intent, context_manager, task_desc):
        return self.approve, "Approved" if self.approve else "Rejected"
    
    def review_result(self, intent, original, modified, task_desc):
        return True, "Looks good"

class MockValidator:
    def __init__(self, success=True):
        self.success = success
    
    def validate(self, files):
        return {"success": self.success}

class MockSemanticValidator:
    def validate(self, files, staged_writes):
        return True, []

class MockIndexer:
    def index_project(self):
        pass

class MockSnapshotManager:
    def _create_selective_snapshot(self, files):
        pass

class MockErrorClassifier:
    def classify(self, output):
        return [{"type": "ERROR", "message": "Test error"}]

def test_execution_engine_initialization():
    """Test ExecutionEngine can be initialized"""
    print("\n" + "="*60)
    print("TEST 1: ExecutionEngine Initialization")
    print("="*60)
    
    logger = Logger()
    state_machine = StateMachine(logger)
    
    engine = ExecutionEngine(
        target_project_path=".",
        state_machine=state_machine,
        planner=MockPlanner(),
        critic=MockCritic(),
        validator=MockValidator(),
        semantic_validator=MockSemanticValidator(),
        indexer=MockIndexer(),
        snapshot_manager=MockSnapshotManager(),
        error_classifier=MockErrorClassifier(),
        logger=logger,
        max_iterations=5
    )
    
    print("ExecutionEngine initialized successfully")
    print(f"Max iterations: {engine.max_iterations}")
    print(f"Stagnation detection: {engine.stagnation_detection_enabled}")
    print("PASS")
    return True

def test_execution_result():
    """Test ExecutionResult data structure"""
    print("\n" + "="*60)
    print("TEST 2: ExecutionResult")
    print("="*60)
    
    # Success result
    result = ExecutionResult(
        status="COMPLETED",
        modified_files=["test.txt"],
        iterations=1
    )
    
    print(f"Status: {result.status}")
    print(f"Is success: {result.is_success()}")
    print(f"Summary: {result.get_summary()}")
    
    assert result.is_success() == True
    assert len(result.modified_files) == 1
    
    # Failure result
    result2 = ExecutionResult(
        status="FAILED",
        modified_files=[],
        iterations=2,
        errors=["Build failed"]
    )
    
    print(f"\nFailure status: {result2.status}")
    print(f"Is success: {result2.is_success()}")
    print(f"Summary: {result2.get_summary()}")
    
    assert result2.is_success() == False
    assert len(result2.errors) == 1
    
    print("PASS")
    return True

def test_callbacks_set():
    """Test that callbacks can be set"""
    print("\n" + "="*60)
    print("TEST 3: Callback Setting")
    print("="*60)
    
    logger = Logger()
    state_machine = StateMachine(logger)
    
    engine = ExecutionEngine(
        target_project_path=".",
        state_machine=state_machine,
        planner=MockPlanner(),
        critic=MockCritic(),
        validator=MockValidator(),
        semantic_validator=MockSemanticValidator(),
        indexer=MockIndexer(),
        snapshot_manager=MockSnapshotManager(),
        error_classifier=MockErrorClassifier(),
        logger=logger
    )
    
    # Mock callbacks
    def mock_validate_intent(intent):
        return True, ""
    
    def mock_ensure_baselines(intent, context):
        pass
    
    def mock_generate_mutations(intent, context):
        return {"test.txt": "content"}
    
    def mock_validate_mutations(staged_writes, context, intent):
        return True, ""
    
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
    
    print("Callbacks set successfully")
    assert engine._validate_intent_callback is not None
    assert engine._ensure_baselines_callback is not None
    assert engine._generate_mutations_callback is not None
    assert engine._validate_mutations_callback is not None
    assert engine._apply_mutations_callback is not None
    assert engine._validate_post_build_callback is not None
    
    print("PASS")
    return True

def main():
    print("\n" + "#"*60)
    print("# EXECUTION ENGINE TEST SUITE")
    print("#"*60)
    
    results = {}
    
    tests = [
        ("ExecutionEngine Initialization", test_execution_engine_initialization),
        ("ExecutionResult", test_execution_result),
        ("Callback Setting", test_callbacks_set)
    ]
    
    for test_name, test_func in tests:
        try:
            results[test_name] = test_func()
        except Exception as e:
            print(f"\nFAIL Exception in {test_name}: {e}")
            import traceback
            traceback.print_exc()
            results[test_name] = False
    
    # Summary
    print("\n" + "="*60)
    print("SUMMARY")
    print("="*60)
    
    passed = sum(1 for v in results.values() if v)
    total = len(results)
    
    for test_name, success in results.items():
        status = "PASS" if success else "FAIL"
        print(f"{status} - {test_name}")
    
    print(f"\nTotal: {passed}/{total} tests passed")
    print("#"*60)
    
    return 0 if passed == total else 1

if __name__ == "__main__":
    sys.exit(main())
