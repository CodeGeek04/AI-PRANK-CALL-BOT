from flask import Flask, request, send_from_directory, Response
from twilio.twiml.voice_response import VoiceResponse, Say
from twilio.rest import Client
import openai
import requests
import os
import time 
import speech_recognition as sr
import whisper
import json

def save_to_file(phone_number, role, message):
    filename = "m" + phone_number.replace('+', '') + ".txt"
    entry = {"role": role, "content": message}
    with open(filename, 'a') as file:
        file.write(json.dumps(entry) + "\n")
    return filename

model = whisper.load_model("base")

app = Flask(__name__)

# Load environment variables
# openai_key = os.environ.get('OPENAI_API_KEY')
openai_key = "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"
elevenlabs_key = '748cff06f599569691dea26649d8222a'
voice_id = '21m00Tcm4TlvDq8ikWAM'

#TWILIO
ACCOUNT_SID = 'ACb7547f75b3ac783503fa8d94c1fddea8'
AUTH_TOKEN = '7bf0ab2b9d6eff89f75f60b8bc67565a'

# in

# @app.route('/', methods=['GET', 'POST'])
# def index():
#     return "Hello World!"

@app.route('/incoming_call', methods=['GET', 'POST'])
def incoming_call():
    caller_number = request.values.get('From')  # Get the caller's phone number
    response = VoiceResponse()
    intro = "Hello there!! Is your refrigerator running?"
    with open("m" + caller_number.replace('+', '') + ".txt", 'w') as file:  # Open in write mode
        pass
    save_to_file(caller_number, "assistant", intro)  # Save bot's message to file
    response.play(text_to_speech(intro))
    time.sleep(1)
    response.record(action='/process_audio', recording_status_callback_event='completed',
                    recording_format='wav', timeout=2, play_beep=False, Transcribe=True)
    return Response(str(response), 200, mimetype='application/xml')


@app.route('/process_audio', methods=['POST', 'GET'])
def process_audio():
    caller_number = request.values.get('From')
    recording_url = request.values.get('RecordingUrl')
    transcribed_text = transcribe_audio(recording_url)
    save_to_file(caller_number, "user", transcribed_text)  # Save user's response to file
    
    # Get all conversation from the file
    filename = "m" + caller_number.replace('+', '') + ".txt"
    with open(filename, 'r') as file:
        entries = [json.loads(line.strip()) for line in file.readlines()]
    messages = [{"role": entry["role"], "content": entry["content"]} for entry in entries]
    
    gpt3_response = get_gpt3_response(messages)
    save_to_file(caller_number, "assistant", gpt3_response)  # Save bot's response to file
    tts_audio_url = text_to_speech(gpt3_response)

    response = VoiceResponse()
    response.play(tts_audio_url)
    response.record(action='/process_audio', recording_status_callback_event='completed',
                    recording_format='wav', timeout=2, play_beep=False, Transcribe=True)
    
    return Response(str(response), 200, mimetype='application/xml')


def transcribe_audio(recording_url, model = None):
    time.sleep(1)
    
    # Download the audio file from the recording_url
    audio_response = requests.get(recording_url, stream=True, auth=(ACCOUNT_SID, AUTH_TOKEN))
    
    # Check if the request was successful
    if audio_response.status_code == 200:
        audio_file_name = "audio_recording.wav"
        
        # Save the audio file
        with open(audio_file_name, "wb") as audio_file:
            for chunk in audio_response.iter_content(chunk_size=128):
                audio_file.write(chunk)
        
        try:
            # Transcribe the audio
            recognizer = sr.Recognizer()
            file_path = "audio_recording.wav"
            
            # Load the audio file
            with sr.AudioFile(file_path) as source:
                audio_data = recognizer.record(source)
                
                try:
                    transcribed_text = recognizer.recognize_google(audio_data)
                    print("Transcription: " + transcribed_text)
                    return transcribed_text
                except Exception as e:
                    print("ERROR: ", e)
                    return "What??"
        except Exception as e:
            print("ERROR: ", e)
            return "What??"
    else:
        print(f"Failed to download audio. Status code: {audio_response.status_code}")
        return "Failed to download audio."

def get_gpt3_response(messages):
    prompt = ""
    with open("system_prompt.txt", 'r') as file:
        prompt = file.read()
    system_message = {"role": "system", "content": str(prompt)}
    
    # Prepend the system message to the list of messages
    messages.insert(0, system_message)

    try:
        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=messages,
            max_tokens=100,
            stop=None,
            temperature=0.5
        )
    except Exception as e:
        print("ERROR: ", e)
        return "Sorry, I didn't get that."

    if response.choices:
        gpt3_response = response.choices[0].message.content.strip()
        print("GPT-3 response:", gpt3_response)
        return gpt3_response
    else:
        raise Exception("GPT-3 API request failed.")

def text_to_speech(text):
    api_url = 'https://api.elevenlabs.io/v1/text-to-speech/' + voice_id
    headers = {
        'accept': 'audio/mpeg',
        'xi-api-key': elevenlabs_key,
        'Content-Type': 'application/json'
    }
    payload = {
        'text': text,
        'voice_settings': {
            'stability': '.6',
            'similarity_boost': 0
        }
    }
    response = requests.post(api_url, headers=headers, json=payload)

    if response.status_code == 200:
        file_name = f"tts_{hash(text)}.mp3"
        audio_directory = 'static/audio'
        os.makedirs(audio_directory, exist_ok=True)
        audio_path = os.path.join(audio_directory, file_name)

        with open(audio_path, 'wb') as f:
            f.write(response.content)

        tts_audio_url = f"/audio/{file_name}"
        return tts_audio_url
    else:
        print("Eleven Labs TTS API response:", response.json())
        raise Exception(f"Eleven Labs TTS API request failed with status code: {response.status_code}")

@app.route('/audio/<path:file_name>')
def serve_audio(file_name):
    return send_from_directory('static/audio', file_name)

if __name__ == '__main__':
    app.run()
