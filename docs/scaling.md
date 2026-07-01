# IPForge Scale & Performance

## Methodology
- **Database:** PostgreSQL 16 (the production engine), schema built by the real
  Alembic migrations — so the indexes match a production deployment.
- **Measurement:** single-user, serial HTTP latency against a running API. Each
  endpoint is warmed up, then timed for N iterations; we report p50 / p95 / max in
  milliseconds. Times are full HTTP round trips measured with a monotonic clock.
- **Not measured here:** concurrent throughput, and the live ping-scan sweep (which
  is network-bound, not database-bound).
- **Reference rig:** Intel Core i7-8700B (6 cores / 12 threads, 3.2 GHz), 32 GB RAM,
  SSD, PostgreSQL 16 in a local container. Your numbers will differ — reproduce below.
- **Reproduce:** `scripts/bench-run.sh --all` (see the last section).

Two kinds of path are reported separately, because they answer different questions:
- **Interactive reads** — the API calls a user waits on (address list, search, subnet
  map, drift views). These need to feel instant.
- **Batch reconciliation** — a full drift detect pass over the whole dataset. This is
  a scheduled / on-demand background job, not a per-request operation.

## Interactive read latency (ms)

### 100,000 addresses / 500 subnets
| Endpoint | p50 | p95 | max |
|----------|----:|----:|----:|
| Address list (paginated) | 18.2 | 20.2 | 20.8 |
| Address search (`?q=`)   | 144.7 | 154.8 | 165.7 |
| Address deep page (offset 90k) | 36.3 | 45.7 | 54.9 |
| Subnet list (with utilization stats) | 311.6 | 324.3 | 341.8 |
| Subnet heatmap (`/map`)  | 20.8 | 27.3 | 34.2 |
| Drift list | 5.9 | 6.8 | 6.9 |
| Drift stats | 6.3 | 7.1 | 9.4 |

### 50,000 addresses / 300 subnets
| Endpoint | p50 | p95 | max |
|----------|----:|----:|----:|
| Address list (paginated) | 14.6 | 18.0 | 18.3 |
| Address search (`?q=`)   | 141.1 | 147.3 | 172.4 |
| Address deep page | 41.7 | 45.0 | 50.1 |
| Subnet list (with utilization stats) | 137.2 | 192.6 | 197.9 |
| Subnet heatmap (`/map`)  | 16.8 | 19.3 | 19.4 |
| Drift list | 6.0 | 6.8 | 6.9 |
| Drift stats | 6.1 | 6.8 | 10.4 |

### 10,000 addresses / 100 subnets
| Endpoint | p50 | p95 | max |
|----------|----:|----:|----:|
| Address list (paginated) | 13.1 | 15.1 | 17.7 |
| Address search (`?q=`)   | 38.3 | 45.6 | 47.4 |
| Address deep page | 13.8 | 16.6 | 18.9 |
| Subnet list (with utilization stats) | 38.5 | 67.8 | 88.3 |
| Subnet heatmap (`/map`)  | 13.9 | 15.0 | 15.3 |
| Drift list | 6.3 | 9.0 | 10.1 |
| Drift stats | 6.1 | 7.3 | 7.5 |

## Batch reconciliation (full drift detect)

A full drift detect pass compares every address across IPAM, DNS, DHCP, and live
state. It scales roughly linearly with dataset size and is meant to run on a
schedule or on demand — not on the request path.

| Dataset | Full detect pass (p50) |
|---------|-----------------------:|
| 10k / 100 subnets  | ~11 s |
| 50k / 300 subnets  | ~57 s |
| 100k / 500 subnets | ~112 s |

## Supported ceiling

IPForge is validated to **100,000 addresses across 500 subnets** on the reference
rig with interactive read paths staying well under half a second at p95:

- Address list, deep pagination, subnet heatmap, and drift views: **under ~50 ms** p95.
- Address search and the utilization-annotated subnet list are the heaviest reads:
  **~155 ms and ~325 ms** p95 respectively at 100k.

Everyday use at 100k addresses stays interactive. Larger datasets are likely workable
but are not yet validated. Full drift detect is a batch job — budget ~2 minutes at
100k and run it scheduled, not per-request.

## Reproduce it yourself

    docker compose up -d db     # or let the bench spin its own Postgres
    scripts/bench-run.sh --all  # seeds 10k/50k/100k, benchmarks each, writes JSON

Results land in `bench-results-<tier>.json`. The benchmark stands up a dedicated
PostgreSQL 16 container, seeds it with the real schema, serves the API with the
background scan/discovery loops disabled (so the dataset stays still), and times each
endpoint serially. Numbers are hardware-dependent — run it on your own hardware for a
figure you can trust.
