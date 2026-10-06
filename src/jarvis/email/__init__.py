"""Private foreground email read/prepare boundary."""

from .exports import LocalEmailExports
from .models import EmailDraft, EmailError, EmailMessage, EmailPreparation, EmailThread
from .service import EmailService, build_email_service

__all__ = [
    "EmailDraft",
    "EmailError",
    "EmailMessage",
    "EmailPreparation",
    "EmailService",
    "EmailThread",
    "LocalEmailExports",
    "build_email_service",
]
