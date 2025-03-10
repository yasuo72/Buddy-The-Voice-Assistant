import datetime
import json
import logging
import os
import random
import smtplib
import string
import webbrowser
from email.message import EmailMessage
from typing import List, Optional, Tuple, Union

import openai
import psutil
import pywhatkit as kit
import requests
import wikipedia
from bs4 import BeautifulSoup
from decouple import UndefinedValueError, config

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[logging.FileHandler('online.log'), logging.StreamHandler()]
)
logger = logging.getLogger(__name__)


# Load API keys with proper error handling
def get_env_var(var_name: str, default: str = None) -> str:
    """Safely get environment variable with logging."""
    try:
        value = config(var_name)
        if not value and default:
            logger.warning(f"{var_name} not found in .env, using default value")
            return default
        elif not value:
            logger.error(f"{var_name} not found in .env and no default provided")
            raise ValueError(f"{var_name} not configured")
        return value
    except UndefinedValueError:
        if default:
            logger.warning(f"{var_name} not found in .env, using default value")
            return default
        logger.error(f"{var_name} not found in .env and no default provided")
        raise ValueError(f"{var_name} not configured")


try:
    OPENWEATHER_API_KEY = get_env_var('OPENWEATHER_API_KEY')
    NEWS_API_KEY = get_env_var('NEWS_API_KEY')
    EMAIL_ADDRESS = get_env_var('EMAIL_ADDRESS')
    EMAIL_PASSWORD = get_env_var('EMAIL_PASSWORD')
    SMTP_SERVER = get_env_var('SMTP_SERVER', 'smtp.gmail.com')
    SMTP_PORT = int(get_env_var('SMTP_PORT', '587'))
    OPENAI_API_KEY = get_env_var('OPENAI_API_KEY')
    ALPHA_VANTAGE_API_KEY = get_env_var('ALPHA_VANTAGE_API_KEY')
    CRYPTO_API_KEY = get_env_var('CRYPTO_API_KEY')
except ValueError as e:
    logger.error(f"Environment variable error: {str(e)}")
    raise


# ------------------- IP Address -------------------
def find_my_ip() -> dict:
    """
    Get detailed IP address information with multiple fallback options.
    
    Returns:
        dict: IP information including address, location, and ISP if available
    """
    try:
        # Try primary service (ipapi.co)
        try:
            response = requests.get('https://ipapi.co/json/', timeout=5)
            if response.status_code == 200:
                data = response.json()
                return {
                    'ip': data.get('ip', 'Unknown'),
                    'city': data.get('city', 'Unknown'),
                    'region': data.get('region', 'Unknown'),
                    'country': data.get('country_name', 'Unknown'),
                    'isp': data.get('org', 'Unknown'),
                    'source': 'ipapi.co'
                }
        except Exception as e:
            logger.warning(f"Primary IP service failed: {str(e)}")

        # First fallback (ipify)
        try:
            response = requests.get('https://api64.ipify.org?format=json', timeout=5)
            if response.status_code == 200:
                ip = response.json().get('ip')
                # Get additional details from ip-api.com
                details = requests.get(f'http://ip-api.com/json/{ip}', timeout=5).json()
                return {
                    'ip': ip,
                    'city': details.get('city', 'Unknown'),
                    'region': details.get('regionName', 'Unknown'),
                    'country': details.get('country', 'Unknown'),
                    'isp': details.get('isp', 'Unknown'),
                    'source': 'ipify + ip-api.com'
                }
        except Exception as e:
            logger.warning(f"First fallback IP service failed: {str(e)}")

        # Second fallback (httpbin)
        try:
            response = requests.get('https://httpbin.org/ip', timeout=5)
            if response.status_code == 200:
                return {
                    'ip': response.json().get('origin', 'Unknown'),
                    'city': 'Not available',
                    'region': 'Not available',
                    'country': 'Not available',
                    'isp': 'Not available',
                    'source': 'httpbin.org'
                }
        except Exception as e:
            logger.warning(f"Second fallback IP service failed: {str(e)}")

        raise Exception("All IP services failed")

    except Exception as e:
        logger.error(f"Error finding IP address: {str(e)}")
        raise


def format_ip_info(ip_info: dict) -> str:
    """Format IP information for display."""
    try:
        lines = [
            "=== IP Address Information ===",
            f"IP Address: {ip_info['ip']}",
        ]

        if ip_info['city'] != 'Not available':
            lines.extend([
                f"Location: {ip_info['city']}, {ip_info['region']}, {ip_info['country']}",
                f"ISP: {ip_info['isp']}"
            ])

        lines.append(f"(Data source: {ip_info['source']})")
        return "\n".join(lines)
    except Exception as e:
        logger.error(f"Error formatting IP info: {str(e)}")
        return f"IP Address: {ip_info.get('ip', 'Unknown')}"


def handle_general_question(query: str) -> str:
    """
    Handle general questions with multiple fallback options.
    
    Args:
        query (str): User's question
        
    Returns:
        str: Response to the question
    """
    try:
        # Clean and normalize the query
        query = query.strip().lower()

        # First try: OpenAI GPT (if available)
        if OPENAI_API_KEY:
            try:
                response = chat_with_gpt(query)
                if response and not response.startswith("Failed to fetch"):
                    return response
            except Exception as e:
                logger.warning(f"OpenAI GPT failed: {str(e)}")

        # Second try: Free AI model (Hugging Face)
        try:
            response = chat_with_free_gpt(query)
            if response and not response.startswith("Failed to fetch"):
                return response
        except Exception as e:
            logger.warning(f"Free AI model failed: {str(e)}")

        # Third try: Wikipedia for knowledge-based questions
        try:
            # Extract main topic from query
            import re
            topic = re.sub(r'^(what|who|where|when|why|how|tell me about|do you know|can you explain)\s+', '', query)
            topic = re.sub(r'\?+$', '', topic)

            wiki_response = search_on_wikipedia(topic)
            if not wiki_response.startswith("Sorry, I couldn't find"):
                return wiki_response
        except Exception as e:
            logger.warning(f"Wikipedia search failed: {str(e)}")

        # Final fallback: Web search suggestion
        return (
            "I'm not able to directly answer that question. "
            "Would you like me to search the web for you? "
            "Just say 'search for [your question]' and I'll help you find the answer."
        )

    except Exception as e:
        logger.error(f"Error handling general question: {str(e)}")
        return "I apologize, but I'm having trouble processing your question. Please try rephrasing it or ask something else."


# ------------------- Wikipedia Search -------------------
def search_on_wikipedia(query: str) -> str:
    """Search Wikipedia with improved reliability and error handling"""
    try:
        # Set language to English
        wikipedia.set_lang("en")

        # Try to get a summary with error handling
        try:
            return wikipedia.summary(query, sentences=3)
        except wikipedia.DisambiguationError as e:
            # If there are multiple matches, use the first option
            return f"Multiple results found. Try being more specific. Some options are: {', '.join(e.options[:5])}"
        except wikipedia.PageError:
            return f"Sorry, I couldn't find any Wikipedia article about {query}"

    except Exception as e:
        logger.error(f"Error searching Wikipedia: {str(e)}")
        raise Exception(f"Error searching Wikipedia: {str(e)}")


# ------------------- Google Search -------------------
def search_on_google(query: str) -> None:
    """Search Google with improved reliability"""
    try:
        # Properly encode the query for URL
        encoded_query = requests.utils.quote(query)
        url = f"https://www.google.com/search?q={encoded_query}"
        webbrowser.open(url)
    except Exception as e:
        logger.error(f"Error searching Google: {str(e)}")
        raise Exception(f"Error performing Google search: {str(e)}")


# ------------------- YouTube Search -------------------
def youtube(query: str) -> None:
    """Search and play a video on YouTube."""
    try:
        # Clean the search query
        query = query.replace(' ', '+')
        # Open in default browser
        webbrowser.open(f'https://www.youtube.com/results?search_query={query}')
    except Exception as e:
        logger.error(f"Error playing YouTube video: {str(e)}")
        raise Exception(f"Error playing YouTube video: {str(e)}")


# ------------------- Fetch News Headlines -------------------
def get_news() -> List[str]:
    """Get latest news headlines."""
    try:
        if not NEWS_API_KEY:
            raise ValueError("News API key not configured")

        url = f'https://newsapi.org/v2/top-headlines?country=us&apiKey={NEWS_API_KEY}'
        response = requests.get(url)

        if response.status_code == 401:
            raise ValueError("Invalid News API key")
        elif response.status_code != 200:
            raise Exception(f"News API Error: {response.status_code}")

        data = response.json()
        if data['status'] != 'ok':
            raise Exception(f"News API Error: {data.get('message', 'Unknown error')}")

        return [article['title'] for article in data['articles'][:5]]
    except requests.RequestException as e:
        logger.error(f"Network error in news fetch: {str(e)}")
        raise Exception("Network error while fetching news")
    except Exception as e:
        logger.error(f"Error in news fetch: {str(e)}")
        raise


# ------------------- Weather Forecast -------------------
def weather_forecast(city: str) -> Tuple[str, float, float, int, float]:
    """Get weather information for a city."""
    try:
        if not OPENWEATHER_API_KEY:
            raise ValueError("OpenWeather API key not configured")

        url = f'http://api.openweathermap.org/data/2.5/weather?q={city}&appid={OPENWEATHER_API_KEY}&units=metric'
        response = requests.get(url)

        if response.status_code == 401:
            raise ValueError("Invalid OpenWeather API key")
        elif response.status_code == 404:
            raise ValueError(f"City '{city}' not found")
        elif response.status_code != 200:
            raise Exception(f"Weather API Error: {response.status_code}")

        data = response.json()
        weather = data['weather'][0]['description']
        temp = data['main']['temp']
        feels_like = data['main']['feels_like']
        humidity = data['main']['humidity']
        wind_speed = data['wind']['speed']

        return weather, temp, feels_like, humidity, wind_speed
    except requests.RequestException as e:
        logger.error(f"Network error in weather forecast: {str(e)}")
        raise Exception("Network error while fetching weather data")
    except Exception as e:
        logger.error(f"Error in weather forecast: {str(e)}")
        raise


# ------------------- Send Email -------------------
def send_email(receiver_email: str, subject: str, message: str) -> str:
    """
    Send an email with improved validation and error handling.
    
    Args:
        receiver_email (str): Recipient's email address
        subject (str): Email subject
        message (str): Email content
        
    Returns:
        str: Success message or error description
    """
    try:
        # Input validation
        if not all([receiver_email, subject, message]):
            raise ValueError("Email, subject, and message are all required")

        if not all([EMAIL_ADDRESS, EMAIL_PASSWORD]):
            raise ValueError("Email credentials not configured")

        # Validate email format
        import re
        email_pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        if not re.match(email_pattern, receiver_email):
            raise ValueError(f"Invalid email format: {receiver_email}")

        msg = EmailMessage()
        msg.set_content(message)
        msg["Subject"] = subject
        msg["From"] = EMAIL_ADDRESS
        msg["To"] = receiver_email

        # Attempt to send with retry logic
        max_retries = 3
        retry_count = 0

        while retry_count < max_retries:
            try:
                with smtplib.SMTP(SMTP_SERVER, SMTP_PORT, timeout=10) as server:
                    server.starttls()
                    server.login(EMAIL_ADDRESS, EMAIL_PASSWORD)
                    server.send_message(msg)
                return "Email sent successfully!"
            except smtplib.SMTPServerDisconnected:
                retry_count += 1
                if retry_count == max_retries:
                    raise
                logger.warning(f"SMTP connection failed, retrying ({retry_count}/{max_retries})")
                continue

    except smtplib.SMTPAuthenticationError:
        raise ValueError("Invalid email credentials - please check your email and password")
    except smtplib.SMTPRecipientsRefused:
        raise ValueError(f"Invalid recipient email address: {receiver_email}")
    except smtplib.SMTPException as e:
        logger.error(f"SMTP error: {str(e)}")
        raise Exception(f"Failed to send email: {str(e)}")
    except Exception as e:
        logger.error(f"Error in email send: {str(e)}")
        raise


# ------------------- Set Reminder -------------------
def set_reminder(task, time):
    with open("reminders.txt", "a") as file:
        file.write(f"{time} - {task}\n")
    return f"Reminder set for: {time} - {task}"


# ------------------- Fetch Stock Price -------------------
def get_stock_price(stock_symbol):
    try:
        if not ALPHA_VANTAGE_API_KEY:
            return "Please set up your Alpha Vantage API key in the .env file"

        url = f'https://www.alphavantage.co/query?function=GLOBAL_QUOTE&symbol={stock_symbol}&apikey={ALPHA_VANTAGE_API_KEY}'
        response = requests.get(url)
        data = response.json()

        if "Global Quote" not in data or not data["Global Quote"]:
            return f"Could not find stock information for {stock_symbol}"

        price = data["Global Quote"]["05. price"]
        return f"The current price of {stock_symbol} is ${price}"

    except Exception as e:
        logger.error(f"Error getting stock price: {str(e)}")
        raise Exception(f"Error getting stock price: {str(e)}")


def get_exchange_rate(base_currency: str, target_currency: str) -> str:
    """
    Get currency exchange rate with improved validation and error handling.
    
    Args:
        base_currency (str): Source currency code (e.g., 'USD')
        target_currency (str): Target currency code (e.g., 'EUR')
        
    Returns:
        str: Formatted exchange rate information
    """
    try:
        # Input validation
        if not all([base_currency, target_currency]):
            raise ValueError("Both base and target currencies are required")

        # Convert to uppercase and validate currency codes
        base_currency = base_currency.upper()
        target_currency = target_currency.upper()

        if len(base_currency) != 3 or len(target_currency) != 3:
            raise ValueError("Currency codes must be 3 letters (e.g., USD, EUR)")

        # Make API request with timeout and retry logic
        max_retries = 3
        retry_count = 0
        timeout_seconds = 10

        while retry_count < max_retries:
            try:
                url = f'https://api.exchangerate-api.com/v4/latest/{base_currency}'
                response = requests.get(url, timeout=timeout_seconds)

                if response.status_code == 404:
                    raise ValueError(f"Invalid currency code: {base_currency}")
                elif response.status_code != 200:
                    raise Exception(f"API Error (Status {response.status_code}): {response.text}")

                data = response.json()

                if target_currency not in data['rates']:
                    raise ValueError(f"Invalid target currency: {target_currency}")

                rate = data['rates'][target_currency]
                formatted_rate = f"{rate:.4f}"  # Format to 4 decimal places

                # Add additional useful information
                timestamp = datetime.datetime.fromtimestamp(data['time_last_updated'])
                last_updated = timestamp.strftime("%Y-%m-%d %H:%M:%S UTC")

                return (f"Exchange Rate: 1 {base_currency} = {formatted_rate} {target_currency}\n"
                        f"Last Updated: {last_updated}")

            except requests.Timeout:
                retry_count += 1
                if retry_count == max_retries:
                    raise Exception("Failed to get exchange rate: Connection timeout")
                logger.warning(f"Request timeout, retrying ({retry_count}/{max_retries})")
                continue

            except requests.RequestException as e:
                logger.error(f"Network error in exchange rate fetch: {str(e)}")
                raise Exception("Network error while fetching exchange rate")

    except ValueError as e:
        logger.error(f"Validation error: {str(e)}")
        raise
    except Exception as e:
        logger.error(f"Error getting exchange rate: {str(e)}")
        raise


# ------------------- Generate Random Password -------------------
def generate_password(length: int = 12) -> str:
    """Generate a secure random password."""
    try:
        if length < 8:
            length = 12  # Minimum secure length

        # Define character sets
        lowercase = string.ascii_lowercase
        uppercase = string.ascii_uppercase
        digits = string.digits
        symbols = string.punctuation

        # Ensure at least one character from each set
        password = [
            random.choice(lowercase),
            random.choice(uppercase),
            random.choice(digits),
            random.choice(symbols)
        ]

        # Fill the rest randomly
        for _ in range(length - 4):
            password.append(random.choice(lowercase + uppercase + digits + symbols))

        # Shuffle the password
        random.shuffle(password)
        password = ''.join(password)

        return f"Generated password: {password}"
    except Exception as e:
        raise Exception(f"Error generating password: {str(e)}")


# ------------------- Fetch Cryptocurrency Prices -------------------
def get_crypto_price(crypto_symbol):
    try:
        if not CRYPTO_API_KEY:
            return "Please set up your CryptoCompare API key in the .env file"

        url = f'https://min-api.cryptocompare.com/data/price?fsym={crypto_symbol.upper()}&tsyms=USD&api_key={CRYPTO_API_KEY}'
        response = requests.get(url)
        data = response.json()

        if 'USD' not in data:
            return f"Could not find price for {crypto_symbol}"

        price = data['USD']
        return f"The current price of {crypto_symbol.upper()} is ${price:,.2f}"

    except Exception as e:
        logger.error(f"Error getting crypto price: {str(e)}")
        raise Exception(f"Error getting crypto price: {str(e)}")


# ------------------- Check System Battery Percentage -------------------
def get_battery_status():
    try:
        battery = psutil.sensors_battery()
        if battery:
            percent = battery.percent
            power_plugged = battery.power_plugged
            status = "plugged in" if power_plugged else "not plugged in"
            return f"Battery is at {percent}% and is {status}"
        return "Could not get battery information"
    except Exception as e:
        logger.error(f"Error getting battery status: {str(e)}")
        raise Exception(f"Error getting battery status: {str(e)}")


# ------------------- Get Current Date & Time -------------------
def get_current_datetime():
    try:
        now = datetime.datetime.now()
        return now.strftime("It's %I:%M %p on %A, %B %d, %Y")
    except Exception as e:
        logger.error(f"Error getting date and time: {str(e)}")
        raise Exception(f"Error getting date and time: {str(e)}")


def chat_with_gpt(prompt):
    API_KEY = os.getenv("OPENAI_API_KEY")  # ✅ Get API key from .env

    if not API_KEY:
        return "API Key not found. Make sure to set OPENAI_API_KEY in the .env file."

    try:
        openai.api_key = API_KEY
        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "You are a helpful assistant."},
                {"role": "user", "content": prompt}
            ]
        )
        return response["choices"][0]["message"]["content"].strip()

    except Exception as e:
        return f"Failed to fetch GPT response: {str(e)}"


import requests


# ------------------- Chat with Free AI (Hugging Face) -------------------
def chat_with_free_gpt(prompt):
    try:
        API_URL = "https://api-inference.huggingface.co/models/mistralai/Mistral-7B-Instruct"
        headers = {"Authorization": f"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"}  # Get from Hugging Face

        response = requests.post(API_URL, headers=headers, json={"inputs": prompt})
        answer = response.json()

        if isinstance(answer, list) and len(answer) > 0:
            return answer[0]["generated_text"]
        return "I couldn't generate a response."

    except Exception as e:
        return f"Failed to fetch AI response: {str(e)}"


def handle_email_input() -> Tuple[str, str, str]:
    """
    Handle user input for email sending with validation.
    
    Returns:
        Tuple[str, str, str]: receiver_email, subject, message
    """
    try:
        print("\n=== Email Composition ===")

        # Get and validate receiver's email
        while True:
            receiver_email = input("Enter recipient's email address: ").strip()
            import re
            email_pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
            if re.match(email_pattern, receiver_email):
                break
            print("Invalid email format. Please try again.")

        # Get and validate subject
        while True:
            subject = input("Enter email subject: ").strip()
            if subject:
                break
            print("Subject cannot be empty. Please try again.")

        # Get and validate message
        print("Enter your message (press Enter twice to finish):")
        message_lines = []
        while True:
            line = input()
            if not line and message_lines and not message_lines[-1]:
                break
            message_lines.append(line)

        message = "\n".join(message_lines[:-1])  # Remove the last empty line
        if not message.strip():
            raise ValueError("Message cannot be empty")

        return receiver_email, subject, message

    except KeyboardInterrupt:
        raise ValueError("Email composition cancelled by user")
    except Exception as e:
        logger.error(f"Error in email input: {str(e)}")
        raise


def send_email_with_input() -> str:
    """
    Interactive function to send email with user input.
    
    Returns:
        str: Success or error message
    """
    try:
        receiver_email, subject, message = handle_email_input()
        return send_email(receiver_email, subject, message)
    except ValueError as e:
        return str(e)
    except Exception as e:
        return f"Failed to send email: {str(e)}"


def handle_exchange_rate_input() -> Tuple[str, str]:
    """
    Handle user input for currency exchange rate with validation.
    
    Returns:
        Tuple[str, str]: base_currency, target_currency
    """
    try:
        print("\n=== Currency Exchange Rate ===")

        # Get and validate base currency
        while True:
            base_currency = input("Enter base currency code (e.g., USD): ").strip().upper()
            if len(base_currency) == 3 and base_currency.isalpha():
                break
            print("Invalid currency code. Please enter a 3-letter code (e.g., USD).")

        # Get and validate target currency
        while True:
            target_currency = input("Enter target currency code (e.g., EUR): ").strip().upper()
            if len(target_currency) == 3 and target_currency.isalpha():
                break
            print("Invalid currency code. Please enter a 3-letter code (e.g., EUR).")

        return base_currency, target_currency

    except KeyboardInterrupt:
        raise ValueError("Currency exchange rate request cancelled by user")
    except Exception as e:
        logger.error(f"Error in exchange rate input: {str(e)}")
        raise


def get_exchange_rate_with_input() -> str:
    """
    Interactive function to get exchange rate with user input.
    
    Returns:
        str: Exchange rate information or error message
    """
    try:
        base_currency, target_currency = handle_exchange_rate_input()
        return get_exchange_rate(base_currency, target_currency)
    except ValueError as e:
        return str(e)
    except Exception as e:
        return f"Failed to get exchange rate: {str(e)}"


def get_greeting() -> str:
    """Get appropriate greeting based on time of day."""
    try:
        hour = datetime.datetime.now().hour

        if 5 <= hour < 12:
            greeting = "Good morning"
        elif 12 <= hour < 17:
            greeting = "Good afternoon"
        elif 17 <= hour < 22:
            greeting = "Good evening"
        else:
            greeting = "Hello"

        # Get user name from environment if available
        user_name = get_env_var('USER', 'there')
        bot_name = get_env_var('BOT', 'Assistant')

        greetings = [
            f"{greeting}, {user_name}! I'm {bot_name}, your personal assistant. How can I help you today?",
            f"{greeting}! Great to see you, {user_name}. I'm ready to assist you!",
            f"Welcome back, {user_name}! Hope you're having a wonderful {datetime.datetime.now().strftime('%A')}.",
            f"{greeting}! I'm {bot_name}, here to help with whatever you need."
        ]

        return random.choice(greetings)

    except Exception as e:
        logger.error(f"Error generating greeting: {str(e)}")
        return "Hello! How can I help you today?"


def initial_greeting() -> str:
    """Function to be called when the assistant starts up."""
    return get_greeting()


def handle_basic_conversation(query: str) -> Optional[str]:
    """
    Handle basic conversational queries with natural responses.
    
    Args:
        query (str): User's input
        
    Returns:
        Optional[str]: Response if query is conversational, None otherwise
    """
    try:
        # Convert to lowercase and remove punctuation
        clean_query = query.lower().strip('?!.,')

        # Get bot name from environment
        bot_name = get_env_var('BOT', 'Assistant').lower()
        user_name = get_env_var('USER', 'there')

        # Basic greetings with more variations
        greetings = [
            'hello', 'hi', 'hey', 'good morning', 'good afternoon', 'good evening',
            'hello buddy', 'hi buddy', 'hey buddy', 'hello assistant', 'hi assistant',
            'greetings', 'start', 'wake up'
        ]

        # Check for greetings including bot name
        if (clean_query in greetings or
                f"hello {bot_name}" in clean_query or
                any(greeting in clean_query for greeting in greetings)):
            return get_greeting()

        # How are you variations with more patterns
        how_are_you = [
            'how are you', 'how do you do', 'how are you doing',
            'whats up', "what's up", 'how is it going', 'how are things',
            'how have you been', 'how do you feel', 'are you well',
            f"how are you {bot_name}", f"how are you doing {bot_name}"
        ]
        if any(phrase in clean_query for phrase in how_are_you):
            responses = [
                f"I'm doing great, {user_name}! Thank you for asking. How can I assist you today?",
                "I'm functioning perfectly! What can I help you with?",
                f"All systems operational and ready to help, {user_name}! What's on your mind?",
                "I'm excellent! Always happy to chat and help. What do you need?"
            ]
            return random.choice(responses)

        # Thank you variations with more patterns
        thanks = [
            'thank you', 'thanks', 'thank you so much', 'thanks a lot',
            'appreciate it', 'thanks buddy', f'thank you {bot_name}',
            'thx', 'ty', 'thanks for your help'
        ]
        if any(phrase in clean_query for phrase in thanks):
            responses = [
                f"You're welcome, {user_name}! Let me know if you need anything else.",
                "Glad I could help! Don't hesitate to ask if you need more assistance.",
                "My pleasure! Is there anything else you'd like to know?",
                f"You're welcome, {user_name}! Have a great day!"
            ]
            return random.choice(responses)

        # Goodbye variations with more patterns
        goodbyes = [
            'goodbye', 'bye', 'see you', 'see you later', 'good night',
            'bye bye', 'catch you later', 'have a good one', 'take care',
            f'goodbye {bot_name}', f'bye {bot_name}'
        ]
        if any(phrase in clean_query for phrase in goodbyes):
            responses = [
                f"Goodbye, {user_name}! Have a great day!",
                f"See you later, {user_name}! Don't hesitate to come back if you need help!",
                "Bye for now! Take care!",
                f"Goodbye! Remember, I'm here 24/7 if you need assistance!"
            ]
            return random.choice(responses)

        # Name queries with more patterns
        name_queries = [
            'what is your name', 'who are you', 'what should i call you',
            'what are you called', 'introduce yourself', 'what are you',
            'what is this', 'who am i talking to'
        ]
        if any(phrase in clean_query for phrase in name_queries):
            bot_name = get_env_var('BOT', 'Assistant')
            responses = [
                f"I'm {bot_name}, your personal AI assistant! I'm here to help you with various tasks.",
                f"My name is {bot_name}, and I'm your AI companion. I can help you with emails, searches, weather updates, and much more!",
                f"You can call me {bot_name}. I'm your AI assistant, ready to help with whatever you need!"
            ]
            return random.choice(responses)

        return None

    except Exception as e:
        logger.error(f"Error in conversation handling: {str(e)}")
        return None


def process_command(command: str) -> str:
    """
    Process user commands with improved handling for all features.
    
    Args:
        command (str): User command
        
    Returns:
        str: Response message
    """
    if not command:
        return "I didn't catch that. Could you please repeat?"

    command = command.lower().strip()

    try:
        # First check for basic conversation
        conversation_response = handle_basic_conversation(command)
        if conversation_response:
            return conversation_response

        # Check for specific commands
        if "ip address" in command or "my ip" in command:
            ip_info = find_my_ip()
            return format_ip_info(ip_info)

        elif "send email" in command or "compose email" in command:
            return send_email_with_input()

        elif "exchange rate" in command or "currency rate" in command:
            return get_exchange_rate_with_input()

        elif "news" in command or "headlines" in command:
            headlines = get_news()
            return "Here are the latest headlines:\n" + "\n".join(f"- {headline}" for headline in headlines)

        elif "weather" in command:
            # Extract city name or ask for it
            city = command.replace("weather", "").strip()
            if not city:
                return "Which city would you like to know the weather for?"
            weather, temp, feels_like, humidity, wind = weather_forecast(city)
            return f"Weather in {city}:\n{weather.capitalize()}\nTemperature: {temp}°C (Feels like: {feels_like}°C)\nHumidity: {humidity}%\nWind Speed: {wind} m/s"

        elif "time" in command or "date" in command:
            return get_current_datetime()

        elif "battery" in command:
            return get_battery_status()

        # Handle general questions
        elif any(q in command for q in
                 ["what's", "who", "where", "when", "why", "how", "tell me", "do you know", "can you explain"]):
            return handle_general_question(command)

        # If no other matches, treat as a general question
        return handle_general_question(command)

    except Exception as e:
        logger.error(f"Error processing command: {str(e)}")
        return f"Sorry, I encountered an error: {str(e)}"
