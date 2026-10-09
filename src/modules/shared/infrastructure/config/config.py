import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    # No default: the real BMS MAC must come from the environment/.env so the
    # repository never carries a specific device address.
    BMS_MAC_ADDRESS = os.getenv("BMS_MAC_ADDRESS", "")
    BMS_SLAVE_ADDR = int(os.getenv("BMS_SLAVE_ADDR", "1"))
    BMS_POLLING_INTERVAL = int(os.getenv("BMS_POLLING_INTERVAL", "5"))
    FLASK_PORT = int(os.getenv("FLASK_PORT", "8000"))
    FLASK_DEBUG = os.getenv("FLASK_DEBUG", "False").lower() == "true"
    # Auto-reload on code changes without exposing the interactive debugger.
    FLASK_RELOAD = os.getenv("FLASK_RELOAD", "False").lower() == "true"
    DATA_DIR = "data"
    # Charge/balance cycle log (written by the server while polling).
    BALANCE_LOG_ENABLED = os.getenv("BALANCE_LOG_ENABLED", "true").lower() == "true"
    BALANCE_LOG_INTERVAL = int(os.getenv("BALANCE_LOG_INTERVAL", "30"))
    BALANCE_LOG_RETENTION_H = float(os.getenv("BALANCE_LOG_RETENTION_H", "48"))
    BALANCE_LOG_FILE = os.getenv("BALANCE_LOG_FILE", "balance_cycle.csv")
    # Low-SOC browser push alerts.
    VAPID_SUBJECT = os.getenv("VAPID_SUBJECT", "mailto:admin@localhost")
    VAPID_KEYS_FILE = os.getenv("VAPID_KEYS_FILE", "vapid_keys.json")
    PUSH_SUBSCRIBE_FILE = os.getenv("PUSH_SUBSCRIBE_FILE", "push_subscriptions.json")
    ALERT_CONFIG_FILE = os.getenv("ALERT_CONFIG_FILE", "alert_config.json")
    SOC_ALERT_PCT = float(os.getenv("SOC_ALERT_PCT", "10"))
    SOC_ALERT_HYSTERESIS = float(os.getenv("SOC_ALERT_HYSTERESIS", "5"))
    # High-SOC browser push alerts (battery nearly full).
    SOC_HIGH_ALERT_PCT = float(os.getenv("SOC_HIGH_ALERT_PCT", "95"))
    SOC_HIGH_HYSTERESIS = float(os.getenv("SOC_HIGH_HYSTERESIS", "5"))
    ALERT_CHECK_INTERVAL = int(os.getenv("ALERT_CHECK_INTERVAL", "5"))
    ALERT_STALE_SECONDS = int(os.getenv("ALERT_STALE_SECONDS", "60"))
    # Send a push notification whenever the server (re)starts.
    PUSH_ON_START = os.getenv("PUSH_ON_START", "true").lower() == "true"

config = Config()
