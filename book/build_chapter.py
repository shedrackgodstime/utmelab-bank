#!/usr/bin/env python3
"""Build a textbook chapter from a chapter spec.

    python3 book/build_chapter.py data/chapter-specs/<chapter_id>.json
    python3 book/build_chapter.py data/chapter-specs/<chapter_id>.json --check

A spec carries what a human authors: the objectives, the misconceptions, the
summary points, the formula sheet, the glossary, the exam links, and any
teaching text we wrote ourselves. Everything else comes from the source: the
prose, the figures, the exercises, the answers and the solutions.

The spec is the source of truth for the authored part. The chapter document
is the built artifact, and the two are checked against each other in CI, so
the chapter can never drift from its spec.

See docs/CONTENT-BOOK-SCHEMA.md for the shapes.
"""
import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import book_media  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
#: The source material the factory reads. It is tracked, so a clean checkout
#: can rebuild a chapter and the content gate can check it.
SOURCES = ROOT / "data/chapter-sources"
CHAPTERS = ROOT / "data/chapters"
BOOKS = ROOT / "data/books"

TIERS = ("warm_up", "core", "stretch")


def rt(text):
    return {"text": text, "inline": []}


def slugify(text):
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:60]


def find_source(module):
    """The source extract for a module, with the solutions that go with it."""
    path = SOURCES / f"{module}.json"
    if not path.exists():
        return None, None
    try:
        document = json.loads(path.read_text())
    except Exception:
        return None, None
    return document, document.get("solutions") or {}


def render_parts(parts):
    out = []
    for part in parts:
        if part["kind"] == "text":
            text = " ".join(part["text"].split())
            if text:
                out.append(text)
        else:
            out.append(f"${part['text']}$")
    return " ".join(out).strip()


def classify(prompt):
    text = prompt.lower()
    if "explain" in text or text.rstrip().endswith("why") or "discuss" in text:
        return "verbal"
    # A multi part problem is marked with two part markers.
    if (re.search(r"\(a\)", text) and re.search(r"\(b\)", text)) or ("ⓐ" in prompt and "ⓑ" in prompt):
        return "application"
    if re.search(r"\d", prompt):
        return "numeric"
    return "algebraic"


CHOICE_ANSWER = re.compile(r"^(?:\([a-e]\)(?:\s*,\s*)?)+$", re.I)
CHOICE_MARKER = re.compile(r"(?:^|[\s(])([a-e])\)\s", re.I)


def split_choices(prompt):
    """Split a flattened multiple choice prompt into its stem and options.

    The scraper flattens the options into one line: the stem, then the
    options separated by semicolons, the first option glued to the stem. The
    answer is a letter, which refers to the options by position. Returns
    (stem, options) or None when the prompt is not a clean set of choices.
    """
    text = " ".join(prompt.split())
    # Some prompts label their options inline: "(a) ... (b) ... (c) ...".
    markers = list(CHOICE_MARKER.finditer(text))
    if len(markers) >= 3:
        letters = [marker.group(1).lower() for marker in markers]
        if letters == list("abcde")[: len(letters)]:
            stem = text[: markers[0].start()].strip()
            options = []
            for index, marker in enumerate(markers):
                end = (
                    markers[index + 1].start()
                    if index + 1 < len(markers)
                    else len(text)
                )
                option = text[marker.end() : end].strip()
                if option.endswith("."):
                    option = option[:-1].strip()
                options.append(option)
            if stem and all(options) and len(set(options)) == len(options):
                return stem, options
    # The usual shape: "Question? option one; option two; option three."
    question = text.rfind("?")
    if question != -1:
        stem = text[: question + 1].strip()
        tail = text[question + 1 :].strip()
        options = []
        for option in tail.split(";"):
            option = option.strip()
            if not option:
                continue
            if option.endswith("."):
                option = option[:-1].strip()
            options.append(option)
        if len(options) >= 2 and len(set(options)) == len(options):
            return stem, options
    return None


def answer_from(parts, kind):
    """The answer as the source states it, never a newly written one."""
    rendered = render_parts([p for paragraph in parts for p in paragraph])
    if kind == "verbal":
        return rendered, "explanation"
    candidates = [
        p["text"]
        for paragraph in parts
        for p in paragraph
        if p["kind"] == "math" and p["text"].strip()
    ]
    if not candidates:
        candidates = [
            p["text"]
            for paragraph in parts
            for p in paragraph
            if p["kind"] == "text" and p["text"].strip() and len(p["text"]) <= 40
        ]
    for candidate in reversed(candidates):
        value = candidate.strip().strip("$").strip()
        value = value.strip(" .,;:")
        if not value or "$" in value:
            continue
        if not re.search(r"[A-Za-z0-9]", value):
            continue
        # A short trailing fragment of a longer expression is not an answer.
        if len(value) < 12 and value[0] in "}^_":
            continue
        if "=" in value:
            tail = value.rsplit("=", 1)[1].strip().strip("$").strip(" .,;:")
            if tail and len(tail) <= 30 and "=" not in tail:
                return tail, "expression"
        # A chain of fractions ends with the answer.
        pieces = value.rsplit("\\cdot", 1)[-1]
        fractions = re.findall(r"\\frac\{(?:[^{}]|\{[^{}]*\})*\}\{(?:[^{}]|\{[^{}]*\})*\}", pieces)
        if len(fractions) > 1:
            return fractions[-1], "expression"
        if len(value) > 70:
            continue
        twins = [
            other.strip().strip("$").strip(" .,;:")
            for other in candidates
            if other is not candidate
        ]
        if value.startswith("-") and value[1:] in twins:
            # The source states both cases, a value and its opposite. The
            # whole solution is the honest answer.
            return rendered, "explanation"
        return value, "expression"
    return rendered, "explanation"


def tier_for(difficulty):
    if difficulty <= 2:
        return "warm_up"
    if difficulty == 3:
        return "core"
    return "stretch"


# The source groups its exercises by how hard they are meant to be. The tier
# comes from that grouping, not from our guess.
GROUP_TIERS = {
    "conceptual questions": "warm_up",
    "problems and exercises": "core",
    "problem exercises": "core",
    "section exercises": "core",
    "test prep for ap courses": "stretch",
}


def tier_for_grouping(grouping):
    return GROUP_TIERS.get((grouping or "").strip().lower(), "core")


# Placeholder prose the scraper leaves behind for an embedded widget. It is
# not teaching and it must not reach a reader.
PLACEHOLDER_PARAGRAPHS = {
    "click to view content",
    "click to view content .",
    "click to view content.",
}

# Headings that start the back matter of a source module. Once one appears,
# the blocks that follow are summary bullets, questions or exercises, not
# teaching. The exercises are still collected; their prose is not.
TAIL_HEADINGS = {
    "section summary",
    "summary",
    "key concepts",
    "key equations",
    "key terms",
    "conceptual questions",
    "conceptual question",
    "problems & exercises",
    "problems & exercise",
    "problem exercises",
    "problem exercise",
    "problems exercises",
    "problems-exercises",
    "test prep for ap courses",
    "section exercises",
    "multiple choice",
    "short answer",
    "chapter review",
    "chapter test",
    "projects",
    "videos",
    "references",
    "glossary",
    "further reading",
}


def apply_prose_fixes(text, fixes, used):
    """Repair the source's own prose where the scraper lost an inline element.

    A source paragraph that pointed at a figure or a table by an embedded
    reference loses the reference, so the sentence reads "shown in ." A spec
    may name the exact fragment and the wording that replaces it. Every fix
    must match, so a stale repair cannot sit in the spec unnoticed.
    """
    for fix in fixes:
        find = fix["find"]
        if find in text:
            text = text.replace(find, fix["replace"])
            used.add(find)
    return text


def tidy_prose(text):
    """Drop the spaces the scraper leaves before a comma or a full stop."""
    return re.sub(r"[ \t]+([,.])", r"\1", text)


def source_blocks(document, module, solutions, manifest, caption_overrides=None,
                  keep_headings=None, drops=None, heading_drops=None,
                  prose_fixes=None, prose_tidy=False, used_fixes=None):
    """Teaching blocks, worked examples and exercises, from the source.

    `keep_headings` limits a section to the named source sections. A module
    often carries more than one teaching section, and a book section should
    not repeat the whole module for each slice it needs, so the spec may name
    the headings it wants and the rest of the module is skipped.

    `heading_drops` suppresses a heading the source split or truncated, while
    its blocks stay inside the heading above it. `prose_fixes` repairs the
    sentences the scraper broke when it lost an inline reference.
    """
    blocks = document["blocks"]
    source = document.get("source_attribution") or {}
    book = source.get("book") or ""
    teaching = []
    worked = []
    exercises = []
    pending = None
    grouping = None
    in_tail = False
    skip_exercise_prose = False
    seen_text: set[str] = set()
    skipped: list[tuple[str, str]] = []
    wanted_headings = {h.strip().lower() for h in keep_headings or []}
    current_heading: str | None = None
    drops = drops or ()

    def in_wanted_heading() -> bool:
        return (
            not wanted_headings
            or (current_heading is not None and current_heading in wanted_headings)
        )

    def provenance(locator):
        return {
            "publisher": source.get("publisher") or "OpenStax",
            "title": source.get("title") or source.get("book") or "",
            "url": source.get("url") or "",
            "locator": locator,
            "licence": source.get("licence") or "",
        }

    caption_overrides = caption_overrides or {}
    drops = drops or ()
    heading_drops = heading_drops or ()
    prose_fixes = prose_fixes or []
    used_fixes = used_fixes if used_fixes is not None else set()
    for block in blocks:
        kind = block.get("type")
        if kind in ("heading", "example", "exercise"):
            skip_exercise_prose = False
        if pending is not None and kind in ("heading", "example", "figure"):
            worked.append(pending)
            pending = None
        if kind == "heading":
            title = block["text"]["text"].strip()
            grouping = title
            if title.lower() in TAIL_HEADINGS:
                current_heading = title.strip().lower()
                in_tail = True
                continue
            if title in heading_drops:
                # The source split or truncated this heading. Its blocks stay
                # under the heading above it, so the reading order is kept.
                continue
            current_heading = title.strip().lower()
            if title in {"Learning Objectives"}:
                continue
            if in_tail:
                continue
            if wanted_headings and current_heading not in wanted_headings:
                continue
            teaching.append({"id": f"b-{len(teaching) + 1}", "type": "heading", "text": rt(title)})
        elif kind == "paragraph":
            if in_tail or not in_wanted_heading():
                continue
            text = block["content"]["text"].strip()
            if text.startswith("By the end of this section, you will be able to"):
                continue
            if pending is not None:
                pending["solution"].append(text)
                continue
            if skip_exercise_prose:
                continue
            if " ".join(text.split()).lower() in PLACEHOLDER_PARAGRAPHS:
                continue
            text = apply_prose_fixes(text, prose_fixes, used_fixes)
            if prose_tidy:
                text = tidy_prose(text)
            # A few of the repairs can only be recognised once the scraper's
            # stray spaces are gone, so run the fixes again on the tidy text.
            text = apply_prose_fixes(text, prose_fixes, used_fixes)
            if text in seen_text:
                continue
            seen_text.add(text)
            teaching.append({"id": f"b-{len(teaching) + 1}", "type": "paragraph", "content": rt(text)})
        elif kind == "figure":
            if in_tail or skip_exercise_prose or not in_wanted_heading():
                continue
            asset = block.get("asset_url") or ""
            if asset in drops:
                skipped.append((asset, "the section's figure_drops names it"))
                continue
            reason = book_media.was_rejected(manifest, asset)
            if reason:
                # A figure that failed the media rules does not ship, so it
                # does not teach. It is left out, and the manifest says why.
                skipped.append((asset, reason))
                continue
            published = book_media.published_for(manifest, asset)
            if published is None:
                raise SystemExit(
                    f"figure {asset} has not been published: run book/publish_book_images.py"
                )
            caption = block.get("caption") or {}
            if not str(caption.get("text") or "").strip():
                caption = rt(caption_overrides.get(asset, ""))
            teaching.append({
                "id": f"b-{len(teaching) + 1}",
                "type": "figure",
                "asset_url": published,
                "caption": caption,
                "alt": block.get("alt") or "",
                "licence": source.get("licence") or "",
            })
        elif kind == "example":
            if in_tail or not in_wanted_heading():
                continue
            pending = {
                "id": f"we-{block['id']}",
                "statement": rt((block.get("title") or {}).get("text", "")),
                "solution": [],
                "provenance": provenance(f"CNXML module {module}, worked example"),
            }
        elif kind == "exercise":
            skip_exercise_prose = True
            if not in_wanted_heading():
                continue
            key = f"{book}:{module}:{block['id']}"
            paragraphs = solutions.get(key)
            if not paragraphs:
                continue
            prompt = (block.get("prompt") or {}).get("text", "").strip()
            if not prompt:
                continue
            solution_text = render_parts(
                [p for paragraph in paragraphs for p in paragraph]
            )
            options = []
            if CHOICE_ANSWER.fullmatch(solution_text.strip()):
                choices = split_choices(prompt)
                if choices is not None:
                    prompt, choices = choices
                    options = [
                        {"id": chr(ord("a") + index), "text": text}
                        for index, text in enumerate(choices)
                    ]
            kind_label = classify(prompt)
            if kind_label == "application" or len(paragraphs) > 2:
                answer, answer_kind = render_parts(
                    [p for paragraph in paragraphs for p in paragraph]
                ), "explanation"
            else:
                answer, answer_kind = answer_from(paragraphs, kind_label)
            steps = []
            number = 0
            for paragraph in paragraphs:
                rendered = render_parts(paragraph)
                if rendered:
                    number += 1
                    steps.append({"step_number": number, "expression": rendered})
            exercises.append({
                "block_id": block["id"],
                "kind": kind_label,
                "stem": rt(prompt),
                "options": options,
                "answer": rt(answer),
                "answer_kind": answer_kind,
                "solution": steps,
                "provenance": provenance(f"CNXML module {module}, exercise block {block['id']}"),
                "solution_provenance": "OpenStax CNXML solution element (in file)",
                "grouping": grouping,
            })

    if pending is not None:
        worked.append(pending)
    for item in worked:
        if item.get("solution"):
            sentences = [
                part.strip()
                for part in re.split(r"(?<=[.!?])\s+", " ".join(item["solution"]))
                if part.strip()
            ]
            item["steps"] = [
                {"step_number": number, "expression": sentence}
                for number, sentence in enumerate(sentences, start=1)
            ]
            item["answer"] = rt(" ".join(item["solution"]))
            item.pop("solution", None)
    # An example block with no prose after it is an empty shell. Its content
    # sits in the exercise nested inside it, and that exercise carries the
    # solution.
    worked = [item for item in worked if item.get("steps")]
    return teaching, worked, exercises, skipped


def build(spec):
    manifest = book_media.load_manifest()
    sections = []
    exercises = []
    number = 0
    used_fixes: set[str] = set()

    for index, section_spec in enumerate(spec["sections"], start=1):
        section_id = section_spec["id"]
        module = section_spec.get("module")
        source_teaching = []
        source_worked = []
        source_exercises = []

        if module:
            document, solutions = find_source(module)
            if document is None:
                raise SystemExit(f"no source extract for module {module}")
            (
                source_teaching,
                source_worked,
                source_exercises,
                skipped,
            ) = source_blocks(
                document,
                module,
                solutions,
                manifest,
                section_spec.get("figure_captions", {}),
                section_spec.get("source_sections"),
                section_spec.get("figure_drops"),
                section_spec.get("heading_drops"),
                section_spec.get("prose_fixes"),
                section_spec.get("prose_tidy", False),
                used_fixes,
            )

        teaching = list(source_teaching)
        for position, block in enumerate(section_spec.get("blocks", []), start=len(teaching) + 1):
            block = dict(block)
            block.setdefault("id", f"b-{position}")
            teaching.append(block)

        worked = list(source_worked)
        for item in section_spec.get("worked", []):
            worked.append(item)

        plan = section_spec.get("exercise_plan", {})
        promoted = section_spec.get("worked_from")
        fixes = spec.get("exercise_fixes", {})
        section_exercises = []
        for source_exercise in source_exercises:
            # Fixes are keyed per section, because source block ids repeat
            # across the modules of a chapter.
            fix = fixes.get(f"{section_id}:{source_exercise['block_id']}", {})
            if fix.get("drop"):
                # The source exercise leans on a figure we do not ship, so it
                # cannot be solved from the section. It does not ship either.
                continue
            if not source_exercise["solution"]:
                # The source has the exercise but nothing readable for the
                # solution. An exercise without a solution is not an
                # exercise.
                continue
            if promoted == source_exercise["block_id"]:
                # The spec promotes one solved exercise to the worked
                # example of the section, so it is shown worked rather than
                # left as practice.
                worked.append({
                    "id": f"we-{source_exercise['block_id']}",
                    "statement": source_exercise["stem"],
                    "steps": source_exercise["solution"],
                    "answer": source_exercise["answer"],
                    "provenance": source_exercise["provenance"],
                })
                continue
            if plan and source_exercise["block_id"] not in plan:
                # The spec selects the exercises it wants from the module.
                continue
            number += 1
            exercise_id = f"ex-{section_id}-{len(section_exercises) + 1:02d}"
            override = plan.get(source_exercise["block_id"], {})
            tier = override.get("tier", tier_for_grouping(source_exercise.get("grouping")))
            if tier == "core" and source_exercise.get("grouping", "").lower().startswith("problems") \
                    and source_exercise.get("kind") == "application":
                # A multi part problem is the stretch of the set.
                tier = "stretch"
            default_difficulty = {"warm_up": 1, "core": 3, "stretch": 4}.get(tier, 3)
            difficulty = override.get("difficulty", default_difficulty)
            marks = override.get("marks", max(1, min(5, difficulty)))
            kind = override.get("kind", source_exercise["kind"])
            fix_stem = fix.get("stem")
            strip = fix.get("stem_strip")
            if strip:
                # The scraper glues the source's teaching title onto the
                # prompt of the exercise that follows it. The title is not
                # part of the question, so the fix names it and it goes.
                if not source_exercise["stem"]["text"].startswith(strip):
                    raise SystemExit(
                        f"{section_id}:{source_exercise['block_id']} stem does not start with {strip!r}"
                    )
                rendered_stem = rt(source_exercise["stem"]["text"][len(strip):].strip())
            elif fix_stem is None:
                rendered_stem = source_exercise["stem"]
            elif isinstance(fix_stem, str):
                rendered_stem = rt(fix_stem)
            else:
                rendered_stem = fix_stem
            fix_solution = fix.get("solution")
            if fix_solution is not None and fix_solution and isinstance(fix_solution[0], str):
                # A fix may supply plain solution sentences; shape them like
                # the source solution steps.
                fix_solution = [
                    {"step_number": index + 1, "expression": step}
                    for index, step in enumerate(fix_solution)
                ]
            exercise = {
                "id": exercise_id,
                "section_id": section_id,
                "tier": tier,
                "kind": kind,
                "difficulty": difficulty,
                "marks": marks,
                "stem": rendered_stem,
                "options": fix.get("options", source_exercise.get("options", [])),
                "answer": rt(fix["answer"]) if fix.get("answer") else source_exercise["answer"],
                "answer_kind": fix.get("answer_kind", source_exercise["answer_kind"]),
                "solution": fix_solution or source_exercise["solution"],
                "tags": section_spec.get("tags") or [slugify(section_spec["title"])],
                "provenance": source_exercise["provenance"],
                "solution_provenance": fix.get(
                    "solution_provenance", source_exercise["solution_provenance"]
                ),
            }
            hints = override.get("hints")
            if hints:
                exercise["hints"] = [
                    {"hint_number": index + 1, "text": rt(hint)}
                    for index, hint in enumerate(hints)
                ]
            section_exercises.append(exercise)

        # Exercises we write ourselves. They are used when the source has no
        # readable solution, when a section needs a warm-up, or when a
        # section has fewer than three exercises. The prompt and the solution
        # are ours, so the provenance says so.
        for authored in section_spec.get("authored_exercises", []):
            number += 1
            exercise_id = f"ex-{section_id}-{len(section_exercises) + 1:02d}"
            tier = authored.get("tier", "core")
            default_difficulty = {"warm_up": 1, "core": 3, "stretch": 4}.get(tier, 3)
            difficulty = authored.get("difficulty", default_difficulty)
            steps = []
            for step_number, expression in enumerate(authored.get("solution", []), start=1):
                steps.append({"step_number": step_number, "expression": expression})
            exercise = {
                "id": exercise_id,
                "section_id": section_id,
                "tier": tier,
                "kind": authored.get("kind", "numeric"),
                "difficulty": difficulty,
                "marks": authored.get("marks", max(1, min(5, difficulty))),
                "stem": rt(authored["stem"]),
                "options": authored.get("options", []),
                "answer": rt(authored["answer"]),
                "answer_kind": authored.get("answer_kind", "expression"),
                "solution": steps,
                "tags": authored.get("tags") or section_spec.get("tags") or [slugify(section_spec["title"])],
                "provenance": {
                    "publisher": "UTME-Lab",
                    "title": spec.get("authored_source_title", "Secondary Physics"),
                    "url": (
                        "https://api.utmelab.com/api/v1/chapters/"
                        f"{spec['chapter_id']}/sections/{section_id}"
                    ),
                    "locator": f"authored exercise for {section_id}",
                    "licence": spec.get("licence", ""),
                },
                "solution_provenance": authored.get(
                    "solution_provenance",
                    "authored by UTME-Lab and checked against the section's teaching text",
                ),
            }
            hints = authored.get("hints")
            if hints:
                exercise["hints"] = [
                    {"hint_number": index + 1, "text": rt(hint)}
                    for index, hint in enumerate(hints)
                ]
            section_exercises.append(exercise)

        # Worked example fixes are keyed per section, because source block ids
        # repeat across the modules of a chapter. They apply after promotion,
        # so a fixed exercise that becomes the section's worked example is
        # fixed too. They can drop an example, or replace its statement, steps
        # and answer.
        worked_fixes = spec.get("worked_fixes", {})
        fixed_worked = []
        for item in worked:
            fix = worked_fixes.get(f"{section_id}:{item['id']}", {})
            if fix.get("drop"):
                continue
            item = dict(item)
            statement = fix.get("statement")
            if statement is not None:
                item["statement"] = rt(statement)
            steps = fix.get("steps")
            if steps is not None:
                item["steps"] = [
                    {"step_number": number, "expression": step}
                    for number, step in enumerate(steps, start=1)
                ]
            answer = fix.get("answer")
            if answer is not None:
                item["answer"] = rt(answer)
            fixed_worked.append(item)
        worked = fixed_worked

        section_exam_links = [
            dict(link) for link in section_spec.get("exam_links", [])
        ]
        sections.append({
            "id": section_id,
            "order": index,
            "slug": section_spec.get("slug", slugify(section_spec["title"])),
            "title": section_spec["title"],
            "est_minutes": section_spec.get("est_minutes", 10),
            "facts_inherited": bool(section_spec.get("facts_inherited")),
            "learning_objectives": [
                {"id": f"lo-{position}", "statement": objective, "bloom_level": section_spec.get("bloom_level", "understand")}
                for position, objective in enumerate(section_spec.get("objectives", []), start=1)
            ],
            "teaching_text": {"blocks": teaching},
            "worked_examples": worked,
            "misconceptions": [
                {
                    "id": f"mis-{position}",
                    "claim": rt(item["claim"]),
                    "correction": rt(item["correction"]),
                    **({"signal": rt(item["signal"])} if item.get("signal") else {}),
                    "provenance": {
                        "publisher": spec.get("publisher", "OpenStax"),
                        "title": spec.get("source_title", spec.get("title")),
                        "url": spec.get("source_url", ""),
                        "locator": item.get("locator") or section_spec.get("locator", ""),
                        "licence": spec.get("licence", ""),
                    },
                }
                for position, item in enumerate(section_spec.get("misconceptions", []), start=1)
            ],
            "summary_points": [rt(point) for point in section_spec.get("summary", [])],
            "exercise_ids": [exercise["id"] for exercise in section_exercises],
            "exam_links": section_exam_links,
            "provenance": {
                "publisher": spec.get("publisher", "OpenStax"),
                "title": spec.get("source_title", spec.get("title")),
                "url": spec.get("source_url", ""),
                "locator": section_spec.get("locator", spec.get("source_locator", "")),
                "licence": spec.get("licence", ""),
            },
        })
        if section_spec.get("no_worked_example_reason"):
            sections[-1]["no_worked_example_reason"] = section_spec["no_worked_example_reason"]
        if section_spec.get("no_exercise_reason"):
            sections[-1]["no_exercise_reason"] = section_spec["no_exercise_reason"]
        if section_spec.get("no_exam_link_reason"):
            sections[-1]["no_exam_link_reason"] = section_spec["no_exam_link_reason"]
        exercises.extend(section_exercises)

    # The chapter holds the union of its sections' exam links, so a reader of
    # the chapter sees the whole exam picture at once.
    union = {}
    for section in sections:
        for link in section.get("exam_links", []):
            key = (link.get("exam"), link.get("subject"), link.get("topic_slug"), link.get("subtopic_slug"))
            if key not in union:
                union[key] = dict(link)
    if not union and spec.get("exam_links"):
        union = {
            (link.get("exam"), link.get("subject"), link.get("topic_slug"), link.get("subtopic_slug")): dict(link)
            for link in spec["exam_links"]
        }
    chapter_links = sorted(
        union.values(),
        key=lambda link: (link.get("exam") or "", link.get("topic_slug") or "", link.get("subtopic_slug") or ""),
    )

    traps = []
    for trap in spec.get("exam_traps", []):
        traps.append({
            "id": trap["id"],
            "exam": trap["exam"],
            "subject": trap["subject"],
            "section_id": trap["section_id"],
            "misconception": rt(trap["misconception"]),
            "correction": rt(trap["correction"]),
            "signal": rt(trap["signal"]),
            "paper_evidence": trap["paper_evidence"],
            "status": trap.get("status", "proven"),
            "frequency": trap.get("frequency", "occasional"),
            "provenance": {
                "publisher": (
                    "West African Examinations Council (WAEC)"
                    if trap["exam"] == "WAEC"
                    else "Joint Admissions and Matriculation Board (JAMB)"
                    if trap["exam"] == "JAMB"
                    else trap["exam"]
                ),
                "title": (
                    f"{trap['exam']} {trap.get('subject', 'Physics').title()} {trap['paper_evidence']['year']}"
                    if trap["paper_evidence"].get("year")
                    else f"{trap['exam']} {trap.get('subject', 'Physics').title()} past paper"
                ),
                "url": trap["paper_evidence"].get("url") or (
                    "https://api.utmelab.com/api/v1/chapters/"
                    f"{spec['chapter_id']}/sections/{trap['section_id']}"
                ),
                "locator": (
                    f"paper question {trap['paper_evidence']['question_id']}"
                    if trap["paper_evidence"].get("question_id")
                    else f"our practice question {trap['paper_evidence'].get('check_id')}"
                ),
                "licence": (
                    "Past-paper question quoted for evidence; rights remain with the "
                    "examination board."
                ),
            },
        })

    recall = []
    for check in spec.get("exam_recall_checks", []):
        recall.append({
            "id": check["id"],
            "exam": check["exam"],
            "subject": check["subject"],
            "section_id": check["section_id"],
            "stem": rt(check["stem"]),
            "options": check["options"],
            "answer": check["answer"],
            "explanation": rt(check["explanation"]),
            "difficulty": check.get("difficulty", 2),
            "source": check.get("source", ""),
        })

    chapter = {
        "chapter_id": spec["chapter_id"],
        "schema_version": 2,
        "updated_at": spec.get("updated_at", "2026-11-12"),
        "title": spec["title"],
        "book_id": spec["book_id"],
        "part_id": spec.get("part_id"),
        "order": spec.get("order"),
        "facts_inherited": bool(spec.get("facts_inherited")),
        "learning_objectives": [
            objective if isinstance(objective, dict)
            else {"id": f"lo-{position}", "statement": objective, "bloom_level": spec.get("bloom_level", "understand")}
            for position, objective in enumerate(spec.get("learning_objectives", []), start=1)
        ],
        "prerequisites": spec.get("prerequisites", []),
        "formula_sheet": spec.get("formula_sheet", []),
        "glossary": spec.get("glossary", []),
        "sections": sections,
        "exercises": exercises,
        "exam_links": chapter_links,
        "exam_traps": traps,
        "exam_recall_checks": recall,
        "sources": spec.get("sources", []),
    }
    for key in ("no_formula_reason", "no_exam_link_reason", "no_trap_reason"):
        if spec.get(key):
            chapter[key] = spec[key]

    declared = [
        fix["find"]
        for section_spec in spec["sections"]
        for fix in section_spec.get("prose_fixes", [])
    ]
    unused = [find for find in declared if find not in used_fixes]
    if unused:
        raise SystemExit(
            "prose_fixes did not match the source:\n"
            + "\n".join(f"    {find!r}" for find in unused)
        )
    return chapter


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("spec")
    parser.add_argument("--check", action="store_true", help="fail if the built chapter differs from the file on disk")
    args = parser.parse_args()

    spec = json.loads(Path(args.spec).read_text())
    chapter = build(spec)
    target = CHAPTERS / f"{spec['chapter_id']}.json"
    rendered = json.dumps(chapter, ensure_ascii=False, indent=2) + "\n"

    if args.check:
        current = target.read_text() if target.exists() else ""
        if current != rendered:
            print(f"{target} differs from its spec")
            raise SystemExit(1)
        print(f"{target} matches its spec")
        return

    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(rendered)
    figures = sum(
        1
        for section in chapter["sections"]
        for block in section["teaching_text"]["blocks"]
        if block["type"] == "figure"
    )
    print(
        f"wrote {target}: {len(chapter['sections'])} sections, "
        f"{len(chapter['exercises'])} exercises, {figures} figures"
    )


if __name__ == "__main__":
    main()
