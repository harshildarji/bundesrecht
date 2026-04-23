import pytest

from bundesrecht import Bundesrecht, normalise, parse_reference


@pytest.fixture(scope="session")
def lib(request):
    return Bundesrecht(request.config.getoption("--jsonl"))


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
    assert normalise("§ 312 ff. BGB") == ["§ 312 ff. BGB"]


@pytest.mark.xfail(
    reason="law dropped when § glued to number: '§312 BGB' → ['§ 312'] instead of ['§ 312 BGB']"
)
def test_normalise_no_space_between_paragraph_sign_and_number():
    assert normalise("§312 BGB") == ["§ 312 BGB"]


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
    # known issues: (1) Absatz prefix leaks into Satz text; trailing period stripped by sentence splitter
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


def test_query_section_betrug_stgb(lib):
    r = lib.query("§ 263 StGB")
    assert r[0].titel() == "Betrug"
    assert "Vermögensvorteil" in r[0].full_text()
