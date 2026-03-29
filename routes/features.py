import io
import json
import os
from datetime import datetime
from functools import wraps

import requests
from bson import ObjectId
from flask import (Blueprint, jsonify, redirect, render_template,
                   request, session, url_for)

from extensions import mongo

features_bp = Blueprint('features', __name__)

MISTRAL_API_KEY = os.getenv('MISTRAL_API_KEY', '')
MISTRAL_URL     = 'https://api.mistral.ai/v1/chat/completions'
MODEL           = 'mistral-small-latest'

# ── PDF / DOCX parsers (optional imports) ────────────────────────────────────
try:
    import fitz  # PyMuPDF
    HAS_PYMUPDF = True
except ImportError:
    HAS_PYMUPDF = False

try:
    from docx import Document as DocxDocument
    HAS_DOCX = True
except ImportError:
    HAS_DOCX = False


# ── helpers ───────────────────────────────────────────────────────────────────

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get('user_id'):
            return redirect(url_for('auth.login'))
        return f(*args, **kwargs)
    return decorated


def mistral(system: str, user: str, max_tokens: int = 1500) -> str:
    headers = {
        'Authorization': f'Bearer {MISTRAL_API_KEY}',
        'Content-Type':  'application/json',
    }
    body = {
        'model':      MODEL,
        'max_tokens': max_tokens,
        'messages':   [
            {'role': 'system', 'content': system},
            {'role': 'user',   'content': user},
        ],
    }
    resp = requests.post(MISTRAL_URL, headers=headers, json=body, timeout=45)
    resp.raise_for_status()
    return resp.json()['choices'][0]['message']['content']


def mistral_convo(messages: list, max_tokens: int = 700) -> str:
    headers = {
        'Authorization': f'Bearer {MISTRAL_API_KEY}',
        'Content-Type':  'application/json',
    }
    body = {'model': MODEL, 'max_tokens': max_tokens, 'messages': messages}
    resp = requests.post(MISTRAL_URL, headers=headers, json=body, timeout=45)
    resp.raise_for_status()
    return resp.json()['choices'][0]['message']['content']


def log_activity(user_id: str, action: str, detail: str = ''):
    mongo.db.activity.insert_one({
        'user_id':    user_id,
        'action':     action,
        'detail':     detail,
        'created_at': datetime.utcnow(),
    })


def parse_json(raw: str) -> dict | None:
    """Strip markdown fences and parse JSON."""
    cleaned = raw.strip()
    if cleaned.startswith('```'):
        cleaned = cleaned.split('\n', 1)[-1]
    if cleaned.endswith('```'):
        cleaned = cleaned.rsplit('```', 1)[0]
    try:
        return json.loads(cleaned)
    except Exception:
        return None


# ── 1. Placement Predictor ────────────────────────────────────────────────────

@features_bp.route('/placement-predictor')
@login_required
def placement_predictor():
    return render_template('features/placement_predictor.html')


@features_bp.route('/api/placement-predictor', methods=['POST'])
@login_required
def api_placement_predictor():
    d = request.get_json(force=True)
    system = (
        "You are a placement probability expert for Indian engineering students. "
        "Return ONLY a valid JSON object — no markdown, no extra text — with keys: "
        "overall_probability (int 0-100), tier1_probability, tier2_probability, "
        "tier3_probability, strengths (list), weaknesses (list), "
        "improvement_areas (list), estimated_package (string e.g. '8-14 LPA'), "
        "top_matching_companies (list), reasoning (string), action_plan (list)."
    )
    prompt = (
        f"CGPA: {d.get('cgpa')}\n"
        f"Skills: {', '.join(d.get('skills', []))}\n"
        f"Projects: {d.get('projects_count')} projects\n"
        f"Internships: {d.get('internships')}\n"
        f"DSA Problems Solved: {d.get('dsa_count')}\n"
        f"Communication (1-10): {d.get('communication')}\n"
        f"Target Companies: {', '.join(d.get('target_companies', []))}\n"
        f"Branch: {d.get('branch')}\n"
        f"College Tier: {d.get('college_tier')}\n"
        f"Certifications: {d.get('certifications', 'None')}\n"
        f"Active Backlogs: {d.get('backlogs', 0)}"
    )
    try:
        raw    = mistral(system, prompt, 1400)
        parsed = parse_json(raw)
        if not parsed:
            return jsonify(success=False, error='JSON parse failed', raw=raw)
        mongo.db.users.update_one(
            {'_id': ObjectId(session['user_id'])},
            {'$set': {'placement_probability': parsed.get('overall_probability', 0)}}
        )
        log_activity(session['user_id'], 'Placement Predictor',
                     f"Score: {parsed.get('overall_probability')}%")
        return jsonify(success=True, data=parsed)
    except Exception as exc:
        return jsonify(success=False, error=str(exc))


# ── 2. Skill Gap Analyzer ─────────────────────────────────────────────────────

@features_bp.route('/skill-gap')
@login_required
def skill_gap():
    return render_template('features/skill_gap.html')


@features_bp.route('/api/skill-gap', methods=['POST'])
@login_required
def api_skill_gap():
    d = request.get_json(force=True)
    system = (
        "You are a technical skill gap analyzer for software engineering placements. "
        "Return ONLY valid JSON with keys: gap_score (int 0-100, 100=no gap), "
        "critical_gaps (list of {skill, importance, resources}), "
        "existing_strengths (list), "
        "recommended_skills (list of {skill, timeline, priority}), "
        "roadmap (list of {week, tasks}), "
        "company_specific_gaps (object {CompanyName: [missing_skills]}). "
        "No markdown, no extra text."
    )
    prompt = (
        f"Target Role: {d.get('target_role')}\n"
        f"Target Companies: {', '.join(d.get('companies', []))}\n"
        f"Current Skills: {', '.join(d.get('current_skills', []))}\n"
        f"Experience: {d.get('experience')}\n"
        f"Timeline: {d.get('timeline')} months"
    )
    try:
        raw    = mistral(system, prompt, 1600)
        parsed = parse_json(raw)
        if not parsed:
            return jsonify(success=False, error='JSON parse failed', raw=raw)
        log_activity(session['user_id'], 'Skill Gap Analysis',
                     f"Role: {d.get('target_role')}")
        return jsonify(success=True, data=parsed)
    except Exception as exc:
        return jsonify(success=False, error=str(exc))


# ── 3. AI Interview Simulator ─────────────────────────────────────────────────

@features_bp.route('/interview-simulator')
@login_required
def interview_simulator():
    return render_template('features/interview_simulator.html')


@features_bp.route('/api/interview/start', methods=['POST'])
@login_required
def api_interview_start():
    config = request.get_json(force=True)
    session['interview_config']  = config
    session['interview_history'] = []

    system = (
        f"You are a senior technical interviewer at {config.get('company', 'a top tech company')} "
        f"hiring for {config.get('role', 'SDE')}. "
        "Conduct a realistic, challenging interview. Ask ONE question at a time. "
        "Mix technical (DSA, system design, CS fundamentals), behavioral, and project questions. "
        "After each candidate answer provide: a brief score (1-10), highlight reasoning quality, "
        "communication clarity, then ask the next question. "
        "Start now: introduce yourself briefly and ask your first question."
    )
    try:
        intro = mistral_convo(
            [{'role': 'system', 'content': system},
             {'role': 'user',   'content': 'Begin the interview.'}],
            500
        )
        session['interview_history'] = [{'role': 'assistant', 'content': intro}]
        return jsonify(success=True, message=intro)
    except Exception as exc:
        return jsonify(success=False, error=str(exc))


@features_bp.route('/api/interview/respond', methods=['POST'])
@login_required
def api_interview_respond():
    data    = request.get_json(force=True)
    history = session.get('interview_history', [])
    config  = session.get('interview_config', {})

    history.append({'role': 'user', 'content': data.get('answer', '')})

    system = (
        f"You are a senior technical interviewer at "
        f"{config.get('company', 'top tech company')} for "
        f"{config.get('role', 'SDE')}. "
        "Evaluate the answer: give score (1-10), note strengths/gaps in reasoning, "
        "comment on communication quality, then ask the next interview question."
    )
    messages = [{'role': 'system', 'content': system}] + history

    try:
        reply = mistral_convo(messages, 600)
        history.append({'role': 'assistant', 'content': reply})
        session['interview_history'] = history
        return jsonify(success=True, message=reply, turn=len(history) // 2)
    except Exception as exc:
        return jsonify(success=False, error=str(exc))


@features_bp.route('/api/interview/end', methods=['POST'])
@login_required
def api_interview_end():
    history = session.get('interview_history', [])
    config  = session.get('interview_config', {})
    transcript = '\n'.join(
        f"{m['role'].upper()}: {m['content']}" for m in history
    )
    system = (
        "You are an expert interview evaluator. "
        "Analyse the full interview transcript and return ONLY valid JSON with keys: "
        "overall_score (int 0-100), technical_score, communication_score, "
        "problem_solving_score, confidence_score, reasoning_depth, "
        "strengths (list), areas_to_improve (list), detailed_feedback (string), "
        "hiring_recommendation (one of: Strong Yes / Yes / Maybe / No), "
        "key_moments (list). No markdown, no extra text."
    )
    try:
        raw    = mistral(system, f"Transcript:\n{transcript}", 1400)
        parsed = parse_json(raw)
        if not parsed:
            return jsonify(success=False, error='JSON parse failed', raw=raw)

        mongo.db.interview_sessions.insert_one({
            'user_id':    session['user_id'],
            'config':     config,
            'scores':     parsed,
            'created_at': datetime.utcnow(),
        })
        mongo.db.users.update_one(
            {'_id': ObjectId(session['user_id'])},
            {'$push': {'interview_sessions': {
                'date':  datetime.utcnow(),
                'score': parsed.get('overall_score'),
            }}}
        )
        log_activity(session['user_id'], 'Interview Completed',
                     f"Score: {parsed.get('overall_score')}")
        return jsonify(success=True, data=parsed)
    except Exception as exc:
        return jsonify(success=False, error=str(exc))


# ── 4. Resume File Upload (text extractor) ───────────────────────────────────

@features_bp.route('/api/resume-upload', methods=['POST'])
@login_required
def api_resume_upload():
    """Accept a PDF / DOCX / TXT file and return extracted plain text."""
    if 'file' not in request.files:
        return jsonify(success=False, error='No file provided')
    f = request.files['file']
    if not f or not f.filename:
        return jsonify(success=False, error='Empty file')

    fname    = f.filename.lower()
    raw_data = f.read()

    try:
        if fname.endswith('.pdf'):
            if not HAS_PYMUPDF:
                return jsonify(success=False, error='PDF parsing unavailable – install PyMuPDF')
            doc  = fitz.open(stream=raw_data, filetype='pdf')
            text = '\n'.join(page.get_text() for page in doc)
        elif fname.endswith('.docx'):
            if not HAS_DOCX:
                return jsonify(success=False, error='DOCX parsing unavailable – install python-docx')
            doc  = DocxDocument(io.BytesIO(raw_data))
            text = '\n'.join(p.text for p in doc.paragraphs)
        else:
            # plain text / .txt
            text = raw_data.decode('utf-8', errors='replace')

        if not text.strip():
            return jsonify(success=False, error='Could not extract text from file')

        return jsonify(success=True, text=text.strip())
    except Exception as exc:
        return jsonify(success=False, error=str(exc))


# ── 4b. Resume ATS Scorer ──────────────────────────────────────────────────────

@features_bp.route('/resume-ats')
@login_required
def resume_ats():
    return render_template('features/resume_ats.html')


@features_bp.route('/api/resume-ats', methods=['POST'])
@login_required
def api_resume_ats():
    d = request.get_json(force=True)
    system = (
        "You are an expert ATS (Applicant Tracking System) and resume evaluator. "
        "Return ONLY valid JSON with keys: ats_score (int 0-100), keyword_match_score, "
        "format_score, content_score, impact_score, matched_keywords (list), "
        "missing_keywords (list), "
        "section_scores ({summary, experience, skills, education, projects}), "
        "critical_issues (list), improvements (list), "
        "rewritten_bullets (list of improved examples), "
        "overall_verdict (Strong/Good/Average/Weak). No markdown."
    )
    prompt = (
        f"Resume Content:\n{d.get('resume_text', '')}\n\n"
        f"Job Description:\n{d.get('jd_text', 'Not provided')}"
    )
    try:
        raw    = mistral(system, prompt, 1600)
        parsed = parse_json(raw)
        if not parsed:
            return jsonify(success=False, error='JSON parse failed', raw=raw)
        mongo.db.users.update_one(
            {'_id': ObjectId(session['user_id'])},
            {'$set': {'resume_score': parsed.get('ats_score', 0)}}
        )
        log_activity(session['user_id'], 'Resume ATS Scored',
                     f"Score: {parsed.get('ats_score')}")
        return jsonify(success=True, data=parsed)
    except Exception as exc:
        return jsonify(success=False, error=str(exc))


# ── 5. Company Prediction Engine ──────────────────────────────────────────────

@features_bp.route('/company-predictor')
@login_required
def company_predictor():
    return render_template('features/company_predictor.html')


@features_bp.route('/api/company-predictor', methods=['POST'])
@login_required
def api_company_predictor():
    d = request.get_json(force=True)
    system = (
        "You are a company-fit prediction engine for tech placements in India. "
        "Return ONLY valid JSON with keys: "
        "recommendations (list of {company, fit_score, tier, package_range, "
        "matching_reasons, gaps_to_fill, interview_process, application_timeline, difficulty}), "
        "avoid_companies (list of {company, reason}), strategy (string), "
        "total_companies_analysed (int). "
        "Include 8-10 company recommendations. No markdown."
    )
    prompt = (
        f"Skills: {', '.join(d.get('skills', []))}\n"
        f"CGPA: {d.get('cgpa')}\nBranch: {d.get('branch')}\n"
        f"DSA Level: {d.get('dsa_level')}\nProjects: {d.get('projects')}\n"
        f"Internship: {d.get('internship')}\n"
        f"Preferred Location: {d.get('location')}\n"
        f"Expected CTC: {d.get('expected_ctc')} LPA"
    )
    try:
        raw    = mistral(system, prompt, 1800)
        parsed = parse_json(raw)
        if not parsed:
            return jsonify(success=False, error='JSON parse failed', raw=raw)
        log_activity(session['user_id'], 'Company Prediction',
                     f"{len(parsed.get('recommendations', []))} companies found")
        return jsonify(success=True, data=parsed)
    except Exception as exc:
        return jsonify(success=False, error=str(exc))


# ── 6. Personalized Learning Path ────────────────────────────────────────────

@features_bp.route('/learning-path')
@login_required
def learning_path():
    return render_template('features/learning_path.html')


@features_bp.route('/api/learning-path', methods=['POST'])
@login_required
def api_learning_path():
    d = request.get_json(force=True)
    system = (
        "You are a personalized learning path generator for software engineering placements. "
        "Return ONLY valid JSON with keys: total_duration (string), "
        "daily_hours_needed (int), "
        "phases (list of {phase, title, duration, focus, "
        "topics (list of {topic, subtopics, resources, estimated_hours}), "
        "milestones, projects}), "
        "weekly_schedule ({Monday:[], Tuesday:[], ...}), "
        "checkpoints (list of {week, goal, assessment}), tips (list). "
        "No markdown."
    )
    prompt = (
        f"Target Role: {d.get('target_role')}\n"
        f"Target Company: {d.get('target_company')}\n"
        f"Current Skills: {', '.join(d.get('current_skills', []))}\n"
        f"Weak Areas: {', '.join(d.get('weak_areas', []))}\n"
        f"Available: {d.get('hours_per_day')} hours/day\n"
        f"Timeline: {d.get('timeline')} weeks\n"
        f"Learning Style: {d.get('learning_style', 'mixed')}"
    )
    try:
        raw    = mistral(system, prompt, 2000)
        parsed = parse_json(raw)
        if not parsed:
            return jsonify(success=False, error='JSON parse failed', raw=raw)
        mongo.db.users.update_one(
            {'_id': ObjectId(session['user_id'])},
            {'$set': {'learning_path': parsed}}
        )
        log_activity(session['user_id'], 'Learning Path Generated',
                     f"Role: {d.get('target_role')}")
        return jsonify(success=True, data=parsed)
    except Exception as exc:
        return jsonify(success=False, error=str(exc))


# ── 7. AI Project Evaluator ───────────────────────────────────────────────────

@features_bp.route('/project-evaluator')
@login_required
def project_evaluator():
    return render_template('features/project_evaluator.html')


@features_bp.route('/api/project-evaluator', methods=['POST'])
@login_required
def api_project_evaluator():
    d = request.get_json(force=True)
    system = (
        "You are a technical project evaluator for placement interviews. "
        "Return ONLY valid JSON with keys: overall_score (int 0-100), "
        "technical_complexity, innovation_score, scalability_score, "
        "presentation_readiness, resume_impact (High/Medium/Low), "
        "strengths (list), weaknesses (list), improvement_suggestions (list), "
        "interview_questions (list), how_to_present (string), "
        "missing_features (list), "
        "tech_stack_review ({stack_chosen, alternatives, justification}), "
        "github_checklist (list), verdict (Excellent/Good/Average/Needs Work). "
        "No markdown."
    )
    prompt = (
        f"Project Title: {d.get('title')}\n"
        f"Description: {d.get('description')}\n"
        f"Tech Stack: {d.get('tech_stack')}\n"
        f"Features: {d.get('features')}\n"
        f"Problem Solved: {d.get('problem')}\n"
        f"Scale/Users: {d.get('scale', 'Personal project')}\n"
        f"GitHub Link: {d.get('github', 'Not provided')}"
    )
    try:
        raw    = mistral(system, prompt, 1600)
        parsed = parse_json(raw)
        if not parsed:
            return jsonify(success=False, error='JSON parse failed', raw=raw)
        log_activity(session['user_id'], 'Project Evaluated',
                     f"{d.get('title')}: {parsed.get('overall_score')}/100")
        return jsonify(success=True, data=parsed)
    except Exception as exc:
        return jsonify(success=False, error=str(exc))


# ── 8. Placement Trend Analysis ───────────────────────────────────────────────

@features_bp.route('/trend-analysis')
@login_required
def trend_analysis():
    return render_template('features/trend_analysis.html')


@features_bp.route('/api/trend-analysis', methods=['POST'])
@login_required
def api_trend_analysis():
    d = request.get_json(force=True)
    system = (
        "You are a tech industry placement trend analyst. "
        "Return ONLY valid JSON with keys: "
        "domain_trends (list of {domain, growth, demand, top_skills, avg_package}), "
        "emerging_skills (list of {skill, demand_growth, timeline, difficulty}), "
        "declining_skills (list), "
        "company_hiring_trends (list of {company, headcount_change, focus_areas}), "
        "salary_trends ({2023, 2024, 2025_prediction}), "
        "remote_vs_onsite ({remote, hybrid, onsite} as % strings), "
        "top_roles_2025 (list of {role, avg_ctc, growth}), "
        "insights (list), recommendations (list). No markdown."
    )
    prompt = (
        f"Domain: {d.get('domain', 'Software Engineering')}\n"
        f"Location: {d.get('location', 'India')}\n"
        f"Role: {d.get('role', 'SDE')}\nYear: 2025"
    )
    try:
        raw    = mistral(system, prompt, 1800)
        parsed = parse_json(raw)
        if not parsed:
            return jsonify(success=False, error='JSON parse failed', raw=raw)
        log_activity(session['user_id'], 'Trend Analysis',
                     f"Domain: {d.get('domain')}")
        return jsonify(success=True, data=parsed)
    except Exception as exc:
        return jsonify(success=False, error=str(exc))


# ── 9. AI Career Mentor (conversational) ─────────────────────────────────────

@features_bp.route('/career-mentor')
@login_required
def career_mentor():
    return render_template('features/career_mentor.html')


@features_bp.route('/api/career-mentor', methods=['POST'])
@login_required
def api_career_mentor():
    data         = request.get_json(force=True)
    history      = data.get('history', [])
    user_message = data.get('message', '')
    user_goals   = data.get('user_goals', 'Get placed in a top tech company')

    system = (
        f"You are PlacementAI's expert career mentor — warm, knowledgeable, and deeply "
        f"experienced in Indian tech placements. "
        f"Help {session.get('fullname', 'the student')} with: career path decisions, "
        f"interview strategies, skill development, salary negotiation, imposter syndrome, "
        f"company selection, and placement anxiety. "
        f"Student goal: {user_goals}. "
        "Be conversational, empathetic, and give specific actionable advice."
    )

    messages = [{'role': 'system', 'content': system}]
    messages += history[-12:]          # keep last 12 turns for context
    messages.append({'role': 'user', 'content': user_message})

    try:
        reply = mistral_convo(messages, 700)
        return jsonify(success=True, message=reply)
    except Exception as exc:
        return jsonify(success=False, error=str(exc))


# ── 10. Aptitude & Reasoning Practice ────────────────────────────────────────

@features_bp.route('/aptitude')
@login_required
def aptitude():
    return render_template('features/aptitude.html')


@features_bp.route('/api/aptitude/generate', methods=['POST'])
@login_required
def api_aptitude_generate():
    d        = request.get_json(force=True)
    category = d.get('category', 'Mixed')
    diff     = d.get('difficulty', 'Medium')
    count    = min(int(d.get('count', 10)), 20)

    system = (
        "You are an expert aptitude and reasoning question setter for Indian engineering "
        "placement tests (TCS, Infosys, Wipro, Cognizant, Capgemini, Accenture, etc.). "
        f"Generate exactly {count} multiple-choice questions for the '{category}' category "
        f"at '{diff}' difficulty. "
        "Return ONLY valid JSON — a list of objects, each with keys: "
        "id (1-indexed int), question (string), options (list of exactly 4 strings A-D), "
        "answer (string — the correct option letter, e.g. 'A'), "
        "explanation (string — clear step-by-step solution), "
        "topic (string — sub-topic name), time_limit (int — seconds recommended). "
        "No markdown, no extra text."
    )
    prompt = (
        f"Category: {category}\nDifficulty: {diff}\nCount: {count}\n"
        "Make questions realistic and based on actual company placement patterns."
    )
    try:
        raw    = mistral(system, prompt, 3000)
        parsed = parse_json(raw)
        if not parsed or not isinstance(parsed, list):
            return jsonify(success=False, error='Failed to generate questions', raw=raw)
        log_activity(session['user_id'], 'Aptitude Practice',
                     f"{category} – {diff} – {count} Qs")
        return jsonify(success=True, questions=parsed)
    except Exception as exc:
        return jsonify(success=False, error=str(exc))


@features_bp.route('/api/aptitude/explain', methods=['POST'])
@login_required
def api_aptitude_explain():
    """Get a deeper AI explanation for a specific question."""
    d = request.get_json(force=True)
    system = (
        "You are an expert aptitude tutor. Provide a thorough, student-friendly explanation "
        "for the following aptitude question. Include the approach, any formulas used, "
        "and why each wrong option is incorrect. Keep it under 200 words."
    )
    prompt = (
        f"Question: {d.get('question')}\n"
        f"Options: {d.get('options')}\n"
        f"Correct Answer: {d.get('answer')}\n"
        f"Brief Explanation: {d.get('explanation')}"
    )
    try:
        reply = mistral(system, prompt, 400)
        return jsonify(success=True, explanation=reply)
    except Exception as exc:
        return jsonify(success=False, error=str(exc))
