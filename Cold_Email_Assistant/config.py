import logging
import os
import sys
from dataclasses import dataclass, field

from dotenv import load_dotenv

load_dotenv(override=False)


def _str_to_bool(value: str) -> bool:
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


@dataclass(frozen=True)
class Settings:
    openai_api_key: str = field(default_factory=lambda: os.getenv("OPENAI_API_KEY", ""))
    openai_model: str = field(default_factory=lambda: os.getenv("OPENAI_MODEL", "gpt-4o"))

    apollo_api_key: str = field(default_factory=lambda: os.getenv("APOLLO_API_KEY", ""))
    apollo_base_url: str = field(
        default_factory=lambda: os.getenv("APOLLO_BASE_URL", "https://api.apollo.io/v1")
    )

    clay_api_key: str = field(default_factory=lambda: os.getenv("CLAY_API_KEY", ""))
    clay_webhook_url: str = field(default_factory=lambda: os.getenv("CLAY_WEBHOOK_URL", ""))

    gmail_credentials_path: str = field(
        default_factory=lambda: os.getenv("GMAIL_CREDENTIALS_PATH", "credentials.json")
    )
    gmail_token_path: str = field(default_factory=lambda: os.getenv("GMAIL_TOKEN_PATH", "token.json"))
    sender_email: str = field(default_factory=lambda: os.getenv("SENDER_EMAIL", ""))

    gmail_delivery_mode: str = field(
        default_factory=lambda: os.getenv("GMAIL_DELIVERY_MODE", "draft").strip().lower()
    )

    dry_run: bool = field(default_factory=lambda: _str_to_bool(os.getenv("DRY_RUN", "true")))
    log_level: str = field(default_factory=lambda: os.getenv("LOG_LEVEL", "INFO").upper())

    request_timeout_seconds: float = field(
        default_factory=lambda: float(os.getenv("REQUEST_TIMEOUT_SECONDS", "10"))
    )
    max_api_retries: int = field(default_factory=lambda: int(os.getenv("MAX_API_RETRIES", "3")))

    allowed_origins: list[str] = field(
        default_factory=lambda: [
            origin.strip()
            for origin in os.getenv("ALLOWED_ORIGINS", "http://localhost:5173,http://localhost:3000,http://localhost:8000").split(",")
            if origin.strip()
        ]
    )

    def validate(self) -> None:
        errors = []

        if not self.openai_api_key:
            errors.append(
                "OPENAI_API_KEY is not set. Add it to your .env file or export it "
                "as an environment variable. Get a key at https://platform.openai.com/api-keys"
            )
        elif not self.openai_api_key.startswith("sk-"):
            errors.append(
                "OPENAI_API_KEY does not look like a valid OpenAI key (expected it "
                "to start with 'sk-'). Double-check the value in your .env file."
            )

        if self.gmail_delivery_mode not in {"draft", "send"}:
            errors.append(
                f"GMAIL_DELIVERY_MODE must be 'draft' or 'send', got '{self.gmail_delivery_mode}'. "
                "'draft' is the safe default - only switch to 'send' once you trust the pipeline."
            )

        if not self.dry_run:
            if not self.sender_email:
                errors.append(
                    "SENDER_EMAIL is required when DRY_RUN=false, since send_email_node "
                    "will attempt to create drafts or send real messages via the Gmail API."
                )
            if not os.path.exists(self.gmail_credentials_path):
                errors.append(
                    f"GMAIL_CREDENTIALS_PATH points to '{self.gmail_credentials_path}', but that "
                    "file doesn't exist. Download an OAuth Desktop-app client from Google Cloud "
                    "Console and point GMAIL_CREDENTIALS_PATH at it, or set DRY_RUN=true to keep "
                    "developing without live Gmail access."
                )

        if errors:
            message = "Configuration error(s) detected:\n" + "\n".join(f"  - {e}" for e in errors)
            print(message, file=sys.stderr)
            raise SystemExit(1)


def configure_logging(level: str) -> logging.Logger:
    numeric_level = getattr(logging, level, logging.INFO)

    root_logger = logging.getLogger()
    root_logger.setLevel(numeric_level)

    if not root_logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        formatter = logging.Formatter(
            fmt="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
        handler.setFormatter(formatter)
        root_logger.addHandler(handler)

    return logging.getLogger("cold_email_assistant")


def _warn_about_optional_integrations(settings: Settings, logger: logging.Logger) -> None:
    if settings.dry_run:
        return

    if not settings.apollo_api_key:
        logger.warning("APOLLO_API_KEY is not set - enrichment will fall back to simulated tech-stack data.")
    if not settings.clay_api_key or not settings.clay_webhook_url:
        logger.warning("CLAY_API_KEY / CLAY_WEBHOOK_URL not fully configured - enrichment will fall back to simulated hiring/news signals.")
    if settings.gmail_delivery_mode == "send":
        logger.warning("GMAIL_DELIVERY_MODE=send - outbound emails will be delivered directly with no draft safety net.")


settings = Settings()
settings.validate()
logger = configure_logging(settings.log_level)
_warn_about_optional_integrations(settings, logger)

logger.debug(
    "Configuration loaded (dry_run=%s, model=%s, delivery_mode=%s)",
    settings.dry_run,
    settings.openai_model,
    settings.gmail_delivery_mode,
)
