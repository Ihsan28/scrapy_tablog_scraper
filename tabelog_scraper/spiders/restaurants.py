from venv import logger

import scrapy
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from scrapy.http import HtmlResponse
import time
import logging

# Set Selenium logging level to WARNING
logging.getLogger('selenium').setLevel(logging.WARNING)

# Set Scrapy logging level to WARNING
logging.getLogger('scrapy').setLevel(logging.WARNING)

class RestaurantsSpider(scrapy.Spider):
    name = "restaurants"
    allowed_domains = ["tabelog.com"]
    start_urls = ['https://tabelog.com/en/rstLst/?utf8=%E2%9C%93&svd=&svt=1900&svps=2&vac_net=1&pcd=41']

    def __init__(self, num_restaurants=1, *args, **kwargs):
        super(RestaurantsSpider, self).__init__(*args, **kwargs)
        # Desired number of restaurant links
        self.num_restaurants = int(num_restaurants)
        self.collected_links = 0  # Counter for collected links

        # Timing variables
        self.total_scraping_time = 0
        self.processed_links = 0

        chrome_options = Options()
        # chrome_options.add_argument("--headless")  # Uncomment if you don't need GUI
        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_argument("--no-sandbox")
        self.driver = webdriver.Chrome(options=chrome_options)
        self.driver.maximize_window()

        # Wait times for different operations
        self.wait_general = 10
        self.wait_modal = 5
        self.wait_menu = 10
        self.wait_photos = 10

    def parse(self, response):
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
        restaurant_links = response.css(
            'a.list-rst__rst-name-target::attr(href)').getall()

        print(f"Found {len(restaurant_links)} restaurant links on the page.")
        print(restaurant_links)
        # just for debugging, append all links to a file and also the number of links found
        with open('restaurant_links.txt', 'a') as f:
            f.write(f"Found {self.collected_links} restaurant links on the previous.\n")
            for link in restaurant_links:
                f.write(link + '\n')
        # Log the number of links found
        self.logger.info(
            f"Found {len(restaurant_links)} restaurant links on the page.")

        # Process links in batches of 5
        batch_size = 5
        for i in range(0, len(restaurant_links), batch_size):
            batch_links = restaurant_links[i:i + batch_size]

            for link in batch_links:
                if self.collected_links < self.num_restaurants:
                    self.collected_links += 1
                    yield scrapy.Request(link, callback=self.parse_detail)
                else:
                    break

            # Stop processing if the desired number of links is reached
            if self.collected_links >= self.num_restaurants:
                break

        # Handle next page if more links are needed
        if self.collected_links < self.num_restaurants:
            next_page = response.css(
                'a.c-pagination__arrow--next::attr(href)').get()
            if next_page:
                print(f"Found next page: {next_page}")
                yield scrapy.Request(response.urljoin(next_page), callback=self.parse)

    def parse_detail(self, response):
        start_time = time.time()  # Start timing

        self.driver.get(response.url)
        body = self.driver.page_source
        response = HtmlResponse(
            self.driver.current_url, body=body, encoding='utf-8', request=response.request)

        headline, full_description = self.get_headline_description(response)
        specialities = self.fetch_specialities_data()
        setmenu = self.navigate_to_menu()
        restaurant_information = self.parse_restaurant_information()
        interior_photos = self.navigate_and_get_interior_official_photos()

        data = {
            "editorial_overview": {
                "headline": headline,
                "description": full_description,
            },
            "review_rating": {},
            "specialities": specialities,
            "menu": setmenu,
            "restaurant_information": restaurant_information,
            "interior_photos": interior_photos,
            'url': response.url
        }

        try:
            # Additional scraping logic for ratings (if applicable)
            ratings_url = response.css('a#rating::attr(href)').get()
            if ratings_url:
                self.driver.get(ratings_url)
                WebDriverWait(self.driver, 3).until(EC.presence_of_element_located(
                    (By.CSS_SELECTOR, 'div.ratings-contents')))
                body = self.driver.page_source
                ratings_response = HtmlResponse(self.driver.current_url, body=body, encoding='utf-8',
                                                request=response.request)
                
                # logger.info("Extracting average ratings...")

                # Extract Average Ratings
                average_ratings = {}

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
                rating_distribution = []

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
                                f"Error extracting distribution item {index}: e")

                # Add extracted data to review_rating
                data["review_rating"] = {
                    "average_ratings": average_ratings,
                    "rating_distribution": rating_distribution
                }

                # Log the final structured data
                # logger.info(f"Final extracted ratings data: {data['review_rating']}")
        except Exception as e:
            self.logger.error(f"Error navigating to Ratings page: e")

        # Yield the final result
        yield data

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
                EC.presence_of_all_elements_located((By.CLASS_NAME, "js-kodawari-cassete"))
            )

            if not specialities_section:
                logger.warning("No specialities section found!")
                return []

            # logger.info(f"Found {len(specialities_section)} specialities.")

            # Click on the first speciality item to open the modal
            first_item = specialities_section[0]
            self.driver.execute_script("arguments[0].scrollIntoView(true);", first_item)
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
                    EC.element_to_be_clickable((By.CLASS_NAME, "js-modal-close"))
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
                    self.driver.execute_script("arguments[0].click();", overlay)
                    WebDriverWait(self.driver, self.wait_modal).until(
                        EC.invisibility_of_element(overlay))
                    logger.info("Overlay closed.")
            except Exception as e:
                logger.info("No overlay found or already handled.")

            # Log the href attribute of the Menu tab
            menu_tab_url = menu_tab.get_attribute('href')
            logger.info(f"Navigating to Menu tab: {menu_tab_url}")

            # Scroll to the Menu tab and click it
            self.driver.execute_script("arguments[0].scrollIntoView(true);", menu_tab)
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
                        logger.info(f"Skipping {tab_name} tab as item count is 0.")
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
                    self.driver.execute_script("arguments[0].scrollIntoView(true);", tab_link)
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
                    logger.warning(f"Failed to navigate to {tab_name} tab or extract data: e")
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

            logger.info(f"Extracted {len(drink_menu_data)} drink menu items with valid images.")
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
        self.driver.quit()
