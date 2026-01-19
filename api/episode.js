const express = require('express');
const router = express.Router();
const axios = require('axios');
const cheerio = require('cheerio');

/**
 * GET /episode/:slug - Get episode video and details
 * Example: /episode/renegade-immortal-episode-124-subtitle-indonesia
 */
router.get('/:slug', async (req, res) => {
  try {
    const slug = req.params.slug;
    const url = `https://donghuafilm.com/${slug}/`;
    
    const response = await axios.get(url, {
      headers: {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        'Referer': 'https://donghuafilm.com/'
      }
    });
    
    const $ = cheerio.load(response.data);
    
    // Extract episode title
    const title = $('h1.entry-title').text().trim();
    
    // Extract video player iframe
    const iframeSrc = $('iframe').attr('src') || 
                     $('.video-player iframe').attr('src') ||
                     $('.player iframe').attr('src');
    
    // Try to find video source directly
    let videoSource = null;
    $('script').each((i, el) => {
      const scriptContent = $(el).html();
      if (scriptContent && scriptContent.includes('video') && scriptContent.includes('http')) {
        // Look for common video patterns
        const videoRegex = /(https?:\/\/[^"'\s]+\.(mp4|m3u8)[^"'\s]*)/gi;
        const matches = scriptContent.match(videoRegex);
        if (matches && matches.length > 0) {
          videoSource = matches[0];
        }
        
        // Also check for player setup
        const playerRegex = /file:\s*["'](https?:\/\/[^"'\s]+)["']/gi;
        const playerMatches = scriptContent.match(playerRegex);
        if (playerMatches && playerMatches.length > 0) {
          videoSource = playerMatches[0].replace(/file:\s*["']|["']$/g, '');
        }
      }
    });
    
    // Extract download links if available
    const downloadLinks = [];
    $('a[href*="download"], a:contains("Download")').each((i, el) => {
      const link = $(el).attr('href');
      const text = $(el).text().trim();
      if (link && link.includes('http')) {
        downloadLinks.push({
          text,
          url: link,
          quality: text.match(/\d+p/i)?.[0] || 'Unknown'
        });
      }
    });
    
    // Extract episode navigation
    const navigation = {
      prev: $('.prev-ep a').attr('href'),
      next: $('.next-ep a').attr('href')
    };
    
    // Extract episode list for this anime
    const episodeList = [];
    $('.episode-list a').each((i, el) => {
      const epUrl = $(el).attr('href');
      const epText = $(el).text().trim();
      if (epUrl) {
        episodeList.push({
          url: epUrl,
          title: epText,
          number: epText.match(/\d+/)?.[0] || `${i + 1}`,
          isCurrent: epUrl === url
        });
      }
    });
    
    res.json({
      success: true,
      url,
      episode: {
        slug,
        title,
        iframeSrc,
        videoSource,
        hasVideo: !!(iframeSrc || videoSource)
      },
      downloads: downloadLinks,
      navigation,
      episodeList,
      totalEpisodes: episodeList.length
    });
    
  } catch (error) {
    console.error('Error fetching episode:', error.message);
    
    if (error.response && error.response.status === 404) {
      return res.status(404).json({
        success: false,
        error: 'Episode not found'
      });
    }
    
    res.status(500).json({
      success: false,
      error: error.message,
      message: 'Failed to fetch episode'
    });
  }
});

module.exports = router;
