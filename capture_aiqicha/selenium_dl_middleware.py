from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
import random
from selenium.webdriver.common.action_chains import ActionChains
from selenium.common.exceptions import NoSuchElementException, TimeoutException
from scrapy.http import HtmlResponse
import time


def get_move_track(width):
    # 拖动图片
    # 根据偏移量获取移动轨迹
    # 一开始加速，然后减速，生长曲线，且加入点随机变动
    # 移动轨迹
    track = []
    # 当前位移
    current = 0
    # 减速阈值
    mid = width * 3 / 4
    # 间隔时间
    t = 0.1
    v = 0
    while current < width:
        if current < mid:
            a = random.randint(5, 10)  #(2, 3)
        else:
            a = - random.randint(10, 15)  # (6, 7)
        v0 = v
        # 当前速度
        v = v0 + a * t
        # 移动距离
        move = v0 * t + 1 / 2 * a * t * t
        # 当前位移
        current += move
        track.append(round(move))
    return track


class SeleniumMiddleware():
    # Middleware中会传递进来一个spider，这就是我们的spider对象，从中可以获取__init__时的chrome相关元素
    def process_request(self, request, spider):
        def check_xpath_appears(browser, xpath):
            try:
                element = spider.browser.find_element_by_xpath(xpath)
                return element
            except NoSuchElementException:
                return None

        # 依靠meta中的标记，来决定是否需要使用selenium来爬取
        use_selenium = request.meta.get('use_selenium', False)
        if use_selenium:
            # print(f"chrome is getting page with selenium: {request.url}")
            try:
                spider.browser.get(request.url)
                start_time = time.time()
                wait_xpath = request.meta.get('wait_xpath', None)
                if wait_xpath:
                    wait_xpaths = [wait_xpath]
                else:
                    wait_xpaths = request.meta.get('wait_xpaths', [])

                loop = True
                while wait_xpaths and loop:
                    for wait_xpath in wait_xpaths:
                        if time.time() - start_time > spider.timeout:
                            raise TimeoutException('Timeout waiting response')
                        time.sleep(1)

                        # 搜索框是否出现
                        # if wait_xpath:
                        # WebDriverWait(spider.browser, 30).until(EC.presence_of_element_located((By.XPATH, wait_xpath)))
                        if check_xpath_appears(spider.browser, wait_xpath):
                            loop = False
                            break

                        # Sometimes, the slider to check robots will appear
                        robot_slider = check_xpath_appears(spider.browser, '//span[@id="nc_1_n1z"]')
                        if robot_slider:
                            time.sleep(1)
                            track = get_move_track(300)
                            ActionChains(spider.browser).click_and_hold(robot_slider).perform()
                            for x in track:
                                ActionChains(spider.browser).move_by_offset(xoffset=x, yoffset=random.randint(-1, 1)).perform()
                                # time.sleep(0.01)
                            time.sleep(1)
                            ActionChains(spider.browser).release().perform()

                        # Some times, the check will fail, then refresh it and try again
                        capture_refresh_anchor = check_xpath_appears(spider.browser, '//a[@href="javascript:noCaptcha.reset(1)"]')
                        if capture_refresh_anchor:
                            # If found it need refresh, then reload the page and try again
                            spider.browser.execute_script('document.location.reload();')

                time.sleep(2)
                # Do some operations after the page is loaded
                post_op = request.meta.get('post_op', None)
                if post_op:
                    post_op(request)
            except Exception as e:
                print(f"chrome getting page error, Exception = {e}")
                return HtmlResponse(url=request.url, status=500, request=request)
            else:
                return HtmlResponse(url=request.url,
                                    body=spider.browser.page_source,
                                    request=request,
                                    encoding='utf-8',
                                    status=200)
