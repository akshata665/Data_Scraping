#  AI Content SCRAPING Intelligence Pipeline

> **"A production-grade multi-source content ingestion and trust scoring pipeline designed for AI-driven healthcare applications. Built to ensure only reliable, recent, and medically sound content enters downstream AI systems."**

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                    SOURCE LAYER (Stage 1)                        │
│  ┌─────────────┐   ┌─────────────┐   ┌─────────────────────┐   │
│  │  PubMed API │   │  Blog HTML  │   │  YouTube API +      │   │
│  │  (NCBI REST)│   │  Scraper    │   │  Transcript API     │   │
│  └──────┬──────┘   └──────┬──────┘   └──────────┬──────────┘   │
└─────────┼─────────────────┼─────────────────────┼──────────────┘
          │                 │                     │
          ▼                 ▼                     ▼
┌─────────────────────────────────────────────────────────────────┐
│               METADATA ENRICHMENT (Stage 2)                      │
│   Language Detection │ Region Inference │ Topic Tagging          │
│   Ingestion Timestamp │ Content Chunking │ Reference Counting     │
└────────────────────────────────┬────────────────────────────────┘
                                 │
                                 ▼
┌─────────────────────────────────────────────────────────────────┐
│                 TRUST SCORING ENGINE (Stage 3)                   │
│                                                                   │
│   Author Credibility  ×0.30  ──┐                                 │
│   Citation Count      ×0.20  ──┤                                 │
│   Domain Authority    ×0.20  ──┼──▶  Trust Score (0.0–1.0)      │
│   Recency             ×0.20  ──┤     Confidence Score            │
│   Medical Disclaimer  ×0.10  ──┘     Score Reasoning (plain EN)  │
│                                      Abuse Flags                  │
│                                      Trust Tier Label             │
└────────────────────────────────┬────────────────────────────────┘
                                 │
                                 ▼
┌─────────────────────────────────────────────────────────────────┐
│                     OUTPUT LAYER (Stage 4)                       │
│  pubmed_results.json │ blog_results.json │ youtube_results.json  │
│  master_output.json  │ pipeline_report.json                      │
└─────────────────────────────────────────────────────────────────┘
```

---

## Quickstart

```bash
# 1. Clone and enter project
git clone <repo-url>
cd gutbut_pipeline

# 2. Install dependencies
pip install -r requirements.txt

# 3. (Optional) Set YouTube API key
export YOUTUBE_API_KEY="your_api_key_here"

# 4. Run the full pipeline
python main.py

# Run individual scrapers
python main.py --pubmed-only
python main.py --blog-only
python main.py --youtube-only

# 5. (Optional) Start the REST API
uvicorn api:app --reload --port 8000

# 6. Run tests
python -m pytest tests/ -v
```

---

## Project Structure

```
gutbut_pipeline/
├── main.py                    # Pipeline runner + report generator
├── api.py                     # FastAPI REST endpoints
├── requirements.txt
├── sample_urls.yaml           # Edit source URLs here
│
├── scrapers/
│   ├── pubmed_scraper.py      # NCBI REST API ingestion
│   ├── blog_scraper.py        # HTML scraping with fallbacks
│   └── youtube_scraper.py     # API + transcript extraction
│
├── trust_engine/
│   └── scorer.py              # Weighted trust scoring + abuse detection
│
├── utils/
│   └── helpers.py             # Language, region, chunking, tagging
│
├── tests/
│   └── test_trust_engine.py   # 20+ unit tests
│
└── output/                    # All generated JSON files
    ├── pubmed_results.json
    ├── blog_results.json
    ├── youtube_results.json
    ├── master_output.json
    └── pipeline_report.json
```

---

## JSON Output Schema

Every source produces this unified structure regardless of origin:

```json
{
  "source_url":          "https://pubmed.ncbi.nlm.nih.gov/38234567/",
  "source_type":         "pubmed",
  "source_title":        "The gut microbiome modulates brain function...",
  "author":              "Chen A; Kumar R; Williams S",
  "published_date":      "2024-02-01",
  "ingestion_timestamp": "2025-08-15T10:32:14+00:00",
  "language":            "en",
  "region":              "United States / Global",
  "topic_tags":          ["gut_health", "mental_health", "immunity"],

  "trust_score":         0.876,
  "trust_tier":          "Verified High Trust",
  "confidence_score":    0.92,

  "score_breakdown": {
    "author_credibility": {"score": 0.90, "weight": 0.30, "weighted": 0.27},
    "citation_count":     {"score": 0.75, "weight": 0.20, "weighted": 0.15},
    "domain_authority":   {"score": 1.00, "weight": 0.20, "weighted": 0.20},
    "recency":            {"score": 1.00, "weight": 0.20, "weighted": 0.20},
    "medical_disclaimer": {"score": 0.00, "weight": 0.10, "weighted": 0.00}
  },

  "score_reasoning": [
    "PubMed source — author associated with peer-reviewed publication.",
    "Article has 12 citations — moderately referenced.",
    "PubMed source automatically receives maximum domain authority baseline.",
    "Content published within the last 6 months — full recency score applied.",
    "No medical disclaimer detected — disclaimer component penalized."
  ],

  "abuse_flags":     ["no_medical_disclaimer"],
  "content_chunks":  ["The gut microbiome modulates..."],
  "processing_status": "success",
  "pipeline_version":  "v1.0"
}
```

---

## Trust Scoring Engine

### The Formula

```
Trust Score = 0.30 × author_credibility
            + 0.20 × citation_count
            + 0.20 × domain_authority
            + 0.20 × recency
            + 0.10 × medical_disclaimer_presence
```

### Weight Reasoning

| Component | Weight | Why This Weight |
|-----------|--------|-----------------|
| **Author Credibility** | 30% | In healthcare AI, an anonymous or unverified author is the single highest risk factor. Polished content from an unknown source is more dangerous than a rough article from a verified MD — users trust aesthetics over substance. |
| **Citation Count** | 20% | External validation. A source that other researchers cite has passed a form of peer review. |
| **Domain Authority** | 20% | Platforms with established reputations have editorial standards to protect. |
| **Recency** | 20% | Medical information decays. A 2019 COVID treatment article isn't just outdated — it's potentially harmful. Recency is a safety factor, not just a quality signal. |
| **Medical Disclaimer** | 10% | Absence is a red flag, but presence alone doesn't confer trustworthiness. It's a compliance signal, not a quality signal. |

### Trust Tier Labels

| Score Range | Tier | Action |
|-------------|------|--------|
| 0.85 – 1.00 | ✅ **Verified High Trust** | Include in AI pipeline |
| 0.65 – 0.84 | 🟡 **Moderate Trust** | Include with monitoring |
| 0.45 – 0.64 | 🟠 **Low Trust — Review Recommended** | Human review before inclusion |
| 0.00 – 0.44 | 🔴 **Untrusted — Exclude from AI Pipeline** | Automatic exclusion |

### Confidence Score (Separate from Trust Score)

The trust score answers: *"How reliable is this content?"*
The confidence score answers: *"How reliable is our trust score?"*

These are different questions. A trust score of 0.75 with confidence 0.45 means:
> "We think this is moderately trustworthy — but we're not very sure because key signals were missing."

A trust score of 0.75 with confidence 0.92 means:
> "We're confident this is moderately trustworthy."

Confidence is automatically reduced when:
- No author is listed
- No publication date is found
- YouTube transcript was unavailable (description used instead)

---

## Abuse Detection System

The pipeline detects six categories of content manipulation:

| Flag | Detection Method |
|------|-----------------|
| `credential_domain_mismatch` | Medical credentials claimed on low-authority domain (e.g., "Dr. John MD" on blogspot.com) |
| `seo_spam_detected` | Health keyword density exceeds 3% of total word count |
| `outdated_medical_content` | Content older than 5 years — triggers hard exclusion flag |
| `no_medical_disclaimer` | No disclaimer language found in medical content |
| `transcript_unavailable_description_used` | YouTube fallback activated — confidence reduced |
| `known_misinformation_adjacent_domain` | Domain matches known penalty list |

---

## Domain Authority Tiers

| Tier | Examples | Default Score |
|------|----------|---------------|
| **Maximum** | pubmed.ncbi.nlm.nih.gov, nih.gov, cdc.gov, who.int, nejm.org, thelancet.com | 1.00 |
| **High** | mayoclinic.org, healthline.com, webmd.com, medicalnewstoday.com | 0.95 |
| **Medium** | health.harvard.edu, verywellhealth.com, medscape.com | 0.70 |
| **Neutral** | Unknown domains | 0.45 |
| **Penalized** | blogspot.com, wordpress.com, tumblr.com | 0.25 |
| **Flagged** | Known misinformation-adjacent platforms | 0.10 |

---

## Graceful Degradation Design

The pipeline never crashes on a single source failure. Here's what happens when things go wrong:

| Failure Scenario | System Response |
|------------------|-----------------|
| Blog site blocks scraper | Log failure → skip source → continue pipeline |
| YouTube transcript unavailable | Use description as fallback → reduce confidence score → add abuse flag |
| PubMed API rate limited | Log error → skip PMID → continue with next query |
| Missing author on any source | Credibility score penalized → confidence reduced |
| Missing publication date | Recency defaults to 0.30 → confidence reduced |
| Invalid YouTube URL | Record flagged with `invalid_url` status → pipeline continues |

---

## Pipeline Health Report

After every run, `output/pipeline_report.json` is generated:

```json
{
  "pipeline_version": "v1.0",
  "report_generated_at": "2025-08-15T10:36:00+00:00",
  "elapsed_seconds": 18.42,
  "total_sources_scraped": 9,
  "successful": 9,
  "failed": 0,
  "fallback_used": 1,
  "sources_with_abuse_flags": 3,
  "average_trust_score": 0.7214,
  "average_confidence_score": 0.856,
  "trust_tier_distribution": {
    "Verified High Trust": 3,
    "Moderate Trust": 4,
    "Low Trust — Review Recommended": 2
  },
  "average_trust_by_source_type": {
    "pubmed": 0.871,
    "blog": 0.703,
    "youtube": 0.591
  },
  "best_performing_source_type": "pubmed",
  "source_diversity_score": 0.78
}
```

---

## REST API (FastAPI)

```bash
uvicorn api:app --reload --port 8000
# Docs at: http://localhost:8000/docs
```

### Endpoints

**POST /scrape** — Scrape any URL (auto-detects type)
```json
{"url": "https://pubmed.ncbi.nlm.nih.gov/38234567/"}
```

**POST /score** — Score raw content directly
```json
{
  "source_url": "https://example.com/article",
  "source_type": "blog",
  "author": "Dr. Jane Smith MD",
  "published_date": "2024-06-01",
  "content": "Your article text here...",
  "citation_count": 5
}
```

**GET /pipeline-report** — Return most recent pipeline report

---

## Design Decisions

### Why PubMed uses a separate ingestion strategy
PubMed has an official REST API (NCBI eutils) designed for programmatic access. Using it instead of HTML scraping means structured data, reliable metadata fields, and no risk of breaking on layout changes. This is the correct approach for any serious health AI system.

### Why confidence score is separate from trust score
A numeric trust score without a reliability indicator is misleading. Two sources can both score 0.70 — one because all signals are strong and converge on that score, and another because half the signals are missing and the system is guessing. The confidence score makes this distinction explicit and allows downstream RAG systems to apply different inclusion thresholds based on how much they trust the scoring itself.

### Why recency gets 20% weight (same as domain authority)
In general content systems, a 3-year-old article from a reputable source is still reliable. In health AI, it isn't — treatment guidelines change, drug recommendations are updated, and epidemiological data evolves. Giving recency equal weight to domain authority reflects this reality.

---

## Limitations & Future Improvements

**Current limitations:**
- Citation count for PubMed articles uses a placeholder (NCBI eutils doesn't expose this easily — the full count requires NIH iCite API integration)
- YouTube API key is optional; metadata quality degrades without it
- Language detection may be inaccurate for very short content

**Next improvements:**
- Integrate NIH iCite API for real citation counts
- Add content freshness decay curves (domain-specific decay rates)
- Cross-source claim consistency check for corroboration scoring
- Semantic deduplication across scraped sources
- Vector embedding pipeline integration (Pinecone/Chroma)

---

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `YOUTUBE_API_KEY` | Optional | YouTube Data API v3 key for full metadata. Falls back to page scraping without it. |

---

## Running Tests

```bash
python -m pytest tests/ -v
# Expected: 20+ tests, all passing
```

---

*Built as a prototype data layer for GutBut — an AI-driven health intelligence platform.*
