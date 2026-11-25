# TradingAgents evaluation - A (2026-10-30)

Decisions: 30 from 5 log(s) · tickers: AAPL, AMZN, JPM, MSFT, NVDA · model: Qwen3.6-27B
Entry = first close after the analysis date; benchmark: SPY.

## Every decision

| Ticker | Date | Rating | 5d raw / alpha | 10d raw / alpha | 20d raw / alpha |
|---|---|---|---|---|---|
| AAPL | 2026-07-20 | Hold | +3.8% / +4.8% | -5.6% / -8.7% | -5.3% / -7.9% |
| AAPL | 2026-08-03 | Buy | -1.4% / -1.3% | +0.3% / +0.8% | +5.2% / +6.4% |
| AAPL | 2026-08-17 | Underweight | -0.0% / +0.2% | +4.9% / +5.6% | +7.2% / +9.0% |
| AAPL | 2026-08-31 | Underweight | -3.0% / -3.1% | +2.2% / +3.3% | +2.4% / +2.1% |
| AAPL | 2026-09-14 | Underweight | +2.5% / +0.2% | -0.6% / -1.7% | +3.0% / +0.0% |
| AAPL | 2026-09-28 | Buy | +1.3% / -0.7% | +3.6% / +1.8% | +5.4% / +4.7% |
| AMZN | 2026-07-20 | Underweight | -6.7% / -5.8% | +12.1% / +9.0% | +4.8% / +2.2% |
| AMZN | 2026-08-03 | Underweight | -1.9% / -1.8% | -6.5% / -6.0% | -8.1% / -6.9% |
| AMZN | 2026-08-17 | Buy | +0.6% / +0.8% | -1.7% / -1.0% | -5.2% / -3.5% |
| AMZN | 2026-08-31 | Buy | -1.0% / -1.1% | -3.5% / -2.5% | -2.3% / -2.6% |
| AMZN | 2026-09-14 | Buy | +2.6% / +0.3% | -0.7% / -1.9% | +4.1% / +1.1% |
| AMZN | 2026-09-28 | Overweight | +3.9% / +2.0% | +4.8% / +3.0% | +2.6% / +1.9% |
| JPM | 2026-07-20 | Buy | +3.5% / +4.5% | +3.6% / +0.5% | +5.2% / +2.7% |
| JPM | 2026-08-03 | Underweight | +1.3% / +1.4% | +1.6% / +2.1% | -0.7% / +0.5% |
| JPM | 2026-08-17 | Buy | -1.8% / -1.6% | -2.3% / -1.5% | -3.9% / -2.2% |
| JPM | 2026-08-31 | Underweight | -0.1% / -0.1% | -1.7% / -0.7% | -6.8% / -7.2% |
| JPM | 2026-09-14 | Underweight | -3.5% / -5.9% | -5.0% / -6.1% | -5.5% / -8.5% |
| JPM | 2026-09-28 | Underweight | -0.6% / -2.6% | -0.6% / -2.4% | +0.7% / +0.0% |
| MSFT | 2026-07-20 | Underweight | -1.1% / -0.1% | +23.9% / +20.8% | +21.1% / +18.5% |
| MSFT | 2026-08-03 | Underweight | +2.2% / +2.3% | -2.3% / -1.8% | +1.9% / +3.1% |
| MSFT | 2026-08-17 | Underweight | +2.3% / +2.5% | +4.2% / +5.0% | +2.0% / +3.7% |
| MSFT | 2026-08-31 | Underweight | -1.9% / -2.0% | -2.1% / -1.1% | +2.4% / +2.0% |
| MSFT | 2026-09-14 | Buy | +0.2% / -2.2% | +2.4% / +1.2% | +9.3% / +6.3% |
| MSFT | 2026-09-28 | Hold | +4.0% / +2.0% | +6.8% / +5.0% | +4.4% / +3.7% |
| NVDA | 2026-07-20 | Underweight | -5.0% / -4.0% | +2.2% / -0.8% | +6.0% / +3.4% |
| NVDA | 2026-08-03 | Underweight | +2.6% / +2.7% | +3.7% / +4.2% | +2.6% / +3.8% |
| NVDA | 2026-08-17 | Underweight | -3.0% / -2.8% | -1.0% / -0.3% | -2.5% / -0.8% |
| NVDA | 2026-08-31 | Buy | +2.9% / +2.8% | -1.5% / -0.5% | +5.1% / +4.8% |
| NVDA | 2026-09-14 | Underweight | +7.9% / +5.5% | +7.1% / +5.9% | +7.7% / +4.7% |
| NVDA | 2026-09-28 | Overweight | +5.3% / +3.3% | +0.6% / -1.2% | -4.1% / -4.8% |

## Scores

### Holding period: 5 trading days
Scored decisions: 30 (directional 28, Hold 2) · pending (window not over yet): 0

| Metric | Value | What it means |
|---|---|---|
| **Alpha hit rate** | 57% (16/28) | Buy/Overweight beat SPY, or Underweight/Sell lagged it |
| p-value vs coin flip | 0.29 | below 0.05 = unlikely to be luck |
| **Raw direction hit rate** | 68% (19/28) | the stock itself moved the way the call said |
| p-value vs coin flip | 0.04 | |
| Mean alpha of bullish calls | +0.63% | should be positive |
| Mean alpha of bearish calls | -0.79% | should be negative |
| **Long-short spread** | +1.41% | bullish minus bearish; > 0 = the ratings separate winners from losers |
| Avg alpha captured per call | +0.72% | following each call (long on bullish, short on bearish) |
| Baseline: stocks that beat SPY | 50% (15/30) | an 'always Buy' agent's alpha hit rate |
| Baseline: stocks that rose | 53% (16/30) | an 'always Buy' agent's raw hit rate |

| Rating | n | Mean raw return | Mean alpha | Alpha hit rate | Raw hit rate |
|---|---|---|---|---|---|
| Buy | 9 | +0.77% | +0.18% | 44% (4/9) | 67% (6/9) |
| Overweight | 2 | +4.60% | +2.65% | 100% (2/2) | 100% (2/2) |
| Hold | 2 | +3.88% | +3.40% | no direction | no direction |
| Underweight | 17 | -0.47% | -0.79% | 59% (10/17) | 65% (11/17) |

### Holding period: 10 trading days
Scored decisions: 30 (directional 28, Hold 2) · pending (window not over yet): 0

| Metric | Value | What it means |
|---|---|---|
| **Alpha hit rate** | 50% (14/28) | Buy/Overweight beat SPY, or Underweight/Sell lagged it |
| p-value vs coin flip | 0.57 | below 0.05 = unlikely to be luck |
| **Raw direction hit rate** | 50% (14/28) | the stock itself moved the way the call said |
| p-value vs coin flip | 0.57 | |
| Mean alpha of bullish calls | -0.12% | should be positive |
| Mean alpha of bearish calls | +2.06% | should be negative |
| **Long-short spread** | -2.17% | bullish minus bearish; > 0 = the ratings separate winners from losers |
| Avg alpha captured per call | -1.29% | following each call (long on bullish, short on bearish) |
| Baseline: stocks that beat SPY | 47% (14/30) | an 'always Buy' agent's alpha hit rate |
| Baseline: stocks that rose | 53% (16/30) | an 'always Buy' agent's raw hit rate |

| Rating | n | Mean raw return | Mean alpha | Alpha hit rate | Raw hit rate |
|---|---|---|---|---|---|
| Buy | 9 | +0.01% | -0.34% | 44% (4/9) | 44% (4/9) |
| Overweight | 2 | +2.70% | +0.90% | 50% (1/2) | 100% (2/2) |
| Hold | 2 | +0.59% | -1.86% | no direction | no direction |
| Underweight | 17 | +2.48% | +2.06% | 53% (9/17) | 47% (8/17) |

### Holding period: 20 trading days
Scored decisions: 30 (directional 28, Hold 2) · pending (window not over yet): 0

| Metric | Value | What it means |
|---|---|---|
| **Alpha hit rate** | 39% (11/28) | Buy/Overweight beat SPY, or Underweight/Sell lagged it |
| p-value vs coin flip | 0.91 | below 0.05 = unlikely to be luck |
| **Raw direction hit rate** | 43% (12/28) | the stock itself moved the way the call said |
| p-value vs coin flip | 0.83 | |
| Mean alpha of bullish calls | +1.35% | should be positive |
| Mean alpha of bearish calls | +1.76% | should be negative |
| **Long-short spread** | -0.41% | bullish minus bearish; > 0 = the ratings separate winners from losers |
| Avg alpha captured per call | -0.54% | following each call (long on bullish, short on bearish) |
| Baseline: stocks that beat SPY | 70% (21/30) | an 'always Buy' agent's alpha hit rate |
| Baseline: stocks that rose | 67% (20/30) | an 'always Buy' agent's raw hit rate |

| Rating | n | Mean raw return | Mean alpha | Alpha hit rate | Raw hit rate |
|---|---|---|---|---|---|
| Buy | 9 | +2.55% | +1.97% | 67% (6/9) | 67% (6/9) |
| Overweight | 2 | -0.74% | -1.45% | 50% (1/2) | 50% (1/2) |
| Hold | 2 | -0.46% | -2.10% | no direction | no direction |
| Underweight | 17 | +2.24% | +1.76% | 24% (4/17) | 29% (5/17) |
