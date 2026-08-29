"""
Canonical critical-flag detection for the Semantic Relevance Engine.

This is the SINGLE SOURCE OF TRUTH for critical-info regex patterns.
Both Tier 1 (chunker.py) and Tier 2 (optimizer.py) import from here.

Design principles for the canonical set:
- Prefer phrase-level patterns over bare-word matches to minimize false positives.
  e.g. "do not" / "must not" rather than bare "not"; "failed with" rather than
  bare "failed".
- Every pattern added here must pass the DETECTOR_SHOULD_NOT_FIRE cases in
  test_hard_cases.py Category 2. If a new term causes a false positive on
  benign text like "See step 4 for details", it doesn't belong here.
- This module is the DETECTOR. The flag-comparison step inside compress_chunk()
  (optimizer.py) acts as the VALIDATOR — it reuses detect_critical_flags() to
  verify that compressed text preserves the same flags as the original. These
  are separate responsibilities (detection vs. validation) but intentionally
  share the same function to prevent drift.

Ancestry:
- Tier 2 (optimizer.py) patterns are the precision baseline.
- Tier 1 (chunker.py) had broader bare-word patterns. The ones that survived
  curation into this canonical set are noted with "# from Tier 1" comments.
  Bare-word matches like "not", "no", "error", "failed", "warning", "fatal"
  were deliberately excluded — they fire on benign text too readily.
"""

import re

CRITICAL_PATTERNS: list[tuple[str, re.Pattern]] = [
    # -- negation --
    # Tier 2 precision phrases only. Bare-word contractions (isn't, aren't,
    # doesn't) and connectives (neither, nor, without) were tested and
    # confirmed to fire on benign text — removed per false-positive discipline.
    ("negation", re.compile(
        r"\b(do not|don't|never|must not|mustn't|can't|cannot|won't|shouldn't|"
        r"should not"
        r")\b", re.IGNORECASE)),

    # -- number --
    # Tier 2's unit-aware pattern: requires a numeric value followed by a
    # recognized unit, OR an assignment pattern like "is 42" / "set to 500".
    # Bare \d+ is deliberately excluded — it false-positives on "step 4",
    # "room 5", "chapter 3", "issue #404", "500 Main Street", "port 8080".
    ("number", re.compile(
        r"(\b\d+(\.\d+)?\s*(seconds?|s|ms|minutes?|hours?|days?|%|percent|"
        r"tokens?|requests?|MB|GB|KB)(?!\w))|"
        r"(\b(is|=|set(?:[a-zA-Z\s]+)?to|equals)\s+\d+\b)|"
        # from Tier 1: dollar amounts are always significant
        r"(\$\d+(?:\.\d+)?)",
        re.IGNORECASE)),

    # -- constraint --
    # Tier 2 baseline + curated Tier 1 additions that don't false-positive
    ("constraint", re.compile(
        r"\b(must|required|shall|has to|needs to|only|always|mandatory|"
        # from Tier 1: these are strong constraint signals, not casual words
        r"strictly|forbidden|restricted"
        r")\b", re.IGNORECASE)),

    # -- error --
    # Tier 2's HTTP-status-aware pattern + curated Tier 1 additions
    ("error", re.compile(
        r"(\b(HTTP\s*)?[1-5]\d{2}\b.{0,20}(error|status|returns?))|"
        r"(\b(error|status|returns?)\b.{0,20}\b(HTTP\s*)?[1-5]\d{2}\b)|"
        r"(\bexception\b|\btraceback\b|\bfailed with\b|\bstack trace\b|"
        # from Tier 1: unambiguous error-domain terms
        r"\bfatal\b|\bpanic\b)",
        re.IGNORECASE)),

    # -- decision --
    # Tier 2's phrase-level patterns + curated Tier 1 single-word additions
    # that are unambiguous decision indicators
    ("decision", re.compile(
        r"\b(we\s+(chose|decided|will use|are using)|we're\s+using|"
        r"switched\s+to|migrat(ed|ing)\s+(to|off)|"
        # from Tier 1: these past-tense verbs are strong decision signals
        r"adopted|approved|rejected"
        r")\b", re.IGNORECASE)),
]


def detect_critical_flags(text: str) -> list[str]:
    """
    Detect critical information flags in chunk text.

    This is the canonical detector — the single source of truth for
    critical-flag regex patterns across both Tier 1 and Tier 2.

    Returns a list of flag names (e.g. ["negation", "number"]) that
    fire on the given text.
    """
    flags = []
    for name, pattern in CRITICAL_PATTERNS:
        if pattern.search(text):
            flags.append(name)
    return flags

