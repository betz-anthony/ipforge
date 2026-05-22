"""Prometheus metrics endpoint.

Example Prometheus scrape configuration:

    scrape_configs:
      - job_name: ipforge
        metrics_path: /metrics
        authorization:
          type: Bearer
          credentials: ipfg_your_readonly_api_token
        static_configs:
          - targets: ['ipforge-api:8000']
"""
import ipaddress
from datetime import timedelta

from fastapi import APIRouter, Depends, Response
from prometheus_client import CONTENT_TYPE_LATEST, CollectorRegistry, generate_latest
from prometheus_client.core import GaugeMetricFamily
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.config import settings
from app.core.deps import get_current_user
from app.core.time import utcnow
from app.database import get_db
from app.models.address import IPAddress, AddressStatus
from app.models.cache import SyncStatus
from app.models.scan import Collision
from app.models.subnet import Subnet
from app.models.user import User

router = APIRouter()

_USED_STATUSES = (AddressStatus.assigned, AddressStatus.reserved, AddressStatus.discovered)


def _usable_total(cidr: str) -> int:
    """Usable host capacity of a CIDR, matching the subnet utilization rule."""
    net = ipaddress.ip_network(cidr, strict=False)
    if net.version == 6 or net.prefixlen >= 31:
        return net.num_addresses
    return max(1, net.num_addresses - 2)


class _IpamCollector:
    """prometheus_client collector — queries the DB at scrape time."""

    def __init__(self, db: Session):
        self.db = db

    def collect(self):
        db = self.db
        now = utcnow()

        subnets = db.query(Subnet).all()
        yield GaugeMetricFamily(
            "ipam_subnets_total", "Number of subnets", value=len(subnets)
        )

        addr_counts = dict(
            db.query(IPAddress.status, func.count(IPAddress.id))
            .group_by(IPAddress.status)
            .all()
        )
        addr_fam = GaugeMetricFamily(
            "ipam_addresses", "IP addresses by status", labels=["status"]
        )
        for status in AddressStatus:
            addr_fam.add_metric([status.value], addr_counts.get(status, 0))
        yield addr_fam

        used_counts = dict(
            db.query(IPAddress.subnet_id, func.count(IPAddress.id))
            .filter(IPAddress.status.in_(_USED_STATUSES))
            .group_by(IPAddress.subnet_id)
            .all()
        )
        used_fam = GaugeMetricFamily(
            "ipam_subnet_used_addresses", "Used addresses per subnet", labels=["subnet"]
        )
        total_fam = GaugeMetricFamily(
            "ipam_subnet_total_addresses", "Usable address capacity per subnet", labels=["subnet"]
        )
        util_fam = GaugeMetricFamily(
            "ipam_subnet_utilization_ratio", "Address utilization ratio per subnet", labels=["subnet"]
        )
        scan_fam = GaugeMetricFamily(
            "ipam_subnet_scan_age_seconds", "Seconds since the subnet was last scanned", labels=["subnet"]
        )
        for s in subnets:
            used = used_counts.get(s.id, 0)
            total = _usable_total(s.cidr)
            used_fam.add_metric([s.cidr], used)
            total_fam.add_metric([s.cidr], total)
            util_fam.add_metric([s.cidr], (used / total) if total else 0.0)
            scan_row = db.get(SyncStatus, f"scan:{s.id}")
            if scan_row is not None and scan_row.synced_at is not None:
                scan_fam.add_metric([s.cidr], (now - scan_row.synced_at).total_seconds())
        yield used_fam
        yield total_fam
        yield util_fam
        yield scan_fam

        age_fam = GaugeMetricFamily(
            "ipam_sync_age_seconds", "Seconds since the last provider sync", labels=["type"]
        )
        ok_fam = GaugeMetricFamily(
            "ipam_sync_ok", "1 if the last provider sync ended ok, else 0", labels=["type"]
        )
        for sync_type in ("dns", "dhcp"):
            row = db.get(SyncStatus, sync_type)
            if row is not None and row.synced_at is not None:
                age_fam.add_metric([sync_type], (now - row.synced_at).total_seconds())
            ok_fam.add_metric([sync_type], 1.0 if (row is not None and row.status == "ok") else 0.0)
        yield age_fam
        yield ok_fam

        open_collisions = (
            db.query(func.count(Collision.id))
            .filter(Collision.resolved.is_(False))
            .scalar()
        ) or 0
        yield GaugeMetricFamily(
            "ipam_open_collisions", "Number of unresolved collisions", value=open_collisions
        )

        stale = 0
        if settings.stale_reclaim_days > 0:
            cutoff = now - timedelta(days=settings.stale_reclaim_days)
            stale = (
                db.query(func.count(IPAddress.id))
                .filter(IPAddress.status.in_((AddressStatus.reserved, AddressStatus.assigned)))
                .filter(IPAddress.last_seen.isnot(None))
                .filter(IPAddress.last_seen < cutoff)
                .filter(
                    (IPAddress.reclaim_dismissed_until.is_(None))
                    | (IPAddress.reclaim_dismissed_until < now)
                )
                .scalar()
            ) or 0
        yield GaugeMetricFamily(
            "ipam_stale_addresses", "Number of stale IP addresses", value=stale
        )


@router.get("/metrics")
def metrics(
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> Response:
    registry = CollectorRegistry()
    registry.register(_IpamCollector(db))
    return Response(generate_latest(registry), media_type=CONTENT_TYPE_LATEST)
