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

from bundesrecht.references import LawReference, ParagraphRef, _expand_multi_target


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
        self.sections: list[dict] | dict[str, dict] = data.get("sections", [])
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

        For multi-DL paragraphs (detected via structured listenende bridge entries),
        uses the in-memory Satz context from _preprocess_satz_context. For simple
        paragraphs, falls back to splitting the absatz lead text.

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

        # Multi-DL paragraph: use precomputed Satz contexts
        contexts = _preprocess_satz_context(abs_data)
        if contexts:
            for ctx in contexts:
                if ctx["satz_num"] == satz:
                    return ctx["text"]
            return None

        # Simple paragraph: split absatz lead text into sentences
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
        self,
        paragraph: str,
        absatz: Optional[Union[int, str]],
        nummer: int,
        nr_range: Optional[tuple] = None,
    ) -> Optional[dict]:
        """Get a specific Nummer item from an Absatz.

        Args:
            paragraph: Paragraph number string.
            absatz: Absatz identifier, or None to use the first content item.
            nummer: 1-based Nummer label to match (matched by text prefix, e.g. "2.").
            nr_range: Optional (start, end) index tuple restricting the search to a
                slice of the nummer list. Used when a Satz qualifier narrows the
                applicable DL group. start is inclusive, end is exclusive (None = to end).
                Supplied by _resolve_paragraph when both Satz and Nr are requested.

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
        if nr_range is not None:
            start, end = nr_range
            start = start if start is not None else 0
            nummern = nummern[start:end]

        return self._match_nummer(nummern, nummer)

    def get_buchstabe(
        self,
        paragraph: str,
        absatz: Optional[Union[int, str]],
        nummer: int,
        buchstabe: str,
        nr_dict: Optional[dict] = None,
    ) -> Optional[str]:
        """Get a specific Buchstabe text from within a Nummer.

        Args:
            paragraph: Paragraph number string.
            absatz: Absatz identifier.
            nummer: 1-based Nummer index.
            buchstabe: Letter label, e.g. 'a', 'b', 'c'.
            nr_dict: Optional pre-resolved Nummer dict. When given (e.g. from a
                Satz-constrained get_nummer call), the Nummer re-lookup is skipped.
                This ensures the buchstabe is resolved within the correct DL group
                when Nummer labels restart across groups.

        Returns:
            The Buchstabe text, or None if not found.
        """
        if nr_dict is None:
            nr_dict = self.get_nummer(paragraph, absatz, nummer)
        if not nr_dict or not isinstance(nr_dict, dict):
            return None
        buchstaben = nr_dict.get("buchstaben", [])
        label = f"{buchstabe})"
        for buch in buchstaben:
            text = buch.get("text", "") if isinstance(buch, dict) else str(buch)
            if text.lstrip().startswith(label) or text.lstrip().startswith(
                f"{buchstabe} )"
            ):
                return text
        return None

    def get_unterbuchstabe(
        self,
        paragraph: str,
        absatz: Optional[Union[int, str]],
        nummer: int,
        buchstabe: str,
        unterbuchstabe: str,
        nr_dict: Optional[dict] = None,
    ) -> Optional[str]:
        """Get a specific Unterbuchstabe text from within a Buchstabe.

        Args:
            paragraph: Paragraph number string.
            absatz: Absatz identifier.
            nummer: 1-based Nummer index.
            buchstabe: Letter label, e.g. 'a', 'b'.
            unterbuchstabe: Double-letter label, e.g. 'aa', 'bb'.
            nr_dict: Optional pre-resolved Nummer dict. When applied (e.g. from a
                Satz-constrained get_nummer call), the Nummer re-lookup is skipped so
                the unterbuchstabe resolves within the correct DL group when labels
                restart.

        Returns:
            The Unterbuchstabe text, or None if not found.
        """
        if nr_dict is None:
            buch_text = self.get_buchstabe(paragraph, absatz, nummer, buchstabe)
            if buch_text is None:
                return None
            nr_dict = self.get_nummer(paragraph, absatz, nummer)
        if not nr_dict or not isinstance(nr_dict, dict):
            return None
        buchstaben = nr_dict.get("buchstaben", [])
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


def _validate_listenende(listenende: object, context: str = "") -> list:
    """Validate and return a structured listenende list.

    Args:
        listenende: The value from a JSONL content block's "listenende" key.
        context: Optional label for error messages.

    Returns:
        The listenende list, or [] if absent/None.

    Raises:
        ValueError: If the old string schema is detected.
        TypeError: If an entry is not a dict or has a wrong field type.
        KeyError: If an entry is missing a required key.
    """
    if isinstance(listenende, str):
        ctx_str = f" (at {context})" if context else ""
        raise ValueError(
            f"Old string listenende schema detected{ctx_str}. "
            "The corpus uses the old schema and must be regenerated."
        )
    if not listenende:
        return []
    entries = list(listenende)
    ctx_str = f" (at {context})" if context else ""
    valid_levels = {"absatz", "nummer", "buchstabe", "unterbuchstabe"}
    for i, entry in enumerate(entries):
        if not isinstance(entry, dict):
            raise TypeError(
                f"listenende[{i}] must be a dict, got {type(entry).__name__}{ctx_str}"
            )
        for required in ("level", "start", "end", "text"):
            if required not in entry:
                raise KeyError(
                    f"listenende[{i}] missing required key '{required}'{ctx_str}"
                )
        if entry["level"] not in valid_levels:
            raise ValueError(
                f"listenende[{i}]['level'] must be one of {valid_levels}, "
                f"got {entry['level']!r}{ctx_str}"
            )
        if not isinstance(entry["text"], str):
            raise TypeError(
                f"listenende[{i}]['text'] must be str, "
                f"got {type(entry['text']).__name__}{ctx_str}"
            )
        start = entry["start"]
        if start is not None and not isinstance(start, int):
            raise TypeError(
                f"listenende[{i}]['start'] must be int or None, "
                f"got {type(start).__name__}{ctx_str}"
            )
        end = entry["end"]
        if end is not None and not isinstance(end, int):
            raise TypeError(
                f"listenende[{i}]['end'] must be int or None, "
                f"got {type(end).__name__}{ctx_str}"
            )
    return entries


def _preprocess_satz_context(absatz_data: dict) -> list[dict]:
    """Build in-memory Satz context for paragraphs with multiple top-level DL groups.

    Detects multi-DL structure by looking for absatz-level listenende entries
    with a non-null end index (these connect two DL groups). For simple paragraphs
    (single DL or no DL), returns an empty list so callers use existing behavior.

    Args:
        absatz_data: One content block dict from the JSONL.

    Returns:
        List of Satz context dicts, each with:
          satz_num : 1-based Satz number
          text     : sentence text (absatz lead or a sentence from a bridge tail)
          nr_start : inclusive start index into nummer list, or None
          nr_end   : exclusive end index into nummer list, or None
        Empty list when no multi-DL bridge entries exist.

    Example for HWG § 11 Abs. 1 (first DL has 15 items, second has 2):
        [{satz_num:1, text:"Ausserhalb...", nr_start:0, nr_end:15},
         {satz_num:2, text:"Fur Medizinprodukte...", nr_start:None, nr_end:None},
         {satz_num:3, text:"Ferner darf...", nr_start:15, nr_end:None}]
    """
    listenende = _validate_listenende(absatz_data.get("listenende", []))
    absatz_entries = [
        e for e in listenende if isinstance(e, dict) and e.get("level") == "absatz"
    ]
    bridge_entries = [e for e in absatz_entries if e.get("end") is not None]

    if not bridge_entries:
        return []

    absatz_text = re.sub(r"^\(\d+\w*\)\s*", "", absatz_data.get("absatz", ""))
    contexts: list[dict] = []
    satz_num = 1

    # Satz 1: the absatz lead text governs the first DL group
    first_bridge = bridge_entries[0]
    contexts.append(
        {
            "satz_num": satz_num,
            "text": absatz_text,
            "nr_start": 0,
            "nr_end": first_bridge["end"],
        }
    )
    satz_num += 1

    for b_idx, bridge in enumerate(bridge_entries):
        tail_text = (bridge.get("text") or "").strip()
        sentences = _split_sentences(tail_text) if tail_text else []

        # Determine the nr range for the DL group following this bridge
        if b_idx + 1 < len(bridge_entries):
            next_nr_end = bridge_entries[b_idx + 1]["end"]
        else:
            next_nr_end = None
        nr_range_start = bridge["end"]

        if not sentences:
            continue

        # All sentences except the last are standalone Sätze (no DL governed)
        for sentence in sentences[:-1]:
            contexts.append(
                {
                    "satz_num": satz_num,
                    "text": sentence,
                    "nr_start": None,
                    "nr_end": None,
                }
            )
            satz_num += 1

        # Last sentence: only governs the following DL if it ends with a colon.
        # A non-colon ending means it is also standalone and the following DL has
        # no explicit intro Satz text.  This prevents over-attaching DL groups in
        # paragraphs where the tail does not grammatically introduce a list.
        last_sentence = sentences[-1]
        if last_sentence.rstrip().endswith(":"):
            contexts.append(
                {
                    "satz_num": satz_num,
                    "text": last_sentence,
                    "nr_start": nr_range_start,
                    "nr_end": next_nr_end,
                }
            )
            satz_num += 1
        else:
            # No colon: last sentence is standalone too. The following DL group
            # has no named Satz intro and is only reachable via Nr without Satz.
            contexts.append(
                {
                    "satz_num": satz_num,
                    "text": last_sentence,
                    "nr_start": None,
                    "nr_end": None,
                }
            )
            satz_num += 1

    return contexts


def _collect_buchstabe_listenende(
    absatz_data: dict, reference: "LawReference"
) -> list[str]:
    """Collect listenende texts from the resolved buchstabe dict.

    Used by QueryResult.full_text() at buchstabe depth to include the
    buchstabe's closing clause in the assembled text.

    Args:
        absatz_data: Content block from the JSONL.
        reference: The parsed law reference (supplies nr_num, buchst_num, satz_num).

    Returns:
        List of listenende text strings for the resolved buchstabe, or [].
    """
    if absatz_data is None or not reference.paragraphs:
        return []
    nr_ref = buchst_ref = satz_ref = None
    for sr in reference.paragraphs[0].sub_refs:
        if sr.level == "Nr" and nr_ref is None:
            try:
                nr_ref = int(sr.number)
            except ValueError:
                pass
        elif sr.level == "Buchst" and buchst_ref is None:
            buchst_ref = sr.number.lower().rstrip(".")
        elif sr.level == "Satz" and satz_ref is None:
            try:
                satz_ref = int(sr.number)
            except ValueError:
                pass
    if nr_ref is None or buchst_ref is None:
        return []
    nummern = absatz_data.get("nummer", [])
    if satz_ref is not None:
        for ctx in _preprocess_satz_context(absatz_data):
            if ctx["satz_num"] == satz_ref:
                start = ctx["nr_start"] if ctx["nr_start"] is not None else 0
                nummern = nummern[start : ctx["nr_end"]]
                break
    nr_dict = LawData._match_nummer(nummern, nr_ref)
    if not isinstance(nr_dict, dict):
        return []
    label = f"{buchst_ref})"
    for buch in nr_dict.get("buchstaben", []):
        if not isinstance(buch, dict):
            continue
        btext = buch.get("text", "").lstrip()
        if btext.startswith(label) or btext.startswith(f"{buchst_ref} )"):
            return [
                le.get("text", "").strip()
                for le in buch.get("listenende", [])
                if isinstance(le, dict) and le.get("text", "").strip()
            ]
    return []


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

    Inserts absatz-level listenende entries at their correct positions between
    Nummern so reading order is preserved for multi-DL paragraphs. Nested
    listenende entries (at nummer/buchstabe level) are included inline after
    their parent item.

    Raises:
        ValueError: If listenende uses the old string schema. The corpus must
            be regenerated.
    """
    parts = []
    lead = c.get("absatz", "")
    if lead:
        parts.append(lead)

    listenende = _validate_listenende(c.get("listenende", []), "absatz")

    # Build positional insertion map: insert after nummer[idx] → [text, ...]
    tail_inserts: dict[int, list[str]] = {}
    for entry in listenende:
        if not isinstance(entry, dict):
            continue
        if entry.get("level") != "absatz":
            continue
        text = (entry.get("text") or "").strip()
        if not text:
            continue
        start = entry.get("start")
        insert_after = start if start is not None else -1
        tail_inserts.setdefault(insert_after, []).append(text)

    # Pre-list entries (start=None edge case)
    for txt in tail_inserts.get(-1, []):
        parts.append(txt)

    for idx, nr in enumerate(c.get("nummer", [])):
        nr_text = nr.get("text", "") if isinstance(nr, dict) else str(nr)
        if nr_text:
            parts.append(nr_text)
        if isinstance(nr, dict):
            for buch in nr.get("buchstaben", []):
                buch_text = (
                    buch.get("text", "") if isinstance(buch, dict) else str(buch)
                )
                if buch_text:
                    parts.append(buch_text)
                if isinstance(buch, dict):
                    for ubuch in buch.get("unterbuchstaben", []):
                        u_text = (
                            ubuch.get("text", "")
                            if isinstance(ubuch, dict)
                            else str(ubuch)
                        )
                        if u_text:
                            parts.append(u_text)
                    for le in buch.get("listenende", []):
                        if isinstance(le, dict):
                            le_text = (le.get("text") or "").strip()
                            if le_text:
                                parts.append(le_text)
            for le in nr.get("listenende", []):
                if isinstance(le, dict):
                    le_text = (le.get("text") or "").strip()
                    if le_text:
                        parts.append(le_text)

        # Insert absatz-level listenende entry after this nummer item
        for txt in tail_inserts.get(idx, []):
            parts.append(txt)

    return " ".join(p for p in parts if p)


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

        Branches by resolved_depth so that a Satz+Nr query at nummer depth
        returns the Nummer text, not the broader Satz intro text.
        """
        if self.resolved_depth == "satz" and self.satz_text:
            return self.satz_text
        if self.unterbuchst_text:
            return _strip_leaf_prefix(self.unterbuchst_text, "buchstabe")
        if self.nummer_text:
            if isinstance(self.nummer_text, str):
                leaf_text = _strip_leaf_prefix(self.nummer_text, "buchstabe")
                if self.resolved_depth == "buchstabe":
                    buch_le = _collect_buchstabe_listenende(
                        self.absatz_data, self.reference
                    )
                    if buch_le:
                        leaf_text = " ".join([leaf_text] + buch_le)
                return leaf_text
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
                    if isinstance(buch, dict):
                        for ubuch in buch.get("unterbuchstaben", []):
                            u_text = (
                                ubuch.get("text", "")
                                if isinstance(ubuch, dict)
                                else str(ubuch)
                            )
                            if u_text:
                                parts.append(u_text)
                        for le in buch.get("listenende", []):
                            if isinstance(le, dict):
                                le_text = (le.get("text") or "").strip()
                                if le_text:
                                    parts.append(le_text)
                for le in self.nummer_text.get("listenende", []):
                    if isinstance(le, dict):
                        le_text = (le.get("text") or "").strip()
                        if le_text:
                            parts.append(le_text)
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
            if self.satz_text:
                satz_part = _strip_leaf_prefix(
                    self.satz_text.rstrip(":").strip(), "satz"
                )
                if satz_part and satz_part not in parts:
                    parts.append(satz_part)

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
                    satz_ref_num = None
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
                        elif sr.level == "Satz":
                            try:
                                satz_ref_num = int(sr.number)
                            except ValueError:
                                pass
                    if nr_ref is not None:
                        nummern = self.absatz_data.get("nummer", [])
                        # Restrict to the Satz's nr range so restarted labels resolve correctly
                        if satz_ref_num is not None:
                            satz_contexts = _preprocess_satz_context(self.absatz_data)
                            for ctx in satz_contexts:
                                if ctx["satz_num"] == satz_ref_num:
                                    start = (
                                        ctx["nr_start"]
                                        if ctx["nr_start"] is not None
                                        else 0
                                    )
                                    end = ctx["nr_end"]
                                    nummern = nummern[start:end]
                                    break
                        nr_dict = LawData._match_nummer(nummern, nr_ref)
                        if nr_dict is not None and isinstance(nr_dict, dict):
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
        pending_aliases: list[tuple[str, LawData]] = []
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
                        pending_aliases.append((amtabk, law))
                    if law.gesetze_id:
                        self._laws[law.gesetze_id] = law
        for alias, law in pending_aliases:
            self._laws.setdefault(alias, law)

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
        satz_context_blocks_subrefs = False

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
                # Precompute once, used by both Satz resolution and Nr range constraint.
                satz_contexts = _preprocess_satz_context(absatz_data)
                satz_found = False
                try:
                    satz_text = law_data.get_satz(para_key, abs_num, int(satz_num))
                    if satz_text:
                        resolved_depth = "satz"
                        satz_found = True
                    else:
                        pref = "Art." if ref.is_art else "§"
                        resolution_note = (
                            f"Satz {satz_num} not found in "
                            f"{pref} {para_ref.paragraph} Abs. {abs_num} - "
                            f"resolved to Abs. {abs_num}"
                        )
                except (ValueError, TypeError):
                    satz_contexts = []
            else:
                satz_contexts = []
                satz_found = False

            if absatz_data and nr_num is not None:
                nr_range = None
                skip_nr = False
                nr_dict_for_sub = None  # preserved for unterbuchstabe lookup below

                if satz_num is not None and satz_contexts:
                    # Multi-DL paragraph: Satz qualifier determines the allowed Nr range.
                    ctx_match = next(
                        (c for c in satz_contexts if c["satz_num"] == satz_num), None
                    )
                    if ctx_match is None:
                        # Satz not found in multi-DL context: unconstrained Nr would
                        # be misleading - do not resolve Nr.
                        skip_nr = True
                        satz_context_blocks_subrefs = True
                    elif ctx_match["nr_start"] is None and ctx_match["nr_end"] is None:
                        # Standalone Satz: no DL group governed, Nr not applicable.
                        skip_nr = True
                        satz_context_blocks_subrefs = True
                        pref = "Art." if ref.is_art else "§"
                        resolution_note = (
                            f"Satz {satz_num} is standalone (no Nummer list) in "
                            f"{pref} {para_ref.paragraph} Abs. {abs_num}"
                        )
                    else:
                        nr_range = (ctx_match["nr_start"], ctx_match["nr_end"])

                if not skip_nr:
                    nummer_text = law_data.get_nummer(
                        para_key, abs_num, nr_num, nr_range=nr_range
                    )
                    if isinstance(nummer_text, dict):
                        nr_dict_for_sub = (
                            nummer_text  # save before potential replacement
                        )
                    if nummer_text is not None:
                        resolved_depth = "nummer"
                        if buchst_num is not None:
                            # Pass the already-resolved Nummer dict so get_buchstabe
                            # does not redo the lookup and accidentally pick from the
                            # wrong DL group when labels restart.
                            buchst_text = law_data.get_buchstabe(
                                para_key,
                                abs_num,
                                nr_num,
                                buchst_num,
                                nr_dict=(
                                    nummer_text
                                    if isinstance(nummer_text, dict)
                                    else None
                                ),
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
                        if satz_num is not None and satz_found:
                            # Nr not found under a resolved Satz - report at Satz depth.
                            resolution_note = (
                                f"Nr. {nr_num} not found in "
                                f"{pref} {para_ref.paragraph} Abs. {abs_num} Satz {satz_num} - "
                                f"resolved to Satz {satz_num}"
                            )
                        elif abs_num is not None:
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
                and not satz_context_blocks_subrefs
            ):
                u_text = law_data.get_unterbuchstabe(
                    para_key,
                    abs_num,
                    nr_num,
                    buchst_num,
                    unterbuchst_num,
                    nr_dict=nr_dict_for_sub,
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
