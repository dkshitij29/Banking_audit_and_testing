# TradingAgents evaluation - ds1 (2026-11-19)

Decisions: 20 from 10 log(s) · tickers: AMZN, CAT, JNJ, JPM, LIN, META, NEE, NVDA, WMT, XOM · model: Qwen3.6-27B
Entry = first close after the analysis date; benchmark: SPY.

## Every decision

| Ticker | Date | Rating | 5d raw / alpha | 10d raw / alpha | 20d raw / alpha |
|---|---|---|---|---|---|
| AMZN | 2025-03-10 | Underweight | -1.9% / -2.8% | +4.6% / +0.8% | -13.2% / -2.8% |
| AMZN | 2026-04-06 | Underweight | +16.5% / +11.1% | +16.9% / +10.1% | +28.0% / +18.2% |
| CAT | 2024-08-19 | Underweight | +2.3% / +1.8% | -1.9% / -0.5% | +3.4% / +3.0% |
| CAT | 2025-04-21 | Underweight | +5.6% / +0.4% | +10.2% / +4.2% | +20.0% / +7.6% |
| JNJ | 2025-04-21 | Underweight | -1.2% / -6.3% | -2.1% / -8.1% | -2.6% / -15.0% |
| JNJ | 2026-02-23 | Underweight | +0.2% / +1.2% | -1.0% / +0.4% | -4.5% / +0.2% |
| JPM | 2025-04-21 | Underweight | +3.8% / -1.3% | +5.8% / -0.2% | +12.8% / +0.3% |
| JPM | 2026-02-23 | Underweight | +1.0% / +2.0% | -2.9% / -1.4% | -1.6% / +3.1% |
| LIN | 2024-08-19 | Underweight | +3.1% / +2.6% | +3.4% / +4.8% | +2.3% / +1.8% |
| LIN | 2026-04-06 | Underweight | +1.0% / -4.3% | +0.1% / -6.8% | +1.2% / -8.6% |
| META | 2025-04-21 | Hold | +10.8% / +5.7% | +17.4% / +11.4% | +27.3% / +14.9% |
| META | 2026-02-23 | Overweight | +2.5% / +3.5% | +2.3% / +3.8% | -7.2% / -2.5% |
| NEE | 2024-08-19 | Underweight | +0.8% / +0.3% | +3.3% / +4.7% | +7.4% / +6.9% |
| NEE | 2026-02-23 | Underweight | -2.6% / -1.5% | -3.7% / -2.2% | -3.6% / +1.1% |
| NVDA | 2025-03-10 | Underweight | +6.1% / +5.2% | +11.0% / +7.2% | -11.4% / -1.0% |
| NVDA | 2026-04-06 | Overweight | +10.3% / +5.0% | +12.2% / +5.4% | +10.3% / +0.5% |
| WMT | 2024-08-19 | Underweight | +2.1% / +1.6% | +3.6% / +5.0% | +6.0% / +5.5% |
| WMT | 2025-03-10 | Buy | -2.1% / -3.0% | -2.8% / -6.6% | -6.2% / +4.2% |
| XOM | 2025-03-10 | Hold | +4.1% / +3.2% | +6.8% / +3.0% | -7.7% / +2.7% |
| XOM | 2026-04-06 | Underweight | -9.0% / -14.3% | -9.5% / -16.3% | -5.5% / -15.3% |

## Scores

### Holding period: 5 trading days
Scored decisions: 20 (directional 18, Hold 2) · pending (window not over yet): 0

| Metric | Value | What it means |
|---|---|---|
| **Alpha hit rate** | 44% (8/18) | Buy/Overweight beat SPY, or Underweight/Sell lagged it |
| p-value vs coin flip | 0.76 | below 0.05 = unlikely to be luck |
| **Raw direction hit rate** | 33% (6/18) | the stock itself moved the way the call said |
| p-value vs coin flip | 0.95 | |
| Mean alpha of bullish calls | +1.82% | should be positive |
| Mean alpha of bearish calls | -0.29% | should be negative |
| **Long-short spread** | +2.10% | bullish minus bearish; > 0 = the ratings separate winners from losers |
| Avg alpha captured per call | +0.54% | following each call (long on bullish, short on bearish) |
| Baseline: stocks that beat SPY | 65% (13/20) | an 'always Buy' agent's alpha hit rate |
| Baseline: stocks that rose | 75% (15/20) | an 'always Buy' agent's raw hit rate |

| Rating | n | Mean raw return | Mean alpha | Alpha hit rate | Raw hit rate |
|---|---|---|---|---|---|
| Buy | 1 | -2.12% | -3.03% | 0% (0/1) | 0% (0/1) |
| Overweight | 2 | +6.40% | +4.24% | 100% (2/2) | 100% (2/2) |
| Hold | 2 | +7.46% | +4.44% | no direction | no direction |
| Underweight | 15 | +1.86% | -0.29% | 40% (6/15) | 27% (4/15) |

### Holding period: 10 trading days
Scored decisions: 20 (directional 18, Hold 2) · pending (window not over yet): 0

| Metric | Value | What it means |
|---|---|---|
| **Alpha hit rate** | 50% (9/18) | Buy/Overweight beat SPY, or Underweight/Sell lagged it |
| p-value vs coin flip | 0.59 | below 0.05 = unlikely to be luck |
| **Raw direction hit rate** | 44% (8/18) | the stock itself moved the way the call said |
| p-value vs coin flip | 0.76 | |
| Mean alpha of bullish calls | +0.86% | should be positive |
| Mean alpha of bearish calls | +0.12% | should be negative |
| **Long-short spread** | +0.74% | bullish minus bearish; > 0 = the ratings separate winners from losers |
| Avg alpha captured per call | +0.04% | following each call (long on bullish, short on bearish) |
| Baseline: stocks that beat SPY | 60% (12/20) | an 'always Buy' agent's alpha hit rate |
| Baseline: stocks that rose | 65% (13/20) | an 'always Buy' agent's raw hit rate |

| Rating | n | Mean raw return | Mean alpha | Alpha hit rate | Raw hit rate |
|---|---|---|---|---|---|
| Buy | 1 | -2.80% | -6.63% | 0% (0/1) | 0% (0/1) |
| Overweight | 2 | +7.27% | +4.61% | 100% (2/2) | 100% (2/2) |
| Hold | 2 | +12.10% | +7.20% | no direction | no direction |
| Underweight | 15 | +2.52% | +0.12% | 47% (7/15) | 40% (6/15) |

### Holding period: 20 trading days
Scored decisions: 20 (directional 18, Hold 2) · pending (window not over yet): 0

| Metric | Value | What it means |
|---|---|---|
| **Alpha hit rate** | 39% (7/18) | Buy/Overweight beat SPY, or Underweight/Sell lagged it |
| p-value vs coin flip | 0.88 | below 0.05 = unlikely to be luck |
| **Raw direction hit rate** | 44% (8/18) | the stock itself moved the way the call said |
| p-value vs coin flip | 0.76 | |
| Mean alpha of bullish calls | +0.76% | should be positive |
| Mean alpha of bearish calls | +0.33% | should be negative |
| **Long-short spread** | +0.44% | bullish minus bearish; > 0 = the ratings separate winners from losers |
| Avg alpha captured per call | -0.15% | following each call (long on bullish, short on bearish) |
| Baseline: stocks that beat SPY | 70% (14/20) | an 'always Buy' agent's alpha hit rate |
| Baseline: stocks that rose | 50% (10/20) | an 'always Buy' agent's raw hit rate |

| Rating | n | Mean raw return | Mean alpha | Alpha hit rate | Raw hit rate |
|---|---|---|---|---|---|
| Buy | 1 | -6.20% | +4.22% | 100% (1/1) | 0% (0/1) |
| Overweight | 2 | +1.58% | -0.96% | 50% (1/2) | 50% (1/2) |
| Hold | 2 | +9.83% | +8.82% | no direction | no direction |
| Underweight | 15 | +2.57% | +0.33% | 33% (5/15) | 47% (7/15) |

Test set ../dataset/test_set_v1.csv: 20 of 20 decisions matched a sample.

## By market condition

A bearish agent should do well in falling markets and badly in rising ones; a skilled one beats the 'always Buy' baseline in every condition.

### 5 trading days

| Market | Decisions | Bearish calls | Alpha hit rate | p-value | Raw hit rate | Always Buy (alpha) | Avg alpha captured |
|---|---|---|---|---|---|---|---|
| falling | 8 | 62% (5/8) | 43% (3/7) | 0.77 | 43% (3/7) | 62% (5/8) | -0.52% |
| flat | 4 | 100% (4/4) | 0% (0/4) | 1.00 | 0% (0/4) | 100% (4/4) | -1.57% |
| rising | 8 | 75% (6/8) | 71% (5/7) | 0.23 | 43% (3/7) | 50% (4/8) | +2.80% |

### 10 trading days

| Market | Decisions | Bearish calls | Alpha hit rate | p-value | Raw hit rate | Always Buy (alpha) | Avg alpha captured |
|---|---|---|---|---|---|---|---|
| falling | 8 | 62% (5/8) | 43% (3/7) | 0.77 | 57% (4/7) | 62% (5/8) | -1.09% |
| flat | 4 | 100% (4/4) | 25% (1/4) | 0.94 | 25% (1/4) | 75% (3/4) | -3.49% |
| rising | 8 | 75% (6/8) | 71% (5/7) | 0.23 | 43% (3/7) | 50% (4/8) | +3.20% |

### 20 trading days

| Market | Decisions | Bearish calls | Alpha hit rate | p-value | Raw hit rate | Always Buy (alpha) | Avg alpha captured |
|---|---|---|---|---|---|---|---|
| falling | 8 | 62% (5/8) | 43% (3/7) | 0.77 | 71% (5/7) | 62% (5/8) | +0.16% |
| flat | 4 | 100% (4/4) | 0% (0/4) | 1.00 | 0% (0/4) | 100% (4/4) | -4.30% |
| rising | 8 | 75% (6/8) | 57% (4/7) | 0.50 | 43% (3/7) | 62% (5/8) | +1.92% |
