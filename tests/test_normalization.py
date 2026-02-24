from luxnews.utils import contains_whole_keyword, normalize_text


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
