# Book Release Workflow

Status: Active  
Last updated: 2026-11-14

This is the process for shipping book content: a new chapter, a rebuilt
chapter, or a correction to one. It keeps authoring local until the gate is
green, keeps the media publish separate from deployment, and makes the
importer's success visible instead of assumed.

The companion contract for concepts and notes is
[`CONTENT-WORKFLOW-CONTRACT.md`](CONTENT-WORKFLOW-CONTRACT.md). This document
covers only what reaches readers through the API's textbook endpoints.

## The rule in one line

Coverage work writes to local files only. A release window is the only time the
work touches a remote, and the gate must be green before the window opens.

## Phases

### 1. Coverage (local, on a branch)

Build and refine the chapter on a branch. Nothing here touches a remote:

- the spec in `data/chapter-specs/`;
- the source extracts in `data/chapter-sources/`;
- the built chapter in `data/chapters/`;
- the builder in `book/build_chapter.py`.

Run `book/build_chapter.py` as often as needed. The spec is the source of
truth; a hand edit to a built chapter is a last resort and goes into the spec
as soon as the reason is understood, or the chapter is added to the stale list
in `book/release_check.py`.

### 2. Figures (dry run until the batch is approved)

The builder refuses to build a chapter whose figures are not in
`data/book-images.json`, because it bakes the published URL into the chapter.
The media store is therefore the one remote a coverage phase can need. Handle
it in two steps:

```bash
# While authoring: check what would be published, write nothing.
python3 book/publish_book_images.py --book <book_id> --module <module> --dry-run

# Only once the batch is approved: publish, which writes the manifest.
python3 book/publish_book_images.py --book <book_id> --module <module>
```

A publish adds bytes and a commit to the media project. It changes nothing
that users read: the API still serves the previous chapter until the import.
A figure that is already published costs one dry-run and no remote write.

### 3. Gate (local)

```bash
python3 book/release_check.py
```

The script refuses (exit 1) unless all three checks hold:

- `book/validate_chapters.py` reports `errors 0` for every built chapter;
- every spec passes `book/build_chapter.py <spec> --check`, except the specs
  on its `KNOWN_STALE` list (see below);
- `book/bundle_chapters.py` writes a bundle covering every built chapter.

The same script runs in CI as the content gate, so a red local gate and a red
CI run mean the same thing.

`KNOWN_STALE` is a debt list, not a waiver. It currently holds
`math_number_bases.json` and `math_laws_of_indices_and_surds.json`, whose
chapters were hand-refined after they were built. The validator still checks
those chapters structurally; only spec equality is waived. An entry that
starts matching its spec triggers a warning so the list cannot outlive its
reason.

### 4. Release window (push and import together)

One window, after the gate is green, with the bundle frozen:

```bash
git add <the changed content files>
git commit -m "feat(content): ..."
git push

# from the API repository, with its .env loaded
cargo run --quiet -- import-chapters /path/to/data/staging/chapters-bundle.json
```

The push is version control, not deployment. The import is the deployment.
Capture its success line. The importer prints

```
imported 37 chapters and 2 books from ...
```

A silent importer is a failed import, not a quiet success. If the line is
missing, stop: do not verify, do not announce. Re-run the import and read the
line.

Do not rebuild, edit, or republish between the gate and the import. If any
file changes, the gate runs again.

### 5. Verification (read production back)

```bash
export UTMELAB_API_KEY=...   # or UTMELAB_DEV_API_KEY
python3 book/verify_release.py --book <book_id>
```

This reads the API and compares it with the bundle that was imported: book
chapter order, chapter order and section index, every exercise and its
solution, each section's figure count and exam links, each figure URL, and
each exam trap's status, frequency and provenance. It fails on any difference.

The first request after an import can answer 408 while the replica wakes. The
script retries that code; anything else is a real failure.

Only after `PRODUCTION MATCHES THE BUNDLE` is the release done. If
verification fails, fix forward with a corrected bundle and a new import. The
import replaces a chapter's children wholesale, so re-importing an earlier
bundle is also a valid rollback.

## Why the order matters

- The gate cannot see a half-applied import. Only step 5 can.
- The media publish is safe before the batch because nothing references the
  new figures until the import. It is the only remote action that coverage
  needs, and it is not deployment.
- A push without an import changes nothing users read; an import without a
  verified gate ships unverified content. Keeping them in one window means the
  committed tree and the served content are the same thing.
