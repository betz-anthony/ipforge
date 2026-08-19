"""DATABASE_URL assembly — passwords with URL-reserved characters.

Regression: the URL used to be interpolated in docker-compose.yml as
postgresql://ipam:${DB_PASSWORD}@db:5432/ipam, so a password containing "@"
ended the userinfo section early and the host was parsed as "<tail>@db".
"""

import pytest
from sqlalchemy.engine import make_url

from app.config import Settings


@pytest.fixture(autouse=True)
def _no_database_url(monkeypatch):
    # conftest sets DATABASE_URL=sqlite:///:memory: process-wide; drop it so
    # the assembly path is what these tests exercise.
    monkeypatch.delenv("DATABASE_URL", raising=False)
    for key in ("DB_USER", "DB_PASSWORD", "DB_HOST", "DB_PORT", "DB_NAME"):
        monkeypatch.delenv(key, raising=False)


def _settings(**kwargs) -> Settings:
    # _env_file=None so a developer's local .env cannot influence the result.
    return Settings(_env_file=None, **kwargs)


@pytest.mark.parametrize("password", [
    "Passw0rd@k32026",
    "p@ss:w/ord?x#y",
    "plain",
    "100%sure",
    "sp ace",
])
def test_password_survives_url_round_trip(password):
    url = make_url(_settings(db_password=password, db_host="db").database_url)
    assert url.password == password
    assert url.host == "db"
    assert url.username == "ipam"


def test_parts_are_used_when_database_url_is_unset():
    s = _settings(db_user="u", db_password="p", db_host="h", db_port=6543, db_name="n")
    assert s.database_url == "postgresql://u:p@h:6543/n"


def test_explicit_database_url_is_used_verbatim():
    # Tests and external/managed databases rely on this override.
    s = _settings(database_url="sqlite:///:memory:", db_password="ignored@me")
    assert s.database_url == "sqlite:///:memory:"


def test_username_is_encoded_too():
    url = make_url(_settings(db_user="DOMAIN\\svc", db_password="x").database_url)
    assert url.username == "DOMAIN\\svc"
