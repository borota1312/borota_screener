"""
fetch_data.py — Download data historis dari Yahoo Finance
Baca ticker dari data/screener.csv, simpan ke data/historical/
"""

import shutil
import yfinance as yf
import pandas as pd
import os


# ─── KONFIGURASI ───
SCREENER_FILE  = "data/screener.csv"
OUTPUT_FOLDER  = "data/historical"
TOP_N          = 10
PERIOD         = "1y"
INTERVAL       = "1h"


def fetch_historical_data(ticker: str, period: str = PERIOD, interval: str = INTERVAL):
    """Download data historis dari Yahoo Finance."""
    try:
        data = yf.download(ticker, period=period, interval=interval, progress=False)

        if data.empty:
            print(f"  ⚠️  {ticker} | Tidak ada data")
            return None

        # Flatten MultiIndex kolom jika ada
        if isinstance(data.columns, pd.MultiIndex):
            data.columns = data.columns.droplevel(1)

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
