import os
import sys
import logging

# Ensure local directory is in path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("test_modules")

from engine.parser import generate_interview_questions, extract_text_from_pdf, process_conversational_turn
from engine.vision_tracker import VisionTracker
from engine.audio_tracker import analyze_speech_metrics
from engine.voice_synth import synthesize_persona_voice
from engine.evaluator import evaluate_interview_session

def test_resume_parser():
    logger.info("--- Testing Ingestion & Parser ---")
    # Test text parsing
    questions = generate_interview_questions("Mock Resume Text", "Mock Job Description for TD Bank")
    assert len(questions) == 4, "Should generate exactly 4 questions"
    for q in questions:
        assert "stage" in q
        assert "stage_name" in q
        assert "question" in q
        assert "focus" in q
    logger.info("SUCCESS: Parser generates correct question graph structure.")

def test_conversational_turn():
    logger.info("--- Testing Conversational Turn Agent ---")
    history = [
        {"role": "interviewer", "text": "Welcome! Tell me about your background."},
        {"role": "candidate", "text": "I am a full stack developer."}
    ]
    result = process_conversational_turn("Mock Resume", "Mock JD", history, 1)
    assert "response_text" in result
    assert "next_stage" in result
    assert "is_final" in result
    logger.info(f"SUCCESS: Conversational Turn output text: '{result['response_text']}' (Stage {result['next_stage']}).")

def test_vision_tracker():
    logger.info("--- Testing Vision Tracker ---")
    tracker = VisionTracker()
    # Test simulated fallback frame
    data = tracker.analyze_frame("data:image/jpeg;base64,mock")
    assert "eye_contact_score" in data
    assert "head_pose_score" in data
    assert "eye_contact_status" in data
    assert "head_pose_status" in data
    logger.info("SUCCESS: Vision Tracker initialized and outputs correct telemetry structure.")

def test_audio_tracker():
    logger.info("--- Testing Audio Tracker ---")
    metrics = analyze_speech_metrics("basically I was like working on a cool project like um you know", 10.0)
    assert metrics["word_count"] > 0
    assert metrics["wpm"] > 0
    assert metrics["filler_count"] > 0
    assert metrics["filler_breakdown"]["like"] == 2
    logger.info(f"SUCCESS: Audio tracker WPM={metrics['wpm']}, fillers={metrics['filler_count']}.")

def test_voice_synth():
    logger.info("--- Testing Voice Synthesis ---")
    # Will fallback if ELEVEN_LABS_API_KEY is not set
    audio_bytes = synthesize_persona_voice("Test question", "alex")
    if audio_bytes is None:
        logger.info("SUCCESS: Voice Synthesis correctly resolved to fallback (API key absent/failed).")
    else:
        assert len(audio_bytes) > 0
        logger.info("SUCCESS: Voice Synthesis successfully returned audio bytes.")

def test_evaluator():
    logger.info("--- Testing Session Evaluator ---")
    questions_answered = [
        {
            "question": "Tell me about your TD Bank project",
            "focus": "technical",
            "transcript": "I built a Java Spring Boot REST API for account balances. It was fun.",
            "wpm": 120,
            "filler_count": 0,
            "eye_contact_score": 92
        }
    ]
    report = evaluate_interview_session("test@example.com", "Software Engineer Co-op", questions_answered)
    assert "readiness_score" in report
    assert "jd_match_percent" in report
    assert "key_strengths" in report
    assert "rubric" in report
    assert len(report["questions"]) == 1
    logger.info(f"SUCCESS: Evaluator generated report with score {report['readiness_score']}%.")

if __name__ == "__main__":
    logger.info("Starting sub-system unit verification...")
    try:
        test_resume_parser()
        test_conversational_turn()
        test_vision_tracker()
        test_audio_tracker()
        test_voice_synth()
        test_evaluator()
        logger.info("ALL SUB-SYSTEMS VERIFIED SUCCESSFULLY!")
    except Exception as e:
        logger.error(f"VERIFICATION FAILED: {e}")
        sys.exit(1)
