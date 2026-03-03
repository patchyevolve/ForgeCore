"""Test multi-file atomic transactions"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.controller import Controller
from core.patch_intent import PatchIntent, FileMutation, Operation
from core.logger import Logger

TARGET_PROJECT_PATH = r"D:\codeWorks\graphicstics\graphicstuff"

class MockBuild:
    def __init__(self, path):
        pass
    def run_build(self):
        return {"exit_code": 0, "stdout": "", "stderr": ""}

def test_file_mutation_creation():
    """Test FileMutation class"""
    print("\n" + "="*60)
    print("TEST 1: FileMutation Creation")
    print("="*60)
    
    # Valid mutation
    mutation = FileMutation(
        target_file="main.cpp",
        operation=Operation.ADD_FUNCTION_STUB,
        payload={"name": "test_func"}
    )
    
    print(f"Created mutation: {mutation.target_file}, {mutation.operation.name}")
    print("PASS FileMutation created successfully")
    
    # Test validation
    try:
        invalid = FileMutation(
            target_file="",
            operation=Operation.ADD_FUNCTION_STUB,
            payload={"name": "test"}
        )
        print("FAIL Should have raised ValueError for empty target_file")
        return False
    except ValueError as e:
        print(f"PASS Validation works: {e}")
    
    return True

def test_single_file_backward_compat():
    """Test that single-file mode still works (backward compatibility)"""
    print("\n" + "="*60)
    print("TEST 2: Single-File Backward Compatibility")
    print("="*60)
    
    # Old way (still works)
    intent = PatchIntent(
        operation=Operation.ADD_FUNCTION_STUB,
        target_file="main.cpp",
        payload={"name": "old_style_func"}
    )
    
    print(f"Single-file intent: {intent.target_file}")
    print(f"Is multi-file: {intent.is_multi_file}")
    print(f"Mutations count: {len(intent.mutations)}")
    print(f"Target files: {intent.target_files}")
    
    if not intent.is_multi_file and len(intent.mutations) == 1:
        print("PASS Backward compatibility maintained")
        return True
    else:
        print("FAIL Backward compatibility broken")
        return False

def test_single_file_factory():
    """Test single_file factory method"""
    print("\n" + "="*60)
    print("TEST 3: Single-File Factory Method")
    print("="*60)
    
    intent = PatchIntent.single_file(
        target_file="main.cpp",
        operation=Operation.APPEND_RAW,
        payload={"content": "// Test comment"}
    )
    
    print(f"Created via factory: {intent.target_file}")
    print(f"Description: {intent.description}")
    
    if not intent.is_multi_file:
        print("PASS Factory method works")
        return True
    else:
        print("FAIL Factory method broken")
        return False

def test_multi_file_intent():
    """Test multi-file intent creation"""
    print("\n" + "="*60)
    print("TEST 4: Multi-File Intent Creation")
    print("="*60)
    
    mutations = [
        FileMutation(
            target_file="file1.cpp",
            operation=Operation.ADD_FUNCTION_STUB,
            payload={"name": "func1"}
        ),
        FileMutation(
            target_file="file2.cpp",
            operation=Operation.ADD_FUNCTION_STUB,
            payload={"name": "func2"}
        )
    ]
    
    intent = PatchIntent.multi_file(
        mutations=mutations,
        description="Add functions to multiple files"
    )
    
    print(f"Multi-file intent created")
    print(f"Is multi-file: {intent.is_multi_file}")
    print(f"Mutations count: {len(intent.mutations)}")
    print(f"Target files: {intent.target_files}")
    print(f"Description: {intent.description}")
    
    if intent.is_multi_file and len(intent.mutations) == 2:
        print("PASS Multi-file intent works")
        return True
    else:
        print("FAIL Multi-file intent broken")
        return False

def test_multi_file_execution():
    """Test executing a multi-file intent"""
    print("\n" + "="*60)
    print("TEST 5: Multi-File Execution")
    print("="*60)
    
    logger = Logger()
    controller = Controller(TARGET_PROJECT_PATH, logger)
    controller.builder = MockBuild(TARGET_PROJECT_PATH)
    
    import time
    unique_suffix = int(time.time())
    
    # Create multi-file intent
    mutations = [
        FileMutation(
            target_file="main.cpp",
            operation=Operation.ADD_FUNCTION_STUB,
            payload={"name": f"multi_func1_{unique_suffix}"}
        ),
        FileMutation(
            target_file="main.cpp",  # Same file, different function
            operation=Operation.ADD_FUNCTION_STUB,
            payload={"name": f"multi_func2_{unique_suffix}"}
        )
    ]
    
    intent = PatchIntent.multi_file(
        mutations=mutations,
        description="Add two functions to main.cpp"
    )
    
    print(f"Executing multi-file intent...")
    print(f"  Mutations: {len(mutations)}")
    print(f"  Target files: {intent.target_files}")
    
    result = controller.execute_patch_intent(intent)
    
    print(f"\nResult: {result}")
    
    if "build succced" in result or "Task completed" in result:
        print("PASS Multi-file execution succeeded")
        return True
    else:
        print(f"FAIL Multi-file execution failed: {result}")
        return False

def test_mutations_property():
    """Test that mutations property works for both modes"""
    print("\n" + "="*60)
    print("TEST 6: Mutations Property")
    print("="*60)
    
    # Single-file
    single = PatchIntent(
        operation=Operation.APPEND_RAW,
        target_file="test.cpp",
        payload={"content": "test"}
    )
    
    print(f"Single-file mutations: {len(single.mutations)}")
    print(f"  First mutation: {single.mutations[0].target_file}")
    
    # Multi-file
    multi = PatchIntent.multi_file(
        mutations=[
            FileMutation("file1.cpp", Operation.APPEND_RAW, {"content": "1"}),
            FileMutation("file2.cpp", Operation.APPEND_RAW, {"content": "2"})
        ]
    )
    
    print(f"Multi-file mutations: {len(multi.mutations)}")
    print(f"  First mutation: {multi.mutations[0].target_file}")
    print(f"  Second mutation: {multi.mutations[1].target_file}")
    
    if len(single.mutations) == 1 and len(multi.mutations) == 2:
        print("PASS Mutations property works for both modes")
        return True
    else:
        print("FAIL Mutations property broken")
        return False

def main():
    print("\n" + "#"*60)
    print("# MULTI-FILE ATOMIC TRANSACTIONS TEST SUITE")
    print("#"*60)
    
    results = {}
    
    tests = [
        ("FileMutation Creation", test_file_mutation_creation),
        ("Single-File Backward Compat", test_single_file_backward_compat),
        ("Single-File Factory", test_single_file_factory),
        ("Multi-File Intent", test_multi_file_intent),
        ("Multi-File Execution", test_multi_file_execution),
        ("Mutations Property", test_mutations_property)
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
        status = "PASS PASS" if success else "FAIL FAIL"
        print(f"{status} - {test_name}")
    
    print(f"\nTotal: {passed}/{total} tests passed")
    
    if all(results.values()):
        print("\nOK All multi-file tests passed!")
        print("   • FileMutation class working")
        print("   • Backward compatibility maintained")
        print("   • Multi-file intents supported")
        print("   • Multi-file execution working")
    
    print("#"*60)
    
    return all(results.values())

if __name__ == "__main__":
    success = main()
    exit(0 if success else 1)
