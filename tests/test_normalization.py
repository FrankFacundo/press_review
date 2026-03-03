from luxnews.utils import contains_whole_keyword, matches_keyword_with_exclusions, normalize_text


def test_normalize_text_case_accent():
    assert normalize_text("FINANCIÈRE") == "financiere"
    assert normalize_text(" BNP   PARIBAS ") == "bnp paribas"


def test_contains_whole_keyword_does_not_match_substring():
    text = normalize_text("Training Inge Fingerzeig")

    assert contains_whole_keyword(text, "ING") is False


def test_contains_whole_keyword_matches_full_word_and_phrase():
    text = normalize_text("ING and BNP Paribas are mentioned here.")

    assert contains_whole_keyword(text, "ING") is True
    assert contains_whole_keyword(text, "BNP PARIBAS") is True


def test_matches_keyword_with_exclusions_matches_bgl_when_not_ligue():
    text = normalize_text("BGL BNP Paribas appoints a new CEO.")

    assert matches_keyword_with_exclusions(text, "BGL") is True


def test_matches_keyword_with_exclusions_blocks_bgl_ligue_context():
    text = normalize_text("Le match de BGL Ligue est reporté.")

    assert matches_keyword_with_exclusions(text, "BGL") is False


def test_matches_keyword_with_exclusions_blocks_liga_bgl_context():
    text = normalize_text("Un résumé de la Liga BGL du weekend.")

    assert matches_keyword_with_exclusions(text, "BGL") is False


def test_matches_keyword_with_exclusions_blocks_bgl_ligue_hyphen_context():
    text = normalize_text("Le choc BGL-Ligue de ce soir.")

    assert matches_keyword_with_exclusions(text, "BGL") is False
