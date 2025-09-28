
import os
import json
import sqlite3
import uuid
import google.generativeai as genai
from flask import Flask, request, render_template, Response, stream_with_context
from flask_cors import CORS
from openai import OpenAI
from dotenv import load_dotenv

# --- Environment and App Setup ---
load_dotenv()
app = Flask(__name__)
CORS(app)

# --- Database Setup ---
# Using a single, unified database
DB_FILE = "/Users/sunbai/galgame_unified.db"

def init_db():
    """Initializes the database and ensures the 'provider' column exists."""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()

    # Step 1: Ensure the table exists.
    # The CREATE statement now includes the 'provider' column for new databases.
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS conversations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL,
            role TEXT NOT NULL,
            content TEXT,
            character_name TEXT,
            expression TEXT,
            action TEXT,
            dialogue TEXT,
            scene_update TEXT,
            provider TEXT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # Step 2: For older databases, check if the 'provider' column needs to be added.
    cursor.execute("PRAGMA table_info(conversations)")
    columns = [column[1] for column in cursor.fetchall()]
    if 'provider' not in columns:
        cursor.execute("ALTER TABLE conversations ADD COLUMN provider TEXT")

    conn.commit()
    conn.close()

def save_message_to_db(session_id, role, content, provider, is_assistant=False):
    """Saves a message to the database, including the provider used."""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    base_insert_sql = '''
        INSERT INTO conversations (session_id, role, content, provider)
        VALUES (?, ?, ?, ?)
    '''
    params = (session_id, role, content, provider)

    if is_assistant:
        try:
            clean_content = content.strip()
            if clean_content.startswith('```json'):
                clean_content = clean_content[7:-3].strip()
            elif clean_content.startswith('json'):
                clean_content = clean_content[4:].strip()
            
            data = json.loads(clean_content)
            
            json_insert_sql = '''
                INSERT INTO conversations (session_id, role, content, character_name, expression, action, dialogue, scene_update, provider)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            '''
            params = (session_id, role, content, data.get('character_name'), data.get('expression'), data.get('action'), data.get('dialogue'), data.get('scene_update'), provider)
            cursor.execute(json_insert_sql, params)
        except (json.JSONDecodeError, TypeError):
            cursor.execute(base_insert_sql, params)
    else:
        cursor.execute(base_insert_sql, params)
        
    conn.commit()
    conn.close()

# --- AI Client Setup ---
# Aliyun (Dashscope) Client
aliyun_client = OpenAI(
    api_key=os.getenv("DASHSCOPE_API_KEY"),
    base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
)

# Gemini Client
try:
    gemini_api_key = os.getenv("GEMINI_API_KEY")
    if not gemini_api_key:
        print("Warning: GEMINI_API_KEY not found.")
        gemini_model = None
    else:
        genai.configure(api_key=gemini_api_key)
        gemini_model = genai.GenerativeModel('gemini-1.5-pro-latest')
except Exception as e:
    print(f"Error configuring Gemini: {e}")
    gemini_model = None

# --- Routes ---
@app.route("/")
def read_root():
    return render_template("index.html")

@app.route("/api/chat", methods=["POST"])
def chat():
    chat_request = request.json
    history = chat_request.get('history', [])
    provider = chat_request.get('provider', 'gemini') # Default to Gemini
    
    session_id = str(uuid.uuid4())
    
    if history and history[-1]['role'] == 'user':
        save_message_to_db(session_id, 'user', history[-1]['content'], provider)

    def stream_generator():
        try:
            if provider == 'aliyun':
                yield from stream_aliyun(history, session_id)
            elif provider == 'gemini':
                yield from stream_gemini(history, session_id)
            else:
                raise ValueError("Invalid provider specified")
        except Exception as e:
            print(f"An error occurred: {e}")
            error_signal = {"type": "error", "content": str(e)}
            yield f"data: {json.dumps(error_signal)}\n\n"

    return Response(stream_with_context(stream_generator()), mimetype="text/event-stream")

def stream_aliyun(history, session_id):
    """Handles the streaming logic for the Aliyun provider."""
    completion = aliyun_client.chat.completions.create(
        model="qwen-plus-latest",
        messages=history,
        stream=True,
        stream_options={"include_usage": True},
        temperature=0.3,
        presence_penalty=0.3,
    )

    is_answering = False
    full_answer = ""
    for chunk in completion:
        if not chunk.choices:
            continue

        delta = chunk.choices[0].delta
        if delta and delta.content:
            if not is_answering:
                start_signal = {"type": "start_answer", "content": ""}
                yield f"data: {json.dumps(start_signal)}\n\n"
                is_answering = True
            
            response_chunk = {"type": "answer", "content": delta.content}
            full_answer += delta.content
            yield f"data: {json.dumps(response_chunk)}\n\n"

    if full_answer:
        save_message_to_db(session_id, 'assistant', full_answer, 'aliyun', is_assistant=True)

    end_signal = {"type": "end", "full_answer": full_answer}
    yield f"data: {json.dumps(end_signal)}\n\n"

def stream_gemini(history, session_id):
    """Handles the streaming logic for the Gemini provider."""
    if not gemini_model:
        raise ConnectionError("Gemini model not initialized. Check API key.")

    gemini_history = [{'role': ('model' if msg['role'] == 'assistant' else 'user'), 'parts': [msg['content']]} for msg in history]
    
    chat_session = gemini_model.start_chat(history=gemini_history[:-1])
    response = chat_session.send_message(gemini_history[-1]['parts'], stream=True)

    full_answer = ""
    is_answering = False
    for chunk in response:
        if not is_answering:
            start_signal = {"type": "start_answer", "content": ""}
            yield f"data: {json.dumps(start_signal)}\n\n"
            is_answering = True
        
        if chunk.text:
            response_chunk = {"type": "answer", "content": chunk.text}
            full_answer += chunk.text
            yield f"data: {json.dumps(response_chunk)}\n\n"

    if full_answer:
        save_message_to_db(session_id, 'assistant', full_answer, 'gemini', is_assistant=True)

    end_signal = {"type": "end", "full_answer": full_answer}
    yield f"data: {json.dumps(end_signal)}\n\n"


if __name__ == "__main__":
    init_db()
    # The unified app runs on a single port, e.g., 8000
    app.run(host="127.0.0.1", port=8000, debug=True)
