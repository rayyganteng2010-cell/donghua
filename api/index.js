const express = require('express');
const cors = require('cors');
const app = express();

// Import route handlers
const homeRoutes = require('./home');
const searchRoutes = require('./search');
const animeRoutes = require('./anime');
const episodeRoutes = require('./episode');

// Middleware
app.use(cors());
app.use(express.json());

// Routes
app.use('/', homeRoutes);
app.use('/search', searchRoutes);
app.use('/anime', animeRoutes);
app.use('/episode', episodeRoutes);

// Health check
app.get('/health', (req, res) => {
  res.json({ status: 'ok', message: 'DonghuaFilm Scraper API is running' });
});

// Error handling
app.use((err, req, res, next) => {
  console.error(err.stack);
  res.status(500).json({ 
    error: 'Something went wrong!',
    message: err.message 
  });
});

// Handle 404
app.use((req, res) => {
  res.status(404).json({ error: 'Route not found' });
});

// Export for Vercel
module.exports = app;
