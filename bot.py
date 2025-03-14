import requests
import time
import logging
import random
import base64
import os
from cryptography.fernet import Fernet
from requests.adapters import HTTPAdapter
from requests.packages.urllib3.util.retry import Retry
from telegram import Bot

# Configure Logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Generate and store encryption key securely
ENCRYPTION_KEY = os.getenv("ENCRYPTION_KEY") or Fernet.generate_key()
cipher = Fernet(ENCRYPTION_KEY)

def encrypt_token(token):
    return cipher.encrypt(token.encode()).decode()

def decrypt_token(token):
    return cipher.decrypt(token.encode()).decode()

# API and Token Configuration
API_BASE_URL = "https://api.getgrass.io"
AUTH_TOKEN_ENCRYPTED = os.getenv("AUTH_TOKEN")  # Store encrypted token securely
AUTH_TOKEN = decrypt_token(AUTH_TOKEN_ENCRYPTED) if AUTH_TOKEN_ENCRYPTED else ""
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

# Proxy Configuration
PRIMARY_PROXY = {
    "http": os.getenv("PRIMARY_PROXY", "http://your_proxy_here"),
    "https": os.getenv("PRIMARY_PROXY", "https://your_proxy_here")
}
import requests
import random

def get_free_proxy():
    """Fetches a random free public proxy."""
    url = "https://www.proxy-list.download/api/v1/get?type=http"
    try:
        response = requests.get(url)
        if response.status_code == 200:
            proxies = response.text.strip().split("\r\n")
            if proxies:
                proxy = random.choice(proxies)
                logging.info(f"Using public proxy: {proxy}")
                return {"http": f"http://{proxy}", "https": f"https://{proxy}"}
    except Exception as e:
        logging.error(f"Failed to fetch free proxies: {e}")
    return None

PUBLIC_PROXY = get_free_proxy() or {"http": None, "https": None}

# User-Agent Rotation
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/110.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/111.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/109.0.0.0 Safari/537.36",
]

def get_proxies():
    """Attempt to use the primary proxy, falling back to the public proxy if unavailable."""
    try:
        response = requests.get("https://httpbin.org/ip", proxies=PRIMARY_PROXY, timeout=5)
        if response.status_code == 200:
            logging.info("Using primary proxy.")
            return PRIMARY_PROXY
    except requests.exceptions.RequestException:
        logging.warning("Primary proxy unavailable, switching to public proxy.")
    
    return PUBLIC_PROXY

def get_session():
    """Creates a session with retry strategy and rotating User-Agent."""
    session = requests.Session()
    retry = Retry(
        total=5,
        backoff_factor=1,
        status_forcelist=[500, 502, 503, 504, 429]
    )
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    session.headers.update({
        "Authorization": f"Bearer {AUTH_TOKEN}",
        "Content-Type": "application/json",
        "User-Agent": random.choice(USER_AGENTS)
    })
    return session

def handle_response(response, success_message, failure_message):
    """Handles API responses and logs errors accordingly."""
    if response is None:
        logging.error("No response received from API.")
        return None
    
    if response.status_code == 200:
        logging.info(success_message)
        return response.json()
    elif response.status_code == 429:
        logging.warning("Rate limited: Too many requests, waiting before retrying...")
        time.sleep(120)
    else:
        logging.error(f"Unexpected Error {response.status_code}: {response.text}")
    return None

def make_request(method, endpoint, success_message, failure_message):
    """Generic function to handle API requests with exception handling, proxy, and session handling."""
    url = f"{API_BASE_URL}{endpoint}"
    proxies = get_proxies()
    session = get_session()
    try:
        if method == "GET":
            response = session.get(url, proxies=proxies, timeout=10)
        elif method == "POST":
            response = session.post(url, proxies=proxies, timeout=10)
        else:
            logging.error("Invalid HTTP method.")
            return None
        
        return handle_response(response, success_message, failure_message)
    except requests.exceptions.Timeout:
        logging.error("Request timed out. Retrying...")
        time.sleep(30)
        return make_request(method, endpoint, success_message, failure_message)
    except requests.exceptions.ConnectionError:
        logging.error("Connection error. Retrying...")
        time.sleep(60)
        return make_request(method, endpoint, success_message, failure_message)
    except Exception as e:
        logging.error(f"Unexpected error: {e}")
        return None

def check_balance():
    """Fetch user balance from the API"""
    return make_request("GET", "/user/balance", "Fetched balance successfully", "Failed to fetch balance")

def fetch_profile():
    """Fetch user profile information from the API."""
    return make_request("GET", "/user/profile", "Fetched profile successfully", "Failed to fetch profile")

def send_farming_update():
    """Fetches current farming progress and sends a Telegram update."""
    balance = check_balance()
    if balance is not None:
        send_telegram_message(f"Farming Progress Update: Current Balance: {balance}")

def check_farming_status():
    """Checks if farming is already active to prevent redundant calls."""
    status = make_request("GET", "/farm/status", "Fetched farming status successfully", "Failed to fetch farming status")
    if status and status.get("active", False):
        logging.info("Farming is already active.")
        return True
    return False

def auto_farm():
    """Automates point farming actions while respecting API limits."""
    while True:
        if not check_farming_status():
            if make_request("POST", "/farm/start", "Successfully started farming action.", "Farming action failed"):
                send_telegram_message("Farming action successful!")
                send_farming_update()
            else:
                send_telegram_message("Farming failed.")
        else:
            logging.info("Skipping farming start request as it is already active.")
        time.sleep(random.randint(45, 75))  # Random delay to simulate human behavior

def send_telegram_message(message):
    """Send a message via Telegram bot."""
    try:
        bot = Bot(token=TELEGRAM_BOT_TOKEN)
        bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=message)
    except Exception as e:
        logging.error(f"Failed to send Telegram message: {e}")

def main():
    """Main function to run the bot."""
    logging.info("Starting automation bot...")
    balance = check_balance()
    profile = fetch_profile()
    if balance is not None:
        send_telegram_message(f"Current balance: {balance}")
    if profile is not None:
        send_telegram_message(f"Profile Info: {profile}")
    auto_farm()

if __name__ == "__main__":
    main()
