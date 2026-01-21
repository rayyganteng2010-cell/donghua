const express = require('express');
const axios = require('axios');
const cheerio = require('cheerio');
const cors = require('cors');

const app = express();
app.use(cors());

const BASE_URL = 'https://v1.samehadaku.how';

const HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Referer': 'https://samehadaku.how/',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
    'Accept-Language': 'en-US,en;q=0.5'
};

// --- HELPERS ---

const extractId = (url) => {
    if (!url) return '';
    // Hapus trailing slash dan ambil segmen terakhir
    const parts = url.replace(/\/$/, '').split('/');
    return parts[parts.length - 1];
};

const extractPoster = ($node) => {
    const img = $node.find('img');
    // Cek atribut lazyload umum
    let src = img.attr('src') || img.attr('data-src') || img.attr('srcset');
    if (!src || src.includes('data:image')) {
        src = img.attr('data-src') || img.attr('src');
    }
    if (!src) return "https://dummyimage.com/300x400/000/fff&text=No+Image";
    return src.split('?')[0]; // Bersihkan query params
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

        // Logic Episode & Date
        let ep = '?';
        let released = '?';
        
        // Ambil full text untuk regex
        const fullText = $(el).text().replace(/\s+/g, ' ');

        // 1. Coba ambil dari elemen spesifik dulu
        const epTag = $(el).find('.episode, .dtla');
        const dateTag = $(el).find('.date, .year');

        if (epTag.length) {
            const rawEp = epTag.text().trim();
            // Regex ambil angka setelah kata Episode atau angka saja
            const mEp = rawEp.match(/(?:Episode\s*)?(\d+)/i);
            if (mEp) ep = mEp[1];
        }

        if (dateTag.length) {
            released = dateTag.text().trim();
        } else {
            // Regex Fallback Date "10 hours yang lalu"
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
    res.json({ message: "Samehadaku API V28 (JS Fixed) is Running" });
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
            // Cari container ID/Class
            let container = content.find(`#${indo}, .${indo}`);
            
            // Fallback cari Header Text
            if (!container.length) {
                content.find('h3, h4, b').each((i, el) => {
                    if ($(el).text().toLowerCase().includes(indo)) {
                        container = $(el).next(); // Coba next sibling
                    }
                });
            }

            if (container && container.length) {
                container.find('.animepost, li').each((i, el) => {
                    // Validasi Link Anime
                    const link = $(el).find('a').attr('href');
                    if (link && link.includes('/anime/')) {
                        const p = parseLibraryItem($, el);
                        if (p) {
                            delete p.status; // Schedule pake estimation
                            let est = "Update";
                            
                            // Cari Jam Tayang
                            const timeTag = $(el).find('.time, .btime');
                            if (timeTag.length) {
                                est = timeTag.text().trim();
                            } else {
                                // Gali tooltip (Javascript Regex)
                                const tt = $(el).find('.ttls, .dtla').text();
                                const m = tt.match(/(?:Pukul|Jam|Time|Rilis)\s*:\s*([\d\:]+)/i);
                                if(m) est = m[1].trim();
                            }
                            p.estimation = est;
                            
                            // Cek duplikat
                            if(!list.find(x => x.title === p.title)) list.push(p);
                        }
                    }
                });
            }
            days.push({ day: eng, animeList: list });
        }
        res.json({ status: "success", creator: "Sanka Vollerei", message: "", data: { days } });
    } catch (e) { res.status(500).json({ status: "failed", message: e.message }); }
});

// 3. LISTS
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
    (p, q) => `${BASE_URL}/${p > 1 ? `page/${p}/` : ''}?s=${q.query || q.s || ''}`,
    ($, el) => parseLibraryItem($, el)
));

// 4. DETAIL ANIME
app.get('/anime/samehadaku/anime/:id', async (req, res) => {
    try {
        const { id } = req.params;
        const { data } = await axios.get(`${BASE_URL}/anime/${id}/`, { headers: HEADERS });
        const $ = cheerio.load(data);

        // Title Clean
        let titleRaw = $('h1.entry-title').text().trim();
        // Hapus kata-kata sampah
        titleRaw = titleRaw.replace(/Nonton Anime|Sub Indo/gi, '').trim();
        // Jika mau title kosong seperti request:
        const title = ""; 

        const poster = extractPoster($('.thumb'));
        
        // Metadata
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

        // Score
        let scoreVal = infos['score'] || '?';
        if (scoreVal === '?') {
            const sc = $('span[itemprop="ratingValue"]').text().trim();
            if (sc) scoreVal = sc;
        }
        
        const ratingCount = $('span[itemprop="ratingCount"]').text().trim();
        const users = ratingCount ? `${ratingCount} users` : 'N/A';

        // Synopsis
        const paragraphs = [];
        $('.desc p, .entry-content p').each((i, el) => {
            if ($(el).text().trim()) paragraphs.push($(el).text().trim());
        });

        // Episodes
        const episodes = [];
        $('.lstepsiode li').each((i, el) => {
            const a = $(el).find('a');
            const href = a.attr('href');
            const epId = extractId(href);
            const rawTitle = $(el).find('.epl-title').text().trim() || a.text().trim();
            
            // Ambil angka episode
            let epNum = rawTitle;
            const mEp = rawTitle.match(/\d+/);
            if (mEp) epNum = parseInt(mEp[0]);

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
            japanese: infos['japanese'] || '-',
            synonyms: infos['synonyms'] || '-',
            english: infos['english'] || '-',
            status: infos['status'] || 'Unknown',
            type: infos['type'] || 'TV',
            source: infos['source'] || '-',
            duration: infos['duration'] || '-',
            episodes: parseInt(infos['total episode']) || null,
            season: infos['season'] || '-',
            studios: infos['studio'] || '-',
            producers: infos['producers'] || '-',
            aired: infos['released'] || '-',
            trailer: $('.trailer-anime iframe').attr('src') || "",
            synopsis: { paragraphs, connections: [] },
            genreList,
            batchList: [],
            episodeList: episodes
        };

        res.json({ status: "success", creator: "Sanka Vollerei", message: "", data: respData, pagination: null });

    } catch (e) { res.status(404).json({ status: "failed", message: "Not found" }); }
});

// 5. EPISODE STREAM & DOWNLOAD
app.get('/anime/samehadaku/episode/:id', async (req, res) => {
    try {
        const { id } = req.params;
        const { data } = await axios.get(`${BASE_URL}/${id}/`, { headers: HEADERS });
        const $ = cheerio.load(data);

        const title = $('h1.entry-title').text().trim();
        const streamUrl = $('iframe').attr('src') || "";
        
        const prevHref = $('.prev').attr('href');
        const nextHref = $('.next').attr('href');
        
        const nav = {
            prev: (prevHref && !prevHref.includes('/anime/')) ? `/samehadaku/episode/${extractId(prevHref)}` : null,
            next: (nextHref && !nextHref.includes('/anime/')) ? `/samehadaku/episode/${extractId(nextHref)}` : null
        };

        const downloads = [];
        const dlBox = $('.download-eps, #server');
        if (dlBox.length) {
            dlBox.find('ul').each((i, ul) => {
                // Find Header (MP4/MKV)
                let format = "Unknown";
                let prev = $(ul).prev();
                // Loop mundur sampai ketemu header text
                while(prev.length && !['p', 'h4', 'div', 'span'].includes(prev.prop('tagName').toLowerCase())) {
                    prev = prev.prev();
                }
                if (prev.length) format = prev.text().trim();

                // Normalisasi nama format
                if (/MKV/i.test(format)) format = 'MKV';
                else if (/MP4/i.test(format)) format = 'MP4';
                else if (/x265/i.test(format)) format = 'x265';

                const qualities = [];
                $(ul).find('li').each((j, li) => {
                    const qName = $(li).find('strong, b').text().trim();
                    const urls = [];
                    $(li).find('a').each((k, a) => {
                        urls.push({ title: $(a).text().trim(), url: $(a).attr('href') });
                    });
                    qualities.push({ title: qName, urls });
                });
                if (qualities.length) downloads.push({ title: format, qualities });
            });
        }

        res.json({
            status: "success", creator: "Sanka Vollerei", message: "",
            data: { title, streamUrl, navigation: nav, downloads }
        });
    } catch (e) { res.status(404).json({ status: "failed" }); }
});

// 6. GENRES & BATCH & MOVIES (Standard Lists)
const standardListHandler = (urlFn) => createListHandler(urlFn, parseLibraryItem);

app.get('/anime/samehadaku/genres', async (req, res) => {
    try {
        const { data } = await axios.get(BASE_URL, { headers: HEADERS });
        const $ = cheerio.load(data);
        const list = [];
        const seen = new Set();
        $('a[href*="/genre/"]').each((i, el) => {
            const href = $(el).attr('href');
            if (!seen.has(href)) {
                list.push({ title: $(el).text().split('(')[0].trim(), genreId: extractId(href), href: `/samehadaku/genres/${extractId(href)}`, samehadakuUrl: href });
                seen.add(href);
            }
        });
        list.sort((a, b) => a.title.localeCompare(b.title));
        res.json({ status: "success", creator: "Sanka Vollerei", message: "", data: { genreList: list } });
    } catch(e) { res.status(500).json({ status: "failed" }); }
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

// START SERVER
const PORT = process.env.PORT || 3000;
if (require.main === module) {
    app.listen(PORT, () => console.log(`Server running on port ${PORT}`));
}

module.exports = app;
