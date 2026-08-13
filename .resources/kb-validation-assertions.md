# Knowledge Base — Validation Assertion Library

Reusable assertions for the `@validator` gates. Every assertion here is **technology-agnostic**: it states an invariant and the logical shape of its check. `@modeler` binds each one to a concrete dialect in the blueprint's Validation Specifications; `@validator` executes the bound form and compares expected against actual.

Used by: `@modeler` (binding), `@validator` (execution), `@architect` (checking a design is verifiable at all).

Related: `kb-scd-fact-patterns.md`, `kb-layered-architecture.md`, `kb-metadata-pipeline-framework.md`

---

## How to use this library

| Field | Meaning |
|---|---|
| **ID** | Stable assertion identifier. Referenced from validation reports and the ledger |
| **Invariant** | The property that must hold, in plain language |
| **Check shape** | The logical form of the test, written generically |
| **Expected** | The passing condition |
| **Fails when** | The defect this assertion actually catches |
| **Severity** | `Must` blocks; `Should` warns. A blueprint may raise a Should to a Must, never lower a Must |

**Two families of assertion:**

- **Structural (VA-Snn)** — depend only on the modelling style, not the business. Apply them automatically wherever the pattern is used. Nobody has to think of them, which is precisely why they catch things nobody thought of.
- **Business (VA-Bnn)** — derived one-to-one from an `AC-nnn`. Carry the tolerance the business actually agreed to.

**Binding rules for `@modeler`:**

1. Every structural assertion applicable to a table's pattern must be bound. Skipping one is a blueprint defect.
2. Every `AC-nnn` must bind to at least one assertion. An unbound acceptance criterion is an unkept promise.
3. Bind thresholds from the requirements verbatim. Never round a tolerance "for practicality".
4. An assertion must be able to **fail**. If no realistic data state makes it fail, it is decoration — replace it.

---

## 1. Historisation Assertions (SCD)

Applies to any dimension tracking history. These are the invariants that a subtly wrong merge silently violates while every row count still looks plausible.

### VA-S01 — Exactly one current row per business key
- **Invariant:** A business key has exactly one row flagged as current.
- **Check shape:** Group the dimension by business key; count rows where the current flag is set; return any group whose count is not 1.
- **Expected:** Zero rows returned.
- **Fails when:** A merge inserts a new version without closing the previous one (duplicate current rows), or closes a version without inserting its successor (orphaned key with no current row). Both are invisible to row-count checks.
- **Severity:** Must

### VA-S02 — No overlapping validity ranges
- **Invariant:** For one business key, no two versions are simultaneously valid.
- **Check shape:** Self-join the dimension on business key where the row identifiers differ and the validity intervals intersect; return matches.
- **Expected:** Zero rows returned.
- **Fails when:** Late-arriving data is merged out of order, or a reload re-processes a batch without closing prior versions. Produces double-counted joins in every downstream fact query.
- **Severity:** Must

### VA-S03 — Contiguous version chain
- **Invariant:** Each version's validity start equals the previous version's validity end — no gaps.
- **Check shape:** For each business key ordered by validity start, compare each row's start against the prior row's end; return mismatches.
- **Expected:** Zero rows returned.
- **Fails when:** A batch is skipped or a load is partially rolled back. Point-in-time queries silently return no dimension row for the gap, dropping facts from results.
- **Severity:** Must

### VA-S04 — Open-ended current version
- **Invariant:** The current version's validity end is the designated open-ended marker.
- **Check shape:** Return current-flagged rows whose validity end is not the open-ended value.
- **Expected:** Zero rows returned.
- **Fails when:** A merge writes a concrete end date to the current row. Point-in-time queries for "now" return nothing.
- **Severity:** Must

### VA-S05 — Version start precedes version end
- **Invariant:** Validity intervals are not inverted.
- **Check shape:** Return rows where validity start is greater than validity end.
- **Expected:** Zero rows returned.
- **Fails when:** Timezone handling differs between source and target, or a corrective load back-dates a version.
- **Severity:** Must

### VA-S06 — Change detection is honest
- **Invariant:** A new version exists only when a tracked attribute actually changed.
- **Check shape:** For consecutive versions of a business key, compare the tracked attributes; return pairs that are identical across all of them.
- **Expected:** Zero rows returned.
- **Fails when:** Change detection includes a volatile column (a load timestamp, a rowhash over the wrong column set). The dimension grows every run and history becomes noise.
- **Severity:** Should — it does not corrupt results, but it inflates storage and destroys the usefulness of history

---

## 2. Key Integrity Assertions

### VA-S10 — Surrogate key uniqueness
- **Invariant:** The surrogate key is unique across the table.
- **Check shape:** Group by surrogate key; return groups with a count above 1.
- **Expected:** Zero rows returned.
- **Severity:** Must

### VA-S11 — No null keys
- **Invariant:** No key column is null.
- **Check shape:** Return rows where any declared key column is null.
- **Expected:** Zero rows returned.
- **Fails when:** A join in the transformation misses, or a source delivers a blank identifier that is not caught at the boundary.
- **Severity:** Must

### VA-S12 — Natural key uniqueness at declared grain
- **Invariant:** The declared natural key is unique at the table's stated grain.
- **Check shape:** Group by the natural key columns (plus version, for historised tables); return groups with a count above 1.
- **Expected:** Zero rows returned.
- **Fails when:** The real grain is finer than documented, or a re-run double-loads a batch. **This assertion is how you discover that the documented grain was wrong** — a common and expensive misunderstanding.
- **Severity:** Must

### VA-S13 — Source key identity survives reuse
- **Invariant:** A source system reusing a natural key does not merge two distinct business objects.
- **Check shape:** For business keys with a discontinuity in their lifecycle, confirm distinct surrogate identities exist rather than one continuous history.
- **Expected:** Distinct identities preserved.
- **Fails when:** A source recycles identifiers (retired product codes, reissued account numbers) and the platform treats the reuse as an update. Misattributes history across unrelated entities.
- **Severity:** Must, wherever key reuse is a known risk

---

## 3. Referential Integrity Assertions

### VA-S20 — No orphaned fact references
- **Invariant:** Every dimension reference on a fact resolves to a dimension row.
- **Check shape:** Anti-join the fact to each referenced dimension on the surrogate key; return non-matching fact rows.
- **Expected:** Zero rows returned.
- **Fails when:** Load ordering runs facts before dimensions, or a late-arriving dimension member is not handled.
- **Severity:** Must

### VA-S21 — Unknown-member handling is deliberate
- **Invariant:** Unresolved references point at the designated unknown member rather than being dropped or nulled.
- **Check shape:** Count fact rows referencing the unknown member; compare against the tolerance the blueprint declares.
- **Expected:** Within declared tolerance.
- **Fails when:** Unmatched rows are silently discarded — **revenue disappears and no error is raised**. The most dangerous class of failure in the library, because every other check still passes.
- **Severity:** Must

### VA-S22 — Point-in-time resolution
- **Invariant:** A fact resolves to the dimension version that was valid at the fact's own event time.
- **Check shape:** Join fact to dimension on business key where the event timestamp falls inside the version's validity interval; compare the resulting surrogate against the one stored on the fact.
- **Expected:** Full match.
- **Fails when:** The load joins to the *current* version instead of the historically valid one. Prior-period reports change retroactively — usually noticed by a finance controller, months later, in a board meeting.
- **Severity:** Must, wherever history is required

---

## 4. Layer Reconciliation Assertions

These assert that data survives the journey between layers. Applies to any layered architecture (see `kb-layered-architecture.md`).

### VA-S30 — Row count conservation
- **Invariant:** Row counts between layers match, subject to the declared transformation.
- **Check shape:** Compare source-layer count against target-layer count for the same batch, adjusted for declared filtering, deduplication, or aggregation.
- **Expected:** Match within declared tolerance, which is **zero** unless the blueprint documents an expected reduction.
- **Fails when:** A join silently drops rows, a filter is more aggressive than specified, or a partition is missed.
- **Severity:** Must

### VA-S31 — Measure conservation
- **Invariant:** Additive measures sum identically across layers.
- **Check shape:** Compare the sum of each additive measure between layers for the same batch.
- **Expected:** Equal within declared tolerance.
- **Fails when:** A type conversion truncates, a currency conversion is applied twice, or duplicate dimension rows fan out a join. **Row counts can pass while sums fail** — an inflating join breaks this and only this.
- **Severity:** Must

### VA-S32 — Aggregate consistency
- **Invariant:** A pre-aggregated table equals the aggregation of its detail table.
- **Check shape:** Recompute the aggregate from detail and compare to the stored aggregate at the declared grain.
- **Expected:** Equal within declared tolerance.
- **Fails when:** The aggregate refresh runs before the detail load, or an incremental aggregate update misses a restatement.
- **Severity:** Must

### VA-S33 — No unintended duplication across reloads
- **Invariant:** Re-running a load produces the same result, not double the rows.
- **Check shape:** Compare row counts and measure sums for a batch before and after a repeat run of the same batch.
- **Expected:** Identical.
- **Fails when:** The load is append-only where it should be idempotent. **Only detectable by actually re-running** — which is why the loop must exercise it rather than reason about it.
- **Severity:** Must

---

## 5. Freshness & Completeness Assertions

### VA-S40 — Data freshness within SLA
- **Invariant:** The most recent load is within the agreed freshness window.
- **Check shape:** Compare the maximum load timestamp against the current time and the declared SLA.
- **Expected:** Within SLA.
- **Severity:** Must, wherever a freshness `AC` exists

### VA-S41 — All expected sources reported
- **Invariant:** Every source expected to deliver for the period has delivered.
- **Check shape:** Anti-join the registry of expected sources against sources present in the period's load log.
- **Expected:** Zero missing, or exactly the set the blueprint declares as optional.
- **Fails when:** A feed silently stops. Totals simply get smaller, which looks like a business trend rather than a defect — one of the hardest failures to notice without this check.
- **Severity:** Must

### VA-S42 — No unexplained gaps in the time series
- **Invariant:** Every expected period in the covered range has data.
- **Check shape:** Compare distinct periods present against the expected calendar for the range; return missing periods not on the declared exception list.
- **Expected:** Zero unexplained gaps.
- **Severity:** Should

### VA-S43 — Load log completeness
- **Invariant:** Every declared process has a load-log entry with a terminal status for the period.
- **Check shape:** Anti-join declared processes against the load log; return processes with no entry or a non-terminal status.
- **Expected:** Zero rows returned.
- **Fails when:** A process fails so early it never logs. **The absence of a failure record is mistaken for success** — the loop must check for the presence of success, never the absence of failure.
- **Severity:** Must

---

## 6. Access Control Assertions

Always assert the **negative** case. A test that only proves the permitted access proves nothing about what is denied.

### VA-S50 — Authorised access returns data
- **Invariant:** An identity that should have access to data receives it.
- **Check shape:** Query as an identity that should have access; confirm a non-empty result.
- **Expected:** Rows returned.
- **Severity:** Must

### VA-S51 — Unauthorised access returns nothing
- **Invariant:** An identity outside a data scope receives nothing from that scope.
- **Check shape:** Query as an identity that should be restricted; confirm zero rows for data outside its scope.
- **Expected:** Exactly zero rows.
- **Fails when:** A filter is defined but not enforced, or enforcement sits only in the reporting tool while the underlying endpoint remains open. **Passing VA-S50 while failing VA-S51 is the standard shape of a data breach.**
- **Severity:** Must

### VA-S52 — Restricted attributes absent
- **Invariant:** Attribute classes the requirements forbid do not exist anywhere in the platform.
- **Check shape:** Inspect every layer for the presence of attribute classes the requirements forbid.
- **Expected:** Absent everywhere, including landing and intermediate layers.
- **Fails when:** Sensitive data is excluded from the presentation layer but retained in landing, where it is still reachable.
- **Severity:** Must, wherever a compliance `AC` exists

---

## 7. Business Assertions (VA-Bnn)

Derived one-to-one from acceptance criteria. Template:

```
VA-B<nn>
Enforces:    AC-<nnn>
Statement:   <the business criterion, verbatim from output/requirements.md>
Check shape: <how the criterion is evaluated>
Expected:    <threshold or condition, taken verbatim from the criterion>
Tolerance:   <exact value from the requirements — never adjusted>
Severity:    Must | Should (inherited from the AC)
```

**Rules:**
- The `Statement` is copied verbatim. Paraphrasing is how a criterion quietly becomes weaker than what was agreed.
- The `Tolerance` comes from the requirements document. If a build cannot meet it, that is a business conversation, not a binding decision.
- If a criterion cannot be expressed as a check with a definite outcome, it is not testable — route it back to `@requirements` rather than binding something approximate.

### Common shapes

| Criterion shape | Assertion shape |
|---|---|
| "Matches an external reference within X%" | Compare aggregate against the reference for a defined period; assert relative difference ≤ X |
| "Reproduces previously published figures exactly" | Compare against archived values for a known period; assert zero difference |
| "Available by <time> on <schedule>" | Compare load completion timestamp against the deadline across a measurement window; assert success rate ≥ threshold |
| "A prior-period report does not change" | Capture output, apply the triggering change, re-run, compare; assert zero difference |
| "Identity A sees only its own scope" | Query as A; assert non-empty in scope and exactly zero out of scope |
| "Distinct entities are never merged" | Assert distinct identities for keys with lifecycle discontinuity |

---

## 8. Anti-Patterns

| Anti-pattern | Why it fails |
|---|---|
| Asserting only that a process succeeded | Success status proves the code ran, not that the output is right. Almost every wrong-numbers incident has a green run behind it |
| Asserting row counts only | An inflating join preserves counts and destroys sums. Assert both |
| Asserting `count > 0` | Passes on one row. Assert the expected count or a meaningful floor |
| Testing only the permitted access path | Proves nothing about denial, which is the case that matters |
| Tolerances chosen to make the current build pass | Inverts the loop: the build defines correctness instead of the business |
| Assertions that cannot fail | Consume runtime, produce green ticks, detect nothing |
| Re-running only failed assertions | Lets a repair break something that previously worked, undetected |
| Treating SKIPPED as PASS | Converts "we did not check" into "it works" — the single most common way a validation loop becomes theatre |
