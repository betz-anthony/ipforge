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
| Address list (paginated) | 17.4 | 22.7 | 25.3 |
| Address search (`?q=`)   | 142.8 | 149.7 | 151.2 |
| Address deep page (offset 90k) | 36.2 | 38.4 | 38.6 |
| Subnet list (with utilization stats) | 304.0 | 331.3 | 347.8 |
| Subnet heatmap (`/map`)  | 21.3 | 23.3 | 23.6 |
| Drift list | 6.1 | 6.9 | 7.1 |
| Drift stats | 6.6 | 7.7 | 8.1 |

### 50,000 addresses / 300 subnets
| Endpoint | p50 | p95 | max |
|----------|----:|----:|----:|
| Address list (paginated) | 15.2 | 18.1 | 18.8 |
| Address search (`?q=`)   | 141.5 | 152.1 | 161.6 |
| Address deep page (offset 45k) | 25.7 | 27.8 | 29.1 |
| Subnet list (with utilization stats) | 140.2 | 196.3 | 205.3 |
| Subnet heatmap (`/map`)  | 17.3 | 19.3 | 20.0 |
| Drift list | 5.9 | 6.9 | 10.9 |
| Drift stats | 6.3 | 7.5 | 8.5 |

### 10,000 addresses / 100 subnets
| Endpoint | p50 | p95 | max |
|----------|----:|----:|----:|
| Address list (paginated) | 13.1 | 15.7 | 16.5 |
| Address search (`?q=`)   | 39.9 | 53.0 | 65.4 |
| Address deep page (offset 9k) | 18.1 | 22.3 | 24.4 |
| Subnet list (with utilization stats) | 39.3 | 58.1 | 97.6 |
| Subnet heatmap (`/map`)  | 14.0 | 16.2 | 17.0 |
| Drift list | 5.8 | 7.0 | 9.5 |
| Drift stats | 6.3 | 7.7 | 8.7 |

## Batch reconciliation (full drift detect)

A full drift detect pass compares every address across IPAM, DNS, DHCP, and live
state. It scales roughly linearly with dataset size and is meant to run on a
schedule or on demand — not on the request path.

| Dataset | Full detect pass (p50) |
|---------|-----------------------:|
| 10k / 100 subnets  | ~11 s |
| 50k / 300 subnets  | ~56 s |
| 100k / 500 subnets | ~117 s |

## Supported ceiling

IPForge is validated to **100,000 addresses across 500 subnets** on the reference
rig with interactive read paths staying under ~350 ms at p95:

- Address list, deep pagination, subnet heatmap, and drift views: **under ~40 ms** p95.
- Address search (substring match) is **~150 ms** p95.
- The utilization-annotated subnet list is the heaviest read at **~330 ms** p95; it
  computes per-subnet usage across all 500 subnets.

Everyday use at 100k addresses stays interactive. Larger datasets are likely workable
but are not yet validated. Full drift detect is a batch job — budget ~2 minutes at
100k and run it scheduled, not per-request.

## Reproduce it yourself

    scripts/bench-run.sh --all   # seeds 10k/50k/100k, benchmarks each, writes JSON

Results land in `bench-results-<tier>.json`. The benchmark stands up a dedicated
PostgreSQL 16 container, seeds it with the real schema, serves the API with the
background scan/discovery loops disabled (so the dataset stays still), and times each
endpoint serially. Numbers are hardware-dependent — run it on your own hardware for a
figure you can trust.
