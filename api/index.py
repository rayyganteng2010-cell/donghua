from flask import Flask, jsonify, request
import requests
from bs4 import BeautifulSoup
import json
import re

app = Flask(__name__)

# --- CONFIG SESSION DARI URL LU ---
# Session ID yang lu kasih di URL
USER_SESSION_ID = "73d069f57044172d83509a511098650e1dd8c1467092a0ea0"

# Headers dimiripin sama browser Android
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36",
    "Referer": "https://www.viu.com/",
    "Origin": "https://www.viu.com",
    "Accept-Language": "id-ID,id;q=0.9,en-US;q=0.8,en;q=0.7",
    "X-Requested-With": "com.viu.phone"  # Kadang ini ngebantu bypass
}

# Cookies wajib injek session
COOKIES = {
    "vusess": USER_SESSION_ID,
    "language_flag": "id",
    "country_flag": "id"
}

def fetch_viu_page(url):
    """
    Request ke Viu dengan full atribut session & cookies
    """
    try:
        # Kita tambahkan parameter session_id juga di URL biar double-protection
        params = {
            "session_id": USER_SESSION_ID,
            "partnerId": "7",
            "chargingPlatform": "frontend_wap",
            "redirectedFromHE": "true"
        }
        
        response = requests.get(
            url, 
            headers=HEADERS, 
            cookies=COOKIES, 
            params=params, 
            timeout=15
        )
        return response
    except Exception as e:
        print(f"Connection Error: {e}")
        return None

def extract_next_data(html_content):
    """
    Ekstrak JSON __NEXT_DATA__
    """
    try:
        soup = BeautifulSoup(html_content, 'html.parser')
        script = soup.find('script', {'id': '__NEXT_DATA__'})
        if script:
            return json.loads(script.string)
    except:
        pass
    return None

@app.route('/')
def home():
    return jsonify({
        "status": "Viu Session Scraper Active",
        "session_used": USER_SESSION_ID[:10] + "...",
        "endpoints": {
            "search": "/api/search?q=keyword",
            "detail": "/api/detail?url=https://www.viu.com/ott/id/id/vod/...",
            "debug": "/api/debug?url=https://www.viu.com/..." 
        }
    })

@app.route('/api/search')
def search():
    query = request.args.get('q')
    if not query:
        return jsonify({"error": "Parameter 'q' is required"}), 400
    
    # URL Search Viu
    target_url = f"https://www.viu.com/ott/id/id/search?keyword={query}"
    
    response = fetch_viu_page(target_url)
    if not response or response.status_code != 200:
        return jsonify({"error": "Failed to fetch search page", "status_code": response.status_code if response else "Error"}), 500

    data = extract_next_data(response.text)
    results = []
    
    if data:
        try:
            # Navigasi JSON Viu
            items = data['props']['pageProps']['initialData']['data']['result']
            for item in items:
                # Ambil ID dan Slug
                vid_id = item.get('id')
                slug = item.get('slug', 'video')
                
                if vid_id:
                    full_url = f"https://www.viu.com/ott/id/id/vod/{vid_id}/{slug}"
                    results.append({
                        "title": item.get('title'),
                        "id": vid_id,
                        "url": full_url,
                        "thumbnail": item.get('cover_image_url'),
                        "is_premium": item.get('is_movie') # 1 = premium, 0 = free
                    })
        except KeyError:
            pass

    return jsonify({"query": query, "results": results})

@app.route('/api/detail')
def detail():
    target_url = request.args.get('url')
    if not target_url:
        return jsonify({"error": "Parameter 'url' is required"}), 400

    response = fetch_viu_page(target_url)
    if not response:
        return jsonify({"error": "Connection failed"}), 500

    data = extract_next_data(response.text)
    
    if not data:
        # Jika gagal ambil JSON, kemungkinan kena blokir atau halaman error
        soup = BeautifulSoup(response.text, 'html.parser')
        title = soup.title.string if soup.title else "No Title"
        return jsonify({
            "error": "Failed to parse NEXT_DATA", 
            "page_title_received": title,
            "hint": "Check /api/debug to see raw HTML"
        }), 500

    res_data = {
        "title": "Unknown",
        "desc": "",
        "episodes": []
    }

    try:
        page_data = data['props']['pageProps']['data']
        current = page_data.get('current_product', {})
        series_list = page_data.get('series_product', [])

        res_data['title'] = current.get('title')
        res_data['desc'] = current.get('description')
        res_data['synopsis'] = current.get('synopsis')
        res_data['img'] = current.get('cover_image_url')

        # Masukkan Episode Current
        if current.get('id'):
             res_data['episodes'].append({
                "no": current.get('number'),
                "title": current.get('subtitle'),
                "id": current.get('id'),
                "url": target_url
            })

        # Masukkan Episode Lainnya
        for ep in series_list:
            if ep.get('id') != current.get('id'):
                ep_url = f"https://www.viu.com/ott/id/id/vod/{ep.get('id')}/{ep.get('slug')}"
                res_data['episodes'].append({
                    "no": ep.get('number'),
                    "title": ep.get('subtitle'),
                    "id": ep.get('id'),
                    "url": ep_url
                })
        
        # Sort episode
        res_data['episodes'].sort(key=lambda x: int(x['no']) if x['no'] and str(x['no']).isdigit() else 9999)

    except Exception as e:
        res_data['error_trace'] = str(e)

    return jsonify(res_data)

@app.route('/api/debug')
def debug():
    """
    Gunakan ini kalau 'Search' atau 'Detail' masih kosong resultnya.
    Ini akan nampilin apa yang sebenarnya dilihat oleh server Vercel.
    """
    target_url = request.args.get('url')
    if not target_url:
        target_url = "https://www.viu.com/ott/id/id/all"
    
    response = fetch_viu_page(target_url)
    
    if not response:
        return "Failed to connect"

    soup = BeautifulSoup(response.text, 'html.parser')
    
    # Cek Title Halaman
    page_title = soup.title.string if soup.title else "No Title"
    
    # Cek apakah ada teks 'Location' atau 'Region' (Tanda kena blokir)
    text_content = soup.get_text()[:500] 
    
    return jsonify({
        "status_code": response.status_code,
        "page_title": page_title,
        "final_url": response.url,
        "content_snippet": text_content,
        "headers_sent": dict(response.request.headers),
        "cookies_sent": dict(response.request._cookies)
    })

if __name__ == '__main__':
    app.run(debug=True)
