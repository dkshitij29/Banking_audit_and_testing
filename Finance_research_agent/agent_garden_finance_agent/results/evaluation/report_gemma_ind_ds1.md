# TradingAgents evaluation - gemma_ind_ds1 (2026-11-20)

Decisions: 20 from 10 log(s) · tickers: AMZN, CAT, JNJ, JPM, LIN, META, NEE, NVDA, WMT, XOM · model: gemma-4-12B
Entry = first close after the analysis date; benchmark: SPY.

## Every decision

| Ticker | Date | Rating | 5d raw / alpha | 10d raw / alpha | 20d raw / alpha |
|---|---|---|---|---|---|
| AMZN | 2025-03-10 | Overweight | -1.9% / -2.8% | +4.6% / +0.8% | -13.2% / -2.8% |
| AMZN | 2026-04-06 | Overweight | +16.5% / +11.1% | +16.9% / +10.1% | +28.0% / +18.2% |
| CAT | 2024-08-19 | Overweight | +2.3% / +1.8% | -1.9% / -0.5% | +3.4% / +3.0% |
| CAT | 2025-04-21 | Overweight | +5.6% / +0.4% | +10.2% / +4.2% | +20.0% / +7.6% |
| JNJ | 2025-04-21 | Overweight | -1.2% / -6.3% | -2.1% / -8.1% | -2.6% / -15.0% |
| JNJ | 2026-02-23 | Overweight | +0.2% / +1.2% | -1.0% / +0.4% | -4.5% / +0.2% |
| JPM | 2025-04-21 | Hold | +3.8% / -1.3% | +5.8% / -0.2% | +12.8% / +0.3% |
| JPM | 2026-02-23 | Overweight | +1.0% / +2.0% | -2.9% / -1.4% | -1.6% / +3.1% |
| LIN | 2024-08-19 | Overweight | +3.1% / +2.6% | +3.4% / +4.8% | +2.3% / +1.8% |
| LIN | 2026-04-06 | Overweight | +1.0% / -4.3% | +0.1% / -6.8% | +1.2% / -8.6% |
| META | 2025-04-21 | Overweight | +10.8% / +5.7% | +17.4% / +11.4% | +27.3% / +14.9% |
| META | 2026-02-23 | Overweight | +2.5% / +3.5% | +2.3% / +3.8% | -7.2% / -2.5% |
| NEE | 2024-08-19 | Overweight | +0.8% / +0.3% | +3.3% / +4.7% | +7.4% / +6.9% |
| NEE | 2026-02-23 | Overweight | -2.6% / -1.5% | -3.7% / -2.2% | -3.6% / +1.1% |
| NVDA | 2025-03-10 | Overweight | +6.1% / +5.2% | +11.0% / +7.2% | -11.4% / -1.0% |
| NVDA | 2026-04-06 | Overweight | +10.3% / +5.0% | +12.2% / +5.4% | +10.3% / +0.5% |
| WMT | 2024-08-19 | Overweight | +2.1% / +1.6% | +3.6% / +5.0% | +6.0% / +5.5% |
| WMT | 2025-03-10 | Overweight | -2.1% / -3.0% | -2.8% / -6.6% | -6.2% / +4.2% |
| XOM | 2025-03-10 | Overweight | +4.1% / +3.2% | +6.8% / +3.0% | -7.7% / +2.7% |
| XOM | 2026-04-06 | Overweight | -9.0% / -14.3% | -9.5% / -16.3% | -5.5% / -15.3% |

## Scores

### Holding period: 5 trading days
Scored decisions: 20 (directional 19, Hold 1) · pending (window not over yet): 0

| Metric | Value | What it means |
|---|---|---|
| **Alpha hit rate** | 68% (13/19) | Buy/Overweight beat SPY, or Underweight/Sell lagged it |
| p-value vs coin flip | 0.08 | below 0.05 = unlikely to be luck |
| **Raw direction hit rate** | 74% (14/19) | the stock itself moved the way the call said |
| p-value vs coin flip | 0.03 | |
| Mean alpha of bullish calls | +0.60% | should be positive |
| Mean alpha of bearish calls | n/a | should be negative |
| **Long-short spread** | n/a | bullish minus bearish; > 0 = the ratings separate winners from losers |
| Avg alpha captured per call | +0.60% | following each call (long on bullish, short on bearish) |
| Baseline: stocks that beat SPY | 65% (13/20) | an 'always Buy' agent's alpha hit rate |
| Baseline: stocks that rose | 75% (15/20) | an 'always Buy' agent's raw hit rate |

| Rating | n | Mean raw return | Mean alpha | Alpha hit rate | Raw hit rate |
|---|---|---|---|---|---|
| Overweight | 19 | +2.62% | +0.60% | 68% (13/19) | 74% (14/19) |
| Hold | 1 | +3.83% | -1.30% | no direction | no direction |

### Holding period: 10 trading days
Scored decisions: 20 (directional 19, Hold 1) · pending (window not over yet): 0

| Metric | Value | What it means |
|---|---|---|
| **Alpha hit rate** | 63% (12/19) | Buy/Overweight beat SPY, or Underweight/Sell lagged it |
| p-value vs coin flip | 0.18 | below 0.05 = unlikely to be luck |
| **Raw direction hit rate** | 63% (12/19) | the stock itself moved the way the call said |
| p-value vs coin flip | 0.18 | |
| Mean alpha of bullish calls | +1.00% | should be positive |
| Mean alpha of bearish calls | n/a | should be negative |
| **Long-short spread** | n/a | bullish minus bearish; > 0 = the ratings separate winners from losers |
| Avg alpha captured per call | +1.00% | following each call (long on bullish, short on bearish) |
| Baseline: stocks that beat SPY | 60% (12/20) | an 'always Buy' agent's alpha hit rate |
| Baseline: stocks that rose | 65% (13/20) | an 'always Buy' agent's raw hit rate |

| Rating | n | Mean raw return | Mean alpha | Alpha hit rate | Raw hit rate |
|---|---|---|---|---|---|
| Overweight | 19 | +3.58% | +1.00% | 63% (12/19) | 63% (12/19) |
| Hold | 1 | +5.80% | -0.19% | no direction | no direction |

### Holding period: 20 trading days
Scored decisions: 20 (directional 19, Hold 1) · pending (window not over yet): 0

| Metric | Value | What it means |
|---|---|---|
| **Alpha hit rate** | 68% (13/19) | Buy/Overweight beat SPY, or Underweight/Sell lagged it |
| p-value vs coin flip | 0.08 | below 0.05 = unlikely to be luck |
| **Raw direction hit rate** | 47% (9/19) | the stock itself moved the way the call said |
| p-value vs coin flip | 0.68 | |
| Mean alpha of bullish calls | +1.29% | should be positive |
| Mean alpha of bearish calls | n/a | should be negative |
| **Long-short spread** | n/a | bullish minus bearish; > 0 = the ratings separate winners from losers |
| Avg alpha captured per call | +1.29% | following each call (long on bullish, short on bearish) |
| Baseline: stocks that beat SPY | 70% (14/20) | an 'always Buy' agent's alpha hit rate |
| Baseline: stocks that rose | 50% (10/20) | an 'always Buy' agent's raw hit rate |

| Rating | n | Mean raw return | Mean alpha | Alpha hit rate | Raw hit rate |
|---|---|---|---|---|---|
| Overweight | 19 | +2.23% | +1.29% | 68% (13/19) | 47% (9/19) |
| Hold | 1 | +12.77% | +0.33% | no direction | no direction |

Test set ../dataset/test_set_v1.csv: 20 of 20 decisions matched a sample.

## By market condition

A bearish agent should do well in falling markets and badly in rising ones; a skilled one beats the 'always Buy' baseline in every condition.

### 5 trading days

| Market | Decisions | Bearish calls | Alpha hit rate | p-value | Raw hit rate | Always Buy (alpha) | Avg alpha captured |
|---|---|---|---|---|---|---|---|
| falling | 8 | 0% (0/8) | 62% (5/8) | 0.36 | 62% (5/8) | 62% (5/8) | +0.96% |
| flat | 4 | 0% (0/4) | 100% (4/4) | 0.06 | 100% (4/4) | 100% (4/4) | +1.57% |
| rising | 8 | 0% (0/8) | 57% (4/7) | 0.50 | 71% (5/7) | 50% (4/8) | -0.38% |

### 10 trading days

| Market | Decisions | Bearish calls | Alpha hit rate | p-value | Raw hit rate | Always Buy (alpha) | Avg alpha captured |
|---|---|---|---|---|---|---|---|
| falling | 8 | 0% (0/8) | 62% (5/8) | 0.36 | 50% (4/8) | 62% (5/8) | +0.62% |
| flat | 4 | 0% (0/4) | 75% (3/4) | 0.31 | 75% (3/4) | 75% (3/4) | +3.49% |
| rising | 8 | 0% (0/8) | 57% (4/7) | 0.50 | 71% (5/7) | 50% (4/8) | +0.01% |

### 20 trading days

| Market | Decisions | Bearish calls | Alpha hit rate | p-value | Raw hit rate | Always Buy (alpha) | Avg alpha captured |
|---|---|---|---|---|---|---|---|
| falling | 8 | 0% (0/8) | 62% (5/8) | 0.36 | 0% (0/8) | 62% (5/8) | +0.64% |
| flat | 4 | 0% (0/4) | 100% (4/4) | 0.06 | 100% (4/4) | 100% (4/4) | +4.30% |
| rising | 8 | 0% (0/8) | 57% (4/7) | 0.50 | 71% (5/7) | 62% (5/8) | +0.32% |
