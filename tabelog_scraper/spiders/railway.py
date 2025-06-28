import json
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import scrapy
import logging
import time

# Set Selenium logging level to WARNING
logging.getLogger('selenium').setLevel(logging.WARNING)


class RailwaySpider(scrapy.Spider):
    name = "railway"
    allowed_domains = ["eticket.railway.gov.bd"]

    def __init__(self, from_city="Dhaka", to_city="Rajshahi", seat_class="SNIGDHA", date="05-Jun-2025", *args, **kwargs):
        super(RailwaySpider, self).__init__(*args, **kwargs)
        self.from_city = from_city
        self.to_city = to_city
        self.seat_class = seat_class
        self.date = date

        self.start_urls = [
            f'https://eticket.railway.gov.bd/booking/train/search?fromcity={self.from_city}&tocity={self.to_city}&doj={self.date}&class={self.seat_class}'
        ]

        # Selenium WebDriver setup
        chrome_options = Options()
        # Uncomment next line to run in headless mode
        # chrome_options.add_argument("--headless")
        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_argument("--no-sandbox")

        # Initialize Chrome WebDriver
        self.driver = webdriver.Chrome(options=chrome_options)
        self.wait_general = 10  # General wait time for loading elements

    def parse(self, response):
        # Open the page with Selenium
        self.driver.get(response.url)

        results = []
        try:
            # Wait until the element is fully loaded using explicit wait
            WebDriverWait(self.driver, self.wait_general).until(
                EC.presence_of_element_located((By.CLASS_NAME, "single-trip-wrapper"))
            )
            
            time.sleep(2)

            # Extract all train elements
            trains = self.driver.find_elements(By.CLASS_NAME, "single-trip-wrapper")

            for train in trains:
                # Expand collapsed section if needed
                # try:
                #     train_name = train.find_element(By.TAG_NAME, 'h2').text.strip()
                #     logging.debug(f"Processing train: {train_name}")
                #     logging.debug(train.text)
                #     trip_collapsible = train.find_element(By.CLASS_NAME, "trip-collapsible trip-div trip-collapsed")
                #     is_expanded = ('trip-collapsible trip-div trip-collapsed' in trip_collapsible.get_attribute("class"))

                #     logging.debug(f"{train_name} Trip {is_expanded} collapsible class: {trip_collapsible.get_attribute('class')}")
                # except Exception:
                #     is_expanded = False

                # # If NOT expanded, click to expand
                # if is_expanded:
                #     try:
                #         collapse_button = train.find_element(By.CLASS_NAME, "trip-collapse-btn")
                #         collapse_button.click()
                #         time.sleep(0.5)  # Wait for content to expand
                #     except Exception as e:
                #         self.logger.warning(f"Could not expand collapsed item: {e}")
                #         continue

                # Extract train name
                train_name = train.find_element(By.TAG_NAME, 'h2').text.strip()

                # Extract journey details (from, to, start time, end time, duration)
                journey_start_elem = train.find_element(By.CLASS_NAME, "journey-start")
                journey_start_time = journey_start_elem.find_element(By.CLASS_NAME, "journey-date").text.strip()
                journey_start_location = journey_start_elem.find_element(By.CLASS_NAME, "journey-location").text.strip()

                journey_end_elem = train.find_element(By.CLASS_NAME, "journey-end")
                journey_end_time = journey_end_elem.find_element(By.CLASS_NAME, "journey-date").text.strip()
                journey_end_location = journey_end_elem.find_element(By.CLASS_NAME, "journey-location").text.strip()

                journey_duration = train.find_element(By.CLASS_NAME, "journey-duration").text.strip()

                # Find seat class details
                seat_classes = train.find_elements(By.CLASS_NAME, "single-seat-class")
                class_list = []
                for seat_class in seat_classes:
                    seat_type = seat_class.find_element(By.CLASS_NAME, "seat-class-name").text.strip()
                    fare = seat_class.find_element(By.CLASS_NAME, "seat-class-fare").text.strip()
                    available_tickets = seat_class.find_element(By.CLASS_NAME, "all-seats").text.strip()
                    class_list.append({
                        "class": seat_type,
                        "fare": fare,
                        "available_tickets": available_tickets,
                    })

                # Append all collected details
                results.append({
                    "train_name": train_name,
                    "from": journey_start_location,
                    "to": journey_end_location,
                    "start_time": journey_start_time,
                    "end_time": journey_end_time,
                    "duration": journey_duration,
                    "classes": class_list,
                })

        except Exception as e:
            self.logger.error(f"Error occurred: {e}")

        finally:
            # Close the browser after scraping
            self.driver.quit()

        # Write results to a JSON file
        self.save_to_json(results)

        # Yield all collected results
        for item in results:
            yield item

    def save_to_json(self, data):
        """Save the scraped data to a JSON file."""
        try:
            with open("train_data.json", "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=4)
            self.logger.info("Data successfully written to train_data.json")
        except Exception as e:
            self.logger.error(f"Failed to write data to JSON file: {e}")