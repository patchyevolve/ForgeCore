# Architectural Drift Audit - March 3, 2026

## Critical Findings

### A. Architectural Depth Drift ❌

**Current State:** "LLM patch wrapper with safety add-ons"
**Target State:** "Deterministic patch transaction engine"

#### Issues Found:

1. **Validation is Syntactic, Not Semantic**
   - Symbol validator checks existence but not semantic correctness
   - Call graph analyzer checks structure but not behavioral invariants
   - No proof-carrying code or formal verification

2. **Call Graph Enforcement is Shallow**
   - Detects cycles and unreachable code
   - Does NOT enforce: data flow invariants, temporal properties, resource safety
   - Missing: effect system, ownership tracking, capability enforcement

3. **Rollback is Filesystem-Only**
   - Snapshots capture file state
   - Does NOT rollback: SQLite index state, dependency graph state, symbol table state
   - **CRITICAL:** Database mutations are not transactional with file mutations

4. **SQLite Not Isolated from Mutation Boundaries**
   - `reindex_files()` called during transaction
   - No savepoints or nested transactions
   - Index state can diverge from file state on rollback

**Evidence:**
```python
# controller.py line ~1050
self.indexer.reindex_files(modified_files)  # NOT in transaction!
```

---

### B. State Machine Strictness Drift ⚠️

**Original Intent:** Invalid transition = hard-fail, no silent fallbacks

#### Issues Found:

1. **Direct State Assignment Bypasses Validation**
   ```python
   # controller.py lines 1289, 1334
   self.state_machine.current_state = State.IDLE  # BYPASSES transition_to()!
   ```
   This violates the state machine contract.

2. **Logic Embedded in Planner/Critic Instead of Controller**
   - Planner has retry logic (3 attempts)
   - Critic has fallback to simulated approval
   - Controller should orchestrate, not agents

3. **No State Logging for Implicit Retries**
   - Planner retries 3 times without state machine awareness
   - Controller doesn't know planner is retrying

**Evidence:**
```python
# planner.py - retry logic outside state machine
for attempt in range(max_rework_attempts):
    # State machine doesn't know about this!
```

---

### C. Agent Role Purity Drift ❌

**Original Intent:**
- Planner = generative synthesis ONLY
- Critic = structural adversarial validator
- Controller = authority

#### Issues Found:

1. **Critic is Just Another Reasoning Model**
   ```python
   # critic.py - LLM prompt
   "Review the proposed mutation for safety and correctness."
   ```
   This is reasoning, not structural enforcement!
   
   **Should be:**
   - AST-level validation
   - Type system enforcement
   - Invariant checking
   - Proof obligations

2. **Planner Self-Corrects Without Critic Gate**
   ```python
   # interactive_session.py
   for attempt in range(max_rework_attempts):
       intent = self.planner.generate_intent(...)
       # Planner retries based on user feedback, not critic
   ```

3. **Critic Approval is Advisory, Not Mandatory**
   ```python
   # controller.py line ~900
   if not approved:
       # For now, continue anyway (critic is advisory)
   ```
   **This defeats the adversarial architecture!**

---

## Severity Assessment

### Critical (Must Fix)
1. ❌ **Database not transactional with file mutations**
   - Risk: Index corruption on rollback
   - Impact: System integrity compromised

2. ❌ **State machine bypass in exception handlers**
   - Risk: Invalid state transitions
   - Impact: State machine guarantees violated

3. ❌ **Critic approval is advisory**
   - Risk: Unsafe mutations proceed
   - Impact: Safety layer is decorative

### High (Should Fix)
4. ⚠️ **Validation is syntactic, not semantic**
   - Risk: Logically incorrect but syntactically valid code
   - Impact: Reduced correctness guarantees

5. ⚠️ **Rollback doesn't restore dependency state**
   - Risk: Inconsistent system state after rollback
   - Impact: Subsequent operations may fail

### Medium (Consider Fixing)
6. ⚠️ **Planner retry logic outside state machine**
   - Risk: Hidden state transitions
   - Impact: Observability reduced

---

## Recommendations

### Immediate Actions

1. **Make Database Transactional**
   ```python
   # Use SQLite savepoints
   cursor.execute("SAVEPOINT mutation_start")
   try:
       # Apply mutations
       # Reindex
       cursor.execute("RELEASE SAVEPOINT mutation_start")
   except:
       cursor.execute("ROLLBACK TO SAVEPOINT mutation_start")
   ```

2. **Fix State Machine Bypass**
   ```python
   # Replace direct assignment
   # self.state_machine.current_state = State.IDLE
   
   # With proper transition
   self.state_machine.transition_to(State.ABORT)
   self.state_machine.transition_to(State.IDLE)
   ```

3. **Make Critic Mandatory**
   ```python
   if not approved:
       self.logger.log_event(
           state=self.state_machine.get_state().name,
           event="CRITIC_REJECTED",
           details={"reason": feedback}
       )
       return self._handle_abort(f"Critic rejected: {feedback}")
   ```

### Architectural Improvements

4. **Add Structural Critic Layer**
   ```python
   class StructuralCritic:
       def validate_ast(self, intent, file_content):
           # Parse AST
           # Check structural invariants
           # Verify type safety
           # Return proof or rejection
   ```

5. **Implement Semantic Validation**
   ```python
   class SemanticValidator:
       def check_invariants(self, intent, context):
           # Data flow analysis
           # Effect system checking
           # Resource safety verification
   ```

6. **Add Transaction Context to Database**
   ```python
   class TransactionalIndexer:
       def begin_transaction(self):
           self.conn.execute("SAVEPOINT tx")
       
       def commit_transaction(self):
           self.conn.execute("RELEASE SAVEPOINT tx")
       
       def rollback_transaction(self):
           self.conn.execute("ROLLBACK TO SAVEPOINT tx")
   ```

---

## Current Architecture vs Target Architecture

### Current (Drifted)
```
User → Interactive Session → Planner (LLM + retry logic)
                           ↓
                    Critic (LLM reasoning, advisory)
                           ↓
                    Controller (orchestrator)
                           ↓
                    Validators (syntactic checks)
                           ↓
                    Filesystem (rollback)
                    SQLite (NOT transactional)
```

### Target (Original Intent)
```
User → Controller (authority)
         ↓
      State Machine (strict transitions)
         ↓
      Planner (synthesis ONLY)
         ↓
      Structural Critic (AST + invariants, MANDATORY)
         ↓
      Semantic Validator (proof obligations)
         ↓
      Transactional System (files + DB + dependencies)
         ↓
      Atomic Commit/Rollback
```

---

## Test Coverage Gaps

Current: 46/46 tests pass (100%)
**But tests don't cover:**

1. Database rollback consistency
2. State machine bypass scenarios
3. Critic rejection enforcement
4. Semantic correctness
5. Dependency state restoration

**Need tests for:**
- Rollback with concurrent index updates
- Invalid state transitions in exception paths
- Critic rejection should abort
- Semantic invariant violations
- Multi-file dependency rollback

---

## Conclusion

**Status:** System has drifted from "Deterministic patch transaction engine" to "LLM patch wrapper with safety add-ons"

**Root Cause:** Pragmatic shortcuts taken during implementation

**Impact:** 
- Reduced correctness guarantees
- Weakened safety layers
- Violated architectural principles

**Path Forward:**
1. Fix critical issues (database transactions, state machine, critic enforcement)
2. Add structural validation layer
3. Implement semantic checking
4. Restore adversarial architecture purity

**Estimated Effort:** 2-3 days to restore architectural integrity
