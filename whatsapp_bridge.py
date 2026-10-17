import os
import requests
from flask import Flask, request
from twilio.twiml.messaging_response import MessagingResponse
from pydub import AudioSegment
from brain import analyze_intent_locally
from stt import listen_to_caller
from audiogen import speak_to_caller
from twilio.rest import Client
from dotenv import load_dotenv

load_dotenv("main.env")

app = Flask(__name__)

# Twilio Credentials
ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID")
AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN")
client = Client(ACCOUNT_SID, AUTH_TOKEN)

@app.route("/whatsapp", methods=["POST"])
def whatsapp_reply():
    """Handle incoming WhatsApp messages (text or voice notes)."""
    incoming_msg = request.values.get("Body", "").strip()
    media_url = request.values.get("MediaUrl0")
    from_number = request.values.get("From")
    
    print(f"📞 [WHATSAPP] Incoming from {from_number}")
    
    resp = MessagingResponse()
    msg = resp.message()
    
    if media_url:
        print(f"🎙️ [WHATSAPP] Received voice note: {media_url}")
        
        # 1. Download the audio file
        audio_data = requests.get(media_url, auth=(ACCOUNT_SID, AUTH_TOKEN)).content
        ogg_path = "incoming_voice.ogg"
        wav_path = "incoming_voice.wav"
        
        with open(ogg_path, "wb") as f:
            f.write(audio_data)
        
        # 2. Transcode OGG (WhatsApp format) to WAV (STT format)
        print("🔄 [WHATSAPP] Transcoding audio...")
        try:
            audio = AudioSegment.from_file(ogg_path)
            audio.export(wav_path, format="wav")
        except Exception as e:
            print(f"❌ [WHATSAPP ERROR] Transcoding failed: {e}")
            msg.body("Sorry, I couldn't process your voice note.")
            return str(resp)

        # 3. Transcribe via existing STT pipeline
        print("📝 [WHATSAPP] Transcribing...")
        user_text = listen_to_caller(wav_path)
        
        if not user_text or user_text.startswith("["):
            msg.body("I heard you, but I couldn't understand the audio.")
            return str(resp)
            
        print(f"👤 [USER] {user_text}")
        
        # 4. Generate AI response via existing Brain
        ai_reply = analyze_intent_locally(user_text)
        print(f"🤖 [AI] {ai_reply}")
        
        # 5. Generate Voice Response via existing Audiogen
        print("🔊 [WHATSAPP] Synthesizing response...")
        audio_response_path = speak_to_caller(ai_reply, use_elevenlabs=True)
        
        if audio_response_path and os.path.exists(audio_response_path):
            # Twilio WhatsApp requires a public URL for media. 
            # For local dev, we'd need ngrok or similar.
            # As a fallback, we send the text and inform about audio limitations.
            msg.body(ai_reply)
            print("⚠️ [WHATSAPP] Audio generated, but requires public URL for delivery.")
        else:
            msg.body(ai_reply)
            
    else:
        # Handle text messages
        print(f"💬 [WHATSAPP] Received text: {incoming_msg}")
        ai_reply = analyze_intent_locally(incoming_msg)
        msg.body(ai_reply)

    return str(resp)

if __name__ == "__main__":
    # Standard Flask port
    app.run(port=5000, debug=True)
