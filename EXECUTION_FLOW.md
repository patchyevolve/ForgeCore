# ForgeCore Execution Flow

## Complete Transaction Pipeline

```
┌─────────────────────────────────────────────────────────────────┐
│                    USER SUBMITS TASK/INTENT                      │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│                    USER SUBMITS TASK/INTENT                      │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│ 1. INITIALIZATION & SNAPSHOT                                     │
│    - Index project (SQLite database via indexer.py)              │
│    - Create filesystem snapshot (snapshot.py)                    │
│    - Initialize TransactionContext (transaction_context.py)       │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│ 2. PLANNING & PRE-REVIEW                                         │
│    - Planner generates PatchIntent (planner.py)                  │
│    - Critic reviews intent (critic.py)                           │
│    - User reviews & approves (interactive_session.py)            │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│ 3. INTENT & MUTATION VALIDATION                                  │
│    - ProposalValidator runs syntactic checks                      │
│    - Check rewrite ratios, line limits, path traversal           │
│    - Verify tier permissions (tier_policy.json)                  │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│ 4. STAGED MUTATION                                               │
│    - Apply patches to virtual workspace                          │
│    - Verify file integrity against baseline hashes               │
│    - Generate diff for user confirmation                         │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│ 5. ATOMIC COMMIT (TRANSACTIONAL)                                 │
│    - Perform atomic file writes to disk                          │
│    - Synchronize SQLite index with local changes                 │
│    - Mark transaction as partially-committed                     │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│ 6. MULTI-STAGE VERIFICATION                                      │
│    - SemanticValidator: Type, flow, and resource safety          │
│    - SmartValidator: Compiles/builds (build.py)                  │
│    - Structural: Call graph & symbol resolution                  │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│ 7. FINAL REVIEW & CLEANUP                                        │
│    - Final critic review of the integrated result                │
│    - Commit SQLite state & purge snapshots                       │
│    - Return results to user                                      │
└─────────────────────────────────────────────────────────────────┘
```

---

## Failure Paths

### Build Failure (Iteration Mode)
```
Build fails → Error classification → Stagnation check → REFINEMENT
                                                              ↓
                                                    Back to PLANNING
                                                    (max 5 iterations)
```

### Validation Failure (Any Stage)
```
Validation fails → ABORT → Rollback snapshot → Rollback DB → IDLE
```

### Stagnation Detection
```
Identical intent/content OR identical errors → ABORT
```

---

## Validation Layers (22 Total)

### Pre-Mutation (Syntactic)
1. Operation support check
2. File indexing check
3. Symbol duplication check
4. Critic intent review (LLM)

### Mutation Stage (Structural)
5. Rewrite ratio (per-file)
6. Rewrite ratio (cross-file)
7. Line limit per file
8. File count limit
9. Path traversal check
10. File integrity guard
11. Tier enforcement
12. Build system warnings

### Post-Mutation (Semantic - NEW!)
13. Type safety
14. Data flow analysis
15. Resource tracking
16. Invariant checking
17. Effect tracking

### Build Stage (Compilation)
18. Build/syntax validation

### Post-Build (Structural)
19. Module integrity
20. Symbol validation
21. Call graph integrity
22. Final critic review (LLM)

---

## State Machine Transitions

```
IDLE → PLANNING → CRITIC_REVIEW → PATCH_READY → APPLYING → 
COMPILING → FINAL_CRITIC → MODULE_INTEGRITY_CHECK → COMMIT → IDLE

                    ↓ (on failure)
                  ABORT → IDLE

                    ↓ (on build failure in iteration mode)
                REFINEMENT → PLANNING
```

---

## Transactional Guarantees (ACID)

### Atomicity
- All file writes succeed or all rollback
- SQLite transactions wrap file operations
- Snapshot provides filesystem-level rollback

### Consistency
- File integrity guard prevents external modifications
- Baseline tracking ensures consistent state
- Cross-file validation maintains relationships

### Isolation
- TransactionContext isolates execution state
- Candidate files pattern prevents premature commits
- Savepoints isolate database operations

### Durability
- Snapshot persists until commit
- SQLite WAL mode for crash recovery
- Baseline hashes verify file state

---

## Key Design Principles

1. **Fail Fast**: Validate early, abort on first error
2. **Deterministic**: Same input → same output
3. **Transactional**: All-or-nothing semantics
4. **Adversarial**: Planner generates, Critic validates
5. **Semantic-Aware**: Deep code analysis, not just syntax
6. **Language-Agnostic**: Works with any programming language

---

## Configuration

All validation layers can be toggled in `policy/invariants.json`:

```json
{
  "validation": {
    "file_integrity_guard_enabled": true,
    "tier_enforcement_enabled": true,
    "module_integrity_check_enabled": true,
    "symbol_validation_enabled": true,
    "call_graph_validation_enabled": true,
    "path_traversal_check_enabled": true,
    "semantic_validation_enabled": true  // NEW!
  }
}
```

---

## Semantic Validation Details

### What It Catches

**Type Safety**
- `int x = "string"` → Type mismatch error
- `bool x = 5` → Implicit conversion warning

**Data Flow**
- `int x; return x;` → Uninitialized variable error
- Use-before-def detection

**Resource Safety**
- `int* p = new int; return;` → Memory leak warning
- `int* p = nullptr; *p = 5;` → Null dereference error
- `delete p;` (where p not allocated) → Invalid delete error

**Invariants**
- `x / 0` → Division by zero error
- `x / y` (no check) → Potential division by zero warning
- `arr[i]` (no bounds check) → Array bounds warning

**Effects**
- `GLOBAL_VAR = x;` in function → Side effect info

### When It Runs

Semantic validation runs **AFTER file writes** but **BEFORE build**, so:
- Files are on disk (can be analyzed)
- Build hasn't run yet (fast feedback)
- Errors abort before expensive compilation

---

## Performance Characteristics

- **Fast Path** (no errors): ~100-500ms per iteration
- **Slow Path** (with LLM): ~2-5s per iteration (Qwen + DeepSeek)
- **Semantic Validation**: ~10-50ms per file
- **Max Iterations**: 5 (configurable)
- **Timeout**: 120s per test (configurable)

---

## Error Recovery

### Automatic Recovery
- Snapshot rollback on any failure
- Database rollback on transaction failure
- State machine force reset as last resort

### Manual Recovery
- Cleanup scripts for test artifacts
- Snapshot cleanup utility
- Database reindexing

---

## Testing Strategy

- **Unit Tests**: Individual validators
- **Integration Tests**: Full transaction pipeline
- **Property Tests**: Invariant checking
- **Mock LLM**: `FORGECORE_USE_LLM=false` for fast tests
- **Cleanup**: Automatic between test suites
