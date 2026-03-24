# Chaos Runbook

This runbook explains how to execute the demo chaos scenarios in the AIOps environment.

## Location

Run all commands from:

```bash
cd /Users/ajithsai.kusal/Desktop/AIOps/demo/tools
```

## Pre-check

Make sure the stack is already running:

```bash
cd /Users/ajithsai.kusal/Desktop/AIOps
docker compose up -d
```

Then move back to the tools directory:

```bash
cd /Users/ajithsai.kusal/Desktop/AIOps/demo/tools
```

## Always Start With Reset

Before a demo, reset both DB and gateway chaos state:

```bash
sh reset-db-proxy.sh
sh reset-gateway-proxy.sh
```

These scripts now recreate missing Toxiproxy proxies automatically.

## 1. DB Latency

Inject latency into the shared database path used by all backend apps:

```bash
sh set-db-latency.sh 3000 250
```

Meaning:

- `3000` = latency in milliseconds
- `250` = jitter in milliseconds

Expected effect:

- all apps slow down
- frontend gets slower
- latency alerts can fire

Recover:

```bash
sh reset-db-proxy.sh
```

## 2. DB Hard Failure

Cut the database path by injecting a timeout toxic:

```bash
sh cut-db-traffic.sh
```

Expected effect:

- DB-backed calls fail or hang
- frontend shows errors
- error alerts can fire

Recover:

```bash
sh reset-db-proxy.sh
```

## 3. Gateway To App Latency

Inject latency between the gateway and backend apps.

All services:

```bash
sh set-gateway-latency.sh all 2000 250
```

Single service:

```bash
sh set-gateway-latency.sh orders 2000 250
sh set-gateway-latency.sh inventory 2000 250
sh set-gateway-latency.sh billing 2000 250
```

Expected effect:

- gateway upstream latency increases
- frontend slows down
- apps may still be healthy if accessed directly

Recover:

```bash
sh reset-gateway-proxy.sh
```

## 4. Gateway To App Hard Cut

Cut traffic between gateway and backend services.

All services:

```bash
sh cut-gateway-traffic.sh all
```

Single service:

```bash
sh cut-gateway-traffic.sh orders
sh cut-gateway-traffic.sh inventory
sh cut-gateway-traffic.sh billing
```

Expected effect:

- gateway returns errors
- frontend can fail for one or more backend sections

Recover:

```bash
sh reset-gateway-proxy.sh
```

## 5. Stop / Start Entire Services

Stop the demo database:

```bash
sh stop-demo-service.sh db
```

Start it again:

```bash
sh start-demo-service.sh db
```

Stop one backend service:

```bash
sh stop-demo-service.sh app-orders
sh stop-demo-service.sh app-inventory
sh stop-demo-service.sh app-billing
```

Start it again:

```bash
sh start-demo-service.sh app-orders
sh start-demo-service.sh app-inventory
sh start-demo-service.sh app-billing
```

## 6. Continuous Traffic During Chaos

Run mixed traffic:

```bash
sh run-demo-traffic.sh mixed
```

Read-only traffic:

```bash
sh run-demo-traffic.sh read
```

Write-flow traffic:

```bash
sh run-demo-traffic.sh write
```

Example with limits:

```bash
ITERATIONS=20 SLEEP_BETWEEN=1 sh run-demo-traffic.sh mixed
```

## Recommended Demo Sequence

Terminal 1:

```bash
cd /Users/ajithsai.kusal/Desktop/AIOps/demo/tools
sh reset-db-proxy.sh
sh reset-gateway-proxy.sh
sh run-demo-traffic.sh mixed
```

Terminal 2:

```bash
cd /Users/ajithsai.kusal/Desktop/AIOps/demo/tools
sh set-db-latency.sh 3000 250
```

Then:

- observe frontend slowdown
- watch Prometheus / Alertmanager
- open AIOps recommendations
- let AiDE analyze RCA

Recover:

```bash
sh reset-db-proxy.sh
sh reset-gateway-proxy.sh
```

## If You See 404 Or 502

Run:

```bash
sh reset-db-proxy.sh
sh reset-gateway-proxy.sh
```

Reason:

- `404` from Toxiproxy usually means the required proxy was missing
- `502` in the UI usually means gateway was routing through a missing or broken proxy

The reset scripts now self-heal the proxy definitions before removing toxics.
