import os
import json
import logging
import requests
import re
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
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
        combined_transcript = ""
        for idx, q_data in enumerate(questions_answered):
            transcript = q_data.get('transcript', '[No Answer]')
            combined_transcript += transcript + " "
            interview_history += f"\n--- Question {idx+1} ({q_data.get('focus', 'General')}) ---\n"
            interview_history += f"Question Asked: {q_data.get('question')}\n"
            interview_history += f"Candidate Transcript: {transcript}\n"
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
        5. "jd_keywords_analysis": Extract key skills/frameworks from target JD and compare against the candidate transcripts. For each keyword, determine if it was "matched" or "missing" and provide an explanation.
        
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
          "jd_keywords_analysis": [
            {{
              "keyword": string,
              "status": "matched" | "missing",
              "context": string
            }}
          ],
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
                
        # Send Webhook and SMTP email
        trigger_n8n_webhook(candidate_email, target_role, evaluation)
        send_scorecard_email(candidate_email, target_role, evaluation)
        
        return evaluation
        
    except Exception as e:
        logger.error(f"Error evaluating interview with Gemini: {e}")
        return get_mock_evaluation(candidate_email, target_role, questions_answered)


def extract_and_match_keywords(job_description: str, combined_transcript: str) -> list[dict]:
    """
    Extracts key technologies from Job Description and matches them against candidate's transcript.
    """
    jd_lower = job_description.lower()
    transcript_lower = combined_transcript.lower()
    
    # Broad tech vocabulary bank
    tech_keywords = [
        "python", "javascript", "react", "fastapi", "docker", "kubernetes", "sql", "postgresql", 
        "database", "typescript", "three.js", "caching", "redis", "aws", "git", "ci/cd", 
        "testing", "agile", "scaling", "latency", "rest api", "graphql", "node.js"
    ]
    
    extracted = []
    for kw in tech_keywords:
        if kw in jd_lower:
            extracted.append(kw)
            
    if not extracted:
        # Generic professional soft-skills if JD is short or empty
        extracted = ["communication", "problem solving", "collaboration", "architecture", "star method"]
        
    analysis = []
    for kw in extracted:
        pattern = r'\b' + re.escape(kw) + r'\b'
        is_spoken = re.search(pattern, transcript_lower) is not None
        
        if is_spoken:
            analysis.append({
                "keyword": kw.capitalize(),
                "status": "matched",
                "context": f"You successfully mentioned '{kw.capitalize()}' in your answers, boosting your stack alignment."
            })
        else:
            analysis.append({
                "keyword": kw.capitalize(),
                "status": "missing",
                "context": f"Target role requirement. Try to weave your experience with '{kw.capitalize()}' into your responses."
            })
    return analysis


def send_scorecard_email(candidate_email: str, target_role: str, report: dict) -> bool:
    """
    Sends the completed scorecard report to the candidate's email using python smtplib.
    """
    smtp_server = os.environ.get("SMTP_SERVER")
    smtp_port = os.environ.get("SMTP_PORT", "587")
    smtp_user = os.environ.get("SMTP_USERNAME")
    smtp_pass = os.environ.get("SMTP_PASSWORD")
    from_email = os.environ.get("SMTP_FROM_EMAIL", smtp_user)
    
    if not (smtp_server and smtp_user and smtp_pass):
        logger.info("SMTP credentials not configured. Skipping SMTP dispatch.")
        return False
        
    try:
        msg = MIMEMultipart('alternative')
        msg['Subject'] = f"Your OmniPrep AI Interview Scorecard: {target_role}"
        msg['From'] = from_email
        msg['To'] = candidate_email
        
        strengths_html = "".join([f"<li style='margin-bottom: 6px;'>{s}</li>" for s in report.get("key_strengths", [])])
        flags_html = "".join([f"<li style='margin-bottom: 6px;'>{f}</li>" for f in report.get("areas_to_improve", [])])
        plan_html = "".join([f"<li style='margin-bottom: 6px;'>{p}</li>" for p in report.get("development_plan", [])])
        
        keywords_html = ""
        for kw in report.get("jd_keywords_analysis", []):
            color = "#059669" if kw["status"] == "matched" else "#dc2626"
            symbol = "✓" if kw["status"] == "matched" else "✗"
            keywords_html += f"""
            <li style="margin-bottom: 8px; font-size: 13px;">
                <strong style="color: {color};">{symbol} {kw['keyword']}</strong>: {kw['context']}
            </li>
            """
            
        questions_html = ""
        for idx, q in enumerate(report.get("questions", [])):
            questions_html += f"""
            <div style="margin-bottom: 20px; padding: 15px; border: 1px solid #e2e8f0; border-radius: 6px; background-color: #f8fafc;">
                <strong style="color: #1e293b; font-size: 14px;">Q{idx+1}: {q.get('question')}</strong><br/>
                <p style="margin: 8px 0; font-size: 13px; color: #475569;"><strong>Your Answer:</strong> {q.get('transcript')}</p>
                <p style="margin: 8px 0; font-size: 13px; color: #059669;"><strong>Gold Standard:</strong> {q.get('gold_standard_response')}</p>
                <p style="margin: 8px 0; font-size: 13px; color: #b45309;"><strong>Critique:</strong> {q.get('feedback')}</p>
                <div style="font-size: 11px; color: #94a3b8; font-family: monospace; margin-top: 8px;">
                    PACE: {q.get('wpm')} WPM | FILLERS: {q.get('fillers')} | FOCUS: {q.get('focus_score')}%
                </div>
            </div>
            """

        html_content = f"""
        <html>
        <body style="font-family: Arial, sans-serif; color: #334155; line-height: 1.6; max-width: 600px; margin: 0 auto; padding: 20px;">
            <div style="text-align: center; margin-bottom: 30px;">
                <h1 style="color: #0f172a; margin: 0; font-size: 28px;">OMNIPREP <span style="color: #06b6d4;">AI</span></h1>
                <p style="font-size: 14px; color: #64748b; margin-top: 5px;">Your Simulated Performance Scorecard</p>
            </div>
            
            <div style="background: linear-gradient(135deg, #0e121e 0%, #1c253c 100%); color: #ffffff; padding: 25px; border-radius: 12px; text-align: center; margin-bottom: 25px;">
                <span style="font-size: 12px; letter-spacing: 2px; text-transform: uppercase; color: #94a3b8; display: block;">Readiness Rating</span>
                <span style="font-size: 54px; font-weight: bold; color: #06b6d4; display: block; margin: 10px 0;">{report.get('readiness_score')}%</span>
                <p style="margin: 0; font-size: 14px; color: #e2e8f0;">Job Description Match: <strong>{report.get('jd_match_percent')}%</strong></p>
            </div>
            
            <h2 style="color: #0f172a; border-bottom: 2px solid #e2e8f0; padding-bottom: 8px; font-size: 18px;">Interview Insights</h2>
            <h3 style="color: #0f172a; font-size: 15px;">Key Strengths</h3>
            <ul>{strengths_html}</ul>
            
            <h3 style="color: #0f172a; font-size: 15px;">Areas to Focus On</h3>
            <ul>{flags_html}</ul>
            
            <h3 style="color: #0f172a; font-size: 15px;">Targeted Development Plan</h3>
            <ol>{plan_html}</ol>

            <h3 style="color: #0f172a; font-size: 15px;">Job Description Keywords Audit</h3>
            <ul style="list-style: none; padding-left: 0;">{keywords_html}</ul>
            
            <h2 style="color: #0f172a; border-bottom: 2px solid #e2e8f0; padding-bottom: 8px; margin-top: 30px; font-size: 18px;">Answering Audit Logs</h2>
            {questions_html}
            
            <div style="text-align: center; margin-top: 40px; font-size: 11px; color: #94a3b8; border-top: 1px solid #e2e8f0; padding-top: 20px;">
                Sent automatically by OmniPrep AI Interview Simulator. Practice makes perfect.
            </div>
        </body>
        </html>
        """
        
        msg.attach(MIMEText(html_content, 'html'))
        
        server = smtplib.SMTP(smtp_server, int(smtp_port))
        server.starttls()
        server.login(smtp_user, smtp_pass)
        server.sendmail(from_email, candidate_email, msg.as_string())
        server.quit()
        
        logger.info(f"Successfully sent scorecard email to {candidate_email}.")
        return True
    except Exception as e:
        logger.error(f"Failed to send scorecard email via SMTP: {e}")
        return False


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
    combined_transcript = ""
    
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
        combined_transcript += transcript + " "
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
    
    # Calculate mock JD keywords matching audit
    is_stripe = "stripe" in role.lower()
    mock_jd = "React Stripe API Payment system scaling frontend telemetry" if is_stripe else "Python FastAPI databases SQL Git PostgreSQL backend scaling"
    jd_keywords_analysis = extract_and_match_keywords(mock_jd, combined_transcript)
    
    # Readjust jd match percent dynamically
    matched_count = sum(1 for k in jd_keywords_analysis if k["status"] == "matched")
    total_count = len(jd_keywords_analysis) if jd_keywords_analysis else 1
    jd_match_percent = int((matched_count / total_count) * 100) if total_count > 0 else 70
    
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
        "yeah": "Used as a conversational bridge. Pause instead to project leadership and high-pressure composure.",
        "so_basically": "Double verbal crutch. Practice transitional silent pauses to project executive presence."
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
        "jd_keywords_analysis": jd_keywords_analysis,
        "questions": evaluated_questions
    }
    
    trigger_n8n_webhook(email, role, report)
    send_scorecard_email(email, role, report)
    
    return report
