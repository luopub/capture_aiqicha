
from scrapy.cmdline import execute

import sys
import os

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

execute(r'scrapy crawl capture_simple -o ..\simple.csv'.split(' '))
