from typing import Any
import time
import datetime
import logging
import re
import os
from dataclasses import dataclass
from functools import wraps
import json
import traceback

from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support.select import Select
from selenium.webdriver.common.keys import Keys
from selenium import webdriver


from database.model import (
    ENUM_RUN_TYPE_NAME,
    # ENUM_SCHEDULE_CLOCK_TYPE_NAME,
)

from database.schemas import M_WORK_SCHEDULE_TYPES


DEFAULT_MSG = "現場規定により在宅勤務いたします。ご確認お願い致します。"


def sleep(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        time.sleep(3)
        r = func(*args, **kwargs)
        time.sleep(3)
        return r
    return wrapper


class Clocker:
    def __init__(
            self,
            email: str,
            password: str,
            schedule_type: str = None,
            # schedule_type: ENUM_SCHEDULE_CLOCK_TYPE_NAME = None,
            gps: str = None,
            runner: ENUM_RUN_TYPE_NAME = None,
            day2apply: str = None,
            details: M_WORK_SCHEDULE_TYPES = None,
            debug: bool = False) -> None:
        self.email = email
        self.password = password

        # run clockin/out if schedule_type is not assgined
        if schedule_type is None:
            latitude, longitude = gps.split(",")
            self.latitude = float(latitude)
            self.longitude = float(longitude)
        else:
            try:
                assert day2apply is not None
                assert details is not None
            except AssertionError:
                raise ValueError("day2apply or details cannot be None")

        self.schedule_type = schedule_type
        # self.telework = telework
        if details is not None:
            if (details.msg is None) or (details.msg == ""):
                details.msg = DEFAULT_MSG
        # self.msg = msg
        self.debug = debug
        if day2apply is not None:
            try:
                assert re.match(r"^\d{4}-\d{2}-\d{2}$", day2apply)
            except AssertionError:
                raise ValueError(
                    r"day2apply not match ^\d{4}-\d{2}-\d{2}$: "
                    f"'{day2apply}'")
        self.day2apply = day2apply
        self.details = details
        self.runner = self.__transfer_enum_run_type(runner)

    def __repr__(self) -> str:
        return self.__str__()

    def __str__(self) -> str:
        return (
            f"<Clocker user: {self.email}, "
            f"schedule_type: {self.schedule_type}, "
            f"details: [{self.details}], "
            f"day2apply: {self.day2apply}, "
            f"task: {self.runner}>"
        )

    def __call__(self, logger, *args: Any, **kwds: Any) -> None:
        try:
            logger.info(f"RUNNING: {self.__str__()}")
            self.init_driver(logger)
            self.login()
            logger.info(f"[S] {self.runner}")
            getattr(self, self.runner)()
            logger.info(f"[E] {self.runner}")
        except Exception:
            logger.error(traceback.format_exc())
            raise
        finally:
            try:
                self.driver.close()
            except Exception as e:
                logger.error(f"Error when dispose driver: {e}")

    def __transfer_enum_run_type(self, enum_type: ENUM_RUN_TYPE_NAME):
        if enum_type == ENUM_RUN_TYPE_NAME.cin:
            return "clock_in"
        elif enum_type == ENUM_RUN_TYPE_NAME.cout:
            return "clock_out"
        else:
            return "apply_telework"


    def init_driver(self, logger):
        logger.info("[S] init driver")
        options = Options()

        options.add_argument("--dns-prefetch-disable")
        options.add_argument("--start-maximized")
        options.add_argument("--enable-automation")
        options.add_argument("--headless")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-infobars")
        options.add_argument('--disable-extensions')
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--disable-browser-side-navigation")
        options.add_argument("--disable-gpu")
        options.add_argument('--ignore-certificate-errors')
        options.add_argument('--ignore-ssl-errors')
        prefs = {"profile.default_content_setting_values.notifications" : 2}
        options.add_experimental_option("prefs", prefs)
        options.headless = True

        options.add_argument(
            '--user-agent=Mozilla/5.0 (iPhone; CPU iPhone OS 13_3_1 '
            'like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) '
            'Mobile/15E148 [FBAN/FBIOS;FBDV/iPhone9,1;FBMD/iPhone;'
            'FBSN/iOS;FBSV/13.3.1;FBSS/2;FBID/phone;FBLC/en_US;'
            'FBOP/5;FBCR/]')
        
        logger.info("    do init driver")
        self.driver = webdriver.Remote(
            command_executor = os.environ["SELENIUM_URL"],
            options = options,
            # enable_cdp_events=True,
            # headless=True,
        )
        self.driver.implicitly_wait(10)
        logger.info("[E] init driver")

        logger.info("[S] Access mypage")
        self.driver.get('https://attendance.moneyforward.com/my_page')


        def send(driver, cmd, params={}):
            """Supprt for remote driver.
            Works like `driver.execute_cdp_cmd`
            """
            resource = ("/session/%s/chromium/send_command_and_get_result" %
                        driver.session_id)
            url = driver.command_executor._url + resource
            body = json.dumps({'cmd': cmd, 'params': params})
            response = driver.command_executor._request('POST', url, body)
            return response.get('value')

        send(self.driver, "Browser.grantPermissions", {
                "origin": "https://attendance.moneyforward.com/my_page",
                "permissions": ["geolocation"]
            }
        )

        # GPS geolocation setup
        if self.runner != "apply_telework":
            send(self.driver, "Emulation.setGeolocationOverride", {
                    "latitude": self.latitude,
                    "longitude": self.longitude,
                    "accuracy": 100,
                },
        )
        logger.info("[E] Access mypage")

    @staticmethod
    def today() -> str:
        return datetime.datetime.today().strftime("%Y-%m-%d")

    def login(self):
        self.driver.find_element(
            By.CLASS_NAME, "attendance-button-mfid").click()
        self.driver.find_element(
            By.ID, "mfid_user[email]").send_keys(self.email)
        self.driver.find_element(By.ID, "submitto").click()
        self.driver.find_element(
            By.ID, "mfid_user[password]").send_keys(self.password)
        self.driver.find_element(By.ID, "submitto").click()

    # @sleep
    # def open_edit_panel(self):
    #     """Must work with `set_telework` or `set_scheduled_time`
    #     """
    #     # open edit panel
    #     self.driver.find_element(
    #         By.XPATH,
    #         '//button[@data-url="/my_page/attendances/'
    #         f'{Clocker.today()}/edit" and @data-action="click->side-'
    #         'modal-link#openSideModal"]').click()

    @sleep
    def commit_edit_panel(self):
        """Must work with `set_telework` or `set_scheduled_time`
        """
        self.driver.find_element(
            By.XPATH, "//input[@name='commit']").click()

    def set_telework(self):
        revealed = self.driver.find_element(
            By.XPATH,
            "//input[@class='custom-counter-input "
            "attendance-input-field-small']"
        )
        wait = WebDriverWait(self.driver, timeout=5)
        wait.until(lambda _: revealed.is_displayed())
        revealed.send_keys("1")

    @sleep
    def set_scheduled_time(self):
        def clear_and_input(elem, s: str):
            # Keys.CONTROL + "a may not work in mac
            # elem.send_keys(Keys.CONTROL + "a")
            if s is None:
                return

            for _ in range(10):
                elem.send_keys(Keys.BACKSPACE)
            # time.sleep(3)
            elem.send_keys(s)

        # set schedule clock type
        revealed = self.driver.find_element(
            By.XPATH,
            "//select[@name='workflow_request"
            "[workflow_request_content_attendance_attributes]"
            "[workflow_request_content_attendance_attendance_schedule_attributes]"
            "[attendance_schedule_template_id]']",
        )

        wait = WebDriverWait(self.driver, timeout=5)
        wait.until(lambda _: revealed.is_displayed())
        select = Select(revealed)

        # select the defined schdule type
        opts = [x.text for x in select.options]
        if self.schedule_type in opts:
            select.select_by_visible_text(self.schedule_type)
            return

        # select 通常勤務 at first to create break_in/out field
        select.select_by_visible_text("通常勤務")
        # select custom defined schdule type and enter values
        select.select_by_value("")
        # select.select_by_index(0)

        # enter schedule clock-in time
        elem_in = self.driver.find_element(
            By.XPATH,
            "//input[@name='workflow_request"
            "[workflow_request_content_attendance_attributes]"
            "[workflow_request_content_attendance_attendance_schedule_attributes]"
            "[start_time]']"
        )

        clear_and_input(elem_in, str(self.details.clockin))

        # enter schedule clock-out time
        elem_out = self.driver.find_element(
            By.XPATH,
            "//input[@name='workflow_request"
            "[workflow_request_content_attendance_attributes]"
            "[workflow_request_content_attendance_attendance_schedule_attributes]"
            "[end_time]']"
        )
        clear_and_input(elem_out, str(self.details.clockout))

        # enter schedule break-in time
        elem_out = self.driver.find_element(
            By.XPATH,
            "//input[@name='workflow_request"
            "[workflow_request_content_attendance_attributes]"
            "[workflow_request_content_attendance_break_time_schedules_attributes]"
            "[0][start_time]']"
        )
        clear_and_input(elem_out, str(self.details.breakin))

        # enter schedule break-out time
        elem_out = self.driver.find_element(
            By.XPATH,
            "//input[@name='workflow_request"
            "[workflow_request_content_attendance_attributes]"
            "[workflow_request_content_attendance_break_time_schedules_attributes]"
            "[0][end_time]']"
        )
        clear_and_input(elem_out, str(self.details.breakout))

    @sleep
    def clock_in(self):
        revealed = self.driver.find_element(
            By.XPATH,
            "//div[@class='clock_in'][1]/button"
        )
        wait = WebDriverWait(self.driver, timeout=10)
        wait.until(lambda _: revealed.is_enabled())
        revealed.click()

    @sleep
    def apply_telework(self):
        url = ("https://attendance.moneyforward.com/"
               "my_page/workflow_requests"
               f"/attendances/new?date={self.day2apply}")
        self.driver.get(url)
        if self.details.telework:
            self.set_telework()
        self.set_scheduled_time()
        elem = self.driver.find_element(By.ID, "workflow_request_comment")
        elem.send_keys(self.details.msg)
        self.commit_edit_panel()

    @sleep
    def clock_out(self):
        revealed = self.driver.find_element(
            By.XPATH,
            "//div[@class='clock_out'][1]/button"
        )
        wait = WebDriverWait(self.driver, timeout=10)
        wait.until(lambda _: revealed.is_enabled())
        revealed.click()

    # @sleep
    # def break_in(self):
    #     self.driver.find_element(
    #         By.XPATH, "//div[@class='start_break'][1]/button").click()

    # @sleep
    # def break_out(self):
    #     self.driver.find_element(
    #         By.XPATH, "//div[@class='end_break'][1]/button").click()
