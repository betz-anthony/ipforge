import re
import platform
import subprocess
import logging
from fastapi import APIRouter, HTTPException, Query

logger = logging.getLogger(__name__)
router = APIRouter()

_SAFE_HOST = re.compile(r'^[a-zA-Z0-9.\-:]+$')


@router.get("/ping")
def ping_host(host: str = Query(...)):
    if not _SAFE_HOST.match(host):
        raise HTTPException(400, "Invalid host")

    system = platform.system()
    if system == "Darwin":
        cmd = ["ping", "-c", "3", "-W", "1000", host]
    elif system == "Windows":
        cmd = ["ping", "-n", "3", host]
    else:
        cmd = ["ping", "-c", "3", "-W", "1", host]

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=12)
        output = result.stdout + result.stderr
    except FileNotFoundError:
        raise HTTPException(503, "ping not available in this environment")
    except subprocess.TimeoutExpired:
        return {"host": host, "reachable": False, "min_ms": None, "avg_ms": None, "max_ms": None, "loss_pct": 100}

    loss_m = re.search(r'(\d+)%\s+packet loss', output)
    loss_pct = int(loss_m.group(1)) if loss_m else 100
    reachable = loss_pct < 100

    # macOS: round-trip min/avg/max/stddev = X/X/X/X ms
    # Linux:  rtt min/avg/max/mdev = X/X/X/X ms
    rtt_m = re.search(r'(?:round-trip|rtt)\s+min/avg/max/\S+\s+=\s+([\d.]+)/([\d.]+)/([\d.]+)', output)
    if rtt_m:
        min_ms = float(rtt_m.group(1))
        avg_ms = float(rtt_m.group(2))
        max_ms = float(rtt_m.group(3))
    else:
        min_ms = avg_ms = max_ms = None

    return {
        "host": host,
        "reachable": reachable,
        "min_ms": min_ms,
        "avg_ms": avg_ms,
        "max_ms": max_ms,
        "loss_pct": loss_pct,
    }
