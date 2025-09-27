# Status Endpoint Microservice

This lightweight Flask application exposes systemd unit health for headless services
so that Dashy can poll them via HTTP.

## Usage

1. Install the Python dependency on your host (or within a dedicated virtualenv):

   ```bash
   pip install flask
   ```

2. Start the service on the host that manages the systemd units:

   ```bash
   STATUS_API_TOKEN="choose-a-strong-token" \
   STATUS_API_PORT=5055 \
   python3 systemd_status_server.py
   ```

   The server listens on `0.0.0.0` by default. Restrict exposure with
   your firewall if the endpoint should remain internal.

3. Point Dashy at the service by setting the following variables in `.env`:

   ```bash
   STATUS_API_BASE=http://192.168.1.198:5055/status
   STATUS_API_TOKEN=choose-a-strong-token
   ```

4. Dashy will include the token as the `X-Status-Token` header for Windscribe
   and Spotifyd status checks. The API responds with HTTP 200 when the unit is
   active and HTTP 503 otherwise.

## Customizing Services

The script limits exposure to the units listed in `ALLOWED_SERVICES`. To add or
remove services, edit `ALLOWED_SERVICES` in
`systemd_status_server.py` and restart the server.

