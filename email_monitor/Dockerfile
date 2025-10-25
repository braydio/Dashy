FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    MAIL_STATUS_HOST=0.0.0.0 \
    MAIL_STATUS_PORT=8765 \
    MBSYNC_COMMAND="mbsync -a"

# Install isync (mbsync) and minimal tools
RUN apt-get update \
    && apt-get install -y --no-install-recommends isync ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY mbsync_status_server.py /app/

EXPOSE 8765

# Default command uses env for host/port and sync command
CMD ["python", "-u", "mbsync_status_server.py"]

