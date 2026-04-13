"""Local storage for multi-device correlation."""
from scadable.storage import data, state

sensor_data = data("128MB")
device_config = state("1MB")
