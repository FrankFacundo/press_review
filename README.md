# LuxNews

Production-grade Luxembourg media monitoring with Selenium or Playwright automation. The project searches predefined media endpoints, validates keyword matches on the rendered article, prints PDFs via Chromium PDF APIs, and provides a Streamlit workflow plus a CLI.

## Features
- Search Luxembourg media sites using the exact endpoints provided in this repo.
- Normalize keywords (case- and accent-insensitive) and validate matches using rendered article text.
- Export per-article PDFs via CDP `Page.printToPDF` and merge into a job PDF with a summary page.
- Streamlit frontend for daily runs and selector debugging.
- CLI for runs and debugging (search, article, selector playground).
- Optional Playwright backend with a persistent offline browser cache.
- Debug toolkit for artifacts, selector playground, and headed DevTools mode.

## Medias Without On-Site Search
- `chronicle.lu`: Search engine does not work properly
- `delano.lu`: Search engine does not work properly

## Install
```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .
```

## CLI
Run default daily jobs (two runs):
```bash
luxnews run --config daily
```

Custom run:
```bash
luxnews run --keywords "BGL" --keywords "BNP PARIBAS" --medias rtl.lu --medias delano.lu --business-days-before 1 --cutoff-hour 11
```
Repeat `--keywords`/`--medias` for multiple values.

Debug search:
```bash
luxnews debug-search --media rtl.lu --keyword BNP --business-days-before 1 --cutoff-hour 11 --headed --pause
```

Debug article:
```bash
luxnews debug-article --url "https://example.com/article" --driver chrome --headed --open-devtools --pause
```

Selector playground:
```bash
luxnews selector-playground --html outputs/debug/<run_id>/rtl.lu/search/0001/page.html --css "article a"
luxnews selector-playground --url "https://rtl.lu/search?q=BNP" --xpath "//a[contains(@href,'/news/')]"
```
Selector playground with selectors file:
```bash
luxnews debug-selectors --selectors-file selectors.json --url "https://rtl.lu/search?q=BNP"
```
Example selectors file:
```json
{
  "css": "article a",
  "xpath": "//a[contains(@href,'news')]"
}
```

Prepare the Playwright browser cache once while online:
```bash
luxnews install-playwright
luxnews install-playwright --platform current --platform windows-x64
```
In a source checkout, Playwright caches are stored under `<repo>/playwright/<platform>`, for example `<repo>/playwright/mac-arm64` and `<repo>/playwright/windows-x64`. Packaged apps automatically use a bundled platform-specific cache when present, and otherwise fall back to the LuxNews app-data folder. Override the cache location with `LUXNEWS_PLAYWRIGHT_CACHE_DIR=/path/to/cache`.

## Streamlit
Run the Streamlit UI:
```bash
streamlit run src/luxnews/streamlit_app.py
```

Or use the PyInstaller-friendly entry:
```bash
python run_streamlit.py
```

To launch LuxNews in one command and open the Streamlit UI in the normal system browser:
```bash
scripts/run_luxnews.sh
```

On Windows:
```bat
scripts\run_luxnews.bat
```

The browser used to display the Streamlit UI is separate from the browser automation engine used for crawling. You can open the UI in your regular browser and still run crawls with `playwright`.

The UI provides:
- One-click daily jobs (two default runs)
- Advanced mode for custom keywords/medias, automation engine, headless toggle, output folder, and debug flags
- Progress and per-media status
- Downloads for merged PDFs and JSON outputs
- Selector Playground tab

### Running Streamlit with a Playwright-downloaded browser

By default Streamlit opens your system browser. This is independent from the crawler engine selected inside LuxNews. If you specifically want the UI itself to open in a Playwright-downloaded browser, start Streamlit in headless mode and launch that browser manually.

#### Install browsers

```bash
# Chromium (via luxnews CLI, stored in playwright/<platform>/browsers/)
luxnews install-playwright --platform current

# Firefox (via Playwright directly, into the same project cache)
PLAYWRIGHT_BROWSERS_PATH=playwright/<platform>/browsers python -m playwright install firefox

# Edge (installs system-wide, not into the project cache)
python -m playwright install msedge
```

Replace `<platform>` with `mac-arm64`, `mac-x64`, `linux-x64`, or `windows-x64`.

#### Launch commands

Start Streamlit in headless mode, then open the downloaded browser pointing to the Streamlit URL. Replace `XXXX` with the revision number found in `playwright/<platform>/browsers/`.

**macOS (Apple Silicon)**
```bash
streamlit run src/luxnews/streamlit_app.py --server.headless true &

# Chromium
open -a "playwright/mac-arm64/browsers/chromium-XXXX/chrome-mac-arm64/Google Chrome for Testing.app" http://localhost:8501

# Firefox
open -a "playwright/mac-arm64/browsers/firefox-XXXX/firefox/Nightly.app" http://localhost:8501

# Edge (system-installed)
open -a "/Applications/Microsoft Edge.app" http://localhost:8501
```

**macOS (Intel)**
```bash
streamlit run src/luxnews/streamlit_app.py --server.headless true &

# Chromium
open -a "playwright/mac-x64/browsers/chromium-XXXX/chrome-mac/Google Chrome for Testing.app" http://localhost:8501

# Firefox
open -a "playwright/mac-x64/browsers/firefox-XXXX/firefox/Nightly.app" http://localhost:8501

# Edge (system-installed)
open -a "/Applications/Microsoft Edge.app" http://localhost:8501
```

**Linux**
```bash
streamlit run src/luxnews/streamlit_app.py --server.headless true &

# Chromium
playwright/linux-x64/browsers/chromium-XXXX/chrome-linux64/chrome http://localhost:8501

# Firefox
playwright/linux-x64/browsers/firefox-XXXX/firefox-linux64/firefox http://localhost:8501

# Edge (system-installed)
microsoft-edge http://localhost:8501
```

**Windows (PowerShell)**
```powershell
Start-Process streamlit -ArgumentList "run", "src\luxnews\streamlit_app.py", "--server.headless", "true"

# Chromium
& "playwright\windows-x64\browsers\chromium-XXXX\chrome-win\chrome.exe" http://localhost:8501

# Firefox
& "playwright\windows-x64\browsers\firefox-XXXX\firefox\firefox.exe" http://localhost:8501

# Edge (system-installed)
& "C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe" http://localhost:8501
```

## Outputs
Each job creates a run directory:
```
outputs/<run_id>/
  matches.json
  summary.pdf
  merged.pdf
  pdfs/
  debug/
```

## PDF Printing
PDF export uses Chromium browser APIs. Selenium uses CDP on Chrome/Edge, while the Playwright backend uses Chromium's native PDF support. The PDF is saved per article and then merged with a Run Summary page generated by reportlab.

## Debug Toolkit
### Artifact Dumping
When debug is enabled (`--debug` in CLI or UI checkbox), every search and article page stores artifacts under:
```
outputs/debug/<run_id>/<media>/<kind>/
```
Artifacts include HTML, MHTML (best-effort), full-page screenshot, console/performance logs (best-effort), and a debug bundle JSON with URL, timestamp, cookies (redacted), selector counts, title, and detected publish date.

Errors also store HTML and screenshot under:
```
outputs/errors/<run_id>/<media>/
```

### Selector Playground
Use CLI or Streamlit to run CSS/XPath selectors against:
- Offline HTML artifacts (BeautifulSoup/lxml)
- Live pages (Selenium or Playwright)

Outputs include match counts and the first N elements' text and href. A JSON report can be saved with `--report`.

### Headed DevTools Mode
Use `--headed`, `--pause`, and `--pause-on-error` to keep the browser open for inspection. Add `--open-devtools` for Chromium to auto-open DevTools (best-effort). When a pause is active, the CLI prompts: `Press Enter to continue` so you can inspect the DOM manually.

For search artifacts, enable `--search-use-selenium` or `--debug` so search pages are rendered in the selected browser backend and captured.

## Tests
Unit tests are offline. Live tests are opt-in:
```bash
pytest
RUN_LIVE_TESTS=1 pytest -m live
```

## CI
GitHub Actions runs lint-style checks (optional) and unit tests with coverage. Live tests are skipped.

## PyInstaller
Build the desktop package for the current OS:
```bash
.venv/bin/python -m pip install -e ".[packaging]"
luxnews install-playwright
.venv/bin/python scripts/build_desktop.py --target mac --smoke-test
```

Targets are `mac`, `linux`, and `windows`, but PyInstaller is not a cross-compiler:
- build `--target mac` on macOS
- build `--target linux` on Linux
- build `--target windows` on Windows

From macOS you have two supported cross-build routes:
- Linux: run `scripts/build_linux_bin.sh` to build a `linux/amd64` artifact via Docker on macOS.
- Windows: use the GitHub Actions `Desktop Packages` workflow, which builds the `.exe` on a native Windows runner and uploads it as an artifact.

Artifacts are written to:
- `dist/mac/LuxNews.app`
- `dist/linux/LuxNews`
- `dist/windows/LuxNews.exe`

If `<repo>/playwright/<platform>` contains a prepared Playwright cache for the build target, `scripts/build_desktop.py` bundles that platform-specific cache into the app as an offline archive. On first packaged launch, LuxNews extracts that archive into the normal app-data Playwright cache and then launches without downloading browser assets at runtime.

Legacy wrappers remain available:
```bash
scripts/build_linux_bin.sh
scripts/build_windows_exe.bat
```

### Linux From macOS via Docker
On macOS, `scripts/build_linux_bin.sh` automatically switches to a Docker-based `linux/amd64` builder:
```bash
scripts/build_linux_bin.sh
scripts/build_linux_bin.sh --name LuxNews --smoke-test
```
The builder prepares a Linux Playwright cache inside the container, bundles it as the same offline archive used by the native build, and writes the final artifact to `dist/linux/`.

### Windows From macOS
For Windows builds, the practical route from macOS is the GitHub Actions `Desktop Packages` workflow in this repository:
1. Open the Actions tab in GitHub.
2. Run `Desktop Packages`.
3. Select `windows` or `all`.
4. Download the uploaded `LuxNews-windows` artifact.

This produces a native Windows `.exe` that already contains the Python runtime, Playwright package, and bundled offline browser cache for first launch.

If you want to trigger that workflow from the terminal on your Mac instead of using the browser:
```bash
export GITHUB_TOKEN=...
python3 scripts/dispatch_desktop_package.py --target windows --ref main --wait --download --extract
```
Notes:
- The workflow builds the pushed commit for the selected ref, not unpushed local changes.
- The token needs permission to run workflows and read workflow artifacts.

For macOS, the generated artifact is an `.app` bundle you can double-click to launch LuxNews in the system browser. Bundled Playwright browser assets are used by crawling features when you select the Playwright automation engine.

If you want to smoke-test a Windows `.exe` from macOS, build it on Windows first and then either:
- run `scripts/test_windows_exe_on_mac.sh /path/to/LuxNews.exe` with Wine/CrossOver installed
- use a Windows VM such as UTM or Parallels

You can still prime the Windows Playwright browser cache from macOS ahead of time with `luxnews install-playwright --platform windows-x64`, but on Apple Silicon the tested Wine-based Docker builder path was not stable enough to rely on for production `.exe` builds.

## Selenium Troubleshooting
- Ensure Chrome or Edge is installed.
- If Selenium Manager cannot locate a browser, set `CHROME_BINARY` or `EDGE_BINARY` environment variables.
- Increase timeouts with `--page-timeout` or `--wait-timeout` if pages are slow.

## Playwright Troubleshooting
- Install the Python dependency with `pip install -e .`.
- Build the desktop app from the same Python environment that has the `playwright` package installed. If you keep a repo-local virtualenv, run `./.venv/bin/python scripts/build_desktop.py ...`.
- Prime the offline browser cache with `luxnews install-playwright` while you still have internet access.
- Use `luxnews install-playwright --platform current --platform windows-x64` if you want both the local browser bundle and the Windows x64 bundle present in the repo at the same time.
- In a source checkout the default cache path is `<repo>/playwright/<platform>`, which is the directory the desktop build bundles automatically for the current target.
- Packaged apps prefer a bundled `playwright/<platform>` directory and fall back to the LuxNews app-data directory if none was bundled.
- Set `LUXNEWS_PLAYWRIGHT_CACHE_DIR` if you want to keep it somewhere else.

## Terms and Robots
Respect each site's terms of service and robots.txt. This project is intended for internal monitoring and QA workflows.
