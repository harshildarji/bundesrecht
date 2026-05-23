import pytest

from bundesrecht import Bundesrecht, LawData, QueryResult, normalise, parse_reference
from bundesrecht.lookup import LawLibrary


@pytest.fixture(scope="session")
def lib(request):
    return Bundesrecht(request.config.getoption("--jsonl"))


def test_law_library_jurabk_takes_precedence_over_later_amtabk_alias(tmp_path):
    jsonl = tmp_path / "laws.jsonl"
    jsonl.write_text(
        "\n".join(
            [
                '{"gesetze_id":"TAV::BJNR217700008","jurabk":"TAV","metadaten":{},"sections":[]}',
                '{"gesetze_id":"TAmbV::BJNR181600022","jurabk":"TAmbV","metadaten":{"amtabk":"TAV"},"sections":[]}',
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    lib = LawLibrary(jsonl)

    assert lib.get_law("TAV").gesetze_id == "TAV::BJNR217700008"
    assert lib.get_law("TAmbV").gesetze_id == "TAmbV::BJNR181600022"


def test_law_library_keeps_amtabk_alias_when_no_primary_collision(tmp_path):
    jsonl = tmp_path / "laws.jsonl"
    jsonl.write_text(
        '{"gesetze_id":"TAmbV::BJNR181600022","jurabk":"TAmbV","metadaten":{"amtabk":"TAV"},"sections":[]}\n',
        encoding="utf-8",
    )

    lib = LawLibrary(jsonl)

    assert lib.get_law("TAV").gesetze_id == "TAmbV::BJNR181600022"


# normalise
def test_normalise_ivm_dots():
    assert normalise("§ 312 i.V.m. § 355 BGB") == ["§ 312 BGB", "§ 355 BGB"]


def test_normalise_ivm_no_dots():
    assert normalise("§ 1 iVm § 2 BGB") == ["§ 1 BGB", "§ 2 BGB"]


def test_normalise_ivm_spaced():
    assert normalise("§ 1 i. V. m. § 2 BGB") == ["§ 1 BGB", "§ 2 BGB"]


def test_normalise_range():
    assert normalise("§§ 12-15 BGB") == ["§ 12 BGB", "§ 13 BGB", "§ 14 BGB", "§ 15 BGB"]


def test_normalise_multi_target():
    assert normalise("§ 2 Abs. 1 Nr. 1, Nr. 7, Abs. 2 UrhG") == [
        "§ 2 Abs. 1 Nr. 1 UrhG",
        "§ 2 Abs. 1 Nr. 7 UrhG",
        "§ 2 Abs. 2 UrhG",
    ]


def test_normalise_multi_law():
    assert normalise("§§ 46 Abs. 2 ArbGG, 91 Abs. 1 ZPO") == [
        "§ 46 Abs. 2 ArbGG",
        "§ 91 Abs. 1 ZPO",
    ]


def test_normalise_shared_law_with_satz():
    assert normalise("§§ 137 S. 2, 398, 903 BGB") == [
        "§ 137 Satz 2 BGB",
        "§ 398 BGB",
        "§ 903 BGB",
    ]


def test_normalise_satz_shorthand():
    assert normalise("§ 1 S. 2 BGB") == ["§ 1 Satz 2 BGB"]


def test_normalise_ff():
    assert normalise("§ 312 ff. BGB", ff_expansion=3) == [
        "§ 312 BGB",
        "§ 313 BGB",
        "§ 314 BGB",
    ]


def test_normalise_no_space_between_paragraph_sign_and_number():
    assert normalise("§312 BGB") == ["§ 312 BGB"]


def test_normalise_no_space_letter_suffix():
    assert normalise("§312a BGB") == ["§ 312a BGB"]


def test_normalise_no_space_multi_paragraph():
    assert normalise("§§312,313 BGB") == ["§ 312 BGB", "§ 313 BGB"]


def test_normalise_no_space_single_digit():
    assert normalise("§1 BGB") == ["§ 1 BGB"]


def test_normalise_no_space_art():
    assert normalise("Art.20 GG") == ["Art. 20 GG"]


def test_parse_no_space_law_preserved():
    r = parse_reference("§133 StGB")
    assert r.paragraphs[0].paragraph == "133"
    assert r.law == "StGB"


def test_parse_no_space_with_sub_ref():
    r = parse_reference("§433 Abs. 1 BGB")
    assert r.paragraphs[0].paragraph == "433"
    assert r.paragraphs[0].sub_refs[0].level == "Abs"
    assert r.paragraphs[0].sub_refs[0].number == "1"
    assert r.law == "BGB"


# parse_reference
def test_parse_simple():
    ref = parse_reference("§ 433 Abs. 1 BGB")
    assert ref.law == "BGB"
    assert len(ref.paragraphs) == 1
    assert ref.paragraphs[0].paragraph == "433"
    assert len(ref.paragraphs[0].sub_refs) == 1
    assert ref.paragraphs[0].sub_refs[0].level == "Abs"
    assert ref.paragraphs[0].sub_refs[0].number == "1"


def test_parse_multi_sub_ref():
    ref = parse_reference("§ 2 Abs. 1 Nr. 1 UrhG")
    assert ref.law == "UrhG"
    para = ref.paragraphs[0]
    assert para.paragraph == "2"
    assert para.sub_refs[0].level == "Abs"
    assert para.sub_refs[0].number == "1"
    assert para.sub_refs[1].level == "Nr"
    assert para.sub_refs[1].number == "1"


def test_parse_multi_paragraph():
    ref = parse_reference("§§ 312, 313 BGB")
    assert ref.law == "BGB"
    assert len(ref.paragraphs) == 2
    assert ref.paragraphs[0].paragraph == "312"
    assert ref.paragraphs[1].paragraph == "313"
    assert ref.paragraphs[0].sub_refs == []
    assert ref.paragraphs[1].sub_refs == []


# query - section level
def test_query_section_titel(lib):
    r = lib.query("§ 433 BGB")
    assert len(r) == 1
    assert r[0].titel() == "Vertragstypische Pflichten beim Kaufvertrag"
    assert r[0].resolved_depth == "section"


def test_query_section_contains_both_absaetze(lib):
    r = lib.query("§ 433 BGB")
    text = r[0].full_text()
    assert "Durch den Kaufvertrag" in text
    assert "vereinbarten Kaufpreis" in text


def test_query_section_no_titel(lib):
    r = lib.query("§ 1 HGB")
    assert r[0].titel() == ""
    assert "Kaufmann" in r[0].full_text()


def test_query_section_weggefallen(lib):
    r = lib.query("§ 343 HGB")
    assert "weggefallen" in r[0].full_text()


# query - absatz level
def test_query_absatz_bgb_242(lib):
    r = lib.query("§ 242 BGB")
    assert len(r) == 1
    assert r[0].resolved_depth == "absatz"
    assert r[0].titel() == "Leistung nach Treu und Glauben"
    assert (
        r[0].full_text()
        == "Der Schuldner ist verpflichtet, die Leistung so zu bewirken, wie Treu und Glauben mit Rücksicht auf die Verkehrssitte es erfordern."
    )


def test_query_absatz_bgb_433_abs1(lib):
    r = lib.query("§ 433 Abs. 1 BGB")
    assert r[0].resolved_depth == "absatz"
    assert "Durch den Kaufvertrag" in r[0].full_text()
    assert "vereinbarten Kaufpreis" not in r[0].full_text()


def test_query_absatz_bgb_985(lib):
    r = lib.query("§ 985 BGB")
    assert r[0].resolved_depth == "absatz"
    assert r[0].titel() == "Herausgabeanspruch"
    assert (
        r[0].full_text()
        == "Der Eigentümer kann von dem Besitzer die Herausgabe der Sache verlangen."
    )


def test_query_absatz_stgb_1(lib):
    r = lib.query("§ 1 StGB")
    assert r[0].resolved_depth == "absatz"
    assert r[0].titel() == "Keine Strafe ohne Gesetz"
    assert (
        r[0].full_text()
        == "Eine Tat kann nur bestraft werden, wenn die Strafbarkeit gesetzlich bestimmt war, bevor die Tat begangen wurde."
    )


def test_query_absatz_urhg_1(lib):
    r = lib.query("§ 1 UrhG")
    assert r[0].resolved_depth == "absatz"
    assert r[0].titel() == "Allgemeines"
    assert (
        r[0].full_text()
        == "Die Urheber von Werken der Literatur, Wissenschaft und Kunst genießen für ihre Werke Schutz nach Maßgabe dieses Gesetzes."
    )


def test_query_absatz_zpo_1(lib):
    r = lib.query("§ 1 ZPO")
    assert r[0].resolved_depth == "absatz"
    assert r[0].titel() == "Sachliche Zuständigkeit"
    assert (
        r[0].full_text()
        == "Die sachliche Zuständigkeit der Gerichte wird durch das Gesetz über die Gerichtsverfassung bestimmt."
    )


def test_query_absatz_zpo_253_abs2(lib):
    r = lib.query("§ 253 Abs. 2 ZPO")
    assert r[0].resolved_depth == "absatz"
    assert r[0].titel() == "Klageschrift"
    assert "Bezeichnung der Parteien" in r[0].full_text()
    assert "bestimmten Antrag" in r[0].full_text()


def test_query_absatz_arbgg_1(lib):
    r = lib.query("§ 1 ArbGG")
    assert r[0].resolved_depth == "absatz"
    assert r[0].titel() == "Gerichte für Arbeitssachen"
    assert (
        r[0].full_text()
        == "Die Gerichtsbarkeit in Arbeitssachen - §§ 2 bis 3 - wird ausgeübt durch die Arbeitsgerichte - §§ 14 bis 31 -, die Landesarbeitsgerichte - §§ 33 bis 39 - und das Bundesarbeitsgericht - §§ 40 bis 45 - (Gerichte für Arbeitssachen)."
    )


# query - satz level
def test_query_satz_bgb_433_abs1_satz1(lib):
    r = lib.query("§ 433 Abs. 1 Satz 1 BGB")
    assert r[0].resolved_depth == "satz"
    assert "Durch den Kaufvertrag" in r[0].full_text()
    assert (
        "zu übergeben und das Eigentum an der Sache zu verschaffen" in r[0].full_text()
    )


def test_query_satz_bgb_433_abs1_satz2(lib):
    r = lib.query("§ 433 Abs. 1 Satz 2 BGB")
    assert r[0].resolved_depth == "satz"
    assert "frei von Sach- und Rechtsmängeln" in r[0].full_text()


# query - nummer level
def test_query_nummer_urhg_2_abs1_nr1(lib):
    r = lib.query("§ 2 Abs. 1 Nr. 1 UrhG")
    assert len(r) == 1
    assert r[0].resolved_depth == "nummer"
    assert r[0].titel() == "Geschützte Werke"
    assert "Sprachwerke" in r[0].full_text()
    assert "Computerprogramme" in r[0].full_text()


# query - buchstabe level
def test_query_buchstabe_bgb_81_abs1_nr1_buchst_a(lib):
    r = lib.query("§ 81 Abs. 1 Nr. 1 Buchst. a BGB")
    assert r[0].resolved_depth == "buchstabe"
    assert "Zweck der Stiftung" in r[0].full_text()


# _match_nummer - text prefix matching
def test_query_nummer_skips_letter_suffix_items(lib):
    # § 1 HWG has items 1, 1a, 2, 3 - Nr. 2 should return item "2." not "1a."
    r = lib.query("§ 1 Abs. 1 Nr. 2 HWG")
    assert r[0].resolved_depth == "nummer"
    assert "andere Mittel" in r[0].full_text()


def test_query_nummer_without_abs_single_content(lib):
    # § 309 BGB has one content block - Nr. 2 without Abs. should resolve
    r = lib.query("§ 309 Nr. 2 BGB")
    assert r[0].resolved_depth == "nummer"
    assert "Leistungsverweigerungsrechte" in r[0].full_text()


def test_query_nummer_without_abs_multi_content_gets_note(lib):
    # § 11 HWG has two content blocks - Nr. 2 without explicit Abs. is ambiguous
    r = lib.query("§ 11 Nr. 2 HWG")
    assert r[0].resolved_depth == "section"
    assert r[0].resolution_note != ""
    assert "Nr. 2" in r[0].resolution_note


def test_query_hwg_11_abs1_nr1_without_satz_uses_first_list_group(lib):
    r = lib.query("§ 11 Abs. 1 Nr. 1 HWG")
    assert r[0].resolved_depth == "nummer"
    assert r[0].full_text() == "(weggefallen)"


def test_query_hwg_4_abs1_full_text_keeps_single_dl_listenende(lib):
    r = lib.query("§ 4 Abs. 1 HWG")
    assert r[0].resolved_depth == "absatz"
    text = r[0].full_text()
    assert "1. den Namen oder die Firma" in text
    assert "7a. bei Arzneimitteln" in text
    assert "Traditionelles pflanzliches Arzneimittel" in text


def test_query_hwg_4_section_full_text_keeps_absatz_listenende(lib):
    r = lib.query("§ 4 HWG")
    assert r[0].resolved_depth == "section"
    text = r[0].full_text()
    assert "1. den Namen oder die Firma" in text
    assert "Traditionelles pflanzliches Arzneimittel" in text
    assert "(6) Die Absätze 1, 1a, 3 und 5 gelten nicht" in text


def test_query_hwg_7_abs1_full_text_keeps_listenende_sentences(lib):
    r = lib.query("§ 7 Abs. 1 HWG")
    assert r[0].resolved_depth == "absatz"
    text = r[0].full_text()
    assert "1. es sich bei den Zuwendungen" in text
    assert "5. es sich um unentgeltlich" in text
    assert "Werbegaben für Angehörige der Heilberufe" in text
    assert "§ 47 Abs. 3 des Arzneimittelgesetzes" in text


def test_query_buchst_not_found_gets_note(lib):
    # § 5 HWG has no Buchstabe structure - falls back to absatz with a note
    r = lib.query("§ 5 Buchst. c HWG")
    assert r[0].resolved_depth in ("section", "absatz")
    assert "Buchst. c" in r[0].resolution_note


def test_query_nummer_sibling_buchstaben(lib):
    # § 309 Nr. 2 BGB has a) and b) as sibling DL - buchstaben must appear in full_text
    r = lib.query("§ 309 Nr. 2 BGB")
    text = r[0].full_text()
    assert "Leistungsverweigerungsrecht" in text  # from buchstabe a)
    assert "Zurückbehaltungsrecht" in text  # from buchstabe b)


def test_query_buchstabe_bgb_309_nr2_buchst_a(lib):
    # § 309 Abs. 1 Nr. 2 Buchst. a BGB - explicit buchstabe resolution
    r = lib.query("§ 309 Nr. 2 Buchst. a BGB")
    assert r[0].resolved_depth == "buchstabe"
    assert "Leistungsverweigerungsrecht" in r[0].full_text()


def test_query_buchstabe_bgb_309_nr2_buchst_b(lib):
    r = lib.query("§ 309 Nr. 2 Buchst. b BGB")
    assert r[0].resolved_depth == "buchstabe"
    assert "Zurückbehaltungsrecht" in r[0].full_text()


def test_query_buchstabe_bgb_81_abs1_nr1_all_buchst(lib):
    # § 81 Abs. 1 Nr. 1 has 4 buchstaben a-d
    for letter, expected in [
        ("a", "Zweck"),
        ("b", "Namen"),
        ("c", "Sitz"),
        ("d", "Vorstand"),
    ]:
        r = lib.query(f"§ 81 Abs. 1 Nr. 1 Buchst. {letter} BGB")
        assert r[0].resolved_depth == "buchstabe", f"Buchst. {letter} not resolved"
        assert (
            expected in r[0].full_text()
        ), f"Expected {expected!r} in Buchst. {letter}"


def test_query_buchstabe_bgb_438_abs1_nr1_buchst_a(lib):
    # § 438 Abs. 1 Nr. 1 Buchst. a BGB
    r = lib.query("§ 438 Abs. 1 Nr. 1 Buchst. a BGB")
    assert r[0].resolved_depth == "buchstabe"
    assert "dinglichen Recht" in r[0].full_text()


def test_query_nummer_bgb_309_nr1_no_buchst(lib):
    # § 309 Nr. 1 has no buchstaben - should resolve to nummer
    r = lib.query("§ 309 Nr. 1 BGB")
    assert r[0].resolved_depth == "nummer"
    assert "Kurzfristige" in r[0].full_text()


def test_query_buchstabe_bgb_309_nr8_buchst_a(lib):
    # § 309 Nr. 8 Buchst. a - unterbuchstaben exist inside b but not a
    r = lib.query("§ 309 Nr. 8 Buchst. a BGB")
    assert r[0].resolved_depth == "buchstabe"
    assert "Ausschluss des Rechts" in r[0].full_text()


# unterbuchstaben resolution
def test_query_unterbuchstabe_bgb_309_nr8_buchst_b_aa(lib):
    # § 309 Nr. 8 Buchst. b Buchst. aa BGB - unterbuchstabe resolution
    r = lib.query("§ 309 Nr. 8 Buchst. b Buchst. aa BGB")
    assert r[0].resolved_depth == "unterbuchstabe"


def test_query_unterbuchstabe_full_text_not_empty(lib):
    r = lib.query("§ 309 Nr. 8 Buchst. b Buchst. aa BGB")
    assert r[0].full_text() != ""


def test_query_buchstabe_b_still_resolves_without_unterbuchstabe(lib):
    # requesting only Buchst. b without unterbuchstabe should still work
    r = lib.query("§ 309 Nr. 8 Buchst. b BGB")
    assert r[0].resolved_depth == "buchstabe"
    assert r[0].full_text() != ""


def test_query_unterbuchstabe_aa_text_content(lib):
    r = lib.query("§ 309 Nr. 8 Buchst. b Buchst. aa BGB")
    assert r[0].resolved_depth == "unterbuchstabe"
    assert "Ausschluss und Verweisung" in r[0].full_text()


def test_query_unterbuchstabe_bb(lib):
    r = lib.query("§ 309 Nr. 8 Buchst. b Buchst. bb BGB")
    assert r[0].resolved_depth == "unterbuchstabe"
    assert "Nacherfüllung" in r[0].full_text()


def test_query_unterbuchstabe_cc(lib):
    r = lib.query("§ 309 Nr. 8 Buchst. b Buchst. cc BGB")
    assert r[0].resolved_depth == "unterbuchstabe"
    assert "Aufwendungen" in r[0].full_text()


def test_query_unterbuchstabe_ff(lib):
    r = lib.query("§ 309 Nr. 8 Buchst. b Buchst. ff BGB")
    assert r[0].resolved_depth == "unterbuchstabe"
    assert "Verjährung" in r[0].full_text()


def test_query_unterbuchstabe_lit_form(lib):
    # lit. b lit. aa should resolve identically
    r = lib.query("§ 309 Nr. 8 lit. b lit. aa BGB")
    assert r[0].resolved_depth == "unterbuchstabe"
    assert "Ausschluss und Verweisung" in r[0].full_text()


def test_query_unterbuchstabe_not_found_falls_back(lib):
    # zz) doesn't exist - should fall back to buchstabe with note
    r = lib.query("§ 309 Nr. 8 Buchst. b Buchst. zz BGB")
    assert r[0].resolved_depth in ("buchstabe", "nummer", "section")
    assert r[0].resolution_note != ""


# query - resolution failures
def test_query_paragraph_not_found(lib):
    r = lib.query("§ 999999 BGB")
    assert len(r) == 1
    assert r[0].resolved_depth == "section"
    assert r[0].resolution_note == "§ 999999 not found in BGB"


def test_query_unknown_law_returns_empty(lib):
    r = lib.query("§ 1 XXXUNKNOWNXXX")
    assert r == []


def test_query_gg_paragraph_1_not_found(lib):
    r = lib.query("§ 1 GG")
    assert r[0].resolution_note == "§ 1 not found in GG"


# query - multi-target expansion
def test_query_multi_target_expands(lib):
    r = lib.query("§ 2 Abs. 1 Nr. 1, Nr. 7, Abs. 2 UrhG")
    assert len(r) == 3
    assert r[0].resolved_depth == "nummer"
    assert r[1].resolved_depth == "nummer"
    assert r[2].resolved_depth == "absatz"


# normalise - Art. / Artikel refs
def test_normalise_art_simple():
    assert normalise("Art. 1 GG") == ["Art. 1 GG"]


def test_normalise_art_with_abs():
    assert normalise("Art. 20 Abs. 3 GG") == ["Art. 20 Abs. 3 GG"]


def test_normalise_artikel_full_word():
    assert normalise("Artikel 14 GG") == ["Art. 14 GG"]


def test_normalise_art_with_nr():
    assert normalise("Art. 74 Abs. 1 Nr. 1 GG") == ["Art. 74 Abs. 1 Nr. 1 GG"]


# query - Art. resolution against GG
def test_query_art_gg_1(lib):
    r = lib.query("Art. 1 GG")
    assert len(r) == 1
    assert r[0].resolved_depth == "section"


def test_query_art_gg_20_abs_3(lib):
    r = lib.query("Art. 20 Abs. 3 GG")
    assert len(r) == 1
    assert r[0].resolved_depth == "absatz"


def test_query_art_gg_section_text_present(lib):
    r = lib.query("Art. 1 GG")
    text = r[0].full_text()
    assert "(1) Die Würde des Menschen ist unantastbar." in text
    assert "(2) Das Deutsche Volk bekennt sich" in text
    assert "(3) Die nachfolgenden Grundrechte binden" in text


# parse_reference - Art. / Artikel
def test_parse_art_simple():
    r = parse_reference("Art. 1 GG")
    assert r.is_art is True
    assert len(r.paragraphs) == 1
    assert r.paragraphs[0].paragraph == "1"
    assert r.law == "GG"


def test_parse_artikel_full_word():
    r = parse_reference("Artikel 20 GG")
    assert r.is_art is True
    assert r.paragraphs[0].paragraph == "20"
    assert r.law == "GG"


def test_parse_art_with_abs():
    r = parse_reference("Art. 20 Abs. 3 GG")
    assert r.is_art is True
    assert r.paragraphs[0].paragraph == "20"
    assert r.paragraphs[0].sub_refs[0].level == "Abs"
    assert r.paragraphs[0].sub_refs[0].number == "3"


def test_parse_art_with_abs_nr():
    r = parse_reference("Art. 74 Abs. 1 Nr. 1 GG")
    assert r.is_art is True
    assert r.paragraphs[0].paragraph == "74"
    assert r.paragraphs[0].sub_refs[0].level == "Abs"
    assert r.paragraphs[0].sub_refs[1].level == "Nr"


def test_parse_art_str_output():
    r = parse_reference("Art. 1 GG")
    assert str(r) == "Art. 1 GG"


def test_parse_art_str_with_sub_refs():
    r = parse_reference("Art. 20 Abs. 3 GG")
    assert str(r) == "Art. 20 Abs. 3 GG"


# parse_reference - malformed / edge cases
def test_parse_empty_string():
    r = parse_reference("")
    assert r.paragraphs == []
    assert r.law is None


def test_parse_whitespace_only():
    r = parse_reference("   ")
    assert r.paragraphs == []


def test_parse_no_paragraph_sign():
    r = parse_reference("BGB")
    assert r.paragraphs == []


def test_parse_paragraph_sign_only():
    r = parse_reference("§")
    assert r.paragraphs == []


def test_parse_paragraph_sign_no_number():
    r = parse_reference("§ BGB")
    assert r.paragraphs == []


def test_parse_art_no_number():
    r = parse_reference("Art. GG")
    assert r.paragraphs == []


def test_normalise_empty_string():
    assert normalise("") == []


def test_normalise_whitespace_only():
    assert normalise("   ") == []


def test_normalise_garbage():
    result = normalise("xyz 123 abc")
    assert isinstance(result, list)


# prefix stripping
def test_absatz_prefix_stripped(lib):
    r = lib.query("§ 433 Abs. 1 BGB")
    text = r[0].full_text()
    assert not text.startswith("(1)")
    assert "Durch den Kaufvertrag" in text


def test_satz_prefix_stripped(lib):
    r = lib.query("§ 433 Abs. 1 Satz 1 BGB")
    text = r[0].full_text()
    assert not text.startswith("(1)")
    assert "Durch den Kaufvertrag" in text


def test_nummer_prefix_stripped(lib):
    r = lib.query("§ 2 Abs. 1 Nr. 1 UrhG")
    text = r[0].full_text()
    assert not text.startswith("1.")
    assert "Sprachwerke" in text


def test_buchstabe_prefix_stripped(lib):
    r = lib.query("§ 81 Abs. 1 Nr. 1 Buchst. a BGB")
    text = r[0].full_text()
    assert not text.startswith("a)")
    assert "Zweck der Stiftung" in text


def test_section_prefixes_preserved(lib):
    # at section depth prefixes should NOT be stripped
    r = lib.query("§ 433 BGB")
    text = r[0].full_text()
    assert "(1)" in text
    assert "(2)" in text


def test_query_section_betrug_stgb(lib):
    r = lib.query("§ 263 StGB")
    assert r[0].titel() == "Betrug"
    assert "Vermögensvorteil" in r[0].full_text()


# sub-ref und/bis expansion
def test_normalise_abs_und():
    result = normalise("Art. 29 Abs. 1 und 2 Dublin-III-VO")
    absaetze = set()
    for r in result:
        p = parse_reference(r)
        for para in p.paragraphs:
            for sr in para.sub_refs:
                if sr.level == "Abs":
                    absaetze.add(sr.number)
    assert absaetze == {"1", "2"}


def test_normalise_nr_und():
    result = normalise("§ 88 Abs. 3 Nr. 1 und 2 BayEUG")
    nummern = set()
    for r in result:
        p = parse_reference(r)
        for para in p.paragraphs:
            for sr in para.sub_refs:
                if sr.level == "Nr":
                    nummern.add(sr.number)
    assert nummern == {"1", "2"}


def test_normalise_abs_bis_range():
    result = normalise("§ 123 Abs. 1 bis 3 VwGO")
    absaetze = set()
    for r in result:
        p = parse_reference(r)
        for para in p.paragraphs:
            for sr in para.sub_refs:
                if sr.level == "Abs":
                    absaetze.add(sr.number)
    assert absaetze == {"1", "2", "3"}


def test_normalise_nr_bis_range():
    result = normalise("§ 14 Nr. 2 bis 4 BGB")
    nummern = set()
    for r in result:
        p = parse_reference(r)
        for para in p.paragraphs:
            for sr in para.sub_refs:
                if sr.level == "Nr":
                    nummern.add(sr.number)
    assert nummern == {"2", "3", "4"}


def test_normalise_abs_und_preserves_existing():
    assert normalise("§ 433 Abs. 1 BGB") == ["§ 433 Abs. 1 BGB"]


# f. / ff. expansion
def test_normalise_f_dot():
    assert normalise("§ 312 f. BGB") == ["§ 312 BGB", "§ 313 BGB"]


def test_normalise_ff_no_dot():
    assert normalise("§ 312 ff BGB", ff_expansion=3) == [
        "§ 312 BGB",
        "§ 313 BGB",
        "§ 314 BGB",
    ]


def test_normalise_f_no_dot():
    assert normalise("§ 312 f BGB") == ["§ 312 BGB", "§ 313 BGB"]


def test_normalise_ff_non_numeric_paragraph_unchanged():
    assert normalise("§ 312a ff. BGB") == ["§ 312a ff. BGB"]


def test_normalise_ff_none_default_preserves():
    # default: ff. is not expanded, preserved as-is
    assert normalise("§ 312 ff. BGB") == ["§ 312 ff. BGB"]


def test_normalise_ff_custom_expansion():
    assert normalise("§ 312 ff. BGB", ff_expansion=5) == [
        "§ 312 BGB",
        "§ 313 BGB",
        "§ 314 BGB",
        "§ 315 BGB",
        "§ 316 BGB",
    ]


def test_normalise_f_dot_unaffected_by_ff_expansion():
    # f. always expands to exactly 2 regardless of ff_expansion
    assert normalise("§ 312 f. BGB", ff_expansion=5) == ["§ 312 BGB", "§ 313 BGB"]
    assert normalise("§ 312 f. BGB") == ["§ 312 BGB", "§ 313 BGB"]


def test_parse_f_no_dot():
    r = parse_reference("§ 312 f BGB")
    assert r.paragraphs[0].paragraph == "312"
    assert r.paragraphs[0].is_f is True
    assert r.paragraphs[0].is_ff is False


def test_parse_ff_no_dot():
    r = parse_reference("§ 312 ff BGB")
    assert r.paragraphs[0].paragraph == "312"
    assert r.paragraphs[0].is_ff is True
    assert r.paragraphs[0].is_f is False


# Roman numeral Absatz shorthand
# Roman expansion happens in _expand_abbreviations (called by normalise()),
# so tests must go through normalise() first.
def _srs_from_normalise(raw):
    refs = normalise(raw) or [raw]
    srs = []
    for ref in refs:
        p = parse_reference(ref)
        for para in p.paragraphs:
            srs.extend(para.sub_refs)
    return srs


def test_roman_absatz_simple():
    srs = _srs_from_normalise("§ 7 I StVG")
    assert any(s.level == "Abs" and s.number == "1" for s in srs)


def test_roman_absatz_with_satz():
    srs = _srs_from_normalise("§ 62 I 2 AufenthG")
    assert any(s.level == "Abs" and s.number == "1" for s in srs)
    assert any(s.level == "Satz" and s.number == "2" for s in srs)


def test_roman_absatz_III():
    srs = _srs_from_normalise("§ 404 III ZPO")
    assert any(s.level == "Abs" and s.number == "3" for s in srs)


def test_roman_absatz_does_not_touch_art_II():
    # Art. II is a different construct - should not be expanded as Absatz
    result = normalise("Art. II § 5 Abs. 1 IntPatÜG")
    assert all("Abs. 2" not in r for r in result)


# Sätz(e) / Absätze plural expansion
def test_normalise_saetze_plural():
    result = normalise("§ 168 Sätze 2 und 3 BGB")
    saetze = set()
    for ref in result:
        p = parse_reference(ref)
        for para in p.paragraphs:
            for sr in para.sub_refs:
                if sr.level == "Satz":
                    saetze.add(sr.number)
    assert saetze == {"2", "3"}


def test_normalise_absaetze_plural():
    result = normalise("§ 60 Absätze 5 und 7 AufenthaltsG")
    absaetze = set()
    for ref in result:
        p = parse_reference(ref)
        for para in p.paragraphs:
            for sr in para.sub_refs:
                if sr.level == "Abs":
                    absaetze.add(sr.number)
    assert absaetze == {"5", "7"}


# Ziffer / Ziff. synonym for Nr. - go through normalise() since expansion is pre-parse
def test_ziffer_synonym():
    srs = _srs_from_normalise("§ 23 Abs. 2 Ziffer 2 SGB VIII")
    assert any(s.level == "Nr" and s.number == "2" for s in srs)


def test_ziff_abbreviated():
    srs = _srs_from_normalise("§ 52 Abs. 1 Ziff. 1 GVG")
    assert any(s.level == "Nr" and s.number == "1" for s in srs)


# lit. / lit → Buchst. expansion
def test_lit_dot_expands_to_buchst():
    srs = _srs_from_normalise("§ 1 Abs. 1 Nr. 1 lit. a UmwRG")
    assert any(s.level == "Buchst" and s.number == "a" for s in srs)


def test_lit_no_dot_expands_to_buchst():
    srs = _srs_from_normalise("§ 1 Abs. 1 Nr. 2 lit a PBZugV")
    assert any(s.level == "Buchst" and s.number == "a" for s in srs)


# Nr. 2b - embedded Buchstabe split
def test_nr_embedded_buchstabe():
    r = parse_reference("§ 17 Nr. 2b TierSchG")
    srs = r.paragraphs[0].sub_refs
    assert any(s.level == "Nr" and s.number == "2" for s in srs)
    assert any(s.level == "Buchst" and s.number == "b" for s in srs)


# g leaking from SG law abbreviation fixed
def test_sg_law_no_spurious_satz_g():
    r = parse_reference("§ 18 Satz 1 SG")
    srs = r.paragraphs[0].sub_refs
    assert all(s.number != "g" and s.number != "G" for s in srs)
    assert any(s.level == "Satz" and s.number == "1" for s in srs)
    assert r.law == "SG"


def test_sg_law_no_spurious_abs_g():
    r = parse_reference("§ 46 Abs. 3 SG")
    srs = r.paragraphs[0].sub_refs
    assert all(s.number != "g" and s.number != "G" for s in srs)
    assert any(s.level == "Abs" and s.number == "3" for s in srs)


# Ab. shorthand - pre-parse expansion, needs normalise()
def test_ab_shorthand_for_abs():
    srs = _srs_from_normalise("§ 78 Ab. 2 GBO")
    assert any(s.level == "Abs" and s.number == "2" for s in srs)


# Satz eins - pre-parse expansion, needs normalise()
def test_satz_eins():
    srs = _srs_from_normalise("§ 87 Abs. 2 Satz eins SGB V")
    assert any(s.level == "Satz" and s.number == "1" for s in srs)


# Art. Na - letter suffix is part of the article number, not a Buchstabe
def test_art_45a_gg_is_article_number():
    r = parse_reference("Art. 45a GG")
    assert r.is_art is True
    assert r.paragraphs[0].paragraph == "45a"
    assert r.paragraphs[0].sub_refs == []
    assert r.law == "GG"


# normkette() positional bug regression - _match_nummer must be used, not nummern[nr_ref - 1]
def test_normkette_gapped_nummern_uses_match_not_position():
    ref = parse_reference("§ 1 Abs. 1 Nr. 2 Buchst. b TestG")
    absatz_data = {
        "absatz": "(1) intro text:",
        "nummer": [
            {"text": "1. first nummer", "buchstaben": []},
            {"text": "1a. first-a nummer", "buchstaben": []},
            {"text": "2. second nummer", "buchstaben": [{"text": "b) buchstabe b"}]},
        ],
    }
    result = QueryResult(
        reference=ref,
        law_data=LawData({"jurabk": "TestG", "sections": []}),
        absatz_data=absatz_data,
        nummer_text="b) buchstabe b",
        resolved_depth="buchstabe",
    )
    chain = result.normkette()
    assert (
        "second nummer" in chain
    ), f"Expected Nr. 2 lead 'second nummer' in chain, got: {chain!r}"
    assert (
        "first-a" not in chain
    ), f"Got Nr. 1a (positional index 1) instead of Nr. 2: {chain!r}"


# normkette() must still work correctly for sequential Nummern after the fix
def test_normkette_sequential_nummern_unaffected():
    ref = parse_reference("§ 1 Abs. 1 Nr. 2 Buchst. a TestG")
    absatz_data = {
        "absatz": "(1) intro text:",
        "nummer": [
            {"text": "1. first nummer", "buchstaben": []},
            {"text": "2. second nummer", "buchstaben": [{"text": "a) buchstabe a"}]},
        ],
    }
    result = QueryResult(
        reference=ref,
        law_data=LawData({"jurabk": "TestG", "sections": []}),
        absatz_data=absatz_data,
        nummer_text="a) buchstabe a",
        resolved_depth="buchstabe",
    )
    chain = result.normkette()
    assert (
        "second nummer" in chain
    ), f"Expected Nr. 2 lead 'second nummer' in chain, got: {chain!r}"


# normkette() must not crash when Nr. exceeds the nummern list length
def test_normkette_nr_beyond_list_returns_no_lead():
    ref = parse_reference("§ 1 Abs. 1 Nr. 5 Buchst. a TestG")
    absatz_data = {
        "absatz": "(1) intro text:",
        "nummer": [
            {"text": "1. only nummer", "buchstaben": []},
        ],
    }
    result = QueryResult(
        reference=ref,
        law_data=LawData({"jurabk": "TestG", "sections": []}),
        absatz_data=absatz_data,
        nummer_text="a) buchstabe a",
        resolved_depth="buchstabe",
    )
    chain = result.normkette()
    assert "buchstabe a" in chain
    assert "only nummer" not in chain


# listenende schema validation
def test_listenende_string_schema_raises():
    """Old string listenende must fail clearly, not silently produce wrong output."""
    import pytest

    from bundesrecht.lookup import _assemble_absatz

    with pytest.raises(ValueError, match="old schema"):
        _assemble_absatz({"absatz": "lead", "nummer": [], "listenende": "stale string"})


# Synthetic HWG § 11 Abs. 1 fixture
# Mirrors the extractor output after the multi-DL refactor.
# Nr 0-14 = first DL group (Satz 1), Nr 15-16 = second DL group (Satz 3).
_HWG_11_ABS1 = {
    "absatz": "(1) Ausserhalb der Fachkreise darf fuer Arzneimittel nicht geworben werden",
    "nummer": [
        {"text": "1. (weggefallen)", "buchstaben": []},
        {"text": "2. zweites Item", "buchstaben": []},
        {"text": "3. drittes Item", "buchstaben": []},
        {"text": "4. viertes Item", "buchstaben": []},
        {"text": "5. fuenftes Item", "buchstaben": []},
        {"text": "6. sechstes Item", "buchstaben": []},
        {"text": "7. siebtes Item", "buchstaben": []},
        {"text": "8. achtes Item", "buchstaben": []},
        {"text": "9. neuntes Item", "buchstaben": []},
        {"text": "10. zehntes Item", "buchstaben": []},
        {"text": "11. elftes Item", "buchstaben": []},
        {"text": "12. zwoelftes Item", "buchstaben": []},
        {"text": "13. dreizehntes Item", "buchstaben": []},
        {"text": "14. vierzehntes Item", "buchstaben": []},
        {"text": "15. fuenfzehntes Item", "buchstaben": []},
        # second DL group (Satz 3), restarted labels 1 and 2
        {"text": "1. mit der Wirkung einer solchen Behandlung", "buchstaben": []},
        {"text": "2. Kinder und Jugendliche", "buchstaben": []},
    ],
    "listenende": [
        {
            "level": "absatz",
            "start": 14,
            "end": 15,
            "text": (
                "Fuer Medizinprodukte gilt Satz 1 entsprechend. "
                "Ferner darf fuer die genannten plastisch-chirurgischen Eingriffe "
                "nicht wie folgt geworben werden:"
            ),
        }
    ],
}

_HWG_11_LAW = LawData(
    {
        "jurabk": "HWG",
        "sections": [
            {
                "paragraf": "§ 11",
                "titel": "",
                "content": [_HWG_11_ABS1],
                "fussnoten": [],
                "gliederung": [],
            }
        ],
    }
)

# Queryable wrapper around the synthetic LawData - constructs without file I/O
from bundesrecht.lookup import LawLibrary as _LawLibrary

_inner_lib = _LawLibrary.__new__(_LawLibrary)
_inner_lib._laws = {"HWG": _HWG_11_LAW}
_HWG_LIB = Bundesrecht.__new__(Bundesrecht)
_HWG_LIB._library = _inner_lib


# _preprocess_satz_context unit tests
def test_preprocess_satz_context_returns_three_satz_entries():
    from bundesrecht.lookup import _preprocess_satz_context

    contexts = _preprocess_satz_context(_HWG_11_ABS1)
    assert len(contexts) == 3


def test_preprocess_satz_context_satz1_governs_first_group():
    from bundesrecht.lookup import _preprocess_satz_context

    ctx = _preprocess_satz_context(_HWG_11_ABS1)
    s1 = next(c for c in ctx if c["satz_num"] == 1)
    assert s1["nr_start"] == 0
    assert s1["nr_end"] == 15


def test_preprocess_satz_context_satz2_standalone():
    from bundesrecht.lookup import _preprocess_satz_context

    ctx = _preprocess_satz_context(_HWG_11_ABS1)
    s2 = next(c for c in ctx if c["satz_num"] == 2)
    assert s2["nr_start"] is None
    assert s2["nr_end"] is None
    assert "Medizinprodukte" in s2["text"]


def test_preprocess_satz_context_satz3_governs_second_group():
    from bundesrecht.lookup import _preprocess_satz_context

    ctx = _preprocess_satz_context(_HWG_11_ABS1)
    s3 = next(c for c in ctx if c["satz_num"] == 3)
    assert s3["nr_start"] == 15
    assert s3["nr_end"] is None
    assert "plastisch-chirurgischen" in s3["text"]


def test_preprocess_satz_context_simple_paragraph_returns_empty():
    from bundesrecht.lookup import _preprocess_satz_context

    simple = {
        "absatz": "(1) Einfacher Absatz",
        "nummer": [{"text": "1. Item", "buchstaben": []}],
        "listenende": [
            {"level": "absatz", "start": 0, "end": None, "text": "Nachsatz"}
        ],
    }
    assert _preprocess_satz_context(simple) == []


# get_satz with multi-DL context
def test_get_satz_satz2_returns_medizinprodukte_sentence():
    satz2 = _HWG_11_LAW.get_satz("11", 1, 2)
    assert satz2 is not None
    assert "Medizinprodukte" in satz2
    assert "plastisch" not in satz2


def test_get_satz_satz3_returns_plastisch_intro():
    satz3 = _HWG_11_LAW.get_satz("11", 1, 3)
    assert satz3 is not None
    assert "plastisch-chirurgischen" in satz3


# Satz-constrained Nummer resolution
def test_satz3_nr1_resolves_to_second_group():
    r = _HWG_LIB.query("§ 11 Abs. 1 Satz 3 Nr. 1 HWG")
    assert len(r) == 1
    assert r[0].resolved_depth == "nummer"
    assert "mit der Wirkung" in r[0].full_text()


def test_satz3_nr2_resolves_to_kinder():
    r = _HWG_LIB.query("§ 11 Abs. 1 Satz 3 Nr. 2 HWG")
    assert len(r) == 1
    assert r[0].resolved_depth == "nummer"
    assert "Kinder und Jugendliche" in r[0].full_text()


def test_nr1_without_satz_resolves_to_first_group():
    r = _HWG_LIB.query("§ 11 Abs. 1 Nr. 1 HWG")
    assert len(r) == 1
    assert r[0].resolved_depth == "nummer"
    assert r[0].full_text() == "(weggefallen)"


# full_text branches by resolved_depth
def test_full_text_satz_plus_nr_returns_nummer_text_not_satz_text():
    """When resolved_depth is 'nummer', full_text must not return the Satz intro."""
    r = _HWG_LIB.query("§ 11 Abs. 1 Satz 3 Nr. 1 HWG")
    assert r[0].resolved_depth == "nummer"
    text = r[0].full_text()
    assert (
        "plastisch" not in text
    ), "full_text should return Nummer text, not Satz intro"
    assert "mit der Wirkung" in text


# normkette uses satz context so restarted Nr. 1 resolves to correct lead
def test_normkette_satz3_nr1_picks_second_group_lead():
    r = _HWG_LIB.query("§ 11 Abs. 1 Satz 3 Nr. 1 HWG")
    chain = r[0].normkette()
    assert "mit der Wirkung" in chain
    assert "(weggefallen)" not in chain


def test_normkette_satz3_nr2_includes_bridge_satz():
    r = _HWG_LIB.query("§ 11 Abs. 1 Satz 3 Nr. 2 HWG")
    chain = r[0].normkette()
    assert "plastisch-chirurgischen" in chain
    assert "Kinder und Jugendliche" in chain
    assert chain.index("plastisch-chirurgischen") < chain.index(
        "Kinder und Jugendliche"
    )


# Restarted labels synthetic test: 15 items followed by 1., 2.
def test_restarted_labels_satz_context_by_index_not_label():
    """Satz context must use index ranges, not label text, to resolve Nr. 1.

    With nummern [1., 2., ..., 15., 1., 2.] and satz3 governing indices 15-16,
    Satz 3 Nr. 1 must return the second "1." (index 15), not the first (index 0).
    """
    nummern = [{"text": f"{i}. Item {i}", "buchstaben": []} for i in range(1, 16)]
    nummern += [
        {"text": "1. Satz3 first item", "buchstaben": []},
        {"text": "2. Satz3 second item", "buchstaben": []},
    ]
    absatz_data = {
        "absatz": "(1) Lead text",
        "nummer": nummern,
        "listenende": [
            {"level": "absatz", "start": 14, "end": 15, "text": "Bridge. Intro:"}
        ],
    }
    law_data = LawData(
        {
            "jurabk": "TestSatz",
            "sections": [
                {
                    "paragraf": "§ 1",
                    "titel": "",
                    "content": [absatz_data],
                    "fussnoten": [],
                    "gliederung": [],
                }
            ],
        }
    )
    inner = _LawLibrary.__new__(_LawLibrary)
    inner._laws = {"TESTSATZ": law_data}
    lib_ts = Bundesrecht.__new__(Bundesrecht)
    lib_ts._library = inner

    r_with_satz = lib_ts.query("§ 1 Abs. 1 Satz 3 Nr. 1 TestSatz")
    assert r_with_satz[0].full_text() == "Satz3 first item"

    r_without_satz = lib_ts.query("§ 1 Abs. 1 Nr. 1 TestSatz")
    assert r_without_satz[0].full_text() == "Item 1"


# _assemble_absatz positional insertion for multi-DL paragraph
def test_assemble_absatz_interleaved_listenende_in_correct_position():
    from bundesrecht.lookup import _assemble_absatz

    text = _assemble_absatz(_HWG_11_ABS1)
    pos_14 = text.find("fuenfzehntes Item")
    pos_bridge = text.find("Medizinprodukte")
    pos_16 = text.find("mit der Wirkung")
    assert (
        pos_14 < pos_bridge < pos_16
    ), "Bridge text must appear between the two DL groups in assembled text"


# Satz blocking rules - standalone and missing Satz must not allow Nr resolution
def test_satz2_nr1_blocked_standalone_satz():
    """Satz 2 is standalone (no DL group). Nr. 1 must not resolve from any DL group."""
    r = _HWG_LIB.query("§ 11 Abs. 1 Satz 2 Nr. 1 HWG")
    assert r[0].resolved_depth == "satz"
    assert "Medizinprodukte" in r[0].full_text()


def test_missing_satz_nr_blocked_in_multi_dl():
    """Satz 99 does not exist. Nr. 1 must not resolve unconstrained."""
    r = _HWG_LIB.query("§ 11 Abs. 1 Satz 99 Nr. 1 HWG")
    assert r[0].resolved_depth != "nummer"
    assert r[0].nummer_text is None


def test_satz3_nr99_falls_back_to_satz_with_correct_note():
    """Nr. 99 is not in Satz 3's list. resolved_depth stays satz, note references Satz 3."""
    r = _HWG_LIB.query("§ 11 Abs. 1 Satz 3 Nr. 99 HWG")
    assert r[0].resolved_depth == "satz"
    assert "Satz 3" in r[0].resolution_note
    assert "resolved to Satz 3" in r[0].resolution_note


# Satz-constrained Buchstabe lookup - must resolve from correct DL group
_HWG_11_ABS1_WITH_BUCHST = {
    "absatz": "(1) Lead text",
    "nummer": [
        # First DL group (Satz 1): Nr. 1 has buchstabe a) from first group
        {
            "text": "1. first group nr1",
            "buchstaben": [
                {"text": "a) first-a from first group"},
            ],
        },
        *({"text": f"{i}. item {i}", "buchstaben": []} for i in range(2, 16)),
        # Second DL group (Satz 3): Nr. 1 has buchstabe a) from second group
        {
            "text": "1. second group nr1",
            "buchstaben": [
                {"text": "a) first-a from second group"},
            ],
        },
        {"text": "2. second group nr2", "buchstaben": []},
    ],
    "listenende": [
        {"level": "absatz", "start": 14, "end": 15, "text": "Bridge. Intro:"}
    ],
}

_hwg_buchst_law = LawData(
    {
        "jurabk": "HWGBuchst",
        "sections": [
            {
                "paragraf": "§ 11",
                "titel": "",
                "content": [_HWG_11_ABS1_WITH_BUCHST],
                "fussnoten": [],
                "gliederung": [],
            }
        ],
    }
)
_hwg_buchst_inner = _LawLibrary.__new__(_LawLibrary)
_hwg_buchst_inner._laws = {"HWGBUCHST": _hwg_buchst_law}
_hwg_buchst_lib = Bundesrecht.__new__(Bundesrecht)
_hwg_buchst_lib._library = _hwg_buchst_inner


def test_satz3_nr1_buchst_a_resolves_from_correct_dl_group():
    """Satz 3 Nr. 1 Buchst. a must resolve from the second DL group, not the first."""
    r = _hwg_buchst_lib.query("§ 11 Abs. 1 Satz 3 Nr. 1 Buchst. a HWGBuchst")
    assert r[0].resolved_depth == "buchstabe"
    assert "second group" in r[0].full_text()
    assert "first group" not in r[0].full_text()


# _validate_listenende - structural validation
def test_validate_listenende_accepts_empty_list():
    from bundesrecht.lookup import _validate_listenende

    assert _validate_listenende([]) == []
    assert _validate_listenende(None) == []


def test_validate_listenende_rejects_string():
    import pytest

    from bundesrecht.lookup import _validate_listenende

    with pytest.raises(ValueError, match="old schema"):
        _validate_listenende("stale string")


def test_validate_listenende_rejects_list_of_strings():
    import pytest

    from bundesrecht.lookup import _validate_listenende

    with pytest.raises(TypeError, match="must be a dict"):
        _validate_listenende(["not a dict"])


def test_validate_listenende_rejects_missing_required_key():
    import pytest

    from bundesrecht.lookup import _validate_listenende

    # Missing start and end keys (now required)
    with pytest.raises(KeyError, match="start"):
        _validate_listenende([{"level": "absatz", "text": "ok"}])


def test_validate_listenende_rejects_invalid_level():
    import pytest

    from bundesrecht.lookup import _validate_listenende

    with pytest.raises(ValueError, match="level"):
        _validate_listenende(
            [{"level": "invalid", "start": 0, "end": None, "text": "ok"}]
        )


def test_validate_listenende_rejects_non_string_text():
    import pytest

    from bundesrecht.lookup import _validate_listenende

    with pytest.raises(TypeError, match="text.*str"):
        _validate_listenende(
            [{"level": "absatz", "start": 0, "end": None, "text": 123}]
        )


def test_validate_listenende_rejects_bad_start_type():
    import pytest

    from bundesrecht.lookup import _validate_listenende

    with pytest.raises(TypeError, match="start.*int"):
        _validate_listenende(
            [{"level": "absatz", "text": "ok", "start": "14", "end": 15}]
        )


def test_validate_listenende_accepts_valid_entry():
    from bundesrecht.lookup import _validate_listenende

    entries = [{"level": "absatz", "start": 14, "end": 15, "text": "Bridge"}]
    result = _validate_listenende(entries)
    assert result == entries


# Unterbuchstabe lookup must also be Satz-constrained
_HWG_11_WITH_UBUCH = {
    "absatz": "(1) Lead text",
    "nummer": [
        # First DL group: Nr. 1 has Buchst. a with aa) unterbuchstabe
        {
            "text": "1. first group nr1",
            "buchstaben": [
                {
                    "text": "a) first group buchst-a",
                    "unterbuchstaben": [
                        {"text": "aa) first group aa"},
                    ],
                },
            ],
        },
        *({"text": f"{i}. item {i}", "buchstaben": []} for i in range(2, 16)),
        # Second DL group: Nr. 1 also has Buchst. a with aa) (different text)
        {
            "text": "1. second group nr1",
            "buchstaben": [
                {
                    "text": "a) second group buchst-a",
                    "unterbuchstaben": [
                        {"text": "aa) second group aa"},
                    ],
                },
            ],
        },
        {"text": "2. second group nr2", "buchstaben": []},
    ],
    "listenende": [
        {"level": "absatz", "start": 14, "end": 15, "text": "Bridge. Intro:"}
    ],
}

_hwg_ubuch_law = LawData(
    {
        "jurabk": "HWGUbuch",
        "sections": [
            {
                "paragraf": "§ 11",
                "titel": "",
                "content": [_HWG_11_WITH_UBUCH],
                "fussnoten": [],
                "gliederung": [],
            }
        ],
    }
)
_hwg_ubuch_inner = _LawLibrary.__new__(_LawLibrary)
_hwg_ubuch_inner._laws = {"HWGUBUCH": _hwg_ubuch_law}
_hwg_ubuch_lib = Bundesrecht.__new__(Bundesrecht)
_hwg_ubuch_lib._library = _hwg_ubuch_inner


def test_satz3_nr1_buchst_a_ubuch_aa_resolves_from_correct_group():
    """Satz 3 Nr. 1 Buchst. a Buchst. aa must resolve from the second DL group."""
    r = _hwg_ubuch_lib.query("§ 11 Abs. 1 Satz 3 Nr. 1 Buchst. a Buchst. aa HWGUbuch")
    assert r[0].resolved_depth == "unterbuchstabe"
    assert "second group aa" in r[0].full_text()
    assert "first group" not in r[0].full_text()


def test_satz2_nr1_buchst_a_ubuch_aa_blocked_standalone_satz():
    """Standalone Satz must not resolve nested Nummer references unconstrained."""
    r = _hwg_ubuch_lib.query("§ 11 Abs. 1 Satz 2 Nr. 1 Buchst. a Buchst. aa HWGUbuch")
    assert r[0].resolved_depth == "satz"
    assert r[0].nummer_text is None
    assert r[0].unterbuchst_text is None
    assert "standalone" in r[0].resolution_note
    assert "first group" not in r[0].full_text()


def test_missing_satz_nr1_buchst_a_ubuch_aa_blocked_in_multi_dl():
    """Missing Satz must not fall through to unconstrained Unterbuchstabe lookup."""
    r = _hwg_ubuch_lib.query("§ 11 Abs. 1 Satz 99 Nr. 1 Buchst. a Buchst. aa HWGUbuch")
    assert r[0].resolved_depth == "absatz"
    assert r[0].nummer_text is None
    assert r[0].unterbuchst_text is None
    assert "Satz 99 not found" in r[0].resolution_note
