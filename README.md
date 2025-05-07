# Tabelog Scraper

**Tabelog Scraper** is a web scraping project built with [Scrapy](https://scrapy.org/) to extract restaurant information from [Tabelog](https://tabelog.com). It gathers details such as restaurant names, ratings, areas, and URLs.

---

## 📁 Project Structure

```
tabelog_scraper/
├── items.py           # Define item models for scraped data
├── middlewares.py     # Custom middlewares for spider and downloader
├── pipelines.py       # Process scraped items
├── settings.py        # Scrapy project settings
├── spiders/
│   ├── __init__.py    # Spider package initialization
│   └── restaurants.py # Spider for scraping restaurant data
.scrapy/
└── httpcache/         # HTTP cache for storing responses

restaurants.json       # Output file for scraped data
scrapy.cfg             # Scrapy configuration file
```

---

## ✅ Features

- Scrapes restaurant details: **name**, **rating**, **area**, and **URL**
- Supports pagination to scrape multiple result pages
- Optional: Includes Selenium middleware for JavaScript-rendered content
- HTTP caching enabled to reduce redundant requests and improve debug speed

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

3. **Install ChromeDriver for Selenium** *(if using Selenium middleware)*:
   ```sh
   pip install webdriver-manager
   ```

---

## 🕷️ Usage

Run the spider and save data to a JSON file:
```sh
scrapy crawl restaurants -o restaurants.json
```

---

## ⚙️ Configuration

- Modify `start_urls` in `spiders/restaurants.py` to scrape different regions.
- Adjust values in `settings.py` to customize behavior (e.g., download delay, concurrency).

---

## ⚠️ Notes

- Ensure compliance with **Tabelog's Terms of Service** when scraping.
- HTTP caching is enabled by default in `settings.py` to reduce load and speed up development.

---

## 📄 License

This project is licensed under the **MIT License**.