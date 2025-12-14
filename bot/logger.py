from typing import Union
import rich
from rich.traceback import Traceback
from rich.text import Text
import inspect
import os
import datetime
import traceback
import functools
import asyncio

enable_file_logging = False  # 全局开关，控制是否启用文件日志记录

class Logger:
    def __init__(self, log_file='log.txt'):
        self.enable_file_logging = enable_file_logging
        self.log_file = log_file if self.enable_file_logging else None

        self.timestamp_format = "%Y-%m-%d %H:%M:%S"
        self.timestamp_color = "#96E6E3"
        self.module_color = "#FFA500"
        self.linemo_color = "#EFADFF"
        self.debug_color = "#A4A4A4"
        self.info_color = "#CDCDCD"
        self.warning_color = "#FFDD00"
        self.error_color = "#FF9A26"
        self.critical_color = "#FF4500"
        
    def _get_caller_info(self):
        stack = inspect.stack()
        if len(stack) > 2:
            caller_frame = stack[2] # 原始调用者的帧
            module = inspect.getmodule(caller_frame[0])
            module_name = module.__name__ if module else 'UnknownModule'
            
            # 如果是 __main__，使用文件名代替
            if module_name == "__main__":
                module_name = os.path.splitext(os.path.basename(caller_frame.filename))[0]
            
            # 加上函数名
            func_name = caller_frame.function
            if func_name and func_name != "<module>":
                module_name = f"{module_name}.{func_name}"

            line_number = caller_frame.lineno
            return module_name, line_number
        return 'UnknownModule', 0
    
    def _log(self, level, message, color, module_name=None, line_number=None):
        timestamp = datetime.datetime.now().strftime(self.timestamp_format)
        if module_name is None or line_number is None:
            module_name, line_number = self._get_caller_info()
        
        prefix = (
            f"[{self.timestamp_color}]{timestamp}[/] | "
            f"[{self.module_color}]{module_name}[/]:"
            f"[{self.linemo_color}]{line_number}[/] | "
            f"[{color}]{level:<9}[/] | "
        )
        
        text_log = Text.from_markup(prefix)
        text_log.append(Text.from_ansi(message))
        
        rich.print(text_log)
        
        if self.enable_file_logging and self.log_file:
            with open(self.log_file, 'a', encoding='utf-8') as f:
                f.write(f"{timestamp} {module_name}:{line_number} {level} {message}\n")

    def debug(self, message):
        module_name, line_number = self._get_caller_info()
        self._log("debug", message, self.debug_color, module_name, line_number)
    def info(self, message):
        module_name, line_number = self._get_caller_info()
        self._log("info", message, self.info_color, module_name, line_number)
    def warning(self, message):
        module_name, line_number = self._get_caller_info()
        self._log("warning", message, self.warning_color, module_name, line_number)
    def error(self, message):
        module_name, line_number = self._get_caller_info()
        self._log("error", message, self.error_color, module_name, line_number)
    def critical(self, message):
        module_name, line_number = self._get_caller_info()
        self._log("critical", message, self.critical_color, module_name, line_number)
    def exception(self, message):
        module_name, line_number = self._get_caller_info()
        self._log("exception", message, self.error_color, module_name, line_number)
        rich.print(Traceback())
        
        if self.enable_file_logging and self.log_file:
            exc_info = traceback.format_exc()
            full_message = f"{message}\n{exc_info}"
            with open(self.log_file, 'a', encoding='utf-8') as f:
                f.write(f"{datetime.datetime.now().strftime(self.timestamp_format)} {self._get_caller_info()[0]}:{self._get_caller_info()[1]} EXCEPTION {full_message}\n")

    # 同/异步tback装饰器
    def logger_catch(self, func):
        if asyncio.iscoroutinefunction(func):
            @functools.wraps(func)
            async def async_wrapper(*args, **kwargs):
                try:
                    return await func(*args, **kwargs)
                except Exception as e:
                    self.exception(f"[TomatOS/logger_catch]执行{func.__name__}时发生异常: {e}")
                    raise
            return async_wrapper
        else:
            @functools.wraps(func)
            def sync_wrapper(*args, **kwargs):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    self.exception(f"[TomatOS/logger_catch]执行{func.__name__}时发生异常: {e}")
                    raise
            return sync_wrapper


    @staticmethod
    def color_to_ansi(fcolor: Union[str, tuple, None] = (255, 255, 255), bcolor: Union[str, tuple, None] = None, text="", style=""):
        # rgb数组
        def rgb_to_ansi(r, g, b, is_background=False):
            code = 48 if is_background else 38
            return f"\033[{code};2;{r};{g};{b}m"
        # 色号转rgb
        def hex_to_rgb(hex_color):
            hex_color = hex_color.lstrip('#')
            return tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))
        
        if isinstance(fcolor, str):
            fcolor = hex_to_rgb(fcolor)
        if isinstance(bcolor, str):
            bcolor = hex_to_rgb(bcolor)
        ansi_sequence = ""
        if fcolor:
            ansi_sequence += rgb_to_ansi(*fcolor, is_background=False)
        if bcolor:
            ansi_sequence += rgb_to_ansi(*bcolor, is_background=True)
        style_codes = {"bold": "1", "underline": "4", "reversed": "7"}
        for s in style.split(","):
            if s in style_codes:
                ansi_sequence += f"\033[{style_codes[s]}m"
        reset_sequence = "\033[0m"
        return f"{ansi_sequence}{text}{reset_sequence}"
        


logger = Logger()

def test_logger():
    logger.debug("This is a debug message.")
    logger.info("This is an info message.")
    logger.warning("This is a warning message.")
    logger.error("This is an error message.")
    logger.critical("This is a critical message.")
    # 带颜色的字的测试
    colored_text = Logger.color_to_ansi(fcolor="#FF5733", bcolor=None, text="This is a colored text!", style="bold,underline")
    logger.info(colored_text)
    try:
        1 / 0
    except ZeroDivisionError:
        logger.exception("An exception occurred.")
    @logger.logger_catch
    def test_function(x, y):
        return x / y
    @logger.logger_catch
    async def test_async_function(x, y):
        return x / y
    test_function(10, 2)
    try:
        test_function(10, 0)
    except ZeroDivisionError:
        pass
    asyncio.run(test_async_function(10, 2))
    try:
        asyncio.run(test_async_function(10, 0))
    except ZeroDivisionError:
        pass
    

if __name__ == "__main__":
    test_logger()
