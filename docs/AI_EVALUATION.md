# AI Evaluation

Tracks: evaluation-set version, human-reviewed labels, model ID, prompt hash/version, sample size, confusion matrix, precision/recall, category accuracy, summary factuality review, citation validity, known limitations, and date run (PLAN §15).

## Classifier (Phase 3)

| | |
|---|---|
| Evaluation set | `backend/tests/fixtures/eval_set.json`, version `eval-v1`, **40 items** (20 labelled relevant, 20 not relevant) |
| What an item is | A real ingested item (title, feed description up to 600 chars, URL), drawn by seeded random sample from every source type: 18 Hacker News, 5 arXiv, 4 GitHub, 13 RSS (FT 5, DCD 4, DCK 2, SemiAnalysis 1, NYT 1) |
| Labels | By the agent (Claude Code) on 2026-11-09, **before** any item was classified. **Human review: done (2026-11-11); no labels changed.** |
| Gold "relevant" | A data center professional would want it in the feed (the item should be published) |
| Gold category | The agent's single best `primary_category`; several items fit two categories (see lenient score) |
| Script | `cd backend && uv run python scripts/eval_classifier.py` (40 paid calls, about $0.01). Not part of the test suite |
| Model | `claude-haiku-5-5`, `effort: low`, structured outputs, thresholds relevance ≥ 55 and quality ≥ 40 |
| Input | Title + feed description only. In the live pipeline, items with robots-permitted full text also send up to 4,000 chars of it |

### Results

| Run (2026-11-09) | Prompt | Prompt hash (rendered system prompt) | Precision | Recall | Accuracy | Primary category strict / lenient | Cost |
|---|---|---|---|---|---|---|---|
| 1 | `classify-v1` | `ef6b1d35cc6e…` | 15/15 = 100.0% | 15/20 = 75.0% | 35/40 = 87.5% | 16/20 = 80.0% / 18/20 = 90.0% | $0.0110 |
| 2 | `classify-v2` | `a4c89b2fc8e4…` | 20/22 = 90.9% | 20/20 = 100.0% | 38/40 = 95.0% | 16/20 = 80.0% / 18/20 = 90.0% | $0.0116 |

"Precision/recall" is for the classifier plus the gate (what gets published). End to end (keyword pre-filter first) gave the same numbers in both runs: the pre-filter rejected 5 items (3951, 101, 112, 116, 127), all labelled not relevant. No answer needed a repair retry.

Confusion matrix, run 2 (`classify-v2`, current):

| | predicted relevant | predicted not relevant |
|---|---|---|
| labelled relevant | 20 (TP) | 0 (FN) |
| labelled not relevant | 2 (FP) | 18 (TN) |

**Run 1 errors.** All 5 false negatives were Hacker News title-only items with high relevance (85–92) and quality 30–35, so the quality gate removed them: 828 (Minnesota $4B data center), 298 (DeepSeek / Huawei Ascend at a Mongolia DC), 650 (fire at NorthC data center), 194 (Texas permitting), 881 (Saudi Arabia / xAI data center deal). The cause was the v1 prompt's title-only rule (D-028).

**Run 2 errors.**
- False positives: 2214 "The Man Who Built NVIDIA [audio]" (relevance 55, quality 45) and 1809 "Perplexity Launches Portable Computer Agent Optimized for Nvidia DGX Spark" (62/40). Both are borderline: they just clear the thresholds.
- Category disagreements (relevance correct): 828 dc-infrastructure → site-selection, 650 security → dc-infrastructure, 3232 optimization → ai-compute-gpus, 5 security → dc-infrastructure. In 2 of the 4 the labelled category is among the predicted categories. Several are arguably label choices (an outage as "security" vs "infrastructure").

### Limitations (read before quoting these numbers)
- **40 items is a small sample.** One item moves precision or recall by about 5 points. This is a sanity check, not proof of production accuracy (§11.13).
- **Agent-labelled, not yet human-reviewed.** Labels are one reviewer's judgement.
- **Not held out.** Run 1's errors led to the v2 prompt change, measured on the same items (D-028), so run 2 is optimistic.
- **Easier than live traffic.** The agent left out candidates it found ambiguous (hn 962, 1731, 1798, 1830; github 3984, 4050).
- **Title + description only.** Summary factuality is not scored here; see the spot checks in VERIFICATION_LOG.md (Phase 3).

### Human review (done 2026-11-11)
Mark each label you agree with, or write your label in the last column. Then record the adjudicated result and re-run the script if any label changes.

| Item | Source | Title | Label | Category label | Predicted (v2) | Rel/Qual | Predicted category | Human verdict |
|---|---|---|---|---|---|---|---|---|
| 784 | hn | We're Measuring Data Center Sustainability Wrong | relevant | sustainability | relevant | 85/50 | sustainability | |
| 828 | hn | In Minnesota, a plan for a $4B data center takes root with renewables projects | relevant | dc-infrastructure | relevant | 90/50 | site-selection | |
| 298 | hn | DeepSeek to use 160K+ of Huawei's Ascend 950DT chips at a Mongolia data center | relevant | ai-compute-gpus | relevant | 85/50 | ai-compute-gpus | |
| 650 | hn | Fire at Dutch NorthC data center, all personnel evacuated in time | relevant | security | relevant | 92/45 | dc-infrastructure | |
| 830 | hn | AI Has Fueled $70B in Data Center M&A Talks This Year | relevant | economics-finance | relevant | 92/52 | economics-finance | |
| 1208 | hn | A Federal Regulator Wants to Fast-Track AI Data Centers onto the Power Grid | relevant | regulation | relevant | 90/50 | regulation | |
| 194 | hn | Texas Continued Data Center Permitting After the Governor's Pause | relevant | regulation | relevant | 72/45 | regulation | |
| 881 | hn | Saudi Arabia Backs Elon Musk's XAI with Data Center Deal | relevant | hyperscaler-investments | relevant | 75/45 | hyperscaler-investments | |
| 3394 | arxiv | Source Side Mitigation of AI Datacenter Power Fluctuations with a Hybrid Energy  | relevant | power-energy | relevant | 92/72 | power-energy | |
| 3290 | arxiv | Smart IoT-Based Leak Forecasting and Detection for Energy-Efficient Liquid Cooli | relevant | cooling | relevant | 93/68 | cooling | |
| 3232 | arxiv | The Energy Cost of Execution-Idle in GPU Clusters | relevant | optimization | relevant | 85/80 | ai-compute-gpus | |
| 3215 | arxiv | DataCenterGym: A Physics-Grounded Simulator for Multi-Objective Data Center Sche | relevant | optimization | relevant | 92/72 | optimization | |
| 3089 | arxiv | DC-CLM: Extending the WECC Composite Load Model for AI Data Center Dynamics | relevant | power-energy | relevant | 92/72 | power-energy | |
| 3895 | github | bitoftech/netbox-dc-digital-twin | relevant | optimization | relevant | 88/62 | optimization | |
| 124 | ft_tech | Anthropic strikes $3.4bn deal to generate gas-fired power for data centres | relevant | power-energy | relevant | 92/62 | power-energy | |
| 79 | semianalysis | The Chinese AI Infrastructure Boom: Introducing the SemiAnalysis China Datacente | relevant | dc-infrastructure | relevant | 92/72 | dc-infrastructure | |
| 64 | dck | How to Secure Data Centers During the Construction Phase | relevant | security | relevant | 88/62 | security | |
| 65 | dck | Virginia Tops AI Data Center Readiness Ranking as Smaller Markets Advance | relevant | site-selection | relevant | 92/62 | site-selection | |
| 6 | dcd | Your data center may be halfway to waterless | relevant | cooling | relevant | 90/55 | cooling | |
| 5 | dcd | Google's UK data center disruption caused by 'misconfiguration' of systems | relevant | security | relevant | 88/62 | dc-infrastructure | |
| 1395 | hn | Nvidia Board to Probe Spying Case After CEO Admits Affair | not | - | not | 10/25 | ai-compute-gpus | |
| 2104 | hn | Nvidia Maxwell Architecture | not | - | not | 25/25 | ai-compute-gpus | |
| 2129 | hn | Five giant hyperscalers–and Nvidia–share a surprising trait: female CFOs | not | - | not | 35/30 | hyperscaler-investments | |
| 2666 | hn | GPU Memory Allocation Bugs with Nvidia on Linux and Wayland Adventures | not | - | not | 15/25 | ai-compute-gpus | |
| 2221 | hn | Nvidia releases Nemotron 3 Nano Omni multimodal model | not | - | not | 35/40 | ai-agentic | |
| 2214 | hn | The Man Who Built NVIDIA [audio] | not | - | relevant | 55/45 | ai-compute-gpus | |
| 2400 | hn | Nvidia Is Planning to Launch an Open-Source AI Agent Platform | not | - | not | 42/45 | ai-agentic | |
| 1635 | hn | Nvidia AI Agent Safety Stack | not | - | not | 35/25 | security | |
| 1809 | hn | Perplexity Launches Portable Computer Agent Optimized for Nvidia DGX Spark | not | - | relevant | 62/40 | ai-compute-gpus | |
| 2593 | hn | AI Engineering: Pi 5 x K8s x Nvidia GPU passthrough [video] | not | - | not | 35/15 | ai-compute-gpus | |
| 3951 | github | kc4ums/rf_baseline_observer | not | - | not | 5/35 | emerging-tech | |
| 3809 | github | api-evangelist/power-lattice | not | - | not | 55/35 | power-energy | |
| 3832 | github | api-evangelist/frore-systems | not | - | not | 55/35 | cooling | |
| 101 | nyt_tech | Tech Billionaires Face Tricky Political Waters After Democratic Midterm Sweep | not | - | not | 10/55 | regulation | |
| 112 | ft_tech | US stocks set for gains after AI rout | not | - | not | 12/30 | economics-finance | |
| 116 | ft_tech | Mark Blyth: ‘I call it the barbell from hell’ | not | - | not | 20/30 | economics-finance | |
| 4556 | dcd | Vodafone Ireland targets 70% 5G Standalone coverage by 2028 | not | - | not | 20/40 | networking | |
| 126 | ft_tech | Is Europe getting serious about ending tech dependence? | not | - | not | 35/30 | regulation | |
| 127 | ft_tech | Apple saves $2.7bn in taxes by booking profits in Singapore | not | - | not | 5/40 | economics-finance | |
| 19 | dcd | Deutsche Telekom CEO welcomes SpaceX terrestrial challenge, warns it will cost M | not | - | not | 35/40 | networking | |

Disagreements and final adjudication: **none**. The human reviewed every label on 2026-11-11 and changed none.

## Assistant citations (Phase 6)

Not started.
