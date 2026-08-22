import os
import io
import logging
import dotenv
dotenv.load_dotenv()
from fastapi import FastAPI, UploadFile, File, HTTPException, Query
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, StreamingResponse
from pydantic import BaseModel

# Import local engine modules
from engine.parser import extract_text_from_pdf, generate_interview_questions, process_conversational_turn
from engine.vision_tracker import VisionTracker
from engine.voice_synth import synthesize_persona_voice
from engine.evaluator import evaluate_interview_session

# Setup logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

app = FastAPI(title="OmniPrep AI Server", version="1.0.0")

# Global instances
vision_tracker = VisionTracker()

# Pydantic Schemas for API Requests
class QuestionRequest(BaseModel):
    resume_text: str
    job_description: str
    custom_questions: str = ""
    target_role: str = "Software Engineer"

class VoiceRequest(BaseModel):
    text: str
    persona: str

class FrameRequest(BaseModel):
    image_data: str

class QuestionAnswer(BaseModel):
    question: str
    focus: str
    transcript: str
    wpm: int
    filler_count: int
    eye_contact_score: int

class ConversationTurn(BaseModel):
    role: str
    text: str

class TurnRequest(BaseModel):
    candidate_email: str
    target_role: str
    resume_text: str
    job_description: str
    history: list[ConversationTurn]
    current_stage: int
    custom_questions: str = ""

class EvaluationRequest(BaseModel):
    candidate_email: str
    target_role: str
    questions_answered: list[QuestionAnswer]

# 1. ROOT & STATIC ROUTING
# Route to serve the frontend homepage
@app.get("/", response_class=HTMLResponse)
async def get_index():
    try:
        index_path = os.path.join("static", "index.html")
        with open(index_path, "r", encoding="utf-8") as f:
            return HTMLResponse(content=f.read())
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Frontend index.html not found.")

# 1.5 CONFIG STATUS ROUTE
@app.get("/api/config-status")
async def get_config_status():
    """
    Checks if API keys and credentials are configured in the current shell environment.
    """
    return {
        "gemini_active": bool(os.environ.get("GEMINI_API_KEY")),
        "elevenlabs_active": bool(os.environ.get("ELEVEN_LABS_API_KEY")),
        "smtp_active": bool(os.environ.get("SMTP_SERVER") and os.environ.get("SMTP_USERNAME") and os.environ.get("SMTP_PASSWORD"))
    }

# 2. RESUME INGESTION ROUTE
@app.post("/api/upload-resume")
async def upload_resume(file: UploadFile = File(...)):
    """
    Ingests and parses a PDF resume file to extract text contents.
    """
    if not file.filename.endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are supported.")
        
    try:
        # Save temp file
        temp_filename = f"temp_{file.filename}"
        with open(temp_filename, "wb") as f:
            f.write(await file.read())
            
        # Parse PDF text
        text = extract_text_from_pdf(temp_filename)
        
        # Cleanup temp file
        if os.path.exists(temp_filename):
            os.remove(temp_filename)
            
        if not text:
            raise HTTPException(status_code=500, detail="Failed to extract readable text from PDF.")
            
        return {"text": text}
    except Exception as e:
        logger.error(f"Error handling upload: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# 3. INTERVIEW QUESTIONS ROUTE
@app.post("/api/generate-questions")
async def generate_questions(payload: QuestionRequest):
    """
    Generates a 4-stage mock interview loop tailored to resume skills and target role JDs.
    """
    try:
        questions = generate_interview_questions(payload.resume_text, payload.job_description, payload.custom_questions, payload.target_role)
        return {"questions": questions}
    except Exception as e:
        logger.error(f"Error generating questions: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# 3.5. CONVERSATIONAL TURN ROUTE
@app.post("/api/conversational-turn")
async def conversational_turn(payload: TurnRequest):
    """
    Evaluates candidate's last answer and returns the interviewer's next spoken follow-up or stage-advancement question.
    """
    try:
        history_list = [h.dict() for h in payload.history]
        result = process_conversational_turn(
            resume_text=payload.resume_text,
            job_description=payload.job_description,
            history=history_list,
            current_stage=payload.current_stage,
            custom_questions=payload.custom_questions
        )
        return result
    except Exception as e:
        logger.error(f"Error in conversational-turn: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# 4. ELEVENLABS PERSONA VOICE ROUTE
@app.post("/api/synthesize-voice")
async def synthesize_voice(payload: VoiceRequest):
    """
    Synthesizes interviewer questions into voice audio using ElevenLabs API.
    Streams back raw audio bytes or returns fallback directive if API key is missing.
    """
    try:
        audio_bytes = synthesize_persona_voice(payload.text, payload.persona)
        
        if not audio_bytes:
            # Tell client to fallback to browser SpeechSynthesis
            return {"fallback": True, "text": payload.text}
            
        return StreamingResponse(io.BytesIO(audio_bytes), media_type="audio/mpeg")
    except Exception as e:
        logger.error(f"Voice synth route error: {e}")
        return {"fallback": True, "text": payload.text}

# 5. WEBCAM FRAME COMPUTER VISION ROUTE
@app.post("/api/process-frame")
async def process_frame(payload: FrameRequest):
    """
    Processes a base64 webcam frame through MediaPipe FaceMesh to retrieve visual telemetry.
    """
    try:
        telemetry = vision_tracker.analyze_frame(payload.image_data)
        return telemetry
    except Exception as e:
        logger.error(f"Error processing frame: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# 6. INTERVIEW EVALUATION & WEBHOOK ROUTE
@app.post("/api/evaluate-session")
async def evaluate_session(payload: EvaluationRequest, trigger_webhook: bool = Query(False)):
    """
    Evaluates candidate responses, outputs the STAR scorecard, and triggers n8n webhook dispatch.
    """
    try:
        # Convert Pydantic schemas to standard dictionaries
        questions_list = [q.dict() for q in payload.questions_answered]
        
        # Call evaluation logic (this also dispatches n8n webhook inside)
        report = evaluate_interview_session(
            candidate_email=payload.candidate_email,
            target_role=payload.target_role,
            questions_answered=questions_list
        )
        return report
    except Exception as e:
        logger.error(f"Error evaluating session: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# Mount static folder for CSS, JS and assets
app.mount("/static", StaticFiles(directory="static"), name="static")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
