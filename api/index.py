from flask import Flask, jsonify, request
import requests
from bs4 import BeautifulSoup
import re

app = Flask(__name__)

# Base URL target
BASE_URL = "https://dracin.io"

# Header agar tidak dideteksi sebagai bot
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
}

def get_soup(url):
    try:
        response = requests.get(url, headers=HEADERS)
        response.raise_for_status()
        return BeautifulSoup(response.text, 'html.parser')
    except Exception as e:
        print(f"Error fetching {url}: {e}")
        return None

@app.route('/')
def home():
    return jsonify({
        "message": "Dracin Scraper API is Running",
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
    
    # URL Search construction
    search_url = f"{BASE_URL}/search?q={query}"
    soup = get_soup(search_url)
    
    results = []
    if soup:
        # Asumsi struktur: mencari container hasil search
        # Note: Class css harus disesuaikan jika dracin.io mengubah stylenya
        # Di sini kita mencoba menangkap elemen umum grid drama
        items = soup.find_all('div', class_=re.compile('col-6|col-md-2')) 
        
        for item in items:
            link_tag = item.find('a')
            if link_tag:
                title = item.get_text(strip=True)
                href = link_tag.get('href')
                img_tag = item.find('img')
                thumbnail = img_tag.get('src') if img_tag else None
                
                # Filter agar hanya link drama yang masuk
                if href and '/drama/' in href:
                    results.append({
                        "title": title,
                        "url": href if href.startswith('http') else f"{BASE_URL}{href}",
                        "thumbnail": thumbnail
                    })
    
    return jsonify({"query": query, "results": results})

@app.route('/api/detail')
def detail():
    target_url = request.args.get('url')
    if not target_url:
        return jsonify({"error": "Parameter 'url' is required"}), 400

    soup = get_soup(target_url)
    if not soup:
        return jsonify({"error": "Failed to fetch detail"}), 500

    data = {
        "title": "Unknown",
        "description": "",
        "episodes": []
    }

    # Ambil Judul
    title_elem = soup.find('h1')
    if title_elem:
        data['title'] = title_elem.get_text(strip=True)

    # Ambil Deskripsi
    desc_elem = soup.find('p', class_=re.compile('description|content'))
    if desc_elem:
        data['description'] = desc_elem.get_text(strip=True)

    # Ambil Episode List
    # Biasanya list episode ada di dalam div list atau ul/li
    episode_links = soup.find_all('a', href=re.compile(r'/watch/'))
    
    for link in episode_links:
        ep_url = link.get('href')
        ep_name = link.get_text(strip=True)
        full_ep_url = ep_url if ep_url.startswith('http') else f"{BASE_URL}{ep_url}"
        
        # Hindari duplikasi
        if not any(d['url'] == full_ep_url for d in data['episodes']):
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
        "source": None,
        "type": "unknown",
        "method": "direct_scrape"
    }

    # 1. Coba cari tag <video> source
    video_tag = soup.find('video')
    if video_tag:
        source = video_tag.find('source')
        if source:
            video_data['source'] = source.get('src')
            video_data['type'] = 'direct_video'

    # 2. Coba cari Iframe (Sering dipakai untuk embed player)
    if not video_data['source']:
        iframe = soup.find('iframe')
        if iframe:
            video_data['source'] = iframe.get('src')
            video_data['type'] = 'iframe_embed'

    # 3. Coba cari Script variable (m3u8 atau mp4 yang di-hardcode di JS)
    if not video_data['source']:
        scripts = soup.find_all('script')
        for script in scripts:
            if script.string:
                # Cari pola URL umum di dalam script
                m3u8_match = re.search(r'(https?://[^\s"\']+\.m3u8)', script.string)
                mp4_match = re.search(r'(https?://[^\s"\']+\.mp4)', script.string)
                
                if m3u8_match:
                    video_data['source'] = m3u8_match.group(1)
                    video_data['type'] = 'hls_stream'
                    break
                elif mp4_match:
                    video_data['source'] = mp4_match.group(1)
                    video_data['type'] = 'mp4_direct'
                    break

    return jsonify(video_data)

# Handler untuk Vercel
# Vercel membutuhkan 'app' object
if __name__ == '__main__':
    app.run(debug=True)
