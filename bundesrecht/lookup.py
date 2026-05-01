"""
bundesrecht.lookup - resolves canonical German legal references against a loaded dataset.

Provides LawData (per-law data access), QueryResult (resolution output),
and LawLibrary (main resolver).

Import from bundesrecht directly rather than using this module directly:
    from bundesrecht import Bundesrecht
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterator, Optional, Union

from bundesrecht.references import (
    LawReference,
    ParagraphRef,
    SubReference,
    _expand_multi_target,
)


class LawData:
    """Holds the parsed data for a single law.

    Provides lookup by section key (paragraph string like '§ 312').
    """

    def __init__(self, data: dict):
        self.gesetze_id: str = data.get("gesetze_id", "")
        self.jurabk: str = data.get("jurabk", "")
        self.metadaten: dict = data.get("metadaten", {})
        self.fussnoten: list = data.get("fussnoten", [])
        self.quelle: dict = data.get("quelle", {})
        self.sections: dict = data.get("sections", {})
        self._index: dict[str, dict] = {}
        self._key_map: dict[str, str] = {}
        # sections is a list of dicts with a "paragraf" key
        if isinstance(self.sections, list):
            for sec in self.sections:
                key = sec.get("paragraf", "")
                norm = _normalise_section_key(key)
                if norm:
                    self._index[norm] = sec
                    self._key_map[norm] = key
        else:
            # legacy dict format
            for key, val in self.sections.items():
                norm = _normalise_section_key(key)
                if norm:
                    self._index[norm] = val
                    self._key_map[norm] = key

    def get_section(self, paragraph: str) -> Optional[dict]:
        """Retrieve a section by normalised paragraph number (e.g. '312', 'art_20')."""
        key = paragraph.lower()
        if key.startswith("art_"):
            return self._index.get(key)
        return self._index.get(key.lstrip("0") or "0")

    def get_absatz(self, paragraph: str, absatz: Union[int, str]) -> Optional[dict]:
        """Get a specific Absatz from a section.

        Args:
            paragraph: Paragraph number string, e.g. '312'.
            absatz: Absatz identifier, either int (1, 2) or str ('1a', '2b').

        Returns:
            The matching Absatz dict, or None if not found.
        """
        section = self.get_section(paragraph)
        if not section:
            return None
        content = section.get("content", [])
        absatz_str = str(absatz)
        for field_name in ("absatz",):
            for c in content:
                text = c.get(field_name, "")
                if text and re.match(rf"^\({re.escape(absatz_str)}\)", text):
                    return c
        if absatz_str == "1" and len(content) == 1:
            return content[0]
        return None

    def get_satz(
        self, paragraph: str, absatz: Optional[int], satz: int
    ) -> Optional[str]:
        """Get a specific Satz from within an Absatz.

        Args:
            paragraph: Paragraph number string.
            absatz: Absatz number, or None to use the first content item.
            satz: 1-based Satz index.

        Returns:
            The sentence text, or None if not found.
        """
        if absatz is not None:
            abs_data = self.get_absatz(paragraph, absatz)
        else:
            section = self.get_section(paragraph)
            abs_data = (
                section["content"][0] if section and section.get("content") else None
            )

        if not abs_data:
            return None

        text = abs_data.get("absatz", "")
        text = re.sub(r"^\(\d+\w*\)\s*", "", text)
        sentences = _split_sentences(text)
        if 1 <= satz <= len(sentences):
            return sentences[satz - 1]
        return None

    @staticmethod
    def _match_nummer(nummern: list, nummer: int) -> Optional[dict]:
        """Match a Nummer item by its text prefix (e.g. "2." or "1a.") rather than
        positional index. Falls back to positional if no prefix match is found.
        Handles non-sequential lists like 1, 1a, 2, 3 correctly.
        """
        target = str(nummer)
        for nr in nummern:
            text = nr.get("text", "") if isinstance(nr, dict) else str(nr)
            m = re.match(r"^(\d+[a-z]?)\.", text.lstrip())
            if m and m.group(1) == target:
                return nr
        if 1 <= nummer <= len(nummern):
            return nummern[nummer - 1]
        return None

    def get_nummer(
        self, paragraph: str, absatz: Optional[Union[int, str]], nummer: int
    ) -> Optional[dict]:
        """Get a specific Nummer item from an Absatz.

        Args:
            paragraph: Paragraph number string.
            absatz: Absatz identifier, or None to use the first content item.
            nummer: 1-based Nummer index.

        Returns:
            The Nummer dict (with text + buchstaben), or None if not found.
        """
        if absatz is not None:
            abs_data = self.get_absatz(paragraph, absatz)
        else:
            section = self.get_section(paragraph)
            abs_data = (
                section["content"][0] if section and section.get("content") else None
            )

        if not abs_data:
            return None

        nummern = abs_data.get("nummer", [])
        return self._match_nummer(nummern, nummer)

    def get_buchstabe(
        self,
        paragraph: str,
        absatz: Optional[Union[int, str]],
        nummer: int,
        buchstabe: str,
    ) -> Optional[str]:
        """Get a specific Buchstabe text from within a Nummer.

        Args:
            paragraph: Paragraph number string.
            absatz: Absatz identifier.
            nummer: 1-based Nummer index.
            buchstabe: Letter label, e.g. 'a', 'b', 'c'.

        Returns:
            The Buchstabe text, or None if not found.
        """
        nr_data = self.get_nummer(paragraph, absatz, nummer)
        if not nr_data or not isinstance(nr_data, dict):
            return None
        buchstaben = nr_data.get("buchstaben", [])
        label = f"{buchstabe})"
        for buch in buchstaben:
            text = buch.get("text", "") if isinstance(buch, dict) else str(buch)
            if text.startswith(label) or text.startswith(f"{buchstabe} )"):
                return text
        return None

    def get_unterbuchstabe(
        self,
        paragraph: str,
        absatz: Optional[Union[int, str]],
        nummer: int,
        buchstabe: str,
        unterbuchstabe: str,
    ) -> Optional[str]:
        """Get a specific Unterbuchstabe text from within a Buchstabe.

        Args:
            paragraph: Paragraph number string.
            absatz: Absatz identifier.
            nummer: 1-based Nummer index.
            buchstabe: Letter label, e.g. 'a', 'b'.
            unterbuchstabe: Double-letter label, e.g. 'aa', 'bb'.

        Returns:
            The Unterbuchstabe text, or None if not found.
        """
        buch_text = self.get_buchstabe(paragraph, absatz, nummer, buchstabe)
        if buch_text is None:
            return None
        nr_data = self.get_nummer(paragraph, absatz, nummer)
        if not nr_data or not isinstance(nr_data, dict):
            return None
        buchstaben = nr_data.get("buchstaben", [])
        label_b = f"{buchstabe})"
        for buch in buchstaben:
            text = buch.get("text", "") if isinstance(buch, dict) else str(buch)
            if not (text.startswith(label_b) or text.startswith(f"{buchstabe} )")):
                continue
            label_u = f"{unterbuchstabe})"
            for ubuch in (
                buch.get("unterbuchstaben", []) if isinstance(buch, dict) else []
            ):
                u_text = (
                    ubuch.get("text", "") if isinstance(ubuch, dict) else str(ubuch)
                )
                if u_text.lstrip().startswith(label_u) or u_text.lstrip().startswith(
                    f"{unterbuchstabe} )"
                ):
                    return u_text
        return None


def _normalise_section_key(key: str) -> Optional[str]:
    """Convert section dict keys like '§ 312', 'Art 20' to a simple normalised form.

    Returns None if the key does not represent a single addressable paragraph.
    """
    key = key.strip()
    key = re.sub(r"^\([^)]*\)\s*", "", key)
    m = re.match(r"^§\s*(\d+[a-z]?)", key, re.IGNORECASE)
    if m:
        num = m.group(1).lstrip("0") or "0"
        return num.lower()
    m = re.match(r"^Art\.?\s*(\d+[a-z]?)", key, re.IGNORECASE)
    if m:
        num = m.group(1).lstrip("0") or "0"
        return f"art_{num.lower()}"
    return None


def _split_sentences(text: str) -> list[str]:
    """Rough sentence splitter for German legal text.

    Splits on '. ' followed by a capital letter, avoiding splits on common
    abbreviations like 'Abs. 2' or 'Nr. 3'.
    """
    placeholder_map = {}
    abbrevs = [
        "Abs.",
        "Nr.",
        "Satz",
        "S.",
        "Art.",
        "Abs",
        "vgl.",
        "bzw.",
        "ggf.",
        "etc.",
        "usw.",
        "z.B.",
        "d.h.",
        "1.",
        "2.",
        "3.",
        "4.",
        "5.",
        "6.",
        "7.",
        "8.",
        "9.",
        "10.",
        "11.",
        "12.",
        "13.",
        "14.",
        "15.",
        "16.",
        "17.",
        "18.",
        "19.",
        "20.",
        "21.",
        "22.",
        "23.",
        "24.",
        "25.",
        "26.",
        "27.",
        "28.",
        "29.",
        "30.",
        "31.",
    ]
    protected = text
    for i, abbr in enumerate(abbrevs):
        token = f"__ABBR{i}__"
        protected = protected.replace(abbr, token)
        placeholder_map[token] = abbr

    parts = re.split(r"\.\s+(?=[A-ZÄÖÜ])", protected)

    sentences = []
    for part in parts:
        for token, abbr in placeholder_map.items():
            part = part.replace(token, abbr)
        sentences.append(part.strip())

    return [s for s in sentences if s]


def _strip_leaf_prefix(text: str, depth: str) -> str:
    """Strip leading notation prefix only at the resolved leaf level."""
    if not text:
        return text
    if depth == "absatz":
        text = re.sub(r"^\(\d+\w*\)\s*", "", text)
    elif depth == "nummer":
        text = re.sub(r"^\d+\.\s*", "", text)
    elif depth == "buchstabe":
        text = re.sub(r"^[a-z]\)\s*", "", text, flags=re.IGNORECASE)
    return text.strip()


def _assemble_absatz(c: dict) -> str:
    """Assemble the full text of a content item.

    Combines lead-in text (absatz), all Nummern, and Listenende.
    """
    parts = []
    lead = c.get("absatz", "")
    if lead:
        parts.append(lead)
    for nr in c.get("nummer", []):
        nr_text = nr.get("text", "") if isinstance(nr, dict) else str(nr)
        if nr_text:
            parts.append(nr_text)
        for buch in nr.get("buchstaben", []) if isinstance(nr, dict) else []:
            buch_text = buch.get("text", "") if isinstance(buch, dict) else str(buch)
            if buch_text:
                parts.append(buch_text)
            for ubuch in (
                buch.get("unterbuchstaben", []) if isinstance(buch, dict) else []
            ):
                u_text = (
                    ubuch.get("text", "") if isinstance(ubuch, dict) else str(ubuch)
                )
                if u_text:
                    parts.append(u_text)
    listenende = c.get("listenende", "")
    if listenende:
        parts.append(listenende)
    return " ".join(parts)


# Result Object
@dataclass
class QueryResult:
    """Holds the result of a law reference query."""

    reference: LawReference
    law_data: LawData
    section: Optional[dict] = None
    absatz_data: Optional[dict] = None
    satz_text: Optional[str] = None
    nummer_text: Optional[str] = None
    unterbuchst_text: Optional[str] = None
    resolved_depth: str = "section"
    resolution_note: str = ""
    resolved_para: Optional["ParagraphRef"] = field(default=None)

    def full_text(self) -> str:
        """Return the most specific text found for the reference.

        Resolution priority: Satz → Nummer → Absatz → full section content.
        """
        if self.satz_text:
            return self.satz_text
        if self.unterbuchst_text:
            return _strip_leaf_prefix(self.unterbuchst_text, "buchstabe")
        if self.nummer_text:
            if isinstance(self.nummer_text, str):
                return _strip_leaf_prefix(self.nummer_text, "buchstabe")
            if isinstance(self.nummer_text, dict):
                nr_text = self.nummer_text.get("text", "")
                parts = []
                if nr_text:
                    parts.append(_strip_leaf_prefix(nr_text, "nummer"))
                for buch in self.nummer_text.get("buchstaben", []):
                    buch_text = (
                        buch.get("text", "") if isinstance(buch, dict) else str(buch)
                    )
                    if buch_text:
                        parts.append(buch_text)
                    for ubuch in (
                        buch.get("unterbuchstaben", [])
                        if isinstance(buch, dict)
                        else []
                    ):
                        u_text = (
                            ubuch.get("text", "")
                            if isinstance(ubuch, dict)
                            else str(ubuch)
                        )
                        if u_text:
                            parts.append(u_text)
                return " ".join(parts)
        if self.absatz_data:
            return _strip_leaf_prefix(_assemble_absatz(self.absatz_data), "absatz")
        if self.section:
            content = self.section.get("content", [])
            return "\n\n".join(_assemble_absatz(c) for c in content)
        return ""

    def titel(self) -> str:
        """Return the section heading (Überschrift), if one exists."""
        if self.section:
            return self.section.get("titel", "")
        return ""

    def normkette(self) -> str:
        """Return the normative chain leading to the resolved leaf.

        Only meaningful at nummer/buchstabe depth. Each level separated by ' → '.
        """
        parts = []

        if self.absatz_data is not None and self.nummer_text is not None:
            lead = self.absatz_data.get("absatz", "")
            if lead:
                parts.append(_strip_leaf_prefix(lead.rstrip(":").strip(), "absatz"))

        if self.nummer_text is not None:
            if isinstance(self.nummer_text, dict):
                nr_text = self.nummer_text.get("text", "")
                if nr_text:
                    parts.append(
                        _strip_leaf_prefix(nr_text, "nummer")
                    )  # buchstaben rendered by caller

            elif isinstance(self.nummer_text, str):
                if self.absatz_data:
                    nr_ref = None
                    for sr in (
                        self.reference.paragraphs[0].sub_refs
                        if self.reference.paragraphs
                        else []
                    ):
                        if sr.level == "Nr":
                            try:
                                nr_ref = int(sr.number)
                            except ValueError:
                                pass
                    if nr_ref is not None:
                        nummern = self.absatz_data.get("nummer", [])
                        if 1 <= nr_ref <= len(nummern):
                            nr_dict = nummern[nr_ref - 1]
                            if isinstance(nr_dict, dict):
                                nr_lead = nr_dict.get("text", "")
                                if nr_lead:
                                    parts.append(_strip_leaf_prefix(nr_lead, "nummer"))
                parts.append(_strip_leaf_prefix(self.nummer_text, "buchstabe"))

        # append unterbuchstabe if resolved
        if self.unterbuchst_text is not None:
            parts.append(_strip_leaf_prefix(self.unterbuchst_text, "buchstabe"))

        if not parts:
            return self.full_text()

        chain = " → ".join(parts)
        if self.resolution_note:
            chain += f"  [Note: {self.resolution_note}]"
        return chain

    def __repr__(self) -> str:
        note = f"\n  note={self.resolution_note!r}" if self.resolution_note else ""
        return (
            f"QueryResult(\n"
            f"  ref={self.reference},\n"
            f"  law={self.law_data.jurabk},\n"
            f"  depth={self.resolved_depth},\n"
            f"  titel={self.titel()!r},\n"
            f"  text={self.full_text()[:120]!r}...{note}\n"
            f")"
        )


class LawLibrary:
    """Loads laws from a JSONL file and provides query methods.

    Args:
        path: Path to gesetze.jsonl (one JSON object per line).

    Examples:
        >>> lib = LawLibrary("gesetze.jsonl")
        >>> results = lib.query("§ 312 Abs. 2 BGB")
    """

    def __init__(self, path: Union[str, Path]):
        self._laws: dict[str, LawData] = {}
        self._load(Path(path))

    def _load(self, path: Path) -> None:
        with path.open(encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    data = json.loads(line)
                except json.JSONDecodeError:
                    continue
                law = LawData(data)
                if law.jurabk:
                    key = law.jurabk.upper()
                    self._laws[key] = law
                    amtabk = law.metadaten.get("amtabk", "").upper()
                    if amtabk and amtabk != key:
                        self._laws[amtabk] = law
                    if law.gesetze_id:
                        self._laws[law.gesetze_id] = law

    @property
    def available_laws(self) -> list[str]:
        """Sorted list of law abbreviations loaded (excludes internal gesetze_id keys)."""
        return sorted(k for k in self._laws if "::" not in k)

    def get_law(self, abbreviation: str) -> Optional[LawData]:
        """Retrieve a LawData object by abbreviation (case-insensitive)."""
        return self._laws.get(abbreviation.upper())

    def query(self, ref_string: str) -> list[QueryResult]:
        """Parse and resolve a reference string.

        Args:
            ref_string: e.g. '§ 312 Abs. 2 BGB' or '§§ 312, 313 BGB'

        Returns:
            List of QueryResult objects, one per paragraph referenced.
        """
        ref = LawReference.parse(ref_string)
        return self._resolve(ref)

    def query_parsed(self, ref: LawReference) -> list[QueryResult]:
        """Resolve an already-parsed LawReference."""
        return self._resolve(ref)

    def _resolve(self, ref: LawReference) -> list[QueryResult]:
        results = []
        if not ref.law:
            return results
        law_data = self._laws.get(ref.law.upper())
        if not law_data:
            return results
        for para_ref in ref.paragraphs:
            for expanded in _expand_multi_target(para_ref):
                result = self._resolve_paragraph(ref, law_data, expanded)
                results.append(result)
        return results

    def _resolve_paragraph(
        self,
        ref: LawReference,
        law_data: LawData,
        para_ref: ParagraphRef,
    ) -> QueryResult:
        para_key = (
            f"art_{para_ref.paragraph.lower()}" if ref.is_art else para_ref.paragraph
        )
        section = law_data.get_section(para_key)

        absatz_data = None
        satz_text = None
        nummer_text = None
        unterbuchst_text_val = None
        abs_num = None
        satz_num = None
        nr_num = None
        buchst_num = None
        unterbuchst_num = None

        for sr in para_ref.sub_refs:
            if sr.level == "Abs" and abs_num is None:
                abs_num = sr.number
            elif sr.level == "Satz" and satz_num is None:
                try:
                    satz_num = int(sr.number)
                except ValueError:
                    pass
            elif sr.level == "Nr" and nr_num is None:
                try:
                    nr_num = int(re.sub(r"[^0-9]", "", sr.number) or "0")
                except ValueError:
                    pass
            elif sr.level == "Buchst":
                letter = sr.number.lower().rstrip(".")
                if buchst_num is None:
                    buchst_num = letter
                elif unterbuchst_num is None:
                    # second Buchst sub_ref is the unterbuchstabe (e.g. aa, bb)
                    unterbuchst_num = letter

        resolved_depth = "section"
        resolution_note = ""

        if not section:
            if para_ref.paragraph:
                resolution_note = (
                    f"Art. {para_ref.paragraph} not found in {ref.law}"
                    if ref.is_art
                    else f"§ {para_ref.paragraph} not found in {ref.law}"
                )
        else:
            resolved_depth = "section"

            if abs_num is not None:
                absatz_data = law_data.get_absatz(para_key, abs_num)
                if absatz_data:
                    resolved_depth = "absatz"
                else:
                    pref = "Art." if ref.is_art else "§"
                    resolution_note = (
                        f"Abs. {abs_num} not found in "
                        f"{pref} {para_ref.paragraph} - resolved to {pref} {para_ref.paragraph}"
                    )
            elif section.get("content"):
                if len(section["content"]) == 1:
                    absatz_data = section["content"][0]
                    resolved_depth = "absatz"
                elif nr_num is not None or buchst_num is not None:
                    # multiple absätze and a sub-ref requested without explicit Abs. -
                    # ambiguous, cannot determine which Absatz is meant
                    pref = "Art." if ref.is_art else "§"
                    sub = (
                        f"Nr. {nr_num}"
                        if nr_num is not None
                        else f"Buchst. {buchst_num}"
                    )
                    resolution_note = (
                        f"{sub} requested in {pref} {para_ref.paragraph} without explicit Absatz - "
                        f"resolved to {pref} {para_ref.paragraph}"
                    )

            if absatz_data and satz_num is not None:
                try:
                    satz_text = law_data.get_satz(para_key, abs_num, int(satz_num))
                    if satz_text:
                        resolved_depth = "satz"
                    else:
                        pref = "Art." if ref.is_art else "§"
                        resolution_note = (
                            f"Satz {satz_num} not found in "
                            f"{pref} {para_ref.paragraph} Abs. {abs_num} - "
                            f"resolved to Abs. {abs_num}"
                        )
                except (ValueError, TypeError):
                    pass

            if absatz_data and nr_num is not None:
                nummer_text = law_data.get_nummer(para_key, abs_num, nr_num)
                if nummer_text is not None:
                    resolved_depth = "nummer"
                    if buchst_num is not None:
                        buchst_text = law_data.get_buchstabe(
                            para_key, abs_num, nr_num, buchst_num
                        )
                        if buchst_text is not None:
                            nummer_text = buchst_text
                            resolved_depth = "buchstabe"
                        else:
                            pref = "Art." if ref.is_art else "§"
                            resolution_note = (
                                f"Buchst. {buchst_num} not found in "
                                f"{pref} {para_ref.paragraph} Abs. {abs_num} Nr. {nr_num} - "
                                f"resolved to Nr. {nr_num}"
                            )
                else:
                    pref = "Art." if ref.is_art else "§"
                    if abs_num is not None:
                        resolution_note = (
                            f"Nr. {nr_num} not found in "
                            f"{pref} {para_ref.paragraph} Abs. {abs_num} - "
                            f"resolved to Abs. {abs_num}"
                        )
                    else:
                        resolution_note = (
                            f"Nr. {nr_num} not found in "
                            f"{pref} {para_ref.paragraph} - "
                            f"resolved to {pref} {para_ref.paragraph}"
                        )

            # unterbuchstabe resolution
            if (
                absatz_data
                and nr_num is not None
                and buchst_num is not None
                and unterbuchst_num is not None
                and resolved_depth != "unterbuchstabe"
            ):
                u_text = law_data.get_unterbuchstabe(
                    para_key, abs_num, nr_num, buchst_num, unterbuchst_num
                )
                if u_text is not None:
                    unterbuchst_text_val = u_text
                    resolved_depth = "unterbuchstabe"
                else:
                    pref = "Art." if ref.is_art else "§"
                    resolution_note = (
                        f"Unterbuchst. {unterbuchst_num} not found in "
                        f"{pref} {para_ref.paragraph} Nr. {nr_num} Buchst. {buchst_num} - "
                        f"resolved to Buchst. {buchst_num}"
                    )

            # fallback: Buchst. requested without Nr. - some laws use letter-prefixed
            # nummer items (a), b)) instead of proper buchstaben inside a nummer.
            # scan nummer items for matching letter prefix.
            if (
                nr_num is None
                and buchst_num is not None
                and resolved_depth != "buchstabe"
            ):
                found_buchst = False
                if absatz_data:
                    label = f"{buchst_num})"
                    for nr in absatz_data.get("nummer", []):
                        text = nr.get("text", "") if isinstance(nr, dict) else str(nr)
                        if text.lstrip().startswith(label) or text.lstrip().startswith(
                            f"{buchst_num} )"
                        ):
                            nummer_text = text
                            resolved_depth = "buchstabe"
                            found_buchst = True
                            break
                if not found_buchst:
                    pref = "Art." if ref.is_art else "§"
                    depth_str = (
                        f"Abs. {abs_num}"
                        if abs_num is not None
                        else f"{pref} {para_ref.paragraph}"
                    )
                    resolution_note = (
                        f"Buchst. {buchst_num} not found in "
                        f"{pref} {para_ref.paragraph} - "
                        f"resolved to {depth_str}"
                    )

        return QueryResult(
            reference=ref,
            law_data=law_data,
            unterbuchst_text=unterbuchst_text_val,
            section=section,
            absatz_data=absatz_data,
            satz_text=satz_text,
            nummer_text=nummer_text,
            resolved_depth=resolved_depth,
            resolution_note=resolution_note,
            resolved_para=para_ref,
        )

    def iter_sections(self, law_abbrev: str) -> Iterator[tuple[str, dict]]:
        """Iterate over all sections of a law as (section_key, section_data) tuples."""
        law_data = self.get_law(law_abbrev)
        if not law_data:
            return
        yield from law_data.sections.items()
