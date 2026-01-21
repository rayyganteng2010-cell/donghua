const express = require('express');
const axios = require('axios');
const cheerio = require('cheerio');
const cors = require('cors');

const app = express();
app.use(cors());

// Gunakan URL utama (kadang v1 diblokir, coba URL root jika v1 gagal)
// Tapi kita tetap pakai v1 sesuai request lu, dengan headers lebih kuat.
const BASE_URL = 'https://samehadaku.how'; 

// --- ANTI-BOT HEADERS (STEALTH MODE) ---
const HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
    'Accept-Language': 'en-US,en;q=0.9,id;q=0.8',
    'Referer': 'https://samehadaku.how/',
    'Connection': 'keep-alive',
    'Upgrade-Insecure-Requests': '1',
    'Sec-Fetch-Dest': 'document',
    'Sec-Fetch-Mode': 'navigate',
    'Sec-Fetch-Site': 'none',
    'Sec-Fetch-User': '?1',
    'Cache-Control': 'max-age=0'
};

// Buat instance axios khusus
const client = axios.create({
    headers: HEADERS,
    timeout: 10000, // Timeout 10 detik
    validateStatus: (status) => status < 500 // Biar 404/403 gak langsung throw error di axios
});

// --- HELPERS ---

const extractId = (url) => {
    if (!url) return '';
    const parts = url.replace(/\/$/, '').split('/');
    return parts[parts.length - 1];
};

const extractPoster = ($node) => {
    const img = $node.find('img');
    let src = img.attr('src') || img.attr('data-src') || img.attr('srcset');
    if (!src || src.includes('data:image')) {
        src = img.attr('data-src') || img.attr('src');
    }
    if (!src) return "https://dummyimage.com/300x400/000/fff&text=No+Image";
    return src.split('?')[0];
};

const parseGenreList = ($, $node) => {
    const genres = [];
    const links = $node.find('a[href*="/genre/"]');
    links.each((i, el) => {
        const href = $(el).attr('href');
        const title = $(el).text().trim();
        const id = extractId(href);
        if (id) {
            genres.push({
                title: title,
                genreId: id,
                href: `/samehadaku/genres/${id}`,
                samehadakuUrl: href
            });
        }
    });
    return genres;
};

const getPagination = ($, currentPage) => {
    const $pagination = $('.pagination');
    if (!$pagination.length) return null;

    let totalPages = 1;
    $pagination.find('.page-numbers').each((i, el) => {
        const txt = $(el).text().replace(/,/g, '').trim();
        if (!isNaN(txt)) {
            const num = parseInt(txt);
            if (num > totalPages) totalPages = num;
        }
    });

    const hasNext = $pagination.find('.next').length > 0;
    const hasPrev = $pagination.find('.prev').length > 0;
    const curr = parseInt(currentPage);

    return {
        currentPage: curr,
        hasPrevPage: hasPrev,
        prevPage: hasPrev ? curr - 1 : null,
        hasNextPage: hasNext,
        nextPage: hasNext ? curr + 1 : null,
        totalPages: totalPages
    };
};

// --- PARSERS ---

const parseLatestItem = ($, el) => {
    try {
        const aTag = $(el).find('a').first();
        if (!aTag.length) return null;

        const href = aTag.attr('href');
        const id = extractId(href);
        let title = $(el).find('.title').text().trim() || aTag.attr('title') || "Unknown";
        const poster = extractPoster($(el));

        let ep = '?';
        let released = '?';
        
        const fullText = $(el).text().replace(/\s+/g, ' '); 

        const epTag = $(el).find('.episode, .dtla');
        const dateTag = $(el).find('.date, .year');

        if (epTag.length) {
            const rawEp = epTag.text().trim();
            const mEp = rawEp.match(/(?:Episode\s*)?(\d+)/i);
            if (mEp) ep = mEp[1];
        }

        if (dateTag.length) {
            released = dateTag.text().trim();
        } else {
            const mDate = fullText.match(/(\d+\s+\w+\s+yang lalu)/i);
            if (mDate) released = mDate[1];
        }

        return {
            title, poster, episodes: ep, releasedOn: released,
            animeId: id, href: `/samehadaku/anime/${id}`, samehadakuUrl: href
        };
    } catch (e) { return null; }
};

const parseLibraryItem = ($, el, statusForce = 'Ongoing') => {
    try {
        const aTag = $(el).find('a').first();
        if (!aTag.length) return null;

        const href = aTag.attr('href');
        const id = extractId(href);
        const title = $(el).find('.title').text().trim() || "Unknown";
        const poster = extractPoster($(el));
        const score = $(el).find('.score').text().trim() || '?';
        const type = $(el).find('.type').text().trim() || 'TV';

        return {
            title, poster, type, score, status: statusForce,
            animeId: id, href: `/samehadaku/anime/${id}`,
            samehadakuUrl: href, genreList: parseGenreList($, $(el))
        };
    } catch (e) { return null; }
};

// --- ROUTES ---

app.get('/', (req, res) => {
    res.json({ message: "Samehadaku API V29 (Anti-Bot Headers) is Running" });
});

// Helper wrapper untuk request agar error 403 tertangkap rapi
const fetchPage = async (url) => {
    try {
        const response = await client.get(url);
        // Jika masih 403/404, throw error manual biar masuk catch
        if (response.status !== 200) {
            throw new Error(`Request failed with status code ${response.status}`);
        }
        return cheerio.load(response.data);
    } catch (error) {
        console.error(`Error fetching ${url}:`, error.message);
        return null;
    }
};

// 1. HOME
app.get('/anime/samehadaku/home', async (req, res) => {
    const $ = await fetchPage(BASE_URL);
    if (!$) return res.status(500).json({ status: "failed", message: "Server blocked connection (403)" });

    const recent = [];
    $('.post-show li, .animepost').slice(0, 10).each((i, el) => {
        const item = parseLatestItem($, el);
        if (item) recent.push(item);
    });

    const top10 = [];
    $('.widget_senction.popular .serieslist li, .serieslist.pop li').each((i, el) => {
        const p = parseLibraryItem($, el);
        if (p) top10.push({
            rank: i+1, title: p.title, poster: p.poster, score: p.score,
            animeId: p.animeId, href: p.href, samehadakuUrl: p.samehadakuUrl
        });
    });

    res.json({
        status: "success", creator: "Sanka Vollerei", message: "",
        data: {
            recent: { href: "/samehadaku/recent", samehadakuUrl: `${BASE_URL}/anime-terbaru/`, animeList: recent },
            top10: { href: "/samehadaku/top10", samehadakuUrl: BASE_URL, animeList: top10 },
            batch: { href: "/samehadaku/batch", samehadakuUrl: `${BASE_URL}/daftar-batch/`, batchList: [] },
            movie: { href: "/samehadaku/movies", samehadakuUrl: `${BASE_URL}/anime-movie/`, animeList: [] }
        }
    });
});

// 2. SCHEDULE
app.get('/anime/samehadaku/schedule', async (req, res) => {
    const $ = await fetchPage(`${BASE_URL}/jadwal-rilis/`);
    if (!$) return res.status(500).json({ status: "failed", message: "Server blocked connection (403)" });

    const dayMap = [
        {eng:"Monday", indo:"senin"}, {eng:"Tuesday", indo:"selasa"}, {eng:"Wednesday", indo:"rabu"},
        {eng:"Thursday", indo:"kamis"}, {eng:"Friday", indo:"jumat"}, {eng:"Saturday", indo:"sabtu"}, {eng:"Sunday", indo:"minggu"}
    ];

    const days = [];
    const content = $('.entry-content, main').first();

    for (const {eng, indo} of dayMap) {
        let list = [];
        let container = content.find(`#${indo}, .${indo}`);
        
        if (!container.length) {
            content.find('h3, h4, b').each((i, el) => {
                if ($(el).text().toLowerCase().includes(indo)) {
                    container = $(el).next();
                }
            });
        }

        if (container && container.length) {
            container.find('.animepost, li').each((i, el) => {
                const link = $(el).find('a').attr('href');
                if (link && link.includes('/anime/')) {
                    const p = parseLibraryItem($, el);
                    if (p) {
                        delete p.status;
                        let est = "Update";
                        const timeTag = $(el).find('.time, .btime');
                        if (timeTag.length) est = timeTag.text().trim();
                        else {
                            const tt = $(el).find('.ttls, .dtla').text();
                            const m = tt.match(/(?:Pukul|Jam|Time|Rilis)\s*:\s*([\d\:]+)/i);
                            if(m) est = m[1].trim();
                        }
                        p.estimation = est;
                        if(!list.find(x => x.title === p.title)) list.push(p);
                    }
                }
            });
        }
        days.push({ day: eng, animeList: list });
    }
    res.json({ status: "success", creator: "Sanka Vollerei", message: "", data: { days } });
});

// 3. LISTS
const createListHandler = (urlFn, parserFn) => async (req, res) => {
    const page = req.query.page || 1;
    const url = urlFn(page, req.query);
    const $ = await fetchPage(url);
    if (!$) return res.status(500).json({ status: "failed", message: "Server blocked connection (403)" });

    const animeList = [];
    $('.post-show li, .animepost').each((i, el) => {
        const item = parserFn($, el);
        if (item) animeList.push(item);
    });

    res.json({ status: "success", creator: "Sanka Vollerei", message: "", data: { animeList }, pagination: getPagination($, page) });
};

app.get('/anime/samehadaku/latest', createListHandler(
    (p) => p > 1 ? `${BASE_URL}/anime-terbaru/page/${p}/` : `${BASE_URL}/anime-terbaru/`,
    parseLatestItem
));

app.get('/anime/samehadaku/ongoing', createListHandler(
    (p) => `${BASE_URL}/daftar-anime-2/${p > 1 ? `page/${p}/` : ''}?status=Currently+Airing&order=update`,
    ($, el) => parseLibraryItem($, el, 'Ongoing')
));

app.get('/anime/samehadaku/completed', createListHandler(
    (p) => `${BASE_URL}/daftar-anime-2/${p > 1 ? `page/${p}/` : ''}?status=Finished+Airing&order=latest`,
    ($, el) => parseLibraryItem($, el, 'Completed')
));

app.get('/anime/samehadaku/popular', createListHandler(
    (p) => `${BASE_URL}/daftar-anime-2/${p > 1 ? `page/${p}/` : ''}?order=popular`,
    ($, el) => parseLibraryItem($, el, 'Popular')
));

app.get('/anime/samehadaku/search', createListHandler(
    (p, q) => `${BASE_URL}/${p > 1 ? `page/${p}/` : ''}?s=${q.query || q.s || ''}`,
    ($, el) => parseLibraryItem($, el)
));

// 4. DETAIL ANIME
app.get('/anime/samehadaku/anime/:id', async (req, res) => {
    const $ = await fetchPage(`${BASE_URL}/anime/${req.params.id}/`);
    if (!$) return res.status(404).json({ status: "failed", message: "Not found or Blocked" });

    // Clean Title
    let titleRaw = $('h1.entry-title').text().trim();
    // Biarkan string kosong sesuai request sebelumnya, atau isi titleRaw jika mau
    const title = ""; 

    const poster = extractPoster($('.thumb'));
    
    const infos = {};
    $('.infox .spe span').each((i, el) => {
        const txt = $(el).text();
        const parts = txt.split(':');
        if (parts.length > 1) {
            const k = parts[0].trim().toLowerCase();
            const v = parts.slice(1).join(':').trim();
            infos[k] = v;
        }
    });

    const scoreVal = infos['score'] || $('.ratingValue').text().trim() || '?';
    const userCount = $('span[itemprop="ratingCount"]').text().trim();
    const users = userCount ? `${userCount} users` : 'N/A';

    const paragraphs = [];
    $('.desc p, .entry-content p').each((i, el) => {
        if ($(el).text().trim()) paragraphs.push($(el).text().trim());
    });

    const episodes = [];
    $('.lstepsiode li').each((i, el) => {
        const a = $(el).find('a');
        const href = a.attr('href');
        const epId = extractId(href);
        const rawTitle = $(el).find('.epl-title').text().trim() || a.text().trim();
        
        let epNum = rawTitle;
        const m = rawTitle.match(/\d+/);
        if (m) epNum = parseInt(m[0]);

        episodes.push({
            title: epNum,
            episodeId: epId,
            href: `/samehadaku/episode/${epId}`,
            samehadakuUrl: href
        });
    });

    const genreList = parseGenreList($, $('.genre-info'));

    const respData = {
        title,
        poster,
        score: { value: scoreVal, users },
        japanese: infos['japanese'] || '-', synonyms: infos['synonyms'] || '-', english: infos['english'] || '-',
        status: infos['status'] || 'Unknown', type: infos['type'] || 'TV', source: infos['source'] || '-',
        duration: infos['duration'] || '-', episodes: parseInt(infos['total episode']) || null,
        season: infos['season'] || '-', studios: infos['studio'] || '-', producers: infos['producers'] || '-',
        aired: infos['released'] || '-', trailer: $('.trailer-anime iframe').attr('src') || "",
        synopsis: { paragraphs, connections: [] },
        genreList,
        batchList: [],
        episodeList: episodes
    };

    res.json({ status: "success", creator: "Sanka Vollerei", message: "", data: respData, pagination: null });
});

// 5. EPISODE
app.get('/anime/samehadaku/episode/:id', async (req, res) => {
    const $ = await fetchPage(`${BASE_URL}/${req.params.id}/`);
    if (!$) return res.status(404).json({ status: "failed", message: "Not found or Blocked" });

    const title = $('h1.entry-title').text().trim();
    const iframe = $('iframe').attr('src') || "";
    
    const prev = $('.prev').attr('href');
    const next = $('.next').attr('href');
    
    const downloads = [];
    $('.download-eps ul, #server ul').each((i, ul) => {
        let format = "Unknown";
        let p = $(ul).prev();
        while(p.length && !['p', 'h4', 'div', 'span'].includes(p.prop('tagName').toLowerCase())) {
            p = p.prev();
        }
        if(p.length) format = p.text().trim();

        if (/MKV/i.test(format)) format = 'MKV';
        else if (/MP4/i.test(format)) format = 'MP4';
        else if (/x265/i.test(format)) format = 'x265';

        const qualities = [];
        $(ul).find('li').each((j, li) => {
            const q = $(li).find('strong, b').text().trim();
            const urls = [];
            $(li).find('a').each((k, a) => urls.push({ title: $(a).text().trim(), url: $(a).attr('href') }));
            qualities.push({ title: q, urls });
        });
        if(qualities.length) downloads.push({ title: format, qualities });
    });

    res.json({
        status: "success", creator: "Sanka Vollerei", message: "",
        data: {
            title, streamUrl: iframe,
            navigation: {
                prev: (prev && !prev.includes('/anime/')) ? `/samehadaku/episode/${extractId(prev)}` : null,
                next: (next && !next.includes('/anime/')) ? `/samehadaku/episode/${extractId(next)}` : null
            },
            downloads
        }
    });
});

// 6. GENRES & BATCH & MOVIES
app.get('/anime/samehadaku/genres', async (req, res) => {
    const $ = await fetchPage(BASE_URL);
    if (!$) return res.status(500).json({ status: "failed" });

    const list = [];
    const seen = new Set();
    $('a[href*="/genre/"]').each((i, el) => {
        const href = $(el).attr('href');
        if (!seen.has(href)) {
            const id = extractId(href);
            if (id) {
                list.push({ title: $(el).text().split('(')[0].trim(), genreId: id, href: `/samehadaku/genres/${id}`, samehadakuUrl: href });
                seen.add(href);
            }
        }
    });
    list.sort((a, b) => a.title.localeCompare(b.title));
    res.json({ status: "success", creator: "Sanka Vollerei", message: "", data: { genreList: list } });
});

app.get('/anime/samehadaku/genres/:id', createListHandler(
    (p, q) => `${BASE_URL}/genre/${req.params.id}/${p > 1 ? `page/${p}/` : ''}`,
    parseLibraryItem
));

app.get('/anime/samehadaku/batch', createListHandler(
    (p) => `${BASE_URL}/daftar-batch/${p > 1 ? `page/${p}/` : ''}`,
    ($, el) => parseLibraryItem($, el, 'Completed')
));

app.get('/anime/samehadaku/movies', createListHandler(
    (p) => `${BASE_URL}/anime-movie/${p > 1 ? `page/${p}/` : ''}`,
    ($, el) => { const i = parseLibraryItem($, el); if(i) i.type = "Movie"; return i; }
));

const PORT = process.env.PORT || 3000;
if (require.main === module) {
    app.listen(PORT, () => console.log(`Server running on port ${PORT}`));
}

module.exports = app;
