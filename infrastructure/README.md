# infrastructure/

Observability for CatetIn: **Grafana Alloy** collecting logs/metrics/traces,
**Tecnativa docker-socket-proxy** standing between Alloy and the Docker socket,
and **Grafana Cloud** as the managed backend. Source of truth for the decisions
below is the "Observability — Keputusan & Implementasi" doc in Outline.

```
deployment/     production: Alloy -> Grafana Cloud (needs .env)
development/    local: Alloy -> single-binary Loki + Grafana (no credentials)
```

The root `compose.yaml` is untouched and still runs the API on its own. These
files describe the API *plus* its telemetry.

## Quick start

```bash
# local, no Grafana Cloud account needed
make infra-dev-up      # Grafana :3001, Loki :3100, Alloy UI :12345, API :8000
make obs-check         # is the collector actually up?
make infra-dev-down

# production
cp infrastructure/deployment/.env.example infrastructure/deployment/.env
$EDITOR infrastructure/deployment/.env      # instance ID + token + 3 URLs
make infra-up
make infra-logs        # follow Alloy
```

Run one stack at a time — they collide on host ports 8000 and 12345.

## Why the socket proxy

`/var/run/docker.sock` is root on the host. Alloy only needs to *list*
containers and *read* their logs, so it never gets the socket: it talks to
`tcp://dockerproxy:2375`, and the proxy is an HAProxy that allows
`CONTAINERS=1` and leaves everything else (AUTH, SECRETS, EXEC, BUILD, COMMIT,
IMAGES, POST) revoked. A compromised Alloy can read; it cannot act.

Port 2375 lives only on the internal `obs-net` bridge and is never published.
If you ever see `unix:///var/run/docker.sock` in an `.alloy` file, that is a
regression.

## The two telemetry paths

1. **Container stdout** — `discovery.docker` + `loki.source.docker` tail every
   container through the proxy. Nothing in the app is required for this.
2. **Application events** — the app's `ObservabilityPort` posts OTLP/HTTP to
   `alloy:4318` (`/v1/logs`, `/v1/metrics`, `/v1/traces`), and Alloy forwards to
   Grafana Cloud's OTLP gateway. **Only Alloy holds Grafana Cloud
   credentials** — the API never sees them.

   Turn it on with `CATETIN_OBSERVABILITY_BACKEND=grafana_cloud` and
   `CATETIN_OTLP_ENDPOINT=http://alloy:4318` (both compose files already do).
   Other values: `stdout` (JSON lines, picked up by path 1) and `null`
   (default — off, and what the test suite uses).

In dev, metrics and traces are dropped at the receiver: there is no local Mimir
or Tempo to send them to. Logs flow end to end, which is what the smoke test is
for.

## Verifying the loop

```bash
make infra-dev-up
curl -s localhost:8000/health                       # generate some traffic
open http://localhost:3001                          # Grafana, Loki pre-provisioned
#   {app="catetin"}                 <- container stdout
#   {service_name="catetin"}        <- OTLP events from ObservabilityPort
```

Alloy's own UI at <http://localhost:12345> shows every component's health and
is the fastest way to see *why* nothing is arriving.

## Before the first real deploy

- **Pin the image tags.** `grafana/alloy:latest` and
  `tecnativa/docker-socket-proxy:latest` follow the design doc, but a
  production host should pin digests.
- **Check `env()`.** Alloy ≥1.5 also spells it `sys.env()`. If a future image
  drops the old alias, the credential lines in `deployment/alloy/config.alloy`
  are the only thing to change — Alloy fails loudly at startup, it does not
  start half-configured.
- **journald** needs `/var/log/journal` to exist on the host and Alloy to run
  as root (both already set in `deployment/compose.yaml`). Drop the
  `loki.source.journald` block if the API only ever runs in Docker.
