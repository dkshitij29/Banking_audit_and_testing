# Architecture Decision Records: Finance Agent

Documented Nov 21, 2026

Project 17 | Group 43 | Harshitha Munukoti | Supervisor: Dr. Praveen Tammana



This log holds one short record for each significant choice in the finance-agent part of Agent Garden (a multi-agent finance agent, with TradingAgents as its base, evaluated on the lab's open-weight models and a 20-sample test set). Each record follows the course template fields. The decision dates below are windows, not exact days. The records were written on the date shown at the top, and none is backdated.

---

## ADR-001 — Use TradingAgents as the base for the finance agent

- **Date, status, scope:** Sept 20 – Sept 30; Accepted; choice of the finance agent for Agent Garden.
- **Context and decision drivers:** The router test needs a realistic finance workload: many model calls per decision, real tool use and steps of different difficulty. The agent must connect to any OpenAI-compatible endpoint, run in batches from a script, work on free open-weight models, and not cost us weeks to build.
- **Options considered:**
  1. Use TradingAgents v0.7.1 (open source, Apache-2.0; 12 agents on LangGraph) as the base and reference design.
  2. Write our own agent: one LLM prompt per decision.
  3. Base it on another finance agent: FinMem or FinAgent.
- **Decision and rationale:** Option 1. The TradingAgents design already splits the work across 12 agents with data tools, has a "quick" model slot (10 agents) and a "deep" model slot (Research Manager and Portfolio Manager), and works with an OpenAI-compatible endpoint. Option 2 is cheaper but does not give a multi-agent workload. FinMem and FinAgent are single-agent research systems. This is a judgment from comparing features; we did not run the other agents.
- **Consequences and trade-offs:** We save build time and get a real multi-agent workload. The finance agent follows the TradingAgents design at version 0.7.1, and our own changes are a 12-line patch plus one new module. Results hold only for this design with its default prompts. The published TradingAgents results used paid models, so our numbers are not comparable with the paper.
- **Evidence and validation:** Comparison of options in the project report, section 2; 156 decisions completed with the finance agent (report section 1, AT-1); the base framework's test suite with our patch: 1,407 passed, 0 failed (`results/tests/pytest_upstream_2026-11-20.txt`).
- **Revisit trigger:** A change in the TradingAgents base stops us from repeating a run, or the router team asks for a different agent.

## ADR-002 — Run backtests in batches from scripts, one stock-date per call

- **Date, status, scope:** Oct 1 – Oct 10; Accepted; how the agent is run during evaluation.
- **Context and decision drivers:** We must run many decisions (156 in the end) with no one typing. Each decision needs a clean start, only the data available on its date, and a recorded result, and a run must survive interruptions on a shared GPU.
- **Options considered:**
  1. Keep the default: use the agent's command-line tool interactively.
  2. The `tradingagents backtest` command, one stock-date per call, driven by PowerShell scripts with parallel windows and resume.
  3. Drive the agent graph from our own Python program.
- **Decision and rationale:** Option 2. It is the simplest way to start a decision from a script and keep its full log, and a rerun skips finished samples. Interactive use cannot be repeated reliably. Our own program would give more control but needs more code to write and test. This is a judgment about effort, not a measurement.
- **Consequences and trade-offs:** Runs are repeatable and resume after a failure. Every decision is saved as a JSON log and one line in the memory log. Only data up to the decision date reaches the agents: SEC filings filed by that date, and no present-day company profile. Free news and social sources return nothing for past dates, so those analysts work with less data. We run 4 windows in parallel, because 5 overloaded the shared GPU.
- **Evidence and validation:** `launch_dataset.ps1`, `run_dataset.ps1`, `run_experiment.ps1`; AT-2 and AT-4 (report section 1): after the lab swapped the model server mid-run on 18 Nov 2026, the relaunch completed 20/20, and the failed logs are archived in `results/backtest/_failed_ds1_qwen38_2026-11-18`.
- **Revisit trigger:** Historical news becomes available (report section 9, task 4), or a rerun cannot reproduce a run's settings.

## ADR-003 — Reach models only through an OpenAI-compatible endpoint on the lab GPU

- **Date, status, scope:** Oct 11 – Oct 20; Accepted; how the agent connects to the two models.
- **Context and decision drivers:** The wider project will put a router between the agent and the models. The agent should not need code changes when that happens, the same agent must run on gemma-4-12B and Qwen3.6-27B, and no paid API may be used.
- **Options considered:**
  1. A paid API model (closest to the TradingAgents paper).
  2. A model on the laptop (llama.cpp).
  3. One OpenAI-compatible base URL and model name, served by vLLM on the lab GPU and reached through an SSH tunnel.
- **Decision and rationale:** Option 3. Changing the base URL and model name is the only step needed to swap a model, or later to put the router in front; our launch scripts take both as settings (`-BackendUrl`, `-Model`). Option 1 breaks the no-paid-API constraint, and the laptop has no GPU that can run 12–27B models. This is a design judgment; before each new model we checked plain chat, tool calling and the structured final decision through the same route.
- **Consequences and trade-offs:** Free, and one simple setup for all runs. We depend on lab staff: the server was swapped mid-run on 18 Nov and gemma's job was cancelled on 19 Nov 2026, and both runs were completed after relaunching. Tool-call parsers are model-specific. The router is not in the path in these runs; the agent calls the model endpoint directly through the tunnel (ports 9000 and 9003 on node slurm-comp01).
- **Evidence and validation:** Model Garden table and Figure 1 (report section 3); AT-5: gemma-4-12B ran the same 20 samples by configuration alone; failures and edge cases table (report section 5).
- **Revisit trigger:** The router team's endpoint needs a header or parameter that the OpenAI-compatible route cannot carry, or the SSH tunnel causes lost samples.

## ADR-004 — Score each rating against the stock's return relative to SPY

- **Date, status, scope:** Oct 21 – Oct 31; Accepted; how each decision is scored.
- **Context and decision drivers:** The score must be objective and repeatable from public prices, and must not reward a model simply for following the market.
- **Options considered:**
  1. Keep the paper's method: simulate trading and report cumulative return and Sharpe ratio.
  2. Ask an LLM judge to rate the agents' reports.
  3. Turn each rating into a direction and check it against the stock's return minus SPY's return (alpha) after 5, 10 and 20 trading days, with a coin-flip test and an always-Buy baseline.
- **Decision and rationale:** Option 3. Entry is the first close after the decision date. A Buy or Overweight call is a hit if alpha is above 0, an Underweight or Sell call if alpha is below 0, and Hold is not scored. A judge cannot tell whether a call was right, and a trading simulation on a few stocks mixes in sizing and timing choices. This is a decision to measure, not to judge.
- **Consequences and trade-offs:** Scores are objective and comparable across models, and a second script recomputes every metric from the raw files. Price targets, stop-losses and position sizes are not scored, and Holds get no score. The agent's plans span weeks to months, but we score at one to four weeks.
- **Evidence and validation:** AT-3: a synthetic log reproduced the hand-computed reference table (`dataset/README.md`); raw scores in `results/evaluation/cells_*.csv`; terms table and Figure 4 (report section 4).
- **Revisit trigger:** The router comparison needs a cost-weighted or position-sized score, or a large share of decisions end as Hold.

## ADR-005 — Offer extra technical indicators as an option, off by default

- **Date, status, scope:** Oct 21 – Oct 31; Accepted; the market analyst's indicator list.
- **Context and decision drivers:** The market analyst picks up to 8 of 12 standard indicators and has no measure of trend strength, volume confirmation or stretch from the mean. We wanted to test whether such indicators help, without changing the baseline runs.
- **Options considered:**
  1. Keep the base list of 12 indicators.
  2. Always add 9 extra indicators: ADX, +DI, −DI, Supertrend and its two bands, OBV, 20-day z-score and StochRSI.
  3. Add them behind a switch that is off by default.
- **Decision and rationale:** Option 3. The baseline stays unchanged, and the same samples can be run with and without the indicators. The selection follows the expanded set of the community fork BichengWang/TradingAgents, trimmed to what stockstats computes; our module was written for this project. The switch stays off by default because the gain is not yet confirmed. The effect is measured, not judged: arm C against arms A and B, and E5 against E4.
- **Consequences and trade-offs:** With Qwen3.6-27B on 30 earlier samples the hit rate rose from 57% to 68%, 50% to 61% and 39% to 46% at 5, 10 and 20 days, above always-Buy at 5 and 10 days (p = 0.04 at 5 days). That is 3 more correct calls out of 28 and does not survive a correction for 9 tests. With gemma-4-12B only 3 of 20 ratings changed. Every saved decision records whether the switch was on.
- **Evidence and validation:** `tradingagents/dataflows/extra_indicators.py` and the 12-line patch; report sections 3 and 5; `results/evaluation/report_compare.md` and `report_gemma_ind_ds1.md`.
- **Revisit trigger:** Qwen3.6-27B with the indicators beats always-Buy on the 20-sample test set (report section 9, task 1); then the switch becomes the default.

## ADR-006 — One run per sample plus one repeat; report hit rate, p-value and baselines

- **Date, status, scope:** Oct 1 – Oct 10; Accepted; how results are counted and reported.
- **Context and decision drivers:** An LLM agent can give a different rating on the same sample each time, and one decision takes 10–25 minutes on a shared GPU. We need to know how large that noise is without multiplying the GPU time.
- **Options considered:**
  1. Keep the simplest approach: one run per sample.
  2. One run per sample, plus one full repeat of a sample set to measure run-to-run agreement.
  3. Three runs per sample with a majority vote.
- **Decision and rationale:** Option 2. The repeat shows the size of the noise at the cost of one extra run of 30 decisions; three runs per sample would triple the GPU time. Metric definitions are fixed: hit rate at 5, 10 and 20 days, a one-sided binomial p-value against a coin flip, the always-Buy baseline and the rating mix. The choice of one repeat is a judgment on cost.
- **Consequences and trade-offs:** We report results per setup and horizon (report section 5). The repeat gave the same rating as the first run on only 10 of 30 samples (33%) and the same direction on 13 (43%), so single-run comparisons must be read with care. With 18 scored calls, p < 0.05 needs 13 hits (72%), so only large effects can show.
- **Evidence and validation:** Arms A and B (`results/evaluation/report_A.md`, `report_B.md`, `report_compare.md`); results tables (report section 5).
- **Revisit trigger:** Agreement between repeats stays below 50%. This is already the case on the earlier samples (33%), so three runs with a majority vote is report section 9, task 2.

## ADR-007 — Use one fixed model per run, before any routing

- **Date, status, scope:** Oct 21 – Oct 31; Accepted; the baseline the router will be compared with.
- **Context and decision drivers:** The router's value is cost saved at the same quality. That can only be shown against fixed-model baselines on the same samples.
- **Options considered:**
  1. Route every agent's calls from the first run.
  2. One fixed model for all 12 agents in a run, with two models: gemma-4-12B (small) and Qwen3.6-27B (large).
- **Decision and rationale:** Option 2. Fixed runs give a clean baseline and keep the agent's behaviour separate from the router's. Option 1 would mix the two effects, and we could not tell which caused a change. Choosing these two models is a judgment based on what the lab GPU serves.
- **Consequences and trade-offs:** On the 20-sample test set, Qwen3.6-27B was right on 44%, 50% and 39% of calls at 5, 10 and 20 days and gemma-4-12B on 67%, 56% and 72%, against 65%, 60% and 70% for always-Buy. Qwen3.6 mostly said Underweight (15 of 20) and gemma Overweight (18 of 20). gemma took about half the time per decision (10–11 against 22 minutes). Neither model beat always-Buy, so the workload does not yet show which steps need the large model. Cost per decision is not measured. A Qwen3.8-27B run was lost when the lab swapped the server.
- **Evidence and validation:** Results tables and observations (report section 5); `results/evaluation/report_ds1.md` and `report_gemma_ds1.md`.
- **Revisit trigger:** The router endpoint is stable, which starts the comparison of router, always-small and always-large on the same 20 samples (report section 9, task 5).

## ADR-008 — Build a balanced 20-sample test set across sectors and market conditions

- **Date, status, scope:** Oct 21 – Oct 31; Accepted; supersedes the first evaluation's five-stock sample as the main test; the evaluation set.
- **Context and decision drivers:** The first evaluation used five large US stocks every 14 days in one rising market, so a bearish model looked bad mostly because of the market. We need several sectors and market conditions, with every label checked, within the GPU time we have.
- **Options considered:**
  1. Keep the earlier five-stock sample.
  2. Pick stocks and dates at random.
  3. Curate 10 stocks, one per sector, each on 2 of 5 dates chosen by SPY's move over the next 20 trading days: falling (−3% or worse), rising (+3% or better) and flat (within ±1%).
- **Decision and rationale:** Option 3. The set is balanced by sector and market condition, and the builder recomputes every label from prices and refuses to write the file if a check fails. Random dates could miss a condition, and the earlier sample has only one. Judgment: 20 samples (8 falling, 8 rising, 4 flat) show a trend, not a precise rate.
- **Consequences and trade-offs:** A clear comparison of models on the same samples. The set is small: 4–8 samples per condition and 18–20 scored calls per run. Its results cannot be compared directly with the first evaluation's.
- **Evidence and validation:** `dataset/test_set_v1.csv`, `dataset/README.md` and `dataset/build_dataset.py` (built 18 Nov 2026); report section 4; experiments E3 to E5 ran on this set (18–20 Nov 2026).
- **Revisit trigger:** Two setups' results cannot be told apart, for example when one more correct call changes which is ahead; then the set grows to at least 100 samples (report section 9, task 2).

## Methodology record — status at 9 October 2026

- **Reaffirmed or changed:** changed. The agent, batch runs, endpoint, scoring and metric choices (ADR-001 to ADR-004, ADR-006) are kept as they were. The evaluation was extended after the presentation: a balanced test set (ADR-008), a second model (ADR-007) and the extra-indicator option (ADR-005).
- **If changed — old approach:** The first evaluation: five large US stocks (AAPL, AMZN, JPM, MSFT, NVDA) every 14 days in one rising market, on one model (Qwen3.6-27B).
- **New evidence:** The first evaluation (36 decisions) showed a bearish lean that the rising market punished: 56% of calls were Underweight, while 67% of the stocks beat SPY over 20 days. The result depended on the market, and a repeat run agreed with the first on only a third of the ratings.
- **Alternatives:** Keep the five-stock sample; pick stocks and dates at random; curate a balanced set (see ADR-008).
- **Selected approach:** A balanced 20-sample test set across 10 sectors and three market conditions, run on two models, with the extra indicators as an option.
- **Impact:** The first-evaluation results are kept and reported separately; the model comparison uses the test set. All test-set figures in the project report use the new set.
- **Revised plan:** Run Qwen3.6-27B with the indicators on the test set, repeat runs with a majority vote, then run the finance agent through the router on the same samples.
- **Documentation date:** This log was written on 21 November 2026. It records decisions taken in the date windows above and is not backdated.
