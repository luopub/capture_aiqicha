import time
import scrapy
from pydispatch import dispatcher
from scrapy import signals
from scrapy.utils.project import get_project_settings
from urllib.parse import urljoin

from ..browser_wrapper import BrowserWrapperMixin, SeleniumRequest


class CaptureSimpleSpider(scrapy.Spider, BrowserWrapperMixin):
    name = 'capture_simple'
    allowed_domains = ['aiqicha.baidu.com']
    start_urls = ['http://aiqicha.baidu.com']

    def __init__(self, **kwargs):
        super().__init__(name=self.name, **kwargs)
        BrowserWrapperMixin.__init__(self)

        self.companies = self.get_company_list()
        self.index = 0

        self.browser = self.connect_browser()

        # 设置信号量，当收到spider_closed信号时，调用mySpiderCloseHandle方法，关闭chrome
        dispatcher.connect(receiver=self.mySpiderCloseHandle,
                           signal=signals.spider_closed
                           )

    def get_company_list(self):
        settings = get_project_settings()
        path = settings.get('COMPANY_LIST_FILE')
        with open(path, encoding='utf8') as f:
            companies = list(filter(lambda x: x, map(lambda x: x.strip(), f.read().split('\n'))))

        return companies

    def mySpiderCloseHandle(self, spider):
        pass

    def error(self, spider):
        pass

    def start_requests(self):
        # Must get the page at front tab, otherwise, the button is hidden and can't be clicked
        # self.switch_to_front_window()

        yield SeleniumRequest(
            url=self.start_urls[0],
            wait_xpaths=['//button[@class="search-btn"]'],
            callback=self.parse_home_page,
            errback=self.error
        )

    def get_next_company_query_request(self):
        if self.index < len(self.companies):
            company = self.companies[self.index]
            print(f'Capturing: {company}')
            url = f'https://aiqicha.baidu.com/s?q={company}&t=0'
            self.index += 1
            return SeleniumRequest(
                url=url,
                wait_xpaths=['//button[@class="search-btn"]'],
                callback=self.parse_query_result,
                meta={'company': company},
                errback=self.error
            )
        return None

    def parse_home_page(self, response):
        request = self.get_next_company_query_request()
        if request:
            yield request

    def parse_query_result(self, response):
        href = response.xpath('//div[@class="company-list"]//div[@class="card"][1]//a/attribute::href').get()
        if href and href.strip():
            yield SeleniumRequest(
                url=urljoin(self.start_urls[0], href.strip()),
                wait_xpaths=['//button[@class="search-btn"]'],
                callback=self.parse_company,
                meta={'company': response.meta['company']},
                errback=self.error
            )
        else:
            request = self.get_next_company_query_request()
            if request:
                yield request

    def parse_company(self, response):
        try:
            create_date = response.xpath('//td[text()="成立日期"]/following-sibling::td[1]/text()').get()
            if create_date:
                create_date = create_date.strip()

            brief = response.xpath(
                '//div[@class="header-content"]/div[@class="content-info"]/div[@class="content-info-child-brief"]//div/text()').get().strip()
            if brief:
                brief = brief.strip()

            stock = response.xpath('//div[@class="tags-list"]/span[contains(@class,"zx-ent-tag")][contains(text(), "A股")]/text()').get()
            if stock:
                stock = stock.strip()

            if not stock:
                stock = response.xpath('//div[@class="tags-list"]/span[contains(@class,"zx-ent-tag")][contains(text(), "新三板")]/text()').get()
                if stock:
                    stock = stock.strip()

            if not stock:
                stock = response.xpath('//div[@class="tags-list"]/span[contains(@class,"zx-ent-tag")][contains(text(), "IPO")]/text()').get()
                if stock:
                    stock = stock.strip()

            if response.xpath('//div[@class="tags-list"]//button//span[contains(text(),"注销")]').get():
                zhuxiao = 1
            else:
                zhuxiao = 0

            yield {
                'company': response.meta['company'],
                'create_date': create_date,
                'stock': stock,
                'brief': brief,
                'zhuxiao': zhuxiao
            }
        except Exception as e:
            print(f'公司解析错误：{response.url}, {str(e)}')

        request = self.get_next_company_query_request()
        if request:
            yield request
