"""Local relevance triage pipeline evaluating Instagram creator viability via Ollama."""

from core.db import get_db_session, init_db
from core.logger import logfire, logger
from core.router import call_llm
from core.schemas import LLMEngine, LLMTaskType

from urllib.parse import urlparse

TRIAGE_SYSTEM_PROMPT = """You are an editorial triage assistant for a fitness and tech Instagram creator.
CRITICAL RULE: The creator operates independent content tracks.
- Track A: 100% Fitness & Training
- Track B: 100% AI & Dev Tools
- Track C: 100% Build in Public

DO NOT penalize a tech post for not mentioning fitness.
DO NOT penalize a fitness post for not mentioning tech.
Score the item from 0.0 to 1.0 on Audience Alignment, Actionability, and Hook Potential for an Instagram Reel or Carousel.

High Score (0.7 - 1.0): Actionable lifting routines, hypertrophy science, recovery habits, practical AI developer tools, local models, or indie hacker build-in-public lessons.
Low Score (0.0 - 0.3): Academic clinical trials, disease treatments, corporate press releases, dense theoretical research with no practical takeaway.

TIMELINESS & EVERGREEN RULE:
- Never include outdated past years (e.g., 2024, 2025) in your generated hooks, angles, or titles.
- If an article discusses gym equipment, lifting mechanics, or developer principles with an outdated year in the title (e.g., "Best Smith Machine in 2025"), strip the year and extract the timeless, evergreen principle (e.g., "Smith Machine buying guide: cable ratios and footprint vs free barbell").
- If an item is purely obsolete past news (e.g., an announcement for an event or release from a past year that has no current utility), score it 0.0.

Return strictly JSON:
{
  "relevance": float,
  "matched_pillar": "Fitness & Training" | "AI & Dev Tools" | "Build in Public" | "None",
  "one_line_angle": "string"
}"""


def score_pending_items(
    tenant_id: str = "v_personal",
    limit: int = 10,
    balanced: bool = True,
) -> int:
    """Triage and score unprocessed research items locally using Ollama and the Instagram viability rubric."""
    with logfire.span("triage_batch", tenant=tenant_id, batch_size=limit, balanced=balanced) as span:
        init_db(tenant_id)

        with get_db_session(tenant_id) as conn:
            cursor = conn.cursor()
            if balanced:
                cursor.execute(
                    """
                    SELECT id, source_type, title, url, raw_text
                    FROM research_items
                    WHERE processed = 0
                    ORDER BY id ASC
                    """
                )
                all_pending = cursor.fetchall()
                if not all_pending:
                    rows = []
                else:
                    groups = {}
                    for item in all_pending:
                        st = (item["source_type"] or "").strip()
                        if st and st not in ("rss", "article"):
                            group_key = st
                        else:
                            u = item["url"] or ""
                            host = urlparse(u).netloc or "source"
                            if "reddit.com" in host and "/r/" in u:
                                sub = u.split("/r/")[1].split("/")[0]
                                host = f"reddit.com/r/{sub}"
                            group_key = host
                        groups.setdefault(group_key, []).append(item)

                    selected = []
                    while len(selected) < limit and any(groups.values()):
                        for key in list(groups.keys()):
                            if groups[key]:
                                selected.append(groups[key].pop(0))
                                if len(selected) >= limit:
                                    break
                    rows = selected
            else:
                cursor.execute(
                    """
                    SELECT id, source_type, title, url, raw_text
                    FROM research_items
                    WHERE processed = 0
                    ORDER BY created_at DESC
                    LIMIT ?
                    """,
                    (limit,),
                )
                rows = cursor.fetchall()

        if not rows:
            logger.info(f"No pending research items to score for tenant '{tenant_id}'.")
            span.set_attribute("items_scored", 0)
            return 0

        logger.info(
            f"Triaging batch of {len(rows)} pending items for tenant '{tenant_id}' using Instagram Viability Rubric."
        )

        scored_count = 0
        total_score = 0.0

        for row in rows:
            item_id = row["id"]
            title = row["title"] or ""
            raw_text = row["raw_text"] or ""

            user_prompt = f"Title: {title}\nSummary: {raw_text[:300]}"

            score = 0.0
            matched_pillar = "None"
            one_line_angle = "Default fallback"

            try:
                response = call_llm(
                    prompt=user_prompt,
                    system_prompt=TRIAGE_SYSTEM_PROMPT,
                    task_type=LLMTaskType.TRIAGE_SCORING,
                    json_mode=True,
                    force_engine=LLMEngine.LOCAL,
                )

                raw_json = response.raw_json or {}
                raw_score = raw_json.get("relevance", 0.0)
                try:
                    score = float(raw_score)
                except (ValueError, TypeError):
                    score = 0.0

                score = max(0.0, min(1.0, round(score, 2)))
                matched_pillar = str(raw_json.get("matched_pillar") or "None").strip()
                one_line_angle = str(
                    raw_json.get("one_line_angle")
                    or "No specific angle provided."
                ).strip()

            except Exception as exc:
                logger.warning(
                    f"Failed to score research item {item_id} ('{title[:30]}'): {exc}. Defaulting score to 0.0."
                )
                score = 0.0
                matched_pillar = "None"
                one_line_angle = f"Triage evaluation error: {exc}"

            with get_db_session(tenant_id) as conn:
                conn.execute(
                    """
                    UPDATE research_items
                    SET relevance_score = ?, matched_pillar = ?, one_line_angle = ?, processed = 1
                    WHERE id = ?
                    """,
                    (score, matched_pillar, one_line_angle, item_id),
                )

            scored_count += 1
            total_score += score
            logger.debug(
                f"Item {item_id} [{score:.2f}] [{matched_pillar}]: {one_line_angle}"
            )

        avg_score = round(total_score / scored_count, 3) if scored_count > 0 else 0.0
        span.set_attribute("items_scored", scored_count)
        span.set_attribute("average_relevance", avg_score)

        logger.info(
            f"Successfully scored {scored_count} items for tenant '{tenant_id}' (avg relevance: {avg_score})."
        )
        return scored_count
