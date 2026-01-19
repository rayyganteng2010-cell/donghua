const express = require('express');
const router = express.Router();
const axios = require('axios');
const cheerio = require('cheerio');

router.get('/', async (req, res) => {
  try {
    const query = req.query.q;
    if (!query) {
      return res.status(400).json({
        success: false,
        error: 'Query parameter "q" is required'
      });
    }
    
    const url = `https://donghuafilm.com/?s=${encodeURIComponent(query)}`;
    console.log(`Searching: ${url}`);
    
    const response = await axios.get(url, {
      headers: {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
      },
      timeout: 10000
    });
    
    const $ = cheerio.load(response.data);
    const results = [];
    
    $('article').each((index, element) => {
      const $el = $(element);
      const title = $el.find('h2 a').text().trim();
      const url = $el.find('h2 a').attr('href');
      
      if (title && url) {
        results.push({
          id: index + 1,
          title,
          url
        });
      }
    });
    
    res.json({
      success: true,
      query,
      results,
      total: results.length,
      scrapedAt: new Date().toISOString()
    });
    
  } catch (error) {
    console.error('Search error:', error.message);
    res.status(500).json({
      success: false,
      error: error.message,
      message: 'Search failed'
    });
  }
});

module.exports = router;
