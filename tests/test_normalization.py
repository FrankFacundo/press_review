from luxnews.utils import normalize_text


def test_normalize_text_case_accent():
    assert normalize_text("FINANCIÈRE") == "financiere"
    assert normalize_text(" BNP   PARIBAS ") == "bnp paribas"
