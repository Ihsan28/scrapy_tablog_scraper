import scrapy
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from scrapy.http import HtmlResponse
import time

class RestaurantsSpider(scrapy.Spider):
    name = "restaurants"
    allowed_domains = ["tabelog.com"]
    start_urls = ['https://tabelog.com/tokyo/rstLst/']

    def __init__(self, num_restaurants=100, *args, **kwargs):
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
        time.sleep(3)

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


    def parse_detail(self, response):
        self.driver.get(response.url)
        time.sleep(3)
        body = self.driver.page_source
        response = HtmlResponse(self.driver.current_url, body=body, encoding='utf-8', request=response.request)

        yield {
            "eidtorial_overview":{
                "headline": response.css('h3.pr-comment-title.js-pr-title::text').get(),
            },

            'url': response.url
        }

    def closed(self, reason):
        self.driver.quit()
