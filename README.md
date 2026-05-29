# Edu Tracker

Edu Tracker is a Flask-based student and teacher portal for attendance, notes, timetable management, homework, and AI-assisted study help.

## Setup

1. Create a virtual environment and install dependencies:

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

2. Copy `.env.example` to `.env` and fill in your values.

3. Make sure you set at least:

```env
SECRET_KEY=your-long-random-secret
TEACHER_ACCESS_CODE=your-private-teacher-code
```

4. Run the app:

```bash
python app.py
```

## Deploying On PythonAnywhere

1. Upload this project to your PythonAnywhere home directory, for example `/home/yourusername/Edu_tracker`.
2. Create a virtualenv that matches the Python version you select for the web app.
3. Install the dependencies:

```bash
pip install -r requirements.txt
```

4. In the PythonAnywhere Web tab, choose `Manual configuration`, then set the virtualenv path to your environment.
5. Open the WSGI configuration file and point it at the project root and `wsgi.application`.
6. Add a static files mapping from `/static/` to `/home/yourusername/Edu_tracker/static`.
7. Upload your existing `instance/database.db` if you want to keep the current data.
8. Set `SECRET_KEY` and `TEACHER_ACCESS_CODE` in your environment before reloading the web app.

The repository now includes a small [`wsgi.py`](./wsgi.py) entrypoint so the app can be imported cleanly by PythonAnywhere.

## Environment Variables

- `SECRET_KEY`: Required for secure sessions.
- `TEACHER_ACCESS_CODE`: Required for teacher signup.
- `OPENAI_API_KEY`: Enables OpenAI-powered responses and image generation.
- `OPENAI_MODEL`: OpenAI text model to use. The default is `gpt-5.4-mini`, which is currently a valid OpenAI model name.
- `OPENAI_IMAGE_MODEL`: Image model name used for image generation.
- `ENABLE_OLLAMA`: Enables local Ollama fallback if you have it running.
- `OLLAMA_MODEL`: Primary Ollama model name.
- `OLLAMA_FALLBACK_MODELS`: Comma-separated fallback models for local AI.

## Notes

- `requirements.txt` no longer includes `marked`; the UI uses the browser-side CDN version instead.
- `use_reloader=False` is intentional to reduce SQLite file-lock issues on Windows. If you edit code while the server is running, restart the process manually.
- The repository includes `.env.example` so new contributors have a clean setup template.
- PythonAnywhere should import `wsgi.application` instead of calling `app.run()`.
