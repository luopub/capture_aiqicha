import time

from scrapy.http import HtmlResponse
from scrapy.http import Request
from scrapy.utils.project import get_project_settings
from selenium.common.exceptions import NoSuchElementException
from selenium.common.exceptions import NoSuchWindowException
from selenium.common.exceptions import MoveTargetOutOfBoundsException
from selenium.webdriver.common.action_chains import ActionChains
import copy
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.desired_capabilities import DesiredCapabilities


def connect_browser(driver_path, addr, port, page_load_strategy):
    """
    Connect to browser that's already started by hand, maybe on another machine
    If pageLoadStrategy is set to 'none', browser.get(url) will return immediately without waiting page ready
    """

    desired_capabilities = copy.deepcopy(DesiredCapabilities.CHROME)
    desired_capabilities['pageLoadStrategy'] = page_load_strategy

    chrome_options = Options()
    chrome_options.add_experimental_option("debuggerAddress", f"{addr}:{port}")

    driver = webdriver.Chrome(driver_path, chrome_options=chrome_options, desired_capabilities=desired_capabilities)
    return driver


class SeleniumRequest(Request):

    def __init__(self, url, callback=None, method='GET', headers=None, body=None,
                 cookies=None, meta=None, encoding='utf-8', priority=0,
                 dont_filter=False, errback=None, flags=None, cb_kwargs=None, wait_xpath=None, wait_xpaths=None):
        if meta:
            meta['use_selenium'] = True
        else:
            meta = {'use_selenium': True}
        meta['wait_xpath'] = wait_xpath
        meta['dont_redirect'] = True

        super().__init__(url, callback=callback, method=method, headers=headers, body=body,
                         cookies=cookies, meta=meta, encoding=encoding, priority=priority,
                         dont_filter=dont_filter, errback=errback, flags=flags, cb_kwargs=cb_kwargs)


class BrowserWrapperMixin:
    def __init__(self, min_windows=0):
        self.browser = None
        self.min_windows = min_windows

    def connect_browser(self, page_load_strategy='normal'):
        settings = get_project_settings()
        self.browser = connect_browser(settings.get('CHROMEDRIVER_PATH'), settings.get('CHROME_ADDR'), settings.get('CHROME_PORT'), page_load_strategy)
        return self.browser

    def switch_to_front_window(self):
        # Sometimes, we need to ensure current wind is in front
        try:
            self.browser.switch_to_window(self.browser.window_handles[0])
        except NoSuchWindowException as e:
            pass

    def get_response_from_browser(self, meta):
        # This may happen accidentally
        if not self.browser.current_url:
            return None

        if not self.browser.current_url.startswith('http://') and not self.browser.current_url.startswith('https://'):
            return None

        request = Request(
            url=self.browser.current_url,
            meta=meta
        )
        response = HtmlResponse(url=self.browser.current_url,
                                body=self.browser.page_source,
                                request=request,
                                encoding='utf-8',
                                status=200)

        return response

    def check_page_ready(self, xpath):
        try:
            element = self.browser.find_element_by_xpath(xpath)
            return element
        except NoSuchElementException:
            return False

    def wait_page_ready(self, xpath, timeout=60):
        time_start = time.time()
        while not self.check_page_ready(xpath):
            time.sleep(1)
            # Wait at most 1 minute, so that to avoid extension suspend forever
            if time.time() - time_start > timeout:
                break

    def scroll_to_bottom(self):
        print('Doing post operation for detail page')
        # scroll to bottom to enable reviews to be loaded
        prev_scrollY = self.browser.execute_script('return window.scrollY;')
        while True:
            # Continuously scroll down until end
            self.browser.execute_script('window.scrollBy(0, 800)')
            time.sleep(1)
            scrollY = self.browser.execute_script('return window.scrollY;')
            if scrollY == prev_scrollY:
                break
            prev_scrollY = scrollY

    def get_element_from_shadow_root(self, element_paths):
        script = f"""
            root = document;
            element_root_paths = {element_paths};
            for (let i = 0; i < element_root_paths.length; i++) {{
                element = root.querySelector(element_root_paths[i]);
                if (i < element_root_paths.length-1) {{
                    root = element.root
                }}
            }}
            return element;
        """
        return self.browser.execute_script(script)

    def get_image_radio_button(self, enable):
        if enable:
            radio_option_id = 'enabledRadioOption'
        else:
            radio_option_id = 'disabledRadioOption'

        return self.get_element_from_shadow_root(f"""
            [
                'settings-ui',
                '#main',
                'settings-basic-page',
                '#basicPage settings-section settings-privacy-page',
                '#pages settings-subpage settings-category-default-radio-group',
                '#settingsCategoryDefaultRadioGroup #{radio_option_id}',
                '#radioCollapse'
            ]
        """)

    def enable_image(self, enable=None):
        if enable is None:
            return

        # Must get the page at front tab, otherwise, the button is hidden and can't be clicked
        self.switch_to_front_window()

        self.browser.get('chrome://settings/content/images')
        time.sleep(2)
        try:
            element = self.get_image_radio_button(enable)

            ActionChains(self.browser).move_to_element(element).click().perform()

            time.sleep(1)
        except Exception as e:
            pass

    def get_extension_toggle_button(self):

        return self.get_element_from_shadow_root(f"""
            [
                'extensions-manager',
                '#viewManager extensions-detail-view',
                '#container .page-content #enable-section .layout.horizontal #enableToggle',
            ]
        """)

    def reenable_extension(self, extension_id):

        # Must get the page at front tab, otherwise, the button is hidden and can't be clicked
        self.switch_to_front_window()

        self.browser.get(f'chrome://extensions/?id={extension_id}')
        time.sleep(2)
        try:
            element = self.get_extension_toggle_button()

            status = element.get_attribute('aria-pressed')

            if status == 'true':
                # If already enable, disable it first
                ActionChains(self.browser).move_to_element(element).click().perform()
                time.sleep(2)

            while element.get_attribute('aria-pressed') == 'false':
                # Loop in case some problem happens, that the enable button is failed to be toggled on
                ActionChains(self.browser).move_to_element(element).click().perform()
                time.sleep(1)

            time.sleep(1)

            return True
        except Exception as e:
            pass

        return False

    def prepare_windows(self):
        if self.min_windows > 0:
            self.open_blank_windows(total_count=self.min_windows)

    def open_blank_windows(self, new_count=0, total_count=1):
        # As javascript is unable to be executed to open new browser window, use a page click to do it.
        curr_count = len(self.browser.window_handles)
        dest_count = max(curr_count + new_count, total_count)
        if curr_count >= dest_count:
            return

        html_path = get_project_settings().get('OPEN_BLANK_PAGE')
        if html_path:
            for _ in range(dest_count-curr_count):
                self.switch_to_front_window()
                self.browser.get(html_path)
                while True:
                    try:
                        time.sleep(0.3)
                        anchor = self.browser.find_element_by_id('newtab')
                        anchor.click()
                        break
                    except NoSuchElementException as e:
                        pass

    @staticmethod
    def get_track(distance):      # distance为传入的总距离
        # 移动轨迹
        track = []
        # 当前位移
        current = 0
        # 减速阈值
        mid = distance * 4 / 5
        # 计算间隔
        t = 0.2
        # 初速度
        v = 1

        while current < distance:
            if current < mid:
                # 加速度为2
                a = 4
            else:
                # 加速度为-2
                a = -3
            v0 = v
            # 当前速度
            v = v0 + a * t
            # 移动距离
            move = v0 * t + 1 / 2 * a * t * t
            # 当前位移
            current += move
            # 加入轨迹
            track.append(round(move))
        return track

    def move_to_gap(self, slider, tracks):  # slider是要移动的滑块,tracks是要传入的移动轨迹
        """
        https://www.jianshu.com/p/f1fef22a14f4
        """
        try:
            ActionChains(self.browser).click_and_hold(slider).perform()
            for x in tracks:
                ActionChains(self.browser).move_by_offset(xoffset=x, yoffset=0).perform()
            time.sleep(0.5)
            ActionChains(self.browser).release().perform()
        except MoveTargetOutOfBoundsException as e:
            pass
