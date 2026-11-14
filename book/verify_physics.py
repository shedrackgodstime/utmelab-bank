#!/usr/bin/env python3
"""The completion gate for Secondary Physics.

This is stricter than `validate_chapters.py`. The validator says the documents
are well formed. This says the book is complete enough to teach from and to
mark done.

    python3 book/verify_physics.py
    python3 book/verify_physics.py --json data/staging/physics-completion.json

It exits 1 while any blocking rule fails. The rules are in
`docs/PHYSICS-COMPLETION.md`.
"""
from __future__ import annotations

import argparse
import glob
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import book_media  # noqa: E402
import build_chapter  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
BOOKS = ROOT / "data/books"
CHAPTERS = ROOT / "data/chapters"
SPECS = ROOT / "data/chapter-specs"
SOURCES = ROOT / "data/chapter-sources"

BOOK_ID = "secondary_physics"
EXPECTED_CHAPTERS = 34
FIRST_CHAPTER = "phy_nature_of_science"
TIER_DIFFICULTY = {"warm_up": {1, 2}, "core": {3}, "stretch": {4, 5}}
QUESTION_ID = re.compile(r"^q_[a-z0-9_]+$")
DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
BANNED_SOURCE_HOSTS = ("youtube.com", "youtu.be")
BANNED_SOURCE_SUFFIXES = (".pdf",)


class Findings:
    def __init__(self) -> None:
        self.rows: list[tuple[str, str, str, str]] = []

    def add(self, rule: str, path: str, message: str, severity: str = "error") -> None:
        self.rows.append((severity, rule, path, message))

    def errors(self) -> list[tuple[str, str, str, str]]:
        return [row for row in self.rows if row[0] == "error"]

    def warnings(self) -> list[tuple[str, str, str, str]]:
        return [row for row in self.rows if row[0] == "warning"]


def richtext(value) -> str:
    if isinstance(value, dict):
        text = value.get("text")
        if isinstance(text, str):
            return text
    return ""


def words_in_section(section: dict) -> int:
    total = 0
    for block in section.get("teaching_text", {}).get("blocks", []):
        if block.get("type") == "paragraph":
            total += len(richtext(block.get("content")).split())
    return total


def absolute_http(url: str) -> bool:
    return isinstance(url, str) and url.startswith(("http://", "https://"))


def check_source_url(url: str, path: str, findings: Findings) -> None:
    if not absolute_http(url):
        findings.add("SOURCE_URL", path, "source URL is not absolute http(s)")
        return
    lowered = url.lower()
    if lowered.endswith(BANNED_SOURCE_SUFFIXES):
        findings.add("SOURCE_URL", path, "source URL points at a PDF")
    if any(host in lowered for host in BANNED_SOURCE_HOSTS):
        findings.add("SOURCE_URL", path, "source URL points at a video")


def check_book(book: dict, findings: Findings) -> list[str]:
    chapters = book.get("chapters") or []
    if len(chapters) != EXPECTED_CHAPTERS:
        findings.add(
            "BOOK_CHAPTER_COUNT",
            book.get("book_id", "book"),
            f"{len(chapters)} chapters, expected {EXPECTED_CHAPTERS}",
        )
    if not chapters or chapters[0] != FIRST_CHAPTER:
        findings.add(
            "BOOK_FIRST_CHAPTER",
            book.get("book_id", "book"),
            f"first chapter is {chapters[0] if chapters else None!r}, expected {FIRST_CHAPTER!r}",
        )
    if chapters == sorted(chapters):
        findings.add(
            "BOOK_ORDER_ALPHABETICAL",
            book.get("book_id", "book"),
            "chapter array is alphabetical, not a teaching order",
        )

    parts = book.get("parts") or []
    part_ids = [part.get("id") for part in parts]
    if len(part_ids) != len(set(part_ids)):
        findings.add("BOOK_PART_DUPLICATE", book.get("book_id", "book"), "duplicate part id")
    for index, part in enumerate(parts, start=1):
        if part.get("order") != index:
            findings.add(
                "BOOK_PART_ORDER",
                f"part {part.get('id')}",
                f"order {part.get('order')} != {index}",
            )
        if not str(part.get("title") or "").strip():
            findings.add("BOOK_PART_TITLE", f"part {part.get('id')}", "part has no title")

    orders = []
    for chapter_id in chapters:
        path = CHAPTERS / f"{chapter_id}.json"
        if not path.exists():
            findings.add("BOOK_CHAPTER_MISSING", chapter_id, "chapter document does not exist")
            continue
        chapter = json.loads(path.read_text())
        if chapter.get("book_id") != BOOK_ID:
            findings.add("BOOK_CHAPTER_BOOK", chapter_id, "chapter names another book")
        part_id = chapter.get("part_id")
        if part_id not in part_ids:
            findings.add("BOOK_PART_UNKNOWN", chapter_id, f"part_id {part_id!r} is not declared by the book")
        order = chapter.get("order")
        if not isinstance(order, int):
            findings.add("BOOK_CHAPTER_ORDER_FIELD", chapter_id, "chapter has no integer order")
        else:
            orders.append(order)
        if not (SPECS / f"{chapter_id}.json").exists():
            findings.add("BOOK_SPEC_MISSING", chapter_id, "chapter has no spec")
    if orders:
        if len(orders) != len(set(orders)):
            findings.add("BOOK_CHAPTER_ORDER_DUP", book.get("book_id", "book"), "duplicate chapter order")
        if sorted(orders) != list(range(1, len(orders) + 1)):
            findings.add("BOOK_CHAPTER_ORDER_GAP", book.get("book_id", "book"), "chapter order is not 1..N")
        part_order = {part.get("id"): part.get("order") for part in parts}
        seen = 0
        for chapter_id in chapters:
            chapter = json.loads((CHAPTERS / f"{chapter_id}.json").read_text())
            current = part_order.get(chapter.get("part_id"))
            if current is None:
                continue
            if current < seen:
                findings.add("BOOK_PART_SEQUENCE", chapter_id, "chapter appears after a later part")
            seen = max(seen, current)
    return chapters


def check_chapter(chapter: dict, findings: Findings, all_chapters: set[str]) -> None:
    cid = chapter.get("chapter_id", "?")
    if len(chapter.get("learning_objectives") or []) < 2:
        findings.add("CHAPTER_OBJECTIVES", cid, "fewer than two chapter objectives")
    if not chapter.get("formula_sheet") and not str(chapter.get("no_formula_reason") or "").strip():
        findings.add("CHAPTER_FORMULA", cid, "empty formula sheet with no reason")
    if not chapter.get("glossary"):
        findings.add("CHAPTER_GLOSSARY", cid, "empty glossary")

    prerequisites = chapter.get("prerequisites")
    if prerequisites is None:
        findings.add("CHAPTER_PREREQ", cid, "prerequisites is missing")
    elif not isinstance(prerequisites, list):
        findings.add("CHAPTER_PREREQ", cid, "prerequisites is not a list")
    elif cid != FIRST_CHAPTER and not prerequisites:
        findings.add("CHAPTER_PREREQ", cid, "no prerequisite chapter")
    for prerequisite in prerequisites or []:
        if prerequisite not in all_chapters:
            findings.add("CHAPTER_PREREQ_UNKNOWN", cid, f"unknown prerequisite {prerequisite}")
        if prerequisite == cid:
            findings.add("CHAPTER_PREREQ_SELF", cid, "chapter is its own prerequisite")

    if not chapter.get("exam_recall_checks"):
        findings.add("CHAPTER_RECALL", cid, "no recall check")
    if not chapter.get("exam_links") and not str(chapter.get("no_exam_link_reason") or "").strip():
        findings.add("CHAPTER_EXAM_LINKS", cid, "no exam links and no reason")
    if not chapter.get("sources"):
        findings.add("CHAPTER_SOURCE", cid, "no sources")
    for source in chapter.get("sources") or []:
        check_source_url(source.get("url", ""), f"{cid}.sources", findings)

    sections = chapter.get("sections") or []
    section_ids = {section.get("id") for section in sections}
    exercises = chapter.get("exercises") or []
    by_section = defaultdict(list)
    for exercise in exercises:
        by_section[exercise.get("section_id")].append(exercise)
    recall_by_section = defaultdict(list)
    for check in chapter.get("exam_recall_checks") or []:
        recall_by_section[check.get("section_id")].append(check)

    for section in sections:
        sid = section.get("id", "?")
        path = f"{cid}/{sid}"
        is_intro = str(section.get("title") or "").lower().startswith("introduction")
        minimum_objectives = 1 if is_intro else 2
        if len(section.get("learning_objectives") or []) < minimum_objectives:
            findings.add(
                "SECTION_OBJECTIVES",
                path,
                f"fewer than {minimum_objectives} section objectives",
            )
        minimum = 40 if is_intro else 120
        count = words_in_section(section)
        if count < minimum:
            findings.add("SECTION_TEACHING", path, f"{count} words, minimum {minimum}")
        if not section.get("worked_examples") and not str(section.get("no_worked_example_reason") or "").strip():
            findings.add("SECTION_WORKED", path, "no worked example and no reason")
        if len(section.get("summary_points") or []) < 2:
            findings.add("SECTION_SUMMARY", path, "fewer than two summary points")
        if is_intro:
            continue
        if not section.get("misconceptions"):
            findings.add("SECTION_MISCONCEPTION", path, "no misconception")
        if not recall_by_section.get(sid):
            findings.add("SECTION_RECALL", path, "no recall check")
        if not section.get("exam_links") and not str(section.get("no_exam_link_reason") or "").strip():
            findings.add("SECTION_EXAM_LINKS", path, "no exam link and no reason")
        section_exercises = by_section.get(sid, [])
        if not section_exercises:
            findings.add("SECTION_EXERCISES", path, "no exercises")
            continue
        if len(section_exercises) < 3:
            findings.add("SECTION_EXERCISES", path, f"{len(section_exercises)} exercises, minimum 3")

    chapter_tiers = Counter(exercise.get("tier") for exercise in exercises)
    for tier in ("warm_up", "core", "stretch"):
        if chapter_tiers.get(tier, 0) < 3:
            findings.add("CHAPTER_TIER", cid, f"{chapter_tiers.get(tier, 0)} {tier} exercises, minimum 3")

    check_exercises(cid, exercises, section_ids, findings)
    check_traps(cid, chapter.get("exam_traps") or [], section_ids, findings)
    check_recall(cid, chapter.get("exam_recall_checks") or [], section_ids, findings)
    check_figures(cid, chapter, findings)


def check_exercises(cid: str, exercises: list[dict], section_ids: set, findings: Findings) -> None:
    seen_stems = {}
    for exercise in exercises:
        eid = exercise.get("id", "?")
        path = f"{cid}/{eid}"
        if exercise.get("section_id") not in section_ids:
            findings.add("EXERCISE_SECTION", path, "exercise points at an unknown section")
        stem = richtext(exercise.get("stem")).strip()
        if not stem:
            findings.add("EXERCISE_STEM", path, "exercise has no stem")
        elif stem in seen_stems:
            findings.add("EXERCISE_DUPLICATE", path, f"same stem as {seen_stems[stem]}")
        else:
            seen_stems[stem] = eid
        answer = richtext(exercise.get("answer")).strip()
        if not answer:
            findings.add("EXERCISE_ANSWER", path, "exercise has no answer")
        solution = exercise.get("solution") or []
        if not solution or not all(str(step.get("expression") or "").strip() for step in solution):
            findings.add("EXERCISE_SOLUTION", path, "exercise has no readable solution")
        # A stem may not lean on a figure or table the book does not carry.
        # These patterns are the flattened remnants of source figure
        # references: "shown in .", "(See .)", "as in .", and friends.
        haystack = " ".join(stem.split()).lower()
        for pattern in (
            r"\b(?:shown|seen)\s+in\s+[,.(]",
            r"\bas\s+(?:in|seen\s+in|shown\s+in|claimed\s+in|given\s+in)\s+[,.(]",
            r"\(\s*see\s*\.",
            r"\b(?:discussed|studied|computed|obtained|read|found)\s+in\s+(?:the\s+)?[.,;)]",
            r"\b(?:figure|graph|table|diagram)\s+in\s+[,.(]",
            r"\b(?:figure|diagram|graph)\s+(?:above|below)",
            r"\bshown\s+(?:above|below)",
            r"\bin\s+the\s+figure\s+below",
            r"\b(?:as\s+shown|shown)\s+in\s+the\s+figure\b",
            r"\bdata\s+in\s+the\s+figure\b",
            r"\bin\s+each\s+of\s+the\s+three\s+cases\s+in\s+[,.(]",
            r"\bthe\s+curve\s+in\s+[,.(]",
        ):
            if re.search(pattern, haystack):
                findings.add(
                    "EXERCISE_FIGURE_REF", path, f"stem leans on a missing figure: /{pattern}/")
                break
        # The flattened source sometimes leaves the answer inside the stem.
        flat_answer = " ".join(answer.split()).lower()
        if len(flat_answer) >= 60 and flat_answer[:60] in haystack:
            findings.add("EXERCISE_LEAKED_ANSWER", path, "the stem contains its own answer")
        for pattern in ("click to view", "lorem ipsum", r"\btodo\b", r"\bfixme\b", "placeholder"):
            if re.search(pattern, haystack):
                findings.add("EXERCISE_PLACEHOLDER", path, f"stem holds a placeholder: /{pattern}/")
                break
        options = exercise.get("options") or []
        if options:
            if len(options) < 2:
                findings.add("EXERCISE_MCQ", path, "fewer than two options")
            else:
                ids = [str(option.get("id", "")).strip().lower() for option in options]
                texts = [str(option.get("text", "")).strip() for option in options]
                if any(not text for text in texts):
                    findings.add("EXERCISE_MCQ", path, "an option has no text")
                if len(set(ids)) != len(ids) or any(not i for i in ids):
                    findings.add("EXERCISE_MCQ", path, "option ids are missing or repeated")
                if ids != [chr(ord("a") + index) for index in range(len(ids))]:
                    findings.add("EXERCISE_MCQ", path, f"option ids {ids} are not a, b, c, ...")
                if len(set(texts)) != len(texts):
                    findings.add("EXERCISE_MCQ", path, "two options repeat the same text")
                letters = re.findall(r"\(([a-e])\)", answer.lower())
                if not letters:
                    findings.add("EXERCISE_MCQ", path, "answer names no option")
                for letter in letters:
                    if letter not in ids:
                        findings.add("EXERCISE_MCQ", path, f"answer ({letter}) has no matching option")
        tier = exercise.get("tier")
        difficulty = exercise.get("difficulty")
        if tier not in TIER_DIFFICULTY:
            findings.add("EXERCISE_TIER", path, f"unknown tier {tier!r}")
        elif difficulty not in TIER_DIFFICULTY[tier]:
            findings.add("EXERCISE_DIFFICULTY", path, f"tier {tier} with difficulty {difficulty}")
        if not exercise.get("provenance"):
            findings.add("EXERCISE_PROVENANCE", path, "no provenance")
        if not exercise.get("solution_provenance"):
            findings.add("EXERCISE_PROVENANCE", path, "no solution provenance")


def check_traps(cid: str, traps: list[dict], section_ids: set, findings: Findings) -> None:
    for trap in traps:
        tid = trap.get("id", "?")
        path = f"{cid}/{tid}"
        if trap.get("section_id") not in section_ids:
            findings.add("TRAP_SECTION", path, "trap points at an unknown section")
        status = trap.get("status")
        if status != "proven":
            findings.add("TRAP_STATUS", path, f"status is {status!r}, only proven traps may ship")
            continue
        evidence = trap.get("paper_evidence") or {}
        question = evidence.get("question_id")
        if evidence.get("source") != "claimed_paper":
            findings.add("TRAP_EVIDENCE", path, f"evidence source is {evidence.get('source')!r}")
        if not isinstance(question, str) or not QUESTION_ID.match(question):
            findings.add("TRAP_EVIDENCE", path, f"question id {question!r} is not a paper question id")
        if evidence.get("exam") != trap.get("exam"):
            findings.add("TRAP_EVIDENCE", path, "evidence exam does not match trap exam")
        if not isinstance(evidence.get("year"), int):
            findings.add("TRAP_EVIDENCE", path, "evidence has no integer year")
        if not absolute_http(evidence.get("url", "")):
            findings.add("TRAP_EVIDENCE", path, "evidence has no absolute URL")


def check_recall(cid: str, checks: list[dict], section_ids: set, findings: Findings) -> None:
    for check in checks:
        rid = check.get("id", "?")
        path = f"{cid}/{rid}"
        if check.get("section_id") not in section_ids:
            findings.add("RECALL_SECTION", path, "recall check points at an unknown section")
        if not richtext(check.get("stem")).strip():
            findings.add("RECALL_STEM", path, "recall check has no stem")
        options = check.get("options") or []
        if len(options) < 2:
            findings.add("RECALL_OPTIONS", path, "fewer than two options")
        ids = {option.get("id") for option in options}
        if check.get("answer") not in ids:
            findings.add("RECALL_ANSWER", path, "answer is not one of the options")
        if not richtext(check.get("explanation")).strip():
            findings.add("RECALL_EXPLANATION", path, "recall check has no explanation")


def check_figures(cid: str, chapter: dict, findings: Findings) -> None:
    manifest = book_media.load_manifest()
    published = {record.get("published_path"): record for record in manifest.get("figures", {}).values()}
    for section in chapter.get("sections") or []:
        for block in section.get("teaching_text", {}).get("blocks", []):
            if block.get("type") != "figure":
                continue
            asset = block.get("asset_url", "")
            path = f"{cid}/{section.get('id')}/{block.get('id')}"
            record = published.get(asset)
            if record is None:
                findings.add("FIGURE_MANIFEST", path, f"{asset} is not published")
            elif record.get("rejected"):
                findings.add("FIGURE_MANIFEST", path, f"{asset} is rejected")
            if not str(block.get("alt") or "").strip():
                findings.add("FIGURE_ALT", path, "figure has no alt text")
            if not richtext(block.get("caption")).strip():
                findings.add("FIGURE_CAPTION", path, "figure has no caption")


def check_rebuild(chapter: dict, findings: Findings) -> None:
    cid = chapter.get("chapter_id", "?")
    spec_path = SPECS / f"{cid}.json"
    if not spec_path.exists():
        return
    try:
        spec = json.loads(spec_path.read_text())
        rebuilt = build_chapter.build(spec)
    except SystemExit as error:
        findings.add("CHAPTER_REBUILD", cid, str(error))
        return
    except Exception as error:  # noqa: BLE001
        findings.add("CHAPTER_REBUILD", cid, f"{type(error).__name__}: {error}")
        return
    rendered = json.dumps(rebuilt, ensure_ascii=False, indent=2) + "\n"
    current = (CHAPTERS / f"{cid}.json").read_text()
    if rendered != current:
        findings.add("CHAPTER_REBUILD", cid, "chapter does not match its spec and source")

    for section in spec.get("sections", []):
        module = section.get("module")
        if module and not (SOURCES / f"{module}.json").exists():
            findings.add("SOURCE_MODULE", f"{cid}/{section.get('id')}", f"no extract for {module}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", default="data/staging/physics-completion.json")
    args = parser.parse_args()

    book_path = BOOKS / f"{BOOK_ID}.json"
    if not book_path.exists():
        print(f"book not found: {book_path}")
        return 1
    book = json.loads(book_path.read_text())
    findings = Findings()
    chapter_ids = check_book(book, findings)
    all_chapters = set(chapter_ids)
    for chapter_id in chapter_ids:
        path = CHAPTERS / f"{chapter_id}.json"
        if not path.exists():
            continue
        chapter = json.loads(path.read_text())
        check_chapter(chapter, findings, all_chapters)
        check_rebuild(chapter, findings)

    report = {
        "book_id": BOOK_ID,
        "chapter_count": len(chapter_ids),
        "expected_chapter_count": EXPECTED_CHAPTERS,
        "errors": len(findings.errors()),
        "warnings": len(findings.warnings()),
        "by_rule": dict(Counter(row[1] for row in findings.errors()).most_common()),
        "findings": [
            {"severity": severity, "rule": rule, "path": path, "message": message}
            for severity, rule, path, message in findings.rows
        ],
    }
    output = ROOT / args.json
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")

    print(f"Physics completion gate: {len(chapter_ids)} chapters, expected {EXPECTED_CHAPTERS}")
    print(f"errors {report['errors']} | warnings {report['warnings']}")
    print("\nby rule")
    for rule, count in Counter(row[1] for row in findings.errors()).most_common():
        print(f"  {count:4} {rule}")
    print("\nby chapter")
    by_chapter = Counter(row[2].split("/")[0] for row in findings.errors())
    for chapter, count in by_chapter.most_common():
        print(f"  {count:4} {chapter}")
    print(f"\nfirst 80 findings (full report: {output.relative_to(ROOT)})")
    for severity, rule, path, message in findings.rows[:80]:
        print(f"  {severity:5} {rule:24} {path:55} {message}")
    return 1 if findings.errors() else 0


if __name__ == "__main__":
    raise SystemExit(main())
