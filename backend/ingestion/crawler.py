import asyncio
from collections.abc import Callable

from playwright.async_api import async_playwright

_MAX_ATTEMPTS = 2  # 1 retry on transient failure
_RETRY_BACKOFF_SECONDS = 2.0
_CONCURRENCY = 5


async def _crawl_async(
    urls: list[str],
    on_page: Callable[[str, bool], None] | None,
    should_stop: Callable[[], bool] | None,
) -> list[dict]:
    semaphore = asyncio.Semaphore(_CONCURRENCY)

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)

        async def _fetch(url: str) -> str | None:
            if url.lower().endswith(".pdf"):
                return None
            async with semaphore:
                for attempt in range(_MAX_ATTEMPTS):
                    if should_stop and should_stop():
                        return None
                    page = None
                    try:
                        page = await browser.new_page()
                        await page.goto(url, timeout=10_000, wait_until="domcontentloaded")
                        return await page.content()
                    except Exception:
                        if attempt + 1 == _MAX_ATTEMPTS:
                            return None
                        await asyncio.sleep(_RETRY_BACKOFF_SECONDS)
                    finally:
                        if page:
                            await page.close()
                return None

        async def _scrape(url: str) -> dict:
            html = await _fetch(url)
            if on_page and not (should_stop and should_stop()):
                on_page(url, html is not None)
            return {"url": url, "html": html}

        results = await asyncio.gather(*[_scrape(url) for url in urls])
        await browser.close()

    return [r for r in results if r["html"] is not None]


def crawl_urls(
    urls: list[str],
    on_page: Callable[[str, bool], None] | None = None,
    should_stop: Callable[[], bool] | None = None,
) -> list[dict]:
    """
    Sync entry point — safe to call from asyncio.to_thread().
    Runs Playwright in a fresh event loop isolated from FastAPI's loop,
    which avoids the Windows NotImplementedError from subprocess transport.

    on_page(url, ok) is called as each page finishes. Once should_stop()
    returns True, pages not yet started are skipped.
    """
    return asyncio.run(_crawl_async(urls, on_page, should_stop))
