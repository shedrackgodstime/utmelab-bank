# Mathematics book backlog

Date: 2026-11-15

This is the work still owed on the Secondary Mathematics book: the chapters that
come next, the two chapters whose specs no longer rebuild, one catalog defect in
production, and the blockers that decide what can be done now.

## Where the book stands

| Order | Part | Chapter | Sections | Exercises | State |
|---:|---|---|---:|---:|---|
| 1 | Number and Algebra | Number Bases | 7 | 29 | imported |
| 2 | Number and Algebra | Sets | 8 | 34 | imported |
| 3 | Number and Algebra | Laws of Indices and Surds | 9 | 50 | imported, spec stale |
| 4 | Geometry and Measurement | Trigonometry | 12 | 74 | imported |
| 5 | Geometry and Measurement | Coordinate Geometry | 6 | 39 | built, gate green, not imported |

Totals for the five chapters: 42 sections, 226 exercises, 112 recall checks,
11 exam traps. The two chapters still stale are the two math chapters in
`KNOWN_STALE` in `book/release_check.py`.

Production currently serves 2 books and 38 chapters. An import of this checkout
would make it 39.

## Coordinate Geometry (built, awaiting a window)

Sources: OpenStax *College Algebra 2e*, CNXML modules `m51252` (coordinate plane,
distance, midpoint) and `m51270` (linear functions, gradient, equations of lines,
parallel and perpendicular lines), both in the
`osbooks-college-algebra-bundle` repository.

Shape: 6 sections, 39 exercises (36 from the source, 3 authored), 6 worked
examples (one per section, each promoted from a fully solved source exercise),
24 recall checks, 8 formulas, 21 glossary entries, 15 figures, 0 traps with a
recorded `no_trap_reason`.

Verification done by hand against the source solutions: distances
(`5√5`, `√74`, `6`, `62.97`, `5`, `37` miles, `54` ft), midpoints, gradients
(`2`, `-2`, `-10`), rates of change (`1,100` and `142` people per year),
equations (`y=-7x+3`, `y=3x-2`, `y=-1.5x-3`, `y=10x-24`, `y=3x-3`,
`y=-(1/3)t+2`, `y=100x-98`), intercepts, and the parallel/perpendicular
verdicts.

Build evidence:

```
python3 book/build_chapter.py data/chapter-specs/math_coordinate_geometry.json
wrote data/chapters/math_coordinate_geometry.json: 6 sections, 39 exercises, 15 figures
python3 book/validate_chapters.py   -> files 39, errors 0
python3 book/release_check.py       -> GO, 37 pass, 2 known stale, 0 unexpected
```

Figures: 49 source figures for the two modules are published in the media
project. `data/book-images.json` now records 1,530 figures and 1 rejection.

## Next chapters: part 2, Geometry and Measurement

### Mensuration

The OpenStax shelf covers areas, volumes and surface areas, and the existing
concepts already carry those. Still unsourced: the earth as a sphere, longitudes
and latitudes, distances along great circles, and several arc, sector and chord
specifics that the WAEC syllabus names. This needs a new source with a recorded
URL and locator before the chapter can be built, not a reshaping of what exists.

### Euclidean geometry

Points, lines, angles and triangles are covered. Missing: circle theorems, cyclic
quadrilaterals, intersecting chords, the full polygon scope, and construction.
Construction is the hardest gap because a book chapter needs either a source
that teaches the compass and straightedge steps or a deliberate reason to leave
the topic out.

### Vectors

No chapter source has been selected. OpenStax vector material exists in the
calculus and precalculus shelves, but the syllabus wants the secondary treatment
(vector notation, addition, scalar multiplication, position vectors, and simple
applications). A source pass is the first task.

## Trigonometry follow-ons

The shipped chapter covers angles, radians, coterminal angles, arc length,
sector area, angular and linear speed, right-triangle ratios, the unit circle,
special angles, reference angles, the six functions and even/odd symmetry. Not
yet in the book:

- the sine rule and the cosine rule, including the ambiguous case;
- bearings as a coordinate and triangle topic;
- angles of elevation and depression as a modelling topic;
- graphs of sine and cosine, amplitude, period and phase;
- triangle area from two sides and the included angle.

Each of these needs its own source and its own exercise set. The bank is dark
this month, so any chapter built now ships with `no_trap_reason` and no proven
traps.

## Part 3: Statistics and Probability

`Introductory Statistics` is the obvious source and three statistics concepts
already exist. Hold this until the catalog defect below is fixed, because part of
the statistics syllabus is currently attached to a trigonometry topic.

## Spec debt: the two stale chapters

Both chapters were built before the builder learned to stop at the source's back
matter, so a rebuild today changes them. Measured on 2026-11-15 by building each
spec in memory and comparing with the stored chapter:

- `math_number_bases`: the rebuild would drop 42 stored-only teaching blocks
  (the duplicated "Key Equations", "Key Concepts" and "Section Exercises" tails).
  The 29 exercises, 30 worked examples and all chapter fields are identical.
- `math_laws_of_indices_and_surds`: the rebuild would drop 704 stored-only tail
  blocks, and the 11 exam traps carry hand-tuned fields the spec does not
  reproduce (for example `trap-1` is `occasional` in the chapter and `recurring`
  from the spec). The 50 exercises and 35 worked examples are identical.

Two ways out, both needing a review pass:

1. Rebuild from the spec, then re-apply the trap tuning and check the prose by
   hand. Removes the debt permanently.
2. Regenerate the specs so they name the source tail sections and reproduce the
   trap fields, then rebuild. Keeps the stored chapters intact.

`release_check.py` only waives spec equality for these two. The validator still
checks them structurally, so neither is broken, just not rebuildable.

## Production defect: WAEC catalog misgrouping

Topic `waec-angles-of-elevation-and-depression` (ord 29, weight 0) owns ten
subtopics. Four belong there:

- `waec-calculating-angles-of-elevation-and-depression`
- `waec-application-to-heights-and-distances`
- `waec-bearing-of-one-point-from-another`
- `waec-calculation-of-distances-and-angles`

Six do not:

- `waec-differentiation-of-algebraic-functions`
- `waec-frequency-distribution`
- `waec-pie-charts-bar-charts-histograms-and-frequency-polygons`
- `waec-mean-median-and-mode-for-both-discrete-and-grouped-data`
- `waec-cumulative-frequency-curve-ogive`
- `waec-measures-of-dispersion-range-semi-inter-quartile-inter-quart`

Measured impact:

- 9 tracked concept files carry 24 WAEC placements under this topic. Twelve of
  those placements point at the six misplaced subtopics: three each from
  `math_statistics_location` and `math_statistics_graphs`, three from
  `math_statistics_histograms`, and one each from `math_differentiation_rules`,
  `math_differentiation_defining` and `math_measures_of_dispersion`.
- `data/generated-notes/prod-topic-notes-math.json` holds 10 notes for the topic,
  one per subtopic, so six of them are differentiation or statistics notes that
  would appear under angles of elevation and depression if imported.

This cannot be fixed inside this repository alone. The subtopics have to move to
their real topics in the catalog first, outside this repo. After that: re-point
the placements in the nine concept files, regenerate the notes, re-run
`book/validate_notes.py`, and import in an approved window.

Note for whoever picks this up: `docs/MATH-COVERAGE-AUDIT.md` is out of date on
this point. It reports 233 notes and says six subtopics are missing notes. The
current file has 239 notes and all ten subtopics have one, which is why the six
wrong notes matter.

## Blockers

1. **Past-paper bank quota.** Exhausted until next month. No new past-paper
   evidence, no new proven traps, no verified frequency labels for any new
   chapter. Chapters built now ship with `no_trap_reason` only.
2. **Eight unset secrets.** `NVIDIA_API_KEY_01` to `05` and three
   `GROQ_API_TOKEN` values are missing, so the pipelines that depend on them stay
   dark.
3. **Release windows.** Import and deploy need an approved window. No production
   database read or write happens outside one.
4. **Catalog change.** The WAEC misgrouping above is a production catalog edit
   and has its own approval path.

## Next actions, in order

1. Import Coordinate Geometry in the next approved window, then run
   `python3 book/verify_release.py --book secondary_mathematics` and confirm
   production matches the bundle.
2. Write the backlog chapter that needs no new source: pick between Mensuration
   and Euclidean geometry based on which gap is smaller, and record the missing
   sub-topics as explicit holds rather than inventing them.
3. Fix the WAEC catalog misgrouping, then regenerate the affected notes.
4. Clear the two stale specs, starting with `math_number_bases` because its diff
   is only the dropped back matter.
5. Revisit Trigonometry follow-ons and part 3 statistics once the bank is back
   and the catalog is clean.
