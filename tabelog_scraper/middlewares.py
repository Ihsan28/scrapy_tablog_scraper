import time
import random
from scrapy.downloadermiddlewares.retry import RetryMiddleware
from scrapy.utils.response import response_status_message

class CustomRetryMiddleware(RetryMiddleware):
    def process_response(self, request, response, spider):
        if response.status == 429:
            spider.logger.info(f"Received 429 for {request.url}, waiting before retry")
            # Wait 30-90 seconds for 429 errors
            wait_time = random.uniform(30, 90)
            time.sleep(wait_time)
            
            reason = response_status_message(response.status)
            return self._retry(request, reason, spider) or response
        
        return super().process_response(request, response, spider)