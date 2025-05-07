from venv import logger

import scrapy
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from scrapy.http import HtmlResponse
import time

class RestaurantsSpider(scrapy.Spider):
    name = "restaurants"
    allowed_domains = ["tabelog.com"]
    start_urls = ['https://tabelog.com/tokyo/rstLst/']

    def __init__(self, num_restaurants=10, *args, **kwargs):
        super(RestaurantsSpider, self).__init__(*args, **kwargs)
        self.num_restaurants = int(num_restaurants)  # Desired number of restaurant links
        self.collected_links = 0  # Counter for collected links
        
        chrome_options = Options()
        # chrome_options.add_argument("--headless")  # Uncomment if you don't need GUI
        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_argument("--no-sandbox")
        self.driver = webdriver.Chrome(options=chrome_options)
        self.driver.maximize_window()

    def parse(self, response):
        self.driver.get(response.url)
        # time.sleep(3)
        try:
            # Wait for the modal to appear (up to 10 seconds)
            WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, 'div.c-lang-switch__inner.js-lang-change-text-en'))
            )

            # Find and click the "Switch to English" button
            switch_to_english_button = WebDriverWait(self.driver, 10).until(
                EC.element_to_be_clickable(
                    (By.CSS_SELECTOR, 'a.c-btn.c-lang-switch__btn.js-inbound-link.js-analytics-lang-switch'))
            )
            switch_to_english_button.click()

            # Wait for the page to reload (adjust wait time depending on network speed)
            WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, 'a.list-rst__rst-name-target'))
                # Example element after reload
            )
        except Exception as e:
            self.logger.info(f"Language switch modal not found or already handled: {e}")

        body = self.driver.page_source
        response = HtmlResponse(self.driver.current_url, body=body, encoding='utf-8', request=response.request)

        # Extract links to restaurant detail pages
        restaurant_links = response.css('a.list-rst__rst-name-target::attr(href)').getall()
        
        for link in restaurant_links:
            if self.collected_links < self.num_restaurants:
                self.collected_links += 1
                yield scrapy.Request(link, callback=self.parse_detail)
            else:
                break

        if self.collected_links < self.num_restaurants:
            # Handle next page

            next_page = response.css('a.c-pagination__arrow--next::attr(href)').get()
            if next_page:
                yield scrapy.Request(response.urljoin(next_page), callback=self.parse)

    def switch_to_english(self):

        try:
            # Wait for the modal to appear (up to 10 seconds)
            WebDriverWait(self.driver, 2).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, 'div.c-lang-switch__inner.js-lang-change-text-en'))
            )

            # Find and click the "Switch to English" button
            switch_to_english_button = WebDriverWait(self.driver, 2).until(
                EC.element_to_be_clickable(
                    (By.CSS_SELECTOR, 'a.c-btn.c-lang-switch__btn.js-inbound-link.js-analytics-lang-switch'))
            )
            switch_to_english_button.click()

            # Wait for the page to reload (adjust wait time depending on network speed)
            WebDriverWait(self.driver, 3).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, 'a.list-rst__rst-name-target'))
                # Example element after reload
            )
        except Exception as e:
            self.logger.info(f"Language switch modal not found or already handled: {e}")


    def get_headline_description(self, response):
        # Extract the visible part of the description
        visible_description = response.css('span.pr-comment__first::text').get()

        # Extract hidden part of the description
        hidden_description = response.css('span.pr-comment__over::text').get()

        # Combine both parts into a meaningful full description
        if visible_description and hidden_description:
            full_description = visible_description.strip() + hidden_description.strip()
        elif visible_description:
            full_description = visible_description.strip()
        else:
            full_description = None

        # Extract and log the headline for debugging
        headline = response.css('h3.pr-comment-title.js-pr-title::text').get()
        if headline:
            headline = headline.strip()

        return headline, full_description

    def parse_detail(self, response):
        self.driver.get(response.url)
        self.switch_to_english()
        body = self.driver.page_source
        response = HtmlResponse(self.driver.current_url, body=body, encoding='utf-8', request=response.request)

        headline, full_description = self.get_headline_description(response)

        data = {
            "editorial_overview":{
                "headline": headline,
                "description": full_description,
            },
            "review_rating": {

            },

            'url': response.url
        }

        self.logger.info(data)

        # Navigate to the Ratings section (optional next step)

        try:
            # Identify the Ratings URL
            ratings_url = response.css('a#rating::attr(href)').get()

            if ratings_url:
                self.logger.info(f"Found Ratings URL: {ratings_url}")

                # Navigate to the Ratings page using Selenium
                self.driver.get(ratings_url)

                # Wait for the Ratings page to load
                WebDriverWait(self.driver, 3).until(EC.presence_of_element_located(
                    (By.CSS_SELECTOR, 'div.ratings-contents')))  # Ensure the ratings section has loaded

                # Get the current page source for scraping
                body = self.driver.page_source
                ratings_response = HtmlResponse(self.driver.current_url, body=body, encoding='utf-8',
                                                request=response.request)

                logger.info("Extracting average ratings...")

                # Extract Average Ratings
                average_ratings = {}

                # Extract titles and scores for average ratings
                rating_titles = ratings_response.css(
                    'dl.ratings-contents__table dt.ratings-contents__table-txt::text').getall()
                rating_scores = ratings_response.css(
                    'dl.ratings-contents__table dd.ratings-contents__table-score::text').getall()

                logger.info(f"Found rating titles: {rating_titles}")
                logger.info(f"Found rating scores: {rating_scores}")

                if not rating_titles or not rating_scores:
                    logger.warning("Rating titles or scores are missing!")
                else:
                    # Combine titles and scores into a dictionary
                    for title, score in zip(rating_titles, rating_scores):
                        average_ratings[title.strip()] = float(score.strip())
                    logger.info(f"Extracted average ratings: {average_ratings}")

                # Extract Rating Distribution
                logger.info("Extracting rating distribution...")
                rating_distribution = []

                # Find all distribution items
                distribution_items = ratings_response.css('li.ratings-contents__item')
                logger.info(f"Found {len(distribution_items)} distribution items.")

                if not distribution_items:
                    logger.warning("No distribution items found! Check the page structure.")
                else:
                    # Loop through each item and extract details
                    for index, item in enumerate(distribution_items, start=1):
                        try:
                            # Get the range (e.g., "5.0", "4.5 - 4.9")
                            rating_range = item.css(
                                'b.c-rating-v2__val.c-rating-v2__val--strong.ratings-contents__item-score::text').get().strip()
                            logger.info(f"Item {index}: Found rating range '{rating_range}'")

                            # Extract percentage width (e.g., "7%") from inline style
                            percentage_width = item.css('span.ratings-contents__item-gauge::attr(style)').re_first(
                                r'width:\s*(\d+)%')
                            logger.info(f"Item {index}: Found percentage width '{percentage_width}'")

                            # Get people count (number of individuals who gave this rating)
                            people_count = item.css('strong.ratings-contents__item-num-strong::text').get().strip()
                            logger.info(f"Item {index}: Found people count '{people_count}'")

                            rating_distribution.append({
                                "range": rating_range,
                                "percentage": int(percentage_width) if percentage_width else 0,
                                "people": int(people_count)
                            })
                        except Exception as e:
                            logger.error(f"Error extracting distribution item {index}: {e}")

                logger.info(f"Extracted rating distribution: {rating_distribution}")

                # Add extracted data to review_rating
                data["review_rating"] = {
                    "average_ratings": average_ratings,
                    "rating_distribution": rating_distribution
                }

                # Log the final structured data
                logger.info(f"Final extracted ratings data: {data['review_rating']}")
        except Exception as e:
            self.logger.error(f"Error navigating to Ratings page: {e}")

        # Yield the final result
        yield data

    def closed(self, reason):
        self.driver.quit()
