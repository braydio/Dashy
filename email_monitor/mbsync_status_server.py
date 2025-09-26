"""Expose Maildir unread counts via HTTP for Dashy email widgets.

The helper functions here periodically run ``mbsync`` to refresh Maildir
mailboxes and count unread messages.  Results are served as JSON so the main
Dashy instance can consume them through the CustomList widget.
"""
from __future__ import annotations

import argparse
import json
import os
import signal
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from threading import Event, Thread
from typing import Dict, Iterable, List, Optional

DEFAULT_MAILDIR = os.environ.get("MAILDIR", str(Path.home() / ".mail"))
DEFAULT_MBSYNC_COMMAND = os.environ.get("MBSYNC_COMMAND", "mbsync -a")
DEFAULT_BIND = os.environ.get("MAIL_STATUS_HOST", "127.0.0.1")
DEFAULT_PORT = int(os.environ.get("MAIL_STATUS_PORT", "8765"))


@dataclass
class MailboxStatus:
    """Snapshot of unread counts for a Maildir mailbox."""

    name: str
    unread: int


@dataclass
class SyncResult:
    """Summary data describing the outcome of an mbsync invocation."""

    timestamp: datetime
    command: str
    duration: float
    exit_code: int
    stderr: str


class MailStatusHandler(BaseHTTPRequestHandler):
    """HTTP handler that serializes the latest mail statistics."""

    def __init__(self, *args, status_provider=None, **kwargs):
        self._status_provider = status_provider
        super().__init__(*args, **kwargs)

    def do_GET(self) -> None:  # noqa: N802 - required by BaseHTTPRequestHandler
        """Return the most recent unread counts as JSON."""
        if self.path not in {"/", "/status"}:
            self.send_error(404, "Not Found")
            return

        payload = self._status_provider()
        body = json.dumps(payload, separators=(",", ":")).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args) -> None:  # noqa: A003 - same signature as parent
        """Silence default logging to keep stdout clean for systemd."""
        return


def enumerate_mailboxes(maildir: Path) -> Iterable[MailboxStatus]:
    """Yield unread counts for each mailbox within a Maildir tree."""
    for child in sorted(maildir.iterdir()):
        if not child.is_dir():
            continue
        new_dir = child / "new"
        if not new_dir.exists():
            continue
        unread = sum(1 for path in new_dir.glob("**/*") if path.is_file())
        yield MailboxStatus(name=child.name, unread=unread)


def collect_mail_status(maildir: Path) -> List[Dict[str, object]]:
    """Return mailbox statistics serialized for Dashy's CustomList widget."""
    timestamp = datetime.now(timezone.utc).isoformat()
    statuses = []
    for mailbox in enumerate_mailboxes(maildir):
        statuses.append(
            {
                "date": timestamp,
                "value": {
                    "text": f"{mailbox.name}: {mailbox.unread} unread",
                    "title": f"Mailbox '{mailbox.name}' unread count at {timestamp}",
                },
            }
        )
    return statuses


def run_mbsync(command: str, timeout: int) -> SyncResult:
    """Execute the mbsync command and summarize the results."""
    start = datetime.now(timezone.utc)
    process = subprocess.run(  # noqa: S603 - command comes from trusted config
        command,
        shell=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
        text=True,
        timeout=timeout,
    )
    duration = (datetime.now(timezone.utc) - start).total_seconds()
    return SyncResult(
        timestamp=start,
        command=command,
        duration=duration,
        exit_code=process.returncode,
        stderr=process.stderr.strip(),
    )


def build_payload(maildir: Path, last_sync: Optional[SyncResult]) -> List[Dict[str, object]]:
    """Compose widget payload including optional sync metadata."""
    payload = collect_mail_status(maildir)
    if last_sync is not None:
        payload.insert(
            0,
            {
                "date": last_sync.timestamp.isoformat(),
                "value": {
                    "text": f"Last sync: exit {last_sync.exit_code} in {last_sync.duration:.1f}s",
                    "title": last_sync.stderr or "mbsync completed without stderr",
                },
            },
        )
    return payload


def start_server(maildir: Path, refresh_interval: int, sync_command: Optional[str],
                 sync_timeout: int, host: str, port: int) -> None:
    """Start the HTTP server and periodically refresh mailbox statistics."""
    maildir = maildir.expanduser()
    if not maildir.exists():
        raise FileNotFoundError(f"Maildir '{maildir}' does not exist")

    last_sync: Optional[SyncResult] = None
    payload_cache: List[Dict[str, object]] = []
    payload_lock = Event()

    def refresh_loop() -> None:
        nonlocal last_sync, payload_cache
        while not stop_event.is_set():
            try:
                if sync_command:
                    last_sync = run_mbsync(sync_command, sync_timeout)
                payload_cache = build_payload(maildir, last_sync)
            except Exception as exc:  # noqa: BLE001 - surface unexpected issues
                timestamp = datetime.now(timezone.utc).isoformat()
                payload_cache = [
                    {
                        "date": timestamp,
                        "value": {
                            "text": "Email monitor error",
                            "title": repr(exc),
                        },
                    }
                ]
            finally:
                payload_lock.set()
                stop_event.wait(refresh_interval)

    def provide_status() -> List[Dict[str, object]]:
        payload_lock.wait()
        return payload_cache

    stop_event = Event()
    worker = Thread(target=refresh_loop, name="mbsync-refresh", daemon=True)
    worker.start()

    def handler(*args, **kwargs):
        MailStatusHandler(*args, status_provider=provide_status, **kwargs)

    server = HTTPServer((host, port), handler)

    def shutdown(signum, frame):  # noqa: D401
        """Gracefully stop the server when receiving a termination signal."""
        stop_event.set()
        server.shutdown()

    signal.signal(signal.SIGTERM, shutdown)
    signal.signal(signal.SIGINT, shutdown)

    try:
        server.serve_forever()
    finally:
        stop_event.set()
        worker.join()


def parse_args(argv: Optional[Iterable[str]] = None) -> argparse.Namespace:
    """Parse command line arguments for the email status utility."""
    parser = argparse.ArgumentParser(description="Serve Dashy-friendly mailbox stats")
    parser.add_argument(
        "--maildir",
        default=DEFAULT_MAILDIR,
        type=Path,
        help="Path to the Maildir root (defaults to $MAILDIR or ~/.mail)",
    )
    parser.add_argument(
        "--sync-command",
        default=DEFAULT_MBSYNC_COMMAND,
        help="Command used to refresh mail before counting (set empty to skip)",
    )
    parser.add_argument(
        "--sync-timeout",
        default=120,
        type=int,
        help="Maximum seconds to wait for the sync command",
    )
    parser.add_argument(
        "--refresh-interval",
        default=120,
        type=int,
        help="Seconds between mailbox scans",
    )
    parser.add_argument(
        "--host",
        default=DEFAULT_BIND,
        help="Address for the status server to bind to",
    )
    parser.add_argument(
        "--port",
        default=DEFAULT_PORT,
        type=int,
        help="Port for the status server",
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="Print a single JSON payload and exit instead of serving HTTP",
    )
    return parser.parse_args(argv)


def main(argv: Optional[Iterable[str]] = None) -> int:
    """Entry point for executing the monitor from the command line."""
    args = parse_args(argv)
    maildir: Path = args.maildir
    sync_cmd: Optional[str] = args.sync_command or None

    if args.once:
        last_sync = run_mbsync(sync_cmd, args.sync_timeout) if sync_cmd else None
        payload = build_payload(maildir, last_sync)
        json.dump(payload, sys.stdout, indent=2)
        sys.stdout.write("\n")
        return 0

    start_server(
        maildir=maildir,
        refresh_interval=args.refresh_interval,
        sync_command=sync_cmd,
        sync_timeout=args.sync_timeout,
        host=args.host,
        port=args.port,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
