import re
import logging

logger = logging.getLogger(__name__)

# List of filler words/phrases to track
FILLER_WORDS = ["um", "uh", "like", "you know", "literally", "basically", "actually", "yeah", "so basically"]

def analyze_speech_metrics(transcript: str, duration_seconds: float) -> dict:
    """
    Analyzes transcripts and duration to compute vocal performance metrics:
    - Words Per Minute (WPM)
    - Filler word count and breakdown
    - Pacing category (Too Slow, Optimal, Too Fast)
    """
    if not transcript:
        return {
            "word_count": 0,
            "wpm": 0,
            "pacing_status": "Silent",
            "filler_count": 0,
            "filler_breakdown": {w: 0 for w in FILLER_WORDS}
        }

    # Count words
    words = re.findall(r'\b\w+\b', transcript.lower())
    word_count = len(words)
    
    # Calculate WPM
    duration_minutes = duration_seconds / 60.0 if duration_seconds > 0 else 0
    wpm = int(word_count / duration_minutes) if duration_minutes > 0 else 0
    
    # Determine pacing status
    # Speedometer boundaries: Too Slow < 110 | Optimal 130–160 | Fast > 180
    if wpm == 0:
        pacing_status = "Silent"
    elif wpm < 110:
        pacing_status = "Too Slow"
    elif wpm < 130:
        pacing_status = "Slightly Slow"
    elif wpm <= 160:
        pacing_status = "Optimal"
    elif wpm <= 180:
        pacing_status = "Slightly Fast"
    else:
        pacing_status = "Too Fast"

    # Analyze filler words using standard regex matching
    # Includes two-word phrase "so basically" and informal tics
    filler_count = 0
    filler_breakdown = {}
    
    # Make a copy of transcript to perform matches
    transcript_lower = transcript.lower()
    
    # We match "so basically" first and remove it so we don't double-count it under "basically"
    so_basically_count = len(re.findall(r'\bso basically\b', transcript_lower))
    filler_breakdown["so basically"] = so_basically_count
    filler_count += so_basically_count
    # Remove to avoid double counting "basically"
    transcript_clean = re.sub(r'\bso basically\b', '', transcript_lower)

    for filler in FILLER_WORDS:
        if filler == "so basically":
            continue
        pattern = rf"\b{re.escape(filler)}\b"
        matches = re.findall(pattern, transcript_clean)
        count = len(matches)
        filler_breakdown[filler] = count
        filler_count += count

    return {
        "word_count": word_count,
        "wpm": wpm,
        "pacing_status": pacing_status,
        "filler_count": filler_count,
        "filler_breakdown": filler_breakdown
    }
