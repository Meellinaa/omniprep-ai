# OmniPrep AI — Multi-Sensory Interview Telemetry

OmniPrep is an interactive, multi-sensory AI mock interview simulation console designed to bridge the gap between passive resume prep and high-stakes performance mastery. By analyzing resume PDFs and target Job Descriptions (JDs), OmniPrep conducts voice-driven mock interviews using hands-free turn-taking, processes real-time computer vision and vocal telemetry, and generates a post-interview STAR-method diagnostic scorecard.

---

## 🚀 The 6-Sponsor Integration Matrix

OmniPrep integrates **all 6 sponsor technologies** offered at Ignition Hacks to form a complete, enterprise-grade recruiting preparation pipeline:

| Sponsor | Integration Role | Technical Implementation |
| --- | --- | --- |
| **World Labs** | 3D Spatial Virtual Backdrop | Implements an interactive 3D spatial boardroom backdrop behind the interviewer avatar using **Three.js** particle rooms and wireframe grid structures, offering spatial depth parallax tracking mouse vectors to reduce candidate real-world anxiety. |
| **ElevenLabs** | Hyper-Realistic Voice Engine | Powers the AI interviewer’s natural voice stream in [`engine/voice_synth.py`](engine/voice_synth.py) utilizing the ElevenLabs Python SDK, mapping distinct voices for three interviewer personas (Tech Lead Alex, Recruiter Sarah, Executive Marcus). |
| **Render** | Scalable Cloud API Hosting | Deploys the Python FastAPI server in a containerized environment using `opencv-python-headless` for zero-downtime microservice execution. |
| **n8n** | Asynchronous Post-Interview Workflows | Fires session scoring matrices and communication stats via webhooks in [`engine/evaluator.py`](engine/evaluator.py) to trigger candidate email debriefs, study flashcards, and resource links. |
| **Mobbin** | Design System & HUD Inspiration | Guides the visual layout of the candidate webcam HUD, word-pacing speedometer, and radial scorecard indicators in [`static/style.css`](static/style.css) inspired by best-in-class tools (Loom, Linear, Duolingo). |
| **Base44** | Rapid App Prototyping Scaffolding | Provided the rapid component layout design grids for resume dropzones, target JD forms, and interviewer cards inside [`static/index.html`](static/index.html). |

---

## 🛠️ Architecture & System Modules

OmniPrep is built entirely on a **Pure Python + HTML5 Canvas/Three.js** stack:

```
 ┌───────────────────────────────────────────────────────────────────────────┐
 │                               FRONTEND & DESIGN                           │
 │                                                                           │
 │   ┌──────────────────────┐                     ┌──────────────────────┐   │
 │   │        Mobbin        │                     │       Base44         │   │
 │   │  UX/UI Design System │                     │ Rapid Micro-Frontend │   │
 │   │  HUD & Scorecard     │                     │ Prototype Scaffolding│   │
 │   └──────────┬───────────┘                     └──────────┬───────────┘   │
 └──────────────┼────────────────────────────────────────────┼───────────────┘
                ▼                                            ▼
 ┌───────────────────────────────────────────────────────────────────────────┐
 │                           LIVE SIMULATION LAYER                           │
 │                                                                           │
 │   ┌──────────────────────┐                     ┌──────────────────────┐   │
 │   │     ElevenLabs       │                     │      World Labs      │   │
 │   │ Ultra-Realistic Voice│                     │ 3D Spatial Virtual   │   │
 │   │ Dynamic Tone & Pause │                     │ Boardroom Backdrop   │   │
 │   └──────────┬───────────┘                     └──────────┬───────────┘   │
 └──────────────┼────────────────────────────────────────────┼───────────────┘
                ▼                                            ▼
 ┌───────────────────────────────────────────────────────────────────────────┐
 │                           BACKEND & AUTOMATION                            │
 │                                                                           │
 │   ┌──────────────────────┐                     ┌──────────────────────┐   │
 │   │        Render        │                     │         n8n          │   │
 │   │ Scalable Cloud API   │                     │ Post-Interview Study │   │
 │   │ WebSocket & Database │                     │ Plan & PDF Emailer   │   │
 │   └──────────────────────┘                     └──────────────────────┘   │
 └───────────────────────────────────────────────────────────────────────────┘
```

* **[`main.py`](main.py)**: The FastAPI server hosting the API routes, parsing requests, and serving static files.
* **[`engine/parser.py`](engine/parser.py)**: Extracts text from PDF resumes using `pypdf` and hosts the dynamic Conversational Turn Agent powered by Gemini.
* **[`engine/vision_tracker.py`](engine/vision_tracker.py)**: Implements facial mesh vector calculations via MediaPipe FaceMesh to track user eye contact and head posture.
* **[`engine/audio_tracker.py`](engine/audio_tracker.py)**: Analyzes voice pace (WPM) and regex filler word frequencies (e.g., *like*, *um*, *uh*, *you know*, *literally*, *basically*, *yeah*, *so basically*).
* **[`engine/evaluator.py`](engine/evaluator.py)**: Scores transcripts against the STAR method (Situation, Task, Action, Result) and generates gold-standard responses.
* **[`static/app.js`](static/app.js)**: Drives client-side webcam capture, Web Audio visualizers, Web Speech API transcription, and hands-free Turn-Taking VAD loops.

---

## 🎙️ Dynamic Hands-Free turn-taking

OmniPrep delivers a completely immersive, voice-driven experience:
* **VAD Silence Detection**: Continuously tracks microphone speech. If the user stops speaking for **1.5 seconds** (after speaking at least 3 words), the system automatically locks the mic, transitions the AI state to `Thinking`, and sends the turn response to the server.
* **Beep Tones**: Synthesizes custom chirps using browser-native `AudioContext` to queue the candidate when it's their turn to speak or when processing is complete.
* **Conversational Probing**: If the candidate provides a brief response (under 15 words) or trails off, the AI interviewer gently probes for details (*"Could you give me a specific technical example of that?"*) instead of dryly jumping to a new topic.

---

## 🚀 Local Quickstart

### 1. Setup Dependencies
Create and activate a virtual environment, then install requirements:
```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 2. Configure Environment Keys (Optional)
If you have API credentials, set them up to activate live AI generation. If not, the application will automatically run in a fully custom mock evaluation mode.
```bash
export GEMINI_API_KEY="your-gemini-key"
export ELEVEN_LABS_API_KEY="your-eleven-labs-key"
export N8N_WEBHOOK_URL="https://your-n8n-webhook-trigger"
```

### 3. Start the Server
```bash
python3 -m uvicorn main:app --port 8001 --reload
```
Once started, open **[http://localhost:8001](http://localhost:8001)** in Google Chrome or Microsoft Edge.
