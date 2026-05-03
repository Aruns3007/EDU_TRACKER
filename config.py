import os
from pathlib import Path

# Set up base directories
base_path = Path(__file__).resolve().parent

try:
    from dotenv import load_dotenv
    load_dotenv(base_path / '.env')
except ImportError:
    pass

INSTANCE_PATH = base_path / 'instance'
UPLOAD_PATH = base_path / 'static' / 'uploads'
VAULT_PATH = UPLOAD_PATH / 'certificates'

# Fixed DB Directory for Windows Stability
local_appdata = os.environ.get('LOCALAPPDATA')
if local_appdata:
    DB_DIR = Path(local_appdata) / 'Edu_tracker'
else:
    DB_DIR = INSTANCE_PATH

DATABASE_FILE = DB_DIR / 'database.db'

# Ensure directories exist
INSTANCE_PATH.mkdir(parents=True, exist_ok=True)
UPLOAD_PATH.mkdir(parents=True, exist_ok=True)
VAULT_PATH.mkdir(parents=True, exist_ok=True)
DB_DIR.mkdir(parents=True, exist_ok=True)

class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY', 'your_secret_key_123')
    TEACHER_ACCESS_CODE = os.environ.get('TEACHER_ACCESS_CODE', 'EDUTRACK-TEACHER')
    ATTENDANCE_SHEET_FILE = str(DB_DIR / 'attendance_records.csv')
    OPENAI_API_KEY = os.environ.get('OPENAI_API_KEY', '')
    OPENAI_MODEL = os.environ.get('OPENAI_MODEL', 'gpt-5.4-mini')
    OPENAI_IMAGE_MODEL = os.environ.get('OPENAI_IMAGE_MODEL', 'gpt-image-1-mini')
    ENABLE_OPENAI_IMAGES = os.environ.get('ENABLE_OPENAI_IMAGES', '0').lower() in ('1', 'true', 'yes', 'on')
    FREE_FIRST_MEDIA_MODE = os.environ.get('FREE_FIRST_MEDIA_MODE', '1').lower() in ('1', 'true', 'yes', 'on')
    OLLAMA_MODEL = os.environ.get('OLLAMA_MODEL', 'gemma3:4b')
    OLLAMA_FALLBACK_MODELS = os.environ.get(
        'OLLAMA_FALLBACK_MODELS',
        'qwen2.5vl:7b,llama3.2-vision:11b,llama3.2:3b'
    )
    OLLAMA_HOST = os.environ.get('OLLAMA_HOST', 'http://localhost:11434')
    OLLAMA_TIMEOUT_SECONDS = int(os.environ.get('OLLAMA_TIMEOUT_SECONDS', '90'))
    CHAT_HISTORY_LIMIT = int(os.environ.get('CHAT_HISTORY_LIMIT', '16'))
    
    # Crucial: Use as_posix() for SQLite compatibility on Windows
    SQLALCHEMY_DATABASE_URI = f"sqlite:///{DATABASE_FILE.as_posix()}"
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    
    UPLOAD_FOLDER = str(UPLOAD_PATH)
    VAULT_FOLDER = str(VAULT_PATH)
