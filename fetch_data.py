"""
fetch_data.py — Download data historis dari Yahoo Finance
Baca ticker dari data/screener.csv, simpan ke data/historical/
Data selalu dipotong sampai 16:00 ET (market close US) hari terakhir
agar hasil konsisten antara lokal dan Streamlit Cloud.
"""

import shutil
import yfinance as yf
import pandas as pd
import os
from datetime import datetime, time
import pytz


# ─── KONFIGURASI ───
SCREENER_FILE  = "data/screener.csv"
OUTPUT_FOLDER  = "data/historical"
TOP_N          = 10
PERIOD         = "1y"
INTERVAL       = "1h"

# Cutoff: data hanya sampai 16:00 ET (NYSE market close)
CUTOFF_HOUR_ET = 16
ET_TZ          = pytz.timezone("America/New_York")


def get_cutoff_timestamp() -> pd.Timestamp:
    """
    Hitung cutoff timestamp: 16:00 ET hari ini.
    Kalau sekarang belum jam 16:00 ET, pakai 16:00 ET kemarin.
    """
    now_et = datetime.now(ET_TZ)
    cutoff_today = now_et.replace(hour=CUTOFF_HOUR_ET, minute=0, second=0, microsecond=0)

    if now_et < cutoff_today:
        # Belum jam 16:00 ET hari ini, pakai kemarin
        cutoff = cutoff_today - pd.Timedelta(days=1)
    else:
        cutoff = cutoff_today

    return pd.Timestamp(cutoff).tz_convert("UTC")


def fetch_historical_data(ticker: str, period: str = PERIOD, interval: str = INTERVAL):
    """Download data historis dari Yahoo Finance, dipotong sampai cutoff 16:00 ET."""
    try:
        data = yf.download(ticker, period=period, interval=interval, progress=False)

        if data.empty:
            print(f"  ⚠️  {ticker} | Tidak ada data")
            return None

        # Flatten MultiIndex kolom jika ada
        if isinstance(data.columns, pd.MultiIndex):
            data.columns = data.columns.droplevel(1)

        # Potong data sampai cutoff 16:00 ET
        cutoff = get_cutoff_timestamp()
        if data.index.tz is None:
            data.index = data.index.tz_localize("UTC")
        else:
            data.index = data.index.tz_convert("UTC")

        data = data[data.index <= cutoff]

        if data.empty:
            print(f"  ⚠️  {ticker} | Tidak ada data setelah cutoff")
            return None

        print(f"  📅 Cutoff: {cutoff.strftime('%Y-%m-%d %H:%M')} UTC | Last bar: {data.index[-1].strftime('%Y-%m-%d %H:%M')} UTC")
        return data

    except Exception as e:
        print(f"  ❌ {ticker} | Error: {e}")
        return None


def resample_to_1h(df: pd.DataFrame) -> pd.DataFrame:
    """Pastikan data dalam format 1h OHLCV yang bersih."""
    if df is None or df.empty:
        return None

    agg = {
        "Open": "first",
        "High": "max",
        "Low": "min",
        "Close": "last",
        "Volume": "sum",
    }
    # Hapus kolom extra seperti Adj Close
    df = df[[c for c in ["Open", "High", "Low", "Close", "Volume"] if c in df.columns]]
    return df.dropna()


def run(screener_file: str = SCREENER_FILE, output_folder: str = OUTPUT_FOLDER,
        top_n: int = TOP_N, period: str = PERIOD):
    """
    Jalankan fetch data:
    1. Baca ticker dari screener.csv
    2. Download historical data
    3. Simpan ke data/historical/
    """
    print("=" * 60)
    print("FETCH DATA — Yahoo Finance")
    print(f"Period: {period} | Interval: {INTERVAL} | Top N: {top_n}")
    print("=" * 60)

    if not os.path.exists(screener_file):
        print(f"❌ {screener_file} tidak ditemukan. Jalankan screener.py dulu.")
        return False

    df_screener = pd.read_csv(screener_file)
    if df_screener.empty or "symbol" not in df_screener.columns:
        print(f"❌ {screener_file} kosong atau tidak punya kolom 'symbol'.")
        return False

    tickers = df_screener["symbol"].dropna().astype(str).str.strip().head(top_n).tolist()
    print(f"\n📋 {len(tickers)} ticker: {', '.join(tickers)}\n")

    # Bersihkan folder lama
    if os.path.exists(output_folder):
        shutil.rmtree(output_folder)
    os.makedirs(output_folder, exist_ok=True)

    print("-" * 60)
    success = 0
    for ticker in tickers:
        print(f"🔄 {ticker}...")
        df = fetch_historical_data(ticker, period=period)
        df = resample_to_1h(df)

        if df is not None:
            path = os.path.join(output_folder, f"{ticker}_historical.csv")
            df.to_csv(path)
            print(f"  ✅ {ticker} | {len(df)} bars | {path}")
            success += 1
        else:
            print(f"  ❌ {ticker} | Gagal")

    print("-" * 60)
    print(f"\n✅ Selesai! {success}/{len(tickers)} saham berhasil didownload.")
    print(f"📁 Tersimpan di: {output_folder}/\n")
    return success > 0


if __name__ == "__main__":
    run()
