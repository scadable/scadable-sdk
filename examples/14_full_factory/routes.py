"""Full factory — cloud routes."""
from scadable import upload_route, notify

upload_route("photos",
    destination="s3", bucket="${S3_BUCKET}",
    prefix="photos/{date}/{device_id}/", ttl="30d")

upload_route("exports",
    destination="s3", bucket="${S3_BUCKET}",
    prefix="exports/", ttl="1y")

notify("ops", slack="${SLACK_WEBHOOK_URL}", severity=["warning", "critical"])
notify("oncall", email=["oncall@acme.com"], severity=["critical"])
