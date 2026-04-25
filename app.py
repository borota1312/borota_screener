"""
app.py — Streamlit Frontend untuk Swing Trading Screener (Realtime)
"""

import streamlit as st
import pandas as pd
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import screener as screener_module
import fetch_data
import backtest

# ─── KONFIGURASI — harus paling atas ───
st.set_page_config(
    page_title="Swing Trading Screener",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Auto-refresh setiap 60 detik via HTML meta tag
st.markdown(
    '<meta http-equiv="refresh" content="60">',
    unsafe_allow_html=True
)


# ─── HELPER FUNCTIONS ───
@st.cache_data(ttl=60)
def get_ranking_data():
    if not os.path.exists(backtest.OUTPUT_FILE):
        return None
    return pd.read_csv(backtest.OUTPUT_FILE)

@st.cache_data(ttl=60)
def get_entry_signals():
    return backtest.check_entry_signals()

def run_pipeline():
    with st.status("Running pipeline...", expanded=True) as status:
        status.write("📡 Fetching from TradingView...")
        df_screener, _ = screener_module.fetch_tradingview_screener(limit=100)
        if df_screener is None or df_screener.empty:
            st.error("❌ Screener gagal")
            return False
        status.update(label="✅ Screener selesai", state="complete")

        status.write("📥 Downloading historical data...")
        ok = fetch_data.run()
        if not ok:
            st.error("❌ Fetch data gagal")
            return False
        status.update(label="✅ Data downloaded", state="complete")

        status.write("🔬 Running backtest...")
        backtest.main()
        get_ranking_data.clear()
        get_entry_signals.clear()
        status.update(label="✅ Pipeline selesai", state="complete")
        return True


# ─── SIDEBAR ───
st.sidebar.title("📈 Swing Trading Screener")
st.sidebar.markdown("---")
st.sidebar.subheader("Pipeline")
if st.sidebar.button("🚀 Run Full Pipeline", type="primary", use_container_width=True):
    run_pipeline()
    st.rerun()

st.sidebar.markdown("---")
st.sidebar.subheader("Settings")
st.sidebar.write(f"Modal: **${backtest.MODAL}**")
st.sidebar.write(f"TP: **{backtest.TP_PCT}%**")
st.sidebar.write(f"SL: **{backtest.SL_PCT}%**")
st.sidebar.write(f"Max Hold: **{backtest.MAX_HOLD_DAYS} hari**")
st.sidebar.markdown("---")
st.sidebar.caption("Auto-refresh: 60 detik | Cache: 60 detik")


# ─── MAIN CONTENT ───
st.title("📊 Dashboard Trading")

df_rank    = get_ranking_data()
df_signals = get_entry_signals()

ready_count = 0
if df_signals is not None and not df_signals.empty:
    ready_count = len(df_signals[df_signals["signal"].isin(["BUY", "SELL"])])

col1, col2, col3 = st.columns(3)
col1.metric("Last Update", datetime.now().strftime("%H:%M:%S"))
col2.metric("Ranking Stocks", len(df_rank) if df_rank is not None else 0)
col3.metric("Ready to Entry", ready_count)

tab1, tab2, tab3 = st.tabs(["📈 Ranking", "🎯 Entry Signals", "📊 History"])

# ─── TAB 1: RANKING ───
with tab1:
    st.header("🏆 Top Ranked Stocks")
    if df_rank is None:
        st.info("⚠️ Belum ada data ranking. Jalankan pipeline dulu.")
    else:
        st.dataframe(
            df_rank.style
            .format({"score": "{:.2f}", "win_rate": "{:.1f}%", "net_pnl_total": "${:.2f}"})
            .highlight_max(subset=["score"], color="#76c950")
            .highlight_min(subset=["score"], color="#e74c3c"),
            width="stretch"
        )
        if len(df_rank) >= 3:
            c1, c2, c3 = st.columns(3)
            for col, row in zip([c1, c2, c3], df_rank.head(3).itertuples()):
                with col:
                    st.metric(
                        label=f"#{row.rank} {row.ticker}",
                        value=f"Score: {row.score:.1f}",
                        delta=f"WR: {row.win_rate:.1f}%"
                    )
                    st.caption(f"Net: ${row.net_pnl_total:.2f} | PF: {row.profit_factor}")

# ─── TAB 2: ENTRY SIGNALS ───
with tab2:
    st.header("🎯 Sinyal Entry Hari Ini")
    if df_signals is None or df_signals.empty:
        st.info("⏳ Belum ada saham yang memenuhi kondisi entry saat ini.")
    else:
        ready = df_signals[df_signals["signal"].isin(["BUY", "SELL"])]
        wait  = df_signals[df_signals["signal"] == "WAIT"]

        if ready.empty:
            st.warning("⏳ Belum ada saham yang siap entry. Tunggu sinyal breakout.")
        else:
            st.success(f"✅ {len(ready)} saham SIAP ENTRY:")
            for _, r in ready.iterrows():
                arrow = "🟢 BUY" if r["signal"] == "BUY" else "🔴 SELL"
                with st.container(border=True):
                    st.markdown(f"**{arrow} {r['ticker']}** — Rank #{r['rank']} | Score: {r['score']}")
                    c1, c2, c3, c4 = st.columns(4)
                    c1.metric("Harga", f"${r['price']}")
                    c2.metric("TP", f"${r['tp_target']}")
                    c3.metric("SL", f"${r['sl_level']}")
                    c4.metric("Net jika TP", f"${r['net_if_tp']}")
                    st.caption(f"WR historis: {r['win_rate']}%")

        if not wait.empty:
            st.warning(f"⏳ Menunggu sinyal: {', '.join(wait['ticker'].tolist())}")

# ─── TAB 3: HISTORY ───
with tab3:
    st.header("📜 Riwayat Backtest")
    if df_rank is None:
        st.info("Belum ada data backtest.")
    else:
        st.dataframe(
            df_rank[["rank", "ticker", "total_trades", "win_rate",
                     "net_pnl_total", "profit_factor", "sharpe",
                     "tp_hits", "sl_hits", "maxhold_exits"]],
            width="stretch",
            hide_index=True
        )
