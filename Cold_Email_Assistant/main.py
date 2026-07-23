from __future__ import annotations

import argparse
import uuid

from pydantic import ValidationError
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt
from rich.table import Table

from config import logger, settings
from services import gmail_client, reply_classifier
from state import LeadInput
from workflow import compile_workflow

console = Console()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Cold Email LangGraph Assistant")
    parser.add_argument("--name", help="Lead's full name")
    parser.add_argument("--email", help="Lead's email address")
    parser.add_argument("--company", help="Lead's company name")
    parser.add_argument("--title", help="Lead's job title", default="")
    parser.add_argument(
        "--check-thread",
        metavar="THREAD_ID",
        help="Standalone mode: check an existing Gmail thread for a reply, classify it, and exit.",
    )
    return parser.parse_args()


def collect_lead(args: argparse.Namespace) -> LeadInput:
    if args.name and args.email and args.company:
        try:
            return LeadInput(full_name=args.name, email=args.email, company_name=args.company, title=args.title)
        except ValidationError as exc:
            console.print(f"[red]Invalid lead details supplied via CLI flags:[/red]\n{exc}")
            raise SystemExit(1)

    console.print(Panel.fit("[bold cyan]Cold Email Assistant[/bold cyan] — new lead intake", border_style="cyan"))
    while True:
        try:
            full_name = Prompt.ask("Lead full name")
            email = Prompt.ask("Lead email")
            company_name = Prompt.ask("Company name")
            title = Prompt.ask("Job title (optional)", default="")
            return LeadInput(full_name=full_name, email=email, company_name=company_name, title=title)
        except ValidationError as exc:
            console.print(f"[red]That didn't validate, try again:[/red]\n{exc}")


def render_review_screen(state: dict) -> None:
    lead = state["lead"]
    enrichment = state.get("enrichment")
    draft = state["draft"]

    console.rule("[bold yellow]Human Review Required[/bold yellow]")

    recipient_table = Table(show_header=False, box=None, padding=(0, 1))
    recipient_table.add_row("[bold]Name[/bold]", lead.full_name)
    recipient_table.add_row("[bold]Email[/bold]", lead.email)
    recipient_table.add_row("[bold]Company[/bold]", lead.company_name)
    recipient_table.add_row("[bold]Title[/bold]", lead.title or "-")
    console.print(Panel(recipient_table, title="Target Recipient", border_style="blue"))

    if enrichment:
        signals_table = Table(show_header=False, box=None, padding=(0, 1))
        signals_table.add_row("[bold]Tech Stack[/bold]", ", ".join(enrichment.tech_stack) or "-")
        signals_table.add_row("[bold]Open Roles[/bold]", ", ".join(enrichment.open_roles) or "-")
        signals_table.add_row("[bold]Recent News[/bold]", ", ".join(enrichment.recent_news) or "-")
        signals_table.add_row("[bold]Industry[/bold]", enrichment.industry or "-")
        signals_table.add_row("[bold]Company Size[/bold]", enrichment.company_size or "-")
        signals_table.add_row("[bold]Source[/bold]", enrichment.source)
        console.print(Panel(signals_table, title="Company Signals", border_style="magenta"))

    email_body = f"[bold]Subject:[/bold] {draft.subject}\n\n{draft.body}"
    console.print(
        Panel(email_body, title=f"Drafted Email ({draft.word_count} words)", border_style="green")
    )

    console.print(f"[dim]Delivery mode on approval: {settings.gmail_delivery_mode}[/dim]")


def review_decision_loop() -> tuple[bool, str | None]:
    choice = Prompt.ask(
        "Approve (y) / Reject (n) / Edit (e)",
        choices=["y", "n", "e"],
        default="y",
        show_choices=True,
    )
    if choice == "y":
        return True, None
    if choice == "n":
        return False, None
    feedback = Prompt.ask("What should change? (feedback for GPT-4o)")
    return False, feedback


def check_thread_command(thread_id: str) -> None:
    console.rule("[bold]Reply Check[/bold]")
    console.print(f"[dim]Looking up thread {thread_id}...[/dim]")

    try:
        reply_text = gmail_client.get_latest_reply(thread_id)
    except Exception as exc:  # noqa: BLE001
        console.print(f"[bold red]Failed to fetch thread:[/bold red] {exc}")
        raise SystemExit(1)

    if not reply_text:
        console.print("[yellow]No reply found yet on this thread.[/yellow]")
        return

    intent = reply_classifier.classify(reply_text)
    console.print(f"[bold]Reply intent:[/bold] {intent}")
    console.print(Panel(reply_text, title="Reply text", border_style="cyan"))


def run() -> None:
    args = parse_args()

    if args.check_thread:
        check_thread_command(args.check_thread)
        return

    lead = collect_lead(args)

    app = compile_workflow()
    thread_id = str(uuid.uuid4())
    config = {"configurable": {"thread_id": thread_id}}

    initial_state = {"lead": lead, "errors": []}

    console.print(f"\n[dim]Starting workflow (dry_run={settings.dry_run}, thread_id={thread_id})[/dim]")
    app.invoke(initial_state, config=config)

    while True:
        snapshot = app.get_state(config)
        if not snapshot.next:
            break

        render_review_screen(snapshot.values)
        approved, feedback = review_decision_loop()

        app.update_state(config, {"human_approved": approved, "human_feedback": feedback})
        app.invoke(None, config=config)

    final_state = app.get_state(config).values
    console.rule("[bold]Result[/bold]")

    if final_state.get("email_sent"):
        delivery_mode = final_state.get("delivery_mode", settings.gmail_delivery_mode)
        dry_note = " [yellow](dry run - nothing left the outbox)[/yellow]" if settings.dry_run else ""

        if delivery_mode == "draft":
            console.print(f"[bold green]Gmail draft created[/bold green]{dry_note}")
            console.print(f"Draft id: {final_state.get('gmail_draft_id')}")
        else:
            console.print(f"[bold green]Email sent successfully[/bold green]{dry_note}")

        console.print(f"Gmail message id: {final_state.get('gmail_message_id')}")
        console.print(f"Gmail thread id: {final_state.get('gmail_thread_id')}")

        reply_status = final_state.get("reply_status")
        if reply_status and reply_status != "NO_REPLY":
            console.print(f"\n[bold]Reply detected:[/bold] {reply_status}")
            console.print(f"[dim]{final_state.get('reply_text')}[/dim]")
        elif delivery_mode == "send":
            console.print(
                "\n[dim]No reply yet - re-check later with "
                f"`python main.py --check-thread {final_state.get('gmail_thread_id')}`[/dim]"
            )
    elif final_state.get("send_error"):
        console.print(f"[bold red]Delivery failed:[/bold red] {final_state['send_error']}")
    else:
        console.print("[bold yellow]No email was sent (reviewer rejected the draft).[/bold yellow]")

    if final_state.get("errors"):
        console.print("\n[dim]Non-fatal issues encountered along the way:[/dim]")
        for err in final_state["errors"]:
            console.print(f"  - {err}")


if __name__ == "__main__":
    try:
        run()
    except KeyboardInterrupt:
        console.print("\n[dim]Interrupted by user, exiting.[/dim]")
    except Exception:
        logger.exception("Unhandled error in main workflow")
        raise
