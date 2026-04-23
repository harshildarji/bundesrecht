"""
bundesrecht.references - internal parser for German legal reference strings.

Tokenises and parses raw citation strings into structured
LawReference/ParagraphRef/SubReference objects.

Also provides _expand_multi_target which splits compound sub-ref lists
(e.g. Abs. 1 Nr. 1, Nr. 7, Abs. 2) into individual canonical targets.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional


# Reference Data Model
@dataclass
class SubReference:
    """One 'layer' within a legal reference.

    Examples:
        Abs. 2     → level='Abs',      number='2'
        Satz 1     → level='Satz',     number='1'
        Nr. 3      → level='Nr',       number='3'
        Buchst. a  → level='Buchst',   number='a'
        Alt. 1     → level='Alt',      number='1'
        Halbsatz 1 → level='Halbsatz', number='1'
    """

    level: str  # 'Abs', 'Satz', 'Nr', 'Buchst', 'Alt', 'Halbsatz'
    number: str  # e.g. '2', '1a', 'a', '1'
    range_end: Optional[str] = None  # set if 'Abs. 2 bis 4' → number='2', range_end='4'

    _DOT_LEVELS = {"Abs", "Nr", "Buchst", "Alt"}
    _NO_DOT_LEVELS = {"Halbsatz", "S"}

    def __str__(self) -> str:
        if self.level in self._DOT_LEVELS:
            s = f"{self.level}. {self.number}"
        else:
            s = f"{self.level} {self.number}"
        if self.range_end:
            s += f" bis {self.range_end}"
        return s


@dataclass
class ParagraphRef:
    """A single-paragraph reference, e.g. § 312 Abs. 2 Satz 1 Nr. 3 Buchst. a.

    May be linked via 'iVm' to another set of sub-references.
    """

    paragraph: str  # '312', '312a', '1', etc.
    sub_refs: list[SubReference] = field(default_factory=list)
    range_end: Optional[str] = None  # § 312 bis 314 → range_end='314'
    is_ff: bool = False  # § 312 ff.
    is_f: bool = False  # § 312 f.
    ivm_refs: list[SubReference] = field(default_factory=list)  # after 'iVm'

    def __str__(self) -> str:
        s = self.paragraph
        if self.range_end:
            s += f" bis {self.range_end}"
        if self.is_ff:
            s += " ff."
        elif self.is_f:
            s += " f."
        for sr in self.sub_refs:
            s += f" {sr}"
        if self.ivm_refs:
            s += " iVm " + " ".join(str(r) for r in self.ivm_refs)
        return s


@dataclass
class LawReference:
    """A fully parsed legal reference, potentially containing multiple paragraphs
    and a law abbreviation.

    Examples:
        §§ 312, 313 BGB
        § 312 Abs. 2 Satz 1 BGB
    """

    paragraphs: list[ParagraphRef]
    law: Optional[str] = None  # 'BGB', 'ZPO', etc.
    raw: str = ""
    is_art: bool = False  # True when parsed from Art./Artikel prefix

    def __str__(self) -> str:
        if self.is_art:
            prefix = "Art."
        else:
            prefix = "§§" if len(self.paragraphs) > 1 else "§"
        para_str = ", ".join(str(p) for p in self.paragraphs)
        law_str = f" {self.law}" if self.law else ""
        return f"{prefix} {para_str}{law_str}"

    @staticmethod
    def parse(ref_string: str) -> "LawReference":
        """Parse a German law reference string into a LawReference object."""
        return _parse_reference(ref_string)


# Tokeniser/Parser Internals
_LEVEL_PATTERNS = [
    (r"Abs\.?", "Abs"),
    (r"Absatz", "Abs"),
    (r"S\.(?!\s*\d+\s+\w+\b)", "Satz"),
    (r"Satz", "Satz"),
    (r"Halbs\.?", "Halbsatz"),
    (r"Halbsatz", "Halbsatz"),
    (r"Nr\.?", "Nr"),
    (r"Nrn\.?", "Nr"),
    (r"Nummer", "Nr"),
    (r"Buchst\.?", "Buchst"),
    (r"Buchstabe", "Buchst"),
    (r"Alt\.?", "Alt"),
    (r"Alternative", "Alt"),
    (r"HS\.?", "Halbsatz"),
]

_LEVEL_RE = re.compile(
    r"\b(" + "|".join(p for p, _ in _LEVEL_PATTERNS) + r")\b\.?", re.IGNORECASE
)

_NUM_RE = re.compile(r"^(\d+[a-z]?|[a-z]|[IVXivx]+)$", re.IGNORECASE)
_RANGE_WORDS = {"bis", "to"}
_RANGE_SUFFIX = re.compile(r"(?:ff\.|ff|f\.)\s*$")
_IVM_RE = re.compile(r"\biVm\.?\b|i\.V\.m\.?", re.IGNORECASE)


def _canonical_level(token: str) -> str:
    """Map a matched level keyword to its canonical name."""
    t = token.rstrip(".").lower()
    mapping = {
        "abs": "Abs",
        "absatz": "Abs",
        "s": "Satz",
        "satz": "Satz",
        "halbs": "Halbsatz",
        "halbsatz": "Halbsatz",
        "hs": "Halbsatz",
        "nr": "Nr",
        "nrn": "Nr",
        "nummer": "Nr",
        "buchst": "Buchst",
        "buchstabe": "Buchst",
        "alt": "Alt",
        "alternative": "Alt",
    }
    return mapping.get(t, token)


def _tokenise(s: str) -> list[str]:
    """Split a reference string into tokens, preserving meaningful punctuation."""
    s = s.replace("\u2013", "-").replace("\u2014", "-")
    s = re.sub(r"([,;])", r" \1 ", s)
    return s.split()


def _parse_sub_refs(tokens: list[str], pos: int) -> tuple[list[SubReference], int]:
    """Parse zero or more SubReference items from the token list starting at pos.

    Args:
        tokens: Tokenised reference string.
        pos: Current position in the token list.

    Returns:
        Tuple of (list of SubReferences, updated position).
    """
    sub_refs: list[SubReference] = []
    n = len(tokens)

    while pos < n:
        tok = tokens[pos]

        m = _LEVEL_RE.fullmatch(tok)
        if not m:
            m2 = re.match(
                r"^(Abs\.?|Satz|Nr\.?|Nrn\.?|Buchst\.?|Alt\.?|Halbs\.?|Halbsatz|S\.?|HS\.?|Absatz|Nummer|Buchstabe|Alternative)(\d+[a-z]?|[a-z])$",
                tok,
                re.IGNORECASE,
            )
            if m2:
                level = _canonical_level(m2.group(1))
                number = m2.group(2)
                sub_refs.append(SubReference(level=level, number=number))
                pos += 1
                continue
            break

        level = _canonical_level(tok)
        pos += 1

        if pos >= n:
            break

        number_tok = tokens[pos]
        number_tok_clean = number_tok.rstrip(".,")

        if not _NUM_RE.match(number_tok_clean):
            break

        number = number_tok_clean
        pos += 1
        range_end = None

        if pos < n and tokens[pos].lower() in _RANGE_WORDS:
            pos += 1
            if pos < n and _NUM_RE.match(tokens[pos].rstrip(".,")):
                range_end = tokens[pos].rstrip(".,")
                pos += 1

        if (
            pos < n
            and re.match(r"^[a-z]$", tokens[pos], re.IGNORECASE)
            and level == "Nr"
        ):
            sub_refs.append(
                SubReference(level=level, number=number, range_end=range_end)
            )
            sub_refs.append(SubReference(level="Buchst", number=tokens[pos]))
            pos += 1
            continue

        sub_refs.append(SubReference(level=level, number=number, range_end=range_end))

        if pos < n and tokens[pos] in (",", "und", "oder"):
            if pos + 1 < n and _LEVEL_RE.fullmatch(tokens[pos + 1]):
                pos += 1
                continue
            else:
                break

    return sub_refs, pos


def _looks_like_law(tok: str) -> bool:
    """Heuristic check: does this token look like a law abbreviation?"""
    if not tok:
        return False
    tok = tok.rstrip(".,;")
    if not tok:
        return False
    if tok.isdigit():
        return False
    if re.match(r"^[IVXivx]+$", tok):
        return False
    if not re.search(r"[A-Za-z]", tok):
        return False
    if _LEVEL_RE.fullmatch(tok):
        return False
    return True


def _parse_paragraph_block(
    tokens: list[str], pos: int
) -> tuple[Optional[ParagraphRef], int]:
    """Parse one paragraph reference starting at pos.

    The leading '§' or '§§' token is assumed to have already been consumed.

    Args:
        tokens: Tokenised reference string.
        pos: Current position in the token list.

    Returns:
        Tuple of (ParagraphRef or None, updated position).
    """
    n = len(tokens)
    if pos >= n:
        return None, pos

    para_tok = tokens[pos].rstrip(".,")
    if not re.match(r"^\d+[a-z]?$", para_tok, re.IGNORECASE):
        return None, pos

    paragraph = para_tok
    pos += 1

    if (
        pos < n
        and re.match(r"^[a-z]$", tokens[pos], re.IGNORECASE)
        and not re.match(r"^[A-ZÄÖÜ]", tokens[pos])
    ):
        tokens[pos + 1] if pos + 1 < n else ""
        paragraph = paragraph + tokens[pos].lower()
        pos += 1

    is_ff = False
    is_f = False
    range_end = None

    if pos < n:
        nxt = tokens[pos]
        if nxt in ("ff.", "ff"):
            is_ff = True
            pos += 1
        elif nxt in ("f.", "f"):
            is_f = True
            pos += 1
        elif nxt.lower() == "bis":
            pos += 1
            if pos < n and re.match(r"^\d+[a-z]?$", tokens[pos], re.IGNORECASE):
                range_end = tokens[pos].rstrip(".,")
                pos += 1

    sub_refs, pos = _parse_sub_refs(tokens, pos)

    ivm_refs: list[SubReference] = []
    if pos < n and _IVM_RE.match(tokens[pos]):
        pos += 1
        ivm_refs, pos = _parse_sub_refs(tokens, pos)

    return (
        ParagraphRef(
            paragraph=paragraph,
            sub_refs=sub_refs,
            range_end=range_end,
            is_ff=is_ff,
            is_f=is_f,
            ivm_refs=ivm_refs,
        ),
        pos,
    )


def _parse_reference(ref_string: str) -> LawReference:
    """Convert a raw reference string to a LawReference."""
    raw = ref_string.strip()
    tokens = _tokenise(raw)
    n = len(tokens)
    pos = 0

    paragraphs: list[ParagraphRef] = []
    law: Optional[str] = None

    if pos >= n:
        return LawReference(paragraphs=[], law=None, raw=raw)

    is_art = False
    multi = False
    if tokens[pos] in ("§§", "§"):
        multi = tokens[pos] == "§§"
        pos += 1
    elif tokens[pos].startswith("§§"):
        multi = True
        rest = tokens[pos][2:]
        if rest:
            tokens.insert(pos + 1, rest)
        pos += 1
    elif tokens[pos].startswith("§"):
        rest = tokens[pos][1:]
        if rest:
            tokens.insert(pos + 1, rest)
        pos += 1
    elif re.match(r"^Artike?l?\.?$", tokens[pos], re.IGNORECASE):
        is_art = True
        pos += 1
    elif re.match(r"^Art\.?$", tokens[pos], re.IGNORECASE):
        is_art = True
        pos += 1
    elif re.match(r"^Art\.?\d", tokens[pos], re.IGNORECASE):
        is_art = True
        rest = re.sub(r"^Art\.?", "", tokens[pos])
        if rest:
            tokens.insert(pos + 1, rest)
        pos += 1

    para, pos = _parse_paragraph_block(tokens, pos)
    if para:
        paragraphs.append(para)

    while multi and pos < n and tokens[pos] in (",", "und", "oder", ";"):
        pos += 1
        if pos >= n:
            break
        nxt = tokens[pos].rstrip(".,")
        if re.match(r"^\d+[a-z]?$", nxt, re.IGNORECASE):
            para2, pos = _parse_paragraph_block(tokens, pos)
            if para2:
                paragraphs.append(para2)
        else:
            break

    if pos < n:
        remaining = tokens[pos:]
        for i in range(len(remaining)):
            candidate = " ".join(remaining[i:]).rstrip(".,;")
            if _looks_like_law(remaining[i].rstrip(".,;")):
                law = candidate
                break

    return LawReference(paragraphs=paragraphs, law=law, raw=raw, is_art=is_art)


# Data Access Layer
def _expand_multi_target(para_ref: ParagraphRef) -> list[ParagraphRef]:
    """Expand a ParagraphRef with repeated sub_ref levels into multiple ParagraphRefs,
    each representing one distinct normative target.

    Examples:
        Abs.1, Nr.1, Nr.7, Abs.2  → [Abs.1+Nr.1, Abs.1+Nr.7, Abs.2]
        Abs.1, Nr.1, Buchst.a, Buchst.b → [Abs.1+Nr.1+Buchst.a, Abs.1+Nr.1+Buchst.b]
        Abs.1, Nr.1 → [Abs.1+Nr.1]  (no expansion needed)
    """
    srs = para_ref.sub_refs
    if not srs:
        return [para_ref]

    LEVEL_ORDER = ["Abs", "Satz", "Nr", "Buchst", "Alt", "Halbsatz"]

    def level_rank(lvl: str) -> int:
        try:
            return LEVEL_ORDER.index(lvl)
        except ValueError:
            return len(LEVEL_ORDER)

    targets: list[list] = []
    current: list = []
    seen_levels: set = set()

    for sr in srs:
        rank = level_rank(sr.level)
        if sr.level in seen_levels:
            targets.append(current)
            current = [s for s in current if level_rank(s.level) < rank]
            seen_levels = {s.level for s in current}
        elif seen_levels and rank < max(level_rank(s.level) for s in current):
            targets.append(current)
            current = [s for s in current if level_rank(s.level) < rank]
            seen_levels = {s.level for s in current}

        current.append(sr)
        seen_levels.add(sr.level)

    if current:
        targets.append(current)

    if len(targets) <= 1:
        return [para_ref]

    return [
        ParagraphRef(
            paragraph=para_ref.paragraph,
            sub_refs=sub_refs,
            range_end=para_ref.range_end,
            is_ff=para_ref.is_ff,
            is_f=para_ref.is_f,
            ivm_refs=para_ref.ivm_refs,
        )
        for sub_refs in targets
    ]


def parse_reference(ref_string: str) -> LawReference:
    """Parse a reference string without loading any law data."""
    return _parse_reference(ref_string)
