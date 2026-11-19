import os
import sys

os.environ.setdefault("AIOT_NO_AUTOAPP", "1")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
