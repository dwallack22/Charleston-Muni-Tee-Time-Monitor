from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional
from datetime import datetime
import re
import traceback

from playwright.sync_api import sync_playwright


BASE = "https://sccharlestonweb.myvscloud.com"

MONTHS = [
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
]
MONTH_RE = re.compile(rf"^\s*({'|'.join(MONTHS)})\s+(\d{{4}})\s*$")


@dataclass
class Slot:
    date: str
    time: str
    players: int  # open slots
    href: str


def _debug_dump(page, prefix: str):
    page.screenshot(path=f"{prefix}.png", full_page=True)
    with open(f"{prefix}.html", "w", encoding="utf-8") as f:
        f.write(page.content())


def _debug_dump_safe(page, prefix: str):
    try:
        _debug_dump(page, prefix)
    except Exception:
        pass


def _iso_from_mmddyyyy(s: str) -> Optional[str]:
    try:
        return datetime.strptime(s.strip(), "%m/%d/%Y").date().isoformat()
    except Exception:
        return None


def _is_disabled_cart(el) -> bool:
    """
    Grey cart icon / disabled = not bookable even if row shows available.
    """
    try:
        if el is None or el.count() == 0:
            return True
        if el.get_attribute("disabled") is not None:
            return True
        if (el.get_attribute("aria-disabled") or "").lower() == "true":
            return True
        cls = (el.get_attribute("class") or "").lower()
        if "disabled" in cls or "unavailable" in cls:
            return True
        tip = f"{(el.get_attribute('title') or '').lower()} {(el.get_attribute('aria-label') or '').lower()}"
        if "in use" in tip or "unavailable" in tip:
            return True
    except Exception:
        return True
    return False


def _best_href(row, page_url: str) -> str:
    try:
        a = row.locator("a[href]").first
        if a.count():
            h = a.get_attribute("href")
            if h:
                return h if h.startswith("http") else BASE + h
    except Exception:
        pass
    return page_url


def _left_pane(page):
    pane = page.locator("#grwebsearch_nextgengroup1").first
    return pane if pane.count() else page.locator("body")


def _find_filter_block(page, title: str):
    """
    Find the filter 'row' that contains the title label.
    In your HTML, these are: div.newline.search-criteria...
    """
    pane = _left_pane(page)
    lbl = pane.get_by_text(re.compile(rf"^{re.escape(title)}$", re.I)).first
    if lbl.count() == 0:
        lbl = pane.get_by_text(re.compile(re.escape(title), re.I)).first
    if lbl.count() == 0:
        raise RuntimeError(f"Could not find filter title '{title}'")

    block = lbl.locator("xpath=ancestor::div[contains(@class,'newline')][1]").first
    if block.count() == 0:
        block = lbl.locator("xpath=ancestor::div[1]").first
    return block


def _open_players_combobox(page, debug: bool = False):
    """
    The real select is hidden. The visible trigger is:
      button#numberofplayers_vm_1_button (aria-haspopup=listbox)
    (from your debug HTML)
    """
    block = _find_filter_block(page, "Number Of Players")

    # Prefer the exact VM button id pattern
    btn = block.locator("button[id^='numberofplayers_vm_'][id$='_button']").first
    if btn.count() == 0:
        # Fallback: any visible listbox trigger inside the block
        btn = block.locator("button[aria-haspopup='listbox']").first

    if btn.count() == 0 or not btn.is_visible():
        if debug:
            _debug_dump_safe(page, "debug_players_no_button")
        raise RuntimeError("Could not find visible Number Of Players combobox button.")

    btn.click(timeout=8000)
    return block


def _click_option_from_open_listbox(page, option_text: str, debug: bool = False):
    """
    After opening a combobox, options typically render in a listbox.
    We find a visible listbox and click the matching option.
    """
    # wait for any listbox to show up (combobox popover)
    page.wait_for_timeout(150)

    listboxes = page.locator("ul[role='listbox'], div[role='listbox']").filter(
        has=page.locator("[role='option']")
    )

    # Try visible listboxes first
    for i in range(min(listboxes.count(), 10)):
        lb = listboxes.nth(i)
        try:
            if not lb.is_visible():
                continue
            opt = lb.locator("[role='option']").filter(
                has_text=re.compile(rf"^\s*{re.escape(option_text)}\s*$")
            ).first
            if opt.count() and opt.is_visible():
                opt.click(timeout=8000)
                return
        except Exception:
            continue

    # Fallback: click any visible role=option with matching text
    opt2 = page.locator("[role='option']").filter(
        has_text=re.compile(rf"^\s*{re.escape(option_text)}\s*$")
    )
    for i in range(min(opt2.count(), 50)):
        el = opt2.nth(i)
        try:
            if el.is_visible():
                el.click(timeout=8000)
                return
        except Exception:
            continue

    if debug:
        _debug_dump_safe(page, f"debug_could_not_click_option_{option_text}")
    raise RuntimeError(f"Could not click option '{option_text}' from listbox.")


def _set_players(page, players: int, debug: bool = False):
    _open_players_combobox(page, debug=debug)
    _click_option_from_open_listbox(page, str(players), debug=debug)
    if debug:
        print(f"[debug] set Number Of Players -> {players}")


def _set_begin_time(page, begin_time_label: str, debug: bool = False):
    """
    Begin time is a timepicker with an input + dropdown button.
    In your HTML:
      input#begintime_vm_3_input (visible)
      li[role=option] texts like '08:00 am'
    """
    block = _find_filter_block(page, "Begin Time")
    dropdown_btn = block.locator("button.timepicker__dropdown-button").first
    if dropdown_btn.count() and dropdown_btn.is_visible():
        dropdown_btn.click(timeout=8000)
    else:
        # fallback: click the input to open
        inp = block.locator("#begintime_vm_3_input").first
        if inp.count() == 0:
            inp = block.locator("input.timepicker__input").first
        inp.click(timeout=8000)

    _click_option_from_open_listbox(page, begin_time_label, debug=debug)
    if debug:
        print(f"[debug] set Begin Time -> {begin_time_label}")


def _open_datepicker(page, debug: bool = False):
    block = _find_filter_block(page, "Date")
    btn = block.locator("button[id^='begindate_vm_'][id$='_button']").first
    if btn.count() == 0:
        btn = block.locator("button.datepicker-button").first
    if btn.count() == 0 or not btn.is_visible():
        if debug:
            _debug_dump_safe(page, "debug_date_no_button")
        raise RuntimeError("Could not open datepicker button.")
    btn.click(timeout=8000)


def _find_month_header(page) -> str:
    candidates = page.locator("div, span, h1, h2, h3, th").filter(
        has_text=re.compile(
            r"\b(?:January|February|March|April|May|June|July|August|September|October|November|December)\b\s+\d{4}"
        )
    )

    for i in range(min(candidates.count(), 120)):
        el = candidates.nth(i)
        try:
            if not el.is_visible():
                continue
            txt = el.inner_text().strip()
            if "Year" in txt or "Month" in txt or "Day" in txt:
                continue
            if MONTH_RE.match(txt):
                return txt
        except Exception:
            continue

    raise RuntimeError("Could not locate month header like 'February 2026'.")


def _set_date_by_calendar_grid(page, iso_date: str, debug: bool = False):
    target = datetime.strptime(iso_date, "%Y-%m-%d")
    target_header = target.strftime("%B %Y")
    day_text = str(target.day)

    _open_datepicker(page, debug=debug)
    page.wait_for_timeout(200)

    next_btn = page.locator("button:has-text('›'), button:has-text('>'), button[aria-label*='Next' i]").first
    prev_btn = page.locator("button:has-text('‹'), button:has-text('<'), button[aria-label*='Prev' i]").first

    # Navigate month
    for _ in range(36):
        current = _find_month_header(page)
        if current == target_header:
            break
        cur_dt = datetime.strptime(current, "%B %Y")
        if cur_dt < target:
            if next_btn.count() == 0:
                raise RuntimeError("No next month button found.")
            next_btn.click(timeout=8000)
        else:
            if prev_btn.count() == 0:
                raise RuntimeError("No prev month button found.")
            prev_btn.click(timeout=8000)
        page.wait_for_timeout(200)
    else:
        raise RuntimeError(f"Could not navigate datepicker to '{target_header}'")

    # Click day (calendar grid)
    day_candidates = page.locator("td, button, div").filter(
        has_text=re.compile(rf"^\s*{re.escape(day_text)}\s*$")
    )

    clicked = False
    for i in range(min(day_candidates.count(), 200)):
        el = day_candidates.nth(i)
        try:
            if not el.is_visible():
                continue
            cls = (el.get_attribute("class") or "").lower()
            if "disabled" in cls or "unavailable" in cls:
                continue
            el.click(timeout=8000)
            clicked = True
            break
        except Exception:
            continue

    if not clicked:
        if debug:
            _debug_dump_safe(page, "debug_date_day_click_fail")
        raise RuntimeError(f"Could not click day '{day_text}' in datepicker.")

    # Close picker (Done)
    done = page.get_by_role("button", name=re.compile(r"Done", re.I))
    if done.count():
        done.first.click(timeout=8000)
    else:
        page.keyboard.press("Escape")

    if debug:
        print(f"[debug] set Date -> {target.strftime('%m/%d/%Y')}")


def _goto_with_retries(page, url: str, nav_timeout_ms: int, debug: bool = False, attempts: int = 3) -> bool:
    for attempt in range(1, attempts + 1):
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=nav_timeout_ms)
            return True
        except Exception as e:
            print(f"[warn] page.goto attempt {attempt}/{attempts} failed: {e}")
            _debug_dump_safe(page, f"debug_goto_fail_attempt_{attempt}")
            if debug:
                traceback.print_exc()
            if attempt < attempts:
                page.wait_for_timeout(1200 * attempt)
    return False


def _run_search_and_wait_for_results(page, search_timeout_ms: int, debug: bool = False) -> str:
    # Click Search (left-side button)
    search_clicked = False
    for attempt in range(1, 3):
        try:
            page.get_by_role("button", name=re.compile(r"^Search$", re.I)).click(timeout=9000)
            search_clicked = True
            break
        except Exception:
            try:
                page.locator("#grwebsearch_buttonsearch, button:has-text('Search')").first.click(timeout=9000)
                search_clicked = True
                break
            except Exception as e:
                print(f"[warn] search click attempt {attempt}/2 failed: {e}")
                _debug_dump_safe(page, f"debug_search_click_fail_attempt_{attempt}")
                if debug:
                    traceback.print_exc()
                page.wait_for_timeout(500)

    if not search_clicked:
        print("[warn] search button click failed after retries")
        _debug_dump_safe(page, "debug_search_click_fail")
        return "failed"

    table = page.locator("table:has-text('Open Slots')").first
    no_results = page.locator(
        "#grwebsearch_noresultsheader, #grwebsearch_noresultsmessage, text=/did not return any matching results/i"
    ).first

    elapsed_ms = 0
    step_ms = 400
    while elapsed_ms <= search_timeout_ms:
        try:
            if table.count() > 0 and table.is_visible():
                return "table"
        except Exception:
            pass
        try:
            if no_results.count() > 0 and no_results.is_visible():
                return "no_results"
        except Exception:
            pass
        page.wait_for_timeout(step_ms)
        elapsed_ms += step_ms

    print("[warn] search completed but neither table nor no-results message appeared")
    _debug_dump_safe(page, "debug_search_wait_fail")
    return "failed"


def scrape_slots_for_date(
    url: str,
    iso_date: str,
    players_to_search: int,
    begin_time_label: str,
    load_timeout_sec: int = 45,
    debug: bool = False,
) -> List[Slot]:
    nav_timeout_ms = max(load_timeout_sec, 60) * 1000
    search_timeout_ms = max(load_timeout_sec, 60) * 1000

    with sync_playwright() as p:
        browser = None
        ctx = None
        page = None
        try:
            browser = p.chromium.launch(headless=(not debug), slow_mo=120 if debug else 0)
            ctx = browser.new_context()
            page = ctx.new_page()
            page.set_default_timeout(nav_timeout_ms)

            if not _goto_with_retries(page, url, nav_timeout_ms=nav_timeout_ms, debug=debug, attempts=3):
                print("[warn] navigation failed after retries; returning no slots")
                _debug_dump_safe(page, "debug_nav_fail")
                return []

            if debug:
                print(f"[debug] landed url: {page.url}")

            # Apply filters (using visible Vue controls)
            _set_players(page, players_to_search, debug=debug)
            _set_begin_time(page, begin_time_label, debug=debug)
            _set_date_by_calendar_grid(page, iso_date, debug=debug)

            search_state = _run_search_and_wait_for_results(page, search_timeout_ms=search_timeout_ms, debug=debug)
            if search_state == "no_results":
                if debug:
                    _debug_dump_safe(page, "debug_no_results")
                    print("[debug] no results shown by site; wrote debug_no_results.*")
                return []
            if search_state != "table":
                print("[warn] search failed; returning no slots")
                _debug_dump_safe(page, "debug_search_fail")
                return []

            if debug:
                _debug_dump_safe(page, "debug_results")
                print("[debug] wrote debug_results.*")

            slots: List[Slot] = []
            table = page.locator("table:has-text('Open Slots')").first
            rows = table.locator("tbody tr")

            if debug:
                print(f"[debug] result rows: {rows.count()}")

            for i in range(rows.count()):
                row = rows.nth(i)
                cells = row.locator("td")
                if cells.count() < 6:
                    continue

                cart_cell = cells.nth(0)
                cart_link = cart_cell.locator("a").first
                cart_btn = cart_cell.locator("button").first
                cart_el = cart_link if cart_link.count() else cart_btn

                # Grey icon / disabled = not actually bookable
                if cart_el.count() == 0 or _is_disabled_cart(cart_el):
                    continue

                time_text = cells.nth(1).inner_text().strip()
                date_text = cells.nth(2).inner_text().strip()
                open_text = cells.nth(5).inner_text().strip()

                iso = _iso_from_mmddyyyy(date_text)
                if not iso:
                    continue

                try:
                    open_slots = int(re.sub(r"[^\d]", "", open_text))
                except Exception:
                    continue

                if open_slots <= 0:
                    continue

                href = _best_href(row, page.url)
                slots.append(Slot(date=iso, time=time_text, players=open_slots, href=href))

            return slots
        except Exception as e:
            print(f"[warn] scraper exception for {iso_date}: {e}")
            if debug:
                traceback.print_exc()
            if page:
                _debug_dump_safe(page, "debug_scrape_unhandled")
            return []
        finally:
            try:
                if ctx:
                    ctx.close()
            except Exception:
                pass
            try:
                if browser:
                    browser.close()
            except Exception:
                pass
