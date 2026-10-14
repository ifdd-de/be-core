"""The third-party files of the documentation pages are the published ones.

``docs_assets/assets.json`` names the npm package, version and SHA-256 of
every third-party file. A file changed by hand, or an update without a new
manifest, fails here.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import ifdd.be.core

ASSETS = Path(ifdd.be.core.__file__).parent / "docs_assets"
MANIFEST = json.loads((ASSETS / "assets.json").read_text(encoding="utf-8"))
OWN_DIRECTORY = "ifdd"


def test_every_listed_file_has_its_checksum():
    for package in MANIFEST["packages"]:
        for name, digest in package["files"].items():
            data = (ASSETS / name).read_bytes()
            assert hashlib.sha256(data).hexdigest() == digest, name


def test_every_third_party_file_is_listed():
    listed = {name for package in MANIFEST["packages"] for name in package["files"]}
    on_disk = {
        path.relative_to(ASSETS).as_posix()
        for path in ASSETS.rglob("*")
        if path.is_file() and path.parts[len(ASSETS.parts)] not in (OWN_DIRECTORY,)
        and path.name != "assets.json"
    }
    assert on_disk == listed


def test_license_texts_are_shipped():
    for package in MANIFEST["packages"]:
        directory = ASSETS / package["directory"]
        assert (directory / "LICENSE").is_file(), package["name"]
    # Apache-2.0, section 4 (d): the NOTICE file goes along.
    assert (ASSETS / "swagger-ui" / "NOTICE").is_file()


def test_pinned_versions():
    versions = {package["name"]: package["version"] for package in MANIFEST["packages"]}
    assert versions == {"swagger-ui-dist": "5.33.0", "redoc": "2.5.4"}
