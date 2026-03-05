# Policy Module Handbook

The `policy/` directory defines the safety constraints and access rules that govern ForgeCore's behavior.

## Key Policies

- **[invariants.json](file:///d:/codeWorks/ForgeCore/policy/invariants.json)**: Defines global limits such as:
    - Max rewrite ratio per file.
    - Max file count per task.
    - Max line count per file.
    - Path traversal protection settings.
- **[tier_policy.json](file:///d:/codeWorks/ForgeCore/policy/tier_policy.json)**: Implements a tiered access system:
    - **Tier 0**: User project code (Full access).
    - **Tier 1**: Non-critical system files (Limited modification).
    - **Tier 2**: Core ForgeCore logic (Read-only for AI agents).

## Enforcement

Policies are checked by the `controller.py` and `proposal_validator.py` at different stages of the execution pipeline. Any violation results in an immediate `ABORT` and rollback.
