require('dotenv').config();
const express = require('express');
const path = require('path');
const axios = require('axios');
const rateLimit = require('express-rate-limit');
const app = express();
const port = process.env.PORT || 3000;

// Rate limiting
const limiter = rateLimit({
  windowMs: 15 * 60 * 1000, // 15 minutes
  max: 100 // limit each IP to 100 requests per windowMs
});

// Middleware
app.set('view engine', 'ejs');
app.set('views', path.join(__dirname, 'views'));
app.use(express.urlencoded({ extended: true }));
app.use(express.static('public'));
app.use(limiter);

// Lead scoring function
function scoreLead(clinic) {
  let score = 0;
  
  if (clinic.phone) score += 20;
  if (clinic.website) score += 20;
  if (clinic.email) score += 30;
  if (clinic.rating) score += Math.min(30, clinic.rating * 6);
  
  return score;
}

// Email extraction function
async function extractEmails(url) {
  try {
    const response = await axios.get(url, {
      headers: { 'User-Agent': 'Mozilla/5.0' },
      timeout: 5000
    });
    const emailRegex = /\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b/g;
    return response.data.match(emailRegex) || [];
  } catch (error) {
    return [];
  }
}

// Add this function to your server code
function isEmailVerified(email) {
  if (!email) return false;
  
  // Simple verification - check for common professional domains
  const verifiedDomains = [
    'gmail.com', 'yahoo.com', 'outlook.com', 
    'icloud.com', 'protonmail.com', 'hotmail.com'
  ];
  
  try {
    const domain = email.split('@')[1].toLowerCase();
    return verifiedDomains.includes(domain);
  } catch (e) {
    return false;
  }
}

// Then modify your route handler to pre-process the data
app.post('/scrape', async (req, res) => {
  const { keyword, location } = req.body;
  
  try {
    const serpapiResponse = await axios.get('https://serpapi.com/search.json', {
      params: {
        engine: 'google_maps',
        q: `${keyword} in ${location}`,
        type: 'search',
        api_key: process.env.SERPAPI_KEY
      }
    });

    let results = [];
    const places = serpapiResponse.data.local_results || [];

    for (const place of places.slice(0, 10)) {
      const clinic = {
        name: place.title,
        address: place.address,
        phone: place.phone,
        website: place.website,
        rating: place.rating,
        reviews: place.reviews,
        email: null,
        emailVerified: false // Initialize as false
      };

      if (place.website) {
        const emails = await extractEmails(place.website);
        if (emails.length > 0) {
          clinic.email = emails[0];
          clinic.emailVerified = isEmailVerified(emails[0]); // Set verification status
        }
      }

      clinic.score = scoreLead(clinic);
      results.push(clinic);
    }

    res.render('results', { 
      keyword,
      location,
      results,
      error: null
    });

  } catch (error) {
    console.error('Scraping error:', error);
    res.render('results', { 
      keyword,
      location,
      results: [],
      error: 'Failed to fetch results. Please try again later.'
    });
  }
});

// Routes
app.get('/', (req, res) => {
  res.render('index');
});

app.post('/scrape', async (req, res) => {
  const { keyword, location } = req.body;
  
  try {
    // Get Google Maps results via SerpAPI
    const serpapiResponse = await axios.get('https://serpapi.com/search.json', {
      params: {
        engine: 'google_maps',
        q: `${keyword} in ${location}`,
        type: 'search',
        api_key: process.env.SERPAPI_KEY
      }
    });

    // Process results
    let results = [];
    const places = serpapiResponse.data.local_results || [];

    for (const place of places.slice(0, 10)) {
      const clinic = {
        name: place.title,
        address: place.address,
        phone: place.phone,
        website: place.website,
        rating: place.rating,
        reviews: place.reviews
      };

      // Extract email if website exists
      if (place.website) {
        clinic.email = (await extractEmails(place.website))[0] || null;
      }

      // Calculate score
      clinic.score = scoreLead(clinic);
      clinic.category = clinic.score >= 70 ? 'Hot' : clinic.score >= 40 ? 'Warm' : 'Cold';
      
      results.push(clinic);
    }

    res.render('results', { 
      keyword,
      location,
      results,
      error: null
    });

  } catch (error) {
    console.error('Scraping error:', error);
    res.render('results', { 
      keyword,
      location,
      results: [],
      error: 'Failed to fetch results. Please try again later.'
    });
  }
});

app.listen(port, () => {
  console.log(`Server running at http://localhost:${port}`);
});