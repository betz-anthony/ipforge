import importlib.util
from pathlib import Path

_spec = importlib.util.spec_from_file_location(
    "bench", Path(__file__).resolve().parents[2] / "scripts" / "bench.py")
bench = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(bench)


def test_percentiles_nearest_rank():
    samples = [float(x) for x in range(1, 101)]   # 1..100 ms
    p = bench.percentiles(samples)
    assert p["p50"] == 50.0
    assert p["p95"] == 95.0
    assert p["max"] == 100.0
    assert p["mean"] == 50.5


def test_percentiles_single_sample():
    p = bench.percentiles([7.0])
    assert p["p50"] == p["p95"] == p["max"] == p["mean"] == 7.0


def test_endpoints_cover_required_paths():
    paths = {path for (_lbl, _m, path) in bench.ENDPOINTS}
    assert any(p.startswith("/api/v1/addresses") for p in paths)
    assert any("/map" in p for p in paths)
    assert any(p.startswith("/api/v1/drift/scan") for p in paths)
    assert any(p.startswith("/api/v1/subnets") for p in paths)
