"""
app.py — Streamlit Frontend untuk Swing Trading Screener (Realtime)
"""

import streamlit as st
import pandas as pd
import os
import sys
import shutil
from datetime import datetime
import pytz

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import screener as screener_module
import fetch_data
import backtest

WIB = pytz.timezone("Asia/Jakarta")

CONFIG_FILE = "data/config.csv"

# ─── LOAD / SAVE CONFIG ───
def load_config() -> dict:
    """Load config dari file, fallback ke default jika tidak ada."""
    defaults = {
        "modal_input": float(backtest.MODAL),
        "comm_type":   "flat",
        "comm_input":  float(backtest.COMMISSION),
        "tp_input":    float(backtest.TP_PCT),
        "sl_input":    float(backtest.SL_PCT),
    }
    if not os.path.exists(CONFIG_FILE):
        return defaults
    try:
        df = pd.read_csv(CONFIG_FILE, index_col=0)
        cfg = df["value"].to_dict()
        return {
            "modal_input": float(cfg.get("modal_input", defaults["modal_input"])),
            "comm_type":   str(cfg.get("comm_type",   defaults["comm_type"])),
            "comm_input":  float(cfg.get("comm_input", defaults["comm_input"])),
            "tp_input":    float(cfg.get("tp_input",   defaults["tp_input"])),
            "sl_input":    float(cfg.get("sl_input",   defaults["sl_input"])),
        }
    except Exception:
        return defaults

def save_config(modal, comm_type, comm, tp, sl):
    """Simpan config ke file CSV."""
    os.makedirs("data", exist_ok=True)
    pd.DataFrame({
        "value": {
            "modal_input": modal,
            "comm_type":   comm_type,
            "comm_input":  comm,
            "tp_input":    tp,
            "sl_input":    sl,
        }
    }).to_csv(CONFIG_FILE)

# ─── SESSION STATE — load dari file saat pertama kali ───
_cfg = load_config()
if "modal_input" not in st.session_state: st.session_state.modal_input = _cfg["modal_input"]
if "comm_type"   not in st.session_state: st.session_state.comm_type   = _cfg["comm_type"]
if "comm_input"  not in st.session_state: st.session_state.comm_input  = _cfg["comm_input"]
if "tp_input"    not in st.session_state: st.session_state.tp_input    = _cfg["tp_input"]
if "sl_input"    not in st.session_state: st.session_state.sl_input    = _cfg["sl_input"]

# ─── KONFIGURASI — harus paling atas ───
st.set_page_config(
    page_title="Swing Trading Screener",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Auto-refresh setiap 60 detik — hanya jika data sudah ada
_has_data = (
    os.path.exists("data/screener.csv") and
    os.path.exists("data/historical") and
    os.path.exists(backtest.OUTPUT_FILE)
)
if _has_data:
    st.markdown('<meta http-equiv="refresh" content="60">', unsafe_allow_html=True)


# ─── HELPER FUNCTIONS ───
@st.cache_data(ttl=60)
def get_ranking_data():
    if not os.path.exists(backtest.OUTPUT_FILE):
        return None
    return pd.read_csv(backtest.OUTPUT_FILE)

@st.cache_data(ttl=60)
def get_entry_signals(modal: float = backtest.MODAL, commission: float = backtest.COMMISSION,
                      commission_type: str = backtest.COMMISSION_TYPE,
                      tp_pct: float = backtest.TP_PCT, sl_pct: float = backtest.SL_PCT):
    return backtest.check_entry_signals(modal=modal, commission=commission,
                                        commission_type=commission_type,
                                        tp_pct=tp_pct, sl_pct=sl_pct)

def run_pipeline():
    with st.status("Running pipeline...", expanded=True) as status:

        # Step 1: Screener
        status.write("📡 Step 1: Fetching from TradingView...")
        df_screener, _ = screener_module.fetch_tradingview_screener(limit=100)
        if df_screener is None or df_screener.empty:
            st.error("❌ Screener gagal")
            return False
        status.update(label="✅ Screener selesai", state="complete")

        # Step 2: Hapus data lama + fetch ulang
        import shutil
        if os.path.exists("data/historical"):
            shutil.rmtree("data/historical")
        if os.path.exists(backtest.OUTPUT_FILE):
            os.remove(backtest.OUTPUT_FILE)

        status.write("📥 Step 2: Downloading historical data...")
        ok = fetch_data.run()
        if not ok:
            st.error("❌ Fetch data gagal")
            return False
        status.update(label="✅ Data downloaded", state="complete")

        # Step 3: Backtest
        status.write("🔬 Step 3: Running backtest...")
        backtest.main(modal=modal_input, commission=comm_input, commission_type=comm_type,
                      tp_pct=tp_input, sl_pct=sl_input)
        get_ranking_data.clear()
        get_entry_signals.clear()
        status.update(label="✅ Pipeline selesai", state="complete")
        return True


# ─── SIDEBAR ───
st.sidebar.title("📈 Swing Trading Screener")
st.sidebar.markdown("---")

# Settings didefinisikan DULU sebelum tombol pipeline
st.sidebar.subheader("⚙️ Settings")

modal_input = st.sidebar.number_input(
    "Modal per trade ($)", min_value=1.0, value=st.session_state.modal_input,
    step=1.0, key="modal_input"
)

comm_type = st.sidebar.radio(
    "Tipe biaya admin", options=["flat", "pct"],
    format_func=lambda x: "Flat ($ tetap)" if x == "flat" else "Persentase (%)",
    horizontal=True, index=0 if st.session_state.comm_type == "flat" else 1,
    key="comm_type"
)

if comm_type == "flat":
    comm_input = st.sidebar.number_input(
        "Biaya admin ($)", min_value=0.0, value=st.session_state.comm_input,
        step=0.01, format="%.4f", key="comm_input"
    )
else:
    comm_input = st.sidebar.number_input(
        "Biaya admin (%)", min_value=0.0, value=st.session_state.comm_input,
        step=0.01, format="%.2f", key="comm_input"
    )

comm_label = f"${comm_input}" if comm_type == "flat" else f"{comm_input}%"

# ─── TP / SL input ───
st.sidebar.markdown("---")
tp_input = st.sidebar.number_input(
    "Take Profit (%)", min_value=0.1, value=st.session_state.tp_input,
    step=0.1, format="%.1f", key="tp_input"
)
sl_input = st.sidebar.number_input(
    "Stop Loss (%)", min_value=0.1, value=st.session_state.sl_input,
    step=0.1, format="%.1f", key="sl_input"
)

# Hitung TP bersih
if comm_type == "pct":
    actual_comm = modal_input * (comm_input / 100)
else:
    actual_comm = comm_input

gross_tp   = modal_input * (tp_input / 100)
net_tp     = gross_tp - actual_comm
net_tp_pct = (net_tp / modal_input) * 100

gross_sl   = modal_input * (sl_input / 100)
net_sl     = gross_sl + actual_comm
net_sl_pct = (net_sl / modal_input) * 100

st.sidebar.info(
    f"TP {tp_input}% → gross **${gross_tp:.2f}** → bersih **${net_tp:.2f}** ({net_tp_pct:.2f}%)\n\n"
    f"SL {sl_input}% → loss **-${gross_sl:.2f}** → total loss **-${net_sl:.2f}** (-{net_sl_pct:.2f}%)"
)

st.sidebar.caption(f"Modal: **${modal_input}** | Biaya: **{comm_label}** | Max Hold: **{backtest.MAX_HOLD_DAYS} hari**")

if st.sidebar.button("💾 Save Settings", use_container_width=True):
    save_config(modal_input, comm_type, comm_input, tp_input, sl_input)
    st.sidebar.success("✅ Settings tersimpan!")

st.sidebar.markdown("---")
st.sidebar.subheader("Pipeline")

if st.sidebar.button("🚀 Run Full Pipeline", type="primary", use_container_width=True):
    save_config(modal_input, comm_type, comm_input, tp_input, sl_input)
    run_pipeline()
    st.rerun()

st.sidebar.markdown("---")
st.sidebar.subheader("Data Management")

if st.sidebar.button("🗑️ Hapus Folder Data", use_container_width=True):
    deleted = []
    if os.path.exists("data/historical"):
        shutil.rmtree("data/historical")
        deleted.append("data/historical/")
    if os.path.exists(backtest.OUTPUT_FILE):
        os.remove(backtest.OUTPUT_FILE)
        deleted.append(backtest.OUTPUT_FILE)
    if os.path.exists("data/screener.csv"):
        os.remove("data/screener.csv")
        deleted.append("data/screener.csv")
    if deleted:
        st.sidebar.success(f"✅ Dihapus: {', '.join(deleted)}")
        get_ranking_data.clear()
        get_entry_signals.clear()
        st.rerun()
    else:
        st.sidebar.info("Tidak ada data untuk dihapus.")

st.sidebar.caption("Screener → Hapus data lama → Fetch → Backtest")


# ─── MAIN CONTENT ───
st.title("📊 Dashboard Trading")

df_rank    = get_ranking_data()
df_signals = get_entry_signals(modal=modal_input, commission=comm_input,
                               commission_type=comm_type,
                               tp_pct=tp_input, sl_pct=sl_input)

ready_count = 0
if df_signals is not None and not df_signals.empty:
    ready_count = len(df_signals[df_signals["signal"].isin(["BUY", "SELL"])])

col1, col2, col3 = st.columns(3)
col1.metric("Last Update", datetime.now(WIB).strftime("%H:%M:%S WIB"))
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
