import time
import os
import subprocess
from telephony_bridge import TelephonyBridge
from brain import analyze_intent_locally
from stt import listen_to_caller
from audiogen import speak_to_caller

class RealtimeSipAI:
    def __init__(self):
        self.bridge = TelephonyBridge()
        self.recording_path = "sip_inbound.wav"
        self.response_path = "response.wav"

    def wait_for_call(self):
        print("🔭 [SIP-AI] Waiting for incoming call on Baresip...")
        while True:
            status = self.bridge.send_command("listcalls")
            if "ESTABLISHED" in status.upper() or "INCOMING" in status.upper():
                print("📞 [SIP-AI] Call Detected! Auto-answering...")
                self.bridge.send_command("accept")
                self.handle_call_loop()
            time.sleep(2)

    def handle_call_loop(self):
        """Main loop for a single phone call interaction."""
        while True:
            # 1. Start recording the caller
            print("🎙️ [SIP-AI] Recording caller...")
            # Baresip records to a file. We'll use a 5-second burst for this prototype.
            # In a production version, we'd use VAD (Voice Activity Detection).
            self.bridge.send_command(f"ausrc_start_file {self.recording_path}")
            time.sleep(5)
            self.bridge.send_command("ausrc_stop_file")

            # 2. Process STT
            user_text = listen_to_caller(self.recording_path)
            if not user_text or "[Google" in user_text:
                print("⚠️ [SIP-AI] No clear audio heard.")
                continue
                
            print(f"👤 [USER] {user_text}")

            # 3. Generate Brain response
            ai_reply = analyze_intent_locally(user_text)
            print(f"🤖 [AI] {ai_reply}")

            # 4. Generate TTS
            speak_to_caller(ai_reply, use_elevenlabs=True)
            
            # Convert response.mp3 to response.wav for Baresip compatibility if needed
            # Baresip's play_file usually handles wav better.
            if os.path.exists("response.mp3"):
                subprocess.run(["ffmpeg", "-y", "-i", "response.mp3", "response.wav"], capture_output=True)

            # 5. Play response back to the caller
            print("🔊 [SIP-AI] Playing response to phone...")
            self.bridge.send_command(f"play_file {os.path.abspath('response.wav')}")
            
            # Check if call is still active
            status = self.bridge.send_command("listcalls")
            if "ESTABLISHED" not in status.upper():
                print("🏁 [SIP-AI] Caller hung up.")
                break

if __name__ == "__main__":
    ai_bot = RealtimeSipAI()
    try:
        ai_bot.wait_for_call()
    except KeyboardInterrupt:
        print("\n🛑 SIP AI Bridge stopped.")
