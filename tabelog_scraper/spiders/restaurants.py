from venv import logger

import scrapy
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from scrapy.http.response.html import HtmlResponse
import time
import logging
from fastapi import FastAPI, Query, BackgroundTasks
from fastapi.responses import JSONResponse, FileResponse
import uvicorn
import os
import json
from datetime import datetime, timedelta
import subprocess
import sys
import threading


# Set up module-level logger
logger = logging.getLogger(__name__)


# Set Selenium logging level to WARNING
logging.getLogger('selenium').setLevel(logging.WARNING)

# Set Scrapy logging level to WARNING
logging.getLogger('scrapy').setLevel(logging.WARNING)

app = FastAPI(title="Tabelog Restaurant Scraper API",
              description="API for scraping Tabelog restaurant data.")

# Global variable to track running scraping tasks
scraping_task_status = {
    "is_running": False,
    "start_time": None,
    "current_params": None,
    "process": None
}


class RestaurantsSpider(scrapy.Spider):
    name = "restaurants"
    allowed_domains = ["tabelog.com"]
    # start_urls = ['https://tabelog.com/en/rstLst/?utf8=%E2%9C%93&svd=&svt=1900&svps=2&vac_net=1&pcd=41']

    # start_urls = ['https://tabelog.com/en/tokyo/A1303/rstLst/?LstSitu=2']

    def __init__(self, num_restaurants=5, start_urls=None, resume=False, *args, **kwargs):
        super(RestaurantsSpider, self).__init__(*args, **kwargs)
        self.num_restaurants = int(num_restaurants)
        self.collected_links = 0
        self.processed_links = 0
        self.resume = resume if isinstance(resume, bool) else resume.lower() == 'true'
        
        # Handle start_urls properly
        if start_urls:
            if isinstance(start_urls, str):
                # If it's a string, convert it to a list
                self.start_urls = [start_urls]
            elif isinstance(start_urls, list):
                self.start_urls = start_urls
            else:
                self.start_urls = ['https://tabelog.com/en/tokyo/A1303/rstLst/?LstSitu=2']
        else:
            self.start_urls = ['https://tabelog.com/en/tokyo/A1303/rstLst/?LstSitu=2']
            
        self.restore_file = 'scrape_restore.json'
        self.status_log = 'scrape_status.log'
        self.output = 'restaurants.json'
        self.scraped_urls = set()
        self.failed_urls = set()
        self.pending_urls = set()
        self.start_time = datetime.now()

        # Set up logging
        self.logger.info(f"Initializing RestaurantsSpider with num_restaurants={num_restaurants}, resume={resume}")
        self.logger.info(f"Start URLs: {self.start_urls}")

        # Restore point logic
        if self.resume and os.path.exists(self.restore_file):
            with open(self.restore_file, 'r') as f:
                data = json.load(f)
                self.scraped_urls = set(data.get('scraped_urls', []))
                self.failed_urls = set(data.get('failed_urls', []))
                self.pending_urls = set(data.get('pending_urls', []))
                self.collected_links = len(self.scraped_urls)
            self.logger.info(f"Restored state - Scraped: {len(self.scraped_urls)}, Failed: {len(self.failed_urls)}")
        elif not self.resume:
            # Clean up existing files if not resuming
            if os.path.exists(self.restore_file):
                os.remove(self.restore_file)
            if os.path.exists(self.status_log):
                os.remove(self.status_log)
            if os.path.exists(self.output):
                os.remove(self.output)
       
        # Set up Selenium WebDriver
        self.logger.info("Setting up Chrome WebDriver")
        chrome_options = Options()
        # chrome_options.add_argument("--headless")  # Uncomment if you don't need GUI
        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument('--disable-dev-shm-usage')
        chrome_options.add_argument('--window-size=1920,1080')
        
        try:
            self.driver = webdriver.Chrome(options=chrome_options)
            self.logger.info("Chrome WebDriver initialized successfully")
        except Exception as e:
            self.logger.error(f"Failed to initialize Chrome WebDriver: {e}")
            raise
        # self.driver.maximize_window()

        # Wait times for different operations
        self.wait_general = 10
        self.wait_modal = 5
        self.wait_menu = 10
        self.wait_photos = 10

    def parse(self, response):
        import time

        # Add 429 error handling at the start
        if response.status == 429:
            self.logger.warning("Received 429 error, waiting 60 seconds before retry")
            time.sleep(60)
            yield scrapy.Request(url=response.url, callback=self.parse, dont_filter=True)
            return
        
        self.logger.info(f"Starting parse for URL: {response.url}")
        # Add delay before using Selenium
        time.sleep(5)  # Wait 5 seconds before using Selenium

        self.driver.get(response.url)

# try:
        #     # Wait for the modal to appear (up to 10 seconds)
        #     WebDriverWait(self.driver, 10).until(
        #         EC.presence_of_element_located(
        #             (By.CSS_SELECTOR, 'div.c-lang-switch__inner.js-lang-change-text-en'))
        #     )

        #     # Find and click the "Switch to English" button
        #     switch_to_english_button = WebDriverWait(self.driver, 10).until(
        #         EC.element_to_be_clickable(
        #             (By.CSS_SELECTOR, 'a.c-btn.c-lang-switch__btn.js-inbound-link.js-analytics-lang-switch'))
        #     )
        #     switch_to_english_button.click()

        #     # Wait for the page to reload (adjust wait time depending on network speed)
        #     WebDriverWait(self.driver, 10).until(
        #         EC.presence_of_element_located(
        #             (By.CSS_SELECTOR, 'a.list-rst__rst-name-target'))
        #         # Example element after reload
        #     )
        # except Exception as e:
        #     self.logger.info(
        #         f"Language switch modal not found or already handled: e")

        body = self.driver.page_source
        response = HtmlResponse(
            self.driver.current_url, body=body, encoding='utf-8', request=response.request)

        # Extract links to restaurant detail pages
        restaurant_links = response.css('a.list-rst__rst-name-target::attr(href)').getall()
        
        # Load existing state or start fresh
        if os.path.exists(self.restore_file):
            with open(self.restore_file, 'r') as f:
                restore_data = json.load(f)
                self.scraped_urls = set(restore_data.get('scraped_urls', []))
                self.failed_urls = set(restore_data.get('failed_urls', []))
                pending_urls = set(restore_data.get('pending_urls', []))
            if self.resume:
                self.logger.info("Resuming - loading existing state")
                self.logger.info(f"Loaded state - Scraped: {len(self.scraped_urls)}, Failed: {len(self.failed_urls)}, Pending: {len(pending_urls)}")
            else:
                self.logger.info("Starting fresh scrape (but preserving collected URLs)")
        else:
            pending_urls = set()
            if self.resume:
                self.logger.info("Resume requested but no restore file found")
            else:
                self.logger.info("Starting fresh scrape")

        # Add new links to pending_urls
        new_links = 0
        for link in restaurant_links:
            if link not in self.scraped_urls and link not in self.failed_urls and link not in pending_urls:
                pending_urls.add(link)
                new_links += 1
        
        self.logger.info(f"Added {new_links} new links to pending list")

        # Save all found links to scrape_restore.json
        self.logger.info(f"Saving {len(pending_urls)} pending URLs to restore file")
        with open(self.restore_file, 'w') as f:
            json.dump({
                'pending_urls': list(pending_urls),
                'scraped_urls': list(self.scraped_urls),
                'failed_urls': list(self.failed_urls)
            }, f)

        # If there are more pages, keep crawling to collect all links
        next_page = response.css('a.c-pagination__arrow--next::attr(href)').get()
        if next_page:
            self.logger.info(f"Found next page: {next_page}")
            yield scrapy.Request(response.urljoin(next_page), callback=self.parse)
        else:
            self.logger.info("No more pages found - starting detail scraping")
            # Once all links are collected, start scraping details
            count = 0
            for link in list(pending_urls):
                if count >= self.num_restaurants:
                    self.logger.info(f"Reached limit of {self.num_restaurants} restaurants")
                    break
                count += 1
                self.logger.info(f"Queuing detail scrape for link {count}/{min(len(pending_urls), self.num_restaurants)}: {link}")
                yield scrapy.Request(link, callback=self.parse_detail, meta={'restaurant_url': link})

    def parse_detail(self, response):
        # Add 429 error handling
        if response.status == 429:
            self.logger.warning("Received 429 error in detail page, waiting 60 seconds")
            import time
            time.sleep(60)
            yield scrapy.Request(url=response.url, callback=self.parse_detail, 
                           meta=response.meta, dont_filter=True)
            return
    
        url = response.meta.get('restaurant_url', response.url)
        start_time = datetime.now()
        # Load restore data
        with open(self.restore_file, 'r') as f:
            restore_data = json.load(f)
        pending_urls = set(restore_data.get('pending_urls', []))
        scraped_urls = set(restore_data.get('scraped_urls', []))
        failed_urls = set(restore_data.get('failed_urls', []))
        try:
            self.driver.get(response.url)
            body = self.driver.page_source
            response = HtmlResponse(
                self.driver.current_url, body=body, encoding='utf-8', request=response.request)

            # headline, full_description = self.get_headline_description(response)
            restaurant_information = self.parse_restaurant_information()
            review_count = self.get_review_count(response)
            # specialities = self.fetch_specialities_data()
            # setmenu = self.navigate_to_menu()
                # interior_photos = self.navigate_and_get_interior_official_photos()
            review_rating_data = self.review_rating(response)
            data = {
                # "editorial_overview": {
                #     "headline": headline,
                #     "description": full_description,
                # },
                "restaurant_information": restaurant_information,
                "review_count": review_count,
                "review_rating": review_rating_data,
                # "specialities": specialities,
                # "menu": setmenu,
                # "interior_photos": interior_photos,
                'url': response.url
            }
            # Update restore data
            pending_urls.discard(url)
            scraped_urls.add(url)
            with open(self.restore_file, 'w') as f:
                json.dump({
                    'pending_urls': list(pending_urls),
                    'scraped_urls': list(scraped_urls),
                    'failed_urls': list(failed_urls)
                }, f)
            # Log status
            elapsed = (datetime.now() - start_time).total_seconds()
            with open(self.status_log, 'a') as logf:
                logf.write(
                    f"SUCCESS: {url} | Time: {elapsed:.2f}s | {datetime.now().isoformat()}\n")
            yield data
        except Exception as e:
            pending_urls.discard(url)
            failed_urls.add(url)
            with open(self.restore_file, 'w') as f:
                json.dump({
                    'pending_urls': list(pending_urls),
                    'scraped_urls': list(scraped_urls),
                    'failed_urls': list(failed_urls)
                }, f)
            elapsed = (datetime.now() - start_time).total_seconds()
            with open(self.status_log, 'a') as logf:
                logf.write(
                    f"FAILED: {url} | Time: {elapsed:.2f}s | {datetime.now().isoformat()} | Error: {e}\n")
                
            # Handle 429 error (Too Many Requests)
            if "429" in str(e) or "Too Many Requests" in str(e):
                import time as _time
                _time.sleep(60)  # Wait 1 minute before retrying
                yield scrapy.Request(url, callback=self.parse_detail, meta={'restaurant_url': url}, dont_filter=True)

    def _save_restore_point(self):
        with open(self.restore_file, 'w') as f:
            json.dump({
                'scraped_urls': list(self.scraped_urls),
                'failed_urls': list(self.failed_urls)
            }, f)

    def review_rating(self, response):
        average_ratings = {}
        rating_distribution = []
        
        try:
            # Additional scraping logic for ratings (if applicable)
            ratings_url = response.css('a#rating::attr(href)').get()
            if ratings_url:
                self.driver.get(ratings_url)
                WebDriverWait(self.driver, 3).until(EC.presence_of_element_located(
                    (By.CSS_SELECTOR, 'div.ratings-contents')))
                body = self.driver.page_source
                ratings_response = HtmlResponse(
                    self.driver.current_url, body=body, encoding='utf-8', request=response.request)

                logger.info("Extracting average ratings...")

                # Extract Average Ratings
                # Extract titles and scores for average ratings
                rating_titles = ratings_response.css(
                    'dl.ratings-contents__table dt.ratings-contents__table-txt::text').getall()
                rating_scores = ratings_response.css(
                    'dl.ratings-contents__table dd.ratings-contents__table-score::text').getall()

                if not rating_titles or not rating_scores:
                    logger.warning("Rating titles or scores are missing!")
                else:
                    # Combine titles and scores into a dictionary
                    for title, score in zip(rating_titles, rating_scores):
                        average_ratings[title.strip()] = float(score.strip())
                    # logger.info(f"Extracted average ratings: {average_ratings}")

                # Extract Rating Distribution
                # Find all distribution items
                distribution_items = ratings_response.css(
                    'li.ratings-contents__item')

                if not distribution_items:
                    logger.warning(
                        "No distribution items found! Check the page structure.")
                else:
                    # Loop through each item and extract details
                    for index, item in enumerate(distribution_items, start=1):
                        try:
                            # Get the range (e.g., "5.0", "4.5 - 4.9")
                            rating_range = item.css(
                                'b.c-rating-v2__val.c-rating-v2__val--strong.ratings-contents__item-score::text'
                            ).get()
                            rating_range = rating_range.strip() if rating_range else None

                            # Extract percentage width (e.g., "7%") from inline style
                            percentage_width = item.css(
                                'span.ratings-contents__item-gauge::attr(style)'
                            ).re_first(r'width:\s*(\d+)%')
                            percentage_width = int(
                                percentage_width) if percentage_width else 0

                            # Get people count (number of individuals who gave this rating)
                            people_count = item.css(
                                'strong.ratings-contents__item-num-strong::text'
                            ).get()
                            people_count = int(
                                people_count.strip()) if people_count else 0

                            # Append the extracted data to the list
                            if rating_range:
                                rating_distribution.append({
                                    "range": rating_range,
                                    "percentage": percentage_width,
                                    "people": people_count
                                })
                        except Exception as e:
                            logger.error(
                                f"Error extracting distribution item {index}: {e}")

                # Log the final structured data
                # logger.info(f"Final extracted ratings data: {data['review_rating']}")

                # After extracting ratings, navigate to review page
                # self.navigate_to_review_page()

        except Exception as e:
            self.logger.error(f"Error navigating to Ratings page: {e}")

        return {
            "average_ratings": average_ratings,
            "rating_distribution": rating_distribution,
            "reviews": self.navigate_to_review_page()
        }

    def navigate_to_review_page(self):
        try:
            # Wait for the Reviews tab to appear
            review_tab = WebDriverWait(self.driver, self.wait_menu).until(
                EC.presence_of_element_located(
                    (By.CSS_SELECTOR, "a#review"))
            )
            review_url = review_tab.get_attribute('href')
            logger.info(f"Navigating to Review tab: {review_url}")

            # Click the Reviews tab
            self.driver.execute_script(
                "arguments[0].scrollIntoView(true);", review_tab)
            review_tab.click()

            # Wait for the review page to load
            WebDriverWait(self.driver, self.wait_menu).until(
                EC.presence_of_element_located(
                    (By.CSS_SELECTOR, "div.rvw-item.js-rvw-item-clickable-area"))
            )
            logger.info("Successfully navigated to the review page.")

            all_reviews = []
            while True:
                # Get the page source and create a Scrapy HtmlResponse
                body = self.driver.page_source
                response = HtmlResponse(
                    self.driver.current_url, body=body, encoding='utf-8')

                # Extract all reviews using parse_reviews
                reviews = self.parse_reviews(response)
                all_reviews.extend(reviews)

                # Check for next page in pagination
                next_page = response.css(
                    'a.c-pagination__arrow--next::attr(href)').get()
                if next_page:
                    logger.info(f"Found next review page: {next_page}")
                    self.driver.get(next_page)
                    WebDriverWait(self.driver, self.wait_menu).until(
                        EC.presence_of_element_located(
                            (By.CSS_SELECTOR, "div.rvw-item.js-rvw-item-clickable-area"))
                    )
                else:
                    break
            return all_reviews

        except Exception as e:
            logger.error(
                f"Failed to navigate to Review page or extract reviews: {e}")
            return []

    def switch_to_english(self):
        try:
            # Wait for the modal to appear
            WebDriverWait(self.driver, self.wait_modal).until(
                EC.presence_of_element_located(
                    (By.CSS_SELECTOR, 'div.c-lang-switch__inner.js-lang-change-text-en'))
            )

            # Find and click the "Switch to English" button
            switch_to_english_button = WebDriverWait(self.driver, self.wait_modal).until(
                EC.element_to_be_clickable(
                    (By.CSS_SELECTOR, 'a.c-btn.c-lang-switch__btn.js-inbound-link.js-analytics-lang-switch'))
            )
            switch_to_english_button.click()

            # Wait for the page to reload
            WebDriverWait(self.driver, self.wait_general).until(
                EC.presence_of_element_located(
                    (By.CSS_SELECTOR, 'a.list-rst__rst-name-target'))
            )
        except Exception as e:
            self.logger.info(
                f"Language switch modal not found or already handled: e")

    def get_headline_description(self, response):
        # Extract the visible part of the description
        visible_description = response.css(
            'span.pr-comment__first::text').get()

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

    def fetch_specialities_data(self):
        try:
            # Wait for the 'Specialities' section to load
            specialities_section = WebDriverWait(self.driver, self.wait_general).until(
                EC.presence_of_all_elements_located(
                    (By.CLASS_NAME, "js-kodawari-cassete"))
            )

            if not specialities_section:
                logger.warning("No specialities section found!")
                return []

            # logger.info(f"Found {len(specialities_section)} specialities.")

            # Click on the first speciality item to open the modal
            first_item = specialities_section[0]
            self.driver.execute_script(
                "arguments[0].scrollIntoView(true);", first_item)
            first_item.click()
            # logger.info("Clicked on the first speciality item.")

            # Force rendering of all modal contents
            self.driver.execute_script(
                "document.querySelectorAll('.c-modal__contents').forEach(modal => modal.classList.remove('is-hidden'));"
            )

            # Use JavaScript to get all modal contents
            modal_contents = self.driver.execute_script(
                "return Array.from(document.querySelectorAll('.c-modal__contents')).map(modal => {"
                "    return {"
                "        image_src: modal.querySelector('.rstdtl-top-kodawari__modal-photo img')?.getAttribute('src')?.replace('320x320_square_', '') || null,"
                "        title: modal.querySelector('.rstdtl-top-kodawari__modal-title')?.innerText.trim() || null,"
                "        comment: modal.querySelector('.rstdtl-top-kodawari__modal-comment')?.innerText.trim() || null,"
                "        label: modal.querySelector('.rstdtl-top-kodawari__modal-label')?.innerText.trim() || null"
                "    };"
                "}).filter(item => item.image_src !== null);"
            )

            # logger.info(f"Extracted {len(modal_contents)} modal contents.")

            # Close the modal at the end
            try:
                close_button = WebDriverWait(self.driver, self.wait_modal).until(
                    EC.element_to_be_clickable(
                        (By.CLASS_NAME, "js-modal-close"))
                )
                close_button.click()
                logger.info("Closed the modal.")
            except Exception as e:
                logger.warning(f"Failed to close the modal: e")

            return modal_contents

        except Exception as e:
            logger.error(f"Failed to retrieve 'Specialities' data: e")
            return []

    def navigate_to_menu(self):
        try:
            # Wait for the Menu tab to appear
            menu_tab = WebDriverWait(self.driver, self.wait_menu).until(
                EC.presence_of_element_located(
                    (By.CSS_SELECTOR, "li#rdnavi-menu a.mainnavi"))
            )

            # Check if an overlay is present and close it
            try:
                overlay = WebDriverWait(self.driver, self.wait_modal).until(
                    EC.presence_of_element_located(
                        (By.CSS_SELECTOR, "div.c-overlay.js-overlay.js-modal-overlay-clickarea.is-closeable"))
                )
                if overlay:
                    logger.info("Closing overlay...")
                    self.driver.execute_script(
                        "arguments[0].click();", overlay)
                    WebDriverWait(self.driver, self.wait_modal).until(
                        EC.invisibility_of_element(overlay))
                    logger.info("Overlay closed.")
            except Exception as e:
                logger.info("No overlay found or already handled.")

            # Log the href attribute of the Menu tab
            menu_tab_url = menu_tab.get_attribute('href')
            logger.info(f"Navigating to Menu tab: {menu_tab_url}")

            # Scroll to the Menu tab and click it
            self.driver.execute_script(
                "arguments[0].scrollIntoView(true);", menu_tab)
            menu_tab.click()

            # Define a dictionary to store menu data from all tabs
            menu_data = {}

            # Define the tabs to navigate (Set Menu, Food, Drink, Lunch)
            menu_tabs = {
                "Set_Menu": "li.rstdtl-navi__sublist-item a[href*='/party/']",
                "Food": "li.rstdtl-navi__sublist-item a[href*='/dtlmenu/']",
                "Drink": "li.rstdtl-navi__sublist-item a[href*='/nu/drink/']",
                "Lunch": "li.rstdtl-navi__sublist-item a[href*='/dtlmenu/nu]"
            }

            for tab_name, tab_selector in menu_tabs.items():
                try:
                    # logger.info(f"Looking for {tab_name} tab using selector: {tab_selector}")

                    # Locate the item count for the tab
                    item_count_element = self.driver.find_element(
                        By.CSS_SELECTOR, f"{tab_selector} .rstdtl-navi__sublist-item-count em"
                    )
                    item_count = int(item_count_element.text.strip())
                    # logger.info(f"Item count for {tab_name}: {item_count}")
                    if item_count == 0:
                        logger.info(
                            f"Skipping {tab_name} tab as item count is 0.")
                        menu_data[tab_name] = []
                        continue

                    # Wait for the tab link to appear
                    tab_link = WebDriverWait(self.driver, self.wait_menu).until(
                        EC.presence_of_element_located(
                            (By.CSS_SELECTOR, tab_selector))
                    )

                    # Log the href attribute of the tab
                    tab_url = tab_link.get_attribute('href')
                    # logger.info(f"Navigating to {tab_name} tab: {tab_url}")

                    # Scroll to the tab link and click it
                    self.driver.execute_script(
                        "arguments[0].scrollIntoView(true);", tab_link)
                    tab_link.click()

                    # logger.info(f"Clicked on {tab_name} tab.")

                    # Delay to allow the page to load
                    time.sleep(1)

                    if tab_name == "Set_Menu":
                        # Wait for the Set Menu section to load
                        WebDriverWait(self.driver, self.wait_menu).until(
                            EC.presence_of_element_located(
                                (By.CLASS_NAME, "rstdtl-course-list"))
                        )
                    else:
                        # Wait for the menu section to load
                        WebDriverWait(self.driver, self.wait_menu).until(
                            EC.presence_of_element_located(
                                (By.CLASS_NAME, "rstdtl-menu-lst"))
                        )

                    # Call the appropriate method based on the tab
                    if tab_name == "Set_Menu":
                        tab_menu_data = self.extract_set_menu()
                    elif tab_name == "Food":
                        tab_menu_data = self.extract_food_menu()
                    elif tab_name == "Drink":
                        tab_menu_data = self.extract_drink_menu()
                    elif tab_name == "Lunch":
                        tab_menu_data = self.extract_lunch_menu()
                    else:
                        tab_menu_data = []

                    # logger.info(f"Extracted {len(tab_menu_data)} items from {tab_name} tab.")
                    menu_data[tab_name] = tab_menu_data

                except Exception as e:
                    logger.warning(
                        f"Failed to navigate to {tab_name} tab or extract data: e")
                    menu_data[tab_name] = []

            return menu_data
        except Exception as e:
            logger.error(f"Failed to navigate to Menu tab: e")
            return {}

    def extract_food_menu(self):
        try:
            # Extract food menu items
            food_menu_data = self.driver.execute_script(
                "return Array.from(document.querySelectorAll('.rstdtl-menu-lst__contents')).map(item => {"
                "    const title = item.querySelector('.rstdtl-menu-lst__menu-title')?.innerText.trim() || null;"
                "    const price = item.querySelector('.rstdtl-menu-lst__price')?.innerText.trim() || null;"
                "    const description = item.querySelector('.rstdtl-menu-lst__ex')?.innerText.trim() || null;"
                "    const image_src = item.querySelector('.rstdtl-menu-lst__img img')?.getAttribute('src')?.replace('150x150_square_', '') || null;"
                "    return { title, price, description, image_src };"
                "}).filter(item => item.image_src !== null);"
            )

            # logger.info(f"Extracted {len(food_menu_data)} food menu items with valid images.")
            return food_menu_data

        except Exception as e:
            logger.error(f"Failed to extract food menu data: e")
            return []

    def extract_set_menu(self):
        try:
            # Extract set menu items
            set_menu_data = self.driver.execute_script(
                "return Array.from(document.querySelectorAll('.rstdtl-course-list')).map(menu => {"
                "    return {"
                "        title: menu.querySelector('.rstdtl-course-list__course-title-text')?.innerText.trim() || null,"
                "        description: menu.querySelector('.rstdtl-course-list__desc')?.innerText.trim() || null,"
                "        price: menu.querySelector('.rstdtl-course-list__price-num em')?.innerText.trim() || null,"
                "        link: menu.querySelector('.rstdtl-course-list__target')?.getAttribute('href') || null,"
                "        image_src: menu.querySelector('.rstdtl-course-list__img-target img')?.getAttribute('src')?.replace('200x200_square_', '') || null,"
                "        available_time: menu.querySelector('.rstdtl-course-list__course-rule dd')?.innerText.trim() || null"
                "    };"
                "}).filter(item => item.image_src !== null);"
            )

            logger.info(
                f"Extracted {len(set_menu_data)} set menu items with valid images.")
            return set_menu_data

        except Exception as e:
            logger.error(f"Failed to extract set menu data: e")
            return []

    def extract_drink_menu(self):
        try:
            # Extract drink menu items
            drink_menu_data = self.driver.execute_script(
                "return Array.from(document.querySelectorAll('.rstdtl-menu-lst__contents')).map(item => {"
                "    const title = item.querySelector('.rstdtl-menu-lst__menu-title')?.innerText.trim() || null;"
                "    const price = item.querySelector('.rstdtl-menu-lst__price')?.innerText.trim() || null;"
                "    const description = item.querySelector('.rstdtl-menu-lst__ex')?.innerText.trim() || null;"
                "    const image_src = item.querySelector('.rstdtl-menu-lst__img img')?.getAttribute('src')?.replace('150x150_square_', '') || null;"
                "    return { title, price, description, image_src };"
                "}).filter(item => item.image_src !== null);"
            )

            logger.info(
                f"Extracted {len(drink_menu_data)} drink menu items with valid images.")
            return drink_menu_data

        except Exception as e:
            logger.error(f"Failed to extract drink menu data: e")
            return []

    def extract_lunch_menu(self):
        try:
            # Extract lunch menu items
            lunch_menu_data = self.driver.execute_script(
                "return Array.from(document.querySelectorAll('.rstdtl-menu-lst__contents')).map(item => {"
                "    const title = item.querySelector('.rstdtl-menu-lst__menu-title')?.innerText.trim() || null;"
                "    const price = item.querySelector('.rstdtl-menu-lst__price')?.innerText.trim() || null;"
                "    const description = item.querySelector('.rstdtl-menu-lst__ex')?.innerText.trim() || null;"
                "    const image_src = item.querySelector('.rstdtl-menu-lst__img img')?.getAttribute('src')?.replace('150x150_square_', '') || null;"
                "    return { title, price, description, image_src };"
                "}).filter(item => item.image_src !== null);"
            )

            logger.info(
                f"Extracted {len(lunch_menu_data)} lunch menu items with valid images.")
            return lunch_menu_data

        except Exception as e:
            logger.error(f"Failed to extract lunch menu data: e")
            return []

    def parse_restaurant_information(self):
        try:
            # Wait for the restaurant information section to load
            WebDriverWait(self.driver, 15).until(
                EC.presence_of_element_located(
                    (By.CLASS_NAME, 'rstinfo-table__table'))
            )

            # Extract all tables under the "Details", "Seats/facilities", "Menu", and "Feature - Related Information" sections
            tables_data = self.driver.execute_script(
                "return Array.from(document.querySelectorAll('h4.rstinfo-table__title')).map(title => {"
                "    const section = title.innerText.trim();"
                "    const rows = Array.from(title.nextElementSibling.querySelectorAll('tr')).map(row => {"
                "        const field = row.querySelector('th')?.innerText.trim() || null;"
                "        const value = row.querySelector('td span, td div span, td p')?.innerText.trim() || null;"
                "        return { field, value };"
                "    });"
                "    return { section, rows };"
                "});"
            )

            # Organize data into separate lists for each section
            details = []
            seats_facilities = []
            menu = []
            feature_related_info = []

            for table in tables_data:
                section = table['section']
                rows = table['rows']

                if section == "Details":
                    details = rows
                elif section == "Seats/facilities":
                    seats_facilities = rows
                elif section == "Menu":
                    menu = rows
                elif "Feature" in section:  # Matches "Feature - Related Information"
                    feature_related_info = rows

            # logger.info(f"Extracted {len(details)} details items.")
            # logger.info(f"Extracted {len(seats_facilities)} seats/facilities items.")
            # logger.info(f"Extracted {len(menu)} menu items.")
            # logger.info(f"Extracted {len(feature_related_info)} feature-related information items.")

            # Return all extracted data as a dictionary
            return {
                "details": details,
                "seats_facilities": seats_facilities,
                "menu": menu,
                "feature_related_info": feature_related_info
            }

        except Exception as e:
            logger.error(f"Failed to retrieve restaurant information: e")
            return {
                "details": [],
                "seats_facilities": [],
                "menu": [],
                "feature_related_info": []
            }

    def navigate_and_get_interior_official_photos(self):
        try:
            # Wait for the Photos link in the navigation menu to appear
            photos_link = WebDriverWait(self.driver, self.wait_photos).until(
                EC.presence_of_element_located(
                    (By.CSS_SELECTOR, "li#rdnavi-photo a.mainnavi"))
            )

            # Log the href attribute of the Photos link
            photos_url = photos_link.get_attribute('href')
            # logger.info(f"Navigating to Photos page: {photos_url}")

            # Click the Photos link
            self.driver.execute_script(
                "arguments[0].scrollIntoView(true);", photos_link)
            photos_link.click()

            # Wait for the Photos page to load
            WebDriverWait(self.driver, self.wait_photos).until(
                EC.presence_of_element_located((By.CLASS_NAME, "rstdtl-photo"))
            )

            # Navigate to the Interior tab
            interior_tab_link = self.driver.find_element(
                By.CSS_SELECTOR, "a[href*='/dtlphotolst/3/smp2/']")
            interior_tab_url = interior_tab_link.get_attribute('href')
            # logger.info(f"Navigating to Interior tab: {interior_tab_url}")
            self.driver.execute_script(
                "arguments[0].click();", interior_tab_link)

            # Wait for the Interior tab to load
            WebDriverWait(self.driver, self.wait_photos).until(
                EC.presence_of_element_located(
                    (By.CLASS_NAME, "rstdtl-thumb-list"))
            )

            # Extract only the Interior Photos URLs
            interior_photo_urls = self.driver.execute_script(
                """
                const officialPhotosSection = Array.from(document.querySelectorAll('.c-heading3.rstdtl-photo__title'))
                    .find(title => title.innerText.trim() === 'Official photos');
                if (officialPhotosSection) {
                    const photoList = officialPhotosSection.nextElementSibling;
                    return Array.from(photoList.querySelectorAll('.rstdtl-thumb-list__item img')).map(img => {
                        let src = img.getAttribute('src');
                        return src.replace('150x150_square_', '');
                    });
                }
                return [];
                """
            )

            # logger.info(f"Extracted {len(interior_photo_urls)} interior photo URLs.")
            return interior_photo_urls

        except Exception as e:
            logger.error(f"Failed to navigate to Interior Photos page: e")
            return []

    def closed(self, reason):
        self.logger.info(f"Spider closing with reason: {reason}")
        try:
            if hasattr(self, 'driver') and self.driver:
                self.driver.quit()
                self.logger.info("WebDriver closed successfully")
        except Exception as e:
            self.logger.error(f"Error closing WebDriver: {e}")
        
        # Log final statistics
        if os.path.exists(self.restore_file):
            with open(self.restore_file, 'r') as f:
                data = json.load(f)
                pending = len(data.get('pending_urls', []))
                scraped = len(data.get('scraped_urls', []))
                failed = len(data.get('failed_urls', []))
                self.logger.info(f"Final stats - Scraped: {scraped}, Failed: {failed}, Pending: {pending}")
        
        elapsed = (datetime.now() - self.start_time).total_seconds()
        self.logger.info(f"Total scraping time: {elapsed:.2f} seconds")
        
    
    def get_review_count(self, response):
        """Extract the review count from the navigation menu"""
        try:
            # Method 1: Try to get from the main navigation Reviews link
            review_count_text = response.css('#rdnavi-review .rstdtl-navi__total-count em::text').get()
            
            if review_count_text:
                return int(review_count_text.strip())
            
            # Method 2: Try to get from the sublist Reviews link  
            review_count_text = response.css('#review .rstdtl-navi__sublist-item-count em::text').get()
            
            if review_count_text:
                return int(review_count_text.strip())
            
            # Method 3: Try alternative selector for review count
            review_count_text = response.css('a[href*="dtlrvwlst"] em::text').get()
            
            if review_count_text:
                return int(review_count_text.strip())
                
            self.logger.warning("Could not find review count")
            return 0
            
        except Exception as e:
            self.logger.error(f"Error extracting review count: {e}")
            return 0

    def parse_reviews(self, response):
        # Extract review details
        reviews = []
        for review in response.css('div.rvw-item.js-rvw-item-clickable-area'):
            # reviewer details
            reviewer_img = review.css('.rvw-item__rvwr-img::attr(src)').get()
            if reviewer_img and not reviewer_img.endswith('rvwr_nophoto_70x70_re1.gif'):
                reviewer_img = reviewer_img.replace('70x70_', '')
            reviewer = {
                'name': review.css('.rvw-item__rvwr-name::text').get(),
                'profile': review.css('.rvw-item__rvwr-name::attr(href)').get(),
                'img': reviewer_img,
                'location': review.css('.rstdtl-rvw-country__name::text').get(),
                'follower_count': review.css('.rvw-item__folower-num::text').get(),
                'review_count': review.css('.rvw-item__rvwr-num::text').get(),
            }

            # Check for 'View all reviews' link for this reviewer
            view_all_reviews_url = review.css(
                'p.review-link-detail a.c-link-circle.js-link-bookmark-detail::attr(data-detail-url)').get()
            reviewer_reviews = []
            if view_all_reviews_url:
                try:
                    self.driver.get(view_all_reviews_url)
                    WebDriverWait(self.driver, self.wait_menu).until(
                        EC.presence_of_element_located(
                            (By.CSS_SELECTOR, 'div.rvw-item--rvwdtl'))
                    )
                    detail_body = self.driver.page_source
                    detail_response = HtmlResponse(
                        self.driver.current_url, body=detail_body, encoding='utf-8')
                    # Each review is inside a .rvw-item__review-contents-wrap > .rvw-item__review-contents
                    for wrap in detail_response.css('div.rvw-item__review-contents-wrap'):
                        rvw = wrap.css('div.rvw-item__review-contents')
                        if not rvw:
                            continue
                        rvw = rvw[0]
                        visit_date = rvw.css(
                            '.rvw-item__date-inner > span:first-child::text').get()
                        visit_count = rvw.css(
                            '.rvw-item__count-num::text').get()
                        overall_rating = rvw.css(
                            '.rvw-item__single-ratings-total .c-rating-v3__val--strong::text').get()
                        meal_type = rvw.css(
                            '.rvw-item__single-ratings-total .c-rating-v3__time::attr(aria-label)').get()
                        price = rvw.css(
                            '.rvw-item__payment-amount-delimiter::text').get()
                        # Sub-ratings
                        sub_ratings = []
                        for sub in rvw.css('.c-rating-detail__item'):
                            label = sub.css('span::text').get()
                            value = sub.css('strong::text').get()
                            sub_ratings.append(
                                {'label': label, 'value': value})
                        # Images
                        review_images = []
                        for img in rvw.css('ul.rvw-photo__list li.rvw-photo__list-item'):
                            img_url = img.css('a.js-imagebox-trigger::attr(href)').get()
                            if img_url:
                                review_images.append(img_url.replace('640x640_rect_', ''))
                        # Comment (not always present)
                        review_comment = rvw.css(
                            'div.rvw-item__rvw-comment p::text').get()
                        # Title (optional)
                        review_title = rvw.css(
                            'p.rvw-item__title strong::text').get()
                        reviewer_reviews.append({
                            'review_title': review_title,
                            'review_comment': review_comment,
                            'review_images': review_images,
                            'visit_date': visit_date,
                            'visit_count': visit_count,
                            'overall_rating': overall_rating,
                            'meal_type': meal_type,
                            'price_per_person': price,
                            'sub_ratings': sub_ratings,
                        })
                except Exception as e:
                    logger.warning(
                        f"Failed to fetch all reviews for reviewer at {view_all_reviews_url}: {e}")
            else:
                # If no 'View all reviews', try to extract all reviews from the current review block
                for wrap in review.css('div.rvw-item__review-contents-wrap'):
                    rvw = wrap.css('div.rvw-item__review-contents')
                    if not rvw:
                        continue
                    rvw = rvw[0]
                    visit_date = rvw.css(
                        '.rvw-item__date-inner > span:first-child::text').get()
                    visit_count = rvw.css('.rvw-item__count-num::text').get()
                    overall_rating = rvw.css(
                        '.rvw-item__single-ratings-total .c-rating-v3__val--strong::text').get()
                    meal_type = rvw.css(
                        '.rvw-item__single-ratings-total .c-rating-v3__time::attr(aria-label)').get()
                    price = rvw.css(
                        '.rvw-item__payment-amount-delimiter::text').get()
                    price_per_person = rvw.css(
                        '.rvw-item__payment-amount-people::text').get()
                    # Sub-ratings
                    sub_ratings = []
                    for sub in rvw.css('.c-rating-detail__item'):
                        label = sub.css('span::text').get()
                        value = sub.css('strong::text').get()
                        sub_ratings.append({'label': label, 'value': value})
                    # Images
                    review_images = [
                        img.css(
                            'a.js-imagebox-trigger::attr(href)').get().replace('640x640_rect_', '')
                        for img in rvw.css('ul.rvw-photo__list li.rvw-photo__list-item')
                        if img.css('a.js-imagebox-trigger::attr(href)').get()
                    ]
                    # Comment (not always present)
                    review_comment = rvw.css(
                        'div.rvw-item__rvw-comment p::text').get()
                    # Title (optional)
                    review_title = rvw.css(
                        'p.rvw-item__title strong::text').get()
                    reviewer_reviews.append({
                        'review_title': review_title,
                        'review_comment': review_comment,
                        'review_images': review_images,
                        'visit_date': visit_date,
                        'visit_count': visit_count,
                        'overall_rating': overall_rating,
                        'meal_type': meal_type,
                        'price': price,
                        'price_per_person': price_per_person,
                        'sub_ratings': sub_ratings,
                    })
            reviews.append({
                'reviewer': reviewer,
                'reviews': reviewer_reviews if reviewer_reviews else None
            })
        return reviews


def run_scraping_background(base_url: str, num_restaurants: int, resume: bool):
    """Background function to run scraping process"""
    global scraping_task_status
    
    # Set up detailed logging for debugging
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
    logger = logging.getLogger(__name__)
    
    try:
        output_file = "restaurants.json"
        restore_file = "scrape_restore.json"
        
        # If not resuming, clear restore and output files
        if not resume:
            logger.info("Not resuming - clearing existing files")
            if os.path.exists(restore_file):
                os.remove(restore_file)
                logger.info(f"Removed {restore_file}")
            if os.path.exists(output_file):
                os.remove(output_file)
                logger.info(f"Removed {output_file}")
        else:
            logger.info("Resuming from existing state")

        # Run Scrapy in a subprocess to avoid Twisted reactor conflicts
        logger.info("Running Scrapy in subprocess to avoid reactor conflicts")
        
        # Construct the scrapy command
        cmd = [
            sys.executable, "-m", "scrapy", "crawl", "restaurants",
            "-a", f"num_restaurants={num_restaurants}",
            "-a", f"start_urls={base_url}",
            "-a", f"resume={resume}",
            "-o", output_file
        ]
        
        logger.info(f"Executing command: {' '.join(cmd)}")
        
        # Run the command with extended timeout for long scraping operations (24 hours)
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=86400)  # 24 hour timeout
        
        logger.info(f"Scrapy subprocess completed with return code: {result.returncode}")
        if result.stdout:
            logger.info(f"Subprocess stdout: {result.stdout[-500:]}")  # Last 500 chars
        if result.stderr:
            logger.warning(f"Subprocess stderr: {result.stderr[-500:]}")  # Last 500 chars
            
    except subprocess.TimeoutExpired:
        logger.error("Scraping process timed out after 24 hours")
    except Exception as e:
        logger.error(f"Exception in background scraping: {str(e)}", exc_info=True)
    finally:
        # Reset the scraping status
        scraping_task_status["is_running"] = False
        scraping_task_status["process"] = None
        logger.info("Background scraping task completed")


@app.get("/download/{filename}", summary="Download output file", description="Download a file generated by the scraper.")
def download_file(filename: str):
    file_path = os.path.join(os.getcwd(), filename)
    if os.path.exists(file_path):
        return FileResponse(file_path, filename=filename, media_type='application/json')
    return JSONResponse(content={"error": "File not found."}, status_code=404)


@app.get("/scrape", summary="Scrape Tabelog restaurants", description="Scrape Tabelog restaurants with given base_url and num_restaurants.")
def scrape(
    base_url: str = Query(..., description="Base URL to start scraping from (e.g. https://tabelog.com/en/tokyo/A1303/rstLst/?LstSitu=2)"), 
    num_restaurants: int = Query(2, description="Number of restaurants to scrape"), 
    resume: bool = Query(False, description="Resume from last restore point (True) or start from beginning (False)"),
    background: bool = Query(True, description="Run scraping in background for long operations (recommended for large num_restaurants)")
    ):

    global scraping_task_status
    
    # Set up detailed logging for debugging
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
    logger = logging.getLogger(__name__)
    
    logger.info(f"Starting scrape with base_url: {base_url}, num_restaurants: {num_restaurants}, resume: {resume}, background: {background}")
    
    # Check if a scraping task is already running
    if scraping_task_status["is_running"]:
        elapsed = (datetime.now() - scraping_task_status["start_time"]).total_seconds()
        return JSONResponse(content={
            "error": "A scraping task is already running",
            "current_task": scraping_task_status["current_params"],
            "elapsed_time_seconds": elapsed,
            "message": "Use /status endpoint to check progress, or /stop to cancel current task"
        }, status_code=409)
    
    # For large numbers of restaurants or if background is requested, run in background
    if background or num_restaurants > 10:
        logger.info("Starting background scraping task")
        
        # Update scraping status
        scraping_task_status["is_running"] = True
        scraping_task_status["start_time"] = datetime.now()
        scraping_task_status["current_params"] = {
            "base_url": base_url,
            "num_restaurants": num_restaurants,
            "resume": resume
        }
        
        # Start background thread
        thread = threading.Thread(
            target=run_scraping_background,
            args=(base_url, num_restaurants, resume)
        )
        thread.daemon = True
        thread.start()
        
        return {
            "message": "Scraping started in background",
            "task_id": "background_scrape",
            "parameters": scraping_task_status["current_params"],
            "start_time": scraping_task_status["start_time"].isoformat(),
            "note": "Use /status endpoint to check progress. This may take several hours for large numbers of restaurants."
        }
    
    # For small numbers, run synchronously (original behavior)
    output_file = "restaurants.json"
    restore_file = "scrape_restore.json"
    
    # If not resuming, clear restore and output files
    if not resume:
        logger.info("Not resuming - clearing existing files")
        if os.path.exists(restore_file):
            os.remove(restore_file)
            logger.info(f"Removed {restore_file}")
        if os.path.exists(output_file):
            os.remove(output_file)
            logger.info(f"Removed {output_file}")
    else:
        logger.info("Resuming from existing state")

    # Run Scrapy in a subprocess to avoid Twisted reactor conflicts
    logger.info("Running Scrapy in subprocess to avoid reactor conflicts")
    
    # Construct the scrapy command
    cmd = [
        sys.executable, "-m", "scrapy", "crawl", "restaurants",
        "-a", f"num_restaurants={num_restaurants}",
        "-a", f"start_urls={base_url}",
        "-a", f"resume={resume}",
        "-o", output_file
    ]
    
    logger.info(f"Executing command: {' '.join(cmd)}")
    
    try:
        # Run the command with shorter timeout for synchronous execution
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=1800)  # 30 minute timeout for sync
        
        logger.info(f"Scrapy subprocess completed with return code: {result.returncode}")
        if result.stdout:
            logger.info(f"Subprocess stdout: {result.stdout[-500:]}")  # Last 500 chars
        if result.stderr:
            logger.warning(f"Subprocess stderr: {result.stderr[-500:]}")  # Last 500 chars
        
        # Check the results
        pending, scraped, failed = [], [], []
        if os.path.exists(restore_file):
            logger.info(f"Reading restore file: {restore_file}")
            with open(restore_file, "r") as f:
                data = json.load(f)
                pending = data.get("pending_urls", [])
                scraped = data.get("scraped_urls", [])
                failed = data.get("failed_urls", [])
            logger.info(f"Status - Pending: {len(pending)}, Scraped: {len(scraped)}, Failed: {len(failed)}")
        else:
            logger.warning(f"Restore file {restore_file} not found")

        if os.path.exists(output_file):
            # Check if output file has data
            with open(output_file, 'r') as f:
                content = f.read().strip()
                if content and content != "[]":
                    download_url = f"/download/{output_file}"
                    logger.info(f"Scraping complete, output file created: {output_file}")
                    return {"message": "Scraping complete.", "download_url": download_url, "scraped": len(scraped), "failed": len(failed)}
                else:
                    logger.warning("Output file exists but is empty or contains empty array")
        
        if pending:
            logger.info("Scraping incomplete - pending URLs remain")
            return {"message": "Scraping in progress or incomplete.", "pending": len(pending), "scraped": len(scraped), "failed": len(failed)}
        elif result.returncode != 0:
            logger.error(f"Scrapy process failed with return code {result.returncode}")
            return JSONResponse(content={"error": f"Scraping process failed: {result.stderr}"}, status_code=500)
        else:
            logger.error("No data scraped and no output file created")
            return JSONResponse(content={"error": "No data scraped. Check logs for details."}, status_code=500)
            
    except subprocess.TimeoutExpired:
        logger.error("Scraping process timed out after 30 minutes")
        return JSONResponse(content={
            "error": "Scraping process timed out", 
            "message": "For large scraping jobs, use background=true parameter"
        }, status_code=500)
    except Exception as e:
        logger.error(f"Exception in scrape endpoint: {str(e)}", exc_info=True)
        return JSONResponse(content={"error": f"Internal server error: {str(e)}"}, status_code=500)


@app.get("/status", summary="Get scraping status", description="Get the current scraping progress, including scraped, failed, pending, and total restaurants, plus recent log entries.")
def get_status():
    global scraping_task_status
    
    restore_file = "scrape_restore.json"
    status_log = "scrape_status.log"
    output_file = "restaurants.json"
    
    scraped = []
    failed = []
    pending = []
    
    if os.path.exists(restore_file):
        with open(restore_file, "r") as f:
            data = json.load(f)
            scraped = data.get("scraped_urls", [])
            failed = data.get("failed_urls", [])
            pending = data.get("pending_urls", [])
    
    total = len(scraped) + len(failed) + len(pending)
    
    # Get recent logs
    last_logs = []
    if os.path.exists(status_log):
        with open(status_log, "r") as f:
            lines = f.readlines()
            last_logs = lines[-10:]
    
    # Check if output file exists and has content
    output_file_info = {
        "exists": os.path.exists(output_file),
        "size_bytes": os.path.getsize(output_file) if os.path.exists(output_file) else 0,
        "last_modified": datetime.fromtimestamp(os.path.getmtime(output_file)).isoformat() if os.path.exists(output_file) else None
    }
    
    # Background task status
    task_info = {
        "is_running": scraping_task_status["is_running"],
        "start_time": scraping_task_status["start_time"].isoformat() if scraping_task_status["start_time"] else None,
        "elapsed_seconds": (datetime.now() - scraping_task_status["start_time"]).total_seconds() if scraping_task_status["start_time"] else None,
        "current_params": scraping_task_status["current_params"]
    }
    
    # Calculate progress percentage
    progress_percentage = 0
    if task_info["is_running"] and task_info["current_params"]:
        target_restaurants = task_info["current_params"]["num_restaurants"]
        if target_restaurants > 0:
            progress_percentage = (len(scraped) / target_restaurants) * 100
            progress_percentage = min(100, progress_percentage)  # Cap at 100%
    
    # Estimate remaining time (rough calculation)
    estimated_completion = None
    if task_info["is_running"] and len(scraped) > 0 and task_info["elapsed_seconds"]:
        avg_time_per_restaurant = task_info["elapsed_seconds"] / len(scraped)
        remaining_restaurants = len(pending)
        if remaining_restaurants > 0:
            estimated_seconds_remaining = avg_time_per_restaurant * remaining_restaurants
            estimated_completion = (datetime.now() + timedelta(seconds=estimated_seconds_remaining)).isoformat()
    
    return {
        "scraping_counts": {
            "scraped": len(scraped),
            "failed": len(failed),
            "pending": len(pending),
            "total": total
        },
        "progress": {
            "percentage": round(progress_percentage, 2),
            "estimated_completion": estimated_completion
        },
        "background_task": task_info,
        "output_file": output_file_info,
        "recent_activity": {
            "last_10_logs": [l.strip() for l in last_logs],
            "log_file_exists": os.path.exists(status_log)
        },
        "urls": {
            "scraped_urls": scraped[-5:] if len(scraped) > 5 else scraped,  # Show last 5 for brevity
            "failed_urls": failed,
            "pending_urls": pending[:5] if len(pending) > 5 else pending  # Show first 5 pending
        }
    }


@app.post("/stop", summary="Stop background scraping", description="Stop any currently running background scraping task.")
def stop_scraping():
    global scraping_task_status
    
    if not scraping_task_status["is_running"]:
        return {"message": "No scraping task is currently running"}
    
    # Note: This is a simple flag. In a production system, you might want to 
    # implement actual process termination for more immediate stopping
    scraping_task_status["is_running"] = False
    scraping_task_status["process"] = None
    
    return {
        "message": "Background scraping task stop requested",
        "note": "The task may take a few moments to fully stop and clean up"
    }


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000, reload=False)
    logger.info("FastAPI server started on http://localhost:8000")
    logger.info("You can access the API at http://localhost:8000/docs")
