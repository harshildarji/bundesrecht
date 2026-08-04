"""Compare bundesrecht with three German legal reference parsers."""

from __future__ import annotations

import json
import pathlib
import re
import sys
import urllib.request
from importlib.metadata import Distribution, distribution
from typing import Callable

PARSER_ROOT = pathlib.Path(__file__).resolve().parents[2]
EVAL_ROOT = PARSER_ROOT / "eval"
sys.path.insert(0, str(PARSER_ROOT))
sys.path.insert(0, str(EVAL_ROOT))

from eval_bundesrecht import (
    FIELDS,
    _gold,
    _load_dataset,
    predict_bundesrecht_fields,
    score_predictions,
)

LAVIS_COMMIT = "66f875feac073f8b5790c6d02866fc9948a22927"
LAVIS_REPOSITORY = "https://github.com/lavis-nlp/german-legal-reference-parser"
LAVIS_LAWS_URL = f"https://raw.githubusercontent.com/lavis-nlp/german-legal-reference-parser/{LAVIS_COMMIT}/resource/laws.txt"
REFEX_REPOSITORY = "https://github.com/openlegaldata/legal-reference-extraction"
GESETZESSUCHE_REPOSITORY = "https://github.com/Steffen-W/gesetzessuche"
GESETZESSUCHE_COMMIT = "64a46a6a44a0c306c5bd2cfa7d1e2ba9145836ef"

LAVIS_FIELDS = ("Artikel", "Absatz", "Satz", "Nummer")
REFEX_FIELDS = ("Artikel",)
GESETZESSUCHE_FIELDS = FIELDS
EXPECTED_BUNDESRECHT = (99.8, 99.7, 99.6, 98.4, 83.6)
ROMAN_TO_ARABIC = {
    "I": "1",
    "II": "2",
    "III": "3",
    "IV": "4",
    "V": "5",
    "VI": "6",
    "VII": "7",
    "VIII": "8",
    "IX": "9",
    "X": "10",
    "XI": "11",
    "XII": "12",
}

Prediction = dict[str, set[str]]
Adapter = Callable[[str], Prediction]


def _repo_url(value: str) -> str:
    return value.strip().lower().removesuffix(".git").rstrip("/")


def _project_urls(dist: Distribution) -> set[str]:
    urls = set()
    for item in dist.metadata.get_all("Project-URL") or []:
        _, url = item.split(",", 1)
        urls.add(_repo_url(url))
    return urls


def _direct_url(dist: Distribution) -> dict:
    matches = [
        dist.locate_file(path)
        for path in dist.files or []
        if str(path).endswith("direct_url.json")
    ]
    if len(matches) != 1:
        raise RuntimeError(
            f"Expected one direct_url.json for {dist.metadata['Name']}, found {len(matches)}"
        )
    return json.loads(matches[0].read_text(encoding="utf-8"))


def verify_tool_identities() -> dict[str, str]:
    lavis = distribution("olparse")
    lavis_direct = _direct_url(lavis)
    assert lavis.metadata["Name"] == "olparse"
    assert _repo_url(lavis_direct["url"]) == _repo_url(LAVIS_REPOSITORY)
    assert lavis_direct["vcs_info"]["commit_id"] == LAVIS_COMMIT

    refex = distribution("legal-reference-extraction")
    assert refex.metadata["Name"] == "legal-reference-extraction"
    assert refex.version == "0.5.3"
    assert _repo_url(REFEX_REPOSITORY) in _project_urls(refex)

    gesetzessuche = distribution("gesetzessuche")
    gesetzessuche_direct = _direct_url(gesetzessuche)
    assert gesetzessuche.metadata["Name"] == "gesetzessuche"
    assert gesetzessuche.version == "0.2.0"
    assert _repo_url(GESETZESSUCHE_REPOSITORY) in _project_urls(gesetzessuche)
    assert _repo_url(gesetzessuche_direct["url"]) == _repo_url(GESETZESSUCHE_REPOSITORY)
    assert gesetzessuche_direct["vcs_info"]["commit_id"] == GESETZESSUCHE_COMMIT

    return {
        "LAVIS": f"olparse {lavis.version}, {LAVIS_REPOSITORY}@{LAVIS_COMMIT}",
        "refex": f"legal-reference-extraction {refex.version}, {REFEX_REPOSITORY}",
        "Gesetzessuche": f"gesetzessuche {gesetzessuche.version}, {GESETZESSUCHE_REPOSITORY}@v0.2.0 ({GESETZESSUCHE_COMMIT})",
    }


def restore_lavis_laws() -> None:
    dist = distribution("olparse")
    laws_path = pathlib.Path(dist.locate_file("")) / "resource" / "laws.txt"
    if laws_path.exists():
        return
    laws_path.parent.mkdir(parents=True, exist_ok=True)
    # wheel omits this pinned resource, so restore only laws.txt and leave parser logic untouched
    with urllib.request.urlopen(LAVIS_LAWS_URL, timeout=120) as response:
        content = response.read()
    if not content:
        raise RuntimeError("The pinned LAVIS laws.txt download was empty")
    laws_path.write_bytes(content)


def _empty_prediction() -> Prediction:
    # Sets deduplicate values and make comparison independent of output order
    return {field_name: set() for field_name in FIELDS}


def _normalise_value(value: object, roman: bool = False) -> str:
    # Case and repeated whitespace do not change the identity of a parsed field value
    cleaned = " ".join(str(value).strip().split())
    if roman and cleaned in ROMAN_TO_ARABIC:
        cleaned = ROMAN_TO_ARABIC[cleaned]
    return cleaned.lower()


def _add_number(prediction: Prediction, value: object) -> None:
    cleaned = " ".join(str(value).strip().split())
    if not cleaned:
        return
    if cleaned in ROMAN_TO_ARABIC:
        # Roman sub-reference values I to XII are equivalent to their Arabic form in the gold
        prediction["Nummer"].add(ROMAN_TO_ARABIC[cleaned])
        return
    combined = re.fullmatch(r"(\d+)([A-Za-z]+)", cleaned)
    if combined:
        # LAVIS has no separate Buchstabe field, so only the Nummer part is scored
        prediction["Nummer"].add(_normalise_value(combined.group(1)))
        return
    if re.fullmatch(r"[A-Za-z]+", cleaned):
        # Alphabetic values cannot be assigned to a native LAVIS output field
        return
    prediction["Nummer"].add(_normalise_value(cleaned, roman=True))


def lavis_adapter(raw: str, parse_any: Callable, law_ref_type: type) -> Prediction:
    prediction = _empty_prediction()
    for parsed, _, _ in parse_any(raw):
        if not isinstance(parsed, law_ref_type):
            continue
        # Multi and i.V.m. references expose every component through unpack()
        for part in parsed.unpack():
            if part.paragraph:
                prediction["Artikel"].add(_normalise_value(part.paragraph))
            if part.abs:
                prediction["Absatz"].add(_normalise_value(part.abs, roman=True))
            if part.satz:
                prediction["Satz"].add(_normalise_value(part.satz, roman=True))
            if part.nr:
                _add_number(prediction, part.nr)
    return prediction


def refex_adapter(raw: str, extractor: object, law_citation_type: type) -> Prediction:
    prediction = _empty_prediction()
    for citation in extractor.extract(raw).citations:
        if isinstance(citation, law_citation_type) and citation.number:
            # refex number is the cited provision, never a lower-level Nummer
            prediction["Artikel"].add(_normalise_value(citation.number))
    return prediction


def gesetzessuche_adapter(raw: str, parse_law_reference: Callable) -> Prediction:
    parsed = parse_law_reference(raw)
    prediction = _empty_prediction()
    if parsed is None:
        return prediction
    mapping = {
        "paragraph": "Artikel",
        "section": "Absatz",
        "sentence": "Satz",
        "number": "Nummer",
        "letter": "Buchstabe",
    }
    for source_field, target_field in mapping.items():
        value = parsed.get(source_field)
        if value:
            prediction[target_field].add(
                _normalise_value(
                    value, roman=target_field in ("Absatz", "Satz", "Nummer")
                )
            )
    return prediction


def run_adapter(rows: list[dict], adapter: Adapter) -> list[Prediction]:
    return [adapter(_gold(row, "Referenz")) for row in rows]


def _rounded_f1(micro: dict, fields: tuple[str, ...]) -> tuple[float, ...]:
    return tuple(round(micro[field_name].f1 * 100, 1) for field_name in fields)


def _covered_indices(
    predictions: list[Prediction], fields: tuple[str, ...]
) -> list[int]:
    return [
        index
        for index, prediction in enumerate(predictions)
        if any(prediction[field_name] for field_name in fields)
    ]


def _subset(values: list, indices: list[int]) -> list:
    return [values[index] for index in indices]


def _macro_f1(
    rows: list[dict], predictions: list[Prediction], fields: tuple[str, ...]
) -> float:
    _, micro = score_predictions(rows, predictions, fields)
    return sum(micro[field_name].f1 for field_name in fields) * 100 / len(fields)


def _paired_scores(
    rows: list[dict],
    bundesrecht_predictions: list[Prediction],
    tool_predictions: list[Prediction],
    fields: tuple[str, ...],
) -> tuple[int, float, float, float]:
    indices = _covered_indices(tool_predictions, fields)
    covered_rows = _subset(rows, indices)
    bundesrecht_score = _macro_f1(
        covered_rows, _subset(bundesrecht_predictions, indices), fields
    )
    tool_score = _macro_f1(covered_rows, _subset(tool_predictions, indices), fields)
    return len(indices), len(indices) * 100 / len(rows), bundesrecht_score, tool_score


def build_results(
    identities: dict[str, str],
    rows: list[dict],
    all_micro: dict[str, dict],
    paired: dict[str, tuple[int, float, float, float]],
) -> str:
    lines = [
        "# Tool Comparison Results",
        "",
        f"Dataset: PaDaS-Lab/legal-reference-annotations ({len(rows)} references). Gold fields use the published comma split, with compound expressions such as `81 ff.`, `9 bis 19`, and `2 oder 3` kept as single values.",
        "",
        "## Verified tools",
        "",
        f"- LAVIS: `{identities['LAVIS']}`.",
        f"- refex: `{identities['refex']}`.",
        f"- Gesetzessuche: `{identities['Gesetzessuche']}`.",
        "",
        "## All-row micro F1",
        "",
        "| Field | bundesrecht | LAVIS | refex | Gesetzessuche |",
        "|---|---:|---:|---:|---:|",
    ]
    supported = {
        "bundesrecht": FIELDS,
        "LAVIS": LAVIS_FIELDS,
        "refex": REFEX_FIELDS,
        "Gesetzessuche": GESETZESSUCHE_FIELDS,
    }
    for field_name in FIELDS:
        values = []
        for tool_name in ("bundesrecht", "LAVIS", "refex", "Gesetzessuche"):
            values.append(
                f"{all_micro[tool_name][field_name].f1:.1%}"
                if field_name in supported[tool_name]
                else "n/a"
            )
        lines.append(f"| {field_name} | {' | '.join(values)} |")

    lines += [
        "",
        "## Coverage and paired macro F1",
        "",
        "| Tool | Compared fields | Covered rows | Coverage | bundesrecht macro F1 | Tool macro F1 |",
        "|---|---|---:|---:|---:|---:|",
    ]
    paired_fields = {
        "LAVIS": LAVIS_FIELDS,
        "refex": REFEX_FIELDS,
        "Gesetzessuche": GESETZESSUCHE_FIELDS,
    }
    for tool_name in ("LAVIS", "refex", "Gesetzessuche"):
        count, coverage, bundesrecht_score, tool_score = paired[tool_name]
        lines.append(
            f"| {tool_name} | {', '.join(paired_fields[tool_name])} | {count}/{len(rows)} | {coverage:.1f}% | {bundesrecht_score:.1f}% | {tool_score:.1f}% |"
        )

    lines += [
        "",
        "## Notes",
        "",
        "Coverage is the share of rows where a tool produced at least one value in its compared field set. Paired macro F1 evaluates both tools on exactly those covered rows and only the listed comparable fields.",
        "",
        "Buchstabe has only 29 gold values, so a small number of errors can change its F1 more than the other field scores.",
        "",
        "Gesetzessuche returns one parsed reference per call, so it cannot return additional references from multi-reference expressions.",
        "",
        "The LAVIS package omits `resource/laws.txt`. The script restores that file from the pinned source commit without changing parser logic.",
        "",
    ]
    return "\n".join(lines)


def main() -> None:
    identities = verify_tool_identities()
    restore_lavis_laws()

    from gesetzessuche import parse_law_reference
    from olparse import parse_any
    from olparse.models import LawRef
    from refex.citations import LawCitation
    from refex.orchestrator import CitationExtractor

    rows = _load_dataset()
    if len(rows) != 2944:
        raise SystemExit(f"Dataset gate failed: expected 2944 rows, got {len(rows)}")

    predictions = {
        "bundesrecht": [
            predict_bundesrecht_fields(_gold(row, "Referenz")) for row in rows
        ]
    }
    _, bundesrecht_micro = score_predictions(rows, predictions["bundesrecht"])
    actual_bundesrecht = _rounded_f1(bundesrecht_micro, FIELDS)
    if actual_bundesrecht != EXPECTED_BUNDESRECHT:
        raise SystemExit(
            f"Bundesrecht sanity gate failed: expected {EXPECTED_BUNDESRECHT}, got {actual_bundesrecht}"
        )

    extractor = CitationExtractor()
    adapters = {
        "LAVIS": lambda raw: lavis_adapter(raw, parse_any, LawRef),
        "refex": lambda raw: refex_adapter(raw, extractor, LawCitation),
        "Gesetzessuche": lambda raw: gesetzessuche_adapter(raw, parse_law_reference),
    }
    for tool_name, adapter in adapters.items():
        predictions[tool_name] = run_adapter(rows, adapter)

    all_micro = {"bundesrecht": bundesrecht_micro}
    for tool_name in adapters:
        _, all_micro[tool_name] = score_predictions(rows, predictions[tool_name])

    paired_fields = {
        "LAVIS": LAVIS_FIELDS,
        "refex": REFEX_FIELDS,
        "Gesetzessuche": GESETZESSUCHE_FIELDS,
    }
    paired = {
        tool_name: _paired_scores(
            rows, predictions["bundesrecht"], predictions[tool_name], fields
        )
        for tool_name, fields in paired_fields.items()
    }

    results_path = pathlib.Path(__file__).with_name("RESULTS.md")
    results_path.write_text(
        build_results(identities, rows, all_micro, paired), encoding="utf-8"
    )
    print(f"Results written to {results_path}")


if __name__ == "__main__":
    main()
