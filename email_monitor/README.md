Email Monitor Service
=====================

Containerized HTTP service exposing Maildir unread counts for Dashy.

How it works
- Periodically runs `mbsync -a` (configurable) to refresh mail.
- Counts unread messages in each Maildir mailbox.
- Serves a simple JSON list at `/status` for Dashy's Custom List widget.

Run on a separate machine
1) Edit `email_monitor/docker-compose.yml` and set the left side of the volume
   to your Maildir path, e.g. `/home/<user>/.mail:/mail`.
2) Start the service:
   docker compose -f email_monitor/docker-compose.yml up --build -d
3) Ensure the host firewall allows inbound TCP 8765.
4) In your Dashy `.env` (on the Dashy host), set:
   MAIL_STATUS_ENDPOINT=http://192.168.1.237:8765/status

Environment variables
- `MAIL_STATUS_HOST` (default `0.0.0.0`) – bind address
- `MAIL_STATUS_PORT` (default `8765`) – listen port
- `MAILDIR` (default `/mail`) – path to Maildir root
- `MBSYNC_COMMAND` (default `mbsync -a`) – command to refresh mail
  - Set to empty to skip syncing and just count

Manual test
curl http://192.168.1.237:8765/status

