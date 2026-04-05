"""
Tests for the Trust Scoring Engine
Run with: python -m pytest tests/ -v
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from trust_engine.scorer import (
    calculate_trust_score,
    score_author_credibility,
    score_domain_authority,
    score_recency,
    score_medical_disclaimer,
    get_trust_tier,
    detect_abuse_flags,
)


# ── get_trust_tier ────────────────────────────────────────────────────────────

def test_trust_tier_verified():
    assert get_trust_tier(0.90) == "Verified High Trust"

def test_trust_tier_moderate():
    assert get_trust_tier(0.70) == "Moderate Trust"

def test_trust_tier_review():
    assert get_trust_tier(0.55) == "Low Trust — Review Recommended"

def test_trust_tier_exclude():
    assert get_trust_tier(0.30) == "Untrusted — Exclude from AI Pipeline"


# ── score_author_credibility ──────────────────────────────────────────────────

def test_author_pubmed_high():
    score, _ = score_author_credibility("Jane Smith", "pubmed.ncbi.nlm.nih.gov", "pubmed")
    assert score >= 0.85

def test_author_unknown_low():
    score, _ = score_author_credibility(None, "example.com", "blog")
    assert score <= 0.15

def test_author_md_high():
    score, _ = score_author_credibility("Dr. Emily Jones MD", "healthline.com", "blog")
    assert score >= 0.80

def test_author_md_low_domain_mismatch():
    score, _ = score_author_credibility("Dr. John PhD", "blogspot.com", "blog")
    assert score < 0.65


# ── score_domain_authority ────────────────────────────────────────────────────

def test_domain_pubmed():
    score, _ = score_domain_authority("pubmed.ncbi.nlm.nih.gov", "pubmed")
    assert score == 1.0

def test_domain_high():
    score, _ = score_domain_authority("nih.gov", "blog")
    assert score >= 0.90

def test_domain_low():
    score, _ = score_domain_authority("blogspot.com", "blog")
    assert score <= 0.30

def test_domain_unknown():
    score, _ = score_domain_authority("randomhealthblog.net", "blog")
    assert 0.30 <= score <= 0.60


# ── score_recency ─────────────────────────────────────────────────────────────

def test_recency_recent():
    # 30 days ago — always within 180-day window
    from datetime import datetime, timezone, timedelta
    recent = (datetime.now(timezone.utc) - timedelta(days=30)).strftime("%Y-%m-%d")
    score, conf, _ = score_recency(recent)
    assert score >= 0.80
    assert conf >= 0.90

def test_recency_old():
    score, conf, _ = score_recency("2015-01-01")
    assert score <= 0.15

def test_recency_none():
    score, conf, _ = score_recency(None)
    assert conf <= 0.60

def test_recency_two_years():
    # 550 days ago — always in the 1–2 year bucket
    from datetime import datetime, timezone, timedelta
    two_years_ago = (datetime.now(timezone.utc) - timedelta(days=550)).strftime("%Y-%m-%d")
    score, conf, _ = score_recency(two_years_ago)
    assert 0.50 <= score <= 0.80


# ── score_medical_disclaimer ──────────────────────────────────────────────────

def test_disclaimer_present():
    content = "This article is for informational purposes only. Always consult a doctor."
    score, _ = score_medical_disclaimer(content)
    assert score == 1.0

def test_disclaimer_absent():
    content = "Eat this and your gut will be healed. Guaranteed results."
    score, _ = score_medical_disclaimer(content)
    assert score == 0.0


# ── detect_abuse_flags ────────────────────────────────────────────────────────

def test_flag_outdated():
    flags = detect_abuse_flags(
        author="Someone",
        domain="example.com",
        content="Health content without disclaimer.",
        published_date="2015-01-01",
        source_type="blog",
    )
    assert "outdated_medical_content" in flags

def test_flag_no_disclaimer():
    flags = detect_abuse_flags(
        author="Dr. Jane",
        domain="healthline.com",
        content="Lose weight fast with this miracle cure.",
        published_date="2024-06-01",
        source_type="blog",
    )
    assert "no_medical_disclaimer" in flags

def test_flag_seo_spam():
    content = " ".join(["weight loss lose weight fast miracle cure weight loss"] * 40)
    flags = detect_abuse_flags(
        author="Author",
        domain="example.com",
        content=content,
        published_date="2024-01-01",
        source_type="blog",
    )
    assert "seo_spam_detected" in flags

def test_flag_transcript_unavailable():
    flags = detect_abuse_flags(
        author="Channel",
        domain="youtube.com",
        content="Short video description.",
        published_date="2024-06-01",
        source_type="youtube",
        transcript_available=False,
    )
    assert "transcript_unavailable_description_used" in flags


# ── full calculate_trust_score ────────────────────────────────────────────────

def test_full_score_pubmed():
    result = calculate_trust_score(
        source_url="https://pubmed.ncbi.nlm.nih.gov/12345678/",
        source_type="pubmed",
        author="Dr. Alice Chen MD; Prof. Bob Kumar PhD",
        published_date="2024-03-15",
        content="This study examines the gut microbiome. This is for informational purposes only.",
        domain="pubmed.ncbi.nlm.nih.gov",
        citation_count=45,
    )
    assert result["trust_score"] >= 0.75
    assert result["trust_tier"] in ("Verified High Trust", "Moderate Trust")
    assert "score_breakdown" in result
    assert "score_reasoning" in result
    assert isinstance(result["abuse_flags"], list)

def test_full_score_low_trust_blog():
    result = calculate_trust_score(
        source_url="https://mysupercures.blogspot.com/post",
        source_type="blog",
        author=None,
        published_date="2014-01-01",
        content="Weight loss miracle cure. Lose weight fast. No medical advice given.",
        domain="blogspot.com",
        citation_count=0,
    )
    assert result["trust_score"] <= 0.50
    assert "outdated_medical_content" in result["abuse_flags"]

def test_pipeline_version_in_result():
    result = calculate_trust_score(
        source_url="https://example.com/article",
        source_type="blog",
        author="Jane",
        published_date="2024-01-01",
        content="Health article content here.",
        domain="example.com",
    )
    assert result["pipeline_version"] == "v1.0"
