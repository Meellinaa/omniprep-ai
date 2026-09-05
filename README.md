# OMNIPREP AI — Multi-Sensory Interview Telemetry HUD

OmniPrep AI is a real-time, multi-sensory AI mock interview flight simulator built for **Ignition Hacks**. It is designed to bridge the gap between passive resume prep and high-stakes performance mastery. By analyzing resume PDFs and target Job Descriptions, OmniPrep AI conducts voice-driven mock interviews using hands-free turn-taking, processes real-time computer vision and vocal telemetry, and delivers a post-interview STAR-method diagnostic scorecard to the candidate's email.

---

## 🚀 Sponsor Integration Matrix

OmniPrep integrates **all 6 sponsor technologies** offered at Ignition Hacks to form a complete, enterprise-grade recruiting preparation pipeline:

| Sponsor | Integration Role | Technical Implementation |
| --- | --- | --- |
| **World Labs** | 3D Spatial Virtual Boardroom | Implements an interactive 3D spatial boardroom backdrop behind the interviewer avatar using **Three.js** particle rooms and wireframe grid structures, offering spatial depth parallax tracking mouse vectors to reduce candidate real-world anxiety. |
| **ElevenLabs** | Hyper-Realistic Voice Engine | Powers the AI interviewer’s natural voice stream in [`engine/voice_synth.py`](engine/voice_synth.py) utilizing the ElevenLabs Python SDK, mapping distinct voices for three interviewer personas (Tech Lead Alex, Recruiter Sarah, Executive Marcus). |
| **Render** | Scalable Cloud API Hosting | Deploys the Python FastAPI server in a containerized environment using `opencv-python-headless` for zero-downtime microservice execution. |
| **n8n** | Asynchronous Post-Interview Workflows | Fires session scoring matrices and communication stats via webhooks in [`engine/evaluator.py`](engine/evaluator.py) to trigger candidate email debriefs, study flashcards, and resource links. |
| **Mobbin** | Design System & HUD Inspiration | Guides the visual layout of the candidate webcam HUD, word-pacing speedometer, and radial scorecard indicators in [`static/style.css`](static/style.css) inspired by best-in-class tools (Loom, Linear, Duolingo). |
| **Base44** | Rapid App Prototyping Scaffolding | Provided the rapid component layout design grids for resume dropzones, target JD forms, and interviewer cards inside [`static/index.html`](static/index.html). |

---

## 🛠️ Code Review Navigation (Available Modules)

Judges can inspect our implementation directly across the following core code files:

* 📄 **[`main.py`](main.py)**: The FastAPI server hosting the REST API routes, parsing uploaded resumes, and serving the single-page application.
* 📄 **[`engine/parser.py`](engine/parser.py)**: Extracts text from PDF resumes using `pypdf` and hosts the dynamic **Conversational Turn Agent** (`process_conversational_turn`) powered by Gemini to ask role-tailored questions.
* 📄 **[`engine/vision_tracker.py`](engine/vision_tracker.py)**: Implements facial mesh coordinate vector calculations via MediaPipe FaceMesh to track user eye contact and head posture.
* 📄 **[`engine/audio_tracker.py`](engine/audio_tracker.py)**: Analyzes voice pace (WPM) and regex filler word frequencies (e.g. *like, um, uh, basically, yeah, so basically*).
* 📄 **[`engine/evaluator.py`](engine/evaluator.py)**: Scores transcripts against the STAR method (Situation, Task, Action, Result), calculates core competencies, and dynamically formats/sends HTML emails via SMTP.
* 📄 **[`static/app.js`](static/app.js)**: Drives client-side webcam capture, Web Audio visualizers, Web Speech API transcription, and hands-free Voice Activity Detection (VAD) loops.
* 📄 **[`static/index.html`](static/index.html)**: SPA dashboard with customized setup cards, webcam HUD telemetry indicators, and collapsible scorecard keyword panel details.

---

## 🎙️ Core Features

* **VAD Silence Detection**: Continuously tracks microphone speech. If the user stops speaking for **1.5 seconds** (after speaking at least 3 words), the system automatically locks the mic, transitions the AI state to `Thinking`, and sends the response.
* **Live HUD Coaching Overlay**: A real-time visual coaching overlay positioned over the camera feed. Warnings slide in and fade out dynamically to guide speech rate (`Speaking too fast!`), crutch words (`Filler word: "Basically"`), or eye contact drift (`Maintain eye contact`).
* **Automated SMTP Scorecard Delivery**: Connects to your email credentials to deliver highly styled, responsive HTML scorecards directly to your inbox upon ending a session.
* **Dedicated Mock Mode Fallback**: If no Gemini API key is configured, the application runs a local evaluation pipeline that calculates dynamic continuous scoring based on transcript lengths, filler counts, and eye-contact ratios.

---

## 🚀 Local Setup & Run Instructions

### 1. Setup Dependencies
Create and activate a virtual environment, then install requirements:
```bash
# Clone the repository
git clone https://github.com/Meellinaa/omniprep-ai.git
cd omniprep-ai

# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### 2. Configure Environment Keys (`.env`)
Create a file named `.env` in the root of the project directory and populate it with your keys:
```env
# Google Gemini API Key (Get one from https://aistudio.google.com/)
GEMINI_API_KEY=your_gemini_api_key_here

# ElevenLabs Speech Voice Synthesis Key (Optional, falls back to browser Speech API if empty)
ELEVEN_LABS_API_KEY=your_elevenlabs_key_here

# Local SMTP Configuration for Scorecard Emails (Optional, skips dispatch if empty)
SMTP_SERVER=smtp.gmail.com
SMTP_PORT=587
SMTP_USERNAME=your_email@gmail.com
SMTP_PASSWORD=your_gmail_app_password_here
```

### 3. Start the Server
Run this command to free up the port (just in case a previous process is hanging) and launch:
```bash
# Free port 8001
kill -9 $(lsof -t -i:8001) 2>/dev/null

# Start the server
venv/bin/python -m uvicorn main:app --port 8001 --reload
```

Once started, open **[http://127.0.0.1:8001](http://127.0.0.1:8001)** in Google Chrome or Microsoft Edge.
