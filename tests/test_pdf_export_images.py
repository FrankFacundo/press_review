import base64

from selenium.common.exceptions import WebDriverException

from luxnews.selenium_utils import print_to_pdf


class _DummyDriver:
    def __init__(self):
        self.calls: list[tuple[str, object]] = []
        self.payload = base64.b64encode(b"pdf-bytes").decode("ascii")

    def execute_async_script(self, script, timeout_ms):
        self.calls.append(("async", timeout_ms))
        assert "image.loading = \"eager\"" in script
        return {"total": 3, "pending": 0}

    def execute_cdp_cmd(self, name, options):
        self.calls.append(("cdp", name))
        assert name == "Page.printToPDF"
        assert options.get("printBackground") is True
        return {"data": self.payload}


def test_print_to_pdf_waits_for_images_before_printing(tmp_path):
    driver = _DummyDriver()
    output_path = tmp_path / "article.pdf"

    print_to_pdf(driver, output_path)

    assert output_path.exists()
    assert output_path.read_bytes() == b"pdf-bytes"
    assert driver.calls[0][0] == "async"
    assert driver.calls[1] == ("cdp", "Page.printToPDF")


def test_print_to_pdf_continues_when_preparation_fails(tmp_path, monkeypatch):
    class _FailingDriver(_DummyDriver):
        def execute_async_script(self, script, timeout_ms):
            raise WebDriverException("prep failed")

    driver = _FailingDriver()
    output_path = tmp_path / "article.pdf"

    print_to_pdf(driver, output_path)

    assert output_path.exists()
    assert output_path.read_bytes() == b"pdf-bytes"
