"""Cloud route definitions for uploads and notifications."""

from __future__ import annotations

_upload_routes: dict[str, dict] = {}
_notify_targets: dict[str, dict] = {}


def upload_route(
    name: str, *, destination: str = "s3", bucket: str = "", prefix: str = "", ttl: str = ""
) -> None:
    """Define a cloud storage destination for file uploads."""
    _upload_routes[name] = {
        "destination": destination,
        "bucket": bucket,
        "prefix": prefix,
        "ttl": ttl,
    }


def notify(
    name: str,
    *,
    slack: str = "",
    email: list[str] | None = None,
    webhook: str = "",
    severity: list[str] | None = None,
) -> None:
    """Define a notification target for alerts."""
    _notify_targets[name] = {
        "slack": slack,
        "email": email or [],
        "webhook": webhook,
        "severity": severity or ["critical"],
    }
