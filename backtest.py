"""
Backtester untuk strategi SR Multi-TF BuySell
Sesuai Pine Script: pivot H4 entry, filter EMA daily, SL/TP, max hold 4 hari
Biaya: $0.27 flat per order (beli + jual)
Modal: $24 — fractional shares (GoTrade), qty = 24 / harga entry
"""

import os
import pandas as pd
import numpy as np


# ─── PARAMETER ───
LOOKBACK_H4   = 18       # pivot lookback H4
SL_PCT        = 2.0      # stop loss %
TP_PCT        = 4.5      # take profit % gross
MODAL         = 24.0     # total modal per trade ($)
COMMISSION    = 0.27     # biaya flat per order (beli+jual = $0.27 total)
COMMISSION_TYPE = "flat" # "flat" = dollar tetap | "pct" = persentase dari modal
MAX_HOLD_DAYS = 4        # maksimal holding (Senin → Jumat)
DATA_DIR      = "data/historical"
OUTPUT_FILE   = "data/ranking.csv"


# ─── HELPER: PIVOT HIGH / LOW ───
def calc_pivots(high: pd.Series, low: pd.Series, lookback: int):
    ph = pd.Series(np.nan, index=high.index)
    pl = pd.Series(np.nan, index=low.index)
    lb = lookback
    for i in range(lb, len(high) - lb):
        window_h = high.iloc[i - lb: i + lb + 1]
        window_l = low.iloc[i - lb: i + lb + 1]
        if high.iloc[i] == window_h.max():
            ph.iloc[i] = high.iloc[i]
        if low.iloc[i] == window_l.min():
            pl.iloc[i] = low.iloc[i]
    return ph, pl


# ─── HELPER: RESAMPLE KE 4H DAN DAILY ───
def resample_ohlcv(df: pd.DataFrame, rule: str) -> pd.DataFrame:
    agg = {"Open": "first", "High": "max", "Low": "min", "Close": "last", "Volume": "sum"}
    return df.resample(rule).agg(agg).dropna()


# ─── BACKTEST SATU SAHAM ───
def backtest(ticker: str, df_1h: pd.DataFrame,
             modal: float = None, commission: float = None,
             commission_type: str = None,
             tp_pct: float = None, sl_pct: float = None) -> dict:
    modal           = modal           if modal           is not None else MODAL
    commission      = commission      if commission      is not None else COMMISSION
    commission_type = commission_type if commission_type is not None else COMMISSION_TYPE
    tp_pct          = tp_pct          if tp_pct          is not None else TP_PCT
    sl_pct          = sl_pct          if sl_pct          is not None else SL_PCT
    if df_1h.empty or len(df_1h) < 50:
        return None

    # Pastikan index datetime dengan timezone
    if df_1h.index.tz is None:
        df_1h.index = df_1h.index.tz_localize("UTC")

    # Resample
    df_h4    = resample_ohlcv(df_1h, "4h")
    df_daily = resample_ohlcv(df_1h, "1D")

    if len(df_h4) < LOOKBACK_H4 * 2 + 5:
        return None

    # ─── Pivot H4 ───
    ph_h4, pl_h4 = calc_pivots(df_h4["High"], df_h4["Low"], LOOKBACK_H4)
    df_h4["res"] = ph_h4.ffill()
    df_h4["sup"] = pl_h4.ffill()

    # ─── EMA 20 Daily ───
    df_daily["ema20"] = df_daily["Close"].ewm(span=20, adjust=False).mean()

    # ─── Align daily ke H4 (forward fill) ───
    df_h4["ema20_d"] = df_daily["ema20"].reindex(df_h4.index, method="ffill")
    df_h4["close_d"] = df_daily["Close"].reindex(df_h4.index, method="ffill")

    # ─── Sinyal ───
    # buy_raw: close crossover resistance H4
    prev_close = df_h4["Close"].shift(1)
    prev_res   = df_h4["res"].shift(1)
    prev_sup   = df_h4["sup"].shift(1)

    df_h4["buy_raw"]  = (prev_close <= prev_res) & (df_h4["Close"] > df_h4["res"])
    df_h4["sell_raw"] = (prev_close >= prev_sup) & (df_h4["Close"] < df_h4["sup"])

    # Filter: close daily > EMA20 daily
    df_h4["bull"] = df_h4["close_d"] > df_h4["ema20_d"]
    df_h4["bear"] = df_h4["close_d"] < df_h4["ema20_d"]

    df_h4["buy"]  = df_h4["buy_raw"]  & df_h4["bull"]
    df_h4["sell"] = df_h4["sell_raw"] & df_h4["bear"]

    # ─── Simulasi Trade ───
    trades = []
    position = None  # {"side", "entry_price", "entry_date", "sl", "tp"}

    for i in range(1, len(df_h4)):
        bar      = df_h4.iloc[i]
        bar_date = df_h4.index[i]
        price    = bar["Close"]

        # Cek exit jika ada posisi
        if position is not None:
            days_held = (bar_date - position["entry_date"]).days
            exit_price  = None
            exit_reason = None

            if position["side"] == "long":
                if bar["Low"] <= position["sl"]:
                    exit_price  = position["sl"]
                    exit_reason = "SL"
                elif bar["High"] >= position["tp"]:
                    exit_price  = position["tp"]
                    exit_reason = "TP"
                elif days_held >= MAX_HOLD_DAYS:
                    exit_price  = price
                    exit_reason = "MaxHold"

            elif position["side"] == "short":
                if bar["High"] >= position["sl"]:
                    exit_price  = position["sl"]
                    exit_reason = "SL"
                elif bar["Low"] <= position["tp"]:
                    exit_price  = position["tp"]
                    exit_reason = "TP"
                elif days_held >= MAX_HOLD_DAYS:
                    exit_price  = price
                    exit_reason = "MaxHold"

            if exit_price is not None:
                if position["side"] == "long":
                    gross_pnl = (exit_price - position["entry_price"]) * position["qty"]
                else:
                    gross_pnl = (position["entry_price"] - exit_price) * position["qty"]

                # Hitung komisi sesuai tipe
                if commission_type == "pct":
                    actual_commission = modal * (commission / 100)
                else:
                    actual_commission = commission

                net_pnl = gross_pnl - actual_commission
                trades.append({
                    "entry_date":  position["entry_date"],
                    "exit_date":   bar_date,
                    "side":        position["side"],
                    "entry_price": position["entry_price"],
                    "exit_price":  exit_price,
                    "qty":         position["qty"],
                    "days_held":   days_held,
                    "gross_pnl":   round(gross_pnl, 4),
                    "net_pnl":     round(net_pnl, 4),
                    "exit_reason": exit_reason,
                })
                position = None

        # Entry baru jika tidak ada posisi
        if position is None:
            if bar["buy"]:
                qty = modal / price
                position = {
                    "side":        "long",
                    "entry_price": price,
                    "entry_date":  bar_date,
                    "sl":          price * (1 - sl_pct / 100),
                    "tp":          price * (1 + tp_pct / 100),
                    "qty":         qty,
                }
            elif bar["sell"]:
                qty = modal / price
                position = {
                    "side":        "short",
                    "entry_price": price,
                    "entry_date":  bar_date,
                    "sl":          price * (1 + sl_pct / 100),
                    "tp":          price * (1 - tp_pct / 100),
                    "qty":         qty,
                }

    if not trades:
        return None

    df_trades = pd.DataFrame(trades)
    total     = len(df_trades)
    wins      = (df_trades["net_pnl"] > 0).sum()
    win_rate  = wins / total * 100
    net_total = df_trades["net_pnl"].sum()
    avg_net   = df_trades["net_pnl"].mean()
    avg_days  = df_trades["days_held"].mean()

    # Profit factor
    gross_wins   = df_trades.loc[df_trades["net_pnl"] > 0, "net_pnl"].sum()
    gross_losses = abs(df_trades.loc[df_trades["net_pnl"] <= 0, "net_pnl"].sum())
    profit_factor = round(gross_wins / gross_losses, 3) if gross_losses > 0 else 999

    # Sharpe (per trade)
    std = df_trades["net_pnl"].std()
    sharpe = round(avg_net / std * np.sqrt(total), 3) if std > 0 else 0

    # ─── Composite Score ───
    # Bobot: win_rate 30%, profit_factor 30%, sharpe 20%, avg_net 20%
    # Dinormalisasi saat ranking semua saham
    return {
        "ticker":        ticker,
        "total_trades":  total,
        "win_rate":      round(win_rate, 2),
        "net_pnl_total": round(net_total, 4),
        "avg_net_pnl":   round(avg_net, 4),
        "profit_factor": profit_factor,
        "sharpe":        sharpe,
        "avg_days_held": round(avg_days, 2),
        "tp_hits":       (df_trades["exit_reason"] == "TP").sum(),
        "sl_hits":       (df_trades["exit_reason"] == "SL").sum(),
        "maxhold_exits": (df_trades["exit_reason"] == "MaxHold").sum(),
    }


# ─── COMPOSITE SCORE ───
def compute_score(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()

    def norm(s, asc=True):
        mn, mx = s.min(), s.max()
        if mx == mn:
            return pd.Series(50.0, index=s.index)
        n = (s - mn) / (mx - mn) * 100
        return n if asc else 100 - n

    df["score"] = (
        norm(df["win_rate"],      asc=True)  * 0.30 +
        norm(df["profit_factor"], asc=True)  * 0.30 +
        norm(df["sharpe"],        asc=True)  * 0.20 +
        norm(df["avg_net_pnl"],   asc=True)  * 0.20
    ).round(2)

    df = df.sort_values("score", ascending=False).reset_index(drop=True)
    df.insert(0, "rank", range(1, len(df) + 1))
    return df


# ─── MAIN ───
def main(modal: float = None, commission: float = None, commission_type: str = None,
         tp_pct: float = None, sl_pct: float = None):
    modal           = modal           if modal           is not None else MODAL
    commission      = commission      if commission      is not None else COMMISSION
    commission_type = commission_type if commission_type is not None else COMMISSION_TYPE
    tp_pct          = tp_pct          if tp_pct          is not None else TP_PCT
    sl_pct          = sl_pct          if sl_pct          is not None else SL_PCT

    comm_label = f"${commission} flat" if commission_type == "flat" else f"{commission}% dari modal"
    print("=" * 60)
    print("BACKTESTER — SR Multi-TF BuySell")
    print(f"SL: {SL_PCT}% | TP: {TP_PCT}% | Modal: ${modal} | Biaya: {comm_label}")
    print(f"Max hold: {MAX_HOLD_DAYS} hari | Qty: fractional (${modal} / harga entry)")
    print("=" * 60)

    files = [f for f in os.listdir(DATA_DIR) if f.endswith("_historical.csv")]
    if not files:
        print(f"Tidak ada file di {DATA_DIR}")
        return

    results = []
    for fname in sorted(files):
        ticker = fname.replace("_historical.csv", "")
        path   = os.path.join(DATA_DIR, fname)

        try:
            df = pd.read_csv(path, index_col=0, parse_dates=True)
            df.columns = [c.strip() for c in df.columns]
            result = backtest(ticker, df, modal=modal, commission=commission,
                              commission_type=commission_type,
                              tp_pct=tp_pct, sl_pct=sl_pct)
            if result:
                results.append(result)
                print(f"  ✅ {ticker:6s} | {result['total_trades']:3d} trades | "
                      f"WR: {result['win_rate']:5.1f}% | "
                      f"Net: ${result['net_pnl_total']:6.2f} | "
                      f"PF: {result['profit_factor']}")
            else:
                print(f"  ⚠️  {ticker:6s} | tidak cukup data / tidak ada trade")
        except Exception as e:
            print(f"  ❌ {ticker}: {e}")

    if not results:
        print("\nTidak ada hasil backtest.")
        return

    df_results = pd.DataFrame(results)
    df_ranked  = compute_score(df_results)

    df_ranked.to_csv(OUTPUT_FILE, index=False)

    print(f"\n{'=' * 60}")
    print(f"RANKING — {len(df_ranked)} saham (disimpan ke {OUTPUT_FILE})")
    print(f"{'=' * 60}")
    print(df_ranked[["rank", "ticker", "score", "win_rate", "net_pnl_total",
                      "profit_factor", "sharpe", "total_trades"]].to_string(index=False))


# ─── CEK SINYAL ENTRY HARI INI ───
def check_entry_signals(ranking_file: str = OUTPUT_FILE, data_dir: str = DATA_DIR,
                        modal: float = None, commission: float = None,
                        commission_type: str = None,
                        tp_pct: float = None, sl_pct: float = None) -> pd.DataFrame:
    modal           = modal           if modal           is not None else MODAL
    commission      = commission      if commission      is not None else COMMISSION
    commission_type = commission_type if commission_type is not None else COMMISSION_TYPE
    tp_pct          = tp_pct          if tp_pct          is not None else TP_PCT
    sl_pct          = sl_pct          if sl_pct          is not None else SL_PCT
    """
    Cek saham mana yang saat ini memenuhi kondisi entry:
    1. Close H4 terbaru breakout di atas resistance H4
    2. Close daily > EMA 20 daily
    Hanya tampilkan saham yang ada di ranking.
    """
    if not os.path.exists(ranking_file):
        print("⚠️  ranking.csv tidak ditemukan, jalankan backtest dulu.")
        return pd.DataFrame()

    df_rank = pd.read_csv(ranking_file)
    signals = []

    for _, row in df_rank.iterrows():
        ticker = row["ticker"]
        path   = os.path.join(data_dir, f"{ticker}_historical.csv")

        if not os.path.exists(path):
            continue

        try:
            df = pd.read_csv(path, index_col=0, parse_dates=True)
            df.columns = [c.strip() for c in df.columns]

            if df.index.tz is None:
                df.index = df.index.tz_localize("UTC")

            df_h4    = resample_ohlcv(df, "4h")
            df_daily = resample_ohlcv(df, "1D")

            if len(df_h4) < LOOKBACK_H4 * 2 + 5:
                continue

            # Pivot H4
            ph_h4, pl_h4 = calc_pivots(df_h4["High"], df_h4["Low"], LOOKBACK_H4)
            df_h4["res"] = ph_h4.ffill()
            df_h4["sup"] = pl_h4.ffill()

            # EMA 20 daily
            df_daily["ema20"] = df_daily["Close"].ewm(span=20, adjust=False).mean()
            df_h4["ema20_d"]  = df_daily["ema20"].reindex(df_h4.index, method="ffill")
            df_h4["close_d"]  = df_daily["Close"].reindex(df_h4.index, method="ffill")

            # Ambil bar terakhir
            last      = df_h4.iloc[-1]
            prev      = df_h4.iloc[-2]
            price     = last["Close"]
            res       = last["res"]
            sup       = last["sup"]
            ema20_d   = last["ema20_d"]
            close_d   = last["close_d"]

            # Cek kondisi entry
            breakout_buy  = (prev["Close"] <= res) and (price > res)
            breakout_sell = (prev["Close"] >= sup) and (price < sup)
            bull_filter   = close_d > ema20_d
            bear_filter   = close_d < ema20_d

            can_buy  = breakout_buy  and bull_filter
            can_sell = breakout_sell and bear_filter

            # Hitung level SL/TP
            tp_buy = price * (1 + tp_pct / 100)
            sl_buy = price * (1 - sl_pct / 100)
            if commission_type == "pct":
                actual_commission = modal * (commission / 100)
            else:
                actual_commission = commission
            net_if_tp = (tp_buy - price) * (modal / price) - actual_commission

            signals.append({
                "rank":        int(row["rank"]),
                "ticker":      ticker,
                "score":       row["score"],
                "price":       round(price, 4),
                "signal":      "BUY" if can_buy else ("SELL" if can_sell else "WAIT"),
                "res_h4":      round(res, 4) if not np.isnan(res) else None,
                "sup_h4":      round(sup, 4) if not np.isnan(sup) else None,
                "ema20_daily": round(ema20_d, 4) if not np.isnan(ema20_d) else None,
                "bull_filter": bull_filter,
                "tp_target":   round(tp_buy, 4),
                "sl_level":    round(sl_buy, 4),
                "net_if_tp":   round(net_if_tp, 4),
                "win_rate":    row["win_rate"],
            })

        except Exception as e:
            print(f"  ⚠️  {ticker}: {e}")
            continue

    if not signals:
        return pd.DataFrame()

    df_sig = pd.DataFrame(signals)
    return df_sig


def print_entry_signals(df_sig: pd.DataFrame):
    """Tampilkan rekomendasi entry hari ini."""
    print("\n" + "=" * 60)
    print("📊 REKOMENDASI ENTRY HARI INI")
    print(f"   Modal: ${MODAL} | TP: {TP_PCT}% | SL: {SL_PCT}% | Max hold: {MAX_HOLD_DAYS} hari")
    print("=" * 60)

    ready = df_sig[df_sig["signal"].isin(["BUY", "SELL"])]
    wait  = df_sig[df_sig["signal"] == "WAIT"]

    if ready.empty:
        print("\n⏳ Belum ada saham yang memenuhi kondisi entry saat ini.")
        print("   Tunggu sinyal breakout H4 + konfirmasi EMA daily.\n")
    else:
        print(f"\n✅ {len(ready)} saham SIAP ENTRY:\n")
        for _, r in ready.iterrows():
            arrow = "🟢 BUY " if r["signal"] == "BUY" else "🔴 SELL"
            print(f"  {arrow} {r['ticker']:6s} | Rank #{r['rank']} | Score: {r['score']}")
            print(f"         Harga: ${r['price']} | TP: ${r['tp_target']} | SL: ${r['sl_level']}")
            print(f"         Net jika TP: ${r['net_if_tp']} | WR historis: {r['win_rate']}%")
            print()

    if not wait.empty:
        print(f"⏳ {len(wait)} saham menunggu sinyal: {', '.join(wait['ticker'].tolist())}\n")


if __name__ == "__main__":
    main()
    df_signals = check_entry_signals()
    if not df_signals.empty:
        print_entry_signals(df_signals)
