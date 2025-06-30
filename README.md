# Tabelog Restaurant Scraper

**Tabelog Scraper** is a comprehensive web scraping project built with [Scrapy](https://scrapy.org/) and [Selenium](https://selenium.dev/) to extract detailed restaurant information from [Tabelog](https://tabelog.com). It features both command-line and web API interfaces for flexible usage.

---

## 📁 Project Structure

```
tabelog_scraper/
├── items.py           # Define item models for scraped data
├── middlewares.py     # Custom middlewares for spider and downloader
├── pipelines.py       # Process scraped items
├── settings.py        # Scrapy project settings with JSON output
├── spiders/
│   ├── __init__.py    # Spider package initialization
│   └── restaurants.py # Main spider with FastAPI web interface
.scrapy/
└── httpcache/         # HTTP cache for storing responses

restaurants.json       # Output file for scraped restaurant data
scrape_restore.json    # Resume/checkpoint file for interrupted scrapes
scrape_status.log      # Detailed logging of scraping progress
scrapy.cfg             # Scrapy configuration file
requirements.txt       # Project dependencies
```

---

## ✅ Features

- **Comprehensive Data Extraction**: Restaurant details, ratings, reviews, menu information, photos, and facilities
- **Dual Interface**: Both FastAPI web interface and command-line usage
- **Resume Capability**: Automatically resume interrupted scrapes from checkpoint
- **Rate Limiting Handling**: Built-in 429 error handling and retry logic
- **Selenium Integration**: Handles JavaScript-heavy pages and dynamic content
- **Progress Tracking**: Real-time status monitoring and logging
- **Multiple Output Formats**: JSON output with detailed restaurant information
- **HTTP Caching**: Enabled to reduce redundant requests and improve performance

---

## 🚀 Installation

1. **Clone the repository**

   ```sh
   git clone <repository-url>
   cd tabelog_scraper
   ```

2. **Install dependencies**

   ```sh
   pip install -r requirements.txt
   ```

3. **Install ChromeDriver for Selenium**

   ```sh
   pip install webdriver-manager
   ```

---

## 🕷️ Usage

### Method 1: Web API Interface (Recommended)

Start the FastAPI web server:

```sh
python -m tabelog_scraper.spiders.restaurants
```

The server will start on `http://localhost:8000` with the following endpoints:

- **Interactive API Documentation**: `http://localhost:8000/docs`
- **Scrape restaurants**: `GET /scrape`
- **Check status**: `GET /status`
- **Download results**: `GET /download/{filename}`

**Example API usage:**
```
http://localhost:8000/scrape?base_url=https://tabelog.com/en/tokyo/A1303/rstLst/?LstSitu=2&num_restaurants=5&resume=false
```

**Parameters:**
- `base_url`: The Tabelog listing page URL
- `num_restaurants`: Number of restaurants to scrape (default: 10)
- `resume`: Whether to resume from a previous run (default: false)

### Method 2: Command Line Interface

**Basic usage - scrape 5 restaurants from Tokyo Ginza area:**

```sh
scrapy crawl restaurants -a num_restaurants=5 -a start_urls="https://tabelog.com/en/tokyo/A1303/rstLst/?LstSitu=2"
```

**Resume a previous scrape:**

```sh
scrapy crawl restaurants -a num_restaurants=10 -a resume=true
```

**Output to a specific file:**

```sh
scrapy crawl restaurants -a num_restaurants=3 -o my_restaurants.json
```

**Available parameters:**
- `num_restaurants`: Number of restaurants to scrape
- `start_urls`: Starting URL for scraping
- `resume`: Resume from previous checkpoint (true/false)

---

## � Data Structure

The scraper extracts the following information for each restaurant:

```json
{
  "restaurant_information": {
    "details": [
      {"field": "Restaurant name", "value": "Restaurant Name"},
      {"field": "Categories", "value": "Japanese, Sushi"},
      {"field": "Address", "value": "Tokyo Address"},
      {"field": "Phone number", "value": "03-1234-5678"},
      {"field": "Business hours", "value": "11:00-22:00"},
      {"field": "Average price", "value": "JPY 3,000 - JPY 5,000"}
    ],
    "seats_facilities": [...],
    "menu": [...],
    "feature_related_info": [...]
  },
  "review_count": 150,
  "review_rating": {
    "average_ratings": {...},
    "rating_distribution": [...],
    "reviews": [...]
  },
  "url": "https://tabelog.com/restaurant/url"
}
```

---

## 🔧 Monitoring and Status

### Status Monitoring

Check scraping progress at: `http://localhost:8000/status`

This endpoint provides:
- Number of restaurants scraped
- Number failed
- Number pending
- Recent log entries
- Complete URL lists

### Resume Functionality

The scraper automatically saves progress to `scrape_restore.json`. If interrupted, simply run with `resume=true` to continue from where you left off.

### Logging

Detailed logs are saved to `scrape_status.log` with timestamps and performance metrics.

---

## ⚙️ Configuration

### Spider Settings

Modify settings in `tabelog_scraper/settings.py`:

- **Output Format**: JSON output is configured by default
- **Rate Limiting**: AutoThrottle is enabled to respect server limits
- **Caching**: HTTP caching enabled for development and debugging
- **Feed Settings**: Automatic JSON export with UTF-8 encoding

### Customization

- **Target Areas**: Modify `start_urls` parameter to scrape different regions
- **Data Fields**: Uncomment sections in `parse_detail()` method to enable additional data extraction:
  - `specialities`: Restaurant specialties and features
  - `menu`: Detailed menu information with prices
  - `interior_photos`: Official restaurant photos
  - `editorial_overview`: Editorial descriptions and headlines

### Chrome Options

The spider uses Chrome WebDriver with optimized settings:
- Headless mode available (uncomment in spider init)
- GPU acceleration disabled for stability
- Window size optimized for page rendering

---

## 🚨 Error Handling

### Rate Limiting (429 Errors)

The scraper automatically handles rate limiting:
- Detects 429 "Too Many Requests" errors
- Waits 60 seconds before retrying
- Continues scraping from the last successful point

### Network Issues

- Automatic retry mechanism for failed requests
- Progress is saved continuously to prevent data loss
- Failed URLs are logged separately for manual review

### Browser Issues

- Selenium WebDriver is automatically managed
- Graceful handling of page load timeouts
- Automatic cleanup of browser resources

---

## 📈 Performance

### Optimization Features

- **HTTP Caching**: Reduces redundant requests during development
- **AutoThrottle**: Automatically adjusts request rate based on response times
- **Concurrent Processing**: Configurable concurrency limits
- **Checkpoint System**: Resume capability prevents starting over

### Recommended Settings

- Start with `num_restaurants=5` for testing
- Use `resume=true` for large scraping jobs
- Monitor the `/status` endpoint for progress tracking
- Check `scrape_status.log` for detailed performance metrics

---

## ⚠️ Important Notes

- **Compliance**: Ensure compliance with **Tabelog's Terms of Service** when scraping
- **Rate Limits**: The scraper includes built-in rate limiting to be respectful to the server
- **Data Usage**: Use scraped data responsibly and in accordance with applicable laws
- **Chrome Dependency**: Requires Chrome/Chromium browser to be installed on the system
- **Memory Usage**: Large scraping jobs may require sufficient RAM for data processing

---

## 🐛 Troubleshooting

### Common Issues

1. **ChromeDriver not found**: Install Chrome and ensure it's in your PATH
2. **Permission denied**: Check file permissions for output directories
3. **Memory errors**: Reduce `num_restaurants` for large scraping jobs
4. **Network timeouts**: Increase timeout values in spider settings

### Getting Help

- Check the `scrape_status.log` file for detailed error messages
- Use the `/status` endpoint to monitor scraping progress
- Review the restore file `scrape_restore.json` for checkpoint data

---

## 📄 License

This project is licensed under the **MIT License**.