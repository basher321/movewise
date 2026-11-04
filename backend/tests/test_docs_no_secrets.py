"""g08: the buyer guides exist and contain no real password, key or token."""

import re
from pathlib import Path

import pytest

from conftest import PROJECT_DIR

DOCS = [PROJECT_DIR / "docs" / "INSTALL.md", PROJECT_DIR / "docs" / "UPDATE.md"]

# A placeholder is written <like this>; anything else in these places counts as a real value.
_URL_PASSWORD = re.compile(r"://[^\s:/@]+:([^\s@]+)@")
_ASSIGNED_SECRET = re.compile(r"\b[A-Z_]*(?:PASSWORD|SECRET|TOKEN|KEY)[A-Z_]*=([^\s`|]+)")
_LICENCE_KEY = re.compile(r"\bMW1\.[A-Za-z0-9_-]{8,}")
_LONG_RANDOM = re.compile(r"(?<![A-Za-z0-9+/_=-])(?=[A-Za-z0-9+/_=-]*\d)(?=[A-Za-z0-9+/_=-]*[A-Za-z])[A-Za-z0-9+/_=-]{24,}")


def _placeholder(value: str) -> bool:
    return value.startswith("<")


def _problems(text: str) -> list[str]:
    found = [m.group(0) for m in _LICENCE_KEY.finditer(text)]
    found += [m.group(0) for m in _LONG_RANDOM.finditer(text)]
    found += [m.group(0) for m in _URL_PASSWORD.finditer(text) if not _placeholder(m.group(1))]
    found += [m.group(0) for m in _ASSIGNED_SECRET.finditer(text) if not _placeholder(m.group(1))]
    return found


@pytest.mark.parametrize("path", DOCS, ids=lambda p: p.name)
def test_guide_exists_without_secrets(path: Path) -> None:
    assert path.is_file()
    assert _problems(path.read_text(encoding="utf-8")) == []


def test_the_check_finds_real_values() -> None:
    assert _problems("postgresql://movewise_app:Real-pass1@localhost/movewise")
    assert _problems("SETUP_TOKEN=4f9c2a7e1b")
    assert _problems("MW1.eyJob2xkZXIiOiJ4In0.c2ln")
    assert _problems("Zz9Yy8Xx7Ww6Vv5Uu4Tt3Ss2Rr1Qq0")
    assert not _problems("postgresql+psycopg://movewise_app:<app password>@localhost:5432/movewise")
    assert not _problems("SETUP_TOKEN=<fill in> and /opt/movewise/deploy/movewise-notify.service")
