# Config Module Handbook

The `config/` directory stores configuration files for ForgeCore's internal components and LLM connections.

## Files

- **[llm_config.json](file:///d:/codeWorks/ForgeCore/config/llm_config.json)**: Defines the models and parameters (temperature, max tokens) for the Planner and Critic agents.
- **[secrets.json](file:///d:/codeWorks/ForgeCore/config/secrets.json)**: (Optional/Internal) Stores API keys or sensitive credentials if using cloud-based LLM providers.

## Configuration Priority

1. Command-line arguments (`--path`, etc.)
2. `forgecore_config.json` (Project root)
3. Internal defaults

## LLM Customization

To learn how to use local models or change your LLM providers, see the **[LLM Provider Guide](file:///d:/codeWorks/ForgeCore/LLM_PROVIDER_GUIDE.md)**.
