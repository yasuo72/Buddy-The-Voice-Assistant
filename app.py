import logging
import queue
import threading
import time

from flask import Flask, jsonify, render_template, request
from flask_cors import CORS

from main import VoiceAssistant

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[logging.FileHandler('flask_app.log'), logging.StreamHandler()]
)
logger = logging.getLogger(__name__)

app = Flask(__name__)
CORS(app)  # Enable CORS for all routes

# Initialize the assistant with web mode enabled
assistant = VoiceAssistant(web_mode=True)
command_queue = queue.Queue()
response_queue = queue.Queue()


class ResponseCapture:
    def __init__(self):
        self.response = None
        self.responses = []

    def speak(self, text):
        self.response = text
        self.responses.append(text)
        logger.info(f"Assistant response: {text}")


def process_commands():
    """Process commands from the queue with optimized response handling."""
    while True:
        try:
            command = command_queue.get()
            response_capture = ResponseCapture()
            original_speak = assistant.speak
            assistant.speak = response_capture.speak

            try:
                if command.get('type') == 'voice':
                    handle_voice_command(command, response_capture)
                else:
                    handle_text_command(command, response_capture)

            except Exception as e:
                logger.error(f"Error processing command: {str(e)}")
                response_capture.speak(str(e))

            finally:
                # Restore original speak method
                assistant.speak = original_speak

                # Prepare response, filtering out unnecessary messages
                responses = [r for r in response_capture.responses if not any(
                    skip in r.lower() for skip in [
                        "i heard:",
                        "processing your request:",
                        "command processed",
                        "please speak clearly",
                        "trying again"
                    ]
                )]

                last_response = responses[-1] if responses else "Command processed"

                response_queue.put({
                    'message': last_response,
                    'requires_input': False,
                    'all_responses': responses,
                    'success': True,
                    'should_stop': assistant.should_stop
                })

                command_queue.task_done()

        except Exception as e:
            logger.error(f"Critical error in command processing: {str(e)}")
            response_queue.put({
                'message': str(e),
                'requires_input': False,
                'all_responses': [str(e)],
                'success': False,
                'should_stop': False
            })
            command_queue.task_done()


def handle_voice_command(command, response_capture):
    """Handle voice commands with improved error handling and feedback."""
    assistant.listening = True
    logger.info("Starting voice command processing...")

    # Check microphone initialization
    if not hasattr(assistant, 'microphone'):
        raise Exception("Microphone is not properly initialized. Please check your settings.")

    # Get voice input with retries
    max_attempts = 2  # Reduced from 3
    query = None

    for attempt in range(max_attempts):
        try:
            query = assistant.take_command()
            if query != "None":
                break

            if attempt < max_attempts - 1:
                response_capture.speak("Please speak clearly.")
                time.sleep(0.5)  # Reduced from 1

        except Exception as e:
            logger.error(f"Error in voice recognition attempt {attempt + 1}: {str(e)}")
            if attempt < max_attempts - 1:
                response_capture.speak("There was an error. Trying again...")
                time.sleep(0.5)  # Reduced from 1
            else:
                raise Exception("Failed to recognize voice command")

    if query and query != "None":
        # Skip the "I heard" message to reduce verbosity
        assistant.execute_command(query)
    else:
        raise Exception("Could not understand. Please try again.")
    
    assistant.listening = False


def handle_text_command(command, response_capture):
    """Handle text commands with minimal feedback."""
    query = command.get('content', '').strip()
    if not query:
        raise Exception("Please provide a command to process.")

    # Skip the "Processing your request" message
    assistant.execute_command(query)


# Start command processing thread
command_thread = threading.Thread(target=process_commands, daemon=True)
command_thread.start()


@app.route('/')
def home():
    """Render the home page with initial greeting."""
    try:
        response_capture = ResponseCapture()
        original_speak = assistant.speak
        assistant.speak = response_capture.speak
        assistant.greet_me()
        assistant.speak = original_speak
        return render_template('index.html', initial_greeting=response_capture.responses)
    except Exception as e:
        logger.error(f"Error in home route: {str(e)}")
        return render_template('index.html', initial_greeting=["Hello! How may I assist you?"])


@app.route('/send_command', methods=['POST'])
def send_command():
    """Handle incoming commands from the web interface."""
    try:
        data = request.json
        command_type = data.get('type', 'text')
        content = data.get('content', '')

        if not content and command_type == 'text':
            return jsonify({
                'status': 'error',
                'message': 'Please provide a command',
                'requires_input': False,
                'success': False
            })

        command_queue.put({
            'type': command_type,
            'content': content
        })

        try:
            response = response_queue.get(timeout=30)
            return jsonify({
                'status': 'success',
                **response
            })
        except queue.Empty:
            return jsonify({
                'status': 'error',
                'message': 'Command processing timeout',
                'requires_input': False,
                'success': False
            })

    except Exception as e:
        logger.error(f"Error in send_command: {str(e)}")
        return jsonify({
            'status': 'error',
            'message': str(e),
            'requires_input': False,
            'success': False
        })


@app.errorhandler(404)
def not_found_error(error):
    """Handle 404 errors."""
    return jsonify({
        'status': 'error',
        'message': 'Resource not found',
        'success': False
    }), 404


@app.errorhandler(500)
def internal_error(error):
    """Handle 500 errors."""
    return jsonify({
        'status': 'error',
        'message': 'Internal server error',
        'success': False
    }), 500


if __name__ == '__main__':
    app.run(debug=True, port=5000)