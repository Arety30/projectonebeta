# projectonebeta

projectonebeta is Syed Abrar Ali's early experimental workspace for a low-cost voice assistant that can be reached by phone or chat: speech comes in (from a browser microphone, a SIP/PBX call, a WhatsApp voice note or a telephony provider webhook), is transcribed, answered by a small local Llama model running in Ollama, turned back into speech, and played to the caller. The goal was a usable phone assistant with near-zero recurring cost, so every stage has a free or local option (Google's free web speech API or local Whisper for STT, Ollama for the model, gTTS as a fallback for ElevenLabs TTS). The folder is a beta: several front doors were tried one after another and all of them are kept here.

## Where it is used

This is the prototype ground for Abrar's voice/phone assistant work. The three shared modules (`stt`/`voice`, `brain`, `audiogen`/`tts`) were reused by each attempt: a browser page served from a home server or a cloud VM, an Asterisk ARI call handler, a Baresip-based SIP bridge, a Vapi custom-LLM webhook (the most recent phone path), WhatsApp bridges, and finally `STT/voiceapi.py`, an API-key protected voice API that other apps call. A separate, keyed voice API on a cloud VM grew out of the `STT/` folder.

## How it works

### Core pipeline (shared by every entry point)

```
audio file --> listen_to_caller()  --> text --> analyze_intent_locally() --> reply --> speak_to_caller()/synthesize() --> mp3/wav
              (stt.py / voice.py)                 (brain.py, Ollama)                    (audiogen.py / STT/tts.py)
```

| Module | What it does |
|--------|--------------|
| `voice.py` | Converts any input to 16 kHz mono WAV with `ffmpeg`, then transcribes with the free Google web speech API via the `SpeechRecognition` package (language code parameter, default `en-US`) |
| `stt.py` (root) | Hardware-mic recording with PyAudio (`recording_N.wav`), Google web API transcription, and a Whisper `tiny` local option; `listen_to_caller()` is hard-wired to Google |
| `STT/stt.py` (newer) | Same API but `pyaudio`/`whisper` are optional imports; `STT_ENGINE=whisper|google` picks the engine (default whisper); Whisper prefers `faster-whisper` (CPU, int8, VAD filter) and falls back to the `whisper` package; model name from `WHISPER_MODEL`, language from `WHISPER_LANGUAGE`; the model is loaded once and cached |
| `brain.py` | `analyze_intent_locally(text)`: POST to Ollama `/api/generate` (`OLLAMA_URL`, `OLLAMA_MODEL`, default `llama3.2:1b`, temperature 0.4, 120 tokens, 60 s timeout) with a short "Abrar Assistant" system prompt; on an out-of-memory error from Ollama it retries with `OLLAMA_FALLBACK_MODEL` |
| `audiogen.py` | `speak_to_caller(text, use_elevenlabs=True)`: ElevenLabs SDK (`ELEVENLABS_API_KEY`, `ELEVENLABS_VOICE_ID`, `ELEVENLABS_MODEL_ID`) writing `response.mp3`, or gTTS when `use_elevenlabs=False` |
| `STT/tts.py` | `synthesize(text, path)`: ElevenLabs REST (`eleven_flash_v2_5` by default) with automatic gTTS fallback; returns which engine produced the file |
| `council.py` | Experimental two-stage answer: local model first, then a Google Gemini API call with the local result as context (`GEMINI_API_KEY`) |

### Entry points

| Script | Channel | Flow |
|--------|---------|------|
| `betaone.py` | Browser (FastAPI :8000) | Serves an HTML page that records 5 s from the user's microphone, POSTs it to `/api/stt-to-brain`, shows transcript + answer, and plays `/api/tts-response` (`response.mp3`) |
| `STT/sttwebinterface.py` | Browser (FastAPI, `HOST`/`PORT`, default :8000) | The most complete web UI: hold-to-talk button or Space bar, uploads a webm/opus clip, server converts with ffmpeg, Whisper (preloaded at startup) -> Llama -> `STT/tts.synthesize`, returns `audio_url` so the browser plays the reply; falls back to the server's own mic and `ffplay` when no clip is uploaded. Handles a path prefix behind a proxy |
| `STT/sttwebintftwo.py`, `sttwebinterfacetwo.py` | Browser, server mic | Older variants: button triggers a 5 s recording on the server's own microphone. `sttwebinterfacetwo.py` is a "grading sheet" demo that regex-parses `Name 95` pairs from dictated speech, computes pass/fail (>= 50) and a class average, and writes `Class_Grades.csv` |
| `STT/voiceapi.py` | HTTP API (:8010) | `GET /v1/health`; key-protected `POST /v1/transcribe`, `/v1/chat`, `/v1/speak`, `/v1/voice` (full pipeline) and `GET /v1/audio/{id}.mp3`. Keys via `X-API-Key` or `Authorization: Bearer`, verified against hashes in a SQLite DB managed by `STT/keys.py` (create / verify / enable-disable / list). One pipeline job at a time (lock), 25 MB upload cap, generated audio deleted after an hour |
| `server.py` | Telephony provider (Vapi) webhook (FastAPI :8000) | `POST /vapi-webhook`: on `assistant-request` returns an assistant definition pointing the provider's "custom LLM" at this server's own `/chat/completions` URL (derived from the request Host header); logs transcripts. `POST /chat/completions`: takes a chat-completions-style `messages` array, answers the last user turn with Ollama, returns a chat-completion-shaped JSON. The provider does STT and TTS itself |
| `ari_handler.py` | Asterisk ARI | WebSocket to Asterisk's ARI event stream for Stasis app `ai_pipeline`: on `StasisStart` answer and record (10 s max, 3 s silence); on `RecordingFinished` transcribe -> brain -> TTS and `play` the file; on `PlaybackFinished` hang up. ARI host/port/credentials are constants at the top |
| `realtime_sip_ai.py`, `telephony_bridge.py`, `telephony_caller.py` | Baresip SIP client | `TelephonyBridge` sends netstring-encoded commands to Baresip's `ctrl_tcp` module on `127.0.0.1:4444`. The loop polls `listcalls`, auto-`accept`s, records 5 s bursts with `ausrc_start_file`, runs the pipeline, converts the reply to WAV with ffmpeg and `play_file`s it. `telephony_caller.py` dials a SIP URI |
| `sipconnect.py` | Baresip, file-based | Polls for `incoming.wav`, runs the pipeline, deletes the file (earliest bridge idea) |
| `whatsapp_bridge.py` | WhatsApp via Twilio (Flask :5000) | `/whatsapp` webhook: text messages go straight to the brain; voice notes are downloaded, transcoded OGG -> WAV with pydub, transcribed and answered as text (audio replies need a public URL and are not sent) |
| `whatsapp_bot/index.js` | WhatsApp Web (Node) | `whatsapp-web.js` client with QR login; saves incoming media to `incoming.ogg` and replies with a placeholder; the hand-off to the Python side is not implemented |
| `exec-comm.py` | CLI | Sends a natural-language request to the Google Gemini API, extracts the returned ```bash block and executes it immediately; unrelated to voice, kept as an automation experiment |
| `kernel_recorder.py`, `STT/kernel_recorder.py` | Utility | 16 kHz mono PyAudio recorder (`kernel_voice.wav`) |
| `test_bot.py` | Utility | pyautogui/netcat smoke test that dials through Baresip and clicks in the browser |
| `generate_school_presentation.py`, `STT/text_to_speech.py` | Utility | python-pptx deck generator; a standalone ElevenLabs REST test |

Storage: only files on disk (`recording_N.wav`, `response.mp3`, `brain_response.mp3`, `STT/api_data/`, `STT/keys.db`, `Class_Grades.csv`, Asterisk's spool directory). External services: Ollama (local), ElevenLabs, Google web speech API, gTTS, Gemini, Twilio, Vapi, Asterisk/Baresip.

## Setup

Requirements: Linux, Python 3.10+, `ffmpeg` (and `ffplay` for server-side playback), a running Ollama with `llama3.2:1b` (or the model you configure). Optional: PortAudio + `pyaudio` for hardware-mic scripts, `faster-whisper` or `whisper` for offline STT, Asterisk with ARI enabled, Baresip with `ctrl_tcp`, Node.js for `whatsapp_bot/`.

```bash
git clone <repo-url> ~/projectonebeta
cd ~/projectonebeta
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt           # fastapi uvicorn[standard] python-dotenv python-multipart requests SpeechRecognition pydub elevenlabs gTTS websockets python-pptx
pip install faster-whisper                # offline STT (optional)
pip install flask twilio                  # whatsapp_bridge.py only
sudo apt install ffmpeg portaudio19-dev && pip install pyaudio   # hardware mic scripts only
cp main.env.example main.env              # then fill in the values
```

`main.env` keys (loaded with `python-dotenv` by `brain.py`, `audiogen.py`, `voice.py`, `server.py`, `whatsapp_bridge.py`, `STT/tts.py`):

```bash
OLLAMA_URL="http://localhost:11434/api/generate"
OLLAMA_MODEL="llama3.2:1b"
OLLAMA_FALLBACK_MODEL="deepseek-coder:1.3b"
ELEVENLABS_API_KEY=""                 # empty -> gTTS fallback in STT/tts.py
ELEVENLABS_VOICE_ID="VOICE_ID"
ELEVENLABS_MODEL_ID="eleven_multilingual_v2"
VAPI_API_KEY=""
VAPI_PHONE_NUMBER="++10000000000"
PUBLIC_BASE_URL="https://your-public-tunnel.example.com"
GEMINI_API_KEY=""
TWILIO_ACCOUNT_SID=""
TWILIO_AUTH_TOKEN=""
```

Process environment variables: `STT_ENGINE` (`whisper`|`google`), `WHISPER_MODEL` (`tiny`/`base`/`small`...), `WHISPER_LANGUAGE`, `VOICE_API_DATA` (storage dir for `voiceapi.py`), `HOST`, `PORT`.

## Usage

```bash
# browser hold-to-talk assistant
cd STT && STT_ENGINE=whisper WHISPER_MODEL=base python3 sttwebinterface.py     # http://localhost:8000

# keyed voice API
cd STT && uvicorn voiceapi:app --host 0.0.0.0 --port 8010
curl -H "X-API-Key: ak_live_XXXX" -F audio=@clip.wav http://localhost:8010/v1/voice
curl -H "X-API-Key: ak_live_XXXX" -H 'Content-Type: application/json' -d '{"text":"hello"}' http://localhost:8010/v1/chat

# phone via Vapi (expose port 8000 publicly, point the provider's server URL at /vapi-webhook)
python3 server.py

# Asterisk ARI handler (dialplan sends calls to Stasis(ai_pipeline))
python3 ari_handler.py

# Baresip SIP loop
python3 realtime_sip_ai.py

# WhatsApp via Twilio sandbox webhook -> http://PUBLIC_HOST/whatsapp
python3 whatsapp_bridge.py
```

## Project structure

```
projectonebeta/
├── brain.py                 # Ollama answer generation (+ fallback model)
├── voice.py                 # ffmpeg convert + Google web STT
├── stt.py                   # mic recording + Google/Whisper STT (older)
├── audiogen.py              # ElevenLabs / gTTS speech
├── council.py               # local model + Gemini second opinion
├── betaone.py               # browser mic web app
├── server.py                # Vapi webhook + chat-completions endpoint over Ollama
├── ari_handler.py           # Asterisk ARI call handler
├── realtime_sip_ai.py       # Baresip call loop
├── telephony_bridge.py      # Baresip ctrl_tcp client (netstrings)
├── telephony_caller.py      # dial a SIP URI
├── sipconnect.py            # file-polling bridge (earliest)
├── whatsapp_bridge.py       # Twilio WhatsApp webhook (Flask)
├── whatsapp_bot/            # whatsapp-web.js client (Node)
├── exec-comm.py             # Gemini -> bash command runner
├── kernel_recorder.py, test_bot.py, sttwebinterfacetwo.py
├── main.env.example, requirements.txt, stt.config, stt.css
└── STT/
    ├── stt.py               # engine switch, faster-whisper
    ├── tts.py               # ElevenLabs with gTTS fallback
    ├── sttwebinterface.py   # hold-to-talk web UI
    ├── sttwebintftwo.py, sttwebinterfacetwo.py, text_to_speech.py
    ├── voiceapi.py          # keyed HTTP voice API
    ├── keys.py              # API key store (SQLite)
    └── kernel_recorder.py, stt.css
```

Ignored: `venv/`, `STT_backup/`, `__pycache__/`, recordings and generated audio (`*.wav`, `*.mp3`, `*.webm`), `run_logs/`, `recordings/`, `call_reports/`, `STT/keys.db`, `STT/api_data/`, `main.env`.

## Limitations and notes

- This is an exploratory beta: there are duplicated modules at the root and under `STT/` (the `STT/` versions are the newer ones), and some scripts are abandoned attempts (`sipconnect.py`, `whatsapp_bot/`).
- Several older scripts carry inline settings (ARI credentials, ElevenLabs voice/API values, local sudo helpers) instead of reading `main.env`; move anything sensitive into `main.env` and strip it from the code before publishing or deploying.
- `exec-comm.py` executes model-generated shell commands without confirmation. Run it only in a disposable environment.
- The Google web speech API path needs Internet and has no SLA; use `STT_ENGINE=whisper` for offline operation.
- `brain.py` limits replies to 120 tokens and the Vapi path to an 8 s Ollama timeout, so answers are short by design.
- Single-tenant file names (`response.mp3`, `recording_N.wav`) mean concurrent callers overwrite each other except in `voiceapi.py`, which uses per-request IDs and a lock.
- `whatsapp_bridge.py` can only reply with text; sending audio back requires hosting the mp3 at a public URL.
- Sound playback with `ffplay` and PyAudio recording only make sense when the server has speakers/microphone; the browser paths are the ones that work on a headless VM.
