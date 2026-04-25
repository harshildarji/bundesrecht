# benchmark

Evaluates the `bundesrecht` parser and normaliser against
[PaDaS-Lab/legal-reference-annotations](https://huggingface.co/datasets/PaDaS-Lab/legal-reference-annotations),
a dataset of 2,944 manually annotated German legal references.

## Usage

```bash
# from the parser/ root
python benchmark/benchmark_bundesrecht.py
python benchmark/benchmark_bundesrecht.py --print-report
```

Output is written to `benchmark/evals/`:

| File | Description |
|------|-------------|
| `results.json` | Full metrics, machine-readable |
| `wrong.jsonl` | Mismatched rows for analysis |
| `report.txt` | Full human-readable report |

`BENCHMARKS.md` is written to `benchmark/` and should be committed after each run.

## Evaluation

Five fields are evaluated independently: `Artikel`, `Absatz`, `Satz`, `Nummer`, `Buchstabe`.

Empty gold = the field is genuinely absent from that reference (manually verified by annotators).

### MODE 1: Strict Exact Match

Row-level: the extracted set must equal the gold set exactly.
Reports the percentage of rows where the parser gets the entire field right.

### MODE 2: Micro IE Metrics

Element-level TP/FP/FN accumulated across individual values, not rows:

```
tp += |gold & extracted|
fp += |extracted - gold|
fn += |gold - extracted|
```

Computes micro precision, recall, and F1. Appropriate for multi-value fields
(e.g. `Abs. 1 und 2`, `Nr. 1, 2, 3`). TN is not defined - standard IE evaluation.

Rows where both gold and extracted are empty contribute nothing to mode 2,
and count as correct in mode 1.
