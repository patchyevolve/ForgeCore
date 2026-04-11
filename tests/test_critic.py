"""Basic unit tests for Critic behaviour."""

import os

from core.critic import Critic, _parse_intent_review_verdict
from core.patch_intent import PatchIntent, Operation


def test_intent_verdict_line_parsing():
    ok, _ = _parse_intent_review_verdict("Issues noted.\nVERDICT: APPROVED")
    assert ok
    bad, fb = _parse_intent_review_verdict("Problems.\nVERDICT: REJECTED")
    assert not bad and "Problems" in fb


def test_simulated_mode():
    """Critic should approve everything in simulated (LLM disabled) mode."""
    prev = os.environ.get("FORGECORE_USE_LLM")
    try:
        os.environ["FORGECORE_USE_LLM"] = "false"
        critic = Critic(use_llm=True)
        assert critic.use_llm is False or critic.llm_client is None

        intent = PatchIntent.single_file("foo.cpp", Operation.ADD_INCLUDE, {"header": "iostream"})
        approved, feedback = critic.review_intent(intent, "int main() {}", task=None)
        assert approved is True
        assert "Simulated" in feedback

        approved2, feedback2 = critic.review_result(intent, "orig", "mod", task=None)
        assert approved2 is True
        assert "Simulated" in feedback2
    finally:
        if prev is None:
            os.environ.pop("FORGECORE_USE_LLM", None)
        else:
            os.environ["FORGECORE_USE_LLM"] = prev


def test_task_optional():
    """Passing None or an empty task string should not crash the critic."""
    critic = Critic(use_llm=False)
    intent = PatchIntent.single_file("bar.cpp", Operation.APPEND_RAW, {"content": "//x"})
    for t in (None, ""):
        approved, feedback = critic.review_intent(intent, "code", task=t)
        assert approved
        approved2, feedback2 = critic.review_result(intent, "a", "b", task=t)
        assert approved2


def test_llm_mocking_behavior():
    """Use a fake LLM client to drive critic decisions.

    This exercises the LLM-path without relying on network or external APIs.
    """
    from core.llm_client import BaseLLMClient

    prev = os.environ.get("FORGECORE_USE_LLM")
    try:
        os.environ["FORGECORE_USE_LLM"] = "true"

        class DummyClient(BaseLLMClient):
            def __init__(self, response):
                self._response = response

            def generate(self, prompt, system=None):
                return "Analysis.\nVERDICT: APPROVED"

            def generate_json(self, prompt, system=None):
                return self._response

        critic = Critic(use_llm=True)
        critic.llm_client = DummyClient({})

        intent = PatchIntent.single_file("baz.cpp", Operation.ADD_INCLUDE, {"header": "foo"})
        ok, fb = critic.review_intent(intent, "whatever", task="dummy")
        assert ok and "LLM Approved" in fb

        class FailingClient(BaseLLMClient):
            def generate(self, prompt, system=None):
                raise RuntimeError("boom")

            def generate_json(self, prompt, system=None):
                raise RuntimeError("boom")

        critic.llm_client = FailingClient()
        ok2, fb2 = critic.review_intent(intent, "whatever", task="x")
        assert ok2 and "Simulated" in fb2
    finally:
        if prev is None:
            os.environ.pop("FORGECORE_USE_LLM", None)
        else:
            os.environ["FORGECORE_USE_LLM"] = prev
