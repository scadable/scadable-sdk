"""Full factory — local storage configuration."""
from scadable.storage import data, files, state

sensor_data   = data("128MB")
camera_roll   = files("512MB", ttl="7d")
ml_results    = data("64MB")
device_config = state("1MB")
