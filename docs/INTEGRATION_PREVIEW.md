# Group F integration preview

This branch combines the exact source snapshots of PR #1 (8df74f4), PR #2 (17d95a4), and PR #3 (750b532), without changing their module code or the shared schemas. It adds an integration workflow. The repository owner's request authorizes this preview only; it is not evidence of three-member approval.

## Run

From the repository root with Python 3.10+:

```sh
python -m pip install -r requirements-dev.txt
python -m unittest discover -s tests -v
python -m tests.model.run_end_to_end --output-dir integration-output
```

The end-to-end runner calls the real semantic, layout, and renderer modules using five resolved Mock Converter cases and emits SMD JSON, Layout JSON and SVG. CI uploads these outputs on success. The browser demo is at `demo/index.html`; it is a preview, not the formal Converter integration.

## Acceptance still pending

- Three-member review of the draft interface and module changes.
- Formal R/S Converter output, real Process Algebra semantics and instructor examples; see `src/model/CONVERTER_HANDOFF.md`.
- Recheck the reported Fork/Join anchor gap and UML pseudostate notation, plus routing/label quality. Previous visual defects are not assumed fixed by this integration.
- Re-run tests against the merged commit before formal acceptance. Earlier reported 57 passing tests used an older Layout commit and do not certify this snapshot.

Original PRs and main remain available for review. No groupctl consensus is asserted here.
