"""
Blog Scraper — HTML-based content ingestion for health blog articles.
Handles author extraction, date parsing, disclaimer detection, and fallbacks.
"""

import requests
from bs4 import BeautifulSoup
import logging
import re
from typing import Optional
from urllib.parse import urlparse

from utils import (
    detect_language, infer_region, extract_domain,
    generate_topic_tags, chunk_content, count_references, now_iso,
)
from trust_engine import calculate_trust_score

logger = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
}

AUTHOR_SELECTORS = [
    '[rel="author"]', '.author', '.author-name', '.byline',
    '[itemprop="author"]', '.post-author', 'a[class*="author"]',
    'span[class*="author"]', 'p[class*="author"]',
]

DATE_SELECTORS = [
    'time[datetime]', 'time[pubdate]', '[itemprop="datePublished"]',
    '.published', '.post-date', '.entry-date', '.date', 'meta[name="article:published_time"]',
    'meta[property="article:published_time"]',
]


def _safe_get(url: str, timeout: int = 15) -> Optional[BeautifulSoup]:
    try:
        resp = requests.get(url, headers=HEADERS, timeout=timeout)
        resp.raise_for_status()
        return BeautifulSoup(resp.text, "lxml")
    except Exception as e:
        logger.error(f"Failed to fetch {url}: {e}")
        return None


def _extract_title(soup: BeautifulSoup) -> str:
    for selector in ["h1", "title", "[itemprop='headline']", ".post-title", ".entry-title"]:
        el = soup.select_one(selector)
        if el and el.get_text(strip=True):
            return el.get_text(strip=True)[:300]
    return "Unknown Title"


def _extract_author(soup: BeautifulSoup) -> str:
    # Try structured selectors
    for sel in AUTHOR_SELECTORS:
        el = soup.select_one(sel)
        if el and el.get_text(strip=True):
            text = el.get_text(strip=True)
            if len(text) < 80:
                return text

    # Try meta tags
    for meta_attr in [("name", "author"), ("property", "article:author")]:
        meta = soup.find("meta", {meta_attr[0]: meta_attr[1]})
        if meta and meta.get("content"):
            return meta["content"].strip()

    # Try JSON-LD
    scripts = soup.find_all("script", type="application/ld+json")
    for script in scripts:
        try:
            import json
            data = json.loads(script.string or "")
            if isinstance(data, dict):
                author = data.get("author")
                if isinstance(author, dict):
                    return author.get("name", "")
                if isinstance(author, str):
                    return author
        except Exception:
            pass

    return "Unknown"


def _extract_date(soup: BeautifulSoup) -> Optional[str]:
    for sel in DATE_SELECTORS:
        el = soup.select_one(sel)
        if el:
            dt = el.get("datetime") or el.get("content") or el.get_text(strip=True)
            if dt and len(dt) > 3:
                return dt.strip()

    # Regex scan page text for date-like strings
    text = soup.get_text()
    patterns = [
        r'\b(\w+ \d{1,2},?\s+\d{4})\b',
        r'\b(\d{1,2}\s+\w+\s+\d{4})\b',
        r'\b(\d{4}-\d{2}-\d{2})\b',
    ]
    for pat in patterns:
        m = re.search(pat, text)
        if m:
            return m.group(1)

    return None


def _extract_content(soup: BeautifulSoup) -> str:
    # Remove nav, header, footer, scripts, ads
    for tag in soup.select("nav, header, footer, script, style, aside, [class*='sidebar'], [class*='ad-']"):
        tag.decompose()

    # Try common article containers
    for sel in ["article", ".post-content", ".entry-content", ".article-body",
                 "[itemprop='articleBody']", "main", ".content"]:
        el = soup.select_one(sel)
        if el:
            text = el.get_text(separator=" ", strip=True)
            if len(text) > 200:
                return text

    return soup.get_text(separator=" ", strip=True)


def scrape_blog(urls: list[str]) -> list[dict]:
    """
    Main entry point.
    Accepts a list of blog URLs, returns structured records.
    """
    results = []

    for url in urls:
        logger.info(f"Scraping blog: {url}")
        soup = _safe_get(url)

        if soup is None:
            results.append({
                "source_url": url,
                "source_type": "blog",
                "processing_status": "fetch_failed",
                "pipeline_version": "v1.0",
            })
            continue

        title   = _extract_title(soup)
        author  = _extract_author(soup)
        pub_date = _extract_date(soup)
        content  = _extract_content(soup)
        domain   = extract_domain(url)

        ingestion_ts = now_iso()
        language     = detect_language(content)
        region       = infer_region(url)
        topic_tags   = generate_topic_tags(content, title)
        chunks       = chunk_content(content)
        ref_count    = count_references(content)

        trust_result = calculate_trust_score(
            source_url=url,
            source_type="blog",
            author=author,
            published_date=pub_date,
            content=content,
            domain=domain,
            citation_count=ref_count,
            transcript_available=True,
        )

        record = {
            "source_url": url,
            "source_type": "blog",
            "source_title": title,
            "author": author,
            "published_date": pub_date,
            "ingestion_timestamp": ingestion_ts,
            "language": language,
            "region": region,
            "topic_tags": topic_tags,
            "trust_score": trust_result["trust_score"],
            "trust_tier": trust_result["trust_tier"],
            "confidence_score": trust_result["confidence_score"],
            "score_breakdown": trust_result["score_breakdown"],
            "score_reasoning": trust_result["score_reasoning"],
            "abuse_flags": trust_result["abuse_flags"],
            "content_chunks": chunks,
            "processing_status": "success",
            "pipeline_version": trust_result["pipeline_version"],
        }

        results.append(record)
        logger.info(f"  ✓ Blog '{title[:60]}' — trust={record['trust_score']} tier={record['trust_tier']}")

    return results
