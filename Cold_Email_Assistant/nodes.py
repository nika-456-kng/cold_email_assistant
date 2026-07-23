from __future__ import annotations

from typing import Literal

from config import logger, settings
from services import enrich_lead, gmail_client, openai_copywriter, reply_classifier
from state import ColdEmailState, EnrichmentSignals


def enrich_lead_node(state: ColdEmailState) -> dict:
    lead = state["lead"]
    logger.info("enrich_lead_node: enriching %s @ %s", lead.full_name, lead.company_name)

    try:
        enrichment = enrich_lead(lead)
    except Exception as exc:  # noqa: BLE001
        logger.warning("enrich_lead_node: enrichment failed, continuing with empty signals: %s", exc)
        enrichment = EnrichmentSignals(source="simulated")
        errors = state.get("errors", []) + [f"Enrichment error: {exc}"]
        return {"enrichment": enrichment, "errors": errors}

    logger.info(
        "enrich_lead_node: found %d tech signals, %d role signals, %d news signals",
        len(enrichment.tech_stack),
        len(enrichment.open_roles),
        len(enrichment.recent_news),
    )
    return {"enrichment": enrichment}


def generate_draft_node(state: ColdEmailState) -> dict:
    lead = state["lead"]
    enrichment = state["enrichment"]
    attempts = state.get("generation_attempts", 0) + 1

    revision_notes = state.get("human_feedback") if attempts > 1 else None

    logger.info("generate_draft_node: attempt #%d for %s", attempts, lead.email)

    draft = openai_copywriter.generate_draft(lead, enrichment, revision_notes=revision_notes)

    logger.info("generate_draft_node: draft ready (%d words) - subject: %r", draft.word_count, draft.subject)

    return {
        "draft": draft,
        "generation_attempts": attempts,
        "human_approved": None,
        "human_feedback": None,
    }


def human_review_gate(state: ColdEmailState) -> dict:
    approved = state.get("human_approved")
    feedback = state.get("human_feedback")
    lead = state["lead"]

    if approved:
        logger.info("human_review_gate: reviewer APPROVED the draft for %s", lead.email)
    elif feedback:
        logger.info("human_review_gate: reviewer requested an EDIT for %s - %r", lead.email, feedback)
    else:
        logger.info("human_review_gate: reviewer REJECTED the draft for %s", lead.email)

    return {}


def route_after_review(state: ColdEmailState) -> Literal["approved", "revise", "rejected"]:
    if state.get("human_approved"):
        return "approved"
    if state.get("human_feedback"):
        return "revise"
    return "rejected"


def send_email_node(state: ColdEmailState) -> dict:
    lead = state["lead"]
    draft = state["draft"]
    mode = settings.gmail_delivery_mode

    if settings.dry_run:
        logger.info("send_email_node: [DRY RUN] would %s for %s | subject=%r", mode, lead.email, draft.subject)
        return {
            "email_sent": True,
            "delivery_mode": mode,
            "gmail_message_id": "dry-run-simulated-message-id",
            "gmail_thread_id": "dry-run-simulated-thread-id",
            "gmail_draft_id": "dry-run-simulated-draft-id" if mode == "draft" else None,
            "send_error": None,
        }

    try:
        if mode == "draft":
            result = gmail_client.create_gmail_draft(to_email=lead.email, subject=draft.subject, body=draft.body)
            logger.info("send_email_node: created Gmail draft for %s (draft id=%s)", lead.email, result["draft_id"])
            return {
                "email_sent": True,
                "delivery_mode": "draft",
                "gmail_draft_id": result["draft_id"],
                "gmail_message_id": result["message_id"],
                "gmail_thread_id": result["thread_id"],
                "send_error": None,
            }

        result = gmail_client.send_gmail_message(to_email=lead.email, subject=draft.subject, body=draft.body)
        logger.info("send_email_node: sent to %s (message id=%s)", lead.email, result["message_id"])
        return {
            "email_sent": True,
            "delivery_mode": "send",
            "gmail_draft_id": None,
            "gmail_message_id": result["message_id"],
            "gmail_thread_id": result["thread_id"],
            "send_error": None,
        }
    except Exception as exc:  # noqa: BLE001
        logger.error("send_email_node: delivery failed for %s: %s", lead.email, exc)
        return {"email_sent": False, "send_error": str(exc)}


def check_reply_node(state: ColdEmailState) -> dict:
    lead = state["lead"]
    thread_id = state.get("gmail_thread_id")
    delivery_mode = state.get("delivery_mode")

    if settings.dry_run or not thread_id or delivery_mode == "draft":
        logger.debug(
            "check_reply_node: skipping reply check for %s (dry_run=%s, delivery_mode=%s)",
            lead.email, settings.dry_run, delivery_mode,
        )
        return {"reply_status": "NO_REPLY", "reply_text": None}

    try:
        reply_text = gmail_client.get_latest_reply(thread_id)
    except Exception as exc:  # noqa: BLE001
        logger.warning("check_reply_node: failed to fetch thread %s: %s", thread_id, exc)
        errors = state.get("errors", []) + [f"Reply check error: {exc}"]
        return {"reply_status": "NO_REPLY", "reply_text": None, "errors": errors}

    if not reply_text:
        logger.info("check_reply_node: no reply yet for %s", lead.email)
        return {"reply_status": "NO_REPLY", "reply_text": None}

    intent = reply_classifier.classify(reply_text)
    logger.info("check_reply_node: classified reply from %s as %s", lead.email, intent)
    return {"reply_status": intent, "reply_text": reply_text}
