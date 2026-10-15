"""Deterministic RSS feed ingestion engine for Marketing OS."""

import calendar
import html
import re
import time
from typing import Any, List, Optional, Union
import feedparser
import requests

from core.config import load_brand_config
from core.db import clear_research_items, get_db_session, init_db
from core.logger import logfire, logger

USER_AGENT = "macos:marketing-agent:v1.0 (by /u/app_dev)"

FEED_FALLBACK_MAP = {
    "https://www.sciencedaily.com/rss/health_physical_therapy.xml": (
        "https://www.sciencedaily.com/rss/health_medicine/fitness.xml"
    ),
}


def clean_html(text: Optional[str]) -> str:
    """Strip HTML tags and unescape entities to return clean text."""
    if not text:
        return ""
    unescaped = html.unescape(text)
    stripped = re.sub(r"<[^>]+>", " ", unescaped)
    return " ".join(stripped.split())


def extract_feed_urls(sources: Union[List[Any], dict]) -> List[str]:
    """Extract list of feed URLs from the brand sources configuration."""
    urls = []
    if isinstance(sources, list):
        for item in sources:
            if isinstance(item, str):
                urls.append(item.strip())
            elif isinstance(item, dict) and "url" in item:
                urls.append(item["url"].strip())
    elif isinstance(sources, dict):
        for val in sources.values():
            if isinstance(val, list):
                urls.extend(extract_feed_urls(val))
            elif isinstance(val, str):
                urls.append(val.strip())
    return [u for u in urls if u.startswith("http")]


def ingest_feeds(tenant_id: str = "v_personal", reset: bool = False) -> int:
    """Fetch RSS feeds for a given tenant, deduplicate by URL, and insert into research_items.

    If reset=True, clears existing research items first to purge obsolete records.
    """
    with logfire.span("ingest_sources", tenant=tenant_id, reset=reset) as span:
        init_db(tenant_id)

        if reset:
            cleared_count = clear_research_items(tenant_id)
            logger.info(f"Reset flag active: cleared {cleared_count} old research items.")

        brand_config = load_brand_config(tenant_id)
        feed_urls = extract_feed_urls(brand_config.sources)

        logger.info(
            f"Starting feed ingestion for tenant '{tenant_id}' across {len(feed_urls)} configured sources."
        )

        total_inserted = 0
        total_fetched = 0

        headers = {"User-Agent": "macos:marketing-agent:v1.0 (by /u/app_dev)"}

        for url in feed_urls:
            target_url = url
            is_reddit = "reddit.com" in target_url

            if is_reddit:
                time.sleep(2.0)  # Polite 2-second sleep for Reddit rate limits

            try:
                response = requests.get(target_url, headers=headers, timeout=12)

                # Fallback for redirected/moved feeds
                if response.status_code != 200 and target_url in FEED_FALLBACK_MAP:
                    alt_url = FEED_FALLBACK_MAP[target_url]
                    logger.info(
                        f"Target '{target_url}' returned HTTP {response.status_code}. Trying alias '{alt_url}'."
                    )
                    response = requests.get(alt_url, headers=headers, timeout=12)
                    if response.status_code == 200:
                        target_url = alt_url

                if response.status_code == 429:
                    try:
                        reset_time = int(
                            response.headers.get("x-ratelimit-reset")
                            or response.headers.get("retry-after")
                            or 2
                        )
                    except (ValueError, TypeError):
                        reset_time = 2

                    if reset_time <= 2:
                        time.sleep(reset_time + 0.5)
                        response = requests.get(target_url, headers=headers, timeout=12)

                if response.status_code != 200:
                    logger.warning(
                        f"Skipping feed '{target_url}': HTTP {response.status_code} ({response.reason or 'Non-200 response'})"
                    )
                    continue

                feed = feedparser.parse(response.content)

                entries = feed.entries or []
                total_fetched += len(entries)
                logger.debug(f"Feed '{target_url}' parsed {len(entries)} entries.")

                with get_db_session(tenant_id) as conn:
                    cursor = conn.cursor()
                    for entry in entries:
                        title = clean_html(entry.get("title", ""))
                        link = (entry.get("link") or "").strip()
                        if not link or not title:
                            continue

                        # Inspect publication date (skip items older than 60 days)
                        published_parsed = entry.get("published_parsed") or entry.get("updated_parsed")
                        if published_parsed:
                            try:
                                pub_ts = calendar.timegm(published_parsed)
                                if (time.time() - pub_ts) > (60 * 86400):
                                    logger.debug(f"Skipping stale article (>60 days old): {title}")
                                    continue
                            except (TypeError, ValueError, OverflowError):
                                pass

                        raw_summary = (
                            entry.get("summary")
                            or entry.get("description")
                            or (
                                entry.get("content", [{}])[0].get("value")
                                if entry.get("content")
                                else ""
                            )
                            or title
                        )
                        raw_text = clean_html(raw_summary)

                        cursor.execute(
                            """
                            INSERT OR IGNORE INTO research_items (source_type, title, url, raw_text)
                            VALUES (?, ?, ?, ?)
                            """,
                            (target_url, title, link, raw_text),
                        )
                        if cursor.rowcount > 0:
                            total_inserted += 1

            except requests.exceptions.Timeout:
                logger.warning(
                    f"Timeout fetching feed '{target_url}' after 12s. Skipping feed."
                )
            except requests.exceptions.RequestException as req_err:
                logger.warning(
                    f"Network error fetching feed '{target_url}': {req_err}. Skipping feed."
                )
            except Exception as exc:
                logger.warning(f"Error ingesting feed '{target_url}': {exc}")

        span.set_attribute("total_sources", len(feed_urls))
        span.set_attribute("total_fetched", total_fetched)
        span.set_attribute("total_inserted", total_inserted)

        logger.info(
            f"Ingestion complete for tenant '{tenant_id}': "
            f"{total_inserted} new items ingested ({total_fetched} total parsed)."
        )
        return total_inserted
