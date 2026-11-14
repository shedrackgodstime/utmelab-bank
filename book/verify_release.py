#!/usr/bin/env python3
"""Read production back and compare it with the bundle that was imported.

    python3 book/verify_release.py --book secondary_mathematics

A content import is the deployment, and a silent or partial import is the
failure mode that matters. This script is the post-import check: it calls the
API for each book and chapter in the local bundle and fails on any difference,
so an import that wrote half a chapter cannot be mistaken for a success.

Checks, per book and chapter:

- the book lists its chapters in the order the book document names them;
- each chapter's order, title and section index match the bundle;
- every exercise in the bundle exists and carries a solution;
- every section's title, teaching figure count and exam links match the bundle;
- every published figure URL answers 200 (skip with --no-figures);
- every exam trap in the bundle appears under its exam with the same status,
  frequency and provenance.

The API key comes from UTMELAB_API_KEY, or UTMELAB_DEV_API_KEY as the name the
API repository's .env already uses. Nothing is written anywhere.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BUNDLE = ROOT / "data/staging/chapters-bundle.json"
BOOKS = ROOT / "data/books"
DEFAULT_API = "https://api.utmelab.com"
RETRIES = 5
BACKOFF_SECONDS = 8


class Api:
    def __init__(self, base: str, key: str, timeout: float):
        self.base = base.rstrip("/")
        self.key = key
        self.timeout = timeout

    def get(self, path: str):
        last = None
        for attempt in range(RETRIES):
            request = urllib.request.Request(
                self.base + path,
                headers={"x-api-key": self.key, "User-Agent": "verify-release"},
            )
            try:
                with urllib.request.urlopen(request, timeout=self.timeout) as response:
                    return json.loads(response.read().decode())
            except urllib.error.HTTPError as error:
                body = error.read().decode()[:300]
                # A cold pull answers 408 until the replica wakes; retry it.
                if error.code in (408, 429) and attempt < RETRIES - 1:
                    time.sleep(BACKOFF_SECONDS)
                    continue
                raise RuntimeError(f"GET {path} -> {error.code}: {body}") from error
            except Exception as error:  # noqa: BLE001 - network failures vary
                last = error
                if attempt < RETRIES - 1:
                    time.sleep(BACKOFF_SECONDS)
                    continue
        raise RuntimeError(f"GET {path} -> {last}")


def head_ok(url: str, timeout: float) -> tuple[bool, str]:
    try:
        request = urllib.request.Request(url, method="HEAD")
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.status == 200, str(response.status)
    except Exception as error:  # noqa: BLE001 - any failure is a failure
        return False, str(error)


def traps_by_exam(bundle: dict) -> dict[str, dict]:
    found: dict[str, dict] = {}
    for chapter in bundle["chapters"]:
        for trap in chapter.get("exam_traps") or []:
            exam = trap.get("exam") or ""
            found.setdefault(exam, {})[
                f"{chapter['chapter_id']}:{trap['id']}"
            ] = trap
    return found


def namespaced(chapter_id: str, local_id: str) -> str:
    """The store prefixes a chapter's child ids with the chapter id."""
    return f"{chapter_id}:{local_id}"


def compare_section(api: Api, chapter_id: str, section: dict, figures: bool,
                    failures: list[str]) -> None:
    local_id = section["id"]
    remote = api.get(f"/api/v1/chapters/{chapter_id}/sections/{local_id}")
    where = f"{chapter_id}/{local_id}"

    if remote.get("title") != section["title"]:
        failures.append(
            f"{where}: title {remote.get('title')!r} != {section['title']!r}"
        )

    local_figures = [
        block
        for block in section["teaching_text"]["blocks"]
        if block.get("type") == "figure"
    ]
    remote_figures = [
        block for block in remote.get("content", []) if block.get("type") == "figure"
    ]
    if len(remote_figures) != len(local_figures):
        failures.append(
            f"{where}: {len(remote_figures)} figures, bundle has {len(local_figures)}"
        )
    if figures:
        for block in remote_figures:
            ok, detail = head_ok(block.get("asset_url") or "", api.timeout)
            if not ok:
                failures.append(f"{where}: figure {block.get('asset_url')} -> {detail}")

    def links(items):
        return sorted(
            (item.get("exam"), item.get("subtopic_slug"), item.get("status"))
            for item in items
        )

    if links(remote.get("exam_links") or []) != links(section.get("exam_links") or []):
        failures.append(f"{where}: exam links differ from the bundle")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle", default=str(BUNDLE))
    parser.add_argument(
        "--book",
        action="append",
        help="book id to verify; repeatable. Default: every book in data/books.",
    )
    parser.add_argument("--api-base", default=os.environ.get("UTMELAB_API_BASE", DEFAULT_API))
    parser.add_argument(
        "--api-key",
        default=os.environ.get("UTMELAB_API_KEY")
        or os.environ.get("UTMELAB_DEV_API_KEY")
        or "",
    )
    parser.add_argument("--timeout", type=float, default=45.0)
    parser.add_argument(
        "--no-figures",
        action="store_true",
        help="skip the published-figure HEAD checks",
    )
    args = parser.parse_args()

    if not args.api_key:
        print("no API key: set UTMELAB_API_KEY or UTMELAB_DEV_API_KEY", file=sys.stderr)
        return 2

    bundle = json.loads(Path(args.bundle).read_text())
    books = bundle["books"]
    chapters = {chapter["chapter_id"]: chapter for chapter in bundle["chapters"]}
    api = Api(args.api_base, args.api_key, args.timeout)

    wanted = set(args.book) if args.book else {book["id"] for book in books}
    failures: list[str] = []

    # The book document keeps the reader-facing chapter order, which the
    # importer turns into order_index, so this is the order users will see.
    for book_id in sorted(wanted):
        document = json.loads((BOOKS / f"{book_id}.json").read_text())
        expected = document.get("chapters") or []
        remote = api.get(f"/api/v1/textbooks/{book_id}")
        actual = [chapter.get("chapter_id") for chapter in remote.get("chapters") or []]
        if actual != expected:
            failures.append(
                f"{book_id}: chapter order {actual} != {expected}"
            )
        else:
            print(f"book {book_id}: {len(actual)} chapters in order")

    for chapter_id, chapter in chapters.items():
        if chapter.get("book_id") not in wanted:
            continue
        remote = api.get(f"/api/v1/chapters/{chapter_id}")
        where = chapter_id
        if remote.get("title") != chapter["title"]:
            failures.append(f"{where}: title {remote.get('title')!r} != {chapter['title']!r}")
        if remote.get("order") != chapter.get("order"):
            failures.append(f"{where}: order {remote.get('order')} != {chapter.get('order')}")

        index = remote.get("section_index") or []
        if [item.get("id") for item in index] != [item["id"] for item in chapter["sections"]]:
            failures.append(f"{where}: section index differs from the bundle")

        expected_ids = [namespaced(chapter_id, item["id"]) for item in chapter["exercises"]]
        remote_exercises = api.get(f"/api/v1/chapters/{chapter_id}/exercises")
        actual_ids = [item.get("id") for item in remote_exercises]
        if actual_ids != expected_ids:
            missing = sorted(set(expected_ids) - set(actual_ids))
            extra = sorted(set(actual_ids) - set(expected_ids))
            failures.append(
                f"{where}: exercises {len(actual_ids)} of {len(expected_ids)}"
                + (f"; missing {missing}" if missing else "")
                + (f"; unexpected {extra}" if extra else "")
            )
        without_solution = [
            item.get("id") for item in remote_exercises if not item.get("solution")
        ]
        if without_solution:
            failures.append(f"{where}: exercises without solutions {without_solution}")

        for section in chapter["sections"]:
            compare_section(api, chapter_id, section, not args.no_figures, failures)
        print(f"chapter {chapter_id}: {len(chapter['sections'])} sections checked")

    # Traps are listed per exam, not per chapter, so each bundle trap is
    # matched by its namespaced id against the exam it should appear under.
    for exam, expected in sorted(traps_by_exam(bundle).items()):
        if not exam:
            continue
        remote = api.get(f"/api/v1/exam-traps?exam={exam}")
        actual = {item.get("id"): item for item in remote}
        for trap_id, trap in expected.items():
            remote_trap = actual.get(trap_id)
            if remote_trap is None:
                failures.append(f"trap {trap_id}: missing from {exam}")
                continue
            for field in ("status", "frequency"):
                if remote_trap.get(field) != trap.get(field):
                    failures.append(
                        f"trap {trap_id}: {field} {remote_trap.get(field)!r} != {trap.get(field)!r}"
                    )
            for field in ("publisher", "title"):
                remote_value = (remote_trap.get("provenance") or {}).get(field)
                local_value = (trap.get("provenance") or {}).get(field)
                if remote_value != local_value:
                    failures.append(
                        f"trap {trap_id}: provenance {field} {remote_value!r} != {local_value!r}"
                    )

    print()
    if failures:
        print("IMPORT VERIFICATION FAILED")
        for failure in failures:
            print(f"  {failure}")
        return 1
    print("PRODUCTION MATCHES THE BUNDLE")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
