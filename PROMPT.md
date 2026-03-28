# Requirements & Scenarios Generation Prompt

Use this prompt with an AI assistant to generate exhaustive requirements and scenarios for any project feature. Copy the template below, fill in the placeholders, and submit it to your assistant.

---

## The Prompt

```
You are a senior systems analyst and requirements engineer. Your job is to produce
a complete, implementation-ready specification and an exhaustive set of test scenarios
for the feature described below. Be as thorough as possible — missed requirements
cost 10x more to fix after implementation than before.

## Feature Description

{{Describe the feature in plain language. Include:
  - What it does
  - Who uses it
  - Why it exists (the business or technical motivation)
  - Any known constraints or non-negotiables}}

## Existing Context

{{Paste or reference any existing documentation, code, APIs, or prior decisions
  that are relevant. If this feature integrates with other systems, describe them here.
  Leave blank if greenfield.}}

## Technology Stack

{{List the languages, frameworks, databases, infrastructure, and any other
  technical constraints the implementation must conform to.}}

---

### Part 1: Requirements Specification

Produce a requirements document with the following sections. Every requirement MUST be
specific enough that two independent developers would implement it the same way.

#### 1.1 Functional Requirements

For each functional requirement, provide:

- **ID:** FR-XXX (sequential numbering)
- **Title:** Short descriptive name
- **Description:** What the system must do, stated as: "The system shall..."
- **Acceptance Criteria:** Concrete, testable conditions that confirm this requirement is met
- **Priority:** Must-Have / Should-Have / Nice-to-Have (MoSCoW)
- **Dependencies:** Other requirement IDs this depends on, or "None"

Cover ALL of the following dimensions exhaustively:

- **Core behavior:** The primary happy-path functionality
- **Input handling:** All expected input types, formats, ranges, and encoding
- **Output behavior:** What the system produces, including format, structure, and destination
- **State management:** How state is created, read, updated, and deleted
- **Sequencing and ordering:** Any required order of operations or event sequences
- **Concurrency:** Behavior under simultaneous access or parallel execution
- **Idempotency:** Whether operations are safe to retry and what guarantees exist
- **Configuration:** All configurable parameters, their defaults, valid ranges, and override mechanisms
- **Defaults:** What happens when optional inputs are omitted
- **Feature flags / toggles:** If the feature can be enabled or disabled, how and by whom

#### 1.2 Data Requirements

- **Data model:** Entities, attributes, types, constraints, and relationships
- **Validation rules:** Per-field constraints (type, range, length, format, uniqueness, nullability)
- **Data flow:** How data moves through the system, transformations at each stage
- **Persistence:** What is stored, where, retention policy, and backup considerations
- **Migration:** If this changes existing data structures, describe the migration path

#### 1.3 API / Interface Requirements

If the feature exposes or consumes APIs, interfaces, or integration points:

- **Endpoints / methods:** Signature, HTTP method (if applicable), URL pattern
- **Request schema:** Full schema with types, required/optional fields, constraints
- **Response schema:** Full schema including success and error response shapes
- **Authentication / authorization:** How callers are identified and what permissions are required
- **Rate limiting:** Limits, quotas, and behavior when exceeded
- **Versioning:** How the interface is versioned and backward-compatibility guarantees
- **Pagination:** Strategy, default page size, maximum page size
- **Idempotency keys:** If applicable, how duplicate requests are detected

#### 1.4 Error Handling Requirements

For every failure mode you can identify:

- **Error condition:** What goes wrong
- **Detection:** How the system detects it
- **Response:** What the system does (error code, message, retry, fallback, circuit-break)
- **User impact:** What the end user sees or experiences
- **Recovery:** How the system returns to a healthy state
- **Logging:** What is logged and at what level

Cover at minimum:
- Invalid input (each field individually and in combination)
- Missing or malformed data
- Authentication and authorization failures
- Downstream service failures (timeout, 5xx, connection refused)
- Resource exhaustion (disk, memory, connections, rate limits)
- Partial failures in multi-step operations
- Concurrent modification conflicts
- Data corruption or inconsistency detection

#### 1.5 Performance Requirements

- **Latency targets:** p50, p95, p99 for each operation (or state "no hard target" explicitly)
- **Throughput targets:** Expected and peak requests/events per second
- **Resource budgets:** CPU, memory, disk, network constraints
- **Scalability:** How the system should behave as load increases (linear, graceful degradation, etc.)
- **Caching:** What can be cached, TTL, invalidation strategy
- **Batch processing:** If applicable, batch sizes, parallelism, and timeout behavior

#### 1.6 Security Requirements

- **Authentication:** How users/services are authenticated
- **Authorization:** Permission model, roles, and what each role can access
- **Data protection:** Encryption at rest and in transit, PII handling, masking
- **Input sanitization:** How untrusted input is validated and sanitized
- **Audit logging:** What actions are logged for audit, retention period
- **Secrets management:** How API keys, tokens, and credentials are stored and rotated
- **OWASP top 10:** Explicitly address injection, XSS, CSRF, and other relevant threats

#### 1.7 Observability Requirements

- **Logging:** What events are logged, structured format, correlation IDs
- **Metrics:** What metrics are emitted (counters, gauges, histograms), naming convention
- **Alerting:** What conditions trigger alerts, severity levels, notification channels
- **Tracing:** Distributed tracing requirements, span structure
- **Health checks:** Liveness and readiness probe behavior

#### 1.8 Non-Functional Requirements

- **Availability:** Uptime target (e.g., 99.9%)
- **Disaster recovery:** RPO, RTO, failover behavior
- **Backward compatibility:** What existing behavior must be preserved
- **Deprecation:** If replacing existing functionality, the deprecation and migration timeline
- **Internationalization:** Locale, timezone, character encoding requirements
- **Accessibility:** WCAG level, assistive technology support (if UI is involved)
- **Documentation:** What documentation must be produced alongside the implementation
- **Compliance:** Regulatory or policy requirements (GDPR, SOC2, HIPAA, etc.)

#### 1.9 Constraints and Assumptions

- **Constraints:** Hard technical, organizational, or regulatory limits
- **Assumptions:** Things assumed to be true that, if wrong, would change the requirements
- **Out of scope:** Explicitly list what this feature does NOT do to prevent scope creep

#### 1.10 Dependency Map

- **Upstream dependencies:** Systems, services, or libraries this feature depends on
- **Downstream consumers:** Systems, services, or users that depend on this feature's output
- **Breaking change risk:** What changes here could break consumers, and what safeguards exist

---

### Part 2: Test Scenarios

Produce an exhaustive set of test scenarios using the format below. Each scenario should be
independently executable and should map back to one or more requirement IDs.

For each scenario, provide:

```
## Scenario NNN: {{Descriptive Title}}

**Requirements:** {{FR-XXX, FR-YYY, ...}}
**Category:** {{Happy Path | Edge Case | Error Handling | Security | Performance | Concurrency | Destructive}}
**Priority:** {{Critical | High | Medium | Low}}

**Preconditions:**
- {{State that must exist before this scenario runs}}

**Given:** {{Initial context and state}}
**When:** {{The action or event that triggers the behavior}}
**Then:** {{The expected outcome, stated as observable and verifiable assertions}}

**Validation:**
- {{Specific assertion 1: what to check and expected value}}
- {{Specific assertion 2: ...}}

**Cleanup:**
- {{Any state to tear down after this scenario, or "None"}}
```

Generate scenarios covering ALL of the following categories. Do not skip any category.
For each category, generate the MINIMUM number of scenarios needed for full coverage,
but do not artificially limit yourself — thoroughness is more important than brevity.

#### Category Checklist

**Happy Path (normal operations):**
- Basic operation with typical, valid inputs
- Each input variation that produces meaningfully different behavior
- Full end-to-end workflow covering the complete lifecycle
- Operations with all optional parameters provided
- Operations with only required parameters (defaults exercised)

**Input Validation & Edge Cases:**
- Empty inputs (empty string, empty array, empty object, null, undefined)
- Boundary values (min, max, min-1, max+1, zero, negative)
- Type mismatches (string where number expected, etc.)
- Encoding edge cases (unicode, emoji, multibyte characters, RTL text)
- Extremely long inputs (field-level and payload-level)
- Special characters (SQL metacharacters, HTML entities, control characters, path separators)
- Whitespace variations (leading, trailing, only whitespace, tabs, newlines)
- Duplicate inputs (same request twice, same data submitted twice)
- Malformed data (invalid JSON, truncated payloads, wrong content-type)

**State & Data:**
- Operation on non-existent resource
- Operation on already-deleted resource
- Concurrent modification of the same resource
- State transitions (valid and invalid)
- Data at storage limits
- Referential integrity (delete parent with children, orphan handling)

**Error Handling & Failure Modes:**
- Each documented error condition from the requirements
- Downstream service timeout
- Downstream service returning errors (4xx, 5xx)
- Downstream service returning malformed responses
- Partial failure in multi-step operations (what is rolled back vs. committed?)
- Resource exhaustion (connection pool, disk space, memory)
- Network partition / connection loss mid-operation

**Security:**
- Unauthenticated access attempt
- Authenticated but unauthorized access attempt
- Privilege escalation attempt
- Injection attacks (SQL, NoSQL, command, LDAP, XSS, SSTI)
- Path traversal attempt
- CSRF / replay attack
- Oversized request / denial of service attempt
- Sensitive data exposure in error messages or logs

**Performance & Load:**
- Operation under normal load meets latency target
- Operation under peak load degrades gracefully
- Batch operation with maximum batch size
- Concurrent operations at expected parallelism level

**Concurrency:**
- Race condition: two writes to the same resource simultaneously
- Read-during-write consistency
- Deadlock potential (if applicable)
- Queue or event ordering under load

**Idempotency & Retry:**
- Same request sent twice — second request is a no-op or returns same result
- Request retry after timeout — no duplicate side effects
- Partial completion followed by retry — system reaches correct final state

**Configuration & Deployment:**
- Feature with default configuration
- Feature with each configuration override
- Feature with invalid configuration (graceful error)
- Feature toggle on/off behavior
- Rolling deployment: old and new versions coexist (if applicable)

**Cleanup & Teardown:**
- Resource cleanup on success
- Resource cleanup on failure
- Graceful shutdown mid-operation

---

### Part 3: Traceability Matrix

Produce a traceability matrix confirming every requirement has at least one scenario covering it:

| Requirement ID | Requirement Title | Scenario IDs | Coverage Notes |
|----------------|-------------------|--------------|----------------|
| FR-001         | ...               | S-001, S-005 | ...            |

Flag any requirement that has ZERO scenarios as **UNCOVERED** and either add a scenario
or explain why testing is not feasible.

---

### Part 4: Open Questions

List anything that is ambiguous, contradictory, or missing from the feature description
that you had to assume an answer for. For each question:

- **Question:** What is unclear
- **Assumption made:** What you assumed for the purposes of this document
- **Impact if wrong:** What would change in the requirements or scenarios
- **Recommended resolution:** Who should answer this and by when

---

### Output Format

- Use Markdown
- Requirement IDs must be stable and referenced consistently
- Scenarios must be numbered sequentially (S-001, S-002, ...)
- All schemas should use a concrete notation (JSON Schema, TypeScript interface, Python TypedDict, or table format)
- Do not use vague language: no "should probably", "might need to", "could potentially" — be definitive or flag it as an open question
```

---

## Tips for Best Results

1. **Be specific in the Feature Description.** The more context you provide, the more targeted the output. Vague inputs produce generic requirements.

2. **Include existing code or API signatures** in the Existing Context section. The assistant can then produce requirements that align with your actual codebase.

3. **Iterate.** Run the prompt once, review the output, then follow up:
   - "Add scenarios for [specific edge case you noticed]"
   - "The requirement FR-012 is too vague — make the acceptance criteria more specific"
   - "We also need to handle [constraint you forgot to mention]"

4. **Split large features.** If your feature description exceeds ~500 words, consider breaking it into sub-features and running this prompt once per sub-feature.

5. **Use the traceability matrix** to verify completeness before starting implementation. Every requirement should be testable, and every test should trace to a requirement.

6. **Feed the outputs into your pipeline.** The spec file maps to `specs/my-feature.md` and the scenarios file maps to `specs/my-feature-scenarios.md` for use with the Attractor pipeline or similar automation.
