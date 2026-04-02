"""Integration tests for planner and critic coordination."""

import os
import sys
import shutil
import tempfile
import unittest
from unittest.mock import MagicMock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.controller import Controller
from core.patch_intent import PatchIntent, Operation


class SuccessfulBuild:
    def run_build(self):
        return {"exit_code": 0, "stdout": "", "stderr": ""}


class RecordingPlanner:
    def __init__(self, target_file, content):
        self.target_file = target_file
        self.content = content
        self.context_manager = object()
        self.calls = []

    def generate_intent(self, task_description, error_context=None, iteration=1, previous_intent=None):
        self.calls.append(
            {
                "task_description": task_description,
                "error_context": error_context,
                "iteration": iteration,
                "previous_intent": previous_intent,
            }
        )
        return PatchIntent.single_file(
            target_file=self.target_file,
            operation=Operation.CREATE_FILE,
            payload={"content": self.content},
            description=f"Create {self.target_file}",
        )


class RecordingCritic:
    def __init__(self, project_path, target_file, approve_intent=True):
        self.project_path = project_path
        self.target_file = target_file
        self.approve_intent = approve_intent
        self.intent_reviews = []
        self.result_reviews = []
        self.call_order = []

    def review_intent(self, intent, context_manager, task_desc):
        self.call_order.append("intent")
        self.intent_reviews.append(
            {
                "intent": intent,
                "context_manager": context_manager,
                "task_desc": task_desc,
                "file_exists": os.path.exists(os.path.join(self.project_path, self.target_file)),
            }
        )
        if self.approve_intent:
            return True, "Approved"
        return False, "Rejected for test"

    def review_result(self, intent, original, modified, task_desc):
        self.call_order.append("result")
        self.result_reviews.append(
            {
                "intent": intent,
                "task_desc": task_desc,
                "file_exists": os.path.exists(os.path.join(self.project_path, self.target_file)),
                "original": original,
                "modified": modified,
            }
        )
        return True, "Looks good"


class TestPlannerCriticIntegration(unittest.TestCase):
    def setUp(self):
        os.environ["FORGECORE_USE_LLM"] = "false"
        self.project_path = tempfile.mkdtemp(prefix="forgecore_planner_critic_")

    def tearDown(self):
        if os.path.exists(self.project_path):
            shutil.rmtree(self.project_path)

    def _create_controller(self):
        controller = Controller(self.project_path, MagicMock())
        controller.builder = SuccessfulBuild()
        controller.execution_engine._validate_post_build_callback = lambda context: (True, "")
        return controller

    def test_execute_task_passes_through_planner_and_critic_for_file_creation(self):
        controller = self._create_controller()
        task_description = "create created_by_agents.py and finish the task"
        target_file = "created_by_agents.py"
        content = "value = 42\n"
        planner = RecordingPlanner(target_file, content)
        critic = RecordingCritic(self.project_path, target_file, approve_intent=True)

        controller.planner = planner
        controller.critic = critic
        controller.execution_engine.planner = planner
        controller.execution_engine.critic = critic

        result = controller.execute_task(task_description)
        target_path = os.path.join(self.project_path, target_file)

        self.assertIn("Task completed successfully", result)
        self.assertTrue(os.path.exists(target_path))
        with open(target_path, "r", encoding="utf-8") as handle:
            self.assertEqual(handle.read(), content)

        self.assertEqual(len(planner.calls), 1)
        self.assertEqual(planner.calls[0]["task_description"], task_description)
        self.assertEqual(planner.calls[0]["iteration"], 1)

        self.assertEqual(critic.call_order, ["intent", "result"])
        self.assertEqual(len(critic.intent_reviews), 1)
        self.assertEqual(len(critic.result_reviews), 1)
        self.assertFalse(critic.intent_reviews[0]["file_exists"])
        self.assertTrue(critic.result_reviews[0]["file_exists"])
        self.assertIs(critic.intent_reviews[0]["context_manager"], planner.context_manager)
        self.assertEqual(critic.intent_reviews[0]["task_desc"], task_description)
        self.assertEqual(critic.result_reviews[0]["task_desc"], task_description)
        self.assertEqual(critic.intent_reviews[0]["intent"].operation, Operation.CREATE_FILE)
        self.assertEqual(critic.result_reviews[0]["original"], "")
        self.assertEqual(critic.result_reviews[0]["modified"], content)

    def test_critic_rejection_stops_task_before_file_creation(self):
        controller = self._create_controller()
        task_description = "create blocked_by_critic.py and finish the task"
        target_file = "blocked_by_critic.py"
        planner = RecordingPlanner(target_file, "value = 7\n")
        critic = RecordingCritic(self.project_path, target_file, approve_intent=False)

        controller.planner = planner
        controller.critic = critic
        controller.execution_engine.planner = planner
        controller.execution_engine.critic = critic

        result = controller.execute_task(task_description)
        target_path = os.path.join(self.project_path, target_file)

        self.assertIn("Critic rejected intent", result)
        self.assertFalse(os.path.exists(target_path))
        self.assertEqual(critic.call_order, ["intent"])
        self.assertEqual(len(critic.result_reviews), 0)


if __name__ == "__main__":
    unittest.main()
