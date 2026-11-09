"""Evaluate the real classifier on the hand-labelled set (PLAN Phase 3, §11.13).

    uv run python scripts/eval_classifier.py [--set tests/fixtures/eval_set.json] [--json out.json]

Makes one paid LLM call per item (about $0.01 for 40 items with a Haiku-class model). Never run
from the test suite. Predictions use the same prompt, schema, gate thresholds and pre-filter as
the pipeline, on title + feed description only (no extracted article text).

Reports, with the actual denominators:
- relevance (classifier + gate): confusion matrix, precision, recall, accuracy;
- end to end (pre-filter, then classifier + gate);
- primary-category accuracy on items labelled relevant (strict: same primary; lenient: the
  labelled category is among the predicted categories).
"""

import argparse
import json
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.ai.classify import (  # noqa: E402
    PROMPT_VERSION,
    CategoryRef,
    Prices,
    build_system_prompt,
    build_user_message,
    classify,
    prompt_hash,
)
from app.ai.llm import AnthropicLLM  # noqa: E402
from app.config import get_settings  # noqa: E402
from app.pipeline.nodes import (  # noqa: E402
    GENERAL_DC_VOCAB,
    gate,
    keyword_pattern,
    normalize_text,
    prefilter,
)
from app.seed import load_categories, load_sources  # noqa: E402

DEFAULT_SET = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "eval_set.json"


def pct(n: int, d: int) -> str:
    return f"{n}/{d} = {n / d:.1%}" if d else "n/a (0 denominator)"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--set", type=Path, default=DEFAULT_SET)
    parser.add_argument("--json", type=Path, help="also write per-item results here")
    args = parser.parse_args(argv)

    settings = get_settings()
    dataset = json.loads(args.set.read_text())
    cats = load_categories(settings.config_dir / "categories.yaml")
    dc_specific = {s.key: s.dc_specific for s in load_sources(settings.config_dir / "sources.yaml")}
    refs = [CategoryRef(c.slug, c.name, c.description) for c in cats]
    slugs = [c.slug for c in cats]
    system = build_system_prompt(refs)
    pattern = keyword_pattern([k for c in cats for k in c.keywords] + list(GENERAL_DC_VOCAB))
    prices = Prices(settings.classifier_input_usd_per_mtok, settings.classifier_output_usd_per_mtok)
    llm = AnthropicLLM(
        api_key=settings.anthropic_api_key,
        model=settings.classifier_model,
        effort=settings.classifier_effort,
        timeout_s=settings.llm_timeout_seconds,
    )

    def evaluate(item: dict[str, Any]) -> dict[str, Any]:
        title, text = normalize_text(item["title"]), normalize_text(item["description"])
        _, pre_reason = prefilter(
            pattern,
            title=title,
            text=text,
            source_tags=[],
            dc_specific=dc_specific.get(item["source"], False),
        )
        user = build_user_message(
            title=title,
            text=text,
            publisher=item["publisher"],
            source=item["source"],
            url=item["url"],
            published_at=item["published_at"],
            source_tags=[],
        )
        r = classify(llm, system=system, user=user, slugs=slugs, prices=prices)
        c = r.classification
        status, reason = gate(c, settings.relevance_threshold, settings.quality_threshold)
        return {
            "db_item_id": item["db_item_id"],
            "source": item["source"],
            "title": item["title"],
            "label": item["label"],
            "prefilter_reject": pre_reason,
            "predicted_relevant": status == "processed",
            "gate_reason": reason,
            "relevance_score": c.relevance_score,
            "quality_score": c.quality_score,
            "primary_category": c.primary_category,
            "categories": c.categories,
            "content_type": c.content_type,
            "summary": c.summary,
            "cost_usd": float(r.cost_usd),
            "tokens_in": r.tokens_in,
            "tokens_out": r.tokens_out,
            "attempts": r.attempts,
        }

    with ThreadPoolExecutor(settings.llm_concurrency) as pool:
        results = list(pool.map(evaluate, dataset["items"]))

    tp = sum(r["label"]["is_relevant"] and r["predicted_relevant"] for r in results)
    fp = sum(not r["label"]["is_relevant"] and r["predicted_relevant"] for r in results)
    fn = sum(r["label"]["is_relevant"] and not r["predicted_relevant"] for r in results)
    tn = len(results) - tp - fp - fn
    e2e = [r["predicted_relevant"] and not r["prefilter_reject"] for r in results]
    e_tp = sum(p and r["label"]["is_relevant"] for p, r in zip(e2e, results, strict=True))
    e_fp = sum(p and not r["label"]["is_relevant"] for p, r in zip(e2e, results, strict=True))
    e_fn = sum(not p and r["label"]["is_relevant"] for p, r in zip(e2e, results, strict=True))
    relevant = [r for r in results if r["label"]["is_relevant"]]
    strict = sum(r["primary_category"] == r["label"]["primary_category"] for r in relevant)
    lenient = sum(r["label"]["primary_category"] in r["categories"] for r in relevant)
    cost = sum(r["cost_usd"] for r in results)

    print(f"# Classifier evaluation: {dataset['version']}, {len(results)} items")
    print(f"model {llm.model} | prompt {PROMPT_VERSION} | prompt hash {prompt_hash(system)[:12]}")
    print(
        f"thresholds relevance >= {settings.relevance_threshold}, "
        f"quality >= {settings.quality_threshold} | effort {settings.classifier_effort or '-'}"
    )
    print("\n## Relevance (classifier + gate)")
    print("| | predicted relevant | predicted not relevant |\n|---|---|---|")
    print(f"| labelled relevant | {tp} (TP) | {fn} (FN) |")
    print(f"| labelled not relevant | {fp} (FP) | {tn} (TN) |")
    print(f"- precision {pct(tp, tp + fp)}\n- recall {pct(tp, tp + fn)}")
    print(f"- accuracy {pct(tp + tn, len(results))}")
    print("\n## End to end (pre-filter, then classifier + gate)")
    print(f"- precision {pct(e_tp, e_tp + e_fp)}\n- recall {pct(e_tp, e_tp + e_fn)}")
    print(f"- pre-filter rejected: {[r['db_item_id'] for r in results if r['prefilter_reject']]}")
    print("\n## Primary category (items labelled relevant)")
    print(f"- strict (same primary) {pct(strict, len(relevant))}")
    print(f"- lenient (label among predicted categories) {pct(lenient, len(relevant))}")
    print("\n## Disagreements")
    print("| item | source | label | predicted | rel | qual | category (label -> predicted) |")
    print("|---|---|---|---|---|---|---|")
    for r in results:
        lab = r["label"]
        wrong_rel = lab["is_relevant"] != r["predicted_relevant"]
        wrong_cat = lab["is_relevant"] and lab["primary_category"] != r["primary_category"]
        if wrong_rel or wrong_cat:
            print(
                f"| {r['db_item_id']} {r['title'][:60]} | {r['source']} | "
                f"{'rel' if lab['is_relevant'] else 'not'} | "
                f"{'rel' if r['predicted_relevant'] else 'not'} ({r['gate_reason'] or 'ok'}) | "
                f"{r['relevance_score']} | {r['quality_score']} | "
                f"{lab['primary_category'] or '-'} -> {r['primary_category']} |"
            )
    print(
        f"\ncost ${cost:.4f} | tokens in {sum(r['tokens_in'] for r in results)} "
        f"out {sum(r['tokens_out'] for r in results)} | "
        f"repair retries {sum(r['attempts'] > 1 for r in results)}"
    )
    if args.json:
        args.json.write_text(json.dumps(results, indent=2, ensure_ascii=False) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
