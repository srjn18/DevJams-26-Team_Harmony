"""
Context chunking and tagging module for Semantic Relevance Engine.
Splits raw context strings into structured chunks with source attribution,
tagging, position tracking, and critical flag detection.
"""

import re
from typing import List, Tuple, Optional
from datetime import datetime, timezone
from .models import Chunk, SourceType, TagType
from .critical_flags import detect_critical_flags


# Regex patterns for various format markers
BRACKET_MARKER_PATTERN = re.compile(
    r'(?m)^(?:\[(SYSTEM|USER|ASSISTANT|HUMAN|AI|CONVERSATION|DOCUMENT|DOC|TOOL_OUTPUT|TOOL)\]\s*)',
    re.IGNORECASE
)

COLON_PREFIX_PATTERN = re.compile(
    r'(?m)^(System|User|Assistant|Human|AI|Document|Doc|Tool Output|Tool):\s*',
    re.IGNORECASE
)

MARKDOWN_HEADER_PATTERN = re.compile(
    r'(?m)^(#{1,6}\s+.+)$'
)


from .optimizer import approx_token_count


def _map_marker_to_source_and_tag(marker: str) -> Tuple[SourceType, TagType, bool]:
    """Map parsed marker or prefix to SourceType, TagType, and pinned flag."""
    norm = marker.strip().upper()
    if norm in ("SYSTEM",):
        return "system", "SYSTEM", True
    elif norm in ("PERSISTENT_CONSTRAINT",):
        return "system", "PERSISTENT_CONSTRAINT", True
    elif norm in ("USER", "ASSISTANT", "HUMAN", "AI", "CONVERSATION"):
        return "conversation", "CONVERSATION", False
    elif norm in ("DOCUMENT", "DOC"):
        return "document", "DOC", False
    elif norm in ("TOOL_OUTPUT", "TOOL", "TOOL OUTPUT"):
        return "tool_output", "TOOL_OUTPUT", False
    else:
        return "document", "DOC", False


def _split_by_bracket_markers(context: str) -> Optional[List[Tuple[str, str]]]:
    """Split context if bracket markers like [SYSTEM], [USER], [DOC] are present."""
    matches = list(BRACKET_MARKER_PATTERN.finditer(context))
    if not matches:
        return None

    chunks_raw: List[Tuple[str, str]] = []
    # If there's leading text before the first marker
    if matches[0].start() > 0:
        leading_text = context[:matches[0].start()].strip()
        if leading_text:
            chunks_raw.append(("DOC", leading_text))

    for i, match in enumerate(matches):
        marker = match.group(1).upper()
        start = match.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(context)
        content = context[start:end].strip()
        if content:
            chunks_raw.append((marker, content))

    return chunks_raw if chunks_raw else None


def _split_by_colon_prefixes(context: str) -> Optional[List[Tuple[str, str]]]:
    """Split context by prefix style like 'User: ...', 'Assistant: ...', 'System: ...'"""
    matches = list(COLON_PREFIX_PATTERN.finditer(context))
    if not matches or len(matches) < 2:
        return None

    chunks_raw: List[Tuple[str, str]] = []
    if matches[0].start() > 0:
        leading_text = context[:matches[0].start()].strip()
        if leading_text:
            chunks_raw.append(("DOC", leading_text))

    for i, match in enumerate(matches):
        marker = match.group(1).upper()
        start = match.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(context)
        content = context[start:end].strip()
        if content:
            chunks_raw.append((marker, content))

    return chunks_raw if chunks_raw else None


def _split_by_markdown_headers(context: str) -> Optional[List[Tuple[str, str]]]:
    """Split context by markdown section headers (## Section)."""
    matches = list(MARKDOWN_HEADER_PATTERN.finditer(context))
    if not matches or len(matches) < 2:
        return None

    chunks_raw: List[Tuple[str, str]] = []
    if matches[0].start() > 0:
        leading_text = context[:matches[0].start()].strip()
        if leading_text:
            chunks_raw.append(("DOC", leading_text))

    for i, match in enumerate(matches):
        header = match.group(1).strip()
        start = match.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(context)
        content = context[start:end].strip()
        combined = f"{header}\n{content}".strip() if content else header
        if combined:
            chunks_raw.append(("DOC", combined))

    return chunks_raw if chunks_raw else None


def _split_by_paragraphs(context: str) -> List[Tuple[str, str]]:
    """Fallback: Split context by paragraph breaks (double newlines)."""
    paragraphs = re.split(r'\n\s*\n', context)
    chunks_raw: List[Tuple[str, str]] = []
    for p in paragraphs:
        cleaned = p.strip()
        if cleaned:
            chunks_raw.append(("DOC", cleaned))
    return chunks_raw


def chunk_context(context: str) -> List[Chunk]:
    """
    Parse and chunk a raw context string into a list of Chunk objects.
    Supports bracket markers, prefix markers, markdown headers, and paragraph splitting.
    """
    if not context or not context.strip():
        return []

    # Try parsing strategies in order of specificity
    raw_sections = (
        _split_by_bracket_markers(context) or
        _split_by_colon_prefixes(context) or
        _split_by_markdown_headers(context) or
        _split_by_paragraphs(context)
    )

    if not raw_sections:
        raw_sections = [("DOC", context.strip())]

    chunks: List[Chunk] = []
    for pos, (marker, text) in enumerate(raw_sections):
        source, tag, pinned = _map_marker_to_source_and_tag(marker)
        chunk_id = f"c_{pos + 1:04d}"
        token_cnt = approx_token_count(text)
        critical_flags = detect_critical_flags(text)

        chunks.append(
            Chunk(
                id=chunk_id,
                text=text,
                token_count=token_cnt,
                source=source,
                tag=tag,
                timestamp=None,
                position=pos,
                pinned=pinned,
                critical_flags=critical_flags,
                relevance_score=0.0,
                is_duplicate_of=None,
                embedding=None,
            )
        )

    return chunks
