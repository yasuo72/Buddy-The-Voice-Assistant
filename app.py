import logging
import queue
import threading
import time

from flask import Flask, jsonify, render_template, request

from main import VoiceAssistant

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[logging.FileHandler('flask_app.log'), logging.StreamHandler()]
)
logger = logging.getLogger(__name__)

app = Flask(__name__)
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
    while True:
        try:
            command = command_queue.get()
            response_capture = ResponseCapture()
            # Temporarily replace speak method to capture response
            original_speak = assistant.speak
            assistant.speak = response_capture.speak

            if command.get('type') == 'text':
                # Check if this is a stop command
                if any(cmd in command['content'].lower() for cmd in ["stop", "exit", "quit", "bye", "goodbye", "shut down", "shutdown", "turn off"]):
                    assistant.handle_stop()
                    response_queue.put({
                        'message': "Goodbye! Have a great day!",
                        'requires_input': False,
                        'all_responses': ["Goodbye! Have a great day!"],
                        'success': True,
                        'should_stop': True
                    })
                    command_queue.task_done()
                    continue

                # Check if this is a response to a pending input
                if assistant.pending_input and command.get('is_response'):
                    assistant.process_pending_input(command['content'])
                else:
                    # Process text command
                    query = command['content'].lower()
                    assistant.execute_command(query)
            elif command.get('type') == 'voice':
                # Process voice command
                assistant.listening = True
                logger.info("Starting voice command processing...")
                
                # First attempt
                query = assistant.take_command()
                if query == "None":
                    # Second attempt if first fails
                    logger.info("First attempt failed, trying again...")
                    response_capture.speak("I didn't catch that. Please speak again.")
                    query = assistant.take_command()
                
                if query != "None":
                    # Check if this is a stop command
                    if any(cmd in query.lower() for cmd in ["stop", "exit", "quit", "bye", "goodbye", "shut down", "shutdown", "turn off"]):
                        assistant.handle_stop()
                        response_queue.put({
                            'message': "Goodbye! Have a great day!",
                            'requires_input': False,
                            'all_responses': ["Goodbye! Have a great day!"],
                            'success': True,
                            'should_stop': True
                        })
                        command_queue.task_done()
                        continue

                    # Add user's voice input to responses
                    response_capture.responses.append(f"You said: {query}")
                    # Execute the command
                    assistant.execute_command(query.lower())
                else:
                    response_capture.speak("I'm having trouble understanding. Please try speaking clearly and check your microphone.")
                
                assistant.listening = False

            # Restore original speak method
            assistant.speak = original_speak

            # Put the response in the response queue
            response = response_capture.responses[-1] if response_capture.responses else "Command processed successfully"
            response_queue.put({
                'message': response,
                'requires_input': assistant.pending_input is not None,
                'input_type': assistant.pending_input,
                'all_responses': response_capture.responses,
                'success': True,
                'should_stop': assistant.should_stop
            })
            command_queue.task_done()
        except Exception as e:
            error_msg = f"Error processing command: {str(e)}"
            logger.error(error_msg)
            response_queue.put({
                'message': error_msg,
                'requires_input': False,
                'all_responses': [error_msg],
                'success': False,
                'should_stop': False
            })


# Start the command processing thread
command_thread = threading.Thread(target=process_commands, daemon=True)
command_thread.start()


@app.route('/')
def home():
    # Initialize assistant with greeting
    response_capture = ResponseCapture()
    original_speak = assistant.speak
    assistant.speak = response_capture.speak
    assistant.greet_me()
    assistant.speak = original_speak
    
    return render_template('index.html', initial_greeting=response_capture.responses)


@app.route('/send_command', methods=['POST'])
def send_command():
    try:
        data = request.json
        command_type = data.get('type')
        content = data.get('content')
        is_response = data.get('is_response', False)

        if command_type in ['text', 'voice']:
            command_queue.put({
                'type': command_type,
                'content': content,
                'is_response': is_response
            })

            # Wait for the response with a timeout
            try:
                response = response_queue.get(timeout=30)  # Increased timeout to 30 seconds
                return jsonify({
                    'status': 'success',
                    'message': response.get('message', ''),
                    'requires_input': response.get('requires_input', False),
                    'input_type': response.get('input_type', None),
                    'all_responses': response.get('all_responses', []),
                    'success': response.get('success', True)
                })
            except queue.Empty:
                return jsonify({
                    'status': 'error',
                    'message': 'Command processing timeout. Please try again.',
                    'requires_input': False,
                    'success': False
                })

        return jsonify({
            'status': 'error',
            'message': 'Invalid command type',
            'requires_input': False,
            'success': False
        })
    except Exception as e:
        error_msg = f"Error processing request: {str(e)}"
        logger.error(error_msg)
        return jsonify({
            'status': 'error',
            'message': error_msg,
            'requires_input': False,
            'success': False
        })


if __name__ == '__main__':
    app.run(debug=True)
