const express = require('express');
const axios = require('axios');
const cheerio = require('cheerio');
const cors = require('cors');

const app = express();
app.use(cors());

// --- BASE CANDIDATES (fallback) ---
const BASES = [
  'https://v1.samehadaku.how',
  'https://samehadaku.how',
  'https://www.samehadaku.how',
];

// --- HEADERS ---
const HEADERS = {
  'User-Agent':
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
  'Accept':
    'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
  'Accept-Language': 'id-ID,id;q=0.9,en-US;q=0.8,en;q=0.7',
  'Accept-Encoding': 'gzip, deflate, br',
  'Connection': 'keep-alive',
  'Upgrade-Insecure-Requests': '1',
};

const client = axios.create({
  timeout: 15000,
  maxRedirects: 5,
  headers: HEADERS,
  validateStatus: (s) => s < 500,
});

// --- HELPERS ---

const joinUrl = (base, pathOrUrl) => {
  if (!pathOrUrl) return base;
  if (/^https?:\/\//i.test(pathOrUrl)) return pathOrUrl;
  if (!pathOrUrl.startsWith('/')) return `${base}/${pathOrUrl}`;
  return `${base}${pathOrUrl}`;
};

const isBlocked = (status, html) => {
  if (status === 403) return true;
  const t = (html || '').toLowerCase();
  if (t.includes('cloudflare') && t.includes('attention required')) return true;
  if (t.includes('access denied')) return true;
  if (t.includes('forbidden')) return true;
  return false;
};

const fetchHtmlAnyBase = async (pathOrUrl) => {
  let lastErr = null;

  const tryList = /^https?:\/\//i.test(pathOrUrl)
    ? [pathOrUrl]
    : BASES.map((b) => joinUrl(b, pathOrUrl));

  for (const url of tryList) {
    try {
      const r = await client.get(url, {
        headers: {
          ...HEADERS,
          Referer: url,
        },
      });

      const html = typeof r.data === 'string' ? r.data : '';

      if (r.status === 200 && !isBlocked(r.status, html)) {
        return { ok: true, url, status: r.status, html };
      }

      lastErr = new Error(`Blocked/failed: ${r.status} @ ${url}`);
    } catch (e) {
      lastErr = e;
    }
  }

  return { ok: false, url: null, status: null, html: null, error: lastErr };
};

const fetchPage = async (pathOrUrl) => {
  const out = await fetchHtmlAnyBase(pathOrUrl);
  if (!out.ok) return null;
  return cheerio.load(out.html);
};

const extractId = (url) => {
  if (!url) return '';
  const parts = url.replace(/\/$/, '').split('/');
  return parts[parts.length - 1];
};

const extractPoster = ($node) => {
  const img = $node.find('img').first();
  let src =
    img.attr('data-src') ||
    img.attr('data-lazy-src') ||
    img.attr('src') ||
    img.attr('srcset');

  if (src && src.includes(' ')) {
    // kalau srcset, ambil yang pertama
    src = src.split(' ')[0];
  }

  if (!src || src.includes('data:image')) {
    src = img.attr('data-src') || img.attr('src');
  }

  if (!src) return 'https://dummyimage.com/300x400/000/fff&text=No+Image';
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
        title,
        genreId: id,
        href: `/anime/samehadaku/genres/${id}`,
        samehadakuUrl: href,
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
      const num = parseInt(txt, 10);
      if (num > totalPages) totalPages = num;
    }
  });

  const hasNext = $pagination.find('.next').length > 0;
  const hasPrev = $pagination.find('.prev').length > 0;
  const curr = parseInt(currentPage, 10);

  return {
    currentPage: curr,
    hasPrevPage: hasPrev,
    prevPage: hasPrev ? curr - 1 : null,
    hasNextPage: hasNext,
    nextPage: hasNext ? curr + 1 : null,
    totalPages,
  };
};

// --- PARSERS ---

const parseLatestItem = ($, el) => {
  try {
    const $el = $(el);
    const aTag = $el.find('a').first();
    if (!aTag.length) return null;

    const href = aTag.attr('href');
    const id = extractId(href);

    let title =
      $el.find('.title').text().trim() ||
      aTag.attr('title') ||
      aTag.text().trim() ||
      'Unknown';

    const poster = extractPoster($el);

    let ep = '?';
    let released = '?';

    const epTag = $el.find('.episode, .eps, .dtla').first();
    const dateTag = $el.find('.date, .year, time').first();

    if (epTag.length) {
      const rawEp = epTag.text().trim();
      const mEp = rawEp.match(/(?:Episode\s*)?(\d+)/i);
      if (mEp) ep = mEp[1];
    } else {
      const mEp = $el.text().match(/Episode\s*(\d+)/i);
      if (mEp) ep = mEp[1];
    }

    if (dateTag.length) {
      released = dateTag.text().trim();
    } else {
      const fullText = $el.text().replace(/\s+/g, ' ');
      const mDate = fullText.match(/(\d+\s+\w+\s+yang lalu)/i);
      if (mDate) released = mDate[1];
    }

    return {
      title,
      poster,
      episodes: ep,
      releasedOn: released,
      animeId: id,
      href: `/anime/samehadaku/anime/${id}`,
      samehadakuUrl: href,
    };
  } catch (e) {
    return null;
  }
};

const parseLibraryItem = ($, el, statusForce = 'Ongoing') => {
  try {
    const $el = $(el);
    const aTag = $el.find('a').first();
    if (!aTag.length) return null;

    const href = aTag.attr('href');
    const id = extractId(href);

    const title =
      $el.find('.title').text().trim() ||
      aTag.attr('title') ||
      aTag.text().trim() ||
      'Unknown';

    const poster = extractPoster($el);
    const score = $el.find('.score').text().trim() || '?';
    const type = $el.find('.type').text().trim() || 'TV';

    return {
      title,
      poster,
      type,
      score,
      status: statusForce,
      animeId: id,
      href: `/anime/samehadaku/anime/${id}`,
      samehadakuUrl: href,
      genreList: parseGenreList($, $el),
    };
  } catch (e) {
    return null;
  }
};

// --- ROUTES ---

app.get('/', (req, res) => {
  res.json({ message: 'Samehadaku API (fixed) is Running' });
});

// Wrapper untuk request
const fetchPageStrict = async (pathOrUrl) => {
  const out = await fetchHtmlAnyBase(pathOrUrl);
  if (!out.ok) {
    return { $: null, meta: { ok: false, reason: out?.error?.message || 'failed' } };
  }
  return { $: cheerio.load(out.html), meta: { ok: true, url: out.url, status: out.status } };
};

// 1) HOME
app.get('/anime/samehadaku/home', async (req, res) => {
  const { $, meta } = await fetchPageStrict('/');
  if (!$) {
    return res.status(502).json({
      status: 'failed',
      message: `Upstream blocked/failed: ${meta.reason}`,
    });
  }

  const recent = [];
  $('.post-show li, .animepost')
    .slice(0, 10)
    .each((i, el) => {
      const item = parseLatestItem($, el);
      if (item) recent.push(item);
    });

  const top10 = [];
  $('.widget_senction.popular .serieslist li, .serieslist.pop li').each((i, el) => {
    const p = parseLibraryItem($, el);
    if (p) {
      top10.push({
        rank: i + 1,
        title: p.title,
        poster: p.poster,
        score: p.score,
        animeId: p.animeId,
        href: p.href,
        samehadakuUrl: p.samehadakuUrl,
      });
    }
  });

  res.json({
    status: 'success',
    creator: 'Sanka Vollerei',
    message: '',
    data: {
      recent: {
        href: '/anime/samehadaku/latest',
        samehadakuUrl: 'auto',
        animeList: recent,
      },
      top10: {
        href: '/anime/samehadaku/popular',
        samehadakuUrl: 'auto',
        animeList: top10,
      },
      batch: { href: '/anime/samehadaku/batch', samehadakuUrl: 'auto', batchList: [] },
      movie: { href: '/anime/samehadaku/movies', samehadakuUrl: 'auto', animeList: [] },
    },
  });
});

// 2) SCHEDULE (FIXED)
app.get('/anime/samehadaku/schedule', async (req, res) => {
  const { $, meta } = await fetchPageStrict('/jadwal-rilis/');
  if (!$) {
    return res.status(502).json({
      status: 'failed',
      message: `Upstream blocked/failed: ${meta.reason}`,
    });
  }

  const dayKeys = [
    { eng: 'Monday', indo: ['senin', 'monday'] },
    { eng: 'Tuesday', indo: ['selasa', 'tuesday'] },
    { eng: 'Wednesday', indo: ['rabu', 'wednesday'] },
    { eng: 'Thursday', indo: ['kamis', 'thursday'] },
    { eng: 'Friday', indo: ['jumat', "jum'at", 'friday'] },
    { eng: 'Saturday', indo: ['sabtu', 'saturday'] },
    { eng: 'Sunday', indo: ['minggu', 'sunday'] },
  ];

  const toDayEng = (txt) => {
    const t = (txt || '').toLowerCase().trim();
    for (const d of dayKeys) {
      if (d.indo.some((k) => t.includes(k))) return d.eng;
    }
    return null;
  };

  const content = $('.entry-content').first().length ? $('.entry-content').first() : $('main').first();

  const map = {};
  dayKeys.forEach((d) => (map[d.eng] = []));

  let currentDay = null;

  const pushAnimeFromNode = ($node) => {
    const a = $node.find('a[href*="/anime/"]').first();
    const href = a.attr('href');
    if (!href || !currentDay) return;

    const item = parseLibraryItem($, $node, '');
    if (!item) return;

    // estimation jam
    let est = $node.find('.time, .btime').first().text().trim();
    if (!est) {
      const raw = $node.text().replace(/\s+/g, ' ');
      const m = raw.match(/(?:pukul|jam|time|rilis)\s*[:\-]?\s*([0-2]?\d[:.][0-5]\d)/i);
      if (m) est = m[1].replace('.', ':');
    }
    item.estimation = est || 'Update';

    if (!map[currentDay].some((x) => x.animeId === item.animeId)) {
      map[currentDay].push(item);
    }
  };

  const children = content.children().toArray();

  for (const el of children) {
    const $el = $(el);
    const tag = (el.tagName || '').toLowerCase();
    const text = $el.text().trim();

    if (['h2', 'h3', 'h4', 'strong', 'b'].includes(tag)) {
      const day = toDayEng(text);
      if (day) currentDay = day;
      continue;
    }

    if (!currentDay) continue;

    if ($el.is('ul') || $el.is('ol')) {
      $el.find('li').each((i, li) => pushAnimeFromNode($(li)));
      continue;
    }

    if ($el.find('li').length) {
      $el.find('li').each((i, li) => pushAnimeFromNode($(li)));
      continue;
    }

    if ($el.hasClass('animepost') || $el.find('.animepost').length) {
      ($el.hasClass('animepost') ? $el : $el.find('.animepost')).each((i, node) =>
        pushAnimeFromNode($(node))
      );
      continue;
    }
  }

  const days = dayKeys.map((d) => ({ day: d.eng, animeList: map[d.eng] }));

  res.json({ status: 'success', creator: 'Sanka Vollerei', message: '', data: { days } });
});

// 3) LISTS
const createListHandler = (urlFn, parserFn, selector = '.post-show li, .animepost') => {
  return async (req, res) => {
    const page = parseInt(req.query.page || '1', 10);
    const url = urlFn(page, req.query);

    const { $, meta } = await fetchPageStrict(url);
    if (!$) {
      return res.status(502).json({
        status: 'failed',
        message: `Upstream blocked/failed: ${meta.reason}`,
      });
    }

    const animeList = [];
    $(selector).each((i, el) => {
      const item = parserFn($, el);
      if (item) animeList.push(item);
    });

    res.json({
      status: 'success',
      creator: 'Sanka Vollerei',
      message: '',
      data: { animeList },
      pagination: getPagination($, page),
    });
  };
};

app.get(
  '/anime/samehadaku/latest',
  createListHandler((p) => (p > 1 ? `/anime-terbaru/page/${p}/` : `/anime-terbaru/`), parseLatestItem)
);

app.get(
  '/anime/samehadaku/ongoing',
  createListHandler(
    (p) => `/daftar-anime-2/${p > 1 ? `page/${p}/` : ''}?status=Currently+Airing&order=update`,
    ($, el) => parseLibraryItem($, el, 'Ongoing')
  )
);

app.get(
  '/anime/samehadaku/completed',
  createListHandler(
    (p) => `/daftar-anime-2/${p > 1 ? `page/${p}/` : ''}?status=Finished+Airing&order=latest`,
    ($, el) => parseLibraryItem($, el, 'Completed')
  )
);

app.get(
  '/anime/samehadaku/popular',
  createListHandler(
    (p) => `/daftar-anime-2/${p > 1 ? `page/${p}/` : ''}?order=popular`,
    ($, el) => parseLibraryItem($, el, 'Popular')
  )
);

app.get(
  '/anime/samehadaku/search',
  createListHandler(
    (p, q) => `/${p > 1 ? `page/${p}/` : ''}?s=${encodeURIComponent(q.query || q.s || '')}`,
    ($, el) => parseLibraryItem($, el, 'Search')
  )
);

// 4) DETAIL ANIME
app.get('/anime/samehadaku/anime/:id', async (req, res) => {
  const { $, meta } = await fetchPageStrict(`/anime/${req.params.id}/`);
  if (!$) {
    return res.status(502).json({
      status: 'failed',
      message: `Upstream blocked/failed: ${meta.reason}`,
    });
  }

  const titleRaw = $('h1.entry-title').text().trim();
  const title = titleRaw || '';

  const poster =
    extractPoster($('.thumb').first().length ? $('.thumb').first() : $('article').first());

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
    const t = $(el).text().trim();
    if (t) paragraphs.push(t);
  });

  const episodes = [];
  $('.lstepsiode li').each((i, el) => {
    const a = $(el).find('a').first();
    const href = a.attr('href');
    if (!href) return;

    const epId = extractId(href);
    const rawTitle = $(el).find('.epl-title').text().trim() || a.text().trim();

    let epNum = rawTitle;
    const m = rawTitle.match(/\d+/);
    if (m) epNum = parseInt(m[0], 10);

    episodes.push({
      title: epNum,
      episodeId: epId,
      href: `/anime/samehadaku/episode/${epId}`,
      samehadakuUrl: href,
    });
  });

  const genreList = parseGenreList($, $('.genre-info').first().length ? $('.genre-info') : $('body'));

  res.json({
    status: 'success',
    creator: 'Sanka Vollerei',
    message: '',
    data: {
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
      episodes: parseInt(infos['total episode'] || infos['episodes'] || '', 10) || null,
      season: infos['season'] || '-',
      studios: infos['studio'] || '-',
      producers: infos['producers'] || '-',
      aired: infos['released'] || infos['aired'] || '-',
      trailer: $('.trailer-anime iframe').attr('src') || '',
      synopsis: { paragraphs, connections: [] },
      genreList,
      batchList: [],
      episodeList: episodes,
    },
    pagination: null,
  });
});

// 5) EPISODE
app.get('/anime/samehadaku/episode/:id', async (req, res) => {
  const { $, meta } = await fetchPageStrict(`/${req.params.id}/`);
  if (!$) {
    return res.status(502).json({
      status: 'failed',
      message: `Upstream blocked/failed: ${meta.reason}`,
    });
  }

  const title = $('h1.entry-title').text().trim();

  // pilih iframe pertama yang masuk akal
  const iframe =
    $('iframe').first().attr('src') ||
    $('iframe[data-src]').first().attr('data-src') ||
    '';

  const prev = $('.prev').attr('href');
  const next = $('.next').attr('href');

  const downloads = [];

  const pushDownloadBlock = (ul) => {
    let format = 'Unknown';
    let p = $(ul).prev();
    if (p && p.length) format = p.text().trim();

    if (/MKV/i.test(format)) format = 'MKV';
    else if (/MP4/i.test(format)) format = 'MP4';
    else if (/x265/i.test(format)) format = 'x265';

    const qualities = [];
    $(ul)
      .find('li')
      .each((j, li) => {
        const q = $(li).find('strong, b').first().text().trim() || 'Unknown';
        const urls = [];
        $(li)
          .find('a')
          .each((k, a) => {
            const u = $(a).attr('href');
            if (!u) return;
            urls.push({ title: $(a).text().trim(), url: u });
          });
        if (urls.length) qualities.push({ title: q, urls });
      });

    if (qualities.length) downloads.push({ title: format, qualities });
  };

  $('.download-eps ul').each((i, ul) => pushDownloadBlock(ul));
  $('#server ul').each((i, ul) => pushDownloadBlock(ul));

  res.json({
    status: 'success',
    creator: 'Sanka Vollerei',
    message: '',
    data: {
      title,
      streamUrl: iframe,
      navigation: {
        prev: prev && !prev.includes('/anime/') ? `/anime/samehadaku/episode/${extractId(prev)}` : null,
        next: next && !next.includes('/anime/') ? `/anime/samehadaku/episode/${extractId(next)}` : null,
      },
      downloads,
    },
  });
});

// 6) GENRES (list)
app.get('/anime/samehadaku/genres', async (req, res) => {
  const { $, meta } = await fetchPageStrict('/');
  if (!$) {
    return res.status(502).json({
      status: 'failed',
      message: `Upstream blocked/failed: ${meta.reason}`,
    });
  }

  const list = [];
  const seen = new Set();

  $('a[href*="/genre/"]').each((i, el) => {
    const href = $(el).attr('href');
    if (!href || seen.has(href)) return;
    const id = extractId(href);
    if (!id) return;

    list.push({
      title: $(el).text().split('(')[0].trim(),
      genreId: id,
      href: `/anime/samehadaku/genres/${id}`,
      samehadakuUrl: href,
    });
    seen.add(href);
  });

  list.sort((a, b) => a.title.localeCompare(b.title));

  res.json({ status: 'success', creator: 'Sanka Vollerei', message: '', data: { genreList: list } });
});

// 6b) GENRE DETAIL (FIXED, no req scope bug)
app.get('/anime/samehadaku/genres/:id', async (req, res) => {
  const page = parseInt(req.query.page || '1', 10);
  const url = `/genre/${req.params.id}/${page > 1 ? `page/${page}/` : ''}`;

  const { $, meta } = await fetchPageStrict(url);
  if (!$) {
    return res.status(502).json({
      status: 'failed',
      message: `Upstream blocked/failed: ${meta.reason}`,
    });
  }

  const animeList = [];
  $('.post-show li, .animepost').each((i, el) => {
    const item = parseLibraryItem($, el, 'Genre');
    if (item) animeList.push(item);
  });

  res.json({
    status: 'success',
    creator: 'Sanka Vollerei',
    message: '',
    data: { animeList },
    pagination: getPagination($, page),
  });
});

// 7) BATCH + MOVIES
app.get(
  '/anime/samehadaku/batch',
  createListHandler(
    (p) => `/daftar-batch/${p > 1 ? `page/${p}/` : ''}`,
    ($, el) => parseLibraryItem($, el, 'Batch')
  )
);

app.get(
  '/anime/samehadaku/movies',
  createListHandler(
    (p) => `/anime-movie/${p > 1 ? `page/${p}/` : ''}`,
    ($, el) => {
      const i = parseLibraryItem($, el, 'Movie');
      if (i) i.type = 'Movie';
      return i;
    }
  )
);

const PORT = process.env.PORT || 3000;
if (require.main === module) {
  app.listen(PORT, () => console.log(`Server running on port ${PORT}`));
}

module.exports = app;
