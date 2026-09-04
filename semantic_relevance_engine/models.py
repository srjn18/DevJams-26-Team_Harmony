"""
Data models and schema definitions for the Semantic Relevance Engine.
Conforms strictly to the hackathon LLM context optimization middleware contract.
"""

from typing import List, Optional, Literal
from pydantic import BaseModel, Field


SourceType = Literal["conversation", "document", "tool_output", "system"]
TagType = Literal["SYSTEM", "PERSISTENT_CONSTRAINT", "CONVERSATION", "DOC", "TOOL_OUTPUT"]


class Chunk(BaseModel):
    id: str = Field(..., description="Unique chunk identifier, e.g. 'c_0001'")
    text: str = Field(..., description="The chunk text content")
    token_count: int = Field(..., description="Estimated or exact token count")
    source: SourceType = Field(..., description="Source of the chunk")
    tag: TagType = Field(..., description="Tag classifying the chunk role")
    timestamp: Optional[str] = Field(None, description="ISO8601 timestamp or None")
    position: int = Field(..., description="Original order in context, 0-indexed")
    pinned: bool = Field(default=False, description="True if tag is SYSTEM or PERSISTENT_CONSTRAINT")
    critical_flags: List[str] = Field(default_factory=list, description="Critical flags (negation, number, constraint, error, decision, etc.)")
    relevance_score: float = Field(default=0.0, description="Cosine similarity score to query, 0.0 to 1.0")
    importance_score: float = Field(default=0.0, description="Importance score based on metadata/role")
    final_score: float = Field(default=0.0, description="Final weighted combination score")
    compressed: bool = Field(default=False, description="True if this chunk has been successfully compressed")
    is_duplicate_of: Optional[str] = Field(None, description="Chunk ID of kept chunk if duplicate, else None")
    embedding: Optional[List[float]] = Field(default=None, description="Internal vector embedding, omitted in exported dicts if needed")
    trace_events: List[str] = Field(default_factory=list, description="Trace events log for checking empty compressions/hallucinations")

    def to_dict(self, include_embedding: bool = False) -> dict:
        data = self.model_dump()
        if not include_embedding:
            data.pop("embedding", None)
        return data
