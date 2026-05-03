"""Scadable API client — talk to the Scadable cloud from your code.

The flip side of the controller SDK: where ``Controller`` + ``@on.message``
let your gateway *receive* commands, this module lets your application
*send* them. Any code outside the gateway (a script, an agent, a
service, a test) calls the cloud's public API to act on a fleet.

Example
-------

::

    from scadable.api import Client

    client = Client(api_key="sk_live_...")  # or env SCADABLE_API_KEY

    # Tell the chip's @on.message(command="set_temperature") handler to fire.
    result = client.send_command(
        gateway_id="gw-abc",
        command="set_temperature",
        payload={"value": 22.5},
    )
    print(result["status"])  # "completed" if the chip acked

The default base URL points at production (``https://api.scadable.com``).
Override with ``base_url=`` or env ``SCADABLE_API_URL`` for staging /
self-hosted clusters.

Auth is API key only — generated from the dashboard's API Keys panel.
Pass via constructor (``Client(api_key="...")``) or env
``SCADABLE_API_KEY``. The CLI's ``scadable login`` flow will eventually
write this to ``~/.config/scadable/config.toml``; until then it's
explicit.
"""

from .client import APIError, Client

__all__ = ["Client", "APIError"]
