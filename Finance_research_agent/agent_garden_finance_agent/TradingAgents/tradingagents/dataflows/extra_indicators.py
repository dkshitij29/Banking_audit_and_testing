"""Optional trend/volume indicators, offered to the market analyst when
``extra_indicators`` is on (TRADINGAGENTS_EXTRA_INDICATORS=true).

The selection follows the expanded indicator set in BichengWang's TradingAgents
fork (https://github.com/BichengWang/TradingAgents), trimmed to what stockstats
computes natively: trend strength (ADX, +DI/-DI), trend direction (Supertrend),
volume confirmation (OBV), stretch from the mean (20-day z-score) and a faster
momentum oscillator (StochRSI). All are computed from bars on or before the
analysis date, like the default indicators, so they add no look-ahead.
"""

from tradingagents.dataflows.config import get_config

EXTRA_INDICATORS = {
    # Trend strength / direction
    "adx": (
        "ADX: Average Directional Index, the strength of the current trend regardless of direction. "
        "Usage: Above 25 means a strong trend, below 20 a weak or ranging market. "
        "Tips: Read with pdi/ndi for direction; adx rises in strong downtrends as well as uptrends."
    ),
    "pdi": (
        "+DI: Positive Directional Indicator, upward pressure. "
        "Usage: +DI above -DI (ndi) points to an uptrend; a crossover marks a possible trend change. "
        "Tips: Use with adx to judge whether that direction is strong enough to trade."
    ),
    "ndi": (
        "-DI: Negative Directional Indicator, downward pressure. "
        "Usage: -DI above +DI (pdi) points to a downtrend. "
        "Tips: Use with adx; a -DI lead with a low adx is a weak, unreliable downtrend."
    ),
    "supertrend": (
        "Supertrend: An ATR-based trailing line that flips with the trend. "
        "Usage: Price above the line = uptrend, below = downtrend; a flip marks a trend change. "
        "Tips: Lags in choppy markets; compare with supertrend_ub/supertrend_lb for the band the price is riding."
    ),
    "supertrend_ub": (
        "Supertrend Upper Band: The ATR band above price that acts as resistance in a downtrend. "
        "Usage: A close above it flips Supertrend to an uptrend. "
        "Tips: Read together with supertrend and supertrend_lb."
    ),
    "supertrend_lb": (
        "Supertrend Lower Band: The ATR band below price that acts as support in an uptrend. "
        "Usage: A close below it flips Supertrend to a downtrend. "
        "Tips: Read together with supertrend and supertrend_ub."
    ),
    # Volume
    "obv": (
        "OBV: On-Balance Volume, cumulative volume signed by the day's price direction. "
        "Usage: Rising OBV confirms buying behind a rise; OBV falling while price rises warns of weak participation. "
        "Tips: The level is arbitrary; read its direction and divergence from price."
    ),
    # Mean reversion / momentum
    "close_20_z": (
        "20-day Z-score: How many standard deviations the close is from its 20-day mean. "
        "Usage: Beyond +/-2 is statistically stretched; near 0 is at the mean. "
        "Tips: Stretched readings can persist in strong trends; confirm with adx before betting on reversion."
    ),
    "stochrsi": (
        "StochRSI: The stochastic oscillator applied to RSI, a faster momentum gauge (0-100). "
        "Usage: Above 80 overbought, below 20 oversold; crosses back through those levels flag turns. "
        "Tips: Very sensitive and noisy; do not select it together with rsi."
    ),
}


def extra_indicators_enabled() -> bool:
    return bool(get_config().get("extra_indicators"))


def extra_indicators_prompt() -> str:
    """The market analyst's menu section for the extra indicators, or '' when off."""
    if not extra_indicators_enabled():
        return ""
    groups = {
        "Trend Strength and Direction Indicators": ("adx", "pdi", "ndi", "supertrend", "supertrend_ub", "supertrend_lb"),
        "Additional Volume Indicators": ("obv",),
        "Mean Reversion and Fast Momentum Indicators": ("close_20_z", "stochrsi"),
    }
    lines = []
    for title, names in groups.items():
        lines.append(f"\n{title}:")
        lines += [f"- {name}: {EXTRA_INDICATORS[name]}" for name in names]
    return "\n".join(lines) + "\n"
