"""
bundesrecht.normaliser - normalises raw German legal reference strings.

Converts a raw citation into a list of canonical, individually-resolvable
reference strings.

Pipeline:
    1. Split on i.V.m. / iVm → two independent refs
    2. Expand §§ N-M ranges → one ref per paragraph number
    3. Parse into LawReference
    4. Expand multi-target sub_refs (Nr. 1, Nr. 7, Abs. 2 → 3 targets)
    5. Reconstruct each target as a clean canonical string

Examples:
    >>> normalise("§ 2 Abs. 1 Nr. 1, Nr. 7, Abs. 2 UrhG")
    ['§ 2 Abs. 1 Nr. 1 UrhG', '§ 2 Abs. 1 Nr. 7 UrhG', '§ 2 Abs. 2 UrhG']
    >>> normalise("§ 312 i.V.m. § 355 BGB")
    ['§ 312 BGB', '§ 355 BGB']
    >>> normalise("§§ 12-15 BGB")
    ['§ 12 BGB', '§ 13 BGB', '§ 14 BGB', '§ 15 BGB']
"""

from __future__ import annotations

import re

from bundesrecht.references import (
    LawReference,
    ParagraphRef,
    SubReference,
    _expand_multi_target,
    _parse_reference,
)

_IVM_SPLIT_RE = re.compile(
    r"\s+(?:i\.?\s*V\.?\s*m\.?|iVm\.?)\s+",
    re.IGNORECASE,
)


def _split_ivm(raw: str) -> list[str]:
    """Split 'A iVm B' into ['A', 'B'].

    When the law abbreviation appears only at the end (e.g. '§ 312 iVm § 355 BGB'),
    propagates it to the first part if missing.
    """
    parts = [p.strip() for p in _IVM_SPLIT_RE.split(raw) if p.strip()]
    if len(parts) < 2:
        return parts

    def _has_law(s: str) -> bool:
        tokens = s.rstrip(".,;").split()
        if not tokens:
            return False
        last = tokens[-1].rstrip(".,;")
        sub_ref_keywords = {
            "abs",
            "absatz",
            "satz",
            "nr",
            "nummer",
            "buchst",
            "buchstabe",
            "alt",
            "alternative",
            "halbs",
            "halbsatz",
            "hs",
            "s",
        }
        return (
            bool(re.search(r"[A-Za-z]", last))
            and not last.isdigit()
            and last.lower().rstrip(".") not in sub_ref_keywords
        )

    last_law = None
    for part in reversed(parts):
        ref = _parse_reference(part)
        if ref.law:
            last_law = ref.law
            break

    result = []
    for part in parts:
        ref = _parse_reference(part)
        if not ref.law and last_law:
            part = part.rstrip(".,; ") + " " + last_law
        result.append(part)

    return result


# §§ multi-law splitter
_MULTI_PAR_RE = re.compile(r"^§§\s*", re.IGNORECASE)
_PARA_WITH_LAW_RE = re.compile(
    r"^(\d+[a-z]?)\s+(.+?)\s+([A-ZÄÖÜ][A-Za-zÄÖÜäöüß0-9]+\.?)\s*$"
)
_PARA_LAW_ONLY_RE = re.compile(r"^(\d+[a-z]?)\s+([A-ZÄÖÜ][A-Za-zÄÖÜäöüß0-9]+\.?)\s*$")


def _extract_trailing_law(s: str) -> tuple[str, str]:
    """Split 'body LAW' into ('body', 'LAW'), or ('body', '') if no law found.

    Handles multi-token abbreviations like 'SGB III', 'SGB V', 'SGB XII'.
    """
    tokens = s.strip().split()
    if not tokens:
        return s, ""
    sub_kw = {
        "abs",
        "absatz",
        "satz",
        "s",
        "nr",
        "nummer",
        "buchst",
        "buchstabe",
        "alt",
        "alternative",
        "halbs",
        "halbsatz",
        "hs",
    }

    def _is_law_token(tok: str) -> bool:
        tok = tok.rstrip(".,;")
        return (
            bool(re.search(r"[A-ZÄÖÜ]", tok))
            and not tok.isdigit()
            and tok.lower().rstrip(".") not in sub_kw
        )

    def _is_roman_or_number(tok: str) -> bool:
        tok = tok.rstrip(".,;")
        return bool(re.match(r"^[IVXivx]+$", tok)) or tok.isdigit()

    law_tokens = []
    i = len(tokens) - 1

    last = tokens[i].rstrip(".,;")
    if _is_roman_or_number(last) and i > 0 and _is_law_token(tokens[i - 1]):
        law_tokens = [tokens[i - 1].rstrip(".,;"), last]
        i -= 2
    elif _is_law_token(last):
        law_tokens = [last]
        i -= 1
    else:
        return s, ""

    law = " ".join(law_tokens)
    return " ".join(tokens[: i + 1]), _normalise_law(law)


def _split_multi_law(raw: str) -> list[str]:
    """Split §§ references with multiple paragraphs into individual § refs.

    Handles two cases:
        Per-chunk law:  §§ 46 Abs. 2 ArbGG, 91 Abs. 1 ZPO
                        → ['§ 46 Abs. 2 ArbGG', '§ 91 Abs. 1 ZPO']
        Shared law:     §§ 137 S. 2, 398, 903 BGB
                        → ['§ 137 S. 2 BGB', '§ 398 BGB', '§ 903 BGB']

    Returns the original string unchanged if the pattern is not recognised.
    """
    if not _MULTI_PAR_RE.match(raw):
        return [raw]

    body = _MULTI_PAR_RE.sub("", raw).strip()
    _UND_ODER_RE = re.compile(
        r"(?<=[\w])\s+(?:und|oder)\s+(?=\d)",
        re.IGNORECASE,
    )
    body = _UND_ODER_RE.sub(", ", body)
    chunks = [c.strip() for c in body.split(",") if c.strip()]

    if len(chunks) < 2:
        return [raw]

    # Case 1: every chunk has its own law abbreviation
    per_chunk_results = []
    all_have_law = True
    for chunk in chunks:
        m = _PARA_WITH_LAW_RE.match(chunk)
        m2 = _PARA_LAW_ONLY_RE.match(chunk)
        if m:
            per_chunk_results.append(
                f'§ {m.group(1)} {m.group(2).strip()} {m.group(3).rstrip(".,")}'
            )
        elif m2:
            per_chunk_results.append(f'§ {m2.group(1)} {m2.group(2).rstrip(".,")}')
        else:
            all_have_law = False
            break
    if all_have_law:
        return per_chunk_results

    # Case 2: shared law at the end of the last chunk
    last_chunk = chunks[-1]
    last_body, shared_law = _extract_trailing_law(last_chunk)
    if not shared_law:
        return [raw]

    results = []
    for i, chunk in enumerate(chunks):
        body_part = last_body if i == len(chunks) - 1 else chunk
        m_para = re.match(r"^(\d+[a-z]?)(.*)", body_part.strip())
        if not m_para:
            return [raw]
        para_num = m_para.group(1)
        sub_part = m_para.group(2).strip()
        if sub_part:
            results.append(f"§ {para_num} {sub_part} {shared_law}")
        else:
            results.append(f"§ {para_num} {shared_law}")

    return results


# §§ range expander
_RANGE_RE = re.compile(
    r"§§\s*(\d+[a-z]?)\s*(?:-|–|—|bis)\s*(\d+[a-z]?)",
    re.IGNORECASE,
)


def _expand_range(raw: str) -> list[str]:
    """Expand '§§ 12-15 BGB' → ['§ 12 BGB', '§ 13 BGB', '§ 14 BGB', '§ 15 BGB'].

    Only expands pure numeric ranges. Ranges with letter suffixes (§§ 12a-12c)
    are left unchanged since intermediate values are not predictable.
    """
    m = _RANGE_RE.search(raw)
    if not m:
        return [raw]

    start_str, end_str = m.group(1), m.group(2)

    if not (start_str.isdigit() and end_str.isdigit()):
        return [raw]

    start, end = int(start_str), int(end_str)
    if end <= start or (end - start) > 50:
        return [raw]

    suffix = raw[m.end() :].strip()
    return [f"§ {n} {suffix}".strip() for n in range(start, end + 1)]


def _expand_f_ff(
    para: ParagraphRef,
    law: str,
    is_art: bool,
    ff_expansion: int | None,
) -> list[LawReference]:
    """Expand f. and ff. continuation markers into individual paragraph refs.

    Legal meaning:
        f.  (und folgende) = that paragraph and the next one -> always exactly 2 paragraphs
        ff. (und fortfolgende) = that paragraph and the following ones -> count set by ff_expansion

    Only applies to pure numeric paragraph numbers.
    If ff_expansion is None, ff. is not expanded (left as-is).
    """
    if not (para.is_f or para.is_ff) or not para.paragraph.isdigit():
        return []
    if para.is_ff and ff_expansion is None:
        return []
    base = int(para.paragraph)
    count = 2 if para.is_f else ff_expansion
    refs = []
    for n in range(base, base + count):
        expanded_para = ParagraphRef(
            paragraph=str(n),
            sub_refs=para.sub_refs,
            ivm_refs=para.ivm_refs,
        )
        refs.append(
            LawReference(paragraphs=[expanded_para], law=law, raw="", is_art=is_art)
        )
    return refs


def _parse_and_expand(raw: str, ff_expansion: int | None = None) -> list[LawReference]:
    """Parse a raw string and expand any multi-target ParagraphRefs."""
    ref = _parse_reference(raw)
    if not ref.paragraphs:
        return [ref]

    expanded_paragraphs: list[ParagraphRef] = []
    for para in ref.paragraphs:
        # expand f./ff. into individual paragraph refs
        ff_expanded = _expand_f_ff(para, ref.law or "", ref.is_art, ff_expansion)
        if ff_expanded:
            return ff_expanded
        expanded_paragraphs.extend(_expand_multi_target(para))

    return [
        LawReference(paragraphs=[para], law=ref.law, raw=raw, is_art=ref.is_art)
        for para in expanded_paragraphs
    ]


# canonical string reconstruction
_ROMAN_RE = re.compile(r"^[IVXivx]+$")


def _roman_to_arabic(tok: str) -> str:
    """Convert a Roman numeral string to its Arabic integer string.

    Examples:
        >>> _roman_to_arabic('III')
        '3'
        >>> _roman_to_arabic('XII')
        '12'
    """
    tok = tok.upper()
    vals = {"I": 1, "V": 5, "X": 10, "L": 50, "C": 100, "D": 500, "M": 1000}
    result, prev = 0, 0
    for ch in reversed(tok):
        v = vals.get(ch, 0)
        result += v if v >= prev else -v
        prev = v
    return str(result)


def _normalise_law(law: str) -> str:
    """Normalise a law abbreviation string.

    Converts Roman numeral suffixes to Arabic so the string matches
    the storage format used in gesetze-im-internet.de.

    Examples:
        >>> _normalise_law('SGB III')
        'SGB 3'
        >>> _normalise_law('BGB')
        'BGB'
    """
    tokens = law.strip().split()
    if len(tokens) >= 2 and _ROMAN_RE.match(tokens[-1]):
        tokens[-1] = _roman_to_arabic(tokens[-1])
    return " ".join(tokens)


def _reconstruct(ref: LawReference) -> str:
    """Reconstruct a clean canonical reference string from a LawReference.

    Output format: '§ {para} {sub_refs...} {law}', e.g. '§ 2 Abs. 1 Nr. 1 UrhG'
    For Art.-based refs: 'Art. {para} {sub_refs...} {law}'
    """
    if not ref.paragraphs:
        return ref.raw

    para = ref.paragraphs[0]
    prefix = "Art." if ref.is_art else "§"
    parts = [f"{prefix} {para.paragraph}"]

    if para.range_end:
        parts.append(f"bis {para.range_end}")
    if para.is_ff:
        parts.append("ff.")
    elif para.is_f:
        parts.append("f.")

    for sr in para.sub_refs:
        parts.append(str(sr))

    if para.ivm_refs:
        parts.append("iVm")
        for sr in para.ivm_refs:
            parts.append(str(sr))

    if ref.law:
        parts.append(_normalise_law(ref.law))

    return " ".join(parts)


def _expand_abbreviations(raw: str) -> str:
    """Expand common shorthand and fix encoding issues before parsing.

    - Fixes mojibake sequences (√§→ä, √ü→ü, √ú→ü, √∂→ö) from broken UTF-8
    - Expands plural level keywords: Sätze→Satz, Absätze→Absatz
    - Expands S. N → Satz N (only when followed by a digit)
    - Expands Ab. / Ab  → Abs. (typo shorthand for Absatz)
    - Expands Ziffer / Ziff. → Nr. (synonym for Nummer)
    - Expands Roman numeral Absatz shorthand: § N I N → § N Abs. 1 N
      e.g. § 62 I 2 AufenthG → § 62 Abs. 1 Satz 2 AufenthG
    - Expands word number "eins" → "1" in Satz context
    """
    # fix mojibake
    raw = (
        raw.replace("√§", "ä").replace("√ü", "ü").replace("√ú", "ü").replace("√∂", "ö")
    )
    # plural level keywords → singular so parser recognises them
    raw = re.sub(r"\bSätze\b", "Satz", raw)
    raw = re.sub(r"\bAbsätze\b", "Absatz", raw)
    # Ab. / Ab shorthand for Abs.
    raw = re.sub(r"\bAb\.\s*(?=\d)", "Abs. ", raw)
    raw = re.sub(r"\bAb\s+(?=\d)", "Abs. ", raw)
    # Ziffer / Ziff. → Nr.
    raw = re.sub(r"\bZiff(?:er)?\.?\s*(?=\d)", "Nr. ", raw, flags=re.IGNORECASE)
    # S. N → Satz N
    raw = re.sub(r"(?<![A-Z])S[.]\s*(?=\d)", "Satz ", raw)
    # "Satz eins" → "Satz 1"
    raw = re.sub(r"\bSatz\s+eins\b", "Satz 1", raw, flags=re.IGNORECASE)
    # Roman numeral Absatz shorthand: § N {I|II|III|IV|V} N LAW
    # matches a Roman numeral standing alone between the paragraph number and a digit/law
    # e.g. § 62 I 2 AufenthG → § 62 Abs. 1 Satz 2 AufenthG
    _ROMAN = {
        "I": 1,
        "II": 2,
        "III": 3,
        "IV": 4,
        "V": 5,
        "VI": 6,
        "VII": 7,
        "VIII": 8,
        "IX": 9,
    }

    def _expand_roman(m: re.Match) -> str:
        roman = m.group(1)
        after = m.group(2)  # what follows the Roman numeral
        absatz_n = _ROMAN.get(roman.upper(), 0)
        if not absatz_n:
            return m.group(0)
        result = f"Abs. {absatz_n}"
        if after and re.match(r"\d", after.strip()):
            result += f" Satz {after.strip()}"
            return result
        return result

    raw = re.sub(
        r"(\b\d+[a-z]?)\s+(I{1,3}|IV|VI{0,3}|VIII|IX)\b"
        r"(\s+\d+)?(?=\s*(?:Nr\.|Nrn\.|Satz|[A-ZÄÖÜ]|$))",
        lambda m: (
            m.group(1)
            + " Abs. "
            + str(_ROMAN.get(m.group(2).upper(), m.group(2)))
            + (" Satz " + m.group(3).strip() if m.group(3) else "")
        ),
        raw,
    )
    return raw


# Public API
def normalise(raw: str, ff_expansion: int | None = None) -> list[str]:
    """Normalise a raw German legal reference string into canonical refs.

    Args:
        raw: Any German legal citation string, e.g.
            '§ 2 Abs. 1 Nr. 1, Nr. 7, Abs. 2 UrhG'
        ff_expansion: Number of paragraphs to expand ff. into. If None (default),
            ff. is preserved as-is. f. always expands to exactly 2 regardless of
            this argument.

    Returns:
        Deduplicated list of canonical reference strings, each independently
        resolvable by the resolver.

    Examples:
        >>> normalise('§ 312 i.V.m. § 355 BGB')
        ['§ 312 BGB', '§ 355 BGB']
        >>> normalise('§§ 12-15 BGB')
        ['§ 12 BGB', '§ 13 BGB', '§ 14 BGB', '§ 15 BGB']
        >>> normalise('§ 2 Abs. 1 Nr. 1, Nr. 7, Abs. 2 UrhG')
        ['§ 2 Abs. 1 Nr. 1 UrhG', '§ 2 Abs. 1 Nr. 7 UrhG', '§ 2 Abs. 2 UrhG']
        >>> normalise('§ 312 ff. BGB', ff_expansion=3)
        ['§ 312 BGB', '§ 313 BGB', '§ 314 BGB']
    """
    raw = raw.strip()
    raw = _expand_abbreviations(raw)

    ivm_parts = _split_ivm(raw)
    canonical: list[str] = []

    for part in ivm_parts:
        part = part.strip()
        multi_law_parts = _split_multi_law(part)
        range_expanded = []
        for ml_part in multi_law_parts:
            range_expanded.extend(_expand_range(ml_part))
        for item in range_expanded:
            refs = _parse_and_expand(item, ff_expansion=ff_expansion)
            for ref in refs:
                canon = _reconstruct(ref)
                if canon and canon not in canonical:
                    canonical.append(canon)

    return canonical
