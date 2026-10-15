"""Verification script for Stage 2: Research Ingestion & Relevance Scoring with Instagram Viability Rubric."""

import argparse
import sys
from pathlib import Path

# Add project root to sys.path
BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from core.db import get_db_session
from core.logger import logfire, logger
from pipeline.ingest import ingest_feeds
from pipeline.triage import score_pending_items


def verify_stage_2(tenant_id: str = "v_personal", limit: int = 6, reset: bool = False) -> bool:
    """Execute Stage 2 ingestion and local triage verification using the Instagram Viability Rubric."""
    with logfire.span("stage_2_verification", tenant=tenant_id, limit=limit, reset=reset):
        logger.info(
            f"Starting Stage 2 verification for tenant '{tenant_id}' (limit={limit}, reset={reset})."
        )

        # 1. Deterministic RSS Feed Ingestion (with optional database reset)
        print(f"\n--- Ingesting Feeds for Tenant '{tenant_id}' (reset={reset}) ---")
        new_items_count = ingest_feeds(tenant_id, reset=reset)
        print(f"New items fetched & ingested: {new_items_count}")

        # 2. Local Relevance Triage via Ollama using the Instagram Viability Rubric
        print(f"\n--- Scoring Up To {limit} Balanced Pending Items (Ollama: llama3.1:8b-instruct-q4_K_M) ---")
        scored_count = score_pending_items(tenant_id, limit=limit, balanced=True)
        print(f"Items scored in this run: {scored_count}")

        # 3. Query Scored Items from SQLite
        print(f"\n--- Evaluated Items with Instagram Viability Rubric ({tenant_id}) ---")
        with get_db_session(tenant_id) as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT relevance_score, matched_pillar, one_line_angle, title, url, processed
                FROM research_items
                WHERE processed = 1
                ORDER BY relevance_score DESC, created_at DESC
                LIMIT ?
                """,
                (limit,),
            )
            scored_items = cursor.fetchall()

        if not scored_items:
            raise RuntimeError(f"No processed research items found in database for tenant '{tenant_id}'!")

        for rank, item in enumerate(scored_items, start=1):
            score = item["relevance_score"]
            pillar = item["matched_pillar"] or "None"
            angle = item["one_line_angle"] or "N/A"
            title = item["title"]
            url = item["url"]
            processed = item["processed"]

            # Assertions
            assert score >= 0.0, f"Expected relevance_score >= 0.0, got {score}"
            assert processed == 1, f"Expected processed == 1, got {processed}"

            tier = "HIGH" if score >= 0.7 else ("MED" if score >= 0.4 else "LOW")
            print(f"\n[{rank}] [{tier} - Score: {score:.2f}] [{pillar}] {title}")
            print(f"    Angle / Rationale: {angle}")
            print(f"    Source:            {url}")

        print("\n=======================================================")
        print("[OK] Stage 2 Ingestion & Local Triage Verified Successfully.")
        print("=======================================================\n")
        return True


def main():
    parser = argparse.ArgumentParser(description="Verify Stage 2 Ingestion & Rubric-Based Triage")
    parser.add_argument("--tenant", type=str, default="v_personal", help="Tenant ID (default: v_personal)")
    parser.add_argument("--limit", type=int, default=6, help="Number of pending items to score (default: 6)")
    parser.add_argument(
        "--reset",
        action="store_true",
        default=False,
        help="Clear old research items and re-seed from fresh feeds",
    )
    args = parser.parse_args()

    try:
        success = verify_stage_2(tenant_id=args.tenant, limit=args.limit, reset=args.reset)
        sys.exit(0 if success else 1)
    except Exception as exc:
        logger.error(f"[FAILED] Stage 2 verification failed: {exc}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
