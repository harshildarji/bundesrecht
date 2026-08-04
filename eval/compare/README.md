# Tool comparison

This experiment compares `bundesrecht` with three public German legal reference tools on the same 2,944 manually annotated references used by the paper evaluation.

The comparison covers the parsing and field-extraction subtask only: each tool receives an already-identified citation string, and its extracted field values are scored against the manual annotations. Reference detection in full text and corpus-backed resolution are outside its scope.

## Compared tools

- LAVIS `german-legal-reference-parser` at commit `66f875feac073f8b5790c6d02866fc9948a22927` provides structured paragraph, Absatz, Satz, and generic Nummer extraction. It has no separate Buchstabe field, so Buchstabe is reported as `n/a`.
- `legal-reference-extraction==0.5.3`, imported as `refex`, provides typed citation extraction and is compared on its provision-number output.
- `gesetzessuche==0.2.0` from `Steffen-W/gesetzessuche` provides the typed `parse_law_reference()` fields `paragraph`, `section`, `sentence`, `number`, and `letter`.

## Gold fields

| Field | Meaning |
|---|---|
| Artikel | The cited provision number following `§`, `Art.`, or `Artikel` |
| Absatz | The cited Absatz value |
| Satz | The cited Satz value |
| Nummer | The cited Nummer value |
| Buchstabe | The cited Buchstabe value |

Gold values are split only on commas. Compound expressions such as `81 ff.`, `9 bis 19`, and `2 oder 3` remain single values, matching the published paper evaluation.

## Scoring

The dataset loader, gold handling, and strict and micro scoring functions are directly from `eval/eval_bundesrecht.py`. The script requires exactly 2,944 rows and stops if the bundesrecht micro F1 values differ from the expected `99.8/99.7/99.6/98.4/83.6` baseline.

All-row micro F1 scores every annotation row for each supported field. When a tool produces no output, every corresponding gold value counts as a false negative.

Coverage is the share of rows where a tool produces at least one value in its compared field set. Paired macro F1 restricts both bundesrecht and the competitor to those same covered rows and averages only over the fields listed for that tool, avoiding comparisons across different row or field sets.

## Adapter normalization

The adapters normalize formatting differences and map each tool's output to the compared fields as described below.

- Values are lowercased, repeated whitespace is collapsed, duplicates are removed, and output order is ignored.
- Roman sub-reference values from `I` through `XII` are converted to Arabic values.
- For LAVIS combined `nr` values such as `1a`, only the numeric part is scored as Nummer. Alphabetic `nr` values are not reclassified because LAVIS has no separate Buchstabe field.
- LAVIS `MultiLawRef` and `IVMLawRef` components are flattened into the same annotation row.
- refex `number` maps only to Artikel and never to a lower-level Nummer.
- Gesetzessuche uses only the fields returned by `parse_law_reference()` and does not reconstruct additional references from resolved text.

The script writes the result tables and notes to [RESULTS.md](RESULTS.md).
