# Evaluation Results

**Dataset:** PaDaS-Lab/legal-reference-annotations (2944 references)  
**Date:** 2026-08-04  

## MODE 1: Strict Exact Match

Row-level: extracted set must equal gold set exactly.

| Field | Correct / Total | Match Rate | n_gold | n_extracted |
|-------|----------------|------------|--------|-------------|
| Artikel | 2934/2944 | 99.7% | 2947 | 2943 |
| Absatz | 2936/2944 | 99.7% | 2148 | 2142 |
| Satz | 2938/2944 | 99.8% | 889 | 882 |
| Nummer | 2934/2944 | 99.7% | 478 | 473 |
| Buchstabe | 2935/2944 | 99.7% | 29 | 26 |

## MODE 2: Micro IE Metrics

Element-level: TP/FP/FN accumulated across individual values (empty-empty rows excluded).

| Field | Precision | Recall | F1 | TP | FP | FN | n_gold | n_extracted |
|-------|-----------|--------|----|----|----|----|--------|-------------|
| Artikel | 99.9% | 99.7% | 99.8% | 2939 | 4 | 8 | 2947 | 2943 |
| Absatz | 99.9% | 99.6% | 99.7% | 2139 | 3 | 9 | 2148 | 2142 |
| Satz | 100.0% | 99.2% | 99.6% | 882 | 0 | 7 | 889 | 882 |
| Nummer | 98.9% | 97.9% | 98.4% | 468 | 5 | 10 | 478 | 473 |
| Buchstabe | 88.5% | 79.3% | 83.6% | 23 | 3 | 6 | 29 | 26 |
