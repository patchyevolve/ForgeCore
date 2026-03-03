"""Test expanded operation surface"""

from core.controller import Controller
from core.patch_intent import PatchIntent, Operation
from core.logger import Logger
import time

TARGET_PROJECT_PATH = r"D:\codeWorks\graphicstics\graphicstuff"

class MockBuild:
    def __init__(self, path):
        pass
    def run_build(self):
        return {"exit_code": 0, "stdout": "", "stderr": ""}

class MockSymbolValidator:
    """Mock symbol validator that always passes"""
    def __init__(self, indexer):
        self.indexer = indexer
    
    def validate_symbol_usage(self, modified_files, check_undefined=True, check_unused=False):
        """Always return valid"""
        return True, []

def test_add_include():
    """Test ADD_INCLUDE operation"""
    print("\n" + "="*60)
    print("TEST 1: Add Include")
    print("="*60)
    
    logger = Logger()
    controller = Controller(TARGET_PROJECT_PATH, logger)
    controller.builder = MockBuild(TARGET_PROJECT_PATH)
    
    task = "Add include <iostream> to main.cpp"
    
    print(f"Task: {task}")
    result = controller.execute_task(task)
    print(f"Result: {result}")
    
    if "completed successfully" in result.lower():
        print("\nPASS PASS - Include added")
        return True
    else:
        print(f"\nFAIL FAIL - {result}")
        return False

def test_insert_before():
    """Test INSERT_BEFORE operation"""
    print("\n" + "="*60)
    print("TEST 2: Insert Before")
    print("="*60)
    
    logger = Logger()
    controller = Controller(TARGET_PROJECT_PATH, logger)
    controller.builder = MockBuild(TARGET_PROJECT_PATH)
    
    # Use direct intent for precise control
    unique_comment = f"// Before marker {int(time.time())}"
    
    intent = PatchIntent(
        operation=Operation.INSERT_BEFORE,
        target_file="main.cpp",
        payload={
            "anchor": "int main",
            "content": unique_comment
        }
    )
    
    print(f"Inserting before 'int main': {unique_comment}")
    result = controller.execute_patch_intent(intent)
    print(f"Result: {result}")
    
    if "succced" in result:
        print("\nPASS PASS - Content inserted before anchor")
        return True
    else:
        print(f"\nFAIL FAIL - {result}")
        return False

def test_insert_after():
    """Test INSERT_AFTER operation"""
    print("\n" + "="*60)
    print("TEST 3: Insert After")
    print("="*60)
    
    logger = Logger()
    controller = Controller(TARGET_PROJECT_PATH, logger)
    controller.builder = MockBuild(TARGET_PROJECT_PATH)
    
    unique_comment = f"// After marker {int(time.time())}"
    
    intent = PatchIntent(
        operation=Operation.INSERT_AFTER,
        target_file="main.cpp",
        payload={
            "anchor": "#include",
            "content": unique_comment
        }
    )
    
    print(f"Inserting after '#include': {unique_comment}")
    result = controller.execute_patch_intent(intent)
    print(f"Result: {result}")
    
    if "succced" in result:
        print("\nPASS PASS - Content inserted after anchor")
        return True
    else:
        print(f"\nFAIL FAIL - {result}")
        return False

def test_replace_content():
    """Test REPLACE_CONTENT operation"""
    print("\n" + "="*60)
    print("TEST 4: Replace Content")
    print("="*60)
    
    logger = Logger()
    controller = Controller(TARGET_PROJECT_PATH, logger)
    controller.builder = MockBuild(TARGET_PROJECT_PATH)
    
    # First add a marker
    marker = f"REPLACE_ME_{int(time.time())}"
    intent1 = PatchIntent(
        operation=Operation.APPEND_RAW,
        target_file="main.cpp",
        payload={"content": f"// {marker}\n"}
    )
    
    print(f"Adding marker: {marker}")
    result1 = controller.execute_patch_intent(intent1)
    print(f"Add result: {result1}")
    
    if "succced" not in result1:
        print("\nFAIL FAIL - Could not add marker")
        return False
    
    # Now replace it
    intent2 = PatchIntent(
        operation=Operation.REPLACE_CONTENT,
        target_file="main.cpp",
        payload={
            "old_content": f"// {marker}",
            "new_content": f"// REPLACED_{marker}"
        }
    )
    
    print(f"Replacing marker...")
    result2 = controller.execute_patch_intent(intent2)
    print(f"Replace result: {result2}")
    
    if "succced" in result2:
        print("\nPASS PASS - Content replaced")
        return True
    else:
        print(f"\nFAIL FAIL - {result2}")
        return False

def test_replace_function():
    """Test REPLACE_FUNCTION operation"""
    print("\n" + "="*60)
    print("TEST 5: Replace Function")
    print("="*60)
    
    logger = Logger()
    controller = Controller(TARGET_PROJECT_PATH, logger)
    controller.builder = MockBuild(TARGET_PROJECT_PATH)
    
    # Use mock symbol validator to bypass validation (testing operation mechanics only)
    controller.symbol_validator = MockSymbolValidator(controller.indexer)
    
    # First add a function
    func_name = f"test_replace_{int(time.time())}"
    intent1 = PatchIntent(
        operation=Operation.ADD_FUNCTION_STUB,
        target_file="main.cpp",
        payload={"name": func_name}
    )
    
    print(f"Adding function: {func_name}")
    result1 = controller.execute_patch_intent(intent1)
    print(f"Add result: {result1}")
    
    if "succced" not in result1:
        print("\nFAIL FAIL - Could not add function")
        return False
    
    # Now replace its body
    new_body = "    // New implementation\n    return 42;\n"
    intent2 = PatchIntent(
        operation=Operation.REPLACE_FUNCTION,
        target_file="main.cpp",
        payload={
            "name": func_name,
            "body": new_body
        }
    )
    
    print(f"Replacing function body...")
    result2 = controller.execute_patch_intent(intent2)
    print(f"Replace result: {result2}")
    
    if "succced" in result2:
        print("\nPASS PASS - Function replaced")
        return True
    else:
        print(f"\nFAIL FAIL - {result2}")
        return False

def test_planner_with_new_operations():
    """Test planner can generate new operation types"""
    print("\n" + "="*60)
    print("TEST 6: Planner with New Operations")
    print("="*60)
    
    logger = Logger()
    controller = Controller(TARGET_PROJECT_PATH, logger)
    controller.builder = MockBuild(TARGET_PROJECT_PATH)
    
    # Use mock symbol validator to bypass validation (testing planner mechanics only)
    controller.symbol_validator = MockSymbolValidator(controller.indexer)
    
    # Test include task
    task = "Add include <vector> to main.cpp"
    print(f"\nTask: {task}")
    result = controller.execute_task(task)
    print(f"Result: {result}")
    
    if "completed successfully" not in result.lower():
        print(f"FAIL Include task failed: {result}")
        return False
    
    print("PASS Include task succeeded")
    
    # Test append task (simpler and more reliable)
    task2 = "Append to main.cpp: // Planner test marker"
    print(f"\nTask: {task2}")
    result2 = controller.execute_task(task2)
    print(f"Result: {result2}")
    
    # Check if planner generated the intent and executed successfully
    if "completed successfully" in result2.lower():
        print("PASS Append task succeeded")
        return True
    else:
        print(f"FAIL Unexpected result: {result2}")
        return False

def main():
    print("\n" + "#"*60)
    print("# EXPANDED OPERATIONS TEST SUITE")
    print("#"*60)
    
    results = {}
    
    try:
        results['Add Include'] = test_add_include()
    except Exception as e:
        print(f"\nFAIL Exception: {e}")
        import traceback
        traceback.print_exc()
        results['Add Include'] = False
    
    try:
        results['Insert Before'] = test_insert_before()
    except Exception as e:
        print(f"\nFAIL Exception: {e}")
        import traceback
        traceback.print_exc()
        results['Insert Before'] = False
    
    try:
        results['Insert After'] = test_insert_after()
    except Exception as e:
        print(f"\nFAIL Exception: {e}")
        import traceback
        traceback.print_exc()
        results['Insert After'] = False
    
    try:
        results['Replace Content'] = test_replace_content()
    except Exception as e:
        print(f"\nFAIL Exception: {e}")
        import traceback
        traceback.print_exc()
        results['Replace Content'] = False
    
    try:
        results['Replace Function'] = test_replace_function()
    except Exception as e:
        print(f"\nFAIL Exception: {e}")
        import traceback
        traceback.print_exc()
        results['Replace Function'] = False
    
    try:
        results['Planner New Ops'] = test_planner_with_new_operations()
    except Exception as e:
        print(f"\nFAIL Exception: {e}")
        import traceback
        traceback.print_exc()
        results['Planner New Ops'] = False
    
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
        print("\nOK All expanded operation tests passed!")
        print("   • ADD_INCLUDE - Add header includes")
        print("   • INSERT_BEFORE - Insert before anchor")
        print("   • INSERT_AFTER - Insert after anchor")
        print("   • REPLACE_CONTENT - Replace text content")
        print("   • REPLACE_FUNCTION - Replace function body")
        print("   • Planner supports new operations")
    
    print("#"*60)
    
    return all(results.values())

if __name__ == "__main__":
    success = main()
    exit(0 if success else 1)


