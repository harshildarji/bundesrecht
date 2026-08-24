"""
bundesrecht._corpus - locate, download, and validate the Bundesrecht corpus.

The package pins one Hugging Face dataset commit. Default construction loads
the matching cached corpus or downloads that exact file into a commit-keyed
cache. Explicit local paths are still supported for offline or reproducible
work, but they must match the corpus structure expected by this package.
"""

from __future__ import annotations

import json
import logging
import os
import re
import tempfile
import urllib.error
import urllib.request
from pathlib import Path
from typing import Optional, Union

logger = logging.getLogger(__name__)

HF_DATASET_REPO = "harshildarji/bundesrecht"
DATA_FILENAME = "gesetze.jsonl"

DEFAULT_DATA_COMMIT = "fa92f69787f31620f37ce10409feae9034b5a3a5"
_COMMIT_HASH_RE = re.compile(r"^[0-9a-f]{40}$")


class CorpusValidationError(ValueError):
    """Raised when a corpus file does not match the expected JSONL shape."""


class CorpusDownloadError(RuntimeError):
    """Raised when the package-managed corpus cannot be downloaded."""


def get_data_url() -> str:
    """Build the pinned Hugging Face URL for the package-managed corpus."""
    return (
        "https://huggingface.co/datasets/"
        f"{HF_DATASET_REPO}/resolve/{DEFAULT_DATA_COMMIT}/{DATA_FILENAME}"
    )


def get_cache_root() -> Path:
    """Return the directory where package-managed corpora are cached."""
    custom = os.environ.get("BUNDESRECHT_CACHE_DIR")
    if custom:
        return Path(custom).expanduser()

    xdg_cache_home = os.environ.get("XDG_CACHE_HOME")
    if xdg_cache_home:
        return Path(xdg_cache_home).expanduser() / "bundesrecht"

    return Path.home() / ".cache" / "bundesrecht"


def get_cached_corpus_path() -> Path:
    """Return the cache path for the corpus commit pinned by this package."""
    return get_cache_root() / DEFAULT_DATA_COMMIT / DATA_FILENAME


def _context(base: str, part: str) -> str:
    return f"{base}.{part}" if base else part


def _require_dict(value: object, context: str) -> dict:
    if not isinstance(value, dict):
        raise CorpusValidationError(
            f"{context} must be an object, got {type(value).__name__}"
        )
    return value


def _require_list(value: object, context: str) -> list:
    if not isinstance(value, list):
        raise CorpusValidationError(
            f"{context} must be a list, got {type(value).__name__}"
        )
    return value


def _require_str(value: object, context: str) -> str:
    if not isinstance(value, str):
        raise CorpusValidationError(
            f"{context} must be a string, got {type(value).__name__}"
        )
    return value


def _require_optional_list(record: dict, key: str, context: str) -> None:
    if key in record and record[key] is not None:
        _require_list(record[key], _context(context, key))


def _validate_listenende(value: object, context: str) -> None:
    entries = _require_list(value, context)
    for i, entry in enumerate(entries):
        entry_context = f"{context}[{i}]"
        data = _require_dict(entry, entry_context)
        for key in ("level", "start", "end", "text"):
            if key not in data:
                raise CorpusValidationError(f"{entry_context} is missing {key!r}")
        _require_str(data["level"], _context(entry_context, "level"))
        _require_str(data["text"], _context(entry_context, "text"))
        start = data["start"]
        if start is not None and not isinstance(start, int):
            raise CorpusValidationError(
                f"{_context(entry_context, 'start')} must be an integer or null"
            )
        end = data["end"]
        if end is not None and not isinstance(end, int):
            raise CorpusValidationError(
                f"{_context(entry_context, 'end')} must be an integer or null"
            )


def _validate_text_item(value: object, context: str) -> None:
    if isinstance(value, str):
        return

    data = _require_dict(value, context)
    if "text" not in data:
        raise CorpusValidationError(f"{context} is missing 'text'")
    _require_str(data["text"], _context(context, "text"))

    if "listenende" in data:
        _validate_listenende(data["listenende"], _context(context, "listenende"))

    if "unterbuchstaben" in data:
        unterbuchstaben = _require_list(
            data["unterbuchstaben"], _context(context, "unterbuchstaben")
        )
        for i, item in enumerate(unterbuchstaben):
            _validate_text_item(item, f"{context}.unterbuchstaben[{i}]")


def _validate_nummer(value: object, context: str) -> None:
    data = _require_dict(value, context)
    if "text" not in data:
        raise CorpusValidationError(f"{context} is missing 'text'")
    _require_str(data["text"], _context(context, "text"))

    if "buchstaben" in data:
        buchstaben = _require_list(data["buchstaben"], _context(context, "buchstaben"))
        for i, item in enumerate(buchstaben):
            _validate_text_item(item, f"{context}.buchstaben[{i}]")

    if "listenende" in data:
        _validate_listenende(data["listenende"], _context(context, "listenende"))


def _validate_content_block(value: object, context: str) -> None:
    data = _require_dict(value, context)
    for key in ("absatz", "nummer", "listenende"):
        if key not in data:
            raise CorpusValidationError(f"{context} is missing {key!r}")

    _require_str(data["absatz"], _context(context, "absatz"))
    nummern = _require_list(data["nummer"], _context(context, "nummer"))
    _validate_listenende(data["listenende"], _context(context, "listenende"))

    for i, nummer in enumerate(nummern):
        _validate_nummer(nummer, f"{context}.nummer[{i}]")


def _validate_section(value: object, context: str) -> None:
    data = _require_dict(value, context)
    if "paragraf" not in data:
        raise CorpusValidationError(f"{context} is missing 'paragraf'")
    if "content" not in data:
        raise CorpusValidationError(f"{context} is missing 'content'")

    _require_str(data["paragraf"], _context(context, "paragraf"))
    if "titel" in data:
        _require_str(data["titel"], _context(context, "titel"))
    _require_optional_list(data, "fussnoten", context)
    _require_optional_list(data, "gliederung", context)

    content = _require_list(data["content"], _context(context, "content"))
    for i, block in enumerate(content):
        _validate_content_block(block, f"{context}.content[{i}]")


def validate_corpus_shape(path: Union[str, Path]) -> None:
    """Validate the JSONL shape expected by this version of bundesrecht.

    Args:
        path: Corpus JSONL path to validate.

    Raises:
        CorpusValidationError: If the file is empty, malformed JSONL, or does
            not match the structural shape consumed by the resolver.
    """
    corpus_path = Path(path)
    rows_seen = 0

    try:
        with corpus_path.open("r", encoding="utf-8") as f:
            for line_number, line in enumerate(f, start=1):
                line = line.strip()
                if not line:
                    continue

                try:
                    row = json.loads(line)
                except json.JSONDecodeError as exc:
                    raise CorpusValidationError(
                        f"line {line_number} is not valid JSON"
                    ) from exc

                context = f"line {line_number}"
                data = _require_dict(row, context)
                for key in ("gesetze_id", "jurabk", "metadaten", "sections"):
                    if key not in data:
                        raise CorpusValidationError(f"{context} is missing {key!r}")

                _require_str(data["gesetze_id"], _context(context, "gesetze_id"))
                _require_str(data["jurabk"], _context(context, "jurabk"))
                _require_dict(data["metadaten"], _context(context, "metadaten"))
                if "fussnoten" in data:
                    _require_list(data["fussnoten"], _context(context, "fussnoten"))
                if "quelle" in data:
                    _require_dict(data["quelle"], _context(context, "quelle"))

                sections = _require_list(
                    data["sections"], _context(context, "sections")
                )
                for i, section in enumerate(sections):
                    _validate_section(section, f"{context}.sections[{i}]")

                rows_seen += 1
    except OSError as exc:
        raise CorpusValidationError(
            f"could not read corpus file: {corpus_path}"
        ) from exc

    if rows_seen == 0:
        raise CorpusValidationError("corpus file is empty")


def _validate_data_commit() -> None:
    if not _COMMIT_HASH_RE.fullmatch(DEFAULT_DATA_COMMIT):
        raise RuntimeError(
            "The package-managed Bundesrecht corpus commit must be a full "
            "40-character Hugging Face commit hash. Pass local_path to "
            "Bundesrecht, or install a release with a pinned corpus commit."
        )


def download_default_corpus() -> Path:
    """Download and cache the corpus pinned by this package version."""
    _validate_data_commit()

    target = get_cached_corpus_path()
    target.parent.mkdir(parents=True, exist_ok=True)

    logger.info(
        "No compatible cached Bundesrecht corpus found for this package version. "
        "Downloading gesetze.jsonl from Hugging Face."
    )

    with tempfile.NamedTemporaryFile(
        mode="wb",
        delete=False,
        dir=str(target.parent),
        prefix="gesetze.",
        suffix=".tmp",
    ) as tmp:
        tmp_path = Path(tmp.name)

    try:
        data_url = get_data_url()
        with urllib.request.urlopen(data_url, timeout=120) as response:
            with tmp_path.open("wb") as f:
                while True:
                    chunk = response.read(1024 * 1024)
                    if not chunk:
                        break
                    f.write(chunk)

        validate_corpus_shape(tmp_path)
        tmp_path.replace(target)
        return target
    except (OSError, TimeoutError, urllib.error.URLError) as exc:
        tmp_path.unlink(missing_ok=True)
        raise CorpusDownloadError(
            "Could not download the package-managed Bundesrecht corpus. "
            "Check your network connection, or pass local_path to Bundesrecht "
            "with a compatible gesetze.jsonl file."
        ) from exc
    except Exception:
        tmp_path.unlink(missing_ok=True)
        raise


def get_default_corpus_path() -> Path:
    """Return a compatible package-managed corpus path."""
    path = get_cached_corpus_path()

    if path.exists():
        try:
            validate_corpus_shape(path)
            return path
        except CorpusValidationError:
            logger.info(
                "Cached Bundesrecht corpus is not compatible with this package "
                "version. Downloading a compatible copy."
            )
            path.unlink(missing_ok=True)

    return download_default_corpus()


def resolve_corpus_path(local_path: Optional[Union[str, Path]] = None) -> Path:
    """Resolve and validate the corpus path for Bundesrecht.

    Args:
        local_path: Optional explicit JSONL file. When omitted, the
            package-managed cached corpus is used or downloaded.

    Returns:
        Local path to a compatible corpus JSONL file.

    Raises:
        FileNotFoundError: If an explicit local path does not exist.
        ValueError: If an explicit local path does not look compatible.
    """
    if local_path is None:
        return get_default_corpus_path()

    path = Path(local_path).expanduser()
    if not path.exists():
        raise FileNotFoundError(f"Bundesrecht corpus file not found: {path}")

    try:
        validate_corpus_shape(path)
    except CorpusValidationError as exc:
        raise ValueError(
            "The provided JSONL file does not look compatible with this version "
            "of bundesrecht. Please provide a compatible file, or simply call "
            "Bundesrecht() instead to use the package-managed corpus."
        ) from exc

    return path
