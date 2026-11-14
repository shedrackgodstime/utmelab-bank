# Secondary Physics Completion Contract

Status: Active
Last updated: 2026-11-12

This document defines what "Physics is done" means. A green chapter build, a
passing schema validator, or a clean repository move does not meet this bar.
The book is done only when every rule below passes in `book/verify_physics.py`,
the independent audit finds no blocking defect, and the same checks pass from
a clean checkout.

Nothing is pushed or deployed while a rule is failing.

## 1. Book shape

- One book, `secondary_physics`, with 34 chapters.
- The book has a declared part for every chapter. Part ids are `part-1` to
  `part-N`, contiguous, with unique order values and non-empty titles.
- Every chapter carries an `order` value. Orders are unique and match the
  order of the `chapters` array in the book.
- The reading order is a teaching order, not an alphabetical order.
- Chapter 1 is `phy_nature_of_science`, the introduction to science,
  physical quantities, units, accuracy, precision, significant figures and
  approximation.
- Chapter prerequisites form an acyclic graph. Every chapter except the first
  names at least one earlier chapter.
- No chapter names an exam at its root.

## 2. Chapter completeness

Every chapter has:

- at least two chapter learning objectives;
- a formula sheet with every formula the chapter uses, or a written
  `no_formula_reason` for a chapter that genuinely has no formulas;
- a glossary with every key term the chapter introduces;
- at least one misconception;
- at least one recall check;
- at least one exam link, or a written `no_exam_link_reason` for a
  foundational chapter that no exam examines;
- at least one source, with publisher, title, URL, locator and licence.

Every teaching section has:

- at least two learning objectives;
- teaching text with at least 120 words of prose;
- at least one worked example, or a written `no_worked_example_reason`;
- at least one misconception;
- at least one recall check;
- at least one exam link, or a written `no_exam_link_reason`;
- at least two summary points;
- at least three exercises.

A chapter introduction is an opener, not a teaching unit. It has at least
one objective, at least 40 words of prose, at least two summary points, and a
worked example or a written reason. It is exempt from the exercise,
misconception, recall-check and exam-link requirements.

Every chapter has at least three warm-up, three core and three stretch
exercises. A warm-up belongs to the chapter's exercise set, not to every
section. Difficulty and tier must agree:

| tier | difficulty |
|------|------------|
| warm_up | 1 or 2 |
| core | 3 |
| stretch | 4 or 5 |

## 3. Exercise completeness

Every exercise has:

- a non-empty stem, answer and at least one solution step;
- a listed section that exists in the same chapter;
- a tier, a difficulty, positive marks and at least one tag;
- complete provenance and solution provenance;
- no duplicate stem within its chapter.

An exercise without a solution is not an exercise and must not ship. A source
exercise whose solution we wrote ourselves is marked as authored in
`solution_provenance`; the prompt keeps its source provenance.

A stem must stand on its own. The gate fails an exercise that:

- leans on a figure, graph, table or diagram the book does not carry, or
  keeps a flattened reference such as `shown in .`, `(See .)` or
  `as claimed in .`;
- contains its own answer text;
- holds placeholder text (`click to view`, `TODO`, and friends);
- offers multiple-choice options whose ids are not `a, b, c, ...`, whose
  option texts are empty or duplicated, or whose answer letters do not all
  match a listed option.

## 4. Exam side

- Every exam trap is `proven`.
- Every proven trap cites `claimed_paper` evidence with a real question id
  matching `q_...`, an exam that matches the trap exam, a year and an absolute
  URL. A placeholder such as `waec` is not evidence.
- No candidate trap ships in a chapter. Candidate material is kept as a
  section misconception until a paper question proves it.
- Every recall check has a stem, at least two options, one answer that is one
  of those options, an explanation, a difficulty and a source.
- Every trap and recall check points at a section that exists.

## 5. Figures and sources

- Every figure in a chapter is in the published manifest, filed under
  `books/secondary_physics/`, not rejected, and has alt text and a caption.
- Every source module named by a spec has a tracked extract in
  `data/chapter-sources/`.
- Every chapter rebuilds byte for byte from its spec and tracked source with
  `book/build_chapter.py --check`.
- Every source URL is absolute, uses https, and is not a PDF.
- The source licence and attribution are present on every chapter, section,
  figure, exercise and worked example.

## 6. Syllabus coverage

- Every WAEC and JAMB physics topic in the coverage map is either mapped to at
  least one section or marked `not_examined` with evidence.
- No topic is left as `no_source`.
- Simple Machines and Vapours and hygrometry are sourced from a reliable
  web-based textbook, not a PDF and not a hand-written assertion.
- The coverage map and the book agree: every mapped section exists, and every
  chapter with exam links maps to a real topic.

## 7. Reproducibility

From a clean checkout with no ignored concept or staging files:

- all 34 chapters rebuild exactly;
- `book/validate_chapters.py` reports zero errors;
- `book/verify_physics.py` reports zero blocking findings;
- the bundle builds;
- the API imports the bundle and returns 34 chapters in book order, with every
  `part_id` resolving to a declared part;
- the textbook, chapter, exercise, trap, recall and practice routes return
  the expected data for a sample of chapters.

## 8. Independent audit

A separate reviewer, not the author of the fixes, reads the whole book and
checks:

- factual accuracy of every formula, worked example and exercise answer;
- that every exercise is solvable from the section that lists it;
- that every trap is supported by the cited paper question;
- that every syllabus mapping is honest;
- that no section is a stub, a duplicate or a source dump without teaching.

Blocking findings are fixed and the full gate is rerun. The book is not marked
done while any blocking finding remains.

## 9. The rule that matters

A passing check is evidence, not a finish line. The gate must pass twice: once
after the last fix, and once from a clean checkout. A second, independent pass
must agree. Only then does Physics get marked done and pushed as one batch.
