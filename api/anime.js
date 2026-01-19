const express = require('express');
const router = express.Router();
const axios = require('axios');
const cheerio = require('cheerio');

router.get('/:slug', async (req, res) => {
  try {
    const { slug } = req.params;
    const url = `https://donghuafilm.com/anime/${slug}/`;
    
    console.log(`🎭 Fetching anime: ${url}`);
    
    const response = await axios.get(url, {
      headers: {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
      },
      timeout: 15000
    });
    
    const $ = cheerio.load(response.data);
    
    // Extract basic info
    const title = $('h1.entry-title').text().trim();
    const thumbnail = $('.thumb img, .poster img, img[itemprop="image"]').attr('src');
    
    // Extract episodes
    const episodes = [];
    $('.eplister li, .episode-list li').each((i, el) => {
      const $el = $(el);
      const epUrl = $el.find('a').attr('href');
      const epTitle = $el.find('.epl-title, .title').text().trim();
      const epNum = $el.find('.epl-num, .num').text().trim();
      
      if (epUrl) {
        episodes.push({
          id: epUrl.split('/').filter(Boolean).pop(),
          url: epUrl,
          title: epTitle,
          number: epNum || `Episode ${i + 1}`,
          episode: i + 1
        });
      }
    });
    
    res.json({
      success: true,
      anime: {
        slug,
        title,
        thumbnail,
        totalEpisodes: episodes.length
      },
      episodes: episodes.reverse(), // Latest first
      totalEpisodes: episodes.length,
      scrapedAt: new Date().toISOString()
    });
    
  } catch (error) {
    console.error('Anime fetch error:', error.message);
    res.status(500).json({
      success: false,
      error: error.message,
      message: 'Failed to fetch anime details'
    });
  }
});

module.exports = router;
