from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import JSONResponse
import requests
from bs4 import BeautifulSoup
import re

app = FastAPI(title="Samehadaku API Final Suite")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Referer": "https://samehadaku.how/",
    "Accept-Language": "id-ID,id;q=0.9,en-US;q=0.8,en;q=0.7"
}

BASE_URL = "https://v1.samehadaku.how"

# --- HELPERS ---

def get_soup(url: str):
    try:
        session = requests.Session()
        req = session.get(url, headers=HEADERS, timeout=20)
        req.raise_for_status()
        return BeautifulSoup(req.text, "html.parser")
    except Exception as e:
        print(f"Error scraping {url}: {e}")
        return None

def extract_id(url):
    """Ambil slug terakhir dari URL"""
    if not url: return ""
    return url.strip("/").split("/")[-1]

def extract_poster(node):
    img = node.find("img")
    if not img: return "https://dummyimage.com/300x400/000/fff&text=No+Image"
    poster = img.get('src')
    if not poster or "data:image" in poster:
        poster = img.get('data-src') or img.get('srcset') or poster
    return poster.split("?")[0] if poster else ""

def parse_genre_list(node):
    genres = []
    # Support selector list page (.genres) dan detail page (.genre-info)
    links = node.select(".genres a") or node.select(".genre-info a") or node.select(".genre a")
    for g in links:
        g_id = extract_id(g['href'])
        genres.append({
            "title": g.get_text(strip=True),
            "genreId": g_id,
            "href": f"/anime/samehadaku/genres/{g_id}",
            "samehadakuUrl": g['href']
        })
    return genres

def get_pagination(soup, current_page):
    pagination = soup.find("div", class_="pagination")
    if not pagination: return None
    
    page_links = pagination.find_all("a", class_="page-numbers")
    total_pages = 1
    if page_links:
        nums = [int(p.get_text(strip=True)) for p in page_links if p.get_text(strip=True).isdigit()]
        if nums: total_pages = max(nums)
    
    has_next = bool(pagination.find("a", class_="next"))
    has_prev = bool(pagination.find("a", class_="prev"))
    
    return {
        "currentPage": current_page,
        "hasPrevPage": has_prev,
        "prevPage": current_page - 1 if has_prev else None,
        "hasNextPage": has_next,
        "nextPage": current_page + 1 if has_next else None,
        "totalPages": total_pages
    }

# --- ENDPOINT 1: GENRES ---
@app.get("/anime/samehadaku/genres/{genre_id}")
def get_anime_by_genre(genre_id: str, page: int = 1):
    url = f"{BASE_URL}/genre/{genre_id}/page/{page}/"
    if page == 1: url = f"{BASE_URL}/genre/{genre_id}/"
    
    soup = get_soup(url)
    if not soup: return JSONResponse({"status": "failed", "message": "Genre not found"}, 404)
    
    anime_list = []
    nodes = soup.select(".animepost")
    for node in nodes:
        try:
            a_tag = node.find("a")
            if not a_tag: continue
            
            real_url = a_tag['href']
            anime_id = extract_id(real_url)
            
            score = "?"
            score_tag = node.find("div", class_="score")
            if score_tag: score = score_tag.get_text(strip=True)
            
            anime_list.append({
                "title": node.find("div", class_="title").get_text(strip=True),
                "poster": extract_poster(node),
                "score": score,
                "animeId": anime_id,
                "href": f"/anime/samehadaku/anime/{anime_id}",
                "genreList": parse_genre_list(node)
            })
        except: continue

    return JSONResponse({
        "status": "success",
        "data": { "animeList": anime_list },
        "pagination": get_pagination(soup, page)
    })

# --- ENDPOINT 2: BATCH LIST ---
@app.get("/anime/samehadaku/batch")
def get_batch_list(page: int = 1):
    url = f"{BASE_URL}/daftar-batch/page/{page}/"
    if page == 1: url = f"{BASE_URL}/daftar-batch/"
    
    soup = get_soup(url)
    if not soup: return JSONResponse({"status": "failed"}, 500)
    
    batch_list = []
    nodes = soup.select(".animepost")
    for node in nodes:
        try:
            a_tag = node.find("a")
            if not a_tag: continue
            real_url = a_tag['href']
            batch_id = extract_id(real_url)
            
            batch_list.append({
                "title": node.find("div", class_="title").get_text(strip=True),
                "poster": extract_poster(node),
                "batchId": batch_id,
                "href": f"/anime/samehadaku/batch/{batch_id}", # Kalau mau detail batch bisa ditambah endpoint baru
                "samehadakuUrl": real_url,
                "genreList": parse_genre_list(node)
            })
        except: continue
        
    return JSONResponse({
        "status": "success",
        "data": { "batchList": batch_list },
        "pagination": get_pagination(soup, page)
    })

# --- ENDPOINT 3: ANIME DETAIL ---
@app.get("/anime/samehadaku/anime/{anime_id}")
def get_anime_detail(anime_id: str):
    url = f"{BASE_URL}/anime/{anime_id}/"
    soup = get_soup(url)
    if not soup: return JSONResponse({"status": "failed", "message": "Not found"}, 404)
    
    try:
        title = soup.find("h1", class_="entry-title").get_text(strip=True)
        poster = extract_poster(soup.find("div", class_="thumb"))
        
        # Info Parsing
        infos = {}
        spe_list = soup.select(".infox .spe span")
        for spe in spe_list:
            text = spe.get_text(strip=True)
            if ":" in text:
                key, val = text.split(":", 1)
                infos[key.strip().lower()] = val.strip()

        # Synopsis
        synopsis_div = soup.find("div", class_="desc") or soup.find("div", class_="entry-content")
        paragraphs = []
        if synopsis_div:
            ps = synopsis_div.find_all("p")
            if ps:
                paragraphs = [p.get_text(strip=True) for p in ps if p.get_text(strip=True)]
            else:
                paragraphs = [synopsis_div.get_text(strip=True)]

        # Episode List
        episodes = []
        ep_list = soup.select(".lstepsiode li")
        for li in ep_list:
            a_tag = li.find("a")
            if not a_tag: continue
            
            ep_url = a_tag['href']
            ep_id = extract_id(ep_url)
            
            episodes.append({
                "title": li.find("span", class_="epl-title").get_text(strip=True) if li.find("span", class_="epl-title") else a_tag.get_text(strip=True),
                "episodeId": ep_id,
                "href": f"/anime/samehadaku/episode/{ep_id}",
                "date": li.find("span", class_="date").get_text(strip=True) if li.find("span", class_="date") else "?"
            })

        data = {
            "title": title,
            "poster": poster,
            "score": infos.get("score", "?"),
            "status": infos.get("status", "Unknown"),
            "type": infos.get("type", "TV"),
            "synopsis": { "paragraphs": paragraphs },
            "genreList": parse_genre_list(soup.find("div", class_="genre-info")),
            "episodeList": episodes
        }
        
        return JSONResponse({"status": "success", "data": data})
    except Exception as e:
        return JSONResponse({"status": "failed", "error": str(e)}, 500)

# --- ENDPOINT 4: EPISODE DETAIL (DOWNLOAD LINKS) ---
@app.get("/anime/samehadaku/episode/{episode_id}")
def get_episode_detail(episode_id: str):
    # Samehadaku episode URL biasanya di root: samehadaku.how/slug-episode/
    url = f"{BASE_URL}/{episode_id}/"
    soup = get_soup(url)
    if not soup: return JSONResponse({"status": "failed", "message": "Episode not found"}, 404)
    
    try:
        title = soup.find("h1", class_="entry-title").get_text(strip=True)
        
        # Next/Prev Navigation
        nav = { "prev": None, "next": None }
        prev_a = soup.find("a", class_="prev") or soup.find("div", class_="naveps bignav").find("a", attrs={"href": True}, string="Previous")
        next_a = soup.find("a", class_="next") or soup.find("div", class_="naveps bignav").find("a", attrs={"href": True}, string="Next")
        
        if prev_a and "/anime/" not in prev_a['href']: # Validasi bukan link ke list anime
            nav["prev"] = f"/anime/samehadaku/episode/{extract_id(prev_a['href'])}"
        if next_a and "/anime/" not in next_a['href']:
            nav["next"] = f"/anime/samehadaku/episode/{extract_id(next_a['href'])}"

        # --- DOWNLOAD LINKS PARSING (COMPLEX) ---
        download_formats = []
        
        # Cari container download
        download_box = soup.find("div", class_="download-eps") or soup.find("div", id="server")
        
        if download_box:
            # Samehadaku sering ganti struktur. Biasanya:
            # <ul> untuk setiap format (MP4, MKV)
            # <li> untuk setiap kualitas
            # <strong> untuk label kualitas
            
            # Kita cari semua unordered list (ul) di dalam box
            uls = download_box.find_all("ul")
            
            for ul in uls:
                # Cari Judul Format (MP4 / MKV / x265)
                # Biasanya ada di elemen sebelum <ul> (misal <p><b>MP4</b></p> atau <h4>)
                format_title = "Unknown Format"
                prev_elem = ul.find_previous(["p", "h4", "div", "span"])
                if prev_elem:
                    format_title = prev_elem.get_text(strip=True)
                
                # Bersihkan title (kadang ada text sampah)
                if "MKV" in format_title: format_title = "MKV"
                elif "x265" in format_title: format_title = "x265 [Mode Irit Kuota]"
                elif "MP4" in format_title: format_title = "MP4"
                
                qualities = []
                
                # Loop setiap baris kualitas (li)
                lis = ul.find_all("li")
                for li in lis:
                    # Ambil label kualitas (360p, 480p, dll)
                    q_tag = li.find("strong") or li.find("b")
                    quality_name = q_tag.get_text(strip=True) if q_tag else "Unknown"
                    
                    # Ambil Link
                    urls = []
                    links = li.find_all("a")
                    for link in links:
                        urls.append({
                            "title": link.get_text(strip=True),
                            "url": link['href']
                        })
                    
                    qualities.append({
                        "title": quality_name,
                        "urls": urls
                    })
                
                # Jika format ini punya qualities, tambahkan ke list utama
                if qualities:
                    download_formats.append({
                        "title": format_title,
                        "qualities": qualities
                    })

        # STREAM LINK (Iframe)
        stream_url = ""
        iframe = soup.find("iframe")
        if iframe: stream_url = iframe['src']

        data = {
            "title": title,
            "streamUrl": stream_url,
            "navigation": nav,
            "downloads": download_formats
        }
        
        return JSONResponse({"status": "success", "data": data})

    except Exception as e:
        return JSONResponse({"status": "failed", "error": str(e)}, 500)

@app.get("/")
def home():
    return {"message": "Samehadaku API V14 - Full Endpoints Ready"}
