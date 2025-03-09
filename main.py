import logging
import os
import subprocess as sp
from datetime import datetime
from pathlib import Path
from random import choice
from typing import Optional

import keyboard
import pyttsx3
import requests
import speech_recognition as sr
from decouple import config

from conv import random_text
from online import (chat_with_free_gpt, chat_with_gpt, find_my_ip,
                    generate_password, get_battery_status, get_crypto_price,
                    get_current_datetime, get_exchange_rate, get_news,
                    get_stock_price, search_on_google, search_on_wikipedia,
                    send_email, set_reminder, weather_forecast, youtube)

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[logging.FileHandler('assistant.log'), logging.StreamHandler()]
)
logger = logging.getLogger(__name__)

class VoiceAssistant:
    def __init__(self, web_mode=False):
        # Initialize Text-to-Speech Engine
        self.engine = pyttsx3.init('sapi5')
        self.engine.setProperty('volume', 1.0)
        self.engine.setProperty('rate', 180)  # Slightly slower for better clarity
        voices = self.engine.getProperty('voices')
        self.engine.setProperty('voice', voices[0].id)

        # Load Configurations
        self.user = config('USER', default="User")
        self.bot = config('BOT', default="Jarvis")
        self.listening = False
        self.web_mode = web_mode
        self.pending_input = None
        self.last_response = None
        self.should_stop = False  # New flag for stopping the assistant
        
        # Initialize speech recognizer with optimized settings
        self.recognizer = sr.Recognizer()
        self.recognizer.energy_threshold = 1000  # Lower threshold for better detection
        self.recognizer.dynamic_energy_threshold = True
        self.recognizer.dynamic_energy_adjustment_damping = 0.15
        self.recognizer.dynamic_energy_ratio = 1.5
        self.recognizer.pause_threshold = 0.3  # Faster response
        self.recognizer.operation_timeout = 5  # Timeout for online operations
        
        if not web_mode:
            self.setup_hotkeys()

    def setup_hotkeys(self):
        """Set up keyboard hotkeys for voice control"""
        keyboard.add_hotkey('k', self.start_listening)
        keyboard.add_hotkey('ctrl+alt+p', self.stop_listening)

    def speak(self, text: str) -> None:
        """Speak out the given text."""
        try:
            if text and isinstance(text, str):
                self.engine.say(text)
                self.engine.runAndWait()
                logger.info(f"Assistant said: {text}")
                self.last_response = text
        except Exception as e:
            logger.error(f"Error in speech: {str(e)}")

    def greet_me(self) -> None:
        """Greet the user based on the time of the day with voice."""
        try:
            hour = datetime.now().hour
            greeting = "Good "
            if 6 <= hour < 12:
                greeting += "Morning"
            elif 12 <= hour < 16:
                greeting += "Afternoon"
            elif 16 <= hour < 19:
                greeting += "Evening"
            else:
                greeting += "Night"
                
            initial_greeting = f"{greeting} {self.user}. I am {self.bot}. How may I assist you?"
            self.speak(initial_greeting)
            logger.info("Greeting delivered successfully")
            
            if self.web_mode:
                return [initial_greeting]
                
        except Exception as e:
            logger.error(f"Error in greeting: {str(e)}")
            self.speak("Hello! How may I assist you?")

    def start_listening(self) -> None:
        self.listening = True
        logger.info("Started Listening...")

    def stop_listening(self) -> None:
        self.listening = False
        logger.info("Stopped Listening...")

    def take_command(self) -> str:
        """Recognize and process user voice input."""
        query = "None"
        
        try:
            # Initialize microphone instance with optimal settings
            mic = sr.Microphone(device_index=None)  # Use default microphone
            with mic as source:
                logger.info("Listening...")
                
                # Adjust for ambient noise with longer duration
                try:
                    logger.info("Adjusting for ambient noise...")
                    self.recognizer.adjust_for_ambient_noise(source, duration=2)
                    logger.info(f"Energy threshold set to {self.recognizer.energy_threshold}")
                except Exception as e:
                    logger.error(f"Error adjusting for ambient noise: {str(e)}")
                
                # Configure recognition settings for better accuracy
                self.recognizer.pause_threshold = 0.8  # Longer pause threshold
                self.recognizer.energy_threshold = 1000  # Lower energy threshold
                self.recognizer.dynamic_energy_threshold = True
                self.recognizer.dynamic_energy_adjustment_damping = 0.15
                self.recognizer.dynamic_energy_ratio = 1.5
                self.recognizer.operation_timeout = 10  # Increased timeout
                
                try:
                    # Listen for voice input with generous timeouts
                    logger.info("Starting to listen for audio...")
                    audio = self.recognizer.listen(
                        source,
                        timeout=10,  # 10 seconds to start speaking
                        phrase_time_limit=10  # 10 seconds max phrase length
                    )
                    logger.info("Audio captured, recognizing...")
                    
                    # Try multiple language codes for better recognition
                    languages = ['en-US', 'en-IN', 'en-GB']
                    recognition_errors = []
                    
                    for language in languages:
                        try:
                            query = self.recognizer.recognize_google(
                                audio,
                                language=language,
                                show_all=False  # Only return most confident result
                            )
                            if query and query.strip():
                                logger.info(f"Successfully recognized: '{query}' using {language}")
                                return query.lower()
                        except sr.UnknownValueError:
                            recognition_errors.append(f"{language}: No speech detected")
                            continue
                        except sr.RequestError as e:
                            recognition_errors.append(f"{language}: {str(e)}")
                            continue
                    
                    # If we get here, no recognition was successful
                    logger.warning(f"Recognition failed with all languages. Errors: {recognition_errors}")
                    return "None"
                    
                except sr.WaitTimeoutError:
                    logger.error("Listening timed out - no speech detected")
                    return "None"
                except Exception as e:
                    logger.error(f"Error during listening: {str(e)}")
                    return "None"

        except Exception as e:
            logger.error(f"Critical error in speech recognition: {str(e)}")
            return "None"

        return "None"

    def execute_command(self, query: str) -> None:
        """Execute the appropriate action based on the voice command"""
        # Handle empty or None queries
        if not query or query == "None":
            self.speak("I couldn't hear you clearly. Please try again.")
            return

        # Check for stop commands first
        stop_commands = ["stop", "exit", "quit", "bye", "goodbye", "shut down", "shutdown", "turn off"]
        if any(cmd in query.lower() for cmd in stop_commands):
            self.handle_stop()
            return

        # Normalize the query
        query = query.lower().strip()
        logger.info(f"Processing command: {query}")
        
        # Define command variations and handlers with more natural language patterns
        command_patterns = {
            "stop assistant": [
                "stop", "exit", "quit", "bye", "goodbye", "shut down",
                "shutdown", "turn off", "stop listening", "stop assistant"
            ],
            "how are you": [
                "how are you", "how're you", "how you doing", "how do you do",
                "what's up", "how are things", "how is it going"
            ],
            "open command prompt": [
                "open cmd", "launch command prompt", "start cmd", "command prompt",
                "cmd", "terminal", "open terminal"
            ],
            "open camera": [
                "open camera", "launch camera", "start camera", "camera",
                "turn on camera", "show camera"
            ],
            "open notepad": [
                "open notepad", "launch notepad", "start notepad", "notepad",
                "text editor", "open text editor"
            ],
            "open discord": [
                "open discord", "launch discord", "start discord", "discord"
            ],
            "open vs code": [
                "open vs code", "launch vs code", "start vs code", "visual studio code",
                "vs code", "vscode", "code editor"
            ],
            "ip address": [
                "ip address", "what's my ip", "what is my ip", "show ip", "get ip",
                "network address", "my ip"
            ],
            "youtube": [
                "youtube", "play youtube", "search youtube", "find on youtube",
                "video", "play video"
            ],
            "open google": [
                "open google", "search google", "google search", "find on google",
                "google", "search the web", "web search"
            ],
            "wikipedia": [
                "wikipedia", "wiki search", "search wiki", "find on wikipedia",
                "wiki", "search wikipedia", "look up on wikipedia"
            ],
            "give me news": [
                "give me news", "show news", "latest news", "what's new",
                "current news", "news update", "tell me the news"
            ],
            "weather": [
                "weather", "what's the weather", "weather forecast", "temperature",
                "how's the weather", "is it going to rain", "weather report"
            ],
            "send email": [
                "send email", "compose email", "write email", "new email",
                "email", "send mail", "write mail"
            ],
            "set reminder": [
                "set reminder", "create reminder", "remind me", "new reminder",
                "set alarm", "reminder"
            ],
            "stock price": [
                "stock price", "check stocks", "stock market", "stock value",
                "stocks", "share price", "stock quote"
            ],
            "exchange rate": [
                "exchange rate", "currency exchange", "convert currency",
                "exchange currency", "currency conversion", "forex"
            ],
            "generate password": [
                "generate password", "create password", "new password",
                "random password", "password", "secure password"
            ],
            "crypto price": [
                "crypto price", "check crypto", "cryptocurrency price",
                "crypto value", "bitcoin price", "ethereum price"
            ],
            "battery status": [
                "battery status", "check battery", "battery level",
                "power status", "battery", "power level"
            ],
            "current time": [
                "current time", "what's the time", "tell me the time",
                "time please", "what time is it", "time"
            ],
            "date and time": [
                "date and time", "what's the date", "tell me the date",
                "date please", "what day is it", "date"
            ],
            "ask gpt": [
                "ask gpt", "chat gpt", "ask chat gpt", "question for gpt",
                "gpt", "ai chat"
            ],
            "ask to ai": [
                "ask to ai", "free gpt", "ask ai", "question for ai",
                "ai", "artificial intelligence"
            ]
        }

        # Command handlers dictionary
        command_handlers = {
            "how are you": lambda: self.speak("I am absolutely fine, sir. What about you?"),
            "open command prompt": lambda: os.system('start cmd'),
            "open camera": lambda: sp.run('start microsoft.windows.camera:', shell=True),
            "open notepad": lambda: os.system('notepad'),
            "open discord": lambda: self.open_application(r"%LOCALAPPDATA%\Discord\app-*\Discord.exe"),
            "open vs code": lambda: self.open_application("vs code"),  # Special handling in open_application
            "ip address": self.handle_ip_address,
            "youtube": self.handle_youtube,
            "open google": self.handle_google_search,
            "wikipedia": self.handle_wikipedia,
            "give me news": self.handle_news,
            "weather": self.handle_weather,
            "send email": self.handle_email,
            "set reminder": self.handle_reminder,
            "stock price": self.handle_stock_price,
            "exchange rate": self.handle_exchange_rate,
            "generate password": self.handle_password,
            "crypto price": self.handle_crypto_price,
            "battery status": self.handle_battery_status,
            "current time": self.handle_datetime,
            "date and time": self.handle_datetime,
            "ask gpt": self.handle_gpt,
            "ask to ai": self.handle_free_gpt
        }

        # Find matching command using improved matching logic
        matched_command = None
        max_similarity = 0
        
        for cmd, variations in command_patterns.items():
            # Check for exact matches first
            if query in variations:
                matched_command = cmd
                break
            
            # Check if any variation is contained within the query
            for variation in variations:
                if variation in query:
                    matched_command = cmd
                    break
            
            if matched_command:
                break
                
            # Check if query contains most of the words from any variation
            for variation in variations:
                variation_words = set(variation.split())
                query_words = set(query.split())
                common_words = variation_words.intersection(query_words)
                
                similarity = len(common_words) / max(len(variation_words), len(query_words))
                if similarity > max_similarity and similarity > 0.5:  # Threshold for similarity
                    max_similarity = similarity
                    matched_command = cmd

        if matched_command:
            try:
                logger.info(f"Executing command: {matched_command}")
                handler = command_handlers[matched_command]
                handler()
            except Exception as e:
                error_msg = f"Error executing command '{matched_command}': {str(e)}"
                logger.error(error_msg)
                self.speak(f"Sorry, there was an error: {str(e)}")
        else:
            logger.warning(f"No matching command found for: {query}")
            self.speak("I'm not sure what you want me to do. Could you please rephrase that?")

    def open_application(self, path: str) -> None:
        """Open an application from the specified path"""
        try:
            # Common paths for VS Code
            vscode_paths = [
                r"C:\Program Files\Microsoft VS Code\Code.exe",
                r"C:\Users\%USERNAME%\AppData\Local\Programs\Microsoft VS Code\Code.exe",
                r"C:\Program Files (x86)\Microsoft VS Code\Code.exe"
            ]
            
            # If path contains VS Code, try all possible paths
            if "vs code" in path.lower():
                for vscode_path in vscode_paths:
                    expanded_path = os.path.expandvars(vscode_path)
                    if Path(expanded_path).exists():
                        os.startfile(expanded_path)
                        self.speak("Opening Visual Studio Code")
                        return
                self.speak("Could not find Visual Studio Code installation")
                return

            # For other applications, try the direct path first
            if Path(path).exists():
                os.startfile(path)
                self.speak(f"Opening {Path(path).name}")
            else:
                # Try expanding environment variables
                expanded_path = os.path.expandvars(path)
                if Path(expanded_path).exists():
                    os.startfile(expanded_path)
                    self.speak(f"Opening {Path(expanded_path).name}")
                else:
                    self.speak("Application path not found")
                    
        except Exception as e:
            logger.error(f"Error opening application: {str(e)}")
            self.speak("Error opening application")

    # Handler methods for different commands
    def handle_ip_address(self) -> None:
        ip_address = find_my_ip()
        self.speak(f"Your IP address is {ip_address}")
        print(f"Your IP address is {ip_address}")

    def handle_youtube(self) -> None:
        if self.web_mode:
            self.last_response = "What do you want to play on YouTube?"
            self.pending_input = "youtube_query"
            return

        self.speak("What do you want to play on YouTube?")
        video = self.take_command()
        self._process_youtube_query(video)

    def _process_youtube_query(self, query):
        youtube(query)
        self.speak(f"Playing {query} on YouTube")

    def handle_google_search(self) -> None:
        if self.web_mode:
            self.last_response = "What do you want to search on Google?"
            self.pending_input = "google_query"
            return

        self.speak("What do you want to search on Google?")
        search_query = self.take_command()
        self._process_google_search(search_query)

    def _process_google_search(self, query):
        search_on_google(query)
        self.speak(f"Searching for {query} on Google")

    def handle_wikipedia(self) -> None:
        if self.web_mode:
            self.last_response = "What do you want to search on Wikipedia?"
            self.pending_input = "wiki_query"
            return

        self.speak("What do you want to search on Wikipedia?")
        search_term = self.take_command()
        self._process_wiki_search(search_term)

    def _process_wiki_search(self, query):
        results = search_on_wikipedia(query)
        self.speak("Here's what I found on Wikipedia:")
        self.speak(results)

    def handle_news(self) -> None:
        self.speak("Fetching the latest news headlines...")
        headlines = get_news()
        for headline in headlines:
            self.speak(headline)
        print("\n".join(headlines))

    def handle_weather(self) -> None:
        """Improved weather handling with better voice interaction"""
        try:
            self.speak("What city would you like to know the weather for?")
            
            if self.web_mode:
                self.last_response = "Please enter your city name:"
                self.pending_input = "weather_city"
                return

            # Wait for voice input
            city = None
            while not city or city == "None":
                city = self.take_command()
                if city == "None":
                    self.speak("I didn't catch that. Please say the city name again.")
            
            self._process_weather(city)
            
        except Exception as e:
            logger.error(f"Error in weather handling: {str(e)}")
            self.speak("I had trouble processing your request. Please try again.")

    def _process_weather(self, city):
        """Process weather request with comprehensive weather information"""
        try:
            self.speak(f"Fetching weather details for {city}...")
            weather_data = weather_forecast(city)
            
            if not weather_data or not any(weather_data):
                self.speak(f"Sorry, I couldn't find weather information for {city}")
                return
                
            weather, temp, feels_like, humidity, wind_speed = weather_data
            
            # Construct detailed weather response with clear temperature units
            response = (
                f"Current weather in {city}: {weather}. "
                f"Temperature is {temp} degrees Celsius "
                f"(feels like {feels_like} degrees Celsius). "
                f"Humidity is {humidity}% with wind speed of {wind_speed} meters per second."
            )
            
            self.speak(response)
            print(response)  # Also print the response for better visibility
            
        except Exception as e:
            logger.error(f"Error getting weather: {str(e)}")
            self.speak(f"Sorry, I had trouble getting weather information for {city}. Please try again.")

    def handle_email(self) -> None:
        """Handle email with voice input"""
        try:
            if self.web_mode:
                self.last_response = "Please enter the recipient's email:"
                self.pending_input = "email_recipient"
                return

            # Get recipient email
            self.speak("Who would you like to send the email to?")
            receiver_email = self.handle_input_with_voice("Please say the email address.")
            
            if not receiver_email:
                self.speak("I couldn't understand the email address. Please try again later.")
                return
                
            # Get subject
            self.speak("What should be the subject of the email?")
            subject = self.handle_input_with_voice("Please say the subject.")
            
            if not subject:
                self.speak("I couldn't understand the subject. Please try again later.")
                return
                
            # Get message
            self.speak("What message would you like to send?")
            message = self.handle_input_with_voice("Please say your message.")
            
            if not message:
                self.speak("I couldn't understand the message. Please try again later.")
                return
                
            self._process_email_final(receiver_email, subject, message)
            
        except Exception as e:
            logger.error(f"Error in email handling: {str(e)}")
            self.speak("I had trouble processing your email request. Please try again.")

    def handle_reminder(self) -> None:
        if self.web_mode:
            self.last_response = "What task should I remind you about?"
            self.pending_input = "reminder_task"
            return

        self.speak("What task should I remind you about?")
        task = self.take_command()
        self._process_reminder_step1(task)

    def _process_reminder_step1(self, task):
        if self.web_mode:
            self.last_response = "At what time? (e.g., 10:30 AM)"
            self.pending_input = "reminder_time"
            self._temp_reminder = {"task": task}
            return

        self.speak("At what time?")
        time = input("Enter time (e.g., 10:30 AM): ")
        self._process_reminder_final(task, time)

    def _process_reminder_final(self, task, time):
        response = set_reminder(task, time)
        self.speak(response)

    def handle_stock_price(self) -> None:
        if self.web_mode:
            self.last_response = "Which stock price would you like to check? (Enter symbol)"
            self.pending_input = "stock_symbol"
            return

        self.speak("Which stock price would you like to check?")
        stock_symbol = input("Enter Stock Symbol: ").upper()
        self._process_stock_price(stock_symbol)

    def _process_stock_price(self, symbol):
        response = get_stock_price(symbol.upper())
        self.speak(response)

    def handle_exchange_rate(self) -> None:
        if self.web_mode:
            self.last_response = "Enter base currency (e.g., USD):"
            self.pending_input = "exchange_base"
            return

        self.speak("Which currencies would you like to convert?")
        base_currency = input("Enter base currency (e.g., USD): ").upper()
        self._process_exchange_step1(base_currency)

    def _process_exchange_step1(self, base_currency):
        if self.web_mode:
            self.last_response = "Enter target currency (e.g., EUR):"
            self.pending_input = "exchange_target"
            self._temp_exchange = {"base": base_currency}
            return

        self.speak("Enter target currency:")
        target_currency = input("Enter target currency (e.g., EUR): ").upper()
        self._process_exchange_final(base_currency, target_currency)

    def _process_exchange_final(self, base_currency, target_currency):
        response = get_exchange_rate(base_currency.upper(), target_currency.upper())
        self.speak(response)

    def handle_password(self) -> None:
        """Handle password generation with voice input"""
        try:
            if self.web_mode:
                self.last_response = "What length should the password be? (default is 12)"
                self.pending_input = "password_length"
                return

            self.speak("What length would you like for the password?")
            length_str = self.handle_input_with_voice("Please say a number for the password length.")
            
            if length_str and length_str.isdigit():
                length = int(length_str)
            else:
                self.speak("Using default length of 12 characters.")
                length = 12
            
            self._process_password(length)
            
        except Exception as e:
            logger.error(f"Error in password handling: {str(e)}")
            self.speak("I had trouble processing your request. Using default length of 12.")
            self._process_password(12)

    def _process_password(self, length):
        try:
            length = int(length) if length else 12
            response = generate_password(length)
            self.speak(response)
        except ValueError:
            self.speak("Invalid length. Using default length of 12.")
            response = generate_password(12)
            self.speak(response)

    def handle_crypto_price(self) -> None:
        if self.web_mode:
            self.last_response = "Which cryptocurrency price would you like to check? (e.g., btc, eth)"
            self.pending_input = "crypto_symbol"
            return

        self.speak("Which cryptocurrency price would you like to check?")
        crypto_symbol = input("Enter cryptocurrency symbol (e.g., btc, eth): ").lower()
        self._process_crypto_price(crypto_symbol)

    def _process_crypto_price(self, symbol):
        response = get_crypto_price(symbol.lower())
        self.speak(response)

    def handle_battery_status(self) -> None:
        response = get_battery_status()
        self.speak(response)
        print(response)

    def handle_datetime(self) -> None:
        response = get_current_datetime()
        self.speak(response)
        print(response)

    def handle_gpt(self) -> None:
        if self.web_mode:
            self.last_response = "What would you like to ask GPT?"
            self.pending_input = "gpt_query"
            return

        self.speak("What would you like to ask GPT?")
        user_prompt = input("Enter your question: ")
        self._process_gpt_query(user_prompt)

    def _process_gpt_query(self, query):
        response = chat_with_gpt(query)
        self.speak(response)

    def handle_free_gpt(self) -> None:
        if self.web_mode:
            self.last_response = "What would you like to ask?"
            self.pending_input = "free_gpt_query"
            return

        self.speak("What would you like to ask?")
        user_prompt = input("Enter your question: ")
        self._process_free_gpt_query(user_prompt)

    def _process_free_gpt_query(self, query):
        response = chat_with_free_gpt(query)
        self.speak(response)

    def process_pending_input(self, user_input):
        """Handle pending input from web interface"""
        if not self.pending_input:
            return False

        input_type = self.pending_input
        self.pending_input = None  # Reset pending input

        handlers = {
            "weather_city": self._process_weather,
            "youtube_query": self._process_youtube_query,
            "google_query": self._process_google_search,
            "wiki_query": self._process_wiki_search,
            "gpt_query": self._process_gpt_query,
            "free_gpt_query": self._process_free_gpt_query,
            "stock_symbol": self._process_stock_price,
            "crypto_symbol": self._process_crypto_price,
            "password_length": self._process_password,
        }

        # Multi-step handlers
        if input_type == "email_recipient":
            self._process_email_step1(user_input)
        elif input_type == "email_subject":
            self._process_email_step2(self._temp_email["recipient"], user_input)
        elif input_type == "email_message":
            self._process_email_final(self._temp_email["recipient"], self._temp_email["subject"], user_input)
        elif input_type == "reminder_task":
            self._process_reminder_step1(user_input)
        elif input_type == "reminder_time":
            self._process_reminder_final(self._temp_reminder["task"], user_input)
        elif input_type == "exchange_base":
            self._process_exchange_step1(user_input)
        elif input_type == "exchange_target":
            self._process_exchange_final(self._temp_exchange["base"], user_input)
        elif input_type in handlers:
            handlers[input_type](user_input)

        return True

    def handle_stop(self) -> None:
        """Handle the stop command"""
        self.speak("Goodbye! Have a great day!")
        logger.info("Stop command received. Shutting down...")
        self.should_stop = True
        self.stop_listening()
        if not self.web_mode:
            os._exit(0)  # Force exit in desktop mode

    def handle_input_with_voice(self, prompt: str, max_attempts: int = 3) -> str:
        """Generic handler for voice input with retries"""
        for attempt in range(max_attempts):
            self.speak(prompt)
            response = self.take_command()
            
            if response and response != "None":
                return response
            
            if attempt < max_attempts - 1:
                self.speak("I didn't catch that. Please try again.")
            
        return None

    def run(self):
        """Main loop to run the voice assistant"""
        self.greet_me()
        while True:
            if self.should_stop:
                break
            if self.listening:
                query = self.take_command()
                if self.should_stop:
                    break
                self.execute_command(query)

# Only run this if the file is run directly (not imported)
if __name__ == '__main__':
    assistant = VoiceAssistant()
    assistant.run()
