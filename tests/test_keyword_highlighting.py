import pytest

try:
    from selenium.common.exceptions import WebDriverException
    from luxnews.selenium_utils import highlight_keywords_on_page
except ModuleNotFoundError:
    WebDriverException = Exception
    highlight_keywords_on_page = None


class _DummyDriver:
    def __init__(self, result):
        self.result = result
        self.calls: list[tuple[str, list[str]]] = []

    def execute_script(self, script, keywords):
        self.calls.append((script, keywords))
        return self.result


@pytest.mark.skipif(highlight_keywords_on_page is None, reason="selenium not installed")
def test_highlight_keywords_on_page_executes_script_with_cleaned_keywords():
    driver = _DummyDriver(result=3)

    count = highlight_keywords_on_page(driver, ["  BNP  ", "", "bnp", "BGL"])

    assert count == 3
    assert len(driver.calls) == 1
    script, cleaned_keywords = driver.calls[0]
    assert cleaned_keywords == ["BNP", "BGL"]
    assert "hasWordBoundaries" in script


@pytest.mark.skipif(highlight_keywords_on_page is None, reason="selenium not installed")
def test_highlight_keywords_on_page_returns_zero_on_webdriver_error():
    class _FailingDriver:
        def execute_script(self, script, keywords):
            raise WebDriverException("boom")

    count = highlight_keywords_on_page(_FailingDriver(), ["BNP"])

    assert count == 0
