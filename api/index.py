from fastapi import FastAPI
from fastapi.responses import JSONResponse
import requests
from bs4 import BeautifulSoup
import re

app = FastAPI(title="Samehadaku Scraper V8 Final")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Referer": "https://samehadaku.how/",
    "Accept-Language": "id-ID,id;q=0.9,en-US;q=0.8,en;q=0.7"
}

BASE_URL = "https://v1.samehadaku.how"

def get_soup(url: str):
    try:
        session = requests.Session()
        # Timeout dinaikin biar kalo server lemot tetep dapet
        req = session.get(url, headers=HEADERS, timeout=20) 
        req.raise_for_status()
        return BeautifulSoup(req.text, "html.parser")
    except Exception as e:
        print(f"Error scraping {url}: {e}")
        return None

# --- FUNGSI PARSER SAKTI (Extractor Universal) ---
def extract_metadata(node):
    """Mencari Judul, Link, & Gambar dengan segala cara"""
    try:
        # 1. Cari LINK dulu (Paling Penting)
        a_tag = node.find("a", href=True)
        if not a_tag: return None # Gak ada link = sampah
        
        link = a_tag['href']
        
        # 2. Cari JUDUL
        # Prioritas: Title attribute -> Text di h2 -> Text di div.title -> Text di a
        title = ""
        if a_tag.get("title"): 
            title = a_tag.get("title")
        elif node.find("h2", class_="entry-title"):
            title = node.find("h2", class_="entry-title").get_text(strip=True)
        elif node.find("div", class_="title"):
            title = node.find("div", class_="title").get_text(strip=True)
        elif node.find("div", class_="dtla"): # Kadang judul nyelip disini
            title = node.find("div", class_="dtla").find("h2").get_text(strip=True)
        else:
            title = a_tag.get_text(strip=True)
            
        if len(title) < 3: return None # Judul terlalu pendek = sampah
        
        # 3. Cari GAMBAR (Handle Lazy Load)
        img_tag = node.find("img")
        thumb = "https://dummyimage.com/300x400/000/fff&text=No+Image"
        if img_tag:
            # Cek urutan atribut yang mungkin berisi link gambar asli
            for attr in ['src', 'data-src', 'data-lazy-src', 'srcset']:
                if img_tag.get(attr) and "http" in img_tag.get(attr):
                    thumb = img_tag.get(attr).split(" ")[0] # Ambil link pertama kalau ada spasi
                    break

        # 4. Info Tambahan (Episode/Rating)
        episode = "New"
        ep_tag = node.find(["span", "div"], class_=re.compile(r'(episode|ep|dtla)'))
        if ep_tag: episode = ep_tag.get_text(strip=True)

        return {
            "title": title,
            "link": link,
            "thumbnail": thumb,
            "episode": episode
        }
    except:
        return None

@app.get("/")
def home():
    return {"status": "Online", "msg": "Samehadaku API V8 - Brute Force Mode"}

# --- 1. LATEST (FIX JUMLAH DIKIT & TITLE) ---
@app.get("/api/latest")
def get_latest():
    soup = get_soup(f"{BASE_URL}/anime-terbaru/")
    if not soup: return {"success": False}
    
    data = []
    seen_links = set()
    
    # STRATEGI: Ambil SEMUA elemen 'li', 'article', atau 'div' yang punya class
    # Kita filter manual nanti biar gak kelewat
    potential_items = soup.find_all(["li", "article", "div"])
    
    for item in potential_items:
        # Filter: Elemen harus punya class yang mengandung 'post', 'anime', atau 'article'
        classes = " ".join(item.get("class", []))
        if not re.search(r'(post|anime|article)', classes):
            continue
            
        # Jangan ambil elemen pembungkus (wrapper), ambil itemnya aja
        if "swiper" in classes or "widget" in classes: continue

        parsed = extract_metadata(item)
        
        # Validasi akhir: Harus link anime (bukan link page/kategori)
        if parsed and "/anime/" in parsed['link'] and parsed['link'] not in seen_links:
            data.append(parsed)
            seen_links.add(parsed['link'])
            
    # Kalau masih dikit, coba fallback ke struktur list biasa
    if len(data) < 5:
        ul_list = soup.find("ul") # Biasanya list utama itu ul pertama/kedua
        if ul_list:
            for li in ul_list.find_all("li"):
                parsed = extract_metadata(li)
                if parsed and parsed['link'] not in seen_links:
                    data.append(parsed)
                    seen_links.add(parsed['link'])

    return JSONResponse(content={"success": True, "total": len(data), "data": data})

# --- 2. JADWAL (FIX KOSONG & HARI INGGRIS) ---
@app.get("/api/schedule")
def get_schedule():
    soup = get_soup(f"{BASE_URL}/jadwal-rilis/")
    if not soup: return {"success": False}
    
    # Struktur Output
    schedule = {k: [] for k in ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]}
    
    # Mapping
    day_map = {
        "senin": "Monday", "selasa": "Tuesday", "rabu": "Wednesday",
        "kamis": "Thursday", "jumat": "Friday", "sabtu": "Saturday", "minggu": "Sunday"
    }
    
    # ALGORITMA SCANNING:
    # Kita iterasi semua elemen HTML Text. Kalau ketemu "Senin", set flag "current_day" = "Monday".
    # Semua link anime yang ditemukan SETELAHNYA akan masuk ke "Monday", sampai ketemu "Selasa".
    
    current_day = None
    
    # Cari area konten utama
    main_area = soup.find("div", class_="entry-content") or soup.find("main") or soup
    
    # Ambil semua elemen penting secara berurutan
    all_elements = main_area.find_all(["h2", "h3", "h4", "div", "li", "span"])
    
    for el in all_elements:
        text = el.get_text(strip=True).lower()
        
        # 1. Cek Ganti Hari
        if text in day_map:
            current_day = day_map[text]
            continue # Skip elemen header ini, lanjut ke bawahnya
            
        # 2. Ambil Anime (Hanya kalau hari sudah terdeteksi)
        if current_day:
            # Cek apakah elemen ini adalah item anime?
            # Syarat: Punya class 'animepost' ATAU tag 'li' yang ada linknya
            is_anime_node = False
            classes = el.get("class", [])
            
            if "animepost" in classes or el.name == "li":
                # Pastikan bukan header sampah
                if el.find("a") and not el.find("h3"): 
                    is_anime_node = True
            
            if is_anime_node:
                parsed = extract_metadata(el)
                # Validasi link anime valid & belum ada di list hari itu
                if parsed and "/anime/" in parsed['link']:
                    # Cek duplikat
                    if not any(x['title'] == parsed['title'] for x in schedule[current_day]):
                        schedule[current_day].append(parsed)

    return JSONResponse(content={"success": True, "data": schedule})

# --- 3. DETAIL & SEARCH (TETAP SEPERTI SEBELUMNYA) ---
@app.get("/api/detail")
def get_detail(url: str):
    soup = get_soup(url)
    if not soup: return {"success": False}
    try:
        title = soup.find("h1", class_="entry-title").get_text(strip=True)
        img = soup.find("div", class_="thumb").find("img")['src'] if soup.find("div", class_="thumb") else None
        
        synopsis = "-"
        desc_div = soup.find("div", class_="desc") or soup.find("div", class_="entry-content")
        if desc_div: synopsis = desc_div.get_text(strip=True)

        episodes = []
        for li in soup.select(".lstepsiode li"):
            episodes.append({
                "title": li.find("a").get_text(strip=True),
                "url": li.find("a")['href'],
                "date": li.find("span", class_="date").get_text(strip=True) if li.find("span", class_="date") else "?"
            })
            
        iframe = soup.find("iframe")
        stream = iframe['src'] if iframe else None
        
        return {"success": True, "result": {"title": title, "cover": img, "synopsis": synopsis, "episodes": episodes, "stream_url": stream}}
    except Exception as e:
        return {"success": False, "error": str(e)}

@app.get("/api/search")
def search(query: str):
    soup = get_soup(f"{BASE_URL}/?s={query}")
    data = []
    if soup:
        for item in soup.select(".animepost"):
            parsed = extract_metadata(item)
            if parsed: data.append(parsed)
    return {"success": True, "results": data}
