from flask import Flask, jsonify, request
import cloudscraper
from bs4 import BeautifulSoup
import re

app = Flask(__name__)

# Base URL target
BASE_URL = "https://dracin.io"

# Inisialisasi Scraper dengan User-Agent Android agar dianggap HP
scraper = cloudscraper.create_scraper(
    browser={
        'browser': 'chrome',
        'platform': 'android',
        'desktop': False
    }
)

# Jika cloudscraper gagal set user-agent spesifik, kita paksa di header
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36",
    "Referer": BASE_URL
}

def get_soup(url):
    try:
        # Menggunakan scraper.get untuk bypass cloudflare ringan
        response = scraper.get(url, headers=HEADERS, timeout=15)
        response.raise_for_status()
        return BeautifulSoup(response.text, 'html.parser')
    except Exception as e:
        print(f"Error fetching {url}: {e}")
        return None

@app.route('/')
def home():
    return jsonify({
        "status": "Online",
        "mode": "Cloudscraper + Regex Mode",
        "endpoints": {
            "search": "/api/search?q=keyword",
            "detail": "/api/detail?url=https://dracin.io/drama/...",
            "watch": "/api/watch?url=https://dracin.io/watch/..."
        }
    })

@app.route('/api/search')
def search():
    query = request.args.get('q')
    if not query:
        return jsonify({"error": "Parameter 'q' is required"}), 400
    
    # URL Search
    search_url = f"{BASE_URL}/search?q={query}"
    soup = get_soup(search_url)
    
    results = []
    seen_urls = set()

    if soup:
        # LOGIKA BARU: Cari SEMUA tag <a> yang punya href mengandung '/drama/'
        # Ini tidak peduli class css-nya apa, jadi lebih anti-gagal.
        all_links = soup.find_all('a', href=True)
        
        for link in all_links:
            href = link.get('href')
            
            # Filter hanya link drama
            if '/drama/' in href:
                full_url = href if href.startswith('http') else f"{BASE_URL}{href}"
                
                # Hindari duplikat
                if full_url in seen_urls:
                    continue
                seen_urls.add(full_url)

                # Coba cari judul dan gambar di dalam tag <a> tersebut atau parent-nya
                # Biasanya struktur: <a> <img src="..."> <div>Judul</div> </a>
                title = link.get_text(strip=True)
                
                # Jika text kosong, mungkin judul ada di atribut title atau alt gambar
                img_tag = link.find('img')
                thumbnail = None
                
                if img_tag:
                    thumbnail = img_tag.get('src')
                    if not title:
                        title = img_tag.get('alt', 'No Title')
                
                # Jika masih tidak ada title, coba cari di parent container
                if not title:
                    parent = link.find_parent()
                    if parent:
                        title = parent.get_text(strip=True)

                # Bersihkan title jika terlalu panjang/kotor
                if len(title) > 100: 
                    title = title[:100] + "..."

                results.append({
                    "title": title,
                    "url": full_url,
                    "thumbnail": thumbnail
                })
    
    return jsonify({
        "query": query, 
        "count": len(results), 
        "results": results
    })

@app.route('/api/detail')
def detail():
    target_url = request.args.get('url')
    if not target_url:
        return jsonify({"error": "Parameter 'url' is required"}), 400

    soup = get_soup(target_url)
    if not soup:
        return jsonify({"error": "Failed to fetch detail or blocked"}), 500

    data = {
        "title": "Unknown",
        "description": "No description found",
        "episodes": []
    }

    # Ambil Judul (Cari H1 pertama)
    h1 = soup.find('h1')
    if h1:
        data['title'] = h1.get_text(strip=True)

    # Ambil Deskripsi (Cari tag p atau div yang panjang teksnya lumayan)
    paragraphs = soup.find_all(['p', 'div'])
    for p in paragraphs:
        text = p.get_text(strip=True)
        # Asumsi deskripsi biasanya lebih dari 50 karakter tapi kurang dari 1000
        if 50 < len(text) < 1000 and "Sinopsis" not in text:
            data['description'] = text
            break

    # Ambil Episode (Cari semua link yang mengandung '/watch/')
    ep_links = soup.find_all('a', href=True)
    seen_eps = set()
    
    for link in ep_links:
        href = link.get('href')
        if '/watch/' in href:
            full_ep_url = href if href.startswith('http') else f"{BASE_URL}{href}"
            
            if full_ep_url not in seen_eps:
                seen_eps.add(full_ep_url)
                ep_name = link.get_text(strip=True)
                # Fallback nama episode
                if not ep_name:
                    ep_name = f"Episode {len(seen_eps)}"
                
                data['episodes'].append({
                    "episode": ep_name,
                    "url": full_ep_url
                })

    return jsonify(data)

@app.route('/api/watch')
def watch():
    target_url = request.args.get('url')
    if not target_url:
        return jsonify({"error": "Parameter 'url' is required"}), 400

    soup = get_soup(target_url)
    if not soup:
        return jsonify({"error": "Failed to fetch watch page"}), 500

    video_data = {
        "original_url": target_url,
        "streams": []
    }

    # Teknik 1: Cari tag Iframe (paling umum di situs dracin)
    iframes = soup.find_all('iframe')
    for iframe in iframes:
        src = iframe.get('src')
        if src:
            video_data['streams'].append({"type": "iframe", "url": src})

    # Teknik 2: Cari Script yang mengandung .m3u8 atau .mp4
    scripts = soup.find_all('script')
    for script in scripts:
        if script.string:
            # Regex untuk url m3u8/mp4
            urls = re.findall(r'(https?://[^\s"\']+\.(?:m3u8|mp4))', script.string)
            for url in urls:
                 video_data['streams'].append({"type": "direct_stream", "url": url})

    return jsonify(video_data)

if __name__ == '__main__':
    app.run(debug=True)
