# Adversarial test cases

Owned jointly: Person 3 extends this for benchmark/quality eval, Person 2
(hardest part) uses it to validate the critical-info detector before
building the compressor on top of it. Add cases here as you find gaps —
don't wait for a scheduled "adversarial testing" phase to start using it.

Format: input chunk text → expected critical_flags → notes.

## Negations

| Text | Expected flags | Status |
|---|---|---|
| "Do NOT use MongoDB for this project." | negation | should pass regex |
| "We can't go with Mongo." | negation | likely regex gap — paraphrase, no trigger word match on "Mongo"/"MongoDB" proximity, verify |
| "MongoDB is off the table." | negation | regex gap — no negation trigger word at all |

## Numbers

| Text | Expected flags | Status |
|---|---|---|
| "Timeout is set to 30 seconds." | number | should pass |
| "The timeout, thirty seconds, was chosen after testing." | number | regex gap — spelled-out number |
| "Requests time out after 30s." | number | check unit regex matches "30s" (no space) |

## Constraints

| Text | Expected flags | Status |
|---|---|---|
| "The API must remain stateless even under load." | constraint | should pass |
| "It's required that we support offline mode." | constraint | should pass |
| "Ideally the API would be stateless." | none (not a hard constraint) | verify it does NOT over-trigger — "ideally" signals soft preference, not requirement |

## Errors

| Text | Expected flags | Status |
|---|---|---|
| "Endpoint returns HTTP 401 after the auth change." | error | should pass |
| "Client threw an exception during login." | error | should pass |
| "Getting weird behavior on the login page." | none | should NOT trigger — vague, no specific error signal |

## Decisions

| Text | Expected flags | Status |
|---|---|---|
| "We decided to migrate off Postgres next quarter." | decision | should pass |
| "We're using JWT now instead of sessions." | decision | should pass |

## Deduplication traps (Person 1's dedup, but verify downstream)

| Text A | Text B | Expected | Notes |
|---|---|---|---|
| "The database is PostgreSQL." | "The application uses PostgreSQL." | dedup OK — same fact | |
| "We use Postgres." | "We're migrating off Postgres next quarter." | MUST NOT dedup | different facts, high topical similarity |

## Full-pipeline scenarios

- **Mostly irrelevant context**: 90% of chunks unrelated to query → expect
  large token reduction, all pinned/critical chunks still survive if present.
- **Everything relevant**: all chunks score high relevance → expect limited
  removal, compression does most of the work instead.
- **Small context**: total tokens under threshold → expect route=SKIP,
  no pipeline stages run.
- **Compression failure injection**: force the compression LLM call to
  raise/timeout → expect fallback to uncompressed-but-filtered context,
  `fallback_triggered: true` in trace, no crash.
- **Budget smaller than pinned content**: set token_budget below the sum of
  all pinned chunk tokens → expect `budget_exceeded_by_pinned_content: true`
  logged loudly, not a silent truncation.
