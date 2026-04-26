# Benchmark Results

**Dataset:** PaDaS-Lab/legal-reference-annotations (2944 references)  
**Date:** 2026-04-26  

## MODE 1: Strict Exact Match

Row-level: extracted set must equal gold set exactly.

| Field | Correct / Total | Match Rate | n_gold | n_extracted |
|-------|----------------|------------|--------|-------------|
| Artikel | 2929/2944 | 99.5% | 2944 | 2943 |
| Absatz | 2925/2944 | 99.4% | 2141 | 2142 |
| Satz | 2904/2944 | 98.6% | 861 | 882 |
| Nummer | 2920/2944 | 99.2% | 465 | 473 |
| Buchstabe | 2934/2944 | 99.7% | 29 | 26 |

## MODE 2: Micro IE Metrics

Element-level: TP/FP/FN accumulated across individual values (empty-empty rows excluded).

| Field | Precision | Recall | F1 | TP | FP | FN | n_gold | n_extracted |
|-------|-----------|--------|----|----|----|----|--------|-------------|
| Artikel | 99.6% | 99.6% | 99.6% | 2931 | 12 | 13 | 2944 | 2943 |
| Absatz | 99.3% | 99.3% | 99.3% | 2127 | 15 | 14 | 2141 | 2142 |
| Satz | 96.1% | 98.5% | 97.3% | 848 | 34 | 13 | 861 | 882 |
| Nummer | 95.8% | 97.4% | 96.6% | 453 | 20 | 12 | 465 | 473 |
| Buchstabe | 84.6% | 75.9% | 80.0% | 22 | 4 | 7 | 29 | 26 |
