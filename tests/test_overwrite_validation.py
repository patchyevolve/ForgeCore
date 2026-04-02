"""
Test suite for the 'overwrite trick' and dynamic baseline management.
Verifies that CREATE_FILE on an existing file correctly bypasses rewrite ratio
and updates baselines for subsequent iterations.
"""

import os
import sys
import unittest
from unittest.mock import MagicMock

# Add parent directory to path
TEST_DIR = os.path.dirname(os.path.abspath(__file__))
PARENT_DIR = os.path.dirname(TEST_DIR)
sys.path.insert(0, PARENT_DIR)

from core.controller import Controller
from core.patch_intent import PatchIntent, Operation
from core.transaction_context import TransactionContext

class TestOverwriteTrick(unittest.TestCase):
    def setUp(self):
        self.project_path = os.path.join(TEST_DIR, "test_proj_overwrite")
        os.makedirs(self.project_path, exist_ok=True)
        
        # Create a small file that would trigger rewrite ratio if modified normally
        self.test_file = "small_file.py"
        self.full_path = os.path.join(self.project_path, self.test_file)
        with open(self.full_path, "w") as f:
            f.write("# Small file\nprint('hello')\n")
            
        self.logger = MagicMock()
        self.controller = Controller(self.project_path, self.logger)
        # Force a low rewrite ratio to make it easy to trigger
        self.controller.rewrite_ratio_threshold = 0.1
        
    def tearDown(self):
        import shutil
        if os.path.exists(self.project_path):
            shutil.rmtree(self.project_path)

    def test_overwrite_bypasses_ratio(self):
        """Test that CREATE_FILE on existing file bypasses rewrite ratio"""
        # 1. Create intent to OVERWRITE the small file
        # This would be a 100% rewrite, which exceeds 0.1 threshold
        new_content = "def new_func():\n    return 42\n"
        intent = PatchIntent(
            operation=Operation.CREATE_FILE,
            target_file=self.test_file,
            payload={"content": new_content}
        )
        
        # 2. Execute via controller
        # We'll use a transaction context to simulate a real run
        context = TransactionContext(iteration_mode=False)
        context.increment_iteration()
        
        # Ensure baseline is captured
        self.controller._ensure_baselines(intent, context)
        
        # Generate mutations
        staged_writes = self.controller._generate_mutations(intent, context)
        
        # Validate - THIS SHOULD PASS because it's a CREATE_FILE op
        valid, reason = self.controller._validate_mutations(staged_writes, context, intent)
        self.assertTrue(valid, f"Validation failed: {reason}")
        
        # Apply
        success, err = self.controller._apply_mutations(staged_writes, context)
        self.assertTrue(success, f"Apply failed: {err}")
        
        # Verify file content on disk
        with open(self.full_path, "r") as f:
            content = f.read()
        self.assertEqual(content, new_content)
        
        # Verify baseline was updated
        baseline = context.get_baseline(self.test_file)
        self.assertEqual(baseline["content"], new_content)

    def test_normal_modify_fails_ratio(self):
        """Test that REPLACE_CONTENT still fails rewrite ratio for the same change"""
        new_content = "def new_func():\n    return 42\n"
        with open(self.full_path, "r") as f:
            old_content = f.read()
            
        intent = PatchIntent(
            operation=Operation.REPLACE_CONTENT,
            target_file=self.test_file,
            payload={"old_content": old_content, "new_content": new_content}
        )
        
        context = TransactionContext(iteration_mode=False)
        context.increment_iteration()
        self.controller._ensure_baselines(intent, context)
        staged_writes = self.controller._generate_mutations(intent, context)
        
        # Validate - THIS SHOULD FAIL because it's REPLACE_CONTENT
        valid, reason = self.controller._validate_mutations(staged_writes, context, intent)
        self.assertFalse(valid)
        self.assertIn("excessive rewrite", reason)

if __name__ == "__main__":
    unittest.main()
