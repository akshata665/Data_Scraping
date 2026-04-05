"""
Trust Scoring Engine
====================
Produces a weighted, explainable trust score for every ingested health content source.

Formula:
  Trust Score = 0.30 × author_credibility
              + 0.20 × citation_count
              + 0.20 × domain_authority
              + 0.20 × recency
              + 0.10 × medical_disclaimer_presence
"""

from datetime import datetime, timezone
from typing import Optional
import re

PIPELINE_VERSION = "v1.0"

# Domain authority tiers
DOMAIN_TIERS = {
    "high": [
        "pubmed.ncbi.nlm.nih.gov", "nih.gov", "cdc.gov", "who.int", "nejm.org",
        "jamanetwork.com", "thelancet.com", "bmj.com", "nature.com", "science.org",
        "mayoclinic.org", "clevelandclinic.org", "hopkinsmedicine.org", "webmd.com",
        "healthline.com", "medicalnewstoday.com", "ncbi.nlm.nih.gov",
    ],
    "medium": [
        "health.harvard.edu", "everydayhealth.com", "verywellhealth.com",
        "medscape.com", "drugs.com", "rxlist.com", "spine-health.com",
    ],
    "low": [
        "blogspot.com", "wordpress.com", "medium.com", "substack.com",
        "tumblr.com", "wix.com", "weebly.com",
    ],
    "penalty": [
        "naturalcures", "alternativehealth", "secretcures", "miraclemed",
    ],
}

MEDICAL_CREDENTIAL_PATTERNS = [
    r"\bM\.?D\.?\b", r"\bD\.?O\.?\b", r"\bPh\.?D\.?\b", r"\bR\.?N\.?\b",
    r"\bNP\b", r"\bPA\b", r"\bPharm\.?D\.?\b", r"\bDr\.\s",
]

DISCLAIMER_PATTERNS = [
    r"not\s+(?:a\s+)?medical\s+advice",
    r"consult\s+(?:a\s+|your\s+)?(?:doctor|physician|healthcare)",
    r"for\s+informational\s+purposes\s+only",
    r"this\s+(?:article|content|information)\s+is\s+not\s+intended",
    r"always\s+seek\s+(?:the\s+)?advice\s+of\s+(?:your\s+)?(?:doctor|physician)",
    r"medical\s+disclaimer",
]

SEO_SPAM_KEYWORDS = [
    "weight loss", "lose weight fast", "miracle cure", "natural remedy",
    "detox", "superfood", "boost immunity", "anti-aging", "fat burning",
]

TRUST_TIERS = [
    (0.85, 1.00, "Verified High Trust"),
    (0.65, 0.84, "Moderate Trust"),
    (0.45, 0.64, "Low Trust — Review Recommended"),
    (0.00, 0.44, "Untrusted — Exclude from AI Pipeline"),
]


def get_trust_tier(score: float) -> str:
    for low, high, label in TRUST_TIERS:
        if low <= score <= high:
            return label
    return "Untrusted — Exclude from AI Pipeline"


def score_author_credibility(author: Optional[str], domain: str, source_type: str) -> tuple[float, list[str]]:
    reasoning = []

    if not author or author.strip().lower() in ("", "unknown", "n/a", "anonymous"):
        reasoning.append("No author identified — credibility score heavily penalized.")
        return 0.10, reasoning

    # PubMed authors get automatic boost
    if source_type == "pubmed":
        reasoning.append("PubMed source — author associated with peer-reviewed publication.")
        return 0.90, reasoning

    # Check for medical credentials
    for pattern in MEDICAL_CREDENTIAL_PATTERNS:
        if re.search(pattern, author, re.IGNORECASE):
            reasoning.append(f"Author credentials contain recognized medical designation — high credibility assigned.")
            # Check domain mismatch
            if any(bad in domain for bad in DOMAIN_TIERS["low"]):
                reasoning.append("Warning: Medical credential claimed on low-authority domain — potential mismatch flagged.")
                return 0.55, reasoning
            return 0.90, reasoning

    # Named author without credentials
    reasoning.append("Named author found but no verified medical credentials detected.")
    return 0.50, reasoning


def score_citation_count(citation_count: int, source_type: str) -> tuple[float, list[str]]:
    reasoning = []

    if source_type == "pubmed":
        if citation_count >= 50:
            reasoning.append(f"Article has {citation_count} citations — highly referenced in literature.")
            return 1.0, reasoning
        elif citation_count >= 10:
            reasoning.append(f"Article has {citation_count} citations — moderately referenced.")
            return 0.75, reasoning
        elif citation_count > 0:
            reasoning.append(f"Article has {citation_count} citations — low but non-zero citation count.")
            return 0.50, reasoning
        else:
            reasoning.append("No citation data available for this source.")
            return 0.30, reasoning

    if source_type == "youtube":
        reasoning.append("YouTube source — citation scoring not applicable; applying neutral baseline.")
        return 0.40, reasoning

    # Blog: check if it has references section
    if citation_count > 0:
        reasoning.append(f"Blog source references {citation_count} external sources.")
        return min(0.70, 0.30 + citation_count * 0.08), reasoning

    reasoning.append("No references or citations found in blog content.")
    return 0.20, reasoning


def score_domain_authority(domain: str, source_type: str) -> tuple[float, list[str]]:
    reasoning = []

    if source_type == "pubmed":
        reasoning.append("PubMed source automatically receives maximum domain authority baseline.")
        return 1.0, reasoning

    for d in DOMAIN_TIERS["high"]:
        if d in domain:
            reasoning.append(f"Domain '{domain}' identified as high-authority medical/academic platform.")
            return 0.95, reasoning

    for d in DOMAIN_TIERS["medium"]:
        if d in domain:
            reasoning.append(f"Domain '{domain}' identified as medium-authority health platform.")
            return 0.70, reasoning

    for d in DOMAIN_TIERS["penalty"]:
        if d in domain:
            reasoning.append(f"Domain '{domain}' identified as potentially misleading health platform — penalized.")
            return 0.10, reasoning

    for d in DOMAIN_TIERS["low"]:
        if d in domain:
            reasoning.append(f"Domain '{domain}' identified as low-authority blog platform — domain score penalized.")
            return 0.25, reasoning

    reasoning.append(f"Domain '{domain}' not in known authority list — applying neutral score.")
    return 0.45, reasoning


def score_recency(published_date: Optional[str]) -> tuple[float, float, list[str]]:
    reasoning = []

    if not published_date:
        reasoning.append("No publication date found — recency score cannot be calculated; confidence reduced.")
        return 0.30, 0.50, reasoning

    try:
        from dateutil import parser as dateparser
        pub_dt = dateparser.parse(published_date)
        if pub_dt.tzinfo is None:
            pub_dt = pub_dt.replace(tzinfo=timezone.utc)
        now = datetime.now(timezone.utc)
        age_days = (now - pub_dt).days

        if age_days < 0:
            age_days = 0

        if age_days <= 180:
            reasoning.append(f"Content published within the last 6 months ({age_days} days ago) — full recency score applied.")
            return 1.0, 1.0, reasoning
        elif age_days <= 365:
            score = 0.85
            reasoning.append(f"Content published within the last year ({age_days} days ago) — high recency score.")
            return score, 1.0, reasoning
        elif age_days <= 730:
            score = 0.65
            reasoning.append(f"Content is 1–2 years old ({age_days} days ago) — moderate recency score.")
            return score, 0.95, reasoning
        elif age_days <= 1825:  # 5 years
            score = 0.35
            reasoning.append(f"Content is 2–5 years old ({age_days} days ago) — low recency score; medical content may be outdated.")
            return score, 0.90, reasoning
        else:
            reasoning.append(f"Content is over 5 years old ({age_days} days ago) — severe recency penalty applied; outdated medical content flagged.")
            return 0.05, 0.85, reasoning

    except Exception as e:
        reasoning.append(f"Could not parse publication date '{published_date}' — recency defaulting to low.")
        return 0.25, 0.40, reasoning


def score_medical_disclaimer(content: str) -> tuple[float, list[str]]:
    reasoning = []

    if not content:
        reasoning.append("No content available to check for medical disclaimer.")
        return 0.20, reasoning

    for pattern in DISCLAIMER_PATTERNS:
        if re.search(pattern, content, re.IGNORECASE):
            reasoning.append("Medical disclaimer detected in content — compliance signal present.")
            return 1.0, reasoning

    reasoning.append("No medical disclaimer detected — disclaimer component penalized; healthcare safety flag raised.")
    return 0.0, reasoning


def detect_abuse_flags(
    author: Optional[str],
    domain: str,
    content: str,
    published_date: Optional[str],
    source_type: str,
    transcript_available: bool = True,
) -> list[str]:
    flags = []

    # Fake author / domain mismatch
    if author:
        has_credential = any(re.search(p, author, re.IGNORECASE) for p in MEDICAL_CREDENTIAL_PATTERNS)
        is_low_domain = any(d in domain for d in DOMAIN_TIERS["low"])
        if has_credential and is_low_domain:
            flags.append("credential_domain_mismatch")

    # SEO spam detection
    if content:
        content_lower = content.lower()
        word_count = max(len(content_lower.split()), 1)
        spam_hits = sum(content_lower.count(kw) for kw in SEO_SPAM_KEYWORDS)
        density = spam_hits / word_count
        if density > 0.03:
            flags.append("seo_spam_detected")

    # Outdated content
    if published_date:
        try:
            from dateutil import parser as dateparser
            pub_dt = dateparser.parse(published_date)
            if pub_dt.tzinfo is None:
                pub_dt = pub_dt.replace(tzinfo=timezone.utc)
            age_days = (datetime.now(timezone.utc) - pub_dt).days
            if age_days > 1825:
                flags.append("outdated_medical_content")
        except Exception:
            pass

    # Missing disclaimer
    if content:
        has_disclaimer = any(re.search(p, content, re.IGNORECASE) for p in DISCLAIMER_PATTERNS)
        if not has_disclaimer:
            flags.append("no_medical_disclaimer")

    # Transcript fallback
    if source_type == "youtube" and not transcript_available:
        flags.append("transcript_unavailable_description_used")

    # Penalty domain
    for d in DOMAIN_TIERS["penalty"]:
        if d in domain:
            flags.append("known_misinformation_adjacent_domain")

    return flags


def calculate_trust_score(
    source_url: str,
    source_type: str,
    author: Optional[str],
    published_date: Optional[str],
    content: str,
    domain: str,
    citation_count: int = 0,
    transcript_available: bool = True,
) -> dict:
    """
    Main trust scoring function.
    Returns full score breakdown, reasoning, confidence, abuse flags, and tier label.
    """
    reasoning_all = []

    # Component scores
    author_score, author_reasoning = score_author_credibility(author, domain, source_type)
    citation_score, citation_reasoning = score_citation_count(citation_count, source_type)
    domain_score, domain_reasoning = score_domain_authority(domain, source_type)
    recency_score, recency_confidence, recency_reasoning = score_recency(published_date)
    disclaimer_score, disclaimer_reasoning = score_medical_disclaimer(content)

    reasoning_all.extend(author_reasoning)
    reasoning_all.extend(citation_reasoning)
    reasoning_all.extend(domain_reasoning)
    reasoning_all.extend(recency_reasoning)
    reasoning_all.extend(disclaimer_reasoning)

    # Weighted trust score
    trust_score = round(
        0.30 * author_score +
        0.20 * citation_score +
        0.20 * domain_score +
        0.20 * recency_score +
        0.10 * disclaimer_score,
        4,
    )

    # Confidence score
    confidence_factors = [1.0]
    if not author or author.strip().lower() in ("", "unknown", "n/a", "anonymous"):
        confidence_factors.append(0.75)
    if not published_date:
        confidence_factors.append(0.80)
    if source_type == "youtube" and not transcript_available:
        confidence_factors.append(0.70)
        reasoning_all.append("YouTube transcript unavailable — confidence reduced; description used as fallback.")

    confidence_score = round(recency_confidence * min(confidence_factors), 4)

    # Abuse flags
    abuse_flags = detect_abuse_flags(
        author, domain, content, published_date, source_type, transcript_available
    )

    score_breakdown = {
        "author_credibility": {"score": round(author_score, 4), "weight": 0.30, "weighted": round(0.30 * author_score, 4)},
        "citation_count":     {"score": round(citation_score, 4), "weight": 0.20, "weighted": round(0.20 * citation_score, 4)},
        "domain_authority":   {"score": round(domain_score, 4), "weight": 0.20, "weighted": round(0.20 * domain_score, 4)},
        "recency":            {"score": round(recency_score, 4), "weight": 0.20, "weighted": round(0.20 * recency_score, 4)},
        "medical_disclaimer": {"score": round(disclaimer_score, 4), "weight": 0.10, "weighted": round(0.10 * disclaimer_score, 4)},
    }

    return {
        "trust_score": trust_score,
        "trust_tier": get_trust_tier(trust_score),
        "confidence_score": confidence_score,
        "score_breakdown": score_breakdown,
        "score_reasoning": reasoning_all,
        "abuse_flags": abuse_flags,
        "pipeline_version": PIPELINE_VERSION,
    }
