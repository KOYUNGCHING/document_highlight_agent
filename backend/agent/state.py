"""Shared state and validated contracts. Only messages use an append reducer."""
from typing import Annotated, Literal, TypedDict

from langchain_core.messages import AnyMessage
from langgraph.graph.message import add_messages
from pydantic import BaseModel, ConfigDict, Field


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Plan(Contract):
    task: Literal["qa", "document_summary", "clarify"]
    resolved_question: str = Field(min_length=1, max_length=4000)
    clarification: str = Field(default="", max_length=1000)


class Draft(Contract):
    answer: str = Field(min_length=1, max_length=12000)
    citation_ids: list[str] = Field(default_factory=list, max_length=40)
    primary_citation_id: str | None = None
    status: Literal["answered", "insufficient_evidence"] = "answered"


class Review(Contract):
    supported: bool
    feedback: list[str] = Field(default_factory=list, max_length=10)


class MemorySummary(Contract):
    summary: str = Field(min_length=1, max_length=6000)


class EvidenceBlock(TypedDict):
    document_id: str
    block_id: str
    page: int
    text: str
    rect: list[float]


class AgentState(TypedDict, total=False):
    messages: Annotated[list[AnyMessage], add_messages]
    conversation_summary: str
    document_id: str
    question: str
    resolved_question: str
    task: str
    clarification: str
    evidence: list[EvidenceBlock]
    draft: dict
    review_passed: bool
    review_feedback: list[str]
    revision_count: int
    result: dict
