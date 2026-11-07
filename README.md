<div align="center">
  <h1>🚀 PlacementAI</h1>
  <p><strong>Your Ultimate AI-Powered Placement & Career Guardian</strong></p>

  [![Python Version](https://img.shields.io/badge/python-3.9+-blue.svg)](https://www.python.org/downloads/)
  [![Flask](https://img.shields.io/badge/Flask-3.0.3-black.svg?logo=flask)](https://flask.palletsprojects.com/)
  [![MongoDB](https://img.shields.io/badge/MongoDB-4.7.3-green.svg?logo=mongodb)](https://www.mongodb.com/)
  [![Mistral AI](https://img.shields.io/badge/AI-Mistral_LLM-orange.svg)](https://mistral.ai/)
</div>

---

PlacementAI is a comprehensive, intelligent web platform designed to empower engineering students and job seekers in India. By leveraging advanced Large Language Models (Mistral AI), it identifies skill gaps, simulates realistic interviews, evaluates resumes through ATS algorithms, and provides highly personalized roadmaps to ensure every user is industry-ready and confident for their dream placements.

![Dashboard Preview](docs/images/dashboard.png)

## ✨ Key Features

1. **📊 Placement Predictor**
   - Calculates your overall placement probability based on CGPA, skills, projects, and target companies.
   - Provides an action plan and highlights your strengths and weaknesses.

2. **🤖 AI Interview Simulator**
   - Engages users in a realistic technical interview. Ask questions natively, get scored by an AI interviewer with detailed breakdown on communication, problem-solving, and tech knowledge.
   
   ![Interview Simulator](docs/images/interview.png)

3. **📄 ATS Resume Scorer**
   - Upload your PDF/DOCX resume alongside a job description.
   - Gets parsed automatically and receives a format, content, and keyword match score (0-100) detailing exactly what keywords are missing.
   
   ![Resume ATS](docs/images/ats_resume.png)

4. **📈 Skill Gap Analyzer & Learning Pathways**
   - Finds critical gaps between your current skill set and your dream roles.
   - Generates fully personalized, day-by-day learning schedules and milestones tailored just for you.

5. **🏢 Company Fit Predictor**
   - Suggests the top 8-10 companies perfect for your profile and gives actionable strategies to clear their unique hiring processes.

6. **💼 AI Project Evaluator & Trend Analysis**
   - Run your GitHub projects through our AI to understand complexity, innovation, and "interview-readiness".
   - Stay updated on 2025 tech hiring trends, remote vs. onsite shifts, and emerging demands.

## 🛠️ Technology Stack

* **Backend:** Python, Flask, Flask-Mail, Flask-Session
* **Database:** MongoDB
* **Artificial Intelligence:** Mistral AI (`mistral-small-latest`)
* **Parsing:** PyMuPDF, `python-docx` for resume extraction
* **Frontend:** Jinja2 Templates, HTML5/CSS3

## ⚙️ Local Setup & Installation

To run this application locally, ensure you have Python 3.9+ and MongoDB installed and running.

1. **Clone the repository** (if hosted):
   ```bash
   git clone https://github.com/yourusername/placementai.git
   cd placementai
   ```

2. **Create a virtual environment:**
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. **Install Dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

4. **Environment Variables Config:**
   Create a `.env` file in the root directory and add the following keys:
   ```env
   SECRET_KEY=your_secret_key_here
   MONGO_URI=mongodb://localhost:27017/placementai
   MAIL_USERNAME=your_gmail@gmail.com
   MAIL_APP_PASSWORD=your_gmail_app_password
   # Recommended free-tier provider:
   GEMINI_API_KEY=your_google_ai_studio_key
   # Optional fallback:
   MISTRAL_API_KEY=your_mistral_api_key
   ```
   On Windows, copy `.env.example` to `.env`, then replace
   `MISTRAL_API_KEY` with your own key from the Mistral console. Do not commit
   `.env` or paste the key into source code. An empty key intentionally makes
   AI endpoints return a clear `503` instead of sending an invalid request.
   `MONGO_URI` and the AI provider keys are validated at startup. Gemini is
   preferred when `GEMINI_API_KEY` is present and uses the free Google AI
   Studio tier. If MongoDB is
   unavailable, the app automatically uses a local file-backed store at
   `data/placementai_fallback.json` (or set `FALLBACK_STORAGE_MODE=memory` for
   ephemeral development). AI feature APIs return a clear `503` dependency
   response until `GEMINI_API_KEY` or `MISTRAL_API_KEY` is configured. The app
   uses Google's `gemini-flash-lite-latest` model. Check
   `/api/status` for the current dependency state.

5. **Run the Application!**
   ```bash
   python app.py
   ```
   > The platform will be accessible at `http://localhost:5000`

## ▲ Deploying on Vercel

Vercel is suitable for the portfolio demo and API, but its filesystem is
ephemeral. Before deploying, create a MongoDB Atlas database and configure
these Vercel project environment variables for **Production**:

```env
SECRET_KEY=<long-random-value>
MONGO_URI=<mongodb-atlas-connection-string>
GEMINI_API_KEY=<google-ai-studio-key>
MAIL_USERNAME=<smtp-account>
MAIL_APP_PASSWORD=<smtp-app-password>
COOKIE_SECURE=true
```

Import the GitHub repository into Vercel and deploy from the repository root.
The included `vercel.json` routes requests through `api/index.py`. On Vercel,
sessions use signed cookies and the local fallback is memory-only; persistent
login accounts and activity therefore require `MONGO_URI`.

After deployment, verify:

- `/` loads the login page.
- `/api/status` reports Gemini configured and MongoDB available without a
  fallback warning.
- Signup, login, and one AI feature work on the deployed URL.

Never upload `.env` to Vercel or commit it to Git. Add secrets in Vercel's
Environment Variables settings, and rotate any key that was previously exposed
in repository history.

## 🤝 Contributing

Contributions, issues, and feature requests are welcome! Feel free to check the issues page.

## 🧭 Portfolio-ready highlights

- Multi-provider AI integration: Gemini free tier first, Mistral fallback.
- MongoDB with a transparent local JSON fallback for zero-setup demos.
- CSRF protection, secure session-cookie defaults, upload/request limits, and
  clear dependency health reporting at `/api/status`.
- Responsive dashboard navigation and an animated, mobile-safe authentication
  experience.
- Pytest smoke coverage for fallback storage, authentication, CSRF, and AI
  dependency errors.

Before publishing, revoke any API key that has ever been committed, remove
`.env` and runtime data from Git history, and configure secrets through the
deployment platform rather than source control.

---
<div align="center">
  <i>Built to make career success predictable, not accidental.</i>
</div>
