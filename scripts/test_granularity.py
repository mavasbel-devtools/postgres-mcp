"""Report the test granularity of the feature specifications.

The inventory is the feature files: tests/features holds one file per use
case, named <use_case>.feature, each with exactly one positive and one
negative scenario. The bindings are the component and live suites that
subscribe to those scenarios.

Tags follow the x-mcp convention (one line of @-tags directly above each
Scenario/Scenario Outline):
    @feature-<feature>.<use_case> @scenario-<positive|negative> @dependency-<dep>

The report fails when a use case file names a different use case than its
scenarios, a use case has no positive or no negative scenario, or a use
case has no component or no live binding.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

REPOSITORY = Path(__file__).resolve().parents[1]
FEATURES = REPOSITORY / "tests" / "features"
COMPONENT = REPOSITORY / "tests" / "component"
LIVE = REPOSITORY / "tests" / "live"


@dataclass(frozen=True)
class Scenario:
    feature: str
    use_case: str
    polarity: str
    dependency: str


def _fields(tags: list[str]) -> Scenario | None:
    feature_use_case = next(
        (tag.removeprefix("feature-") for tag in tags if tag.startswith("feature-")),
        "",
    )
    feature, _, use_case = feature_use_case.partition(".")
    polarity = next(
        (tag.removeprefix("scenario-") for tag in tags if tag.startswith("scenario-")),
        "",
    )
    dependency = next(
        (tag.removeprefix("dependency-") for tag in tags if tag.startswith("dependency-")),
        "",
    )
    if not feature or not use_case or polarity not in {"positive", "negative"}:
        return None
    return Scenario(
        feature=feature, use_case=use_case, polarity=polarity, dependency=dependency
    )


def read_scenarios(path: Path) -> list[Scenario]:
    """Return the scenarios of one feature file, with their tags."""
    scenarios: list[Scenario] = []
    tags: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped.startswith("@"):
            tags = [tag.removeprefix("@") for tag in stripped.split()]
            continue
        if stripped.startswith("Scenario:") or stripped.startswith("Scenario Outline:"):
            scenario = _fields(tags)
            if scenario is None:
                raise SystemExit(f"gap: {path}: a scenario lacks a feature tag or polarity")
            scenarios.append(scenario)
            tags = []
    if not scenarios:
        raise SystemExit(f"gap: {path}: no scenario")
    return scenarios


def bindings(use_case: str) -> tuple[bool, bool]:
    return (
        (COMPONENT / f"test_{use_case}.py").exists(),
        (LIVE / f"test_{use_case}.py").exists(),
    )


def main() -> int:
    problems: list[str] = []
    rows: list[str] = []
    use_cases = scenarios = positives = negatives = 0

    files = sorted(FEATURES.glob("*.feature"))
    if not files:
        print("gap: tests/features holds no use case file")
        print("granularity: incomplete")
        return 1
    for path in files:
        found = read_scenarios(path)
        cases = {scenario.use_case for scenario in found}
        if len(cases) != 1 or path.stem not in cases:
            problems.append(
                f"gap: {path.name} names use cases {sorted(cases)} "
                f"but the file stem is {path.stem}"
            )
        for use_case in sorted(cases):
            amu = [s for s in found if s.use_case == use_case]
            polarities = {s.polarity for s in amu}
            for polarity in ("positive", "negative"):
                if polarity not in polarities:
                    problems.append(f"gap: {use_case} has no {polarity} scenario")
            component, live = bindings(use_case)
            if not component:
                problems.append(f"gap: {use_case} has no component binding")
            if not live:
                problems.append(f"gap: {use_case} has no live binding")

            use_cases += 1
            scenarios += len(amu)
            positives += sum(1 for s in amu if s.polarity == "positive")
            negatives += sum(1 for s in amu if s.polarity == "negative")
            rows.append(
                f"{amu[0].feature}.{use_case:<28} scenarios {len(amu):>2}"
                f" (+{sum(1 for s in amu if s.polarity == 'positive')}/"
                f"-{sum(1 for s in amu if s.polarity == 'negative')})"
                f"  component {'yes' if component else 'NO '}"
                f"  live {'yes' if live else 'NO '}"
            )

    print("\n".join(rows))
    print(f"use cases: {use_cases}")
    print(f"scenarios: {scenarios} (positive {positives}, negative {negatives})")
    for problem in problems:
        print(problem)
    if problems:
        print("granularity: incomplete")
        return 1
    print("granularity: complete")
    return 0


if __name__ == "__main__":
    sys.exit(main())
