"""Expose systemd unit health via a lightweight HTTP API for Dashy status checks."""

from __future__ import annotations

import os
import subprocess
from typing import Dict

from flask import Flask, abort, jsonify, request

ALLOWED_SERVICES: Dict[str, str] = {
    "windscribe": "openvpn-client@windscribe.service",
    "spotifyd": "spotifyd.service",
}

DEFAULT_HOST = "0.0.0.0"
DEFAULT_PORT = int(os.getenv("STATUS_API_PORT", "5055"))
TOKEN_ENV_VAR = "STATUS_API_TOKEN"
TOKEN_HEADER = "X-Status-Token"

app = Flask(__name__)


def _require_token() -> None:
    """Validate request authorization token when configured."""
    token = os.getenv(TOKEN_ENV_VAR)
    if not token:
        return
    provided = request.headers.get(TOKEN_HEADER)
    if provided != token:
        abort(401, description="Missing or invalid status token")


def _systemctl_is_active(unit: str) -> subprocess.CompletedProcess[str]:
    """Run ``systemctl is-active`` for the provided unit and return the completed process."""
    return subprocess.run(
        ["systemctl", "is-active", unit],
        check=False,
        capture_output=True,
        text=True,
        timeout=8,
    )


@app.route("/status/systemd/<service>", methods=["GET"])
def systemd_status(service: str):
    """Return JSON describing the active state of the requested systemd unit."""
    _require_token()
    unit = ALLOWED_SERVICES.get(service)
    if unit is None:
        abort(404, description="Unknown service")

    try:
        result = _systemctl_is_active(unit)
    except subprocess.SubprocessError as err:
        return (
            jsonify(
                {
                    "service": service,
                    "unit": unit,
                    "active": False,
                    "state": "unknown",
                    "error": str(err),
                }
            ),
            500,
        )

    state = (result.stdout or result.stderr).strip() or "unknown"
    active = result.returncode == 0
    status_code = 200 if active else 503
    return (
        jsonify(
            {
                "service": service,
                "unit": unit,
                "active": active,
                "state": state,
            }
        ),
        status_code,
    )


@app.route("/status/health", methods=["GET"])
def healthcheck():
    """Simple readiness endpoint."""
    _require_token()
    return jsonify({"status": "ok", "services": list(ALLOWED_SERVICES)}), 200


if __name__ == "__main__":
    app.run(host=DEFAULT_HOST, port=DEFAULT_PORT)
