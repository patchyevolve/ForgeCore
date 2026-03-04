"""
LLM Client - Interface to Ollama for local LLM inference
"""

import json
import ollama
import threading
from typing import Dict, Any, Optional
from json_repair import repair_json


class TimeoutError(Exception):
    """Raised when LLM call times out"""
    pass


class LLMClient:
    """
    Client for interacting with local LLM models via Ollama.
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
    
    def generate(self, prompt: str, system: str = None) -> str:
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
        result = {'response': None, 'error': None}
        
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
                result['error'] = e
        
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
    
    def generate_json(self, prompt: str, system: str = None) -> Dict[str, Any]:
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


def create_planner_client(config_path: str = "config/llm_config.json") -> LLMClient:
    """
    Create LLM client for planner agent.
    
    Args:
        config_path: Path to config file
        
    Returns:
        Configured LLMClient
    """
    config = load_config(config_path)
    planner_config = config['planner']
    
    return LLMClient(
        model=planner_config['model'],
        temperature=planner_config['temperature'],
        timeout=planner_config['timeout']
    )


def create_critic_client(config_path: str = "config/llm_config.json") -> LLMClient:
    """
    Create LLM client for critic agent.
    
    Args:
        config_path: Path to config file
        
    Returns:
        Configured LLMClient
    """
    config = load_config(config_path)
    critic_config = config['critic']
    
    return LLMClient(
        model=critic_config['model'],
        temperature=critic_config['temperature'],
        timeout=critic_config['timeout']
    )
