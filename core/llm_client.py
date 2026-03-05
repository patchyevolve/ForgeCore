"""
LLM Client module

Provides a pluggable interface allowing both local (Ollama-backed) and
remote (online API) language models to be used interchangeably by the
planner/critic. Configuration is read from `config/llm_config.json` and
runtime behaviour may be overridden via environment variables.
"""

import json
import threading
import os
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional

# third-party dependencies
import ollama
from json_repair import repair_json
import requests


def _load_secrets(secrets_path: str = "config/secrets.json") -> Dict[str, str]:
    """Load secrets from file if it exists."""
    if os.path.exists(secrets_path):
        try:
            with open(secrets_path, "r") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}


class TimeoutError(Exception):
    """Raised when LLM call times out"""
    pass


class BaseLLMClient(ABC):
    """Abstract base class for LLM clients."
    
    Subclasses must implement :meth:`generate` and :meth:`generate_json`.
    """

    @abstractmethod
    def generate(self, prompt: str, system: Optional[str] = None) -> str:
        ...

    @abstractmethod
    def generate_json(self, prompt: str, system: Optional[str] = None) -> Dict[str, Any]:
        ...


class OllamaClient(BaseLLMClient):
    """
    Client for interacting with a local LLM model through Ollama.
    """
    
    def __init__(self, model: str, temperature: float = 0.1, timeout: int = 60):
        """
        Initialize LLM client.
        
        Args:
            model: Model name (e.g., "qwen2.5-coder:7b-instruct")
            temperature: Sampling temperature (0.0 = deterministic, 1.0 = creative)
            timeout: Timeout in seconds for inference
        """
        self.model = model
        self.temperature = temperature
        self.timeout = timeout
    
    def generate(self, prompt: str, system: Optional[str] = None) -> str:
        """
        Generate text from prompt with timeout.
        
        Args:
            prompt: User prompt
            system: Optional system prompt
            
        Returns:
            Generated text
            
        Raises:
            TimeoutError: If generation exceeds timeout
            RuntimeError: If generation fails
        """
        messages = []
        
        if system:
            messages.append({
                'role': 'system',
                'content': system
            })
        
        messages.append({
            'role': 'user',
            'content': prompt
        })
        
        # Use threading to implement timeout
        # explicitly type to allow None values and later Exception
        result: Dict[str, Any] = {'response': None, 'error': None}
        
        def _generate():
            try:
                response = ollama.chat(
                    model=self.model,
                    messages=messages,
                    options={
                        'temperature': self.temperature,
                        'num_predict': 2048
                    }
                )
                result['response'] = response['message']['content']
            except Exception as e:
                # type is Any so assignment is permitted
                result['error'] = e  # type: ignore
        
        thread = threading.Thread(target=_generate)
        thread.daemon = True
        thread.start()
        thread.join(timeout=self.timeout)
        
        if thread.is_alive():
            # Timeout occurred
            raise TimeoutError(f"LLM generation timed out after {self.timeout}s")
        
        if result['error']:
            raise RuntimeError(f"LLM generation failed: {result['error']}")
        
        return result['response']
    
    def generate_json(self, prompt: str, system: Optional[str] = None) -> Dict[str, Any]:
        """
        Generate structured JSON output.
        
        Args:
            prompt: User prompt (should request JSON output)
            system: Optional system prompt
            
        Returns:
            Parsed JSON dict
        """
        # Add JSON instruction to prompt
        json_prompt = f"{prompt}\n\nRESPOND ONLY WITH VALID JSON. NO EXPLANATIONS."
        
        # Generate text
        text = self.generate(json_prompt, system)
        
        # Extract JSON from response (handle markdown code blocks)
        text = text.strip()
        
        # Remove markdown code blocks if present
        if text.startswith('```'):
            lines = text.split('\n')
            # Remove first line (```json or ```)
            lines = lines[1:]
            # Remove last line (```)
            if lines and lines[-1].strip() == '```':
                lines = lines[:-1]
            text = '\n'.join(lines)
        
        # Try to parse JSON
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            # Try to repair malformed JSON
            try:
                repaired = repair_json(text)
                return json.loads(repaired)
            except Exception as e:
                raise ValueError(f"Failed to parse JSON from LLM output: {e}\nOutput: {text[:200]}")


class OnlineLLMClient(BaseLLMClient):
    """Client for interacting with an online LLM inference API."""

    def __init__(
        self,
        model: str,
        api_token: Optional[str],
        temperature: float = 0.1,
        timeout: int = 60,
        endpoint: str = "https://api-inference.huggingface.co/models",
    ):
        self.model = model
        self.api_token = api_token
        self.temperature = temperature
        self.timeout = timeout
        self.endpoint = endpoint.rstrip("/")

    def _post(self, prompt: str) -> str:
        if not self.api_token:
            raise RuntimeError("No API token provided for online LLM")
        headers = {"Authorization": f"Bearer {self.api_token}"}
        data = {"inputs": prompt, "parameters": {"temperature": self.temperature}}
        resp = requests.post(
            f"{self.endpoint}/{self.model}",
            headers=headers,
            json=data,
            timeout=self.timeout,
        )
        resp.raise_for_status()
        payload = resp.json()
        if isinstance(payload, dict):
            return payload.get("generated_text", payload.get("text", ""))
        if isinstance(payload, list) and payload:
            return payload[0].get("generated_text", "")
        return ""

    def generate(self, prompt: str, system: Optional[str] = None) -> str:
        full_prompt = prompt if system is None else f"{system}\n\n{prompt}"
        return self._post(full_prompt)

    def generate_json(self, prompt: str, system: Optional[str] = None) -> Dict[str, Any]:
        json_prompt = f"{prompt}\n\nRESPOND ONLY WITH VALID JSON. NO EXPLANATIONS."
        text = self.generate(json_prompt, system)
        return _parse_json_response(text)


class GroqClient(BaseLLMClient):
    """Client for interacting with the Groq inference API."""

    def __init__(
        self,
        model: str,
        api_token: Optional[str],
        temperature: float = 0.1,
        timeout: int = 60,
        endpoint: str = "https://api.groq.com/openai/v1/chat/completions",
    ):
        self.model = model
        self.api_token = api_token
        self.temperature = temperature
        self.timeout = timeout
        self.endpoint = endpoint

    def generate(self, prompt: str, system: Optional[str] = None) -> str:
        if not self.api_token:
            raise RuntimeError("No API token provided for Groq")
        
        headers = {
            "Authorization": f"Bearer {self.api_token}",
            "Content-Type": "application/json"
        }
        
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        data = {
            "model": self.model,
            "messages": messages,
            "temperature": self.temperature
        }
        
        resp = requests.post(
            self.endpoint,
            headers=headers,
            json=data,
            timeout=self.timeout,
        )
        resp.raise_for_status()
        payload = resp.json()
        return payload["choices"][0]["message"]["content"]

    def generate_json(self, prompt: str, system: Optional[str] = None) -> Dict[str, Any]:
        json_prompt = f"{prompt}\n\nRESPOND ONLY WITH VALID JSON. NO EXPLANATIONS."
        text = self.generate(json_prompt, system)
        return _parse_json_response(text)


def _parse_json_response(text: str) -> Dict[str, Any]:
    text = text.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        try:
            repaired = repair_json(text)
            return json.loads(repaired)
        except Exception as e:
            raise ValueError(f"Failed to parse JSON from LLM output: {e}\nOutput: {text[:200]}")


def load_config(config_path: str = "config/llm_config.json") -> Dict[str, Any]:
    """
    Load LLM configuration from file.
    
    Args:
        config_path: Path to config file
        
    Returns:
        Config dict
    """
    with open(config_path, 'r') as f:
        return json.load(f)


def _create_client(role_cfg: dict) -> BaseLLMClient:
    """Return an LLM client based on configuration.

    The configuration dictionary should contain keys:
    - backend: "local" or "online" or "groq"
    - model, temperature, timeout, etc.
    """
    backend = role_cfg.get("backend", "local")
    secrets = _load_secrets()
    
    if backend == "groq":
        token = os.getenv("GROQ_API_KEY") or secrets.get("GROQ_API_KEY")
        return GroqClient(
            model=role_cfg["model"],
            api_token=token,
            temperature=role_cfg["temperature"],
            timeout=role_cfg["timeout"],
        )
    elif backend == "online":
        token = os.getenv("HF_API_KEY") or os.getenv("OPENAI_API_KEY") or secrets.get("HF_API_KEY")
        return OnlineLLMClient(
            model=role_cfg["model"],
            api_token=token,
            temperature=role_cfg["temperature"],
            timeout=role_cfg["timeout"],
        )
    # default to local Ollama client
    return OllamaClient(
        model=role_cfg["model"],
        temperature=role_cfg["temperature"],
        timeout=role_cfg["timeout"],
    )


def _get_fallback_model(model_name: str) -> str:
    """Map online model names to local Ollama equivalents."""
    mapping = {
        "Qwen/Qwen2.5-Coder-7B-Instruct": "qwen2.5-coder:7b-instruct",
        "Qwen2.5-Coder-7B-Instruct": "qwen2.5-coder:7b-instruct",
        "qwen-2.5-coder-32b": "qwen2.5-coder:7b-instruct",
        "qwen/qwen3-32b": "qwen2.5-coder:7b-instruct",
        "meta-llama/llama-4-scout-17b-16e-instruct": "qwen2.5-coder:7b-instruct",
        "deepseek-ai/deepseek-coder-6.7b-instruct": "deepseek-coder:6.7b-instruct",
        "deepseek-coder-6.7b-instruct": "deepseek-coder:6.7b-instruct",
        "llama-3.3-70b-versatile": "deepseek-coder:6.7b-instruct",
        "openai/gpt-oss-120b": "deepseek-coder:6.7b-instruct"
    }
    return mapping.get(model_name, model_name)


def create_planner_client(config_path: str = "config/llm_config.json") -> BaseLLMClient:
    """Instantiate a planner LLM client with optional online-to-local fallback.

    After creating the client we perform a lightweight request when using an
    online backend so that transient network/API failures can be detected early
    and trigger the configured fallback. This mirrors the behaviour of the
    tests which simulate a broken network by patching ``requests.post``.
    """
    config = load_config(config_path)
    planner_config = config["planner"]
    try:
        client = _create_client(planner_config)
        # If this is an online client, attempt a tiny dummy call to verify
        # connectivity. Use a short timeout (5s) for this check to avoid hangs.
        if isinstance(client, OnlineLLMClient):
            try:
                # Override timeout temporarily for the connectivity check
                orig_timeout = client.timeout
                client.timeout = 5
                try:
                    client.generate("ping")
                finally:
                    client.timeout = orig_timeout
            except Exception:
                raise
        return client
    except Exception:
        if os.getenv("LLM_FALLBACK_LOCAL", "true").lower() == "true":
            # fallback to a minimal local model to ensure functionality
            fallback_model = _get_fallback_model(planner_config.get("model", ""))
            return OllamaClient(model=fallback_model)
        raise


def create_critic_client(config_path: str = "config/llm_config.json") -> BaseLLMClient:
    """Instantiate a critic LLM client with a connectivity check similar to
    :func:`create_planner_client`.
    """
    config = load_config(config_path)
    critic_config = config["critic"]
    try:
        client = _create_client(critic_config)
        if isinstance(client, OnlineLLMClient):
            try:
                # Override timeout temporarily for the connectivity check
                orig_timeout = client.timeout
                client.timeout = 5
                try:
                    client.generate("ping")
                finally:
                    client.timeout = orig_timeout
            except Exception:
                raise
        return client
    except Exception:
        if os.getenv("LLM_FALLBACK_LOCAL", "true").lower() == "true":
            fallback_model = _get_fallback_model(critic_config.get("model", ""))
            return OllamaClient(model=fallback_model)
        raise
