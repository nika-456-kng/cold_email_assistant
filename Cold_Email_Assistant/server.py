from __future__ import annotations

import asyncio
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.encoders import jsonable_encoder
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, EmailStr, Field, ValidationError

from config import logger, settings
from nodes import check_reply_node
from state import LeadInput
from workflow import compile_workflow

app = FastAPI(
    title="Cold Email Assistant API",
    description="HTTP/WebSocket wrapper around the LangGraph cold-email workflow.",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

graph_app = compile_workflow()

_campaigns: dict[str, dict] = {}


class CampaignStartRequest(BaseModel):
    first_name: str = Field(..., min_length=1, max_length=100)
    last_name: str = Field(..., min_length=1, max_length=100)
    lead_email: EmailStr
    company_name: str = Field(..., min_length=1, max_length=200)
    title: str = Field(default="", max_length=200)


class EditRequest(BaseModel):
    feedback: str = Field(..., min_length=1, max_length=1000)


_CONTROL_CHARS_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def _sanitize_input(text: str, max_len: int = 1000) -> str:
    return _CONTROL_CHARS_RE.sub("", text).strip()[:max_len]


class ThreadEventBroker:
    def __init__(self) -> None:
        self._subscribers: dict[str, list[asyncio.Queue]] = {}
        self._loop: Optional[asyncio.AbstractEventLoop] = None

    def bind_event_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        self._loop = loop

    def subscribe(self, thread_id: str) -> asyncio.Queue:
        queue: asyncio.Queue = asyncio.Queue()
        self._subscribers.setdefault(thread_id, []).append(queue)
        return queue

    def unsubscribe(self, thread_id: str, queue: asyncio.Queue) -> None:
        subscribers = self._subscribers.get(thread_id, [])
        if queue in subscribers:
            subscribers.remove(queue)

    def publish(self, thread_id: str, event: dict) -> None:
        if self._loop is None:
            return
        for queue in list(self._subscribers.get(thread_id, [])):
            self._loop.call_soon_threadsafe(queue.put_nowait, event)


broker = ThreadEventBroker()


@app.on_event("startup")
async def _bind_broker_to_event_loop() -> None:
    broker.bind_event_loop(asyncio.get_running_loop())


def _thread_config(thread_id: str) -> dict:
    return {"configurable": {"thread_id": thread_id}}


def _get_snapshot_or_404(thread_id: str):
    snapshot = graph_app.get_state(_thread_config(thread_id))
    if not snapshot.values:
        raise HTTPException(status_code=404, detail=f"No campaign found with thread_id={thread_id}")
    return snapshot


def _run_graph(thread_id: str, resume_input) -> None:
    config = _thread_config(thread_id)
    for update in graph_app.stream(resume_input, config=config, stream_mode="updates"):
        for node_name, partial_state in update.items():
            broker.publish(
                thread_id,
                {
                    "type": "node_complete",
                    "node": node_name,
                    "detail": jsonable_encoder(partial_state),
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                },
            )
    broker.publish(
        thread_id,
        {"type": "graph_paused_or_completed", "timestamp": datetime.now(timezone.utc).isoformat()},
    )


def _serialize_state(thread_id: str, snapshot) -> dict:
    state = snapshot.values
    awaiting_review = "human_review_gate" in snapshot.next

    if awaiting_review:
        status = "awaiting_review"
    elif snapshot.next:
        status = "processing"
    elif state.get("send_error"):
        status = "failed"
    elif state.get("email_sent"):
        status = "completed"
    elif state.get("human_approved") is False:
        status = "rejected"
    else:
        status = "processing"

    return {
        "thread_id": thread_id,
        "status": status,
        "lead": state.get("lead"),
        "enrichment": state.get("enrichment"),
        "draft": state.get("draft"),
        "generation_attempts": state.get("generation_attempts", 0),
        "human_approved": state.get("human_approved"),
        "human_feedback": state.get("human_feedback"),
        "email_sent": state.get("email_sent", False),
        "delivery_mode": state.get("delivery_mode"),
        "gmail_message_id": state.get("gmail_message_id"),
        "gmail_thread_id": state.get("gmail_thread_id"),
        "gmail_draft_id": state.get("gmail_draft_id"),
        "send_error": state.get("send_error"),
        "reply_status": state.get("reply_status"),
        "reply_text": state.get("reply_text"),
        "errors": state.get("errors", []),
    }


@app.get("/api/health")
def health_check() -> dict:
    return {"status": "ok", "dry_run": settings.dry_run, "delivery_mode": settings.gmail_delivery_mode}


@app.get("/api/campaigns")
def list_campaigns() -> list[dict]:
    return sorted(_campaigns.values(), key=lambda c: c["created_at"], reverse=True)


@app.post("/api/campaigns/start")
def start_campaign(payload: CampaignStartRequest) -> dict:
    full_name = f"{payload.first_name.strip()} {payload.last_name.strip()}".strip()

    try:
        lead = LeadInput(
            full_name=full_name,
            email=payload.lead_email,
            company_name=payload.company_name.strip(),
            title=payload.title.strip(),
        )
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    thread_id = str(uuid.uuid4())
    logger.info("API: starting campaign for %s @ %s (thread_id=%s)", lead.full_name, lead.company_name, thread_id)

    try:
        _run_graph(thread_id, {"lead": lead, "errors": []})
    except Exception as exc:  # noqa: BLE001
        logger.exception("API: campaign start failed for thread_id=%s", thread_id)
        raise HTTPException(status_code=502, detail=f"Workflow execution failed: {exc}")

    _campaigns[thread_id] = {
        "thread_id": thread_id,
        "lead_name": lead.full_name,
        "company_name": lead.company_name,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }

    return _serialize_state(thread_id, graph_app.get_state(_thread_config(thread_id)))


@app.get("/api/campaigns/{thread_id}/state")
def get_campaign_state(thread_id: str) -> dict:
    snapshot = _get_snapshot_or_404(thread_id)
    return _serialize_state(thread_id, snapshot)


@app.post("/api/campaigns/{thread_id}/approve")
def approve_campaign(thread_id: str) -> dict:
    _get_snapshot_or_404(thread_id)
    logger.info("API: campaign %s approved for delivery", thread_id)

    graph_app.update_state(_thread_config(thread_id), {"human_approved": True, "human_feedback": None})
    try:
        _run_graph(thread_id, None)
    except Exception as exc:  # noqa: BLE001
        logger.exception("API: delivery failed for thread_id=%s", thread_id)
        raise HTTPException(status_code=502, detail=f"Delivery failed: {exc}")

    return _serialize_state(thread_id, graph_app.get_state(_thread_config(thread_id)))


@app.post("/api/campaigns/{thread_id}/reject")
def reject_campaign(thread_id: str) -> dict:
    _get_snapshot_or_404(thread_id)
    logger.info("API: campaign %s rejected", thread_id)

    graph_app.update_state(_thread_config(thread_id), {"human_approved": False, "human_feedback": None})
    try:
        _run_graph(thread_id, None)
    except Exception as exc:  # noqa: BLE001
        logger.exception("API: reject-path execution failed for thread_id=%s", thread_id)
        raise HTTPException(status_code=502, detail=f"Workflow execution failed: {exc}")

    return _serialize_state(thread_id, graph_app.get_state(_thread_config(thread_id)))


@app.post("/api/campaigns/{thread_id}/edit")
def edit_campaign(thread_id: str, payload: EditRequest) -> dict:
    _get_snapshot_or_404(thread_id)

    feedback = _sanitize_input(payload.feedback, max_len=1000)
    if not feedback:
        raise HTTPException(status_code=422, detail="Feedback cannot be empty.")

    logger.info("API: campaign %s revision requested - %r", thread_id, feedback)

    graph_app.update_state(_thread_config(thread_id), {"human_approved": False, "human_feedback": feedback})
    try:
        _run_graph(thread_id, None)
    except Exception as exc:  # noqa: BLE001
        logger.exception("API: draft regeneration failed for thread_id=%s", thread_id)
        raise HTTPException(status_code=502, detail=f"Draft regeneration failed: {exc}")

    return _serialize_state(thread_id, graph_app.get_state(_thread_config(thread_id)))


@app.get("/api/campaigns/{thread_id}/reply")
def check_campaign_reply(thread_id: str) -> dict:
    snapshot = _get_snapshot_or_404(thread_id)

    try:
        result = check_reply_node(snapshot.values)
    except Exception as exc:  # noqa: BLE001
        logger.exception("API: reply check failed for thread_id=%s", thread_id)
        raise HTTPException(status_code=502, detail=f"Reply check failed: {exc}")

    graph_app.update_state(_thread_config(thread_id), result)
    return _serialize_state(thread_id, graph_app.get_state(_thread_config(thread_id)))


@app.websocket("/ws/campaigns/{thread_id}")
async def campaign_events_ws(websocket: WebSocket, thread_id: str) -> None:
    await websocket.accept()
    queue = broker.subscribe(thread_id)
    try:
        while True:
            event = await queue.get()
            await websocket.send_json(event)
    except WebSocketDisconnect:
        pass
    finally:
        broker.unsubscribe(thread_id, queue)


_frontend_dir = Path(__file__).parent / "frontend"
if _frontend_dir.exists():
    app.mount("/", StaticFiles(directory=str(_frontend_dir), html=True), name="frontend")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("server:app", host="0.0.0.0", port=8000, reload=True, workers=1)
