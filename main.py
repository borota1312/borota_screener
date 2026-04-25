"""
main.py — Orchestrator pipeline trading
Skema: screener.py → fetch_data.py → backtest.py
"""

import sys
import screener as screener_module
import fetch_data
import backtest


def main():
    print("\n" + "=" * 60)
    print("  SWING TRADING PIPELINE")
    print("  Beli Senin → Jual Jumat | Target bersih ~3%")
    print("=" * 60 + "\n")

    # ─── STEP 1: SCREENER ───
    print("📡 STEP 1: Screener TradingView...\n")
    df_screener, screener_path = screener_module.fetch_tradingview_screener(
        limit=100,
        symbols=["SYML:SP;SPX", "SYML:NASDAQ;NDX", "SYML:DJ;DJI"],
    )

    if df_screener is None or df_screener.empty:
        print("❌ Screener gagal. Pipeline berhenti.")
        sys.exit(1)

    print(f"\n✅ Screener selesai: {len(df_screener)} saham → {screener_path}\n")

    # ─── STEP 2: FETCH DATA ───
    print("=" * 60)
    print("📥 STEP 2: Download Historical Data...\n")
    ok = fetch_data.run()

    if not ok:
        print("❌ Fetch data gagal. Pipeline berhenti.")
        sys.exit(1)

    # ─── STEP 3: BACKTEST ───
    print("=" * 60)
    print("🔬 STEP 3: Backtest & Ranking...\n")
    backtest.main()

    # ─── STEP 4: CEK SINYAL ENTRY HARI INI ───
    print("=" * 60)
    df_signals = backtest.check_entry_signals()
    if not df_signals.empty:
        backtest.print_entry_signals(df_signals)

    print("\n" + "=" * 60)
    print("🎉 PIPELINE SELESAI!")
    print("   📄 Screener   → data/screener.csv")
    print("   📁 Historical → data/historical/")
    print("   🏆 Ranking    → data/ranking.csv")
    print("=" * 60 + "\n")


if __name__ == "__main__":
    main()
