import os
import json
import logging
import requests
import re
from google import genai
from google.genai import types

logger = logging.getLogger(__name__)

def evaluate_interview_session(
    candidate_email: str,
    target_role: str,
    questions_answered: list[dict]
) -> dict:
    """
    Evaluates the complete interview transcript using Gemini.
    Scores responses against STAR criteria, computes executive competencies,
    creates a detailed development plan, and provides filler diagnostics.
    """
    api_key = os.environ.get("GEMINI_API_KEY")
    
    if not api_key:
        logger.warning("GEMINI_API_KEY environment variable not found. Using comprehensive mock evaluation.")
        return get_mock_evaluation(candidate_email, target_role, questions_answered)

    try:
        client = genai.Client(api_key=api_key)
        
        # Prepare content for Gemini
        interview_history = ""
        for idx, q_data in enumerate(questions_answered):
            interview_history += f"\n--- Question {idx+1} ({q_data.get('focus', 'General')}) ---\n"
            interview_history += f"Question Asked: {q_data.get('question')}\n"
            interview_history += f"Candidate Transcript: {q_data.get('transcript', '[No Answer]')}\n"
            interview_history += f"Candidate Telemetry: WPM={q_data.get('wpm', 0)}, Fillers={q_data.get('filler_count', 0)}, Focus%={q_data.get('eye_contact_score', 0)}%\n"

        prompt = f"""
        You are an expert technical interviewer and executive communication coach. Evaluate the candidate's interview session for the target role: "{target_role}".
        
        Here is the interview history:
        {interview_history}
        
        Evaluate the candidate's answers based on the STAR method (Situation, Task, Action, Result).
        For each question answered, calculate:
        - "star_score": overall score (0 to 100).
        - "gold_standard_response": A high-impact, professional version of their answer in perfect STAR format, showcasing the same achievements but optimized for metrics.
        - "feedback": concrete critique directly addressing their transcript.
        
        Calculate overall session metrics:
        - "readiness_score": average readiness score (0 to 100).
        - "jd_match_percent": job description match percentage (0 to 100).
        - "key_strengths": 3-4 key strength points.
        - "areas_to_improve": 2-3 critical improvement points.
        
        Provide the following new comprehensive analysis modules:
        1. "competency_scores": Grade 4 core skills out of 100:
           - "technical_articulation": clarity and depth of tech explanations.
           - "structured_delivery": STAR layout execution.
           - "vocal_telemetry": pacing, tone, and filler word control.
           - "visual_presence": eye contact stability and posture alignment.
        2. "development_plan": A personalized, checklist-style study and growth plan (3-4 items) based on their weak points.
        3. "filler_diagnostics": Constructive, 1-sentence tips for each filler word tic used (like, um/uh, basically, yeah).
        4. "rubric": Average situation_task_clarity, action_specifics, and result_impact scores across the session.
        
        Return strictly a JSON object matching this schema:
        {{
          "readiness_score": int,
          "jd_match_percent": int,
          "key_strengths": [string],
          "areas_to_improve": [string],
          "rubric": {{
            "situation_task_clarity": int,
            "action_specifics": int,
            "result_impact": int
          }},
          "competency_scores": {{
            "technical_articulation": int,
            "structured_delivery": int,
            "vocal_telemetry": int,
            "visual_presence": int
          }},
          "development_plan": [string],
          "filler_diagnostics": {{
            "like": "tip text",
            "um_uh": "tip text",
            "basically": "tip text",
            "yeah": "tip text"
          }},
          "questions": [
            {{
              "question": string,
              "transcript": string,
              "star_score": int,
              "gold_standard_response": string,
              "feedback": string,
              "wpm": int,
              "fillers": int,
              "focus_score": int
            }}
          ]
        }}
        """
        
        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
            )
        )
        
        clean_text = response.text.strip()
        if clean_text.startswith("```"):
            lines = clean_text.splitlines()
            if lines[0].startswith("```"): lines = lines[1:]
            if lines[-1].startswith("```"): lines = lines[:-1]
            clean_text = "\n".join(lines).strip()
            
        evaluation = json.loads(clean_text)
        
        # Merge telemetry from questions
        for idx, q_eval in enumerate(evaluation.get("questions", [])):
            if idx < len(questions_answered):
                orig = questions_answered[idx]
                q_eval["wpm"] = orig.get("wpm", q_eval.get("wpm", 0))
                q_eval["fillers"] = orig.get("filler_count", q_eval.get("fillers", 0))
                q_eval["focus_score"] = orig.get("eye_contact_score", q_eval.get("focus_score", 0))
                
        # Send Webhook to n8n if url exists
        trigger_n8n_webhook(candidate_email, target_role, evaluation)
        
        return evaluation
        
    except Exception as e:
        logger.error(f"Error evaluating interview with Gemini: {e}")
        return get_mock_evaluation(candidate_email, target_role, questions_answered)


def trigger_n8n_webhook(email: str, role: str, report: dict) -> bool:
    """
    Sends the completed scorecard to an n8n webhook to automate emailing.
    """
    webhook_url = os.environ.get("N8N_WEBHOOK_URL")
    if not webhook_url:
        logger.info("N8N_WEBHOOK_URL not configured. Skipping webhook dispatch.")
        return False
        
    payload = {
        "candidate_email": email,
        "target_role": role,
        "overall_score": report.get("readiness_score", 0),
        "jd_match_percent": report.get("jd_match_percent", 0),
        "strengths": report.get("key_strengths", []),
        "red_flags": report.get("areas_to_improve", []),
        "star_averages": report.get("rubric", {}),
        "competency_scores": report.get("competency_scores", {}),
        "development_plan": report.get("development_plan", []),
        "filler_diagnostics": report.get("filler_diagnostics", {}),
        "questions_answered": report.get("questions", [])
    }
    
    try:
        response = requests.post(webhook_url, json=payload, timeout=8)
        if response.status_code in [200, 201]:
            logger.info("Successfully dispatched scorecard to n8n webhook.")
            return True
        else:
            logger.warning(f"n8n webhook returned status code {response.status_code}: {response.text}")
            return False
    except Exception as e:
        logger.error(f"Failed to trigger n8n webhook: {e}")
        return False


def get_mock_evaluation(email: str, role: str, questions: list[dict]) -> dict:
    """
    Provides comprehensive mock evaluation scoring and detailed analytics when Gemini is not active.
    Generates dynamic feedback, competencies, diagnostics, and study tasks.
    """
    avg_eye_contact = int(sum(q.get("eye_contact_score", 90) for q in questions) / len(questions)) if questions else 90
    avg_wpm = int(sum(q.get("wpm", 140) for q in questions) / len(questions)) if questions else 140
    total_fillers = sum(q.get("filler_count", 0) for q in questions)
    
    evaluated_questions = []
    total_star_score = 0
    
    stage_data = {
        0: {
            "name": "Introduction",
            "gold": f"Situation: I am applying for the {role} position. Task: My objective was to connect my core competencies in system architecture and coding to your roadmap. Action: I highlighted key achievements, including leading a team of 4 engineers and optimizing web performance. Result: This alignment positions me to deliver immediate value to your current projects.",
            "critique": "Your introduction was brief. Next time, summarize 1-2 major technical achievements and align them with the specific job description requirements."
        },
        1: {
            "name": "Technical Project",
            "gold": "Situation: In my last project, our backend service hit scaling limitations under heavy traffic. Task: I was responsible for optimizing API response latency and database throughput. Action: I refactored the caching middleware, set up database indexing, and introduced connection pooling. Result: API latency dropped by 35% and overall system load decreased by 40% with zero downtime.",
            "critique": "Your project description was missing key engineering steps. Discuss your specific database choices, caching mechanisms, or architectural trade-offs."
        },
        2: {
            "name": "Behavioral",
            "gold": "Situation: During a release cycle, our technical requirements shifted midway. Task: I needed to adapt the project scope while maintaining code quality. Action: I restructured our sprint priorities, set up automated tests, and conducted team check-ins. Result: We delivered the core feature set on time with a 98% test coverage and no critical bugs.",
            "critique": "Your behavioral answer was unstructured. Emphasize the conflict resolution and follow the STAR layout: start with the situation, outline your actions, and state the results."
        },
        3: {
            "name": "Situational Trade-Off",
            "gold": "Situation: We had to decide between launching a critical feature quickly or refactoring a database bottleneck first. Task: I had to weigh the technical risk against business deadlines. Action: I conducted a load test, proposed a phased release strategy using feature flags, and scheduled the refactoring for the next cycle. Result: We shipped on time while mitigating production risk.",
            "critique": "Your analysis of trade-offs was too high-level. Try addressing customer impact, technical debt isolation, and how you communicate risk to stakeholders."
        }
    }

    for idx, q in enumerate(questions):
        transcript = q.get("transcript", "").strip()
        q_text = q.get("question", "")
        wpm = q.get("wpm", 0)
        fillers = q.get("filler_count", 0)
        focus = q.get("eye_contact_score", 90)
        
        is_empty = not transcript or transcript == "[No vocal answer recorded]" or transcript == "[No Answer]"
        is_gibberish = "blah" in transcript.lower() or "nonsense" in transcript.lower() or len(transcript) < 15
        
        if is_empty:
            star_score = 10
            feedback = "You did not provide an answer. In the real interview, try to state a situation even if you are not fully familiar with the topic."
        elif is_gibberish:
            star_score = 25
            feedback = f"Your answer '{transcript}' was flagged as gibberish or empty. In a real interview, you must respond to the question."
        else:
            word_count = len(transcript.split())
            if word_count < 35:
                star_score = 48
                feedback = f"Short response. {stage_data.get(idx, stage_data[0])['critique']} Expand on your specific technical actions."
            elif fillers > 6 or wpm > 175:
                star_score = 70
                feedback = f"Good technical points, but delivery is compromised. You used {fillers} filler words and spoke at {wpm} WPM. Pace yourself and use structure."
            else:
                star_score = 88
                feedback = f"Strong answer. {stage_data.get(idx, stage_data[0])['critique']} Good flow and direct explanation."
                
        total_star_score += star_score
        
        gold = stage_data.get(idx, stage_data[0])["gold"]
        
        evaluated_questions.append({
            "question": q_text,
            "transcript": transcript or "[No Answer]",
            "star_score": star_score,
            "gold_standard_response": gold,
            "feedback": feedback,
            "wpm": wpm,
            "fillers": fillers,
            "focus_score": focus
        })

    # Overall Scores
    q_count = len(evaluated_questions) if evaluated_questions else 1
    avg_star = total_star_score / q_count
    
    wpm_deviation = abs(avg_wpm - 145)
    pacing_score = max(50, 100 - wpm_deviation * 0.8)
    filler_score = max(50, 100 - total_fillers * 4)
    
    readiness_score = int((avg_star * 0.45) + (avg_eye_contact * 0.25) + (pacing_score * 0.20) + (filler_score * 0.10))
    readiness_score = max(10, min(95, readiness_score))
    
    jd_match_percent = int(readiness_score * 0.95)
    
    # Key strengths and improvement areas
    strengths = [
        "Consistent eye-contact and engaged posture throughout the session."
    ]
    if avg_star > 70:
        strengths.append("Detailed layout of technical responsibilities and architectural decisions.")
        strengths.append("Direct focus on problem solving and overcoming implementation hurdles.")
    else:
        strengths.append("Steady voice pitch and volume control during explanation.")
        strengths.append("Enthusiastic and professional introductory overview.")
        
    areas_to_improve = []
    if total_fillers > 8:
        areas_to_improve.append(f"Frequent verbal crutches detected ({total_fillers} fillers). Practice pausing instead of saying 'like' or 'yeah'.")
    if avg_wpm > 170:
        areas_to_improve.append("Speech rate is quite high. Slow down to allow the interviewer to digest details.")
    elif avg_wpm < 110:
        areas_to_improve.append("Pacing is a bit slow. Try to structure thoughts faster to prevent awkward gaps.")
        
    if avg_star < 75:
        areas_to_improve.append("Add quantifiable metrics (percentages, throughput metrics, time saved) to the Result portion of your answers.")
        
    if not areas_to_improve:
        areas_to_improve.append("Refine technical system design depth on complex backend architecture.")
    
    # Core Competencies out of 100
    technical_articulation = int(avg_star * 0.96)
    structured_delivery = int(avg_star * 0.98)
    vocal_telemetry_grade = int(pacing_score * 0.7 + filler_score * 0.3)
    visual_presence_grade = int(avg_eye_contact)

    # Detailed Filler diagnostics
    filler_diagnostics = {
        "like": "Used to buy thinking time. Try to pause silently for 1 second instead of inserting 'like'.",
        "um_uh": "Indicates high cognitive processing load. Map out your project stories in key bullet points beforehand.",
        "basically": "Dilutes technical precision. Replace with authoritative direct verbs (e.g. 'I refactored' instead of 'I basically refactored').",
        "yeah": "Used as a conversational bridge. Pause instead to project leadership and high-pressure composure."
    }

    # Development Study Plan
    development_plan = [
        f"Map out your technical project stories in a 4-bullet point STAR grid (Situation, Task, Action, Result) before your next mock run.",
        "Practice speaking at a steady 140 WPM using a local metronome or pacing guide.",
        "Conduct a 3-minute video journal recording where you focus purely on looking directly at your camera lens.",
        f"Review the generated Gold Standard response for the '{role}' interview to study how to present engineering metrics."
    ]

    # STAR Rubric averages
    sit_clarity = int(avg_star * 0.95)
    act_spec = int(avg_star * 1.02)
    res_impact = int(avg_star * 0.88)
    
    report = {
        "readiness_score": readiness_score,
        "jd_match_percent": jd_match_percent,
        "key_strengths": strengths,
        "areas_to_improve": areas_to_improve,
        "rubric": {
            "situation_task_clarity": min(100, sit_clarity),
            "action_specifics": min(100, act_spec),
            "result_impact": min(100, res_impact)
        },
        "competency_scores": {
            "technical_articulation": min(100, technical_articulation),
            "structured_delivery": min(100, structured_delivery),
            "vocal_telemetry": min(100, vocal_telemetry_grade),
            "visual_presence": min(100, visual_presence_grade)
        },
        "development_plan": development_plan,
        "filler_diagnostics": filler_diagnostics,
        "questions": evaluated_questions
    }
    
    # Try sending webhook even for mocks if URL is present
    trigger_n8n_webhook(email, role, report)
    
    return report
