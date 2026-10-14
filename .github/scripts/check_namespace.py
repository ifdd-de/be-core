"""Fail if the built wheel turns the namespace packages into regular ones.

`ifdd` and `ifdd.be` are PEP 420 implicit namespace packages. An __init__.py
in either would make this distribution claim the whole namespace and shut out
ifdd.fe, ifdd.tools and anything else added to it later.
"""

import glob
import sys
import zipfile

FORBIDDEN = ("ifdd/__init__.py", "ifdd/be/__init__.py")


def main() -> int:
    wheels = sorted(glob.glob("dist/*.whl"))
    if not wheels:
        print("No wheel found in dist/", file=sys.stderr)
        return 1

    wheel = wheels[-1]
    names = zipfile.ZipFile(wheel).namelist()
    found = [name for name in FORBIDDEN if name in names]
    if found:
        print(f"Namespace packages must stay implicit, found: {found}", file=sys.stderr)
        return 1

    print(f"{wheel}: namespace is implicit")
    return 0


if __name__ == "__main__":
    sys.exit(main())
