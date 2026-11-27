# Phase 3 baseline

Captured from integrated main at 5b1eefd7d8aefaccedcbacbd3dc92b7fa609f244. On Windows, the original 58 tests pass with Python UTF-8 mode. A fixture reader otherwise depends on the system code page and can fail on Chinese text.

```powershell
python -X utf8 -m unittest discover -s tests -q
python -X utf8 -m tests.model.run_end_to_end --output-dir benchmarks/baseline
```

The five outputs cover linear and guarded behavior, nested composites, orthogonal regions and pseudostates. Observed issues include composite fills covering internal routes, a measured 9.12-unit gap at two Fork/Join anchors, and deviations in Junction, Terminate and connection-point notation. Layout follows the input order, recomputes nested dimensions, and can fall back to a route without checking its intersections. The browser demo maintains a second SVG implementation, which can disagree with Python. Existing SMD validation preserves symbolic behavior and reports unresolved Grammar without silently converting it.
