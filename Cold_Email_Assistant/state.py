from typing import Literal, Optional, TypedDict

from pydantic import BaseModel, EmailStr, Field

ReplyStatus = Literal["HOT_LEAD", "NOT_INTERESTED", "OUT_OF_OFFICE", "NO_REPLY"]


class LeadInput(BaseModel):
    full_name: str
    email: EmailStr
    company_name: str
    title: str = Field(default="", description="Job title, e.g. 'VP of Engineering'")


class EnrichmentSignals(BaseModel):
    tech_stack: list[str] = Field(default_factory=list)
    open_roles: list[str] = Field(default_factory=list)
    recent_news: list[str] = Field(default_factory=list)
    company_size: Optional[str] = None
    industry: Optional[str] = None
    source: str = Field(default="simulated", description="'apollo', 'clay', or 'simulated'")


class DraftEmail(BaseModel):
    subject: str
    body: str
    word_count: int = 0


class ColdEmailState(TypedDict, total=False):
    lead: LeadInput

    enrichment: EnrichmentSignals

    draft: DraftEmail
    generation_attempts: int

    human_approved: Optional[bool]
    human_feedback: Optional[str]

    email_sent: bool
    delivery_mode: str
    gmail_message_id: Optional[str]
    gmail_thread_id: Optional[str]
    gmail_draft_id: Optional[str]
    send_error: Optional[str]

    reply_status: Optional[ReplyStatus]
    reply_text: Optional[str]

    errors: list[str]
