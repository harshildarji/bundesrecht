"""
bundesrecht - structured parsing, normalisation, and resolution of German federal law references.

    from bundesrecht import Bundesrecht

    lib = Bundesrecht("path/to/gesetze.jsonl")

    results = lib.query("§ 2 Abs. 1 Nr. 1, Nr. 7, Abs. 2 UrhG")
    for r in results:
        print(r.normkette())

    results = lib.query_canonical("§ 2 Abs. 1 Nr. 1 UrhG")

    from bundesrecht import normalise
    refs = normalise("§ 312 i.V.m. § 355 BGB")
    # → ["§ 312 BGB", "§ 355 BGB"]

Public API:
    Bundesrecht      - main entry point (load once, query many times)
    QueryResult      - resolution result with full_text(), normkette()
    normalise()      - raw string → list of canonical strings
    parse_reference() - raw string → LawReference (parsed structure)
"""

from pathlib import Path
from typing import Optional, Union

from bundesrecht._corpus import resolve_corpus_path
from bundesrecht.lookup import LawData, LawLibrary, QueryResult
from bundesrecht.normaliser import normalise
from bundesrecht.references import (
    LawReference,
    ParagraphRef,
    SubReference,
    parse_reference,
)


class Bundesrecht:
    """Main entry point for bundesrecht.

    Loads a compatible JSONL corpus once and exposes query methods.

    Args:
        local_path: Optional path to gesetze.jsonl. If omitted, bundesrecht
            uses the package-managed corpus pinned to this package version,
            downloading it into a local cache if necessary.

    Examples:
        >>> lib = Bundesrecht()
        >>> lib = Bundesrecht("data/gesetze.jsonl")
        >>> results = lib.query("§ 2 Abs. 1 Nr. 1, Nr. 7, Abs. 2 UrhG")
        >>> results = lib.query_canonical("§ 2 Abs. 1 Nr. 1 UrhG")
        >>> lib.normalise("§ 312 iVm § 355 BGB")
        ['§ 312 BGB', '§ 355 BGB']
        >>> lib.normalise("§ 312 ff. BGB", ff_expansion=3)
        ['§ 312 BGB', '§ 313 BGB', '§ 314 BGB']
    """

    def __init__(
        self,
        local_path: Optional[Union[str, Path]] = None,
        *,
        jsonl_path: Optional[Union[str, Path]] = None,
    ):
        if local_path is not None and jsonl_path is not None:
            raise TypeError("Pass either local_path or jsonl_path, not both")
        # Keep jsonl_path as a compatibility alias for the old constructor API.
        if jsonl_path is not None:
            local_path = jsonl_path
        jsonl_path = resolve_corpus_path(local_path)
        self._library = LawLibrary(str(jsonl_path))

    # normalisation (no lookup)
    def normalise(self, raw: str, ff_expansion: int | None = None) -> list[str]:
        """Normalise a raw citation string → list of canonical strings.

        Args:
            raw: Any German legal citation string.
            ff_expansion: Number of paragraphs to expand ff. into. If None (default),
                ff. is preserved as-is. f. always expands to exactly 2.
        """
        return normalise(raw, ff_expansion=ff_expansion)

    # resolution
    def query(self, raw: str, ff_expansion: int | None = None) -> list[QueryResult]:
        """Normalise then resolve a raw citation string.

        Args:
            raw: Any German legal citation, e.g. '§ 2 Abs. 1 Nr. 1, Nr. 7, Abs. 2 UrhG'
            ff_expansion: Number of paragraphs to expand ff. into. If None (default),
                ff. is preserved as-is. f. always expands to exactly 2.

        Returns:
            One QueryResult per resolved canonical reference, preserving
            the order of the normalised canonical strings.
        """
        canonical_refs = normalise(raw, ff_expansion=ff_expansion)
        results: list[QueryResult] = []
        for canon in canonical_refs:
            results.extend(self._library.query(canon))
        return results

    def query_canonical(self, canonical: str) -> list[QueryResult]:
        """Resolve an already-canonical reference string directly.

        Skips normalisation - use when you already have a clean ref.
        """
        return self._library.query(canonical)

    # data access
    def get_law(self, abbreviation: str) -> Optional[LawData]:
        """Retrieve a LawData object by abbreviation (case-insensitive)."""
        return self._library.get_law(abbreviation)

    @property
    def available_laws(self) -> list[str]:
        """Sorted list of all law abbreviations loaded."""
        return self._library.available_laws

    @property
    def law_count(self) -> int:
        """Number of distinct laws loaded (deduplicated)."""
        return len({l.gesetze_id for l in self._library._laws.values() if l.gesetze_id})

    def __repr__(self) -> str:
        return f"Bundesrecht({self.law_count} laws loaded)"


__all__ = [
    "Bundesrecht",
    "QueryResult",
    "LawData",
    "LawReference",
    "ParagraphRef",
    "SubReference",
    "normalise",
    "parse_reference",
]

__version__ = "0.1.0"
