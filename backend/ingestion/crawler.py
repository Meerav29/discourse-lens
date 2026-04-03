import asyncio

from playwright.async_api import async_playwright


async def _crawl_async(urls: list[str]) -> list[dict]:
    semaphore = asyncio.Semaphore(5)

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)

        async def _scrape(url: str) -> dict:
            if url.lower().endswith(".pdf"):
                return {"url": url, "html": None}
            async with semaphore:
                page = None
                try:
                    page = await browser.new_page()
                    await page.goto(url, timeout=10_000, wait_until="domcontentloaded")
                    html = await page.content()
                    return {"url": url, "html": html}
                except Exception:
                    return {"url": url, "html": None}
                finally:
                    if page:
                        await page.close()

        results = await asyncio.gather(*[_scrape(url) for url in urls])
        await browser.close()

    return [r for r in results if r["html"] is not None]


def crawl_urls(urls: list[str]) -> list[dict]:
    """
    Sync entry point — safe to call from asyncio.to_thread().
    Runs Playwright in a fresh event loop isolated from FastAPI's loop,
    which avoids the Windows NotImplementedError from subprocess transport.
    """
    return asyncio.run(_crawl_async(urls))
