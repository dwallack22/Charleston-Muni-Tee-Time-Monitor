# Charleston Muni Tee Time Monitor (WebTrac)

Monitors Charleston's WebTrac tee time search and sends notifications when new matching tee times appear.

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
playwright install chromium
```

Copy `.env.example` to `.env` and fill in your Pushover keys:

```bash
cp .env.example .env
```

Edit `config.yaml`:
- `watch.start_date`, `watch.end_date`
- `watch.start_time`, `watch.end_time`
- `watch.min_open_slots` (1..4)
- `site.check_interval_sec`

## Run

Run once:

```bash
python monitor.py --once --debug
```

Continuous monitor:

```bash
python monitor.py
```

## Notes
- This site is JavaScript-driven; the scraper uses Playwright (headless Chromium).
- The scraper intentionally avoids hardcoding `..._csrf_token=...` URLs.
- WebTrac can sometimes show green "Available" dots even when the tee time is effectively locked (cart icon is grey / tooltip says "In Use"). The scraper filters those out.
