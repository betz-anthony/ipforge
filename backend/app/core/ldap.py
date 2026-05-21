import logging
import ldap3
from app.config import settings

logger = logging.getLogger(__name__)


def _make_server() -> ldap3.Server:
    return ldap3.Server(
        settings.ldap_host,
        port=settings.ldap_port,
        use_ssl=settings.ldap_use_ssl,
        get_info=ldap3.NONE,
    )


def _group_role(user_dn: str) -> str | None:
    """Return role from group membership, or None if no groups configured."""
    group_map = [
        ("admin",    settings.ldap_group_admin),
        ("operator", settings.ldap_group_operator),
        ("readonly", settings.ldap_group_readonly),
    ]
    configured = [(role, dn) for role, dn in group_map if dn]
    if not configured:
        return None

    server = _make_server()
    for role, group_dn in configured:
        try:
            conn = ldap3.Connection(
                server,
                user=settings.ldap_bind_dn,
                password=settings.ldap_bind_password,
                auto_bind=False,
            )
            if not conn.bind():
                logger.warning("LDAP service bind failed during group check")
                return None
            conn.search(
                group_dn,
                f"(member={ldap3.utils.conv.escape_filter_chars(user_dn)})",
                search_scope=ldap3.BASE,
                attributes=["cn"],
            )
            if conn.entries:
                return role
        except Exception as exc:
            logger.warning("LDAP group check error for %s: %s", group_dn, exc)
    return settings.ldap_default_role


def authenticate_ldap(username: str, password: str) -> str | None:
    """Authenticate username/password against LDAP. Returns role string or None."""
    if not settings.ldap_enabled:
        return None

    # A bind with a DN but empty password performs an unauthenticated
    # (anonymous) bind that many LDAP servers accept — reject empty
    # credentials so an empty password can never authenticate an account.
    if not username or not password:
        return None

    server = _make_server()
    try:
        svc = ldap3.Connection(
            server,
            user=settings.ldap_bind_dn,
            password=settings.ldap_bind_password,
            auto_bind=False,
        )
        if not svc.bind():
            logger.error("LDAP service bind failed")
            return None

        user_filter = settings.ldap_user_filter.format(
            username=ldap3.utils.conv.escape_filter_chars(username)
        )
        svc.search(settings.ldap_base_dn, user_filter, attributes=["dn"])
        if not svc.entries:
            logger.debug("LDAP user not found: %s", username)
            return None
        user_dn = svc.entries[0].entry_dn

        usr = ldap3.Connection(server, user=user_dn, password=password, auto_bind=False)
        if not usr.bind():
            logger.debug("LDAP password check failed for %s", username)
            return None

        role = _group_role(user_dn)
        return role if role is not None else settings.ldap_default_role

    except Exception as exc:
        logger.error("LDAP authentication error: %s", exc)
        return None
