"""Fail if the built wheel lacks a file of the documentation pages.

The /docs and /redoc pages (ifdd.be.core.docs_ui) serve Swagger UI and
ReDoc from the package itself. A wheel without them still imports and
passes every test of a source checkout, but its pages stay empty; the
instances install the wheel, not the source.
"""

import glob
import json
import sys
import zipfile

PREFIX = "ifdd/be/core/docs_assets/"
OWN_FILES = ("ifdd/swagger-init.js", "ifdd/docs.css")


def main() -> int:
    wheels = sorted(glob.glob("dist/*.whl"))
    if not wheels:
        print("No wheel found in dist/", file=sys.stderr)
        return 1

    wheel = zipfile.ZipFile(wheels[-1])
    names = set(wheel.namelist())
    if PREFIX + "assets.json" not in names:
        print(f"{wheels[-1]}: {PREFIX}assets.json is missing", file=sys.stderr)
        return 1
    manifest = json.loads(wheel.read(PREFIX + "assets.json"))
    expected = [name for package in manifest["packages"] for name in package["files"]]
    expected += OWN_FILES
    missing = [name for name in expected if PREFIX + name not in names]
    if missing:
        print(f"{wheels[-1]}: missing documentation assets: {missing}", file=sys.stderr)
        return 1

    print(f"{wheels[-1]}: {len(expected)} documentation assets present")
    return 0


if __name__ == "__main__":
    sys.exit(main())
