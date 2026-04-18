# bundesrecht

Python package for parsing, normalising, and resolving German federal law references.

Zero dependencies. Pure Python 3.10+.


## Installation

```bash
pip install bundesrecht
```

## Quick start

```python
from bundesrecht import Bundesrecht

lib = Bundesrecht('data/gesetze.jsonl')

results = lib.query('§ 242 BGB')
for r in results:
    print(r.titel())
    print(r.full_text())
```


## The Bundesrecht class

The main entry point. Load once, query as many times as you like.

```python
lib = Bundesrecht('data/gesetze.jsonl')
```

### lib.query(raw)

Normalises a raw citation string and resolves each canonical reference.
Returns `list[QueryResult]`.

```python
# Simple paragraph
results = lib.query('§ 242 BGB')

# Paragraph + Absatz
results = lib.query('§ 433 Abs. 1 BGB')

# Paragraph + Absatz + Nummer
results = lib.query('§ 2 Abs. 1 Nr. 1 UrhG')

# Multi-target: expands into 3 separate results
results = lib.query('§ 2 Abs. 1 Nr. 1, Nr. 7, Abs. 2 UrhG')
# → QueryResult for § 2 Abs. 1 Nr. 1 UrhG
# → QueryResult for § 2 Abs. 1 Nr. 7 UrhG
# → QueryResult for § 2 Abs. 2 UrhG

# i.V.m.: expands into 2 separate results
results = lib.query('§ 312 i.V.m. § 355 BGB')
# → QueryResult for § 312 BGB
# → QueryResult for § 355 BGB

# §§ range: expands into one result per paragraph
results = lib.query('§§ 12-15 BGB')
# → § 12, § 13, § 14, § 15

# §§ with separate laws per chunk
results = lib.query('§§ 46 Abs. 2 ArbGG, 91 Abs. 1 ZPO')
# → § 46 Abs. 2 ArbGG
# → § 91 Abs. 1 ZPO

# Satz reference
results = lib.query('§ 1 Satz 2 BGB')

# Buchstabe reference
results = lib.query('§ 2 Abs. 1 Nr. 1 Buchst. a UrhG')
```

### lib.query_canonical(canonical)

Skips normalisation and resolves a pre-cleaned reference directly.
Use this when you have already normalised the string yourself.

```python
results = lib.query_canonical('§ 2 Abs. 1 Nr. 1 UrhG')
```

### lib.normalise(raw)

Normalises a citation string without resolving it.
Returns `list[str]` of canonical strings.

```python
lib.normalise('§ 312 i.V.m. § 355 BGB')
# → ['§ 312 BGB', '§ 355 BGB']

lib.normalise('§§ 12-15 BGB')
# → ['§ 12 BGB', '§ 13 BGB', '§ 14 BGB', '§ 15 BGB']

lib.normalise('§ 2 Abs. 1 Nr. 1, Nr. 7, Abs. 2 UrhG')
# → ['§ 2 Abs. 1 Nr. 1 UrhG', '§ 2 Abs. 1 Nr. 7 UrhG', '§ 2 Abs. 2 UrhG']
```

### lib.get_law(abbreviation)

Returns a `LawData` object for a law by its abbreviation. Case-insensitive.
Returns `None` if not found.

```python
bgb = lib.get_law('BGB')
bgb = lib.get_law('bgb')   # same result
```

### lib.available_laws

Sorted list of all law abbreviations currently loaded.

```python
lib.available_laws[:5]
# → ['AABG', 'AAG', 'AAGN', 'AAV', 'AbfAEV']
```

### lib.law_count

Number of distinct laws loaded.

```python
lib.law_count   # → 6867
```


## QueryResult

Returned by `query()` and `query_canonical()`. One object per resolved reference.

```python
r = lib.query('§ 433 Abs. 1 BGB')[0]
```

### r.full_text()

Returns the most specific statutory text found, in this priority order:
Satz → Nummer → Absatz → full section content.

```python
r.full_text()
# → 'Durch den Kaufvertrag wird der Verkäufer einer Sache verpflichtet...'
```

### r.titel()

Returns the section heading (Überschrift), if one exists.

```python
r.titel()
# → 'Vertragstypische Pflichten beim Kaufvertrag'
```

### r.resolved_depth

String indicating how deeply the reference was resolved.
One of: `'buchstabe'`, `'nummer'`, `'absatz'`, `'section'`.

```python
r.resolved_depth   # → 'absatz'  (Absatz found, but no Nummer requested)
```

### r.resolution_note

Human-readable explanation when the requested depth was not fully resolved.
Empty string when resolution was complete.

```python
r.resolution_note
# → ''  (fully resolved)
# → 'Buchstabe c not found in Nr. 1'  (partial resolution)
```

### r.reference

The parsed `LawReference` object for this result.

```python
r.reference.law           # → 'BGB'
r.reference.paragraphs    # → [ParagraphRef(paragraph='433', ...)]
str(r.reference)          # → '§ 433 Abs. 1 BGB'
```

### r.law_data

The `LawData` object for the parent statute.

```python
r.law_data.jurabk                            # → 'BGB'
r.law_data.gesetze_id                        # → 'BJNR001950896'
r.law_data.metadaten.get('langue')           # → 'Bürgerliches Gesetzbuch'
r.law_data.metadaten.get('ausfertigung-datum')  # → '1896-08-18'
len(r.law_data.sections)                     # → 2541
```

### r.section

Raw dict of the resolved section, or `None` if not found.

```python
r.section.get('titel')    # same as r.titel()
r.section.get('content')  # list of Absatz dicts
```

### r.resolved_para

The specific `ParagraphRef` that was matched (after multi-target expansion).

```python
str(r.resolved_para)   # → '433 Abs. 1'
```


## LawData

Returned by `lib.get_law()` and available as `result.law_data`.

```python
bgb = lib.get_law('BGB')
```

### Attributes

```python
bgb.jurabk        # → 'BGB'          abbreviation
bgb.gesetze_id    # → 'BJNR001950896'  internal corpus ID
bgb.metadaten     # → dict            full metadata
bgb.sections      # → dict            all sections keyed by paragraph string
bgb.fussnoten     # → list            footnotes at law level
bgb.quelle        # → dict            source metadata
```

### Useful metadaten keys

```python
bgb.metadaten.get('langue')              # → 'Bürgerliches Gesetzbuch'
bgb.metadaten.get('kurzue')             # short title if present
bgb.metadaten.get('ausfertigung-datum') # → '1896-08-18'
bgb.metadaten.get('gliederungsnummer')  # → '400-2'  subject classification
bgb.metadaten.get('periodikum')         # → 'BGBl'
bgb.metadaten.get('zitstelle')          # citation location
```

### bgb.get_section(paragraph)

Look up a section by paragraph number string.

```python
sec = bgb.get_section('433')
sec['titel']    # → 'Vertragstypische Pflichten beim Kaufvertrag'
sec['content']  # → list of Absatz dicts
```

### bgb.get_absatz(paragraph, absatz)

Look up a specific Absatz within a section.

```python
abs1 = bgb.get_absatz('433', 1)
abs1 = bgb.get_absatz('433', '1')   # string also works
```


## normalise() - standalone function

Available directly without loading any law data.

```python
from bundesrecht import normalise

normalise('§ 312 i.V.m. § 355 BGB')
# → ['§ 312 BGB', '§ 355 BGB']

normalise('§§ 12-15 BGB')
# → ['§ 12 BGB', '§ 13 BGB', '§ 14 BGB', '§ 15 BGB']

normalise('§ 2 Abs. 1 Nr. 1, Nr. 7, Abs. 2 UrhG')
# → ['§ 2 Abs. 1 Nr. 1 UrhG', '§ 2 Abs. 1 Nr. 7 UrhG', '§ 2 Abs. 2 UrhG']

normalise('§§ 137 S. 2, 398, 903 BGB')
# → ['§ 137 Satz 2 BGB', '§ 398 BGB', '§ 903 BGB']

normalise('§§ 46 Abs. 2 ArbGG, 91 Abs. 1 ZPO')
# → ['§ 46 Abs. 2 ArbGG', '§ 91 Abs. 1 ZPO']

# iVm variants — all recognised
normalise('§ 1 iVm § 2 BGB')
normalise('§ 1 i.V.m. § 2 BGB')
normalise('§ 1 i. V. m. § 2 BGB')
# → ['§ 1 BGB', '§ 2 BGB']  in all cases

# S. expands to Satz
normalise('§ 1 S. 2 BGB')
# → ['§ 1 Satz 2 BGB']

# ff. and f. are preserved
normalise('§ 312 ff. BGB')
# → ['§ 312 ff. BGB']
```


## parse_reference() - standalone function

Parses a raw citation string into a structured `LawReference` object
without resolving it against any law data.

```python
from bundesrecht import parse_reference

ref = parse_reference('§ 2 Abs. 1 Nr. 1 UrhG')

ref.law                   # → 'UrhG'
ref.paragraphs            # → [ParagraphRef(...)]
str(ref)                  # → '§ 2 Abs. 1 Nr. 1 UrhG'

para = ref.paragraphs[0]
para.paragraph            # → '2'
para.sub_refs             # → [SubReference(Abs, '1'), SubReference(Nr, '1')]
str(para.sub_refs[0])     # → 'Abs. 1'
str(para.sub_refs[1])     # → 'Nr. 1'
```


## Data model

### LawReference

```python
@dataclass
class LawReference:
    paragraphs: list[ParagraphRef]   # one or more paragraphs
    law: str | None                  # e.g. 'BGB', 'UrhG'
    raw: str                         # original input string
```

### ParagraphRef

```python
@dataclass
class ParagraphRef:
    paragraph: str                   # '312', '312a', '1'
    sub_refs: list[SubReference]     # Abs, Satz, Nr, Buchst, etc.
    range_end: str | None            # set for '§ 312 bis 314'
    is_ff: bool                      # § 312 ff.
    is_f: bool                       # § 312 f.
    ivm_refs: list[SubReference]     # sub-refs after 'iVm' within a paragraph
```

### SubReference

```python
@dataclass
class SubReference:
    level: str      # 'Abs', 'Satz', 'Nr', 'Buchst', 'Alt', 'Halbsatz'
    number: str     # '1', '2', 'a', '1a'
    range_end: str  # set for 'Abs. 2 bis 4'
```

String representations:

| level     | example output  |
|-----------|-----------------|
| Abs       | `Abs. 2`        |
| Satz      | `Satz 1`        |
| Nr        | `Nr. 3`         |
| Buchst    | `Buchst. a`     |
| Alt       | `Alt. 1`        |
| Halbsatz  | `Halbsatz 2`    |


## What the normaliser handles

| Input form                          | Output                                      |
|-------------------------------------|---------------------------------------------|
| `§ 312 i.V.m. § 355 BGB`           | `['§ 312 BGB', '§ 355 BGB']`               |
| `§ 312 iVm § 355 BGB`              | `['§ 312 BGB', '§ 355 BGB']`               |
| `§§ 12-15 BGB`                     | `['§ 12 BGB', ..., '§ 15 BGB']`            |
| `§§ 12 bis 15 BGB`                 | same                                        |
| `§§ 137 S. 2, 398 BGB`             | `['§ 137 Satz 2 BGB', '§ 398 BGB']`        |
| `§§ 46 Abs. 2 ArbGG, 91 ZPO`      | `['§ 46 Abs. 2 ArbGG', '§ 91 ZPO']`       |
| `§ 2 Abs. 1 Nr. 1, Nr. 7, Abs. 2` | three separate canonical refs               |
| `§ 1 S. 2 BGB`                     | `['§ 1 Satz 2 BGB']`                       |
| `§ 312 ff. BGB`                    | `['§ 312 ff. BGB']`                        |
| `§312 BGB` (no space)              | `['§ 312 BGB']`                            |

Ranges with letter suffixes (`§§ 12a-12c`) are left unchanged because
intermediate values are not predictable.


## Resolved depth reference

| `resolved_depth` | Meaning                                          |
|------------------|--------------------------------------------------|
| `'section'`      | Only the paragraph was found (no sub-ref match)  |
| `'absatz'`       | Absatz resolved; Nummer was not requested/found  |
| `'nummer'`       | Nummer resolved; Buchstabe not requested/found   |
| `'buchstabe'`    | Fully resolved to Buchstabe level                |


## Complete example

```python
from bundesrecht import Bundesrecht, normalise, parse_reference

# Load
lib = Bundesrecht('data/gesetze.jsonl')
print(lib)   # → Bundesrecht(6867 laws loaded)

# Normalise only
normalise('§ 2 Abs. 1 Nr. 1, Nr. 7, Abs. 2 UrhG')
# → ['§ 2 Abs. 1 Nr. 1 UrhG', '§ 2 Abs. 1 Nr. 7 UrhG', '§ 2 Abs. 2 UrhG']

# Parse only
ref = parse_reference('§ 433 Abs. 1 Satz 1 BGB')
ref.law                          # → 'BGB'
ref.paragraphs[0].paragraph      # → '433'
ref.paragraphs[0].sub_refs       # → [SubReference(Abs,1), SubReference(Satz,1)]

# Resolve
results = lib.query('§ 433 Abs. 1 BGB')
r = results[0]

r.titel()          # → 'Vertragstypische Pflichten beim Kaufvertrag'
r.full_text()      # → actual statutory text of Abs. 1
r.resolved_depth   # → 'absatz'
str(r.reference)   # → '§ 433 Abs. 1 BGB'

# Inspect a law directly
bgb = lib.get_law('BGB')
bgb.metadaten.get('langue')              # → 'Bürgerliches Gesetzbuch'
bgb.metadaten.get('ausfertigung-datum')  # → '1896-08-18'
len(bgb.sections)                        # → 2541

# List all laws
lib.available_laws[:5]    # → ['AABG', 'AAG', ...]
lib.law_count             # → 6867
```