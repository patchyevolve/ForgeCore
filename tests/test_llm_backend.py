"""Test LLM backend configuration and fallback logic."""

import sys
import os
import json
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.llm_client import (
    load_config,
    _create_client,
    OllamaClient,
    OnlineLLMClient,
    create_planner_client,
    create_critic_client,
    BaseLLMClient,
)


def write_config(cfg: dict, path: str):
    with open(path, "w") as f:
        json.dump(cfg, f)


def test_local_backend():
    print("\nTEST: local backend selection")
    cfg = {
        "planner": {"backend": "local", "model": "foo", "temperature": 0.1, "timeout": 1},
        "critic": {"backend": "local", "model": "bar", "temperature": 0.1, "timeout": 1},
    }
    path = "config/llm_config.json"
    write_config(cfg, path)

    planner = create_planner_client(path)
    critic = create_critic_client(path)

    print(f"planner type: {type(planner)}")
    print(f"critic type: {type(critic)}")

    if isinstance(planner, OllamaClient) and isinstance(critic, OllamaClient):
        print("PASS local clients created")
        return True
    else:
        print("FAIL wrong backend")
        return False


def test_online_backend_and_fallback():
    print("\nTEST: online backend behavior and fallback")
    cfg = {
        "planner": {"backend": "online", "model": "mymodel", "temperature": 0.5, "timeout": 1},
        "critic": {"backend": "online", "model": "mymodel", "temperature": 0.5, "timeout": 1},
    }
    path = "config/llm_config.json"
    write_config(cfg, path)

    # monkeypatch requests.post to simulate failure
    import requests
    original_post = requests.post

    def fake_post_fail(*args, **kwargs):
        raise requests.RequestException("network down")

    requests.post = fake_post_fail

    # set fallback env var and verify both clients fallback
    os.environ["LLM_FALLBACK_LOCAL"] = "true"
    os.environ["FORGECORE_REMOTE_HEALTHCHECK"] = "true"
    try:
        planner = create_planner_client(path)
        critic = create_critic_client(path)
        print(f"planner fallback type: {type(planner)}")
        print(f"critic fallback type: {type(critic)}")
        if isinstance(planner, OllamaClient) and isinstance(critic, OllamaClient):
            print("PASS fallback to local on online failure")
        else:
            print("FAIL did not fall back")
            return False
    finally:
        requests.post = original_post
        del os.environ["LLM_FALLBACK_LOCAL"]
        os.environ.pop("FORGECORE_REMOTE_HEALTHCHECK", None)

    # now test that online clients do not eagerly hit the network during creation
    call_count = {'count': 0}

    class DummyResponse:
        def __init__(self, data):
            self._data = data
        def raise_for_status(self):
            pass
        def json(self):
            return self._data

    def fake_post(*args, **kwargs):
        call_count['count'] += 1
        # return minimal valid structure
        return DummyResponse({'generated_text': 'pong'})

    requests.post = fake_post

    # ensure an API key is set so OnlineLLMClient does not bail out early
    os.environ["HF_API_KEY"] = "dummy"
    try:
        cfg_online = {
            "planner": {"backend": "online", "model": "test", "temperature": 0.1, "timeout": 1},
            "critic": {"backend": "online", "model": "test", "temperature": 0.1, "timeout": 1},
        }
        write_config(cfg_online, path)
        planner2 = create_planner_client(path)
        critic2 = create_critic_client(path)
        print(f"network calls during creation: {call_count['count']}")
        if call_count['count'] != 0:
            print("FAIL online clients should not eagerly hit network")
            return False
        print("PASS online clients skipped eager network checks")

        os.environ["FORGECORE_REMOTE_HEALTHCHECK"] = "true"
        planner3 = create_planner_client(path)
        critic3 = create_critic_client(path)
        print(f"network calls with healthcheck enabled: {call_count['count']}")
        if call_count['count'] >= 2:
            print("PASS optional healthcheck triggers network calls")
            return True
        print("FAIL optional healthcheck did not hit network")
        return False
    finally:
        del os.environ["HF_API_KEY"]
        os.environ.pop("FORGECORE_REMOTE_HEALTHCHECK", None)


def main():
    all_passed = True
    print("\nRunning LLM backend configuration tests")

    if not test_local_backend():
        all_passed = False
    if not test_online_backend_and_fallback():
        all_passed = False

    if all_passed:
        print("\nAll LLM backend tests passed")
    else:
        print("\nSome LLM backend tests failed")
    return all_passed


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
