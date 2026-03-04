# ForgeCore Execution Flow

## Complete Transaction Pipeline

```
┌─────────────────────────────────────────────────────────────────┐
│                    USER SUBMITS TASK/INTENT                      │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│ 1. INITIALIZATION                                                │
│    - Index project (SQLite database)                             │
│    - Create snapshot (filesystem backup)                         │
│    - Create TransactionContext (isolated state)                  │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│ 2. PLANNING (State: PLANNING)                                    │
│    - Planner generates PatchIntent (LLM: Qwen 2.5 Coder 7B)     │
│    - Intent contains: operation, target files, payload           │
│    - Dynamic baseline capture for new files                      │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│ 3. INTENT VALIDATION                                             │
│    ✓ Operation supported?                                        │
│    ✓ Target files indexed?                                       │
│    ✓ No duplicate symbols?                                       │
│    ❌ ABORT if invalid                                           │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│ 4. CRITIC REVIEW (State: CRITIC_REVIEW)                          │
│    - Critic reviews intent (LLM: DeepSeek Coder 6.7B)           │
│    - Checks: correctness, safety, best practices                 │
│    ❌ ABORT if rejected (MANDATORY gate)                         │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│ 5. MUTATION GENERATION (State: APPLYING)                         │
│    - Generate new file content from intent                       │
│    - Stage writes (not yet committed to disk)                    │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│ 6. MUTATION VALIDATION                                           │
│    ✓ Rewrite ratio check (per-file & cross-file)                │
│    ✓ Line limit check                                            │
│    ✓ File count limit                                            │
│    ✓ Path traversal check                                        │
│    ✓ File integrity guard (unchanged since baseline)             │
│    ✓ Tier enforcement (no tier2 modifications)                   │
│    ✓ Build system warnings (CMakeLists, .sln, etc.)             │
│    ❌ ABORT if validation fails                                  │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│ 7. ATOMIC FILE WRITES                                            │
│    - Begin SQLite transaction (savepoint)                        │
│    - Write all files atomically                                  │
│    - Commit SQLite transaction                                   │
│    - Update baselines for file integrity guard                   │
│    ❌ ROLLBACK (files + DB) if any write fails                   │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│ 8. SEMANTIC VALIDATION (NEW!)                                    │
│    ✓ Type safety (type mismatches, implicit conversions)         │
│    ✓ Data flow (uninitialized variables, use-before-def)        │
│    ✓ Resource safety (memory leaks, null pointers)              │
│    ✓ Invariants (division by zero, array bounds)                │
│    ✓ Effects (side effects in pure functions)                    │
│    ❌ ABORT if semantic errors found                             │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│ 9. BUILD VALIDATION (State: COMPILING)                           │
│    - SmartValidator runs build/syntax check                      │
│    - Language-agnostic (C++, Python, JS, etc.)                   │
│    ❌ If build fails → classify errors → REFINEMENT              │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│ 10. FINAL CRITIC REVIEW (State: FINAL_CRITIC)                   │
│     - Critic reviews actual result                               │
│     - Compares original vs modified code                         │
│     - Logs concerns (advisory, not blocking)                     │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│ 11. POST-BUILD VALIDATION (State: MODULE_INTEGRITY_CHECK)       │
│     - Begin SQLite transaction for reindexing                    │
│     - Reindex modified files                                     │
│     ✓ Module integrity (file-level dependencies)                │
│     ✓ Symbol validation (cross-file symbol resolution)          │
│     ✓ Call graph integrity (cycles, recursion)                  │
│     - Commit SQLite transaction                                  │
│     ❌ ROLLBACK (index only) if validation fails                │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│ 12. COMMIT (State: COMMIT → IDLE)                               │
│     - Cleanup snapshot                                           │
│     - Return success message                                     │
│     ✅ TRANSACTION COMPLETE                                      │
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
