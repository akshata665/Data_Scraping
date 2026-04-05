"""
GutBut AI Content Intelligence Pipeline
========================================
Hybrid pipeline:
1) Manual source mode via sample_urls.yaml
2) Topic preset mode via topic_presets.yaml
3) Dynamic fallback mode for unseen topics
"""

import json
import logging
import argparse
from datetime import datetime, timezone
from pathlib import Path
import yaml

from scrapers import scrape_pubmed, scrape_blog, scrape_youtube

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("pipeline")

OUTPUT_DIR = Path("output")
OUTPUT_DIR.mkdir(exist_ok=True)

PIPELINE_VERSION = "v2.0"
CONFIG_FILE = Path("sample_urls.yaml")
TOPIC_FILE = Path("topic_presets.yaml")


# ─────────────────────────────────────────────────────────────
# YAML LOADERS
# ─────────────────────────────────────────────────────────────
def load_config():
    if not CONFIG_FILE.exists():
        raise FileNotFoundError(f"{CONFIG_FILE} not found")

    with open(CONFIG_FILE, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)

    return {
        "pubmed_queries": config.get("pubmed_queries", []),
        "blog_urls": config.get("blog_urls", []),
        "youtube_urls": config.get("youtube_urls", []),
    }


def load_topic_presets():
    if not TOPIC_FILE.exists():
        return {}

    with open(TOPIC_FILE, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    return data.get("topics", {})


# ─────────────────────────────────────────────────────────────
# HYBRID SOURCE GENERATION
# ─────────────────────────────────────────────────────────────
def generate_dynamic_sources(topic: str):
    topic = topic.lower().strip()
    presets = load_topic_presets()

    if topic in presets:
        logger.info(f"Using preset topic sources for: {topic}")
        return presets[topic]

    logger.info(f"Topic '{topic}' not found in presets → auto-generating sources")

    topic_slug = topic.replace(" ", "_")
    topic_plus = topic.replace(" ", "+")
    topic_hyphen = topic.replace(" ", "-")

    blog_urls = [
        f"https://en.wikipedia.org/wiki/{topic_slug}",
        f"https://www.britannica.com/search?query={topic_plus}",
        f"https://www.khanacademy.org/search?page_search_query={topic_plus}",
        f"https://www.coursera.org/search?query={topic_plus}",
        f"https://www.ibm.com/search?query={topic_plus}",
        f"https://www.geeksforgeeks.org/{topic_hyphen}/",
        f"https://ourworldindata.org/search?q={topic_plus}",
    ]

    youtube_keywords = [
        f"https://www.youtube.com/results?search_query={topic_plus}+explained",
        f"https://www.youtube.com/results?search_query={topic_plus}+tutorial",
        f"https://www.youtube.com/results?search_query={topic_plus}+beginner+guide",
        f"https://www.youtube.com/results?search_query={topic_plus}+advanced+concepts",
        f"https://www.youtube.com/results?search_query={topic_plus}+research+overview",
        f"https://www.youtube.com/results?search_query={topic_plus}+real+world+applications",
        f"https://www.youtube.com/results?search_query={topic_plus}+case+study",
    ]

    pubmed_queries = [
        f"{topic} review",
        f"{topic} case study",
        f"{topic} systematic analysis",
        f"{topic} research paper",
        f"{topic} recent advances",
        f"{topic} practical applications",
        f"{topic} latest trends",
    ]

    return {
        "pubmed_queries": pubmed_queries,
        "blog_urls": blog_urls,
        "youtube_urls": youtube_keywords,
    }


# ─────────────────────────────────────────────────────────────
# REPORT GENERATION
# ─────────────────────────────────────────────────────────────
def generate_pipeline_report(all_results: list[dict], elapsed_seconds: float) -> dict:
    total = len(all_results)
    if total == 0:
        return {"error": "No results to report."}

    scores = [r["trust_score"] for r in all_results if "trust_score" in r]
    confidence = [r["confidence_score"] for r in all_results if "confidence_score" in r]
    flagged = [r for r in all_results if r.get("abuse_flags")]
    failed = [r for r in all_results if "fetch_failed" in r.get("processing_status", "")]

    by_type = {}
    for r in all_results:
        st = r.get("source_type", "unknown")
        by_type.setdefault(st, []).append(r.get("trust_score", 0))

    type_averages = {k: round(sum(v) / len(v), 4) for k, v in by_type.items()}
    best_type = max(type_averages, key=type_averages.get) if type_averages else "n/a"

    return {
        "pipeline_version": PIPELINE_VERSION,
        "report_generated_at": datetime.now(timezone.utc).isoformat(),
        "elapsed_seconds": round(elapsed_seconds, 2),
        "total_sources_scraped": total,
        "successful": total - len(failed),
        "failed": len(failed),
        "sources_with_abuse_flags": len(flagged),
        "average_trust_score": round(sum(scores) / len(scores), 4) if scores else 0,
        "average_confidence_score": round(sum(confidence) / len(confidence), 4) if confidence else 0,
        "average_trust_by_source_type": type_averages,
        "best_performing_source_type": best_type,
    }


# ─────────────────────────────────────────────────────────────
# SAVE JSON
# ─────────────────────────────────────────────────────────────
def save_json(data, path: Path):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    logger.info(f"Saved: {path}")


# ─────────────────────────────────────────────────────────────
# MAIN PIPELINE
# ─────────────────────────────────────────────────────────────
def run_pipeline(run_pubmed=True, run_blog=True, run_youtube=True, topic=None):
    config = generate_dynamic_sources(topic) if topic else load_config()

    start = datetime.now(timezone.utc)
    logger.info("=" * 60)
    logger.info("GutBut AI Content Intelligence Pipeline — Starting")
    logger.info(f"Pipeline Version: {PIPELINE_VERSION}")
    logger.info("=" * 60)

    all_results = []

    if run_pubmed and config["pubmed_queries"]:
        logger.info("\n[Stage 1] PubMed Scraper")
        pubmed_results = scrape_pubmed(config["pubmed_queries"], max_per_query=3)
        save_json(pubmed_results, OUTPUT_DIR / "pubmed_results.json")
        all_results.extend(pubmed_results)
        logger.info(f"  → {len(pubmed_results)} PubMed records ingested.")

    if run_blog and config["blog_urls"]:
        logger.info("\n[Stage 2] Blog Scraper")
        blog_results = scrape_blog(config["blog_urls"])
        save_json(blog_results, OUTPUT_DIR / "blog_results.json")
        all_results.extend(blog_results)
        logger.info(f"  → {len(blog_results)} blog records ingested.")

    if run_youtube and config["youtube_urls"]:
        logger.info("\n[Stage 3] YouTube Scraper")
        youtube_results = scrape_youtube(config["youtube_urls"])
        save_json(youtube_results, OUTPUT_DIR / "youtube_results.json")
        all_results.extend(youtube_results)
        logger.info(f"  → {len(youtube_results)} YouTube records ingested.")

    save_json(all_results, OUTPUT_DIR / "master_output.json")

    elapsed = (datetime.now(timezone.utc) - start).total_seconds()
    report = generate_pipeline_report(all_results, elapsed)
    save_json(report, OUTPUT_DIR / "pipeline_report.json")

    logger.info("\n" + "=" * 60)
    logger.info("PIPELINE COMPLETE — SUMMARY")
    logger.info("=" * 60)
    logger.info(f"  Total sources:     {report.get('total_sources_scraped', 0)}")
    logger.info(f"  Successful:        {report.get('successful', 0)}")
    logger.info(f"  Failed:            {report.get('failed', 0)}")
    logger.info(f"  Avg trust score:   {report.get('average_trust_score', 0)}")
    logger.info(f"  Avg confidence:    {report.get('average_confidence_score', 0)}")
    logger.info(f"  Best source type:  {report.get('best_performing_source_type', 'n/a')}")
    logger.info("=" * 60)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="GutBut Hybrid Pipeline")
    parser.add_argument("--pubmed-only", action="store_true")
    parser.add_argument("--blog-only", action="store_true")
    parser.add_argument("--youtube-only", action="store_true")
    parser.add_argument("--topic", type=str, help="Run using preset topic")
    args = parser.parse_args()

    if args.pubmed_only:
        run_pipeline(run_pubmed=True, run_blog=False, run_youtube=False, topic=args.topic)
    elif args.blog_only:
        run_pipeline(run_pubmed=False, run_blog=True, run_youtube=False, topic=args.topic)
    elif args.youtube_only:
        run_pipeline(run_pubmed=False, run_blog=False, run_youtube=True, topic=args.topic)
    else:
        run_pipeline(topic=args.topic)