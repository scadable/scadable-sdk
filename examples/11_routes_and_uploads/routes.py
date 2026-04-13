"""Cloud routes — where uploads and notifications go.

upload_route  — defines S3/Spaces destinations for file uploads
notify        — defines alert delivery targets (Slack, email, webhook)

Controllers call self.upload() and self.alert() — these routes
determine WHERE those calls deliver to.
"""
from scadable import upload_route, notify

# Photos uploaded to DO Spaces with 30-day retention
upload_route("high-temp-photos",
    destination = "s3",
    bucket      = "${S3_BUCKET}",
    prefix      = "photos/{date}/{device_id}/",
    ttl         = "30d",
)

# CSV data exports
upload_route("data-exports",
    destination = "s3",
    bucket      = "${S3_BUCKET}",
    prefix      = "exports/",
    ttl         = "1y",
)

# Alert notifications — Slack for warnings, email for critical
notify("ops-team",
    slack    = "${SLACK_WEBHOOK_URL}",
    severity = ["warning", "critical"],
)

notify("on-call",
    email    = ["oncall@acme.com"],
    severity = ["critical"],
)
