#!/usr/bin/env python3
"""The local release gate for the book factory. It touches no remote.

    python3 book/release_check.py

Run it before a release window, after the last content edit and before the
commit. It answers one question: may this checkout be imported?

Three checks, in order:

1. `book/validate_chapters.py` over every chapter. Any error is a no-go.
2. `book/build_chapter.py --check` for every spec, so no built chapter has
   drifted from its spec. A spec that differs fails the gate unless it is on
   KNOWN_STALE below.
3. `book/bundle_chapters.py`, so the file the importer reads is current.

KNOWN_STALE is a debt list, not a permission slip. The two math chapters
were hand-refined after they were built, so their specs no longer describe
their chapters and a rebuild would discard the refinements. The validator
still checks those chapters structurally; only the spec-equality check is
waived. When a chapter is rebuilt from its spec, remove the name here. The
gate prints a warning when an entry has become clean, so the list cannot
quietly outlive its reason.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SPECS = ROOT / "data/chapter-specs"
CHAPTERS = ROOT / "data/chapters"
WORKFLOW = ROOT / "docs/BOOK-RELEASE-WORKFLOW.md"

# Specs whose built chapters were hand-refined and are never rebuilt. The
# validator still covers them; see docs/BOOK-RELEASE-WORKFLOW.md.
KNOWN_STALE = {
    "math_number_bases.json",
    "math_laws_of_indices_and_surds.json",
}


def run(*args: str) -> tuple[int, str]:
    result = subprocess.run(
        [sys.executable, *args],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    output = (result.stdout + result.stderr).strip()
    return result.returncode, output


def tail(text: str, lines: int = 4) -> str:
    kept = [line for line in text.splitlines() if line.strip()]
    return "\n".join(kept[-lines:]) if kept else "(no output)"


def main() -> int:
    failures: list[str] = []
    warnings: list[str] = []

    # 1. Structural validation of every built chapter.
    code, output = run("book/validate_chapters.py")
    files = errors = None
    for line in output.splitlines():
        if line.startswith("files "):
            files = line.split()[1]
        elif line.startswith("errors "):
            errors = line.split()[1]
    if code != 0 or errors != "0":
        failures.append("validator\n" + tail(output))
        print(f"validator      FAIL  files {files} errors {errors}")
    else:
        print(f"validator      ok    files {files} errors 0")

    # 2. Every built chapter agrees with its spec, except the debt list.
    specs = sorted(SPECS.glob("*.json"))
    passed = expected = failed = 0
    for spec in specs:
        code, output = run("book/build_chapter.py", str(spec), "--check")
        if code == 0:
            passed += 1
            if spec.name in KNOWN_STALE:
                warnings.append(
                    f"{spec.name} now matches its spec; remove it from KNOWN_STALE"
                )
        elif spec.name in KNOWN_STALE:
            expected += 1
        else:
            failed += 1
            failures.append(f"spec check {spec.name}\n" + tail(output))
    print(
        f"spec checks    {'FAIL' if failed else 'ok'}    "
        f"{passed} pass, {expected} known stale, {failed} unexpected"
    )

    # 3. The bundle the importer reads must exist and be current.
    code, output = run("book/bundle_chapters.py")
    if code != 0:
        failures.append("bundle\n" + tail(output))
        print("bundle         FAIL")
    else:
        print(f"bundle         ok    {tail(output, 1)}")

    built = len(list(CHAPTERS.glob("*.json")))
    if files is not None and files != str(built):
        failures.append(
            f"validator covered {files} chapters but {built} are built"
        )

    print()
    for warning in warnings:
        print(f"warning: {warning}")
    if failures:
        print("NO-GO")
        for failure in failures:
            print()
            print(failure)
        return 1

    print("GO: the checkout is ready for a release window")
    print(f"process: {WORKFLOW.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
