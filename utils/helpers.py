"""
Utils — Shared helpers used across all scrapers.
"""

import re
import tldextract
from datetime import datetime, timezone
from typing import Optional

# ── Language detection ────────────────────────────────────────────────────────

def detect_language(text: str) -> str:
    try:
        from langdetect import detect
        return detect(text[:2000])
    except Exception:
        return "en"


# ── Region inference ──────────────────────────────────────────────────────────

TLD_REGION_MAP = {
    "uk": "United Kingdom", "au": "Australia", "ca": "Canada",
    "in": "India", "de": "Germany", "fr": "France", "jp": "Japan",
    "br": "Brazil", "mx": "Mexico", "za": "South Africa",
    "nz": "New Zealand", "sg": "Singapore", "ie": "Ireland",
}

def infer_region(url: str) -> str:
    ext = tldextract.extract(url)
    tld = ext.suffix.split(".")[-1].lower()
    if tld == "com" or tld == "org" or tld == "net" or tld == "gov" or tld == "edu":
        return "United States / Global"
    return TLD_REGION_MAP.get(tld, f"Unknown ({tld})")


# ── Domain extraction ─────────────────────────────────────────────────────────

def extract_domain(url: str) -> str:
    ext = tldextract.extract(url)
    return f"{ext.domain}.{ext.suffix}"


# ── Keyword / topic tagging ───────────────────────────────────────────────────

HEALTH_TOPIC_KEYWORDS = {
    "gut_health": ["gut", "microbiome", "probiotics", "prebiotics", "digestive", "intestinal", "bowel", "colon"],
    "mental_health": ["anxiety", "depression", "mental health", "stress", "mindfulness", "therapy", "psychiatry"],
    "nutrition": ["nutrition", "diet", "vitamins", "minerals", "calories", "protein", "carbohydrate", "fat"],
    "sleep": ["sleep", "insomnia", "circadian", "melatonin", "rem", "sleep quality"],
    "exercise": ["exercise", "fitness", "workout", "strength training", "cardio", "physical activity"],
    "heart_health": ["heart", "cardiovascular", "blood pressure", "cholesterol", "cardiac"],
    "diabetes": ["diabetes", "insulin", "glucose", "blood sugar", "type 2", "type 1"],
    "cancer": ["cancer", "tumor", "oncology", "chemotherapy", "radiation", "malignant"],
    "immunity": ["immune", "immunity", "autoimmune", "inflammation", "cytokine", "antibody"],
    "womens_health": ["menopause", "pregnancy", "fertility", "menstrual", "pcos", "estrogen"],
}

def generate_topic_tags(text: str, title: str = "") -> list[str]:
    combined = (text + " " + title).lower()
    tags = []
    for tag, keywords in HEALTH_TOPIC_KEYWORDS.items():
        if any(kw in combined for kw in keywords):
            tags.append(tag)
    # Extract prominent capitalized phrases as extra tags
    extra = re.findall(r'\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,3}\b', title)
    for e in extra[:5]:
        slug = e.lower().replace(" ", "_")
        if slug not in tags:
            tags.append(slug)
    return tags[:10]


# ── Content chunking ──────────────────────────────────────────────────────────

def chunk_content(text: str, chunk_size: int = 500, overlap: int = 50) -> list[str]:
    """Split text into overlapping word chunks for RAG ingestion."""
    words = text.split()
    chunks = []
    i = 0
    while i < len(words):
        chunk = " ".join(words[i: i + chunk_size])
        chunks.append(chunk)
        i += chunk_size - overlap
    return chunks


# ── Reference / citation counting (blog) ─────────────────────────────────────

def count_references(text: str) -> int:
    """Count hyperlinks or numbered references as a proxy for citations."""
    urls = re.findall(r'https?://\S+', text)
    numbered = re.findall(r'\[\d+\]', text)
    return len(urls) + len(numbered)


# ── Ingestion timestamp ───────────────────────────────────────────────────────

def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
