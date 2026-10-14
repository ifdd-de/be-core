"""Check the documentation of a repository or rendered instance (docs/en, docs/de).

    python check_docs.py DIRECTORY --prefix ifdd-be-core- [--external PREFIX ...] [--no-build]

1. Both languages have the same files, and per file the same labels and the
   same number of headings per level: a page or section added in one language
   only fails here.
2. Every label starts with the service prefix (``--prefix``), so labels stay
   unique when the documentation of all services is put together.
3. Every reference to a label with the service prefix points to a label that
   exists. References to other parts of the full documentation (prefixes
   given with ``--external``, e.g. the instance chapter) are not checked: they
   resolve only in the full build.
4. Each language builds with Sphinx without a warning (``-W``), using the
   configuration next to this script (tests/docs/conf.py). Needs the packages
   of tests/docs/requirements.txt.

Exit code 1 on any problem, with one line per problem on stderr.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
import tempfile
from collections import Counter
from pathlib import Path

LANGUAGES = ("en", "de")
LABEL = re.compile(r"^\(([A-Za-z0-9_.:-]+)\)=\s*$", re.MULTILINE)
REF = re.compile(r"\{ref\}`(?:[^`<]*<)?([A-Za-z0-9_.:-]+)>?`")
FENCE = re.compile(r"^(```|~~~)")
HEADING = re.compile(r"^(#{1,6})\s")
CONF_DIR = Path(__file__).resolve().parent / "docs"


def headings(text: str) -> Counter:
    """Number of headings per level, outside fenced code blocks."""
    levels: Counter = Counter()
    in_fence = False
    for line in text.splitlines():
        if FENCE.match(line):
            in_fence = not in_fence
            continue
        match = HEADING.match(line)
        if match and not in_fence:
            levels[len(match.group(1))] += 1
    return levels


def pages(directory: Path) -> dict[str, str]:
    return {
        path.relative_to(directory).as_posix(): path.read_text(encoding="utf-8")
        for path in sorted(directory.rglob("*.md"))
    }


def check_structure(docs: Path, prefix: str, external: list[str]) -> list[str]:
    problems: list[str] = []
    languages = {}
    for language in LANGUAGES:
        directory = docs / language
        if not directory.is_dir():
            problems.append(f"{directory} is missing")
            continue
        languages[language] = pages(directory)
    if len(languages) != len(LANGUAGES):
        return problems

    english, german = languages["en"], languages["de"]
    for name in sorted(set(english) ^ set(german)):
        side = "en" if name in english else "de"
        problems.append(f"{name}: only in docs/{side}")

    defined: set[str] = set()
    for name in sorted(set(english) & set(german)):
        labels_en = LABEL.findall(english[name])
        labels_de = LABEL.findall(german[name])
        if labels_en != labels_de:
            problems.append(f"{name}: labels differ (en {labels_en}, de {labels_de})")
        if headings(english[name]) != headings(german[name]):
            problems.append(
                f"{name}: headings per level differ "
                f"(en {dict(headings(english[name]))}, de {dict(headings(german[name]))})"
            )
        defined.update(labels_en)

    for language, files in languages.items():
        for name, text in files.items():
            for label in LABEL.findall(text):
                if not label.startswith(prefix):
                    problems.append(f"{language}/{name}: label {label!r} lacks prefix {prefix!r}")
            for target in REF.findall(text):
                if not target.startswith(prefix) or target.startswith(tuple(external)):
                    continue
                if target not in defined:
                    problems.append(f"{language}/{name}: reference to unknown label {target!r}")
    return problems


def build(docs: Path) -> list[str]:
    problems = []
    for language in LANGUAGES:
        with tempfile.TemporaryDirectory() as out:
            result = subprocess.run(
                [
                    sys.executable, "-m", "sphinx", "-W", "--keep-going", "-q",
                    "-c", str(CONF_DIR), "-D", f"language={language}",
                    "-b", "html", str(docs / language), out,
                ],
                capture_output=True,
                text=True,
                check=False,
            )
        if result.returncode != 0:
            problems.append(f"sphinx-build docs/{language} failed:\n{result.stderr.strip()}")
    return problems


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("instance", type=Path)
    parser.add_argument("--prefix", required=True, help="label prefix of the service, e.g. ifdd-be-")
    parser.add_argument(
        "--external",
        action="append",
        default=["ifdd-instances-"],
        help="label prefix of another part of the full documentation (repeatable)",
    )
    parser.add_argument("--no-build", action="store_true", help="skip the Sphinx build")
    args = parser.parse_args(argv)

    docs = args.instance / "docs"
    problems = check_structure(docs, args.prefix, args.external)
    if not problems and not args.no_build:
        problems = build(docs)
    for problem in problems:
        print(problem, file=sys.stderr)
    if not problems:
        print(f"{docs}: en and de match and build without warnings")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
