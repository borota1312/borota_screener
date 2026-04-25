# tradingview_scraper.py
import requests
import pandas as pd
import os
from datetime import datetime


def rank_stocks(df: pd.DataFrame) -> pd.DataFrame:
    """
    Ranking saham untuk strategi swing 4 hari (beli Senin, jual Jumat).
    Target profit bersih 2-3%, biaya transaksi 0.54% (0.27% beli + 0.27% jual).

    Formula score (0-100):
      - ATRP         35% → volatility harian, makin tinggi makin besar peluang hit target
      - Rel. Volume  25% → konfirmasi momentum, makin tinggi makin ada "aksi"
      - RSI score    20% → makin dekat ke 55 makin bagus (baru mulai, belum overbought)
      - 1W room      20% → makin kecil change 1W makin banyak ruang naik minggu ini
    """
    df = df.copy()

    def normalize(series, ascending=True):
        mn, mx = series.min(), series.max()
        if mx == mn:
            return pd.Series(50.0, index=series.index)
        norm = (series - mn) / (mx - mn) * 100
        return norm if ascending else 100 - norm

    # 1. ATRP score (35%) — makin tinggi makin bagus
    if "atrp" in df.columns:
        df["score_atrp"] = normalize(df["atrp"], ascending=True) * 0.35
    else:
        df["score_atrp"] = 0

    # 2. Relative Volume score (25%) — makin tinggi makin bagus
    if "relative_volume" in df.columns:
        df["score_relvol"] = normalize(df["relative_volume"], ascending=True) * 0.25
    else:
        df["score_relvol"] = 0

    # 3. RSI score (20%) — optimal di 55, makin jauh makin rendah
    if "rsi" in df.columns:
        df["score_rsi"] = (1 - abs(df["rsi"] - 55) / 20).clip(0, 1) * 100 * 0.20
    else:
        df["score_rsi"] = 0

    # 4. 1W room score (20%) — makin kecil change_1w makin bagus (ruang masih banyak)
    if "change_1w_pct" in df.columns:
        df["score_1w"] = normalize(df["change_1w_pct"], ascending=False) * 0.20
    else:
        df["score_1w"] = 0

    df["swing_score"] = (
        df["score_atrp"] + df["score_relvol"] + df["score_rsi"] + df["score_1w"]
    ).round(2)

    df = df.drop(columns=["score_atrp", "score_relvol", "score_rsi", "score_1w"])
    df = df.sort_values("swing_score", ascending=False).reset_index(drop=True)
    df.insert(0, "rank", range(1, len(df) + 1))

    return df


def fetch_tradingview_screener(
    output_folder="data",
    output_filename=None,
    limit=100,
    symbols=["SYML:SP;SPX", "SYML:NASDAQ;NDX", "SYML:DJ;DJI"],
):
    """
    Scraping data dari TradingView Screener API dengan filter custom + Ranking.
    Ranking: swing_score berdasarkan ATRP, Relative Volume, RSI, dan 1W room.
    """

    print("🔍 Fetching data dari TradingView Screener API...")

    url = "https://scanner.tradingview.com/america/scan"
    params = {"label-product": "screener-stock"}

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "en-US,en;q=0.9",
        "Content-Type": "application/json",
        "Origin": "https://www.tradingview.com",
        "Referer": "https://www.tradingview.com/screener/",
    }

    # Kolom yang diambil — urutan index penting untuk parsing
    # 0=ticker, 1=close, 2=type, 3=typespecs, 4=pricescale, 5=minmov,
    # 6=fractional, 7=minmove2, 8=currency, 9=change, 10=volume,
    # 11=relative_volume, 12=RSI, 13=ATRP, 14=change|1W
    payload = {
        "columns": [
            "ticker-view",          # 0
            "close",                # 1
            "type",                 # 2
            "typespecs",            # 3
            "pricescale",           # 4
            "minmov",               # 5
            "fractional",           # 6
            "minmove2",             # 7
            "currency",             # 8
            "change",               # 9
            "volume",               # 10
            "relative_volume_10d_calc",  # 11
            "RSI",                  # 12
            "ATRP",                 # 13
            "change|1W",            # 14
        ],
        "filter": [
            {"left": "is_blacklisted", "operation": "equal", "right": False},
            {"left": "close", "operation": "greater", "right": "SMA20"},
            {"left": "change", "operation": "in_range", "right": [0.5, 4]},
            {"left": "RSI", "operation": "in_range", "right": [50, 68]},
            {"left": "change|1W", "operation": "in_range", "right": [0, 8]},
            {"left": "close|1W", "operation": "greater", "right": "SMA20|1W"},
            {"left": "ATRP", "operation": "greater", "right": 2.5},
            {"left": "volume", "operation": "greater", "right": 500000},
            {"left": "is_primary", "operation": "equal", "right": True},
        ],
        "ignore_unknown_fields": False,
        "options": {"lang": "en"},
        "range": [0, limit],
        "sort": {"sortBy": "volume", "sortOrder": "desc"},
        "symbols": {"symbolset": symbols},
        "markets": ["america"],
        "filter2": {
            "operator": "and",
            "operands": [
                {
                    "operation": {
                        "operator": "or",
                        "operands": [
                            {
                                "operation": {
                                    "operator": "and",
                                    "operands": [
                                        {"expression": {"left": "type", "operation": "equal", "right": "stock"}},
                                        {"expression": {"left": "typespecs", "operation": "has", "right": ["common"]}},
                                    ],
                                }
                            },
                            {
                                "operation": {
                                    "operator": "and",
                                    "operands": [
                                        {"expression": {"left": "type", "operation": "equal", "right": "stock"}},
                                        {"expression": {"left": "typespecs", "operation": "has", "right": ["preferred"]}},
                                    ],
                                }
                            },
                            {
                                "operation": {
                                    "operator": "and",
                                    "operands": [
                                        {"expression": {"left": "type", "operation": "equal", "right": "dr"}}
                                    ],
                                }
                            },
                            {
                                "operation": {
                                    "operator": "and",
                                    "operands": [
                                        {"expression": {"left": "type", "operation": "equal", "right": "fund"}},
                                        {"expression": {"left": "typespecs", "operation": "has_none_of", "right": ["etf", "mutual", "closedend"]}},
                                    ],
                                }
                            },
                        ],
                    }
                },
                {
                    "expression": {
                        "left": "typespecs",
                        "operation": "has_none_of",
                        "right": ["pre-ipo"],
                    }
                },
            ],
        },
    }

    all_results = []

    try:
        response = requests.post(
            url, params=params, json=payload, headers=headers, timeout=30
        )
        response.raise_for_status()
        data = response.json()

        total_count = data.get("totalCount", 0)
        records = data.get("data", [])

        print(f"📊 Total hasil dari API: {total_count}")
        print(f"📦 Data yang diterima: {len(records)} record")

        for item in records:
            raw_symbol = item.get("s", "")
            details = item.get("d", [])

            if not raw_symbol or not isinstance(details, list) or len(details) < 2:
                continue

            if ":" in raw_symbol:
                exchange, symbol = raw_symbol.split(":", 1)
            else:
                exchange, symbol = "UNKNOWN", raw_symbol

            def safe(val, cast=float):
                try:
                    return cast(val) if val not in [None, ""] else None
                except (ValueError, TypeError):
                    return None

            try:
                all_results.append({
                    "symbol":          symbol.strip(),
                    "exchange":        exchange.strip(),
                    "close":           safe(details[1] if len(details) > 1 else None),
                    "change_1d_pct":   safe(details[9] if len(details) > 9 else None),
                    "volume":          safe(details[10] if len(details) > 10 else None, int),
                    "relative_volume": safe(details[11] if len(details) > 11 else None),
                    "rsi":             safe(details[12] if len(details) > 12 else None),
                    "atrp":            safe(details[13] if len(details) > 13 else None),
                    "change_1w_pct":   safe(details[14] if len(details) > 14 else None),
                    "fetched_at":      datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                })
            except (ValueError, TypeError, IndexError) as e:
                print(f"⚠️ Skip record {raw_symbol}: {e}")
                continue

        if all_results:
            df = pd.DataFrame(all_results)

            # Pastikan kolom numerik
            for col in ["change_1d_pct", "volume", "relative_volume", "rsi", "atrp", "change_1w_pct"]:
                df[col] = pd.to_numeric(df[col], errors="coerce")

            # Hapus baris yang tidak punya data penting
            df = df.dropna(subset=["change_1d_pct", "volume"]).copy()

            # === RANKING ===
            df_ranked = rank_stocks(df)
            # ===============

            os.makedirs(output_folder, exist_ok=True)

            if output_filename is None:
                output_filename = "screener.csv"

            full_path = os.path.join(output_folder, output_filename)
            df_ranked.to_csv(full_path, index=False, encoding="utf-8")

            print(f"\n✅ SUCCESS! {len(df_ranked)} simbol disimpan ke: `{full_path}`")
            print("\n📋 Top 10 Ranking (Swing Score Tertinggi):")
            print("-" * 70)

            preview_cols = ["rank", "symbol", "close", "swing_score", "atrp", "relative_volume", "rsi", "change_1w_pct", "change_1d_pct"]
            preview_cols = [c for c in preview_cols if c in df_ranked.columns]
            print(df_ranked[preview_cols].head(10).to_string(index=False))

            return df_ranked, full_path
        else:
            print("\n⚠️ Tidak ada data yang memenuhi filter saat ini.")
            return pd.DataFrame(), None

    except requests.exceptions.HTTPError as e:
        if e.response.status_code == 429:
            print("❌ Rate limit (429). Tunggu 60 detik lalu coba lagi.")
        elif e.response.status_code == 403:
            print("❌ Forbidden (403). TradingView mungkin memblokir request ini.")
        else:
            print(f"❌ HTTP Error {e.response.status_code}: {e}")
    except requests.exceptions.RequestException as e:
        print(f"❌ Network error: {e}")
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        import traceback
        traceback.print_exc()

    return pd.DataFrame(), None


if __name__ == "__main__":
    df_result, file_path = fetch_tradingview_screener(
        limit=100,
        symbols=["SYML:SP;SPX", "SYML:NASDAQ;NDX", "SYML:DJ;DJI"],
    )

    if df_result is not None and not df_result.empty:
        print(f"\n✅ Screener selesai! File: {file_path}")
    else:
        print("\n❌ Screener gagal atau tidak menghasilkan data")
