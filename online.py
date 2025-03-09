import datetime
import logging
import random
import smtplib
import webbrowser
from email.message import EmailMessage

import openai
import psutil
import pywhatkit as kit
import requests
import wikipedia
from decouple import config

logger = logging.getLogger(__name__)


# ------------------- IP Address -------------------
def find_my_ip() -> str:
    """Get public IP address with improved reliability"""
    ip_services = [
        "https://api.ipify.org?format=json",
        "https://api.myip.com",
        "https://ip.seeip.org/jsonip"
    ]
    
    for service in ip_services:
        try:
            response = requests.get(service, timeout=5)
            response.raise_for_status()
            data = response.json()
            
            # Different services return IP in different formats
            if 'ip' in data:
                return data['ip']
            elif 'query' in data:
                return data['query']
                
        except Exception as e:
            logger.error(f"Error getting IP from {service}: {str(e)}")
            continue
            
    return "Could not determine IP address"


# ------------------- Wikipedia Search -------------------
def search_on_wikipedia(query: str) -> str:
    """Search Wikipedia with improved reliability and error handling"""
    try:
        # Set language to English
        wikipedia.set_lang("en")
        
        # Try to get a summary with error handling
        try:
            return wikipedia.summary(query, sentences=2)
        except wikipedia.DisambiguationError as e:
            # If there are multiple matches, use the first option
            return wikipedia.summary(e.options[0], sentences=2)
        except wikipedia.PageError:
            return f"Sorry, I couldn't find any Wikipedia article about {query}"
            
    except Exception as e:
        logger.error(f"Error searching Wikipedia: {str(e)}")
        return "Sorry, I encountered an error while searching Wikipedia. Please try again."


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
        raise Exception("Could not search Google. Please try again.")


# ------------------- YouTube Search -------------------
def youtube(query: str) -> None:
    """Search and open YouTube with improved reliability"""
    try:
        # Properly encode the query for URL
        encoded_query = requests.utils.quote(query)
        url = f"https://www.youtube.com/results?search_query={encoded_query}"
        webbrowser.open(url)
    except Exception as e:
        logger.error(f"Error opening YouTube: {str(e)}")
        raise Exception("Could not open YouTube. Please try again.")


# ------------------- Fetch News Headlines -------------------
def get_news() -> list:
    """Get news headlines with improved reliability"""
    try:
        # NewsAPI configuration
        api_key = config('NEWS_API_KEY', default='YOUR_API_KEY')
        base_url = "https://newsapi.org/v2/top-headlines"
        
        params = {
            'country': 'us',
            'apiKey': api_key
        }
        
        response = requests.get(base_url, params=params, timeout=10)
        response.raise_for_status()
        
        news_data = response.json()
        
        if news_data.get('status') != 'ok':
            logger.error(f"News API error: {news_data.get('message', 'Unknown error')}")
            return ["Sorry, I couldn't fetch the news right now."]
            
        articles = news_data.get('articles', [])
        headlines = []
        
        for article in articles[:5]:  # Get top 5 headlines
            if article.get('title'):
                headlines.append(article['title'])
                
        return headlines if headlines else ["No news headlines available at the moment."]
        
    except Exception as e:
        logger.error(f"Error fetching news: {str(e)}")
        return ["Sorry, I encountered an error while fetching the news."]


# ------------------- Weather Forecast -------------------
def weather_forecast(city: str) -> tuple:
    """Get weather forecast for a city with proper temperature conversion"""
    try:
        # OpenWeatherMap API configuration
        api_key = config('OPENWEATHER_API_KEY', default='YOUR_API_KEY')
        base_url = "http://api.openweathermap.org/data/2.5/weather"
        
        # Make the API request with metric units
        params = {
            'q': city,
            'appid': api_key,
            'units': 'metric'  # Use metric units (Celsius)
        }
        
        response = requests.get(base_url, params=params, timeout=10)
        response.raise_for_status()
        
        # Parse the response
        weather_data = response.json()
        
        if weather_data.get('cod') != 200:
            logger.error(f"Weather API error: {weather_data.get('message', 'Unknown error')}")
            return None, None, None, None, None
            
        # Extract weather information
        weather = weather_data['weather'][0]['description']
        temp = float(weather_data['main']['temp'])  # Already in Celsius
        feels_like = float(weather_data['main']['feels_like'])  # Already in Celsius
        humidity = weather_data['main']['humidity']
        wind_speed = weather_data['wind']['speed']
        
        # Format weather description and temperatures
        weather = weather.capitalize()
        temp = round(temp, 1)  # Round to 1 decimal place
        feels_like = round(feels_like, 1)  # Round to 1 decimal place
        
        # Return comprehensive weather data
        return (
            weather,
            temp,
            feels_like,
            humidity,
            wind_speed
        )
        
    except requests.RequestException as e:
        logger.error(f"Weather API request failed: {str(e)}")
        return None, None, None, None, None
    except (KeyError, IndexError) as e:
        logger.error(f"Error parsing weather data: {str(e)}")
        return None, None, None, None, None
    except Exception as e:
        logger.error(f"Unexpected error in weather_forecast: {str(e)}")
        return None, None, None, None, None


# ------------------- Send Email -------------------
def send_email(receiver_email, subject, message):
    EMAIL = config("kingrohi38@gmail.com")
    PASSWORD = config("Rs965198@")

    try:
        msg = EmailMessage()
        msg.set_content(message)
        msg["Subject"] = subject
        msg["From"] = EMAIL
        msg["To"] = receiver_email

        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(EMAIL, PASSWORD)
            server.send_message(msg)

        return "Email sent successfully!"

    except Exception as e:
        return f"Failed to send email: {str(e)}"


# ------------------- Set Reminder -------------------
def set_reminder(task, time):
    with open("reminders.txt", "a") as file:
        file.write(f"{time} - {task}\n")
    return f"Reminder set for: {time} - {task}"


# ------------------- Fetch Stock Price -------------------
def get_stock_price(stock_symbol):
    API_KEY = config("cuv2311r01qpi6rss3n0", default="cuv2311r01qpi6rss3lgcuv2311r01qpi6rss3m0")

    try:
        url = f"https://finnhub.io/api/v1/quote?symbol={stock_symbol}&token={API_KEY}"
        response = requests.get(url).json()
        return f"Current price of {stock_symbol} is ${response['c']}"

    except requests.exceptions.RequestException:
        return "Failed to fetch stock price."


def get_exchange_rate(base_currency, target_currency):
    API_KEY = config("7d4262ccf8e7a28b6ae56535", default="7d4262ccf8e7a28b6ae56535")

    try:
        url = f"https://v6.exchangerate-api.com/v6/{API_KEY}/latest/{base_currency}"
        response = requests.get(url).json()
        rate = response["conversion_rates"].get(target_currency)

        if rate:
            return f"1 {base_currency} equals {rate} {target_currency}."
        else:
            return f"Invalid currency code provided."

    except requests.exceptions.RequestException:
        return "Failed to fetch exchange rates."


# ------------------- Generate Random Password -------------------
def generate_password(length=12):
    characters = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789!@#$%^&*()?"
    password = "".join(random.choice(characters) for _ in range(length))
    return f"Generated password: {password}"


# ------------------- Fetch Cryptocurrency Prices -------------------
def get_crypto_price(crypto_symbol):
    try:
        # CoinPaprika API (Free, No API Key Required)
        url = f"https://api.coinpaprika.com/v1/tickers/{crypto_symbol}-usd"
        response = requests.get(url).json()

        if "quotes" in response and "USD" in response["quotes"]:
            price = response["quotes"]["USD"]["price"]
            return f"Current price of {crypto_symbol.upper()} is ${price}"
        else:
            return "Invalid cryptocurrency symbol. Please try again."

    except requests.exceptions.RequestException:
        return "Failed to fetch cryptocurrency price."


# ------------------- Check System Battery Percentage -------------------
def get_battery_status():
    battery = psutil.sensors_battery()
    if battery:
        return f"Battery is at {battery.percent}%"
    else:
        return "Battery status not available."


# ------------------- Get Current Date & Time -------------------
def get_current_datetime():
    now = datetime.datetime.now()
    return f"Current date and time: {now.strftime('%Y-%m-%d %H:%M:%S')}"


def chat_with_gpt(prompt):
    API_KEY = config("sk-proj"
                     "-28LzhDx7qPv4dtuZc0GqzVCk_DhFyByLDy6DX6URKLDY77TEX2Li1OAHkQup7A8oNRsuhPKgK5T3BlbkFJ2YcfBCWZIz0n7AX2XO3lxE7MNQ0UwCIl8JLpNg5qzU7OidMU8VPdpc4amHl6zlk_lxo4VzhRcA",
                     default="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")

    try:
        openai.api_key = API_KEY
        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[{"role": "system", "content": "You are a helpful assistant."},
                      {"role": "user", "content": prompt}]
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
