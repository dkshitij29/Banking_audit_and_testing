# Experiment comparison: A vs B vs C

Cells all arms share: 30 (AAPL, AMZN, JPM, MSFT, NVDA; 2026-07-20 to 2026-09-28). Every number below uses only these cells, so the arms are scored on identical stock-date pairs.

## Rating mix

| Arm | Buy | Overweight | Hold | Underweight | Sell | Bearish share |
|---|---|---|---|---|---|---|
| A | 9 | 2 | 2 | 17 | 0 | 57% |
| B | 5 | 8 | 1 | 16 | 0 | 53% |
| C | 6 | 4 | 1 | 18 | 0 | 60% |

## Agreement between arms (same stock, same date)

| Pair | Same rating | Same direction (bullish / neutral / bearish) |
|---|---|---|
| A vs B | 33% (10/30) | 43% (13/30) |
| A vs C | 43% (13/30) | 57% (17/30) |
| B vs C | 40% (12/30) | 47% (14/30) |

A vs B is the noise floor: the same setup run twice. A later arm only shows a real effect if it moves further from the baseline than that.

## 5 trading days

| Arm | Alpha hit rate | Raw direction hit rate | Long-short spread | Avg alpha captured per call |
|---|---|---|---|---|
| A | 57% (16/28) | 68% (19/28) | +1.41% | +0.72% |
| B | 59% (17/29) | 52% (15/29) | -0.19% | -0.10% |
| C | 68% (19/28) | 71% (20/28) | +1.97% | +0.92% |

## 10 trading days

| Arm | Alpha hit rate | Raw direction hit rate | Long-short spread | Avg alpha captured per call |
|---|---|---|---|---|
| A | 50% (14/28) | 50% (14/28) | -2.17% | -1.29% |
| B | 52% (15/29) | 59% (17/29) | -0.18% | -0.19% |
| C | 61% (17/28) | 61% (17/28) | +2.33% | +0.77% |

## 20 trading days

| Arm | Alpha hit rate | Raw direction hit rate | Long-short spread | Avg alpha captured per call |
|---|---|---|---|---|
| A | 39% (11/28) | 43% (12/28) | -0.41% | -0.54% |
| B | 41% (12/29) | 38% (11/29) | -1.38% | -0.81% |
| C | 46% (13/28) | 46% (13/28) | +0.45% | -0.19% |