import json
import urllib.request
import urllib.error
import urllib.parse
from datetime import datetime, timedelta, timezone

# 日本時間のタイムゾーン (UTC+9)
JST = timezone(timedelta(hours=9))


def get_stock_price_yfinance_v8(ticker, interval='1d'):
    """
    Yahoo Finance v8 API（より安定）を使用
    JSONレスポンスを直接パース

    Parameters:
    - ticker: 銘柄コード
    - interval: 時間足 ('15m', '30m', '60m', '1d', '1wk', '1mo')
    """
    try:
        # 期間設定（過去10年分）
        end_date = int(datetime.now().timestamp())
        start_date = int((datetime.now() - timedelta(days=3650)).timestamp())
        
        # Yahoo Finance v8 API（公式に近い）
        url = f"https://query2.finance.yahoo.com/v8/finance/chart/{ticker}?period1={start_date}&period2={end_date}&interval={interval}"
        
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        
        request = urllib.request.Request(url, headers=headers)
        
        with urllib.request.urlopen(request, timeout=10) as response:
            data = json.loads(response.read().decode('utf-8'))
            
            # データ検証
            if 'chart' not in data or 'result' not in data['chart']:
                print(f"  ⚠️  {ticker}: Invalid response structure")
                return None
            
            result = data['chart']['result']
            if not result or len(result) == 0:
                print(f"  ⚠️  {ticker}: No data in result")
                return None
            
            quote = result[0]
            
            # 銘柄名を取得
            meta = quote.get('meta', {})
            short_name = meta.get('shortName', ticker)
            
            # タイムスタンプと終値を取得
            timestamps = quote.get('timestamp', [])
            prices = quote.get('indicators', {}).get('quote', [{}])[0].get('close', [])
            
            if not timestamps or not prices:
                print(f"  ⚠️  {ticker}: Missing timestamps or prices")
                return None
            
            # データを整形（全データを返す）
            chart_data = []
            valid_prices = []

            for i in range(len(timestamps)):
                if i >= len(prices) or prices[i] is None:
                    continue

                # タイムスタンプを日本時間に変換
                utc_time = datetime.fromtimestamp(timestamps[i], tz=timezone.utc)
                jst_time = utc_time.astimezone(JST)

                # intervalに応じて日時フォーマットを調整
                if interval in ['15m', '30m', '60m']:
                    date = jst_time.strftime('%Y-%m-%d %H:%M')
                else:
                    date = jst_time.strftime('%Y-%m-%d')

                price = float(prices[i])

                chart_data.append({
                    "time": date,
                    "value": price
                })
                valid_prices.append(price)
            
            if not valid_prices:
                print(f"  ⚠️  {ticker}: No valid prices")
                return None
            
            print(f"  ✓ {ticker}: {len(chart_data)} data points fetched ({interval})")
            
            return {
                "data": chart_data,
                "current_price": valid_prices[-1],
                "year_high": max(valid_prices),
                "year_low": min(valid_prices),
                "year_change_pct": round(((valid_prices[-1] - valid_prices[0]) / valid_prices[0]) * 100, 2) if len(valid_prices) > 1 else 0,
                "data_points": len(chart_data),
                "short_name": short_name
            }
            
    except urllib.error.HTTPError as e:
        print(f"  ✗ {ticker}: HTTP Error {e.code}")
        return None
    except urllib.error.URLError as e:
        print(f"  ✗ {ticker}: URL Error - {e.reason}")
        return None
    except Exception as e:
        print(f"  ✗ {ticker}: Unexpected error - {str(e)}")
        return None


def search_ticker(query):
    """
    Yahoo Finance APIで銘柄を検索
    """
    try:
        encoded_query = urllib.parse.quote(query)
        url = f"https://query2.finance.yahoo.com/v1/finance/search?q={encoded_query}&quotesCount=10&newsCount=0&enableFuzzyQuery=true&quotesQueryId=tss_match_phrase_query"
        
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        
        request = urllib.request.Request(url, headers=headers)
        
        with urllib.request.urlopen(request, timeout=5) as response:
            data = json.loads(response.read().decode('utf-8'))
            
            quotes = data.get('quotes', [])
            results = []
            
            for quote in quotes:
                symbol = quote.get('symbol', '')
                # 日本株（.T で終わる）のみをフィルタ
                if symbol.endswith('.T'):
                    results.append({
                        "symbol": symbol,
                        "name": quote.get('shortname', quote.get('longname', symbol)),
                        "type": quote.get('typeDisp', 'Stock'),
                        "exchange": quote.get('exchange', '')
                    })
            
            return results
            
    except Exception as e:
        print(f"Search error: {str(e)}")
        return []


def lambda_handler(event, context):
    """
    リクエストごとにYahoo Financeからデータを取得
    依存関係ゼロ（urllib標準ライブラリのみ）
    """
    
    print("=== Lambda Function Started ===")
    print(f"Event: {json.dumps(event)}")
    
    # 現在の日本時間を取得
    now_jst = datetime.now(JST)
    
    # CORS ヘッダー（すべてのレスポンスで共通）
    cors_headers = {
        'Access-Control-Allow-Origin': '*',
        'Access-Control-Allow-Headers': 'Content-Type,X-Amz-Date,Authorization,X-Api-Key,X-Amz-Security-Token',
        'Access-Control-Allow-Methods': 'GET,OPTIONS,POST',
        'Access-Control-Max-Age': '86400'
    }
    
    # OPTIONSメソッドの処理（CORSプリフライトリクエスト）
    http_method = event.get('httpMethod') or event.get('requestContext', {}).get('http', {}).get('method')
    if http_method == 'OPTIONS':
        print("OPTIONS request - returning CORS headers")
        return {
            'statusCode': 200,
            'headers': cors_headers,
            'body': ''
        }
    
    # クエリパラメータを取得
    query_params = event.get('queryStringParameters') or {}
    action = query_params.get('action', 'get_stocks')
    
    # 検索アクション
    if action == 'search':
        search_query = query_params.get('q', '')
        if not search_query:
            return {
                'statusCode': 400,
                'headers': {**cors_headers, 'Content-Type': 'application/json; charset=utf-8'},
                'body': json.dumps({"error": "検索クエリが必要です"}, ensure_ascii=False)
            }
        
        results = search_ticker(search_query)
        return {
            'statusCode': 200,
            'headers': {
                **cors_headers,
                'Content-Type': 'application/json; charset=utf-8',
                'Cache-Control': 'public, max-age=300'
            },
            'body': json.dumps({
                "results": results,
                "query": search_query,
                "updated_at_jst": now_jst.strftime('%Y-%m-%d %H:%M:%S JST')
            }, ensure_ascii=False)
        }
    
    # 単一銘柄取得
    if action == 'get_stock':
        ticker = query_params.get('ticker', '')
        interval = query_params.get('interval', '1d')

        # intervalのバリデーション
        valid_intervals = ['15m', '30m', '60m', '1d', '1wk', '1mo']
        if interval not in valid_intervals:
            return {
                'statusCode': 400,
                'headers': {**cors_headers, 'Content-Type': 'application/json; charset=utf-8'},
                'body': json.dumps({"error": f"無効なintervalです。有効な値: {', '.join(valid_intervals)}"}, ensure_ascii=False)
            }

        if not ticker:
            return {
                'statusCode': 400,
                'headers': {**cors_headers, 'Content-Type': 'application/json; charset=utf-8'},
                'body': json.dumps({"error": "銘柄コードが必要です"}, ensure_ascii=False)
            }

        # .T が付いていなければ追加
        if not ticker.endswith('.T'):
            ticker = ticker + '.T'

        stock_data = get_stock_price_yfinance_v8(ticker, interval)
        
        if stock_data:
            return {
                'statusCode': 200,
                'headers': {
                    **cors_headers,
                    'Content-Type': 'application/json; charset=utf-8',
                    'Cache-Control': 'public, max-age=300'
                },
                'body': json.dumps({
                    "ticker": ticker,
                    "name": stock_data.get('short_name', ticker),
                    **stock_data,
                    "updated_at_jst": now_jst.strftime('%Y-%m-%d %H:%M:%S JST')
                }, ensure_ascii=False)
            }
        else:
            return {
                'statusCode': 404,
                'headers': {**cors_headers, 'Content-Type': 'application/json; charset=utf-8'},
                'body': json.dumps({"error": f"銘柄 {ticker} のデータを取得できませんでした"}, ensure_ascii=False)
            }
    
    # デフォルト: 複数銘柄を取得（従来の動作）
    # 取得する銘柄リスト
    tickers_param = query_params.get('tickers', '')
    interval = query_params.get('interval', '1d')

    # intervalのバリデーション
    valid_intervals = ['15m', '30m', '60m', '1d', '1wk', '1mo']
    if interval not in valid_intervals:
        return {
            'statusCode': 400,
            'headers': {**cors_headers, 'Content-Type': 'application/json; charset=utf-8'},
            'body': json.dumps({"error": f"無効なintervalです。有効な値: {', '.join(valid_intervals)}"}, ensure_ascii=False)
        }

    if tickers_param:
        # カンマ区切りで銘柄を指定
        ticker_list = [t.strip() for t in tickers_param.split(',') if t.strip()]
        TICKERS = {}
        for t in ticker_list:
            if not t.endswith('.T'):
                t = t + '.T'
            TICKERS[t] = t
    else:
        # デフォルトの銘柄リスト
        TICKERS = {
            "7203.T": "トヨタ自動車",
            "6758.T": "ソニーグループ",
            "9984.T": "ソフトバンクグループ",
            "6861.T": "キーエンス",
            "8306.T": "三菱UFJ"
        }
    
    print(f"Processing {len(TICKERS)} tickers...")
    
    result = {
        "updated_at": now_jst.isoformat(),
        "updated_at_jst": now_jst.strftime('%Y-%m-%d %H:%M:%S JST'),
        "timezone": "Asia/Tokyo (UTC+9)",
        "stocks": {},
        "summary": {
            "total_tickers": len(TICKERS),
            "successful": 0,
            "failed": 0,
            "failed_tickers": []
        }
    }
    
    # 各銘柄のデータを取得
    for ticker, name in TICKERS.items():
        print(f"Fetching {ticker} ({name})...")
        stock_data = get_stock_price_yfinance_v8(ticker, interval)
        
        if stock_data:
            result["stocks"][ticker] = {
                "name": stock_data.get('short_name', name),
                "ticker": ticker,
                **stock_data
            }
            result["summary"]["successful"] += 1
        else:
            result["summary"]["failed"] += 1
            result["summary"]["failed_tickers"].append(ticker)
    
    print(f"\n=== Summary ===")
    print(f"Successful: {result['summary']['successful']}/{len(TICKERS)}")
    print(f"Failed: {result['summary']['failed']}")
    if result["summary"]["failed_tickers"]:
        print(f"Failed tickers: {', '.join(result['summary']['failed_tickers'])}")
    
    return {
        'statusCode': 200 if result["summary"]["successful"] > 0 else 500,
        'headers': {
            **cors_headers,
            'Content-Type': 'application/json; charset=utf-8',
            'Cache-Control': 'public, max-age=300',
            'X-Request-Time-JST': now_jst.strftime('%Y-%m-%d %H:%M:%S'),
            'X-Success-Count': str(result["summary"]["successful"]),
            'X-Failed-Count': str(result["summary"]["failed"])
        },
        'body': json.dumps(result, ensure_ascii=False)
    }
