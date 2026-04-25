"""
Evaluate the bundesrecht parser and normaliser against
PaDaS-Lab/legal-reference-annotations.

Downloads the annotation dataset from HuggingFace at runtime.

Usage:
    python benchmark/benchmark_bundesrecht.py
    python benchmark/benchmark_bundesrecht.py --jsonl gesetze.jsonl
    python benchmark/benchmark_bundesrecht.py --print-report
"""

from __future__ import annotations

import argparse
import contextlib
import datetime
import io
import json
import pathlib
import re
import sys
from collections import Counter
from dataclasses import dataclass, field

# ensure the parser repo root is on the path when running from benchmark/
sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))


# Dataset loading
def _load_dataset() -> list[dict]:
    try:
        from datasets import load_dataset
    except ImportError:
        print("ERROR: 'datasets' not installed. Run: pip install datasets")
        sys.exit(1)
    print("Downloading PaDaS-Lab/legal-reference-annotations from HuggingFace...")
    ds = load_dataset("PaDaS-Lab/legal-reference-annotations", split="train")
    rows = [dict(row) for row in ds]
    if rows and not rows[0]["Referenz"].startswith(("§", "Art", "Artikel")):
        rows = rows[1:]
    return rows


# Helpers
def _norm(val) -> str:
    if val is None:
        return ""
    return str(val).strip()


def _gold(row: dict, *keys: str) -> str:
    for k in keys:
        v = _norm(row.get(k, ""))
        if v and v.lower() != "nan":
            return v
    return ""


def _gold_set(row: dict, *keys: str) -> set[str]:
    """Parse a comma-separated gold value into a normalised set."""
    raw = _gold(row, *keys)
    if not raw:
        return set()
    return {v.strip().lower() for v in raw.split(",") if v.strip()}


_PREFIX_RE = re.compile(r"^\s*\(\d+\)\s*")


def _strip_absatz_prefix(text: str) -> str:
    return _PREFIX_RE.sub("", text).strip()


_SUBREF_KW = {
    "Abs",
    "Absatz",
    "Satz",
    "Nr",
    "Nrn",
    "Nummer",
    "Buchst",
    "Buchstabe",
    "Alt",
    "Alternative",
    "Halbs",
    "Halbsatz",
    "HS",
    "S",
    "Art",
    "Artikel",
}


def _ref_pattern(raw: str) -> str:
    """Collapse a reference to a structural pattern for grouping failures."""
    s = re.sub(r"\b\d{4}\b", "", raw.strip())
    s = re.sub(r"\b\d+[a-z]?\b", "N", s)
    out = []
    for tok in s.split():
        bare = tok.rstrip(".,;")
        if bare in _SUBREF_KW or bare in ("§", "§§", "iVm", "i.V.m.", "N"):
            out.append(tok)
        elif re.match(r"^[A-ZÄÖÜ][A-Za-zÄÖÜäöüß0-9]*$", bare):
            out.append("LAW")
        else:
            out.append(tok)
    return " ".join(out)


def _collect_field(parsed, field_name: str) -> set[str]:
    """Return all extracted values for one field from a single LawReference."""
    if not parsed.paragraphs:
        return set()
    level_map = {"Absatz": "Abs", "Satz": "Satz", "Nummer": "Nr", "Buchstabe": "Buchst"}
    result: set[str] = set()
    for para in parsed.paragraphs:
        if field_name == "Artikel":
            result.add(para.paragraph.lower())
        else:
            target = level_map.get(field_name)
            if target:
                for sr in para.sub_refs:
                    if sr.level == target:
                        result.add(sr.number.lower())
    return result


# Result containers
@dataclass
class StrictResult:
    """MODE 1: row-level exact set match."""

    correct: int = 0
    total: int = 0
    n_gold: int = 0
    n_extracted: int = 0

    @property
    def match_rate(self) -> float:
        return self.correct / self.total if self.total else 0.0


@dataclass
class MicroResult:
    """MODE 2: element-level micro IE metrics."""

    tp: int = 0
    fp: int = 0
    fn: int = 0
    n_gold: int = 0
    n_extracted: int = 0
    failures: list = field(default_factory=list)

    @property
    def precision(self) -> float:
        return self.tp / (self.tp + self.fp) if (self.tp + self.fp) else 0.0

    @property
    def recall(self) -> float:
        return self.tp / (self.tp + self.fn) if (self.tp + self.fn) else 0.0

    @property
    def f1(self) -> float:
        p, r = self.precision, self.recall
        return 2 * p * r / (p + r) if (p + r) else 0.0


# Parser + Normaliser benchmark
def run_parser_benchmark(
    rows: list[dict],
) -> tuple[dict[str, StrictResult], dict[str, MicroResult]]:
    from bundesrecht import normalise, parse_reference

    fields = ["Artikel", "Absatz", "Satz", "Nummer", "Buchstabe"]
    strict: dict[str, StrictResult] = {f: StrictResult() for f in fields}
    micro: dict[str, MicroResult] = {f: MicroResult() for f in fields}

    for row in rows:
        raw = _gold(row, "Referenz")
        if not raw:
            continue

        expanded = normalise(raw) or [raw]
        parsed_refs = [parse_reference(r) for r in expanded]

        for f in fields:
            gold_set = _gold_set(
                row, f, f + " "
            )  # "Buchstabe " has trailing space in dataset

            extracted_set: set[str] = set()
            for p in parsed_refs:
                extracted_set |= _collect_field(p, f)

            # MODE 1: strict exact match
            s = strict[f]
            s.total += 1
            s.n_gold += len(gold_set)
            s.n_extracted += len(extracted_set)
            if extracted_set == gold_set:
                s.correct += 1

            # MODE 2: micro IE metrics
            # rows where both are empty contribute nothing (no TN in IE evaluation)
            if gold_set or extracted_set:
                m = micro[f]
                m.tp += len(gold_set & extracted_set)
                m.fp += len(extracted_set - gold_set)
                m.fn += len(gold_set - extracted_set)
                m.n_gold += len(gold_set)
                m.n_extracted += len(extracted_set)
                if extracted_set != gold_set:
                    m.failures.append(
                        {
                            "Referenz": raw,
                            "field": f,
                            "gold": _gold(row, f, f + " "),
                            "extracted": ", ".join(sorted(extracted_set)),
                            "tp": len(gold_set & extracted_set),
                            "fp": len(extracted_set - gold_set),
                            "fn": len(gold_set - extracted_set),
                            "pattern": _ref_pattern(raw),
                        }
                    )

    return strict, micro


def _print_failure_analysis(micro: dict[str, MicroResult]) -> None:
    print("\nFailure analysis (mode 2 - rows where extracted != gold):")
    for f, m in micro.items():
        if not m.failures:
            continue
        fps = [x for x in m.failures if x["fp"] > 0 and x["fn"] == 0]
        fns = [x for x in m.failures if x["fn"] > 0 and x["fp"] == 0]
        mixed = [x for x in m.failures if x["fp"] > 0 and x["fn"] > 0]
        partial = [x for x in m.failures if x["tp"] > 0]
        print(
            f"\n  [{f}]  {len(m.failures)} mismatched rows"
            f"  ({len(partial)} partial, {len(fps)} pure-FP, {len(fns)} pure-FN, {len(mixed)} mixed)"
        )
        if fns or mixed:
            by_pair: Counter = Counter(
                (x["gold"], x["extracted"]) for x in m.failures if x["fn"] > 0
            )
            print("    Missed values (FN):")
            for (gold, extr), count in by_pair.most_common(8):
                print(f"      gold={gold!r:15} extracted={extr!r:15}  x{count}")
            top = by_pair.most_common(1)[0][0]
            examples = [
                x["Referenz"]
                for x in m.failures
                if x["gold"] == top[0] and x["extracted"] == top[1]
            ][:2]
            for ex in examples:
                print(f"        e.g. {ex!r}")
        if fps or mixed:
            by_extr: Counter = Counter(
                x["extracted"] for x in m.failures if x["fp"] > 0
            )
            print("    Spurious values (FP):")
            for extr, count in by_extr.most_common(5):
                print(f"      extracted={extr!r}  x{count}")
            examples = [x["Referenz"] for x in m.failures if x["fp"] > 0][:2]
            for ex in examples:
                print(f"        e.g. {ex!r}")


# Resolver benchmark
@dataclass
class ResolverResult:
    total: int = 0
    correct: int = 0
    not_in_dataset: int = 0
    failed_resolve: int = 0
    failures: list = field(default_factory=list)

    @property
    def precision(self) -> float:
        denom = self.total - self.not_in_dataset
        return self.correct / denom if denom else 0.0

    def __str__(self) -> str:
        denom = self.total - self.not_in_dataset
        return (
            f"{self.correct}/{denom} correct ({self.precision:.1%})"
            f"  [{self.not_in_dataset} not in dataset,"
            f" {self.failed_resolve} resolve failures,"
            f" {len(self.failures)} wrong]"
        )


def run_resolver_benchmark(
    rows: list[dict], jsonl_path: str
) -> dict[str, ResolverResult]:
    from bundesrecht import Bundesrecht

    lib = Bundesrecht(jsonl_path)

    fields = ["full_text", "absatz_text"]
    results: dict[str, ResolverResult] = {f: ResolverResult() for f in fields}

    for row in rows:
        raw = _gold(row, "Referenz")
        if not raw:
            for f in fields:
                results[f].total += 1
                results[f].not_in_dataset += 1
            continue

        try:
            resolved = lib.query(raw)
        except Exception:
            for f in fields:
                results[f].total += 1
                results[f].failed_resolve += 1
            continue

        if not resolved:
            for f in fields:
                results[f].total += 1
                results[f].failed_resolve += 1
            continue

        r0 = resolved[0]
        depth = getattr(r0, "resolved_depth", "section")

        res_ft = results["full_text"]
        res_ft.total += 1
        gold_ft = _gold(row, "full_text")
        if not gold_ft:
            res_ft.not_in_dataset += 1
        else:
            try:
                extracted_ft = _norm(r0.full_text())
            except Exception:
                extracted_ft = ""
            norm_gold = (
                _strip_absatz_prefix(gold_ft) if depth != "section" else _norm(gold_ft)
            )
            if extracted_ft == norm_gold:
                res_ft.correct += 1
            else:
                res_ft.failures.append(
                    {"Referenz": raw, "depth": depth, "pattern": _ref_pattern(raw)}
                )

        res_at = results["absatz_text"]
        res_at.total += 1
        gold_at = _gold(row, "absatz_text")
        if not gold_at:
            res_at.not_in_dataset += 1
        else:
            if depth not in ("absatz", "satz", "nummer", "buchstabe"):
                res_at.failed_resolve += 1
            else:
                try:
                    extracted_at = _norm(r0.full_text())
                except Exception:
                    extracted_at = ""
                if extracted_at == _strip_absatz_prefix(gold_at):
                    res_at.correct += 1
                else:
                    res_at.failures.append(
                        {"Referenz": raw, "depth": depth, "pattern": _ref_pattern(raw)}
                    )

    return results


def _print_resolver_analysis(results: dict[str, ResolverResult]) -> None:
    for f, r in results.items():
        if not r.failures:
            continue
        by_depth: Counter = Counter(x["depth"] for x in r.failures)
        by_pattern: Counter = Counter(x["pattern"] for x in r.failures)
        print(f"\n  [{f}] {len(r.failures)} wrong:")
        print(f"    by depth: {dict(by_depth.most_common())}")
        for pat, count in by_pattern.most_common(10):
            print(f"    {count:4d}x  {pat}")


# Serialisation
def _to_serialisable_parser(
    strict: dict[str, StrictResult],
    micro: dict[str, MicroResult],
) -> dict:
    out = {}
    for f in strict:
        out[f] = {
            "strict_match_rate": round(strict[f].match_rate, 4),
            "strict_correct": strict[f].correct,
            "strict_total": strict[f].total,
            "strict_n_gold": strict[f].n_gold,
            "strict_n_extracted": strict[f].n_extracted,
            "micro_precision": round(micro[f].precision, 4),
            "micro_recall": round(micro[f].recall, 4),
            "micro_f1": round(micro[f].f1, 4),
            "micro_tp": micro[f].tp,
            "micro_fp": micro[f].fp,
            "micro_fn": micro[f].fn,
            "micro_n_gold": micro[f].n_gold,
            "micro_n_extracted": micro[f].n_extracted,
        }
    return out


def _to_serialisable_resolver(results: dict[str, ResolverResult]) -> dict:
    return {
        k: {
            "total": v.total,
            "correct": v.correct,
            "not_in_dataset": v.not_in_dataset,
            "failed_resolve": v.failed_resolve,
            "precision": round(v.precision, 4),
            "n_failures": len(v.failures),
        }
        for k, v in results.items()
    }


# Report building
def _build_report(
    rows: list[dict],
    strict: dict[str, StrictResult],
    micro: dict[str, MicroResult],
    resolver_results: dict | None = None,
) -> str:
    buf = io.StringIO()

    def p(line: str = "") -> None:
        buf.write(line + "\n")

    sep = "-" * 60
    p(f"{sep}\n  Parser + Normaliser Benchmark\n{sep}")
    p(f"\nLoaded {len(rows)} annotated references.")

    col = 12
    p(f"\nMODE 1 - Strict exact match (extracted_set == gold_set per row):")
    p(
        f"  {'field':<{col}} {'correct/total':>15}  {'match rate':>10}  {'n_gold':>8}  {'n_extracted':>8}"
    )
    p(f"  {'-'*col}  {'-'*15}  {'-'*10}  {'-'*8}  {'-'*8}")
    for f, s in strict.items():
        p(
            f"  {f:<{col}} {f'{s.correct}/{s.total}':>15}  {s.match_rate:>9.1%}  {s.n_gold:>8}  {s.n_extracted:>8}"
        )

    p(
        f"\nMODE 2 - Micro IE metrics (element-level TP/FP/FN, empty-empty rows excluded):"
    )
    p(
        f"  {'field':<{col}} {'precision':>10}  {'recall':>8}  {'F1':>8}  {'TP':>6}  {'FP':>6}  {'FN':>6}  {'n_gold':>8}  {'n_extracted':>8}"
    )
    p(
        f"  {'-'*col}  {'-'*10}  {'-'*8}  {'-'*8}  {'-'*6}  {'-'*6}  {'-'*6}  {'-'*8}  {'-'*8}"
    )
    for f, m in micro.items():
        p(
            f"  {f:<{col}} {m.precision:>9.1%}  {m.recall:>8.1%}  {m.f1:>8.1%}"
            f"  {m.tp:>6}  {m.fp:>6}  {m.fn:>6}  {m.n_gold:>8}  {m.n_extracted:>8}"
        )

    with contextlib.redirect_stdout(buf):
        _print_failure_analysis(micro)
        if resolver_results:
            print(f"\n{sep}\n  Resolver Benchmark  (lib.query)\n{sep}")
            for f, r in resolver_results.items():
                print(f"  {f:<15} {r}")
            _print_resolver_analysis(resolver_results)

    return buf.getvalue()


def _build_benchmarks_md(
    strict: dict[str, StrictResult],
    micro: dict[str, MicroResult],
    n_rows: int,
) -> str:
    lines = [
        "# Benchmark Results",
        "",
        f"**Dataset:** PaDaS-Lab/legal-reference-annotations ({n_rows} references)  ",
        f"**Date:** {datetime.date.today().isoformat()}  ",
        "",
        "## MODE 1: Strict Exact Match",
        "",
        "Row-level: extracted set must equal gold set exactly.",
        "",
        "| Field | Correct / Total | Match Rate | n_gold | n_extracted |",
        "|-------|----------------|------------|--------|-------------|",
    ]
    for f, s in strict.items():
        lines.append(
            f"| {f} | {s.correct}/{s.total} | {s.match_rate:.1%} | {s.n_gold} | {s.n_extracted} |"
        )
    lines += [
        "",
        "## MODE 2: Micro IE Metrics",
        "",
        "Element-level: TP/FP/FN accumulated across individual values (empty-empty rows excluded).",
        "",
        "| Field | Precision | Recall | F1 | TP | FP | FN | n_gold | n_extracted |",
        "|-------|-----------|--------|----|----|----|----|--------|-------------|",
    ]
    for f, m in micro.items():
        lines.append(
            f"| {f} | {m.precision:.1%} | {m.recall:.1%} | {m.f1:.1%}"
            f" | {m.tp} | {m.fp} | {m.fn} | {m.n_gold} | {m.n_extracted} |"
        )
    lines.append("")
    return "\n".join(lines)


def _build_wrong_rows(micro: dict[str, MicroResult]) -> list[dict]:
    seen: set[tuple] = set()
    wrong_rows: list[dict] = []
    for f_name, m in micro.items():
        for entry in m.failures:
            key = (entry["Referenz"], f_name)
            if key in seen:
                continue
            seen.add(key)
            wrong_rows.append(
                {
                    "field": f_name,
                    "Referenz": entry["Referenz"],
                    "gold": entry["gold"],
                    "extracted": entry["extracted"],
                    "tp": entry["tp"],
                    "fp": entry["fp"],
                    "fn": entry["fn"],
                    "pattern": entry["pattern"],
                }
            )
    wrong_rows.sort(key=lambda x: (x["field"], x["Referenz"]))
    return wrong_rows


def _write_evals(evals_dir: pathlib.Path, files: dict) -> None:
    evals_dir.mkdir(parents=True, exist_ok=True)
    for name, content in files.items():
        path = evals_dir / name
        if isinstance(content, str):
            path.write_text(content, encoding="utf-8")
        elif isinstance(content, list):
            with open(path, "w", encoding="utf-8") as fh:
                for row in content:
                    fh.write(json.dumps(row, ensure_ascii=False) + "\n")
        else:
            with open(path, "w", encoding="utf-8") as fh:
                json.dump(content, fh, indent=2, ensure_ascii=False)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Benchmark bundesrecht parser+normaliser against PaDaS-Lab/legal-reference-annotations"
    )
    parser.add_argument(
        "--jsonl",
        default=None,
        help="Path to gesetze.jsonl - if provided, also runs the resolver benchmark",
    )
    parser.add_argument(
        "--print-report",
        dest="print_output",
        action="store_true",
        help="Also echo the report to the terminal",
    )
    args = parser.parse_args()

    script_dir = pathlib.Path(__file__).parent
    evals_dir = script_dir / "evals"

    rows = _load_dataset()
    strict, micro = run_parser_benchmark(rows)

    resolver_results = None
    if args.jsonl:
        resolver_results = run_resolver_benchmark(rows, args.jsonl)

    output: dict = {
        "n_rows": len(rows),
        "parser": _to_serialisable_parser(strict, micro),
    }
    if resolver_results:
        output["resolver"] = _to_serialisable_resolver(resolver_results)

    report = _build_report(rows, strict, micro, resolver_results)
    wrong_rows = _build_wrong_rows(micro)

    _write_evals(
        evals_dir,
        {
            "results.json": output,
            "wrong.jsonl": wrong_rows,
            "report.txt": report,
        },
    )

    benchmarks_path = script_dir / "BENCHMARKS.md"
    benchmarks_path.write_text(
        _build_benchmarks_md(strict, micro, len(rows)),
        encoding="utf-8",
    )

    if args.print_output:
        print(report)

    print(f"evals written to {evals_dir}/")
    print(f"  results.json")
    print(f"  wrong.jsonl  ({len(wrong_rows)} rows)")
    print(f"  report.txt")
    print(f"BENCHMARKS.md updated at {benchmarks_path}")


if __name__ == "__main__":
    main()
