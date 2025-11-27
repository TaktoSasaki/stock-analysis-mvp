import yfinance as yf
import json
import os
import time
from datetime import datetime

# 取得したい銘柄コード（東証プライム主要銘柄）
TICKERS = {
    "7203.T": "トヨタ自動車",
    "6758.T": "ソニーグループ",
    "9984.T": "ソフトバンクグループ",
    "6861.T": "キーエンス",
    "8306.T": "三菱UFJ"
}

def fetch_data():
    """株価データを取得してJSONに変換"""
    result = {
        "updated_at": datetime.now().isoformat(),
        "stocks": {}
    }
    
    failed_tickers = []
    
    for ticker, name in TICKERS.items():
        try:
            print(f"Fetching {name} ({ticker})...")
            stock = yf.Ticker(ticker)
            
            # 過去1年分のデータを取得（リトライ機能付き）
            hist = None
            for attempt in range(3):
                try:
                    hist = stock.history(period="1y")
                    if not hist.empty:
                        break
                except Exception as e:
                    print(f"  Attempt {attempt + 1} failed: {e}")
                    time.sleep(2)
            
            if hist is None or hist.empty:
                print(f"  ⚠️  {name}: データ取得失敗")
                failed_tickers.append(ticker)
                continue
            
            # Lightweight Charts形式に変換
            chart_data = []
            for index, row in hist.iterrows():
                # NaN値のチェック
                if not row['Close'] or row['Close'] != row['Close']:  # NaNチェック
                    continue
                    
                chart_data.append({
                    "time": index.strftime('%Y-%m-%d'),
                    "value": float(row['Close'])
                })
            
            if not chart_data:
                print(f"  ⚠️  {name}: 有効なデータなし")
                failed_tickers.append(ticker)
                continue
            
            # 基本的な統計情報も追加
            prices = [d['value'] for d in chart_data]
            current_price = prices[-1]
            year_high = max(prices)
            year_low = min(prices)
            year_change = ((current_price - prices[0]) / prices[0]) * 100
            
            result["stocks"][ticker] = {
                "name": name,
                "ticker": ticker,
                "data": chart_data,
                "current_price": current_price,
                "year_high": year_high,
                "year_low": year_low,
                "year_change_pct": round(year_change, 2),
                "data_points": len(chart_data)
            }
            
            print(f"  ✓ {name}: {len(chart_data)}件のデータ取得成功")
            
        except Exception as e:
            print(f"  ✗ {name}: エラー - {str(e)}")
            failed_tickers.append(ticker)
            continue
    
    # 結果のサマリー
    result["summary"] = {
        "total_tickers": len(TICKERS),
        "successful": len(result["stocks"]),
        "failed": len(failed_tickers),
        "failed_tickers": failed_tickers
    }
    
    # JSONとして保存
    os.makedirs("data", exist_ok=True)
    output_path = "data/stock_data.json"
    
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    
    print(f"\n{'='*50}")
    print(f"データ取得完了: {len(result['stocks'])}/{len(TICKERS)}銘柄")
    print(f"出力先: {output_path}")
    if os.path.exists(output_path):
        print(f"ファイルサイズ: {os.path.getsize(output_path) / 1024:.1f} KB")
    if failed_tickers:
        print(f"⚠️  取得失敗: {', '.join(failed_tickers)}")
    print(f"{'='*50}")
    
    return len(result["stocks"]) > 0  # 最低1つ成功すればTrue

if __name__ == "__main__":
    success = fetch_data()
    exit(0 if success else 1)  # CIで失敗を検知できるようにする