import base64
import html
import json
import mimetypes
import os
import sqlite3
from pathlib import Path
from urllib.parse import quote_plus
from urllib import error as urllib_error
from urllib import request as urllib_request
from flask import Blueprint, render_template, request, jsonify, redirect, url_for, current_app, send_from_directory
from flask_login import login_required, current_user
from werkzeug.utils import secure_filename
from datetime import datetime
from routes.access_control import student_required

# Safety check for the library installation
try:
    from youtube_search_python import VideosSearch
except ImportError:
    VideosSearch = None

try:
    from openai import OpenAI
except ImportError:
    OpenAI = None

try:
    from pypdf import PdfReader
except ImportError:
    PdfReader = None

try:
    import ollama
except ImportError:
    ollama = None

ai = Blueprint('ai', __name__)

# --- 1. Configuration ---
def get_db_connection():
    """Finds the configured SQLite database using the app config."""
    db_uri = current_app.config.get('SQLALCHEMY_DATABASE_URI', '')
    if db_uri.startswith('sqlite:///'):
        db_path = db_uri.replace('sqlite:///', '', 1)
    else:
        basedir = Path(__file__).resolve().parent.parent
        db_path = str(basedir / 'instance' / 'database.db')

    db_path = os.path.normpath(db_path)
    if not os.path.isabs(db_path):
        basedir = Path(__file__).resolve().parent.parent
        db_path = os.path.normpath(str(basedir / db_path))
    
    if not os.path.exists(db_path):
        return None
    try:
        conn = sqlite3.connect(db_path) 
        conn.row_factory = sqlite3.Row
        return conn
    except Exception as e:
        return None

# --- 2. Helper Functions ---

def _build_system_prompt():
    return (
        "You are EduTrack AI, a warm and practical study assistant for students.\n"
        "Explain things clearly, simply, and in a friendly tone.\n"
        "When a screenshot, image, or file is attached, analyze it carefully and use it to answer.\n"
        "If the user asks for an image, diagram, poster, cartoon, avatar, or study visual, create a helpful visual response.\n"
        "Give short steps, examples, and study tips when helpful.\n"
        "Use markdown only. Never output raw HTML.\n"
        "If the user writes in Tamil, reply in Tamil.\n"
        "Use conversation history when it is provided so follow-up questions stay connected.\n"
        "Keep the answer concise unless the question needs detail.\n"
        "If you mention media, refer to the provided links naturally."
    )

def _build_user_prompt(user_message, sched, vault, yt_context, image_context, attachment_context='', history_context=''):
    return (
        f"Conversation history:\n{history_context or 'None'}\n\n"
        f"User question: {user_message}\n\n"
        f"Schedule context: {sched}\n"
        f"Vault context: {vault}\n"
        f"{attachment_context}\n\n"
        f"Video links:\n{yt_context or 'None'}\n\n"
        f"Image links:\n{image_context or 'None'}"
    )

def _normalize_history(history):
    normalized = []
    if not isinstance(history, list):
        return normalized

    limit = current_app.config.get('CHAT_HISTORY_LIMIT', 16)
    for item in history[-limit:]:
        if len(normalized) >= current_app.config.get('CHAT_HISTORY_LIMIT', 16):
            break
        if not isinstance(item, dict):
            continue

        role = _safe_text(item.get('role') or '').lower()
        if role not in {'user', 'assistant'}:
            continue

        content = item.get('content')
        if content is None:
            continue

        text = str(content).strip()
        if not text:
            continue

        normalized.append({
            'role': role,
            'content': text[:2500],
        })

    return normalized

def _build_history_context(history):
    normalized = _normalize_history(history)
    if not normalized:
        return ''

    lines = ['Conversation history (most recent turns):']
    for item in normalized:
        label = 'User' if item['role'] == 'user' else 'Assistant'
        lines.append(f"{label}: {item['content']}")
    return '\n'.join(lines)

def _data_url_to_base64(data_url):
    if not data_url or ',' not in data_url:
        return ''
    return data_url.split(',', 1)[1].strip()

def _ollama_model_candidates():
    primary = current_app.config.get('OLLAMA_MODEL', 'gemma3:4b')
    fallbacks = current_app.config.get('OLLAMA_FALLBACK_MODELS', '')
    candidates = []

    for raw in (primary, fallbacks):
        if not raw:
            continue
        for candidate in str(raw).split(','):
            cleaned = candidate.strip()
            if cleaned and cleaned not in candidates:
                candidates.append(cleaned)

    return candidates or ['gemma3:4b']

def _call_ollama_chat(model_name, system_prompt, user_prompt, image_attachments=None):
    host = current_app.config.get('OLLAMA_HOST', 'http://localhost:11434').rstrip('/')
    timeout_seconds = current_app.config.get('OLLAMA_TIMEOUT_SECONDS', 90)
    message = {
        'role': 'user',
        'content': user_prompt,
    }

    image_payloads = []
    for item in image_attachments or []:
        data_url = item.get('data_url') or ''
        encoded = _data_url_to_base64(data_url)
        if encoded:
            image_payloads.append(encoded)

    if image_payloads:
        message['images'] = image_payloads

    payload = {
        'model': model_name,
        'messages': [
            {'role': 'system', 'content': system_prompt},
            message,
        ],
        'stream': False,
    }

    url = f"{host}/api/chat"
    body = json.dumps(payload).encode('utf-8')
    request_obj = urllib_request.Request(
        url,
        data=body,
        headers={'Content-Type': 'application/json'},
        method='POST',
    )

    with urllib_request.urlopen(request_obj, timeout=timeout_seconds) as response:
        raw_body = response.read().decode('utf-8', errors='replace')

    data = json.loads(raw_body or '{}')
    message_data = data.get('message', {}) if isinstance(data, dict) else {}
    if isinstance(message_data, dict):
        return _safe_text(message_data.get('content') or '')
    return ''

def _safe_text(value, default=''):
    text = str(value if value is not None else default)
    return text.replace('\n', ' ').replace('\r', ' ').strip()

def _safe_file_name(value, default='attachment'):
    text = _safe_text(value, default)
    return text or default

def _looks_like_text_file(name, mime_type):
    ext = Path(_safe_text(name)).suffix.lower()
    return (
        mime_type.startswith('text/')
        or ext in {'.txt', '.md', '.csv', '.json', '.log', '.xml', '.html', '.htm', '.py', '.js', '.css'}
    )

def _decode_data_url(data_url):
    if not data_url:
        return b''
    if isinstance(data_url, bytes):
        return data_url
    if not isinstance(data_url, str):
        return b''
    if ',' not in data_url or ';base64' not in data_url:
        return b''
    try:
        return base64.b64decode(data_url.split(',', 1)[1], validate=False)
    except Exception:
        return b''

def _extract_pdf_text(pdf_bytes):
    if not pdf_bytes or PdfReader is None:
        return ''
    try:
        from io import BytesIO
        reader = PdfReader(BytesIO(pdf_bytes))
        chunks = []
        for page in reader.pages[:8]:
            page_text = page.extract_text() or ''
            if page_text.strip():
                chunks.append(page_text.strip())
        return '\n\n'.join(chunks)[:6000]
    except Exception:
        return ''

def _normalize_attachments(attachments):
    normalized = []
    if not isinstance(attachments, list):
        return normalized

    for item in attachments[:6]:
        if not isinstance(item, dict):
            continue

        name = _safe_file_name(item.get('name') or item.get('filename'))
        mime_type = _safe_text(item.get('mime_type') or item.get('mime') or mimetypes.guess_type(name)[0] or '')
        kind = _safe_text(item.get('kind') or '').lower()
        text = _safe_text(item.get('text') or item.get('content') or '')
        data_url = _safe_text(item.get('data_url') or item.get('dataUrl') or item.get('data'))

        if kind == 'image' or mime_type.startswith('image/'):
            normalized.append({
                'kind': 'image',
                'name': name,
                'mime_type': mime_type or 'image/*',
                'data_url': data_url,
            })
            continue

        if kind == 'pdf' or mime_type == 'application/pdf' or name.lower().endswith('.pdf'):
            pdf_bytes = _decode_data_url(data_url)
            normalized.append({
                'kind': 'pdf',
                'name': name,
                'mime_type': mime_type or 'application/pdf',
                'text': _extract_pdf_text(pdf_bytes),
            })
            continue

        if kind == 'text' or _looks_like_text_file(name, mime_type):
            if not text and data_url:
                text_bytes = _decode_data_url(data_url)
                if text_bytes:
                    for encoding in ('utf-8', 'utf-16', 'latin-1'):
                        try:
                            text = text_bytes.decode(encoding)
                            break
                        except Exception:
                            continue
            normalized.append({
                'kind': 'text',
                'name': name,
                'mime_type': mime_type or 'text/plain',
                'text': text[:6000],
            })
            continue

        normalized.append({
            'kind': 'file',
            'name': name,
            'mime_type': mime_type or 'application/octet-stream',
            'text': text[:1000],
        })

    return normalized

def _build_attachment_context(attachments):
    normalized = _normalize_attachments(attachments)
    if not normalized:
        return '', []

    image_inputs = []
    summary_lines = ['Attachment context:']

    for item in normalized:
        kind = item.get('kind')
        name = item.get('name') or 'attachment'
        mime_type = item.get('mime_type') or ''

        if kind == 'image':
            if item.get('data_url'):
                image_inputs.append({
                    'type': 'input_image',
                    'image_url': item['data_url'],
                })
            summary_lines.append(f"- {name}: image or screenshot attached. Analyze visible text, diagrams, and UI carefully.")
        elif kind == 'pdf':
            extracted = _safe_text(item.get('text') or '')
            if extracted:
                summary_lines.append(f"- {name}: PDF text extract:\n{extracted}")
            else:
                summary_lines.append(f"- {name}: PDF attached, but text extraction did not return content.")
        elif kind == 'text':
            extracted = _safe_text(item.get('text') or '')
            if extracted:
                summary_lines.append(f"- {name}: text file content:\n{extracted}")
        else:
            summary_lines.append(f"- {name}: {mime_type or 'file'} attached.")

    return '\n\n'.join(summary_lines), image_inputs

def _extract_channel_name(video):
    channel = video.get('channel')
    if isinstance(channel, dict):
        return _safe_text(channel.get('name') or channel.get('title') or '')
    if channel:
        return _safe_text(channel)
    return _safe_text(video.get('channelName') or video.get('ownerText') or '')

def _extract_thumbnail_url(video):
    thumbnails = video.get('thumbnails') or video.get('thumbnail')
    if isinstance(thumbnails, list) and thumbnails:
        thumb = thumbnails[-1]
        if isinstance(thumb, dict):
            return _safe_text(thumb.get('url') or thumb.get('src') or '')
        return _safe_text(thumb)
    if isinstance(thumbnails, dict):
        return _safe_text(thumbnails.get('url') or thumbnails.get('src') or '')
    return ''

def _extract_snippet(video):
    snippet = video.get('descriptionSnippet') or video.get('description')
    if isinstance(snippet, list):
        parts = []
        for item in snippet:
            if isinstance(item, dict) and item.get('text'):
                parts.append(str(item['text']))
            else:
                parts.append(str(item))
        snippet = ' '.join(parts)
    return _safe_text(snippet)[:180]

def _build_video_search_queries(query):
    topic = _safe_text(query, 'study topic')
    return [
        f"{topic} tutorial",
        f"{topic} explained",
        f"{topic} lecture",
        f"{topic} practice problems",
        f"{topic} khan academy",
        f"{topic} crash course",
    ]

def _build_video_fallback_cards(query):
    topic = _safe_text(query, 'study topic')
    variants = [
        (f"{topic} tutorial", 'Tutorial Search'),
        (f"{topic} explained", 'Concept Search'),
        (f"{topic} lecture", 'Lecture Search'),
        (f"{topic} practice problems", 'Practice Search'),
    ]
    return [
        _format_video_card(
            {
                'url': f"https://www.youtube.com/results?search_query={quote_plus(search_query)}",
                'title': topic,
                'channel': label,
                'duration': '',
                'thumbnail': '',
                'snippet': f"Search YouTube for {search_query}.",
                'source': 'fallback',
            }
        )
        for search_query, label in variants
    ]

def _format_video_card(video):
    payload = {
        'url': _safe_text(video.get('url') or video.get('link')),
        'title': _safe_text(video.get('title') or 'Study Video'),
        'channel': _safe_text(video.get('channel') or ''),
        'duration': _safe_text(video.get('duration') or ''),
        'thumbnail': _safe_text(video.get('thumbnail') or ''),
        'snippet': _safe_text(video.get('snippet') or ''),
        'source': _safe_text(video.get('source') or ''),
    }
    return f"VIDEO_CARD:{json.dumps(payload, ensure_ascii=False)}"

def _build_study_image_prompt(query):
    topic = _safe_text(query, 'Study topic')
    lower = topic.lower()

    if any(word in lower for word in ['cartoon', 'avatar', 'character', 'mascot', 'student selfie']):
        return (
            f"Create a friendly cartoon-style student AI avatar inspired by '{topic}'. "
            "Use a clean classroom-friendly design, expressive face, warm colors, and a polished digital illustration look. "
            "Avoid photorealism, clutter, text walls, and watermarks."
        )

    if any(word in lower for word in ['photosynthesis', 'cell', 'biology', 'dna', 'ecology', 'human body', 'anatomy']):
        style = "clean biology infographic with labeled arrows, sections, and simple icons"
    elif any(word in lower for word in ['math', 'algebra', 'geometry', 'calculus', 'equation', 'probability']):
        style = "step-by-step math explainer with formula blocks, highlighted steps, and minimal clutter"
    elif any(word in lower for word in ['history', 'timeline', 'war', 'empire', 'freedom movement', 'civilization']):
        style = "timeline-style educational poster with dates, icons, and concise callouts"
    elif any(word in lower for word in ['physics', 'chemistry', 'force', 'energy', 'atom', 'wave', 'electric']):
        style = "technical science diagram with labeled components and directional arrows"
    elif any(word in lower for word in ['programming', 'coding', 'software', 'database', 'api', 'network']):
        style = "clean flowchart or architecture diagram with modular boxes and clear labels"
    else:
        style = "modern educational infographic with labeled sections, icons, and readable spacing"

    return (
        f"Create a high-quality educational diagram for students about '{topic}'. "
        f"Style: {style}. "
        "Use a polished classroom-friendly design, strong hierarchy, bright but balanced colors, "
        "large readable labels, and clear visual structure. "
        "Avoid watermarks, photorealistic people, tiny text, and busy backgrounds."
    )

def _generate_openai_study_image(query):
    api_key = current_app.config.get('OPENAI_API_KEY', '').strip()
    if (
        not api_key
        or OpenAI is None
        or not current_app.config.get('ENABLE_OPENAI_IMAGES', False)
    ):
        return ""

    prompt = _build_study_image_prompt(query)
    image_model = current_app.config.get('OPENAI_IMAGE_MODEL', 'gpt-image-1-mini')

    try:
        client = OpenAI(api_key=api_key)
        response = client.images.generate(
            model=image_model,
            prompt=prompt,
            size='1024x1024',
            quality='medium',
        )
        first = response.data[0] if getattr(response, 'data', None) else None
        if not first:
            return ""

        b64_image = getattr(first, 'b64_json', None)
        if not b64_image and isinstance(first, dict):
            b64_image = first.get('b64_json')

        if b64_image:
            safe_title = _safe_text(query or 'Study Topic')[:70]
            return f"IMAGE_LINK:[data:image/png;base64,{b64_image}]({safe_title})"
    except Exception as exc:
        print(f"OpenAI image error: {exc}")

    return ""

def _build_brain_svg(title):
    safe_title = html.escape(_safe_text(title, 'Human Brain')[:70].replace('(', '[').replace(')', ']'))
    svg = f"""
    <svg xmlns="http://www.w3.org/2000/svg" width="1200" height="720" viewBox="0 0 1200 720">
        <defs>
            <linearGradient id="bg" x1="0%" y1="0%" x2="100%" y2="100%">
                <stop offset="0%" stop-color="#020617"/>
                <stop offset="55%" stop-color="#111827"/>
                <stop offset="100%" stop-color="#581c87"/>
            </linearGradient>
            <linearGradient id="brainGlow" x1="0%" y1="0%" x2="100%" y2="100%">
                <stop offset="0%" stop-color="#00f2ff"/>
                <stop offset="100%" stop-color="#f472b6"/>
            </linearGradient>
            <filter id="blur" x="-20%" y="-20%" width="140%" height="140%">
                <feGaussianBlur stdDeviation="15"/>
            </filter>
        </defs>
        <rect width="1200" height="720" rx="36" fill="url(#bg)"/>
        <circle cx="960" cy="130" r="180" fill="#00f2ff" fill-opacity="0.08" filter="url(#blur)"/>
        <circle cx="220" cy="600" r="240" fill="#a855f7" fill-opacity="0.12" filter="url(#blur)"/>
        <text x="120" y="130" fill="#00f2ff" font-size="34" font-family="Arial, sans-serif" letter-spacing="3">EDUTRACK STUDY DIAGRAM</text>
        <text x="120" y="185" fill="#ffffff" font-size="48" font-family="Arial, sans-serif" font-weight="700">{safe_title}</text>
        <text x="120" y="228" fill="#cbd5e1" font-size="22" font-family="Arial, sans-serif">Simplified labeled brain map for quick revision</text>
        <rect x="90" y="270" width="1020" height="360" rx="30" fill="#0f172a" fill-opacity="0.86" stroke="#00f2ff" stroke-opacity="0.20"/>
        <ellipse cx="520" cy="450" rx="180" ry="150" fill="#1f2937" stroke="url(#brainGlow)" stroke-width="6"/>
        <path d="M430 360 C380 360, 350 405, 350 450 C350 505, 390 540, 435 550" fill="none" stroke="#00f2ff" stroke-width="5" stroke-linecap="round"/>
        <path d="M610 360 C660 360, 700 405, 700 450 C700 505, 660 540, 615 550" fill="none" stroke="#f472b6" stroke-width="5" stroke-linecap="round"/>
        <path d="M430 430 C470 390, 560 390, 610 430" fill="none" stroke="#38bdf8" stroke-width="5" stroke-linecap="round"/>
        <path d="M430 500 C480 540, 570 540, 615 500" fill="none" stroke="#a855f7" stroke-width="5" stroke-linecap="round"/>
        <circle cx="520" cy="450" r="150" fill="none" stroke="#94a3b8" stroke-opacity="0.25" stroke-width="2" stroke-dasharray="8 12"/>
        <line x1="270" y1="320" x2="390" y2="370" stroke="#00f2ff" stroke-width="3"/>
        <line x1="270" y1="390" x2="400" y2="435" stroke="#38bdf8" stroke-width="3"/>
        <line x1="270" y1="470" x2="410" y2="500" stroke="#f472b6" stroke-width="3"/>
        <line x1="840" y1="320" x2="640" y2="370" stroke="#00f2ff" stroke-width="3"/>
        <line x1="840" y1="395" x2="630" y2="435" stroke="#38bdf8" stroke-width="3"/>
        <line x1="840" y1="470" x2="620" y2="500" stroke="#f472b6" stroke-width="3"/>
        <rect x="130" y="300" width="150" height="220" rx="18" fill="#0b1220" stroke="#00f2ff" stroke-opacity="0.18"/>
        <text x="150" y="335" fill="#e2e8f0" font-size="18" font-family="Arial, sans-serif" font-weight="700">Key Parts</text>
        <text x="150" y="370" fill="#cbd5e1" font-size="16" font-family="Arial, sans-serif">Frontal lobe</text>
        <text x="150" y="405" fill="#cbd5e1" font-size="16" font-family="Arial, sans-serif">Parietal lobe</text>
        <text x="150" y="440" fill="#cbd5e1" font-size="16" font-family="Arial, sans-serif">Temporal lobe</text>
        <text x="150" y="475" fill="#cbd5e1" font-size="16" font-family="Arial, sans-serif">Occipital lobe</text>
        <rect x="850" y="300" width="220" height="220" rx="18" fill="#0b1220" stroke="#00f2ff" stroke-opacity="0.18"/>
        <text x="880" y="335" fill="#e2e8f0" font-size="18" font-family="Arial, sans-serif" font-weight="700">Study Notes</text>
        <text x="880" y="372" fill="#cbd5e1" font-size="16" font-family="Arial, sans-serif">Cerebrum handles thinking</text>
        <text x="880" y="408" fill="#cbd5e1" font-size="16" font-family="Arial, sans-serif">Cerebellum balances movement</text>
        <text x="880" y="444" fill="#cbd5e1" font-size="16" font-family="Arial, sans-serif">Brain stem controls basics</text>
        <text x="880" y="480" fill="#cbd5e1" font-size="16" font-family="Arial, sans-serif">Use this map to revise fast</text>
    </svg>
    """.strip()
    encoded = base64.b64encode(svg.encode('utf-8')).decode('ascii')
    return f"IMAGE_LINK:[data:image/svg+xml;base64,{encoded}]({safe_title})"

def generate_assistant_reply(system_prompt, user_prompt, attachments=None):
    api_key = current_app.config.get('OPENAI_API_KEY', '').strip()
    model_name = current_app.config.get('OPENAI_MODEL', 'gpt-5.4-mini')
    image_attachments = [item for item in (attachments or []) if item.get('kind') == 'image' and item.get('data_url')]

    if OpenAI is not None and api_key:
        try:
            client = OpenAI(api_key=api_key)
            if image_attachments:
                content = [{'type': 'input_text', 'text': user_prompt}]
                for item in image_attachments:
                    content.append({'type': 'input_image', 'image_url': item['data_url']})
                response = client.responses.create(
                    model=model_name,
                    instructions=system_prompt,
                    input=[{'role': 'user', 'content': content}],
                )
            else:
                response = client.responses.create(
                    model=model_name,
                    instructions=system_prompt,
                    input=user_prompt,
                )
            text = getattr(response, 'output_text', '') or ''
            if text.strip():
                return text.strip()
        except Exception as exc:
            print(f"OpenAI response error: {exc}")

    if current_app.config.get('OLLAMA_HOST'):
        last_error = None
        for ollama_model in _ollama_model_candidates():
            try:
                response_text = _call_ollama_chat(
                    model_name=ollama_model,
                    system_prompt=system_prompt,
                    user_prompt=user_prompt,
                    image_attachments=image_attachments,
                )
                if response_text.strip():
                    return response_text.strip()
            except urllib_error.HTTPError as exc:
                last_error = exc
                print(f"Ollama HTTP error for {ollama_model}: {exc}")
            except urllib_error.URLError as exc:
                last_error = exc
                print(f"Ollama connection error for {ollama_model}: {exc}")
            except Exception as exc:
                last_error = exc
                print(f"Ollama error for {ollama_model}: {exc}")
        if last_error:
            print(f"Ollama fallback exhausted: {last_error}")

    return ""

def get_youtube_videos(query):
    """Returns richer study video recommendations with structured metadata."""
    title = _safe_text(query, "Study Topic")[:70]

    if VideosSearch is None:
        return "\n".join(_build_video_fallback_cards(query))

    results_map = {}
    search_queries = _build_video_search_queries(query)

    try:
        for search_query in search_queries:
            results = VideosSearch(search_query, limit=5).result()
            for video in results.get('result', []):
                link = _safe_text(video.get('link'))
                if not link or link in results_map:
                    continue
                results_map[link] = {
                    'url': link,
                    'title': _safe_text(video.get('title') or title),
                    'channel': _extract_channel_name(video),
                    'duration': _safe_text(video.get('duration') or ''),
                    'thumbnail': _extract_thumbnail_url(video),
                    'snippet': _extract_snippet(video),
                    'source': _safe_text(search_query),
                }
                if len(results_map) >= 5:
                    break
            if len(results_map) >= 5:
                break

        if results_map:
            return "\n".join(_format_video_card(video) for video in results_map.values())
    except Exception as e:
        print(f"YT Search Error: {e}")

    return "\n".join(_build_video_fallback_cards(query))

def build_study_image(query):
    """Builds a topic-aware study visual, using OpenAI first and SVG fallback."""
    generated = _generate_openai_study_image(query)
    if generated:
        return generated

    title = _safe_text(query, "Study Topic")
    safe_title = title[:70].replace('(', '[').replace(')', ']')
    clean_title = html.escape(safe_title)
    lower_title = title.lower()

    if 'brain' in lower_title or any(word in lower_title for word in ['neuro', 'cerebrum', 'nervous system', 'human anatomy']):
        return _build_brain_svg(title)

    if any(word in lower_title for word in ['neural network', 'ai', 'machine learning', 'deep learning']):
        nodes_left = [(180, 180), (180, 290), (180, 400)]
        nodes_mid = [(420, 140), (420, 250), (420, 360), (420, 470)]
        nodes_right = [(660, 210), (660, 340), (660, 470)]
        edge_lines = []
        for x1, y1 in nodes_left:
            for x2, y2 in nodes_mid:
                edge_lines.append(f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="#00f2ff" stroke-opacity="0.34" stroke-width="2"/>')
        for x1, y1 in nodes_mid:
            for x2, y2 in nodes_right:
                edge_lines.append(f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="#7000ff" stroke-opacity="0.36" stroke-width="2"/>')

        left_nodes = "".join(
            f'<circle cx="{x}" cy="{y}" r="18" fill="#0f172a" stroke="#00f2ff" stroke-width="4"/>'
            for x, y in nodes_left
        )
        mid_nodes = "".join(
            f'<circle cx="{x}" cy="{y}" r="22" fill="#0f172a" stroke="#38bdf8" stroke-width="4"/>'
            for x, y in nodes_mid
        )
        right_nodes = "".join(
            f'<circle cx="{x}" cy="{y}" r="24" fill="#0f172a" stroke="#a855f7" stroke-width="4"/>'
            for x, y in nodes_right
        )

        svg = f"""
        <svg xmlns="http://www.w3.org/2000/svg" width="1200" height="720" viewBox="0 0 1200 720">
            <defs>
                <linearGradient id="bg" x1="0%" y1="0%" x2="100%" y2="100%">
                    <stop offset="0%" stop-color="#020617"/>
                    <stop offset="55%" stop-color="#0f172a"/>
                    <stop offset="100%" stop-color="#1d4ed8"/>
                </linearGradient>
                <linearGradient id="glow" x1="0%" y1="0%" x2="100%" y2="100%">
                    <stop offset="0%" stop-color="#00f2ff"/>
                    <stop offset="100%" stop-color="#7000ff"/>
                </linearGradient>
                <filter id="blur" x="-20%" y="-20%" width="140%" height="140%">
                    <feGaussianBlur stdDeviation="18"/>
                </filter>
            </defs>
            <rect width="1200" height="720" rx="36" fill="url(#bg)"/>
            <circle cx="980" cy="130" r="180" fill="#00f2ff" fill-opacity="0.10" filter="url(#blur)"/>
            <circle cx="180" cy="590" r="220" fill="#7000ff" fill-opacity="0.10" filter="url(#blur)"/>
            <rect x="90" y="90" width="1020" height="540" rx="28" fill="#0f172a" fill-opacity="0.82" stroke="#00f2ff" stroke-opacity="0.26" stroke-width="2"/>
            <text x="130" y="160" fill="#00f2ff" font-size="32" font-family="Arial, sans-serif" letter-spacing="3">EDUTRACK AI VISUAL</text>
            <text x="130" y="210" fill="#ffffff" font-size="48" font-family="Arial, sans-serif" font-weight="700">{clean_title}</text>
            <text x="130" y="252" fill="#cbd5e1" font-size="22" font-family="Arial, sans-serif">Layered network diagram with input, hidden, and output nodes</text>
            {' '.join(edge_lines)}
            {left_nodes}
            {mid_nodes}
            {right_nodes}
            <rect x="820" y="360" width="220" height="110" rx="18" fill="#00f2ff" fill-opacity="0.10" stroke="#00f2ff" stroke-opacity="0.18"/>
            <text x="850" y="402" fill="#e2e8f0" font-size="20" font-family="Arial, sans-serif">Input</text>
            <text x="850" y="432" fill="#e2e8f0" font-size="20" font-family="Arial, sans-serif">Hidden</text>
            <text x="850" y="462" fill="#e2e8f0" font-size="20" font-family="Arial, sans-serif">Output</text>
            <circle cx="965" cy="414" r="36" fill="url(#glow)"/>
            <circle cx="965" cy="414" r="18" fill="#020617"/>
        </svg>
        """.strip()
    else:
        svg = f"""
        <svg xmlns="http://www.w3.org/2000/svg" width="1200" height="720" viewBox="0 0 1200 720">
            <defs>
                <linearGradient id="bg" x1="0%" y1="0%" x2="100%" y2="100%">
                    <stop offset="0%" stop-color="#020617"/>
                    <stop offset="55%" stop-color="#0f172a"/>
                    <stop offset="100%" stop-color="#1d4ed8"/>
                </linearGradient>
                <linearGradient id="glow" x1="0%" y1="0%" x2="100%" y2="100%">
                    <stop offset="0%" stop-color="#00f2ff"/>
                    <stop offset="100%" stop-color="#7000ff"/>
                </linearGradient>
                <filter id="blur" x="-20%" y="-20%" width="140%" height="140%">
                    <feGaussianBlur stdDeviation="18"/>
                </filter>
            </defs>
            <rect width="1200" height="720" rx="36" fill="url(#bg)"/>
            <circle cx="980" cy="130" r="180" fill="#00f2ff" fill-opacity="0.10" filter="url(#blur)"/>
            <circle cx="180" cy="590" r="220" fill="#7000ff" fill-opacity="0.10" filter="url(#blur)"/>
            <rect x="90" y="90" width="1020" height="540" rx="28" fill="#0f172a" fill-opacity="0.82" stroke="#00f2ff" stroke-opacity="0.26" stroke-width="2"/>
            <text x="130" y="160" fill="#00f2ff" font-size="32" font-family="Arial, sans-serif" letter-spacing="3">EDUTRACK AI VISUAL</text>
            <text x="130" y="210" fill="#ffffff" font-size="48" font-family="Arial, sans-serif" font-weight="700">{clean_title}</text>
            <text x="130" y="252" fill="#cbd5e1" font-size="22" font-family="Arial, sans-serif">Generated study visual for quick revision</text>
            <rect x="130" y="320" width="360" height="180" rx="24" fill="#0b1220" stroke="#00f2ff" stroke-opacity="0.20"/>
            <circle cx="210" cy="390" r="34" fill="#00f2ff" fill-opacity="0.9"/>
            <circle cx="290" cy="355" r="26" fill="#38bdf8" fill-opacity="0.95"/>
            <circle cx="370" cy="402" r="28" fill="#a855f7" fill-opacity="0.9"/>
            <line x1="210" y1="390" x2="290" y2="355" stroke="#00f2ff" stroke-width="4"/>
            <line x1="290" y1="355" x2="370" y2="402" stroke="#a855f7" stroke-width="4"/>
            <line x1="210" y1="390" x2="370" y2="402" stroke="#38bdf8" stroke-width="3" stroke-opacity="0.7"/>
            <rect x="560" y="320" width="420" height="180" rx="24" fill="#0b1220" stroke="#00f2ff" stroke-opacity="0.20"/>
            <path d="M600 430 C650 350, 720 350, 770 430 S890 510, 940 380" fill="none" stroke="url(#glow)" stroke-width="8" stroke-linecap="round"/>
            <circle cx="600" cy="430" r="16" fill="#00f2ff"/>
            <circle cx="720" cy="365" r="16" fill="#38bdf8"/>
            <circle cx="840" cy="465" r="16" fill="#a855f7"/>
            <circle cx="940" cy="380" r="16" fill="#00f2ff"/>
            <circle cx="965" cy="414" r="36" fill="url(#glow)"/>
            <circle cx="965" cy="414" r="18" fill="#020617"/>
        </svg>
        """.strip()

    encoded = base64.b64encode(svg.encode("utf-8")).decode("ascii")
    return f"IMAGE_LINK:[data:image/svg+xml;base64,{encoded}]({safe_title})"

def get_today_schedule(user_id):
    day_name = datetime.now().strftime('%A')
    conn = get_db_connection()
    if not conn: return "Schedule database currently offline."
    try:
        query = "SELECT * FROM timetable WHERE user_id = ? AND day = ?"
        classes = conn.execute(query, (user_id, day_name)).fetchall()
        if not classes: return f"No classes scheduled for today ({day_name})."
        items = []
        for c in classes:
            start_time = c['start_time'] if c['start_time'] else 'TBD'
            end_time = c['end_time'] if c['end_time'] else ''
            time_label = f"{start_time}-{end_time}" if end_time else start_time
            items.append(f"{c['subject']} at {time_label}")
        return f"Arun's Schedule for {day_name}: " + ", ".join(items)
    except:
        return "Schedule unavailable."
    finally:
        conn.close()

def get_vault_context(user_id):
    conn = get_db_connection()
    if not conn: return "Vault connection offline."
    try:
        docs = conn.execute("SELECT doc_type FROM student_docs WHERE user_id = ?", (user_id,)).fetchall()
        conn.close()
        return "Vault Files: " + ", ".join([d['doc_type'] for d in docs]) if docs else "No files in vault."
    except:
        return "Vault storage empty."

# --- 3. Dashboard & Vault Routes ---
@ai.route('/assistant')
@student_required
def chat_page():
    return render_template('ai_chat.html')

@ai.route('/vault')
@student_required
def vault_page():
    conn = get_db_connection()
    docs = []
    if conn:
        try:
            docs = conn.execute("SELECT * FROM student_docs WHERE user_id = ? ORDER BY id DESC", (current_user.id,)).fetchall()
        except:
            docs = []
        finally:
            conn.close()
    return render_template('vault.html', documents=docs)

@ai.route('/upload_doc', methods=['POST'])
@student_required
def upload_doc():
    if 'certificate' not in request.files:
        return redirect(url_for('ai.vault_page'))
    file = request.files['certificate']
    doc_type = request.form.get('doc_type', 'Other Certificate')
    if file and file.filename != '':
        filename = secure_filename(f"u{current_user.id}_{datetime.now().strftime('%H%M%S')}_{file.filename}")
        vault_folder = current_app.config.get('VAULT_FOLDER', 'uploads')
        file_path = os.path.join(vault_folder, filename)
        os.makedirs(os.path.dirname(file_path), exist_ok=True)
        file.save(file_path)
        conn = get_db_connection()
        if conn:
            conn.execute("INSERT INTO student_docs (user_id, file_name, file_path, doc_type, upload_date) VALUES (?, ?, ?, ?, ?)",
                (current_user.id, filename, file_path, doc_type, datetime.now().strftime('%Y-%m-%d')))
            conn.commit()
            conn.close()
    return redirect(url_for('ai.vault_page'))

@ai.route('/view_file/<int:doc_id>')
@student_required
def view_file(doc_id):
    conn = get_db_connection()
    doc = conn.execute("SELECT * FROM student_docs WHERE id = ? AND user_id = ?", (doc_id, current_user.id)).fetchone()
    conn.close()
    if doc: return send_from_directory(current_app.config.get('VAULT_FOLDER', 'uploads'), doc['file_name'])
    return "File not found", 404

@ai.route('/delete_doc/<int:doc_id>', methods=['POST'])
@student_required
def delete_doc(doc_id):
    conn = get_db_connection()
    doc = conn.execute("SELECT * FROM student_docs WHERE id = ? AND user_id = ?", (doc_id, current_user.id)).fetchone()
    if doc:
        try:
            if os.path.exists(doc['file_path']): os.remove(doc['file_path'])
        except Exception as e: print(f"File delete error: {e}")
        conn.execute("DELETE FROM student_docs WHERE id = ?", (doc_id,))
        conn.commit()
    conn.close()
    return redirect(url_for('ai.vault_page'))

# --- 4. AI Core Logic ---
@ai.route('/ask', methods=['POST'])
@student_required
def ask():
    data = request.get_json(silent=True)
    if not data or 'message' not in data:
        return jsonify({'response': "AI: Awaiting signal..."})

    user_message = data.get('message', '').strip()
    attachments = data.get('attachments', [])
    history = data.get('history', [])
    if isinstance(attachments, str):
        try:
            attachments = json.loads(attachments)
        except Exception:
            attachments = []
    if isinstance(history, str):
        try:
            history = json.loads(history)
        except Exception:
            history = []
    user_msg_lower = user_message.lower()
    
    video_triggers = ['video', 'youtube', 'watch', 'tutorial', 'show me', 'course video', 'vedio', 'learn from video']
    image_triggers = [
        'image', 'diagram', 'draw', 'illustration', 'picture', 'chart', 'photo', 'visual',
        'poster', 'infographic', 'cartoon', 'avatar', 'sketch', 'design'
    ]
    image_phrases = [
        'generate image', 'create image', 'make image',
        'generate a study image', 'create a study image', 'make a study image',
        'generate a poster', 'create a poster', 'make a poster',
        'generate an infographic', 'create an infographic', 'make an infographic',
        'generate a cartoon', 'create a cartoon', 'make a cartoon',
    ]
    is_video_request = any(word in user_msg_lower for word in video_triggers)
    is_image_request = any(word in user_msg_lower for word in image_triggers) or any(phrase in user_msg_lower for phrase in image_phrases)

    sched = get_today_schedule(current_user.id)
    vault = get_vault_context(current_user.id)
    attachment_context, attachment_images = _build_attachment_context(attachments)
    
    yt_context = ""
    if is_video_request:
        yt_context = get_youtube_videos(user_message)

    image_context = ""
    if is_image_request:
        image_context = build_study_image(user_message)

    quick_media_mode = bool(is_image_request and current_app.config.get('FREE_FIRST_MEDIA_MODE', True) and not attachment_images)
    system_prompt = _build_system_prompt()
    history_context = _build_history_context(history)
    user_prompt = _build_user_prompt(
        user_message,
        sched,
        vault,
        yt_context,
        image_context,
        attachment_context,
        history_context,
    )
    final_response = ""
    if not quick_media_mode:
        final_response = generate_assistant_reply(system_prompt, user_prompt, attachments=attachment_images)

    media_blocks = []
    if image_context:
        media_blocks.append(image_context)
    if yt_context:
        media_blocks.append(yt_context)

    if media_blocks:
        combined_media = "\n\n".join(media_blocks)
        if final_response:
            if image_context and 'IMAGE_LINK:[' not in final_response:
                final_response = f"{image_context}\n\n{final_response}"
            if yt_context and 'VIDEO_CARD:' not in final_response and 'VIDEO_LINK:[' not in final_response:
                final_response = f"{final_response}\n\n{yt_context}"
        else:
            final_response = combined_media

    if not final_response:
        final_response = (
            "I've prepared the study diagram and key notes for you."
            if image_context
            else "I've gathered the study materials you requested. How else can I help?"
            if media_blocks
            else "I can analyze screenshots, images, and supported files if you attach them."
            if attachment_context
            else "AI Chat is currently offline. Add OPENAI_API_KEY for the best experience."
        )

    return jsonify({'response': final_response})
