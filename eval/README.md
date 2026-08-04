# eval

Evaluates the `bundesrecht` parser and normaliser against
[PaDaS-Lab/legal-reference-annotations](https://huggingface.co/datasets/PaDaS-Lab/legal-reference-annotations),
a dataset of 2,944 manually annotated German legal references.

## Usage

```bash
# from the parser/ root
python eval/eval_bundesrecht.py
python eval/eval_bundesrecht.py --print-report
```

Output is written to `eval/evals/`:

| File | Description |
|------|-------------|
| `results.json` | Full metrics, machine-readable |
| `wrong.jsonl` | Mismatched rows for analysis |
| `report.txt` | Full human-readable report |

`RESULTS.md` is written to `eval/` and should be committed after each run.

The external tool comparison is in [`compare/`](compare/). It imports this evaluator's dataset loader and scoring functions so both evaluations use the same 2,944 rows and metric definitions.

## Evaluation

Five fields are evaluated independently: `Artikel`, `Absatz`, `Satz`, `Nummer`, `Buchstabe`.

An empty gold cell is scored as no annotated value for that field. Some citations contain an explicit field marker while the corresponding annotation cell is empty, so an empty cell does not prove that the field is absent from the citation text.

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
