const express = require('express');
const cors = require('cors');

// Inisialisasi app
const app = express();

// Middleware SIMPLE
app.use(cors());
app.use(express.json());

// Health check - TEST DULU INI
app.get('/health', (req, res) => {
  console.log('Health check called');
  res.json({ 
    status: 'OK', 
    message: 'API is working',
    timestamp: new Date().toISOString()
  });
});

// Route sederhana untuk testing
app.get('/', (req, res) => {
  console.log('Home route called');
  res.json({
    message: 'DonghuaFilm API v2.0',
    endpoints: [
      '/health',
      '/test',
      '/search?q=immortal'
    ]
  });
});

// Test route untuk scrape sederhana
app.get('/test', async (req, res) => {
  try {
    const axios = require('axios');
    const cheerio = require('cheerio');
    
    console.log('Testing scrape...');
    const response = await axios.get('https://donghuafilm.com/', {
      timeout: 5000,
      headers: {
        'User-Agent': 'Mozilla/5.0'
      }
    });
    
    const $ = cheerio.load(response.data);
    const titles = [];
    
    $('h2 a').each((i, el) => {
      const title = $(el).text().trim();
      if (title) titles.push(title);
    });
    
    res.json({
      success: true,
      scraped: titles.slice(0, 10),
      total: titles.length
    });
    
  } catch (error) {
    console.error('Test error:', error.message);
    res.json({
      success: false,
      error: error.message,
      note: 'Scraping test failed'
    });
  }
});

// **NANTI tambahkan routes lain setelah ini bekerja**

// Error handler
app.use((err, req, res, next) => {
  console.error('Error:', err.message);
  res.status(500).json({
    error: 'Internal Server Error',
    details: err.message,
    timestamp: new Date().toISOString()
  });
});

// 404 handler
app.use((req, res) => {
  res.status(404).json({
    error: 'Not Found',
    path: req.path
  });
});

// Export untuk Vercel - INI YANG PALING PENTING
module.exports = app;
