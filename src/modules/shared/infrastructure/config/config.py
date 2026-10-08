import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    BMS_MAC_ADDRESS = os.getenv("BMS_MAC_ADDRESS", "AA:BB:CC:DD:EE:FF")
    BMS_SLAVE_ADDR = int(os.getenv("BMS_SLAVE_ADDR", "1"))
    BMS_POLLING_INTERVAL = int(os.getenv("BMS_POLLING_INTERVAL", "5"))
    FLASK_PORT = int(os.getenv("FLASK_PORT", "8000"))
    FLASK_DEBUG = os.getenv("FLASK_DEBUG", "False").lower() == "true"
    DATA_DIR = "data"
    # Charge/balance cycle log (written by the server while polling).
    BALANCE_LOG_ENABLED = os.getenv("BALANCE_LOG_ENABLED", "true").lower() == "true"
    BALANCE_LOG_INTERVAL = int(os.getenv("BALANCE_LOG_INTERVAL", "30"))
    BALANCE_LOG_RETENTION_H = float(os.getenv("BALANCE_LOG_RETENTION_H", "48"))
    BALANCE_LOG_FILE = os.getenv("BALANCE_LOG_FILE", "balance_cycle.csv")

config = Config()
