# UTME Lab content

This repository prepares and validates the content served by the
[UTME Lab API](https://github.com/shedrackgodstime/utmelab-api).

It holds two pipelines that share one checkout and one data directory:

- `utmelab-bank/` is the exam question bank. It fetches source papers, captures
  figures, tags and explains questions, reviews them, and hands approved rows to
  the production catalogue. See [`utmelab-bank/README.md`](utmelab-bank/README.md).
- `book/` is the textbook factory. It rebuilds chapters and books from the
  tracked source extracts in `data/chapter-sources/`, checks them against the
  chapter specs, and publishes validated figures to the media project. See
  [`docs/CONTENT-BOOK-SCHEMA.md`](docs/CONTENT-BOOK-SCHEMA.md).

`data/` is the shared content directory: chapters, books, packs, chapter
specs, source extracts, coverage reports, and the published figure manifest.
The API keeps its own copy in Turso. This repository is the authoring and
review side.

## Install

The bank is a Python 3.14 package:

```bash
cd utmelab-bank
python3 -m venv .venv
. .venv/bin/activate
pip install -e ".[dev]"
```

The book scripts use the same interpreter and dependencies, and are run from
the repository root:

```bash
python3 book/validate_chapters.py
for spec in data/chapter-specs/*.json; do
  python3 book/build_chapter.py "$spec" --check
done
```

## Checks

```bash
cd utmelab-bank
ruff format --check src tests
ruff check src tests
mypy src/utmelab_bank
pytest
```

The content gate is the two book commands above. Both run in
`.github/workflows/quality.yml` on every push and pull request.

## Boundaries

The API repository holds the Rust service and the public site. It does not hold
the bank, the book scripts, or the content data.

The GitLab project `shedrackgodstime/utmelab-bank` is separate again: it stores
published images under `images/` and `books/`. This GitHub repository stores
the code that publishes and verifies them.

## Bank operations

The bank workflows are manual. They run against the isolated bank database and
read production with a read-only token, except where a migration is explicitly
scoped. See [`utmelab-bank/README.md`](utmelab-bank/README.md) and the
workflows in `.github/workflows/` for the exact commands.
