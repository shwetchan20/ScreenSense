from __future__ import annotations

import re
import time
from dataclasses import dataclass
from typing import Iterable

from screensense.core.action_gate import ActionGate
try:
    from ddgs import DDGS
except Exception:  # pragma: no cover
    DDGS = None  # type: ignore[assignment]

try:
    from playwright.sync_api import sync_playwright
except Exception:  # pragma: no cover
    sync_playwright = None  # type: ignore[assignment]
try:
    from playwright.async_api import async_playwright
except Exception:  # pragma: no cover
    async_playwright = None  # type: ignore[assignment]


@dataclass(slots=True)
class SearchResult:
    title: str
    snippet: str
    link: str


class BrowserOps:
    def __init__(self, action_gate: ActionGate | None = None) -> None:
        self._gate = action_gate
        self._playwright = None
        self._browser = None
        self._context = None
        self._page = None
        self._apw = None
        self._abrowser = None
        self._acontext = None
        self._apage = None

    def search_web(self, query: str) -> str:
        if not self._approve(f"search_web {query}", "low"):
            return ""
        try:
            api_content = self.search_web_api(query)
            if api_content:
                return api_content
            page = self._ensure_page()
            if page is None:
                return ""
            url = f"https://html.duckduckgo.com/html/?q={_encode_query(query)}"
            print("[BrowserOps] navigating to duckduckgo...")
            page.goto(url, wait_until="domcontentloaded", timeout=15000)
            page.wait_for_timeout(2000)
            try:
                print(f"[BrowserOps] page title: {page.title()}")
            except Exception:
                pass
            content = self._extract_ddg_content(page)
            print(f"[BrowserOps] content length: {len(content)}")
            if content:
                return content
            results = self._extract_search_results(page)
            return _format_results(results)
        except Exception as exc:
            print(f"[BrowserOps] {type(exc).__name__}: {exc}")
            return f"search failed: {exc}"

    def search_web_api(self, query: str) -> str:
        if DDGS is None:
            return ""
        try:
            with DDGS() as ddgs:
                results = list(ddgs.text(query, max_results=5))
        except Exception:
            return ""
        if not results:
            return ""
        output: list[str] = []
        for item in results:
            title = str(item.get("title") or "").strip()
            href = str(item.get("href") or "").strip()
            body = str(item.get("body") or "").strip()
            if title:
                output.append(f"TITLE: {title}")
            if href:
                output.append(f"URL: {href}")
            if body:
                output.append(f"SNIPPET: {body}")
        return "\n".join(output)

    def open_url(self, url: str) -> str:
        if not self._approve(f"open_url {url}", "low"):
            return ""
        page = self._ensure_page()
        if page is None:
            return ""
        print(f"[BrowserOps] opening URL: {url}")
        page.goto(url, wait_until="domcontentloaded", timeout=15000)
        page.wait_for_timeout(1500)
        try:
            text = page.evaluate(
                """() => {
                    ['script','style','nav','footer','header','aside']
                        .forEach(tag => {
                            document.querySelectorAll(tag)
                                .forEach(el => el.remove());
                        });
                    return document.body.innerText
                        .replace(/\\n{3,}/g, '\\n\\n')
                        .trim()
                        .slice(0, 3000);
                }"""
            )
        except Exception:
            return ""
        return _clean_text(str(text or ""))[:3000]

    async def open_url_async(self, url: str) -> str:
        if not self._approve(f"open_url {url}", "low"):
            return ""
        try:
            import httpx
        except Exception as exc:
            print(f"[BrowserOps] open_url_async failed: {exc}")
            return ""
        print(f"[BrowserOps] opening URL: {url}")
        try:
            headers = {
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/120.0.0.0 Safari/537.36"
                )
            }
            async with httpx.AsyncClient(
                timeout=15,
                follow_redirects=True,
                headers=headers,
            ) as client:
                response = await client.get(url)
                text = response.text
        except Exception as exc:
            print(f"[BrowserOps] open_url_async failed: {exc}")
            return ""
        text = re.sub(r"<script[^>]*>.*?</script>", "", text, flags=re.DOTALL | re.IGNORECASE)
        text = re.sub(r"<style[^>]*>.*?</style>", "", text, flags=re.DOTALL | re.IGNORECASE)
        text = re.sub(r"<[^>]+>", " ", text)
        text = re.sub(r"\\s+", " ", text).strip()
        return text[:3000]

    def search_docs(self, query: str, site: str | None = None) -> str:
        if site:
            query = f"site:{site} {query}"
        return self.search_web(query)

    def get_current_page_text(self) -> str:
        if not self._approve("get_current_page_text", "low"):
            return ""
        page = self._ensure_page()
        if page is None:
            return ""
        try:
            text = page.inner_text("body")
        except Exception:
            return ""
        return _clean_text(text)[:2000]

    def search_stackoverflow(self, error_text: str) -> str:
        results = self.search_docs(error_text, "stackoverflow.com")
        return results

    def _ensure_page(self):
        if sync_playwright is None:
            print("[BrowserOps] Playwright not installed. Run: pip install playwright")
            return None
        if self._page is not None:
            return self._page
        try:
            self._playwright = sync_playwright().start()
            self._browser = self._playwright.chromium.launch(headless=True)
            self._context = self._browser.new_context()
            self._page = self._context.new_page()
            print("[BrowserOps] browser ready")
            return self._page
        except Exception as exc:
            print(f"[BrowserOps] launch failed: {exc}")
            print("[BrowserOps] run: playwright install chromium")
            return None

    async def _ensure_async_page(self):
        if async_playwright is None:
            print("[BrowserOps] Playwright async API not installed. Run: pip install playwright")
            return None
        if self._apage is not None:
            return self._apage
        try:
            self._apw = await async_playwright().start()
            self._abrowser = await self._apw.chromium.launch(headless=True)
            self._acontext = await self._abrowser.new_context()
            self._apage = await self._acontext.new_page()
            print("[BrowserOps] browser ready (async)")
            return self._apage
        except Exception as exc:
            print(f"[BrowserOps] async launch failed: {exc}")
            print("[BrowserOps] run: playwright install chromium")
            return None

    def _approve(self, preview: str, risk: str) -> bool:
        if self._gate is None:
            return True
        return self._gate.approve(preview, risk)

    @staticmethod
    def _extract_search_results(page) -> list[SearchResult]:
        results: list[SearchResult] = []
        try:
            blocks = page.query_selector_all("div.g")
        except Exception:
            return results
        for block in blocks:
            if len(results) >= 5:
                break
            try:
                title_el = block.query_selector("h3")
                link_el = block.query_selector("a")
                snippet_el = block.query_selector("div.VwiC3b")
                title = title_el.inner_text().strip() if title_el else ""
                link = link_el.get_attribute("href") if link_el else ""
                snippet = snippet_el.inner_text().strip() if snippet_el else ""
                if title and link:
                    results.append(SearchResult(title=title, snippet=snippet, link=link))
            except Exception:
                continue
        return results

    @staticmethod
    def _extract_ddg_content(page) -> str:
        try:
            results = page.evaluate(
                """() => {
                    const items = [];
                    document.querySelectorAll('.result__title')
                        .forEach(el => items.push('TITLE: ' + el.innerText.trim()));
                    document.querySelectorAll('.result__snippet')
                        .forEach(el => items.push('SNIPPET: ' + el.innerText.trim()));
                    document.querySelectorAll('.result__url')
                        .forEach(el => items.push('URL: ' + el.innerText.trim()));
                    return items.slice(0, 15).join('\\n');
                }"""
            )
            if results:
                print(f"[BrowserOps] extracted: {str(results)[:200]}")
                return str(results)
        except Exception:
            pass
        try:
            snippets = page.query_selector_all(".result__snippet")
        except Exception:
            snippets = []
        lines: list[str] = []
        for snippet in snippets[:5]:
            try:
                text = snippet.inner_text().strip()
            except Exception:
                continue
            if text:
                lines.append(text)
        if lines:
            return " | ".join(lines)
        try:
            paragraphs = page.query_selector_all("p")
        except Exception:
            paragraphs = []
        for para in paragraphs:
            try:
                text = para.inner_text().strip()
            except Exception:
                continue
            if len(text) > 50:
                lines.append(text)
            if len(lines) >= 5:
                break
        if lines:
            return " | ".join(lines)
        try:
            body_text = page.inner_text("body")
        except Exception:
            return ""
        cleaned = _clean_text(body_text)
        return cleaned[:1000]


def _encode_query(query: str) -> str:
    return re.sub(r"\\s+", "+", query.strip())


def _clean_text(text: str) -> str:
    cleaned = re.sub(r"\\s+", " ", text).strip()
    return cleaned


def _format_results(results: list[SearchResult]) -> str:
    if not results:
        return ""
    lines: list[str] = []
    for idx, item in enumerate(results, start=1):
        snippet = f" — {item.snippet}" if item.snippet else ""
        lines.append(f"{idx}. {item.title}{snippet}")
    return "\n".join(lines)
