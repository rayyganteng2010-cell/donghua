const express = require('express');
const axios = require('axios');
const cheerio = require('cheerio');
const cors = require('cors');

const app = express();
app.use(cors());

const BASE_URL = 'https://v1.samehadaku.how';

// Headers lengkap biar dikira browser beneran
const HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Referer': 'https://samehadaku.how/',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
    'Accept-Language': 'en-US,en;q=0.9,id;q=0.8'
};

// --- HELPERS ---

const extractId = (url) => {
    if (!url) return '';
    const parts = url.replace(/\/$/, '').split('/');
    return parts[parts.length - 1];
};

const extractPoster = ($node) => {
    const img = $node.find('img');
    let src = img.attr('src') || img.attr('data-src') || img.attr('srcset');
    if (!src) return "https://dummyimage.com/300x400/000/fff&text=No+Image";
    return src.split('?')[0];
};

const parseGenreList = ($, $node) => {
    const genres = [];
    const links = $node.find('.genres a, .genre-info a, .genre a, div.bean a');
    links.each((i, el) => {
        const href = $(el).attr('href');
        genres.push({
            title: $(el).text().trim(),
            genreId: extractId(href),
            href: `/samehadaku/genres/${extractId(href)}`,
            samehadakuUrl: href
        });
    });
    return genres;
};

const getPagination = ($, currentPage) => {
    const $pagination = $('.pagination');
    if (!$pagination.length) return null;

    let totalPages = 1;
    const pageNumbers = $pagination.find('.page-numbers');
    
    pageNumbers.each((i, el) => {
        const txt = $(el).text().replace(/,/g, '');
        const num = parseInt(txt);
        if (!isNaN(num) && num > totalPages) {
            totalPages = num;
        }
    });

    const hasNext = $pagination.find('.next').length > 0;
    const hasPrev = $pagination.find('.prev').length > 0;

    return {
        currentPage: parseInt(currentPage),
        hasPrevPage: hasPrev,
        prevPage: hasPrev ? parseInt(currentPage) - 1 : null,
        hasNextPage: hasNext,
        nextPage: hasNext ? parseInt(currentPage) + 1 : null,
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
        const title = $(el).find('.title').text().trim() || aTag.attr('title') || "Unknown";
        const poster = extractPoster($(el));

        // Fix Episode & Date (Regex Clean)
        let ep = '?';
        let released = '?';
        
        // Ambil full text node, pisahkan dengan |
        // Contoh raw: "One Piece Episode 123 Released on: 1 hour ago"
        const fullText = $(el).text().replace(/\s\s+/g, ' '); 

        // Regex Episode
        const epMatch = fullText.match(/(?:Episode\s?|Ep\s?)(\d+)/i);
        if (epMatch) ep = epMatch[1];

        // Regex Date
        if (fullText.includes("Released on:")) {
            const parts = fullText.split("Released on:");
            if (parts[1]) released = parts[1].trim().split("Posted")[0].trim();
        } else if (fullText.includes("yang lalu")) {
            const dateMatch = fullText.match(/(\d+\s+\w+\s+yang lalu)/);
            if (dateMatch) released = dateMatch[1];
        } else {
            const dateTag = $(el).find('.date, .year');
            if (dateTag.length) released = dateTag.text().trim();
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
    res.json({ 
        status: "Online", 
        message: "Samehadaku API is Running", 
        routes: [
            "/anime/samehadaku/home",
            "/anime/samehadaku/schedule",
            "/anime/samehadaku/latest",
            "/anime/samehadaku/ongoing",
            "/anime/samehadaku/completed",
            "/anime/samehadaku/search?query=naruto",
            "/anime/samehadaku/genres"
        ]
    });
});

// 1. HOME
app.get('/anime/samehadaku/home', async (req, res) => {
    try {
        const { data } = await axios.get(BASE_URL, { headers: HEADERS });
        const $ = cheerio.load(data);
        
        const recent = [];
        const nodes = $('.post-show li, .animepost').slice(0, 10);
        nodes.each((i, el) => {
            const item = parseLatestItem($, el);
            if (item) recent.push(item);
        });

        const top10 = [];
        $('.widget_senction.popular .serieslist li, .serieslist.pop li').each((i, el) => {
            const p = parseLibraryItem($, el);
            if (p) top10.push({ rank: i+1, ...p });
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
    } catch (e) { res.status(500).json({ status: "failed", message: e.message }); }
});

// 2. SCHEDULE
app.get('/anime/samehadaku/schedule', async (req, res) => {
    try {
        const { data } = await axios.get(`${BASE_URL}/jadwal-rilis/`, { headers: HEADERS });
        const $ = cheerio.load(data);
        
        const dayMap = [
            {eng:"Monday", indo:"senin"}, {eng:"Tuesday", indo:"selasa"}, {eng:"Wednesday", indo:"rabu"},
            {eng:"Thursday", indo:"kamis"}, {eng:"Friday", indo:"jumat"}, {eng:"Saturday", indo:"sabtu"}, {eng:"Sunday", indo:"minggu"}
        ];

        const days = [];
        const content = $('.entry-content, main').first();

        for (const {eng, indo} of dayMap) {
            let list = [];
            // Cari container dengan ID atau Class hari
            let container = content.find(`#${indo}, .${indo}`);
            
            // Fallback: Cari header text
            if (!container.length) {
                content.find('h3, h4, b').each((i, el) => {
                    if ($(el).text().toLowerCase().includes(indo)) {
                        let next = $(el).next();
                        for(let k=0; k<3; k++) {
                            if(next.find('.animepost, li a').length) { container = next; break; }
                            next = next.next();
                        }
                    }
                });
            }

            if (container.length) {
                container.find('.animepost, li').each((i, el) => {
                    const p = parseLibraryItem($, el);
                    if (p && p.samehadakuUrl.includes('/anime/')) {
                        delete p.status;
                        
                        // Estimation
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
                });
            }
            days.push({ day: eng, animeList: list });
        }
        res.json({ status: "success", creator: "Sanka Vollerei", message: "", data: { days }, pagination: null });
    } catch (e) { res.status(500).json({ status: "failed", message: e.message }); }
});

// 3. LISTS (Latest, Ongoing, Completed, Search)
const createListHandler = (urlFn, parserFn) => async (req, res) => {
    try {
        const page = req.query.page || 1;
        const url = urlFn(page, req.query);
        const { data } = await axios.get(url, { headers: HEADERS });
        const $ = cheerio.load(data);
        
        const animeList = [];
        $('.post-show li, .animepost').each((i, el) => {
            const item = parserFn($, el);
            if (item) animeList.push(item);
        });

        res.json({ status: "success", creator: "Sanka Vollerei", message: "", data: { animeList }, pagination: getPagination($, page) });
    } catch (e) { res.status(500).json({ status: "failed", message: e.message }); }
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
    (p, q) => `${BASE_URL}/${p > 1 ? `page/${p}/` : ''}?s=${q.query || q.s}`,
    ($, el) => parseLibraryItem($, el)
));

// 4. GENRES
app.get('/anime/samehadaku/genres', async (req, res) => {
    try {
        const { data } = await axios.get(BASE_URL, { headers: HEADERS });
        const $ = cheerio.load(data);
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
    } catch (e) { res.status(500).json({ status: "failed" }); }
});

app.get('/anime/samehadaku/genres/:id', createListHandler(
    (p, q) => `${BASE_URL}/genre/${req.params.id}/${p > 1 ? `page/${p}/` : ''}`, // Note: this needs req context fix, creating specific handler below
    ($, el) => parseLibraryItem($, el)
));
// Fix Genre ID Route
app.get('/anime/samehadaku/genres/:id', async (req, res) => {
    try {
        const page = req.query.page || 1;
        const url = `${BASE_URL}/genre/${req.params.id}/${page > 1 ? `page/${page}/` : ''}`;
        const { data } = await axios.get(url, { headers: HEADERS });
        const $ = cheerio.load(data);
        const animeList = [];
        $('.animepost').each((i, el) => {
            const item = parseLibraryItem($, el);
            if(item) animeList.push(item);
        });
        res.json({ status: "success", creator: "Sanka Vollerei", message: "", data: { animeList }, pagination: getPagination($, page) });
    } catch(e) { res.status(500).json({ status: "failed" }); }
});

// 5. DETAIL & EPISODE
app.get('/anime/samehadaku/anime/:id', async (req, res) => {
    try {
        const { data } = await axios.get(`${BASE_URL}/anime/${req.params.id}/`, { headers: HEADERS });
        const $ = cheerio.load(data);

        let title = $('h1.entry-title').text().trim().replace(/Nonton Anime|Sub Indo/gi, '').trim();
        const poster = extractPoster($('.thumb'));
        
        const infos = {};
        $('.infox .spe span').each((i, el) => {
            const txt = $(el).text();
            const p = txt.split(':');
            if(p.length > 1) infos[p[0].trim().toLowerCase()] = p.slice(1).join(':').trim();
        });

        const scoreVal = infos['score'] || $('.ratingValue').text().trim() || '?';
        const users = $('span[itemprop="ratingCount"]').text().trim() ? `${$('span[itemprop="ratingCount"]').text().trim()} users` : 'N/A';

        const paragraphs = [];
        $('.desc p, .entry-content p').each((i, el) => { if($(el).text().trim()) paragraphs.push($(el).text().trim()); });

        const episodes = [];
        $('.lstepsiode li').each((i, el) => {
            const a = $(el).find('a');
            const href = a.attr('href');
            const epId = extractId(href);
            const titleRaw = $(el).find('.epl-title').text().trim() || a.text().trim();
            const epNumMatch = titleRaw.match(/\d+/);
            const epNum = epNumMatch ? parseInt(epNumMatch[0]) : titleRaw;
            episodes.push({ title: epNum, episodeId: epId, href: `/samehadaku/episode/${epId}`, samehadakuUrl: href });
        });

        res.json({
            status: "success", creator: "Sanka Vollerei", message: "",
            data: {
                title: "", // Kosong sesuai request
                poster,
                score: { value: scoreVal, users },
                japanese: infos['japanese'] || '-', synonyms: infos['synonyms'] || '-', english: infos['english'] || '-',
                status: infos['status'] || 'Unknown', type: infos['type'] || 'TV', source: infos['source'] || '-',
                duration: infos['duration'] || '-', episodes: parseInt(infos['total episode']) || null,
                season: infos['season'] || '-', studios: infos['studio'] || '-', producers: infos['producers'] || '-',
                aired: infos['released'] || '-', trailer: $('.trailer-anime iframe').attr('src') || "",
                synopsis: { paragraphs, connections: [] },
                genreList: parseGenreList($, $('.genre-info')),
                batchList: [], episodeList: episodes
            },
            pagination: null
        });
    } catch (e) { res.status(404).json({ status: "failed", message: "Not found" }); }
});

app.get('/anime/samehadaku/episode/:id', async (req, res) => {
    try {
        const { data } = await axios.get(`${BASE_URL}/${req.params.id}/`, { headers: HEADERS });
        const $ = cheerio.load(data);
        const title = $('h1.entry-title').text().trim();
        const prev = $('.prev').attr('href');
        const next = $('.next').attr('href');
        
        const downloads = [];
        $('.download-eps ul, #server ul').each((i, ul) => {
            let format = "Unknown";
            let p = $(ul).prev();
            while(p.length && !p.is('p, h4, div, span')) p = p.prev();
            if(p.length) format = p.text().trim().replace(/MKV|MP4|x265/g, m => m).split(' ')[0]; // Simple format guess
            
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
                title, streamUrl: $('iframe').attr('src') || "",
                navigation: {
                    prev: (prev && !prev.includes('/anime/')) ? `/samehadaku/episode/${extractId(prev)}` : null,
                    next: (next && !next.includes('/anime/')) ? `/samehadaku/episode/${extractId(next)}` : null
                },
                downloads
            }
        });
    } catch (e) { res.status(404).json({ status: "failed" }); }
});

// --- PENTING: START SERVER (SUPPORT LOCAL & VERCEL) ---
// Ini yang bikin bisa jalan di localhost:3000
const PORT = process.env.PORT || 3000;
if (require.main === module) {
    app.listen(PORT, () => {
        console.log(`Server running on http://localhost:${PORT}`);
    });
}

module.exports = app;
