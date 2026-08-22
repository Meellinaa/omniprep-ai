import os
import logging
import json
import re
from pypdf import PdfReader
from google import genai
from google.genai import types

logger = logging.getLogger(__name__)

def extract_text_from_pdf(pdf_path: str) -> str:
    """
    Extracts text content from a PDF file using pypdf.
    """
    try:
        reader = PdfReader(pdf_path)
        text = ""
        for page in reader.pages:
            page_text = page.extract_text()
            if page_text:
                text += page_text + "\n"
        return text.strip()
    except Exception as e:
        logger.error(f"Error reading PDF {pdf_path}: {e}")
        return ""

def generate_interview_questions(
    resume_text: str, 
    job_description: str, 
    custom_questions: str = "",
    target_role: str = "Software Engineer"
) -> list[dict]:
    """
    Generates an initial starting list of 4 structured questions based on resume, JD, and custom focus areas.
    """
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        return get_mock_questions(resume_text, job_description, custom_questions, target_role)

    try:
        client = genai.Client(api_key=api_key)
        prompt = f"""
        You are an elite technical interviewer. Generate an initial starting list of 4 questions for these stages:
        1. Introduction & Background (Warmup)
        2. Technical Project Deep-Dive (System Design & Code)
        3. Behavioral Challenge (STAR method conflict or failure scenario)
        4. Situational Trade-Off (Business alignment & trade-offs)
        
        Target Position / Role:
        {target_role}
        
        Resume Profile:
        {resume_text}
        
        Target Job Description:
        {job_description}
        
        Candidate's Manual Focus Areas / Specific Questions:
        {custom_questions}
        
        Combine the information in the resume, target job description, target role, and custom questions. 
        Tailor the questions specifically to their technical projects and the targeted role.
        
        Return a raw JSON list. Do not include markdown code block formatting.
        Schema: [{{"stage": 1, "stage_name": "Introduction", "question": "text", "focus": "text"}}]
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
            
        questions = json.loads(clean_text)
        if isinstance(questions, list) and len(questions) == 4:
            return questions
        raise ValueError("Invalid format")
    except Exception as e:
        logger.error(f"Error starting questions: {e}")
        return get_mock_questions(resume_text, job_description, custom_questions, target_role)

def get_mock_questions(
    resume_text: str, 
    job_description: str, 
    custom_questions: str = "",
    target_role: str = "Software Engineer"
) -> list[dict]:
    """
    Mock questions generator helper. Dynamically parses the resume, target job description, 
    and custom questions to generate highly tailored mock questions without relying on the Gemini API.
    """
    role = target_role or "Software Engineer"
    resume_lower = resume_text.lower()
    jd_lower = job_description.lower()
    
    tech_keywords = [
        "react", "fastapi", "django", "java", "spring boot", "kubernetes", "docker", 
        "postgresql", "mysql", "javascript", "typescript", "aws", "gcp", "python", "sql"
    ]
    
    extracted_skills = []
    for skill in tech_keywords:
        if skill in resume_lower or skill in jd_lower:
            extracted_skills.append(skill.capitalize())
            
    primary_skills = ", ".join(extracted_skills[:3]) if extracted_skills else "software engineering fundamentals"

    custom_topic = ""
    if custom_questions:
        words = [w.strip(",.!?").capitalize() for w in custom_questions.split() if len(w) > 4 and w.lower() not in ["about", "experience", "questions", "please", "would", "could", "focus"]]
        if words:
            custom_topic = words[0]
            
    featured_project = ""
    project_matches = re.findall(r'(?i)(?:project|application|system|app):\s*([a-zA-Z0-9_\-\s]{3,15})', resume_text)
    if project_matches:
        featured_project = project_matches[0].strip()
    else:
        match = re.search(r'\b([A-Z][a-zA-Z]+(?:\s+[A-Z][a-zA-Z]+){0,2})\s+(?:website|portal|dashboard|app|platform|system|service)\b', resume_text)
        if match:
            featured_project = match.group(1).strip()
            
    featured_project = featured_project or "featured software application"

    q1 = f"Welcome to your mock interview for the {role} position. To start, could you walk me through your background and explain how your experience with {primary_skills} prepares you for this role?"
    
    if custom_topic:
        q2 = f"Looking at your {featured_project} and your request to focus on {custom_topic}, what was the main engineering challenge you solved using {custom_topic}, and how did you verify its performance?"
    else:
        q2 = f"Looking at your {featured_project}, can you outline a major engineering hurdle you encountered during its implementation, how you resolved it, and what technical trade-offs you made?"
        
    q3 = f"Describe a situation where you had to lead or collaborate on a {custom_topic or 'technical'} deliverable with shifting deadlines or conflicting technical opinions. What action did you take to align the team, and what was the result?"
    
    q4 = f"In a production environment for a {role}, how do you evaluate the balance between shipping a feature quickly to meet critical business needs versus managing technical debt in your database and scaling architecture?"

    return [
        {
            "stage": 1,
            "stage_name": "Introduction",
            "question": q1,
            "focus": "Communication clarity and resume introduction."
        },
        {
            "stage": 2,
            "stage_name": "Technical Project Deep-Dive",
            "question": q2,
            "focus": "Problem-solving depth and architecture."
        },
        {
            "stage": 3,
            "stage_name": "Behavioral Challenge",
            "question": q3,
            "focus": "Conflict resolution and flexibility (STAR method)."
        },
        {
            "stage": 4,
            "stage_name": "Situational Trade-Off",
            "question": q4,
            "focus": "Technical risk management and trade-off negotiation."
        }
    ]

def process_conversational_turn(
    resume_text: str,
    job_description: str,
    history: list[dict],
    current_stage: int,
    custom_questions: str = ""
) -> dict:
    """
    Evaluates the last candidate response and generates the next conversational question.
    Turn rules:
    - If candidate response is too brief or trailing, ask a probing follow-up. Do not advance stage.
    - If candidate response is a query/question, answer it directly, then pivot back to the interview.
    - If answer is sufficient, acknowledge and advance stage (or conclude interview if stage 4).
    """
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        return get_mock_conversational_turn(history, current_stage, job_description, custom_questions)

    try:
        client = genai.Client(api_key=api_key)
        
        # Compile conversational thread
        thread = ""
        for turn in history:
            role_lbl = "Interviewer" if turn["role"] == "interviewer" else "Candidate"
            thread += f"{role_lbl}: {turn['text']}\n"
            
        prompt = f"""
        You are an active human interviewer conducting a live spoken mock interview for the target role.
        You must evaluate the candidate's last answer and generate your next spoken response.
        
        Candidate Resume Profile:
        {resume_text}
        
        Target Job Description:
        {job_description}
        
        Candidate's Manual Focus Areas / Specific Questions:
        {custom_questions}
        
        Current Stage: {current_stage} (1=Intro, 2=Tech Project, 3=Behavioral, 4=Situational Trade-Off)
        
        Conversation History:
        {thread}
        
        Turn Rules:
        1. Always keep your response short (2-3 spoken sentences). Do not list things, use markdown, or bullet points. Emojis are forbidden.
        2. INTERACTIVE RESPONDING: If the candidate asks you a question, seeks clarification, or makes a comment (e.g. asking 'Can you explain the stack?', 'What does that mean?', 'What is the team size?'), you MUST answer their question directly in a conversational, human way (1-2 sentences), and then pivot back to the interview topic. Do not ignore their questions!
        3. PROBING: If the candidate gives a very short, trailing, empty, or gibberish answer (e.g. 'blah blah', 'I don't know', 'yes', 'no'), DO NOT advance the stage. Ask a gentle follow-up probing question to get more details (e.g. 'Could you give me a specific technical hurdle you solved?').
        4. TRANSITIONS: If the candidate answered sufficiently, acknowledge a specific detail they mentioned, and transition to the next stage (or conclude if Stage 4 is completed).
        
        Return strictly a JSON object with this schema:
        {{
          "response_text": "Your conversational dialogue",
          "next_stage": int (same as current_stage if follow-up, or current_stage + 1 if advancing, capped at 4),
          "is_final": bool
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
            
        return json.loads(clean_text)
        
    except Exception as e:
        logger.error(f"Error processing conversational turn: {e}")
        return get_mock_conversational_turn(history, current_stage, job_description, custom_questions)

def get_mock_conversational_turn(history: list[dict], current_stage: int, job_description: str, custom_questions: str = "") -> dict:
    """
    Mock back-and-forth conversational follow-up rules when Gemini key is absent.
    Handles gibberish, user questions, and stage transitions realistically.
    """
    # Get last candidate answer
    last_candidate_answer = ""
    for turn in reversed(history):
        if turn["role"] == "candidate":
            last_candidate_answer = turn["text"].strip()
            break
            
    is_empty = not last_candidate_answer or last_candidate_answer == "[No vocal answer recorded]"
    words = last_candidate_answer.split()
    word_count = len(words)
    
    # Gibberish/short checks
    is_gibberish = "blah" in last_candidate_answer.lower() or "nonsense" in last_candidate_answer.lower() or word_count < 4
    
    # Candidate question checking (starts with query words or ends with question mark)
    is_candidate_asking = last_candidate_answer.endswith("?") or any(last_candidate_answer.lower().startswith(q) for q in ["what", "how", "why", "can you", "could you", "tell me"])

    # 1. Answer Candidate Questions
    if is_candidate_asking and not is_empty:
        # Formulate dynamic conversational answer
        mock_clarifications = {
            1: "As the interviewer, I can tell you that we look for developers who have a solid grasp of web technologies. But returning to your background, what makes you a good fit?",
            2: "That's a very fair question! In our stack, we typically run Node.js/Python microservices. But focusing back on your project, what database challenges did you face?",
            3: "We value a collaborative engineering culture where teammates resolve design conflicts through data and metrics. Returning to your scenario, what action did you take?",
            4: "We balance fast delivery with stability by scheduling refactoring iterations immediately following quick feature releases. Looking at your experience, how would you decide?"
        }
        return {
            "response_text": mock_clarifications.get(current_stage, "That is a great query. We balance fast delivery with code quality. But returning to your resume, what challenges have you solved?"),
            "next_stage": current_stage,
            "is_final": False
        }

    # 2. Probe Gibberish/Refusal
    if (is_empty or is_gibberish) and current_stage <= 4:
        probing_questions = {
            1: "I didn't catch that. Could you please walk me through your background and outline your primary engineering experience?",
            2: "That answer is a bit too brief. Could you go into more technical detail? What frameworks or tools did you write for this project?",
            3: "Could you share a specific situation where you had a disagreement or bottleneck, detailing your action and the result?",
            4: "Could you unpack your reasoning a bit more? How would you communicate technical trade-offs to business stakeholders?"
        }
        return {
            "response_text": probing_questions.get(current_stage, "Could you elaborate on that point? I'd like to hear more details about your work."),
            "next_stage": current_stage,
            "is_final": False
        }
        
    # 3. Advance stage
    next_stage = current_stage + 1
    
    if next_stage > 4:
        return {
            "response_text": "Thank you so much for your time. That concludes our interview session. I will compile your scorecard telemetry report now.",
            "next_stage": 4,
            "is_final": True
        }
        
    # Get next base question
    mock_list = get_mock_questions("", job_description, custom_questions)
    next_q_data = mock_list[next_stage - 1]
    
    # Acknowledge and transition (never say "nice answer" statically)
    transitions = {
        2: f"That makes sense. Thank you for walking me through your background. Let's move into a technical project. {next_q_data['question']}",
        3: f"I appreciate that technical explanation. Let's transition to a behavioral scenario. {next_q_data['question']}",
        4: f"Great details. Finally, let's explore architectural trade-offs under deadlines. {next_q_data['question']}"
    }
    
    return {
        "response_text": transitions.get(next_stage, next_q_data['question']),
        "next_stage": next_stage,
        "is_final": False
    }
