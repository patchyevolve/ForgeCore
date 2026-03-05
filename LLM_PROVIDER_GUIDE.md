# LLM Provider Configuration Guide

ForgeCore supports multiple LLM providers, allowing you to switch between local execution (Ollama) and high-performance remote APIs (Groq, HuggingFace, OpenAI).

## 1. Provider Backends

ForgeCore uses the `backend` field in `config/llm_config.json` to determine how to communicate with the model.

### Available Backends:
- **`local`**: Uses [Ollama](https://ollama.com/) for on-device inference.
- **`groq`**: Uses the [Groq API](https://groq.com/) for ultra-fast inference.
- **`online`**: Use for [HuggingFace](https://huggingface.co/) or other OpenAI-compatible inference endpoints.

---

## 2. Configuration (`config/llm_config.json`)

The configuration is split into two roles: `planner` and `critic`. You can use different providers for each.

### Example: Multi-Provider Setup
```json
{
    "planner": {
        "backend": "groq",
        "model": "qwen-2.5-coder-32b",
        "temperature": 0.1,
        "timeout": 60
    },
    "critic": {
        "backend": "local",
        "model": "deepseek-coder:6.7b-instruct",
        "temperature": 0.1,
        "timeout": 60
    }
}
```

---

## 3. API Key Management

For remote providers, you must provide an API key. ForgeCore checks two locations:
1.  **Environment Variables** (Recommended)
2.  **`config/secrets.json`**

### Groq Setup
- **Backend**: `"groq"`
- **API Key**: Set `GROQ_API_KEY` in your environment or in `config/secrets.json`.
- **Models**: [Groq Supported Models](https://console.groq.com/docs/models)

### Online (HuggingFace/OpenAI) Setup
- **Backend**: `"online"`
- **API Key**: Set `HF_API_KEY` or `OPENAI_API_KEY` in your environment.
- **Models**: Specify the model identifier (e.g., `meta-llama/Llama-3.3-70B-Instruct`).

---

## 4. Local LLM Setup (Ollama)

- **Backend**: `"local"` (or omit, as it is the default).
- **Prerequisites**: [Install Ollama](https://ollama.com/) and pull your desired models:
  ```bash
  ollama pull qwen2.5-coder:7b-instruct
  ollama pull deepseek-coder:6.7b-instruct
  ```

---

## 5. Summary of Configuration Sets

| Feature | Local (Ollama) | Groq | Online (HF/Other) |
| :--- | :--- | :--- | :--- |
| **Backend** | `"local"` | `"groq"` | `"online"` |
| **Model Format** | `name:tag` | `provider-model-size` | `namespace/model` |
| **Auth** | None | `GROQ_API_KEY` | `HF_API_KEY` |
| **Speed** | Hardware dependent | Ultra Fast | Moderate |
| **Privacy** | High (100% Local) | Moderate (Cloud) | Moderate (Cloud) |

---

## 6. Model Fallback Mechanism

If an online provider fails (network issue or quota exceeded), ForgeCore will automatically attempt to use a local fallback model if:
1.  `LLM_FALLBACK_LOCAL=true` is set in your environment.
2.  You have the local equivalent installed (e.g., `qwen2.5-coder:7b-instruct`).

This logic is implemented in `core/llm_client.py`'s `_get_fallback_model` function.
