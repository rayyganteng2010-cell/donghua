const express = require('express');
const router = express.Router();
const axios = require('axios');
const cheerio = require('cheerio');

router.get('/', async (req, res) => {
  try {
    const page = req.query.page || 1;
    const url = page > 1 
      ? `https://donghuafilm.com/page/${page}/` 
      : 'https://donghuafilm.com/';
    
    console.log(`Scraping: ${url}`);
    
    const response = await axios.get(url, {
      headers: {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
      },
      timeout: 10000
    });
    
    const $ = cheerio.load(response.data);
    const donghuaList = [];
    
    // Simple scraping logic
    $('article').each((index, element) => {
      const $el = $(element);
      
      const title = $el.find('h2 a').text().trim();
      const url = $el.find('h2 a').attr('href');
      const thumbnail = $el.find('img').attr('src');
      
      if (title && url) {
        donghuaList.push({
          id: index + 1,
          title,
          url,
          thumbnail,
          index
        });
      }
    });
    
    res.json({
      success: true,
      data: donghuaList,
      total: donghuaList.length,
      page: parseInt(page),
      scrapedAt: new Date().toISOString()
    });
    
  } catch (error) {
    console.error('Home scraping error:', error.message);
    res.status(500).json({
      success: false,
      error: error.message,
      message: 'Failed to scrape homepage'
    });
  }
});

module.exports = router;
