"""Cloud routes for multi-device example."""
from scadable import notify

notify("factory-ops",
    slack    = "${SLACK_WEBHOOK_URL}",
    severity = ["warning", "critical"],
)
