from http.server import BaseHTTPRequestHandler
import json
import urllib.request
import urllib.error
import urllib.parse
from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse, parse_qs

JST = timezone(timedelta(hours=9))


def get_stock_price(ticker, interval='1d'):
    try:
        end_date = int(datetime.now().timestamp())
        start_date = int((datetime.now() - timedelta(days=3650)).timestamp())

        url = (
            f"https://query2.finance.yahoo.com/v8/finance/chart/{ticker}"
            f"?period1={start_date}&period2={end_date}&interval={interval}"
        )
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }

        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=15) as response:
            data = json.loads(response.read().decode('utf-8'))

        if 'chart' not in data or not data['chart'].get('result'):
            return None

        quote = data['chart']['result'][0]
        meta = quote.get('meta', {})
        short_name = meta.get('shortName', ticker)

        timestamps = quote.get('timestamp', [])
        prices = quote.get('indicators', {}).get('quote', [{}])[0].get('close', [])

        if not timestamps or not prices:
            return None

        chart_data = []
        valid_prices = []

        for i in range(len(timestamps)):
            if i >= len(prices) or prices[i] is None:
                continue

            price = float(prices[i])

            # lightweight-charts requires:
            #   intraday  → UTCTimestamp (int, seconds since epoch)
            #   daily+    → 'YYYY-MM-DD' string
            if interval in ['15m', '30m', '60m']:
                time_value = int(timestamps[i])
            else:
                jst_time = datetime.fromtimestamp(timestamps[i], tz=timezone.utc).astimezone(JST)
                time_value = jst_time.strftime('%Y-%m-%d')

            chart_data.append({"time": time_value, "value": price})
            valid_prices.append(price)

        if not valid_prices:
            return None

        return {
            "data": chart_data,
            "current_price": valid_prices[-1],
            "year_high": max(valid_prices),
            "year_low": min(valid_prices),
            "year_change_pct": round(
                ((valid_prices[-1] - valid_prices[0]) / valid_prices[0]) * 100, 2
            ) if len(valid_prices) > 1 else 0,
            "data_points": len(chart_data),
            "short_name": short_name,
        }

    except (urllib.error.HTTPError, urllib.error.URLError, Exception):
        return None


def search_ticker(query):
    try:
        encoded = urllib.parse.quote(query)
        url = (
            f"https://query2.finance.yahoo.com/v1/finance/search"
            f"?q={encoded}&quotesCount=10&newsCount=0"
        )
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=5) as response:
            data = json.loads(response.read().decode('utf-8'))

        return [
            {
                "symbol": q.get('symbol', ''),
                "name": q.get('shortname', q.get('longname', q.get('symbol', ''))),
                "type": q.get('typeDisp', 'Stock'),
                "exchange": q.get('exchange', ''),
            }
            for q in data.get('quotes', [])
            if q.get('symbol', '').endswith('.T')
        ]
    except Exception:
        return []


class handler(BaseHTTPRequestHandler):

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()

    def do_GET(self):
        parsed = urlparse(self.path)
        params = parse_qs(parsed.query, keep_blank_values=True)

        def p(key, default=''):
            return params.get(key, [default])[0]

        now_jst = datetime.now(JST)

        def send_json(status, data):
            body = json.dumps(data, ensure_ascii=False).encode('utf-8')
            self.send_response(status)
            self.send_header('Content-Type', 'application/json; charset=utf-8')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.send_header('Cache-Control', 'public, max-age=300')
            self.end_headers()
            self.wfile.write(body)

        valid_intervals = ['15m', '30m', '60m', '1d', '1wk', '1mo']
        action = p('action', 'get_stocks')
        interval = p('interval', '1d')

        if interval not in valid_intervals:
            send_json(400, {"error": "無効なintervalです"})
            return

        # --- search ---
        if action == 'search':
            q = p('q')
            if not q:
                send_json(400, {"error": "検索クエリが必要です"})
                return
            send_json(200, {
                "results": search_ticker(q),
                "query": q,
                "updated_at_jst": now_jst.strftime('%Y-%m-%d %H:%M:%S JST'),
            })
            return

        # --- get_stock (single) ---
        if action == 'get_stock':
            ticker = p('ticker')
            if not ticker:
                send_json(400, {"error": "銘柄コードが必要です"})
                return
            if not ticker.endswith('.T'):
                ticker += '.T'

            stock_data = get_stock_price(ticker, interval)
            if stock_data:
                send_json(200, {
                    "ticker": ticker,
                    "name": stock_data.get('short_name', ticker),
                    **stock_data,
                    "updated_at_jst": now_jst.strftime('%Y-%m-%d %H:%M:%S JST'),
                })
            else:
                send_json(404, {"error": f"銘柄 {ticker} のデータを取得できませんでした"})
            return

        # --- get_stocks (default, multiple) ---
        tickers_param = p('tickers')
        if tickers_param:
            tickers = {}
            for t in [x.strip() for x in tickers_param.split(',') if x.strip()]:
                key = t if t.endswith('.T') else t + '.T'
                tickers[key] = key
        else:
            tickers = {
                "7203.T": "トヨタ自動車",
                "6758.T": "ソニーグループ",
                "9984.T": "ソフトバンクグループ",
                "6861.T": "キーエンス",
                "8306.T": "三菱UFJ",
            }

        result = {
            "updated_at": now_jst.isoformat(),
            "updated_at_jst": now_jst.strftime('%Y-%m-%d %H:%M:%S JST'),
            "timezone": "Asia/Tokyo (UTC+9)",
            "stocks": {},
            "summary": {
                "total_tickers": len(tickers),
                "successful": 0,
                "failed": 0,
                "failed_tickers": [],
            },
        }

        for ticker, name in tickers.items():
            stock_data = get_stock_price(ticker, interval)
            if stock_data:
                result["stocks"][ticker] = {
                    "name": stock_data.get('short_name', name),
                    "ticker": ticker,
                    **stock_data,
                }
                result["summary"]["successful"] += 1
            else:
                result["summary"]["failed"] += 1
                result["summary"]["failed_tickers"].append(ticker)

        send_json(200 if result["summary"]["successful"] > 0 else 500, result)

    def log_message(self, format, *args):
        pass  # Vercelのログに任せる
