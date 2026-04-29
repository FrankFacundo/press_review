from luxnews.browser_types import BrowserError

from luxnews.browser_utils import print_to_pdf


class _DummyDriver:
    def __init__(self):
        self.calls: list[tuple[str, object]] = []

    def execute_async_script(self, script, timeout_ms):
        self.calls.append(("async", timeout_ms))
        assert "image.loading = \"eager\"" in script
        return {"total": 3, "pending": 0}

    def save_pdf(self, output_path, *, print_background, prefer_css_page_size, scale):
        self.calls.append(("pdf", print_background, prefer_css_page_size, scale))
        output_path.write_bytes(b"pdf-bytes")


def test_print_to_pdf_waits_for_images_before_printing(tmp_path):
    driver = _DummyDriver()
    output_path = tmp_path / "article.pdf"

    print_to_pdf(driver, output_path)

    assert output_path.exists()
    assert output_path.read_bytes() == b"pdf-bytes"
    assert driver.calls[0][0] == "async"
    assert driver.calls[1] == ("pdf", True, True, 0.75)


def test_print_to_pdf_continues_when_preparation_fails(tmp_path, monkeypatch):
    class _FailingDriver(_DummyDriver):
        def execute_async_script(self, script, timeout_ms):
            raise BrowserError("prep failed")

    driver = _FailingDriver()
    output_path = tmp_path / "article.pdf"

    print_to_pdf(driver, output_path)

    assert output_path.exists()
    assert output_path.read_bytes() == b"pdf-bytes"
