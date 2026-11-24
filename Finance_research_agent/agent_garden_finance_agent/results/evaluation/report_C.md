# TradingAgents evaluation - C (2026-10-30)

Decisions: 30 from 5 log(s) · tickers: AAPL, AMZN, JPM, MSFT, NVDA · model: Qwen3.6-27B
Entry = first close after the analysis date; benchmark: SPY.
Unreadable ratings (counted as no direction): REVIEW

## Every decision

| Ticker | Date | Rating | 5d raw / alpha | 10d raw / alpha | 20d raw / alpha |
|---|---|---|---|---|---|
| AAPL | 2026-07-20 | Underweight | +3.8% / +4.8% | -5.6% / -8.7% | -5.3% / -7.9% |
| AAPL | 2026-08-03 | Underweight | -1.4% / -1.3% | +0.3% / +0.8% | +5.2% / +6.4% |
| AAPL | 2026-08-17 | Underweight | -0.0% / +0.2% | +4.9% / +5.6% | +7.2% / +9.0% |
| AAPL | 2026-08-31 | Underweight | -3.0% / -3.1% | +2.2% / +3.3% | +2.4% / +2.1% |
| AAPL | 2026-09-14 | Underweight | +2.5% / +0.2% | -0.6% / -1.7% | +3.0% / +0.0% |
| AAPL | 2026-09-28 | Buy | +1.3% / -0.7% | +3.6% / +1.8% | +5.4% / +4.7% |
| AMZN | 2026-07-20 | Overweight | -6.7% / -5.8% | +12.1% / +9.0% | +4.8% / +2.2% |
| AMZN | 2026-08-03 | Underweight | -1.9% / -1.8% | -6.5% / -6.0% | -8.1% / -6.9% |
| AMZN | 2026-08-17 | Overweight | +0.6% / +0.8% | -1.7% / -1.0% | -5.2% / -3.5% |
| AMZN | 2026-08-31 | Overweight | -1.0% / -1.1% | -3.5% / -2.5% | -2.3% / -2.6% |
| AMZN | 2026-09-14 | REVIEW | +2.6% / +0.3% | -0.7% / -1.9% | +4.1% / +1.1% |
| AMZN | 2026-09-28 | Underweight | +3.9% / +2.0% | +4.8% / +3.0% | +2.6% / +1.9% |
| JPM | 2026-07-20 | Underweight | +3.5% / +4.5% | +3.6% / +0.5% | +5.2% / +2.7% |
| JPM | 2026-08-03 | Hold | +1.3% / +1.4% | +1.6% / +2.1% | -0.7% / +0.5% |
| JPM | 2026-08-17 | Underweight | -1.8% / -1.6% | -2.3% / -1.5% | -3.9% / -2.2% |
| JPM | 2026-08-31 | Underweight | -0.1% / -0.1% | -1.7% / -0.7% | -6.8% / -7.2% |
| JPM | 2026-09-14 | Underweight | -3.5% / -5.9% | -5.0% / -6.1% | -5.5% / -8.5% |
| JPM | 2026-09-28 | Underweight | -0.6% / -2.6% | -0.6% / -2.4% | +0.7% / +0.0% |
| MSFT | 2026-07-20 | Underweight | -1.1% / -0.1% | +23.9% / +20.8% | +21.1% / +18.5% |
| MSFT | 2026-08-03 | Underweight | +2.2% / +2.3% | -2.3% / -1.8% | +1.9% / +3.1% |
| MSFT | 2026-08-17 | Buy | +2.3% / +2.5% | +4.2% / +5.0% | +2.0% / +3.7% |
| MSFT | 2026-08-31 | Underweight | -1.9% / -2.0% | -2.1% / -1.1% | +2.4% / +2.0% |
| MSFT | 2026-09-14 | Underweight | +0.2% / -2.2% | +2.4% / +1.2% | +9.3% / +6.3% |
| MSFT | 2026-09-28 | Buy | +4.0% / +2.0% | +6.8% / +5.0% | +4.4% / +3.7% |
| NVDA | 2026-07-20 | Underweight | -5.0% / -4.0% | +2.2% / -0.8% | +6.0% / +3.4% |
| NVDA | 2026-08-03 | Buy | +2.6% / +2.7% | +3.7% / +4.2% | +2.6% / +3.8% |
| NVDA | 2026-08-17 | Underweight | -3.0% / -2.8% | -1.0% / -0.3% | -2.5% / -0.8% |
| NVDA | 2026-08-31 | Overweight | +2.9% / +2.8% | -1.5% / -0.5% | +5.1% / +4.8% |
| NVDA | 2026-09-14 | Buy | +7.9% / +5.5% | +7.1% / +5.9% | +7.7% / +4.7% |
| NVDA | 2026-09-28 | Buy | +5.3% / +3.3% | +0.6% / -1.2% | -4.1% / -4.8% |

## Scores

### Holding period: 5 trading days
Scored decisions: 30 (directional 28, Hold 2) · pending (window not over yet): 0

| Metric | Value | What it means |
|---|---|---|
| **Alpha hit rate** | 68% (19/28) | Buy/Overweight beat SPY, or Underweight/Sell lagged it |
| p-value vs coin flip | 0.04 | below 0.05 = unlikely to be luck |
| **Raw direction hit rate** | 71% (20/28) | the stock itself moved the way the call said |
| p-value vs coin flip | 0.02 | |
| Mean alpha of bullish calls | +1.22% | should be positive |
| Mean alpha of bearish calls | -0.75% | should be negative |
| **Long-short spread** | +1.97% | bullish minus bearish; > 0 = the ratings separate winners from losers |
| Avg alpha captured per call | +0.92% | following each call (long on bullish, short on bearish) |
| Baseline: stocks that beat SPY | 50% (15/30) | an 'always Buy' agent's alpha hit rate |
| Baseline: stocks that rose | 53% (16/30) | an 'always Buy' agent's raw hit rate |

| Rating | n | Mean raw return | Mean alpha | Alpha hit rate | Raw hit rate |
|---|---|---|---|---|---|
| Buy | 6 | +3.89% | +2.57% | 83% (5/6) | 100% (6/6) |
| Overweight | 4 | -1.06% | -0.80% | 50% (2/4) | 50% (2/4) |
| Hold | 1 | +1.26% | +1.36% | no direction | no direction |
| Underweight | 18 | -0.40% | -0.75% | 67% (12/18) | 67% (12/18) |

### Holding period: 10 trading days
Scored decisions: 30 (directional 28, Hold 2) · pending (window not over yet): 0

| Metric | Value | What it means |
|---|---|---|
| **Alpha hit rate** | 61% (17/28) | Buy/Overweight beat SPY, or Underweight/Sell lagged it |
| p-value vs coin flip | 0.17 | below 0.05 = unlikely to be luck |
| **Raw direction hit rate** | 61% (17/28) | the stock itself moved the way the call said |
| p-value vs coin flip | 0.17 | |
| Mean alpha of bullish calls | +2.56% | should be positive |
| Mean alpha of bearish calls | +0.23% | should be negative |
| **Long-short spread** | +2.33% | bullish minus bearish; > 0 = the ratings separate winners from losers |
| Avg alpha captured per call | +0.77% | following each call (long on bullish, short on bearish) |
| Baseline: stocks that beat SPY | 47% (14/30) | an 'always Buy' agent's alpha hit rate |
| Baseline: stocks that rose | 53% (16/30) | an 'always Buy' agent's raw hit rate |

| Rating | n | Mean raw return | Mean alpha | Alpha hit rate | Raw hit rate |
|---|---|---|---|---|---|
| Buy | 6 | +4.32% | +3.44% | 83% (5/6) | 100% (6/6) |
| Overweight | 4 | +1.32% | +1.24% | 25% (1/4) | 25% (1/4) |
| Hold | 1 | +1.60% | +2.11% | no direction | no direction |
| Underweight | 18 | +0.93% | +0.23% | 61% (11/18) | 56% (10/18) |

### Holding period: 20 trading days
Scored decisions: 30 (directional 28, Hold 2) · pending (window not over yet): 0

| Metric | Value | What it means |
|---|---|---|
| **Alpha hit rate** | 46% (13/28) | Buy/Overweight beat SPY, or Underweight/Sell lagged it |
| p-value vs coin flip | 0.71 | below 0.05 = unlikely to be luck |
| **Raw direction hit rate** | 46% (13/28) | the stock itself moved the way the call said |
| p-value vs coin flip | 0.71 | |
| Mean alpha of bullish calls | +1.68% | should be positive |
| Mean alpha of bearish calls | +1.23% | should be negative |
| **Long-short spread** | +0.45% | bullish minus bearish; > 0 = the ratings separate winners from losers |
| Avg alpha captured per call | -0.19% | following each call (long on bullish, short on bearish) |
| Baseline: stocks that beat SPY | 70% (21/30) | an 'always Buy' agent's alpha hit rate |
| Baseline: stocks that rose | 67% (20/30) | an 'always Buy' agent's raw hit rate |

| Rating | n | Mean raw return | Mean alpha | Alpha hit rate | Raw hit rate |
|---|---|---|---|---|---|
| Buy | 6 | +3.00% | +2.64% | 83% (5/6) | 83% (5/6) |
| Overweight | 4 | +0.62% | +0.24% | 50% (2/4) | 50% (2/4) |
| Hold | 1 | -0.72% | +0.52% | no direction | no direction |
| Underweight | 18 | +1.93% | +1.23% | 33% (6/18) | 33% (6/18) |
