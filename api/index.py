from flask import Flask, jsonify, request
import requests
from bs4 import BeautifulSoup
import json
import re

app = Flask(__name__)

# Base Headers (Penting biar dianggap browser PC/HP)
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Referer": "https://www.viu.com/",
    "Origin": "https://www.viu.com"
}

def get_next_data(url):
    """
    Fungsi sakti untuk mengambil JSON '__NEXT_DATA__' dari situs Next.js seperti Viu.
    """
    try:
        response = requests.get(url, headers=HEADERS, timeout=10)
        if response.status_code != 200:
            return None
        
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Cari tag script dengan id __NEXT_DATA__
        script = soup.find('script', {'id': '__NEXT_DATA__'})
        if script:
            return json.loads(script.string)
        return None
    except Exception as e:
        print(f"Error: {e}")
        return None

@app.route('/')
def home():
    return jsonify({
        "status": "Viu Scraper Running",
        "endpoints": {
            "search": "/api/search?q=keyword",
            "detail": "/api/detail?url=https://www.viu.com/ott/id/id/vod/..."
        }
    })

@app.route('/api/search')
def search():
    query = request.args.get('q')
    if not query:
        return jsonify({"error": "Parameter 'q' is required"}), 400
    
    # URL Search Viu
    target_url = f"https://www.viu.com/ott/id/id/search?keyword={query}"
    data = get_next_data(target_url)
    
    results = []
    
    if data:
        try:
            # Jalur data Viu (bisa berubah, tapi biasanya pola ini bertahan lama)
            # props -> pageProps -> initialData -> data -> result
            search_results = data['props']['pageProps']['initialData']['data']['result']
            
            for item in search_results:
                # Kita cari yang tipenya 'vod' (Video) atau 'series'
                # Viu mencampur hasil search (ada category, ada clip, ada full movie)
                if 'id' in item and 'title' in item:
                    # Construct URL
                    # Format: /ott/id/id/vod/{id}/{slug}
                    vid_id = item.get('id')
                    slug = item.get('slug', 'video')
                    full_url = f"https://www.viu.com/ott/id/id/vod/{vid_id}/{slug}"
                    
                    # Image URL (Viu biasanya punya beberapa ukuran)
                    img_url = item.get('cover_image_url')
                    
                    results.append({
                        "title": item.get('title'),
                        "id": vid_id,
                        "url": full_url,
                        "description": item.get('description'),
                        "thumbnail": img_url
                    })
        except KeyError:
            pass

    return jsonify({"query": query, "count": len(results), "results": results})

@app.route('/api/detail')
def detail():
    target_url = request.args.get('url')
    if not target_url:
        return jsonify({"error": "Parameter 'url' is required"}), 400

    data = get_next_data(target_url)
    if not data:
        return jsonify({"error": "Failed to fetch data or blocked"}), 500

    result = {
        "title": "Unknown",
        "description": "",
        "episodes": [],
        "stream_info": "Not available directly"
    }

    try:
        # Mengambil metadata utama dari pageProps
        current_product = data['props']['pageProps']['data']['current_product']
        series_product = data['props']['pageProps']['data'].get('series_product', [])
        
        result['title'] = current_product.get('title')
        result['description'] = current_product.get('description')
        result['synopsis'] = current_product.get('synopsis')
        result['cover'] = current_product.get('cover_image_url')
        
        # MENGAMBIL LIST EPISODE
        # Di Viu, list episode lain biasanya ada di 'series_product'
        # Atau jika ini adalah halaman episode, 'current_product' adalah episode itu sendiri.
        
        # Masukkan episode yang sedang aktif (current)
        if current_product:
            result['episodes'].append({
                "episode_number": current_product.get('number'),
                "title": current_product.get('subtitle'),
                "id": current_product.get('id'),
                "url": target_url, # URL halaman ini
                "is_premium": current_product.get('is_movie', 0) == 1 # Indikator kasar
            })
            
        # Masukkan episode lainnya dari list series
        for ep in series_product:
            # Hindari duplikat dengan current product
            if ep.get('id') != current_product.get('id'):
                ep_url = f"https://www.viu.com/ott/id/id/vod/{ep.get('id')}/{ep.get('slug')}"
                result['episodes'].append({
                    "episode_number": ep.get('number'),
                    "title": ep.get('subtitle'),
                    "id": ep.get('id'),
                    "url": ep_url,
                    "is_premium": ep.get('is_movie', 0) == 1
                })
        
        # Sort episode biar rapi (1, 2, 3...)
        # Kadang 'number' itu string kosong, jadi perlu handle error
        result['episodes'].sort(key=lambda x: int(x['episode_number']) if x['episode_number'] and str(x['episode_number']).isdigit() else 9999)

    except Exception as e:
        result['error_parsing'] = str(e)

    return jsonify(result)

# Note untuk Streaming:
# Viu menggunakan API internal untuk generate link streaming (.m3u8) yang memiliki token.
# API itu butuh parameter seperti 'appid', 'platform_flag', 'r' (random), dll.
# Mengambil raw mp4 dari sisi server Vercel sangat sulit karena Geo-Blocking dan Token Auth.
# Disarankan hanya mengambil metadata & list episode, lalu biarkan frontend user membuka link aslinya.

if __name__ == '__main__':
    app.run(debug=True)
