#!/usr/bin/env python3
"""Serial single-user latency benchmark for the IPForge API.

Times the key read/scan endpoints against a running API and reports p50/p95/max.
Postgres-backed, single-user — see docs/scaling.md for methodology. Requires an
admin ipfg_ token.

Usage:
    python3 scripts/bench.py --base-url http://localhost:8000 --token ipfg_... \
        --tier 100k --iterations 40
"""
import argparse
import json
import math
import time
import urllib.request

# (label, method, path) — {sid} is filled with subnet id 1.
ENDPOINTS = [
    ("addresses_list",   "GET",  "/api/addresses?limit=50&offset=0"),
    ("addresses_search", "GET",  "/api/addresses?q=host-1&limit=50"),
    ("addresses_deep",   "GET",  "/api/addresses?limit=50&offset=90000"),
    ("subnets_list",     "GET",  "/api/subnets"),
    ("subnet_map",       "GET",  "/api/subnets/1/map"),
    ("drift_list",       "GET",  "/api/drift"),
    ("drift_stats",      "GET",  "/api/drift/stats"),
    ("drift_scan",       "POST", "/api/drift/scan"),
]
# Heavy endpoints run fewer iterations.
ITER_OVERRIDE = {"drift_scan": 5}


def percentiles(samples: list[float]) -> dict:
    s = sorted(samples)
    n = len(s)

    def nearest_rank(pct: float) -> float:
        k = max(1, math.ceil(pct / 100.0 * n))
        return s[k - 1]

    return {
        "p50": round(nearest_rank(50), 2),
        "p95": round(nearest_rank(95), 2),
        "max": round(s[-1], 2),
        "mean": round(sum(s) / n, 2),
    }


def _call(base_url: str, token: str, method: str, path: str) -> float:
    req = urllib.request.Request(base_url + path, method=method)
    req.add_header("Authorization", f"Bearer {token}")
    t0 = time.monotonic()
    with urllib.request.urlopen(req) as resp:
        if resp.status >= 300:
            raise RuntimeError(f"{method} {path} -> HTTP {resp.status}")
        resp.read()
    return (time.monotonic() - t0) * 1000.0  # ms


def run(base_url: str, token: str, iterations: int) -> dict:
    results = {}
    for label, method, path in ENDPOINTS:
        iters = ITER_OVERRIDE.get(label, iterations)
        for _ in range(3):            # warm up
            _call(base_url, token, method, path)
        samples = [_call(base_url, token, method, path) for _ in range(iters)]
        results[label] = percentiles(samples)
    return results


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-url", default="http://localhost:8000")
    ap.add_argument("--token", required=True)
    ap.add_argument("--tier", default="adhoc")
    ap.add_argument("--iterations", type=int, default=40)
    args = ap.parse_args()

    results = run(args.base_url, args.token, args.iterations)
    out = f"bench-results-{args.tier}.json"
    with open(out, "w") as fh:
        json.dump({"tier": args.tier, "results": results}, fh, indent=2)

    print(f"{'endpoint':<18}{'p50':>8}{'p95':>8}{'max':>8}  (ms)")
    for label, p in results.items():
        print(f"{label:<18}{p['p50']:>8}{p['p95']:>8}{p['max']:>8}")
    print(f"\nWrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
