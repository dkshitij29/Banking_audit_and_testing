# Test set v1: 10 stocks × 2 time periods = 20 samples

Our first evaluation (36 decisions, Jul–Oct 2026) covered 5 stocks in a rising market,
and the agent leaned bearish. Test set v1 adds more stocks and sectors, and falling and
flat markets, to ask whether that lean hurts everywhere or only in a rising market.

## Periods
| Period | Date | Market over the next 20 sessions (SPY) | Model may know the period | Stocks |
|---|---|---|---|---|
| P1 | 2024-08-19 | flat, +0.5% | likely | CAT, LIN, NEE, WMT |
| P2 | 2025-03-10 | falling, −10.4% (tariff sell-off) | likely | AMZN, NVDA, WMT, XOM |
| P3 | 2025-04-21 | rising, +12.4% (rebound) | likely | CAT, JNJ, JPM, META |
| P4 | 2026-02-23 | falling, −4.7% | less likely | JNJ, JPM, META, NEE |
| P5 | 2026-04-06 | rising, +9.8% | less likely | AMZN, LIN, NVDA, XOM |

## Stocks (10 sectors)
| Stock | Sector | Tested in |
|---|---|---|
| NVDA | Information technology | falling 2025, rising 2026 |
| META | Communication services | rising 2025, falling 2026 |
| AMZN | Consumer discretionary | falling 2025, rising 2026 |
| WMT | Consumer staples | flat 2024, falling 2025 |
| JPM | Financials | rising 2025, falling 2026 |
| XOM | Energy | falling 2025, rising 2026 |
| JNJ | Health care | rising 2025, falling 2026 |
| CAT | Industrials | flat 2024, rising 2025 |
| NEE | Utilities | flat 2024, falling 2026 |
| LIN | Materials | flat 2024, rising 2026 |

Each stock appears twice, in two different market conditions; six of them get one falling
and one rising period. Each period holds 4 stocks, giving 8 falling, 8 rising and 4 flat samples.

Selection rule: each date is a Monday, and its SPY move over the next 20 sessions is
≤ −3% for falling, ≥ +3% for rising and within ±1% for flat. `build_dataset.py` re-measures
every period and every stock from Yahoo prices and refuses to write the file if a check fails.
SEC filings (as filed before each date) were checked for every stock.

"Model may know": Qwen3.6-27B may have seen news from 2024–2025 during training, so it
could recall those outcomes. We could not verify its training cutoff. The 2026 periods are
the fairer test.

The market columns are for analysis only. The agent receives just a ticker and a date.

## Reference: an agent that always says Underweight
| Market | 20-day alpha hit rate | 20-day raw hit rate |
|---|---|---|
| falling | 38% | 100% |
| rising | 38% | 25% |
| flat | 0% | 0% |

In a falling market, a stock that falls less than SPY still beats the market. That is why
always-Underweight scores 100% on raw direction but only 38% on alpha. Our agent should
beat these numbers, and the "always Buy" baseline, in each market condition.

## Run and evaluate
```
.\start_tunnel.ps1                 # in its own window
.\launch_dataset.ps1               # 4 windows, 2–3 stocks each; rerun to resume
cd TradingAgents
.venv\Scripts\python.exe ..\evaluate.py --name ds1 --groups ..\dataset\test_set_v1.csv "ds1_*"
```
Results go to `results\backtest\ds1_<TICKER>\`, and the report to `results\evaluation\report_ds1.md`.
The report includes a "By market condition" section: falling, rising and flat, each at 5, 10 and 20 days.

Settings match the first evaluation: baseline prompts (extra indicators off) and FRED off.
