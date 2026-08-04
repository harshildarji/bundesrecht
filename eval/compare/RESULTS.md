# Tool Comparison Results

Dataset: PaDaS-Lab/legal-reference-annotations (2944 references). Gold fields use the published comma split, with compound expressions such as `81 ff.`, `9 bis 19`, and `2 oder 3` kept as single values.

## Verified tools

- LAVIS: `olparse 0.1, https://github.com/lavis-nlp/german-legal-reference-parser@66f875feac073f8b5790c6d02866fc9948a22927`.
- refex: `legal-reference-extraction 0.5.3, https://github.com/openlegaldata/legal-reference-extraction`.
- Gesetzessuche: `gesetzessuche 0.2.0, https://github.com/Steffen-W/gesetzessuche@v0.2.0 (64a46a6a44a0c306c5bd2cfa7d1e2ba9145836ef)`.

## All-row micro F1

| Field | bundesrecht | LAVIS | refex | Gesetzessuche |
|---|---:|---:|---:|---:|
| Artikel | 99.8% | 87.5% | 96.1% | 98.8% |
| Absatz | 99.7% | 82.9% | n/a | 94.1% |
| Satz | 99.6% | 85.0% | n/a | 86.8% |
| Nummer | 98.4% | 74.4% | n/a | 70.0% |
| Buchstabe | 83.6% | n/a | n/a | 12.9% |

## Coverage and paired macro F1

| Tool | Compared fields | Covered rows | Coverage | bundesrecht macro F1 | Tool macro F1 |
|---|---|---:|---:|---:|---:|
| LAVIS | Artikel, Absatz, Satz, Nummer | 2295/2944 | 78.0% | 99.6% | 96.2% |
| refex | Artikel | 2729/2944 | 92.7% | 99.9% | 99.8% |
| Gesetzessuche | Artikel, Absatz, Satz, Nummer, Buchstabe | 2944/2944 | 100.0% | 96.2% | 72.5% |

## Notes

Coverage is the share of rows where a tool produced at least one value in its compared field set. Paired macro F1 evaluates both tools on exactly those covered rows and only the listed comparable fields.

Buchstabe has only 29 gold values, so a small number of errors can change its F1 more than the other field scores.

Gesetzessuche returns one parsed reference per call, so it cannot return additional references from multi-reference expressions.

The LAVIS package omits `resource/laws.txt`. The script restores that file from the pinned source commit without changing parser logic.
