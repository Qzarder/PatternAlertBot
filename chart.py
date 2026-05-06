import io
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd
import mplfinance as mpf
from patterns import PatternType


def generate_chart(candles: list, symbol: str, timeframe: str,
                   pattern_type: PatternType) -> io.BytesIO | None:
    if len(candles) < 3:
        return None

    df = pd.DataFrame(candles, columns=["Date", "Open", "High", "Low", "Close", "Volume"])
    df["Date"] = pd.to_datetime(df["Date"], unit="ms")
    df.set_index("Date", inplace=True)

    if pattern_type == PatternType.MORNING_STAR:
        hl_color = "#22c55e"
        label = "MORNING STAR"
    else:
        hl_color = "#ef4444"
        label = "EVENING STAR"

    mc = mpf.make_marketcolors(
        up="#26a69a", down="#ef5350",
        edge="inherit", wick="inherit", volume="inherit",
    )
    style = mpf.make_mpf_style(
        base_mpf_style="charles", marketcolors=mc, gridstyle=":",
        gridcolor="#e0e0e0", facecolor="#fafafa",
    )

    fig, axes = mpf.plot(
        df, type="candle", style=style, volume=True,
        title=f"{symbol}  {timeframe}",
        returnfig=True, figsize=(14, 7),
        datetime_format="%d.%m %H:%M",
        xrotation=30,
        panel_ratios=(3, 1),
    )

    ax = axes[0]
    n = len(df)
    ax.axvspan(n - 3.5, n - 0.5, alpha=0.15, color=hl_color, zorder=0)

    y_min, y_max = ax.get_ylim()
    y_text = y_max + (y_max - y_min) * 0.02
    ax.text(n - 2, y_text, label, ha="center", va="bottom",
            fontsize=11, fontweight="bold", color=hl_color,
            bbox=dict(boxstyle="round,pad=0.3", facecolor="white",
                      edgecolor=hl_color, alpha=0.9))

    for i in range(max(0, n - 3), n):
        x = i
        o = df["Open"].iloc[i]
        c = df["Close"].iloc[i]
        body_bottom = min(o, c)
        body_top = max(o, c)
        color = "#22c55e" if c >= o else "#ef4444"
        ax.add_patch(plt.Rectangle((x - 0.4, body_bottom), 0.8, body_top - body_bottom,
                                    linewidth=2, edgecolor=color, facecolor="none", zorder=5))
        ax.add_patch(plt.Rectangle((x - 0.4, body_bottom), 0.8, body_top - body_bottom,
                                    linewidth=0, facecolor=color, alpha=0.15, zorder=4))

    ax.set_ylim(y_min, y_max + (y_max - y_min) * 0.08)

    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=120, bbox_inches="tight", pad_inches=0.2)
    plt.close(fig)
    buf.seek(0)
    return buf
