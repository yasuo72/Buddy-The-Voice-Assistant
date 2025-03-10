import logging
import os
import subprocess as sp
import time
import json
from datetime import datetime
from pathlib import Path
from typing import Optional

import keyboard
import pyttsx3
import speech_recognition as sr
from decouple import config

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
        self.engine.setProperty('rate', 180)
        voices = self.engine.getProperty('voices')
        self.engine.setProperty('voice', voices[0].id)

        # Load Configurations
        self.user = config('USER', default="User  ")
        self.bot = config('BOT', default="Jarvis")
        self.listening = False
        self.web_mode = web_mode
        self.pending_input = None
        self.last_response = None
        self.should_stop = False

        # Load responses from JSON file
        self.load_responses()

        # Initialize speech recognizer and microphone
        self.initialize_microphone()

        if not web_mode:
            self.setup_hotkeys()

    def load_responses(self):
        """Load responses from a JSON file."""
        try:
            with open('responses.json', 'r') as file:
                self.responses = json.load(file)
            logger.info("Responses loaded successfully.")
        except Exception as e:
            logger.error(f"Error loading responses: {str(e)}")
            self.responses = {}

    def initialize_microphone(self):
        """Initialize the microphone for speech recognition."""
        try:
            self.recognizer = sr.Recognizer()
            mics = sr.Microphone.list_microphone_names()
            logger.info(f"Available microphones: {mics}")

            mic_index = self.select_microphone(mics)
            if mic_index is not None:
                self.microphone = sr.Microphone(device_index=mic_index)
                with self.microphone as source:
                    self.recognizer.energy_threshold = 4000
                    self.recognizer.dynamic_energy_threshold = True
                    self.recognizer.adjust_for_ambient_noise(source, duration=1)
                    logger.info("Microphone initialized successfully")
            else:
                raise Exception("No suitable microphone found")
        except Exception as e:
            logger.error(f"Error initializing microphone: {str(e)}")
            self.speak("Warning: There was an issue initializing the microphone. Voice commands may not work properly.")

    def select_microphone(self, mics):
        """Select the best microphone based on keywords."""
        preferred_keywords = ["array", "mic", "input"]
        mic_index = None

        for index, name in enumerate(mics):
            name_lower = name.lower()
            if any(keyword in name_lower for keyword in preferred_keywords) and "output" not in name_lower:
                mic_index = index
                logger.info(f"Selected microphone: {name}")
                break

        if mic_index is None and len(mics) > 0:
            for index, name in enumerate(mics):
                if "output" not in name.lower():
                    mic_index = index
                    logger.info(f"Using default microphone: {name}")
                    break

        return mic_index

    def setup_hotkeys(self):
        """Set up keyboard hotkeys for voice control."""
        keyboard.add_hotkey('k', self.start_listening)
        keyboard.add_hotkey('ctrl+alt+p', self.stop_listening)

    def speak(self, text: str) -> None:
        """Speak out the given text with optimized settings."""
        if text and isinstance(text, str):
            try:
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
        """Recognize and process user voice input with improved reliability."""
        query = "None"

        try:
            with self.microphone as source:
                logger.info("Listening...")
                self.recognizer.adjust_for_ambient_noise(source, duration=0.2)
                self.recognizer.energy_threshold = 2500
                self.recognizer.dynamic_energy_threshold = True
                self.recognizer.pause_threshold = 0.5

                try:
                    audio = self.recognizer.listen(source, timeout=5, phrase_time_limit=5)
                    logger.info("Audio captured, recognizing...")
                except Exception as e:
                    logger.error(f"Error capturing audio: {str(e)}")
                    return "None"

                try:
                    query = self.recognizer.recognize_google(audio)
                    if query and query.strip():
                        logger.info(f"Successfully recognized: '{query}'")
                        return query.lower().strip()
                except sr.UnknownValueError:
                    return "None"
                except sr.RequestError as e:
                    logger.error(f"Could not request results; {str(e)}")
                    return "None"

        except Exception as e:
            logger.error(f"Error in speech recognition: {str(e)}")
            return "None"

        return "None"

    def execute_command(self, query: str) -> None:
        """Execute the appropriate action based on the voice command."""
        if not query or query == "None":
            self.speak("I couldn't hear you clearly. Please try again.")
            return

        query = query.lower().strip()
        logger.info(f"Processing command: {query}")

        # Check for normal question answers
        response = self.get_response(query)
        if response:
            self.speak(response)
            return

        # Handle stop commands first
        stop_commands = ["stop", "exit", "quit", "bye", "goodbye", "shut down", "shutdown", "turn off"]
        if any(cmd in query for cmd in stop_commands):
            self.handle_stop()
            return

        # Handle search commands
        try:
            # YouTube commands
            if "youtube" in query or "play" in query:
                search_term = self.extract_search_term(query, ["youtube", "play", "on", "search", "for"])
                if search_term:
                    youtube(search_term)
                    self.speak(f"Playing {search_term} on YouTube")
                    return
                else:
                    self.speak("What would you like to play on YouTube?")
                    search_term = self.take_command()
                    if search_term != "None":
                        youtube(search_term)
                        self.speak(f"Playing {search_term} on YouTube")
                    return

            # Google search commands
            if "google" in query or "search" in query:
                search_term = self.extract_search_term(query, ["google", "search", "for", "on"])
                if search_term:
                    self.speak(f"Searching Google for {search_term}")
                    search_on_google(search_term)
                    return
                else:
                    self.speak("What would you like to search for?")
                    search_term = self.take_command()
                    if search_term != "None":
                        self.speak(f"Searching Google for {search_term}")
                        search_on_google(search_term)
                    return

            # Wikipedia commands
            if "wikipedia" in query:
                search_term = self.extract_search_term(query, ["wikipedia", "search", "for", "on", "wiki"])
                if search_term:
                    self.speak(f"Searching Wikipedia for {search_term}")
                    result = search_on_wikipedia(search_term)
                    self.speak(result)
                    return
                else:
                    self.speak("What would you like to look up on Wikipedia?")
                    search_term = self.take_command()
                    if search_term != "None":
                        self.speak(f"Searching Wikipedia for {search_term}")
                        result = search_on_wikipedia(search_term)
                        self.speak(result)
                    return

            # Handle other commands
            if "weather" in query:
                self.handle_weather()
            elif "news" in query:
                self.handle_news()
            elif "email" in query:
                self.handle_email()
            elif "reminder" in query:
                self.handle_reminder()
            elif "stock" in query:
                self.handle_stock_price()
            elif "exchange rate" in query:
                self.handle_exchange_rate()
            elif "password" in query:
                self.handle_password()
            elif "crypto" in query:
                self.handle_crypto_price()
            elif "battery" in query:
                self.handle_battery_status()
            elif "time" in query:
                self.handle_datetime()
            elif "gpt" in query or "chat" in query:
                self.handle_gpt()
            elif "open" in query:
                if "command prompt" in query or "cmd" in query:
                    os.system('start cmd')
                elif "camera" in query:
                    sp.run('start microsoft.windows.camera:', shell=True)
                elif "notepad" in query:
                    os.system('notepad')
                elif "discord" in query:
                    self.open_application(r"%LOCALAPPDATA%\Discord\app-*\Discord.exe")
                elif "vs code" in query or "visual studio code" in query:
                    self.open_application("vs code")
            else:
                self.speak("I'm not sure what you want me to do. Could you please rephrase that?")

        except Exception as e:
            logger.error(f"Error executing command: {str(e)}")
            self.speak(f"I encountered an error: {str(e)}")

    def get_response(self, query: str) -> Optional[str]:
        """Get a response from the loaded JSON data based on the query."""
        for key in self.responses:
            if key in query:
                return self.responses[key]
        return None

    def extract_search_term(self, query: str, words_to_remove: list) -> Optional[str]:
        """Extract search term from query by removing command words."""
        query_words = query.split()
        search_words = [word for word in query_words if word not in words_to_remove]
        return " ".join(search_words).strip() if search_words else None

    def handle_youtube(self, search_term: Optional[str] = None) -> None:
        """Handle YouTube commands with improved search term handling."""
        try:
            if not search_term:
                self.speak("What would you like to play on YouTube?")
                search_term = self.take_command()
                if search_term == "None":
                    self.speak("I couldn't understand what you want to play. Please try again.")
                    return

            if search_term:
                self.speak(f"Playing {search_term} on YouTube")
                youtube(search_term)
            else:
                self.speak("I couldn't understand what you want to play. Please try again.")
        except Exception as e:
            logger.error(f"Error in YouTube handling: {str(e)}")
            self.speak("Sorry, I had trouble playing that on YouTube")

    def handle_google_search(self, search_term: Optional[str] = None) -> None:
        """Handle Google search with improved search term handling."""
        try:
            if not search_term:
                self.speak("What would you like to search for on Google?")
                search_term = self.take_command()
                if search_term == "None":
                    self.speak("I couldn't understand what you want to search. Please try again.")
                    return

            if search_term:
                self.speak(f"Searching Google for {search_term}")
                search_on_google(search_term)
            else:
                self.speak("I couldn't understand what you want to search. Please try again.")
        except Exception as e:
            logger.error(f"Error in Google search: {str(e)}")
            self.speak("Sorry, I had trouble searching Google")

    def handle_wikipedia(self, search_term: Optional[str] = None) -> None:
        """Handle Wikipedia search with improved search term handling."""
        try:
            if not search_term:
                self.speak("What would you like to look up on Wikipedia?")
                search_term = self.take_command()
                if search_term == "None":
                    self.speak("I couldn't understand what you want to search. Please try again.")
                    return

            if search_term:
                self.speak(f"Searching Wikipedia for {search_term}")
                result = search_on_wikipedia(search_term)
                self.speak(result)
            else:
                self.speak("I couldn't understand what you want to search. Please try again.")
        except Exception as e:
            logger.error(f"Error in Wikipedia search: {str(e)}")
            self.speak("Sorry, I had trouble searching Wikipedia")

    def handle_news(self) -> None:
        """Handle news with better conversation flow."""
        try:
            self.speak("Here are the latest headlines:")
            headlines = get_news()

            if not headlines:
                self.speak("Sorry, I couldn't fetch any news at the moment.")
                return

            for headline in headlines[:3]:  # Limit to 3 headlines to avoid too much talking
                self.speak(headline)
                time.sleep(0.5)  # Brief pause between headlines

        except Exception as e:
            logger.error(f"Error fetching news: {str(e)}")
            self.speak("Sorry, I had trouble fetching the news.")

    def handle_weather(self, city=None) -> None:
        """Improved weather handling with better conversation flow."""
        try:
            if not city:
                self.speak("What city would you like to know the weather for?")
                city = self.take_command()

                if city == "None":
                    self.speak("I couldn't understand the city name. Please try again.")
                    return

            # Don't announce fetching, just get the data
            weather_data = weather_forecast(city)

            if not weather_data or not any(weather_data):
                self.speak(f"Sorry, I couldn't find weather information for {city}")
                return

            weather, temp, feels_like, humidity, wind_speed = weather_data

            # Format temperature values to be more natural
            temp = round(float(temp))
            feels_like = round(float(feels_like))

            response = (
                f"The weather in {city} is {weather}. "
                f"It's {temp} degrees Celsius, "
                f"feels like {feels_like} degrees. "
                f"Humidity is {humidity}% with wind speed of {wind_speed} meters per second."
            )

            self.speak(response)

        except Exception as e:
            logger.error(f"Error in weather handling: {str(e)}")
            self.speak("I had trouble getting the weather information. Please try again.")

    def handle_email(self) -> None:
        """Handle email with better conversation flow."""
        try:
            # Get recipient
            self.speak("Who would you like to send the email to?")
            receiver_email = self.take_command()
            if not receiver_email or receiver_email == "None":
                self.speak("I couldn't understand the email address.")
                return

            # Get subject
            self.speak("What should be the subject of the email?")
            subject = self.take_command()
            if not subject or subject == "None":
                self.speak("I couldn't understand the subject.")
                return

            # Get message
            self.speak("What message would you like to send?")
            message = self.take_command()
            if not message or message == "None":
                self.speak("I couldn't understand the message.")
                return

            # Send email
            try:
                response = send_email(receiver_email, subject, message)
                self.speak(response)
            except Exception as e:
                logger.error(f"Error sending email: {str(e)}")
                self.speak("Sorry, I couldn't send the email. Please check the email address and try again.")

        except Exception as e:
            logger.error(f"Error in email handling: {str(e)}")
            self.speak("I had trouble with the email process. Please try again.")

    def handle_reminder(self) -> None:
        """Handle reminders with better conversation flow."""
        # Get task
        self.speak("What should I remind you about?")
        task = self.take_command()
        if not task or task == "None":
            self.speak("I couldn't understand the task.")
            return

        # Get time
        self.speak("At what time? Please say the time like 10:30 AM.")
        time_str = self.take_command()
        if not time_str or time_str == "None":
            self.speak("I couldn't understand the time.")
            return

        try:
            response = set_reminder(task, time_str)
            self.speak(response)
        except Exception as e:
            logger.error(f"Error setting reminder: {str(e)}")
            self.speak(
                "Sorry, I couldn't set the reminder. Please make sure to specify the time in the correct format.")

    def handle_stock_price(self) -> None:
        """Handle stock price check with better conversation flow."""
        self.speak("Which stock would you like to check? Please say the symbol.")
        stock_symbol = self.take_command()

        if stock_symbol and stock_symbol != "None":
            try:
                response = get_stock_price(stock_symbol.upper())
                self.speak(response)
            except Exception as e:
                logger.error(f"Error getting stock price: {str(e)}")
                self.speak(f"Sorry, I couldn't find the stock price for {stock_symbol}")
        else:
            self.speak("I couldn't understand the stock symbol.")

    def handle_exchange_rate(self) -> None:
        """Handle currency exchange with better conversation flow."""
        # Get base currency
        self.speak("What is the base currency? For example, USD for US Dollar.")
        base_currency = self.take_command()

        if not base_currency or base_currency == "None":
            self.speak("I couldn't understand the base currency.")
            return

        # Get target currency
        self.speak("What is the target currency? For example, EUR for Euro.")
        target_currency = self.take_command()

        if not target_currency or target_currency == "None":
            self.speak("I couldn't understand the target currency.")
            return

        try:
            response = get_exchange_rate(base_currency.upper(), target_currency.upper())
            self.speak(response)
        except Exception as e:
            logger.error(f"Error getting exchange rate: {str(e)}")
            self.speak("Sorry, I couldn't get the exchange rate.")

    def handle_password(self) -> None:
        """Handle password generation with voice input."""
        try:
            if self.web_mode:
                self.last_response = "What length should the password be? (default is 12)"
                self.pending_input = "password_length"
                return

            self.speak("What length would you like for the password?")
            length_str = self.take_command()

            length = int(length_str) if length_str and length_str.isdigit() else 12
            self._process_password(length)

        except Exception as e:
            logger.error(f"Error in password handling: {str(e)}")
            self.speak("I had trouble processing your request. Using default length of 12.")
            self._process_password(12)

    def _process_password(self, length):
        try:
            response = generate_password(length)
            self.speak(response)
        except ValueError:
            self.speak("Invalid length. Using default length of 12.")
            response = generate_password(12)
            self.speak(response)

    def handle_crypto_price(self) -> None:
        """Handle cryptocurrency price check with better conversation flow."""
        self.speak("Which cryptocurrency would you like to check?")
        crypto = self.take_command()

        if crypto and crypto != "None":
            try:
                response = get_crypto_price(crypto.lower())
                self.speak(response)
            except Exception as e:
                logger.error(f"Error getting crypto price: {str(e)}")
                self.speak(f"Sorry, I couldn't find the price for {crypto}")
        else:
            self.speak("I couldn't understand the cryptocurrency name.")

    def handle_battery_status(self) -> None:
        response = get_battery_status()
        self.speak(response)
        print(response)

    def handle_datetime(self) -> None:
        response = get_current_datetime()
        self.speak(response)
        print(response)

    def handle_gpt(self) -> None:
        """Handle GPT interaction with better conversation flow."""
        self.speak("What would you like to ask?")
        question = self.take_command()

        if question and question != "None":
            try:
                response = chat_with_gpt(question)
                self.speak(response)
            except Exception as e:
                logger.error(f"Error with GPT: {str(e)}")
                self.speak("Sorry, I had trouble getting a response from GPT.")
        else:
            self.speak("I couldn't understand your question.")

    def handle_free_gpt(self) -> None:
        """Handle free GPT interaction with voice input."""
        self.speak("What would you like to ask?")
        user_prompt = self.take_command()

        if user_prompt and user_prompt != "None":
            response = chat_with_free_gpt(user_prompt)
            self.speak(response)
        else:
            self.speak("I couldn't understand your question. Please try again.")

    def handle_stop(self) -> None:
        """Handle the stop command."""
        self.speak("Goodbye! Have a great day!")
        logger.info("Stop command received. Shutting down...")
        self.should_stop = True
        self.stop_listening()
        if not self.web_mode:
            os._exit(0)  # Force exit in desktop mode

    def run(self):
        """Main loop to run the voice assistant."""
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