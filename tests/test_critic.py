"""Basic unit tests for Critic behaviour."""

import os

from core.critic import Critic
from core.patch_intent import PatchIntent, Operation


def test_simulated_mode():
    """Critic should approve everything in simulated (LLM disabled) mode."""
    # ensure LLM is not used even if use_llm=True by forcing failure
    os.environ["FORGECORE_USE_LLM"] = "false"
    critic = Critic(use_llm=True)
    # Simulated client ensures llm_client is None or not used
    assert critic.use_llm is False or critic.llm_client is None

    intent = PatchIntent.single_file("foo.cpp", Operation.add_include, {"header": "iostream"})
    approved, feedback = critic.review_intent(intent, "int main() {}", task=None)
    assert approved is True
    assert "Simulated" in feedback

    approved2, feedback2 = critic.review_result(intent, "orig", "mod", task=None)
    assert approved2 is True
    assert "Simulated" in feedback2


def test_task_optional():
    """Passing None or an empty task string should not crash the critic."""
    critic = Critic(use_llm=False)
    intent = PatchIntent.single_file("bar.cpp", Operation.append_raw, {"content": "//x"})
    for t in (None, ""):
        approved, feedback = critic.review_intent(intent, "code", task=t)
        assert approved
        approved2, feedback2 = critic.review_result(intent, "a", "b", task=t)
        assert approved2


def test_llm_mocking_behavior():
    """Use a fake LLM client to drive critic decisions.

    This exercises the LLM-path without relying on network or external APIs.
    """
    class DummyClient(BaseLLMClient):
        def __init__(self, response):
            self._response = response

        def generate_json(self, prompt, system=None):
            # simply return the preset dictionary
            return self._response

    critic = Critic(use_llm=True)
    # replace with dummy client that approves
    dummy_resp = {"approved": True, "feedback": "looks good", "concerns": []}
    critic.llm_client = DummyClient(dummy_resp)

    intent = PatchIntent.single_file("baz.cpp", Operation.add_include, {"header": "foo"})
    ok, fb = critic.review_intent(intent, "whatever", task="dummy")
    assert ok and "looks good" in fb

    # now simulate a failure inside the client to trigger simulated fallback
    class FailingClient(BaseLLMClient):
        def generate_json(self, prompt, system=None):
            raise RuntimeError("boom")

    critic.llm_client = FailingClient()
    # even though use_llm True, error should cause fallback
    ok2, fb2 = critic.review_intent(intent, "whatever", task="x")
    assert ok2 and "Simulated" in fb2
