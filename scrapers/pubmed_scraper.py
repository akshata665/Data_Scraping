"""
PubMed Scraper — Uses NCBI REST API (no key required for basic access).
Fetches article metadata + abstract for a given list of PubMed IDs or search query.
"""

import requests
import xml.etree.ElementTree as ET
import logging
from typing import Optional

from utils import (
    detect_language, infer_region, extract_domain,
    generate_topic_tags, chunk_content, now_iso, count_references,
)
from trust_engine import calculate_trust_score

logger = logging.getLogger(__name__)

PUBMED_SEARCH_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
PUBMED_FETCH_URL  = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"
PUBMED_BASE       = "https://pubmed.ncbi.nlm.nih.gov/"

HEADERS = {"User-Agent": "GutBut-Pipeline/1.0 (health AI research tool; contact@gutbut.ai)"}


def search_pubmed(query: str, max_results: int = 5) -> list[str]:
    """Return a list of PubMed IDs for a query."""
    params = {
        "db": "pubmed", "term": query, "retmax": max_results,
        "retmode": "json", "sort": "relevance",
    }
    try:
        resp = requests.get(PUBMED_SEARCH_URL, params=params, headers=HEADERS, timeout=15)
        resp.raise_for_status()
        ids = resp.json().get("esearchresult", {}).get("idlist", [])
        logger.info(f"PubMed search '{query}' returned {len(ids)} IDs.")
        return ids
    except Exception as e:
        logger.error(f"PubMed search failed: {e}")
        return []


def fetch_pubmed_record(pmid: str) -> Optional[dict]:
    """Fetch and parse a single PubMed article by PMID."""
    params = {"db": "pubmed", "id": pmid, "retmode": "xml", "rettype": "abstract"}
    try:
        resp = requests.get(PUBMED_FETCH_URL, params=params, headers=HEADERS, timeout=15)
        resp.raise_for_status()
        root = ET.fromstring(resp.content)
        article = root.find(".//PubmedArticle")
        if article is None:
            return None

        # Title
        title_el = article.find(".//ArticleTitle")
        title = "".join(title_el.itertext()).strip() if title_el is not None else "Unknown Title"

        # Abstract
        abstract_parts = article.findall(".//AbstractText")
        abstract = " ".join("".join(p.itertext()) for p in abstract_parts).strip()

        # Authors
        author_els = article.findall(".//Author")
        authors = []
        for a in author_els:
            last = a.findtext("LastName", "")
            fore = a.findtext("ForeName", "")
            suffix = a.findtext("Suffix", "")
            affiliation = a.findtext(".//Affiliation", "")
            full = f"{fore} {last}".strip()
            if suffix:
                full += f", {suffix}"
            authors.append(full)
        author_str = "; ".join(authors[:5]) if authors else "Unknown"

        # Publication date
        pub_date_el = article.find(".//PubDate")
        year  = pub_date_el.findtext("Year", "")  if pub_date_el is not None else ""
        month = pub_date_el.findtext("Month", "1") if pub_date_el is not None else "1"
        pub_date = f"{year}-{month}-01" if year else None

        # Journal
        journal = article.findtext(".//Journal/Title", "Unknown Journal")

        # Citation count (NCBI doesn't expose this via eutils easily — placeholder)
        citation_count = 0

        source_url = f"{PUBMED_BASE}{pmid}/"
        domain = extract_domain(source_url)
        content = abstract
        ingestion_ts = now_iso()
        language = detect_language(content) if content else "en"
        region = "United States / Global"
        topic_tags = generate_topic_tags(content, title)
        chunks = chunk_content(content)
        ref_count = count_references(content)

        trust_result = calculate_trust_score(
            source_url=source_url,
            source_type="pubmed",
            author=author_str,
            published_date=pub_date,
            content=content,
            domain=domain,
            citation_count=citation_count,
            transcript_available=True,
        )

        return {
            "source_url": source_url,
            "source_type": "pubmed",
            "source_title": title,
            "author": author_str,
            "journal": journal,
            "pmid": pmid,
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

    except Exception as e:
        logger.error(f"Failed to fetch PubMed PMID {pmid}: {e}")
        return None


def scrape_pubmed(queries: list[str], max_per_query: int = 3) -> list[dict]:
    """
    Main entry point.
    Accepts a list of search queries, returns list of structured records.
    """
    results = []
    seen_pmids = set()
    for query in queries:
        pmids = search_pubmed(query, max_results=max_per_query)
        for pmid in pmids:
            if pmid in seen_pmids:
                continue
            seen_pmids.add(pmid)
            record = fetch_pubmed_record(pmid)
            if record:
                results.append(record)
                logger.info(f"  ✓ PubMed {pmid} — trust={record['trust_score']} tier={record['trust_tier']}")
    return results
