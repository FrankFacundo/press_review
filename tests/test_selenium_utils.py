from __future__ import annotations

import pytest

try:
    from selenium.webdriver.chrome.options import Options as ChromeOptions
    from selenium.webdriver.edge.options import Options as EdgeOptions
    import luxnews.selenium_utils as selenium_utils
except ModuleNotFoundError:
    ChromeOptions = None
    EdgeOptions = None
    selenium_utils = None


@pytest.mark.skipif(selenium_utils is None, reason="selenium not installed")
def test_build_options_returns_concrete_chrome_options() -> None:
    options = selenium_utils._build_options("chrome", headless=True, open_devtools=True)

    assert isinstance(options, ChromeOptions)
    assert "--headless=new" in options.arguments
    assert "--auto-open-devtools-for-tabs" in options.arguments


@pytest.mark.skipif(selenium_utils is None, reason="selenium not installed")
def test_build_options_returns_concrete_edge_options() -> None:
    options = selenium_utils._build_options("edge", headless=False, open_devtools=False)

    assert isinstance(options, EdgeOptions)
    assert "--headless=new" not in options.arguments
    assert "--auto-open-devtools-for-tabs" not in options.arguments
