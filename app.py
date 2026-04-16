import os
import json
import sqlite3
import re
import traceback
import ast
import operator
import random
from datetime import datetime, timedelta
from flask import Flask, render_template, request, redirect, url_for, session, flash, g, send_from_directory, jsonify, has_request_context
from werkzeug.security import generate_password_hash, check_password_hash
import pandas as pd
from dotenv import load_dotenv
from functools import wraps
import PyPDF2
import spacy
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib import colors
from io import BytesIO
from urllib.parse import urlparse, parse_qs
#change
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(BASE_DIR, '.env'))

GEMINI_OPENAI_BASE_URL = 'https://generativelanguage.googleapis.com/v1beta/openai/'
DEFAULT_GEMINI_MODEL = os.environ.get('GEMINI_MODEL', 'gemini-2.5-flash')
DEFAULT_OPENAI_MODEL = os.environ.get('OPENAI_MODEL', 'gpt-4o-mini')

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'dev_secret_change_me')

# âœ… Login Required Decorator
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not getattr(g, 'current_user', None):
            flash('Please log in to access this feature.', 'warning')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

# âœ… Correct absolute path for DB inside "database" folder
DB_PATH = os.path.join(BASE_DIR, "database", "marg_darshak.db")

# âœ… Auto-create tables if not exist and load data if empty
def init_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    # --- Careers Table ---
    c.execute('''CREATE TABLE IF NOT EXISTS careers (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT,
        category TEXT,
        description TEXT,
        required_skills TEXT,
        avg_salary_inr INTEGER,
        growth_rate TEXT,
        difficulty_level TEXT,
        education_required TEXT,
        top_colleges TEXT,
        job_roles TEXT
    )''')

    # Ensure an older careers table without id is migrated to the proper schema
    columns = [row[1] for row in c.execute('PRAGMA table_info(careers)').fetchall()]
    if 'id' not in columns and 'title' in columns:
        print('Migrating careers table to add id column...')
        c.execute('ALTER TABLE careers RENAME TO careers_old')
        c.execute('''CREATE TABLE careers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT,
            category TEXT,
            description TEXT,
            required_skills TEXT,
            avg_salary_inr INTEGER,
            growth_rate TEXT,
            difficulty_level TEXT,
            education_required TEXT,
            top_colleges TEXT,
            job_roles TEXT
        )''')
        c.execute('''INSERT INTO careers (title, category, description, required_skills, avg_salary_inr,
                         growth_rate, difficulty_level, education_required, top_colleges, job_roles)
                     SELECT title, category, description, required_skills, avg_salary_inr,
                            growth_rate, difficulty_level, education_required, top_colleges, job_roles
                     FROM careers_old''')
        c.execute('DROP TABLE careers_old')
        conn.commit()
        columns = [row[1] for row in c.execute('PRAGMA table_info(careers)').fetchall()]

    # Check if careers table is empty, if so, load data
    c.execute('SELECT COUNT(*) FROM careers')
    if c.fetchone()[0] == 0:
        print("Loading careers data...")
        try:
            careers_df = pd.read_csv(os.path.join(BASE_DIR, 'data', 'careers.csv'))
            careers_df.to_sql('careers', conn, if_exists='append', index=False)
            print(f"âœ… Loaded {len(careers_df)} careers")
        except Exception as e:
            print(f"Error loading careers data: {e}")

    # --- Gyan Kosh Table ---
    c.execute('''CREATE TABLE IF NOT EXISTS gyan_kosh (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        source TEXT,
        chapter INTEGER,
        verse_number INTEGER,
        sanskrit_text TEXT,
        hindi_meaning TEXT,
        english_meaning TEXT,
        practical_application TEXT,
        tags TEXT,
        audio_url TEXT
    )''')

    # Check if gyan_kosh table is empty
    c.execute('SELECT COUNT(*) FROM gyan_kosh')
    if c.fetchone()[0] == 0:
        print("Loading gyan kosh data...")
        try:
            import csv
            rows = []
            with open(os.path.join(BASE_DIR, 'data', 'shlokas.csv'), 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    rows.append([row['source'], row['chapter'], row['verse_number'], row['sanskrit_text'], row['hindi_meaning'], row['english_meaning'], row['practical_application'], row['tags'], row['audio_url']])
            gyan_df = pd.DataFrame(rows, columns=['source', 'chapter', 'verse_number', 'sanskrit_text', 'hindi_meaning', 'english_meaning', 'practical_application', 'tags', 'audio_url'])
            gyan_df.to_sql('gyan_kosh', conn, if_exists='replace', index=False)
            print(f"âœ… Loaded {len(gyan_df)} gyan kosh entries")
        except Exception as e:
            print(f"Error loading gyan kosh data: {e}")

    # --- Learning Resources Table ---
    c.execute('''CREATE TABLE IF NOT EXISTS learning_resources (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        topic TEXT,
        title TEXT,
        platform TEXT,
        resource_type TEXT,
        url TEXT,
        difficulty TEXT,
        duration_hours INTEGER,
        quality_score REAL,
        language TEXT,
        is_free INTEGER
    )''')

    # Check if learning_resources table exists and matches CSV schema
    resources_csv_path = os.path.join(BASE_DIR, 'data', 'resources.csv')
    load_resources = False
    try:
        c.execute('SELECT COUNT(*) FROM learning_resources')
        row_count = c.fetchone()[0]
        if row_count == 0:
            load_resources = True
        else:
            existing_cols = [col[1] for col in c.execute('PRAGMA table_info(learning_resources)').fetchall()]
            expected_cols = ['id', 'topic', 'title', 'platform', 'resource_type', 'url', 'difficulty', 'duration_hours', 'quality_score', 'language', 'is_free']
            if set(existing_cols) != set(expected_cols):
                load_resources = True
    except Exception:
        load_resources = True

    if load_resources:
        print("Loading learning resources data...")
        try:
            resources_df = pd.read_csv(resources_csv_path)
            if 'is_free' in resources_df.columns:
                resources_df['is_free'] = resources_df['is_free'].astype(str).str.upper().map({'TRUE': 1, 'FALSE': 0}).fillna(0).astype(int)
            if 'duration_hours' in resources_df.columns:
                resources_df['duration_hours'] = pd.to_numeric(resources_df['duration_hours'], errors='coerce').fillna(0).astype(int)
            resources_df.to_sql('learning_resources', conn, if_exists='replace', index=False)
            print(f"âœ… Loaded {len(resources_df)} learning resources")
        except Exception as e:
            print(f"Error loading learning resources data: {e}")

    # --- Mood Entries Table ---
    c.execute('''CREATE TABLE IF NOT EXISTS mood_entries (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        date TEXT,
        mood TEXT,
        notes TEXT,
        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
    )''')
    # ensure user_id column exists for per-user mood entries
    try:
        c.execute('ALTER TABLE mood_entries ADD COLUMN user_id INTEGER')
    except Exception:
        pass

    # --- User Activity Table ---
    c.execute('''CREATE TABLE IF NOT EXISTS user_activity (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        activity_type TEXT,
        module TEXT,
        description TEXT,
        metadata TEXT,
        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
    )''')
    # ensure user_id column exists for per-user activity logging
    try:
        c.execute('ALTER TABLE user_activity ADD COLUMN user_id INTEGER')
    except Exception:
        pass

    # --- Daily Aptitude Quiz Cache ---
    c.execute('''CREATE TABLE IF NOT EXISTS daily_aptitude_quizzes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        quiz_date TEXT NOT NULL,
        topic TEXT NOT NULL,
        mode TEXT NOT NULL DEFAULT 'daily',
        questions_json TEXT NOT NULL,
        source TEXT NOT NULL DEFAULT 'gemini',
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        UNIQUE (user_id, quiz_date, topic, mode),
        FOREIGN KEY (user_id) REFERENCES users (id)
    )''')
    c.execute('CREATE INDEX IF NOT EXISTS idx_daily_quiz_lookup ON daily_aptitude_quizzes (user_id, quiz_date, topic, mode)')

    # --- Student GD Connect Tables ---
    c.execute('''CREATE TABLE IF NOT EXISTS gd_queue (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        name TEXT NOT NULL,
        field TEXT,
        target_role TEXT,
        status TEXT NOT NULL DEFAULT 'waiting',
        session_id INTEGER,
        room_id TEXT,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        matched_at DATETIME,
        FOREIGN KEY (user_id) REFERENCES users (id)
    )''')
    c.execute('CREATE INDEX IF NOT EXISTS idx_gd_queue_status ON gd_queue (status, created_at)')
    c.execute('CREATE INDEX IF NOT EXISTS idx_gd_queue_user_status ON gd_queue (user_id, status)')

    c.execute('''CREATE TABLE IF NOT EXISTS gd_sessions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        topic TEXT NOT NULL,
        room_id TEXT NOT NULL UNIQUE,
        status TEXT NOT NULL DEFAULT 'active',
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        thinking_end_at DATETIME,
        discussion_end_at DATETIME,
        feedback_deadline_at DATETIME,
        completed_at DATETIME
    )''')
    c.execute('CREATE INDEX IF NOT EXISTS idx_gd_sessions_room ON gd_sessions (room_id)')
    # Add host-managed meeting columns if missing
    gd_session_columns = [row[1] for row in c.execute('PRAGMA table_info(gd_sessions)').fetchall()]
    if 'host_user_id' not in gd_session_columns:
        c.execute('ALTER TABLE gd_sessions ADD COLUMN host_user_id INTEGER')
    if 'max_participants' not in gd_session_columns:
        c.execute('ALTER TABLE gd_sessions ADD COLUMN max_participants INTEGER DEFAULT 5')
    if 'duration_minutes' not in gd_session_columns:
        c.execute('ALTER TABLE gd_sessions ADD COLUMN duration_minutes INTEGER DEFAULT 10')
    if 'started_at' not in gd_session_columns:
        c.execute('ALTER TABLE gd_sessions ADD COLUMN started_at DATETIME')
    if 'ended_at' not in gd_session_columns:
        c.execute('ALTER TABLE gd_sessions ADD COLUMN ended_at DATETIME')
    if 'timer_started_by' not in gd_session_columns:
        c.execute('ALTER TABLE gd_sessions ADD COLUMN timer_started_by INTEGER')

    c.execute('''CREATE TABLE IF NOT EXISTS gd_participants (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        session_id INTEGER NOT NULL,
        user_id INTEGER NOT NULL,
        name TEXT NOT NULL,
        field TEXT,
        target_role TEXT,
        joined_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        UNIQUE (session_id, user_id),
        FOREIGN KEY (session_id) REFERENCES gd_sessions (id),
        FOREIGN KEY (user_id) REFERENCES users (id)
    )''')
    c.execute('CREATE INDEX IF NOT EXISTS idx_gd_participants_session ON gd_participants (session_id)')
    gd_participant_columns = [row[1] for row in c.execute('PRAGMA table_info(gd_participants)').fetchall()]
    if 'status' not in gd_participant_columns:
        c.execute("ALTER TABLE gd_participants ADD COLUMN status TEXT DEFAULT 'accepted'")
    if 'role' not in gd_participant_columns:
        c.execute("ALTER TABLE gd_participants ADD COLUMN role TEXT DEFAULT 'participant'")

    c.execute('''CREATE TABLE IF NOT EXISTS gd_messages (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        session_id INTEGER NOT NULL,
        user_id INTEGER NOT NULL,
        message TEXT NOT NULL,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (session_id) REFERENCES gd_sessions (id),
        FOREIGN KEY (user_id) REFERENCES users (id)
    )''')
    c.execute('CREATE INDEX IF NOT EXISTS idx_gd_messages_session ON gd_messages (session_id, id)')

    c.execute('''CREATE TABLE IF NOT EXISTS gd_responses (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        session_id INTEGER NOT NULL,
        user_id INTEGER NOT NULL,
        response TEXT,
        experience TEXT,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        UNIQUE (session_id, user_id),
        FOREIGN KEY (session_id) REFERENCES gd_sessions (id),
        FOREIGN KEY (user_id) REFERENCES users (id)
    )''')

    c.execute('''CREATE TABLE IF NOT EXISTS gd_peer_feedback (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        session_id INTEGER NOT NULL,
        from_user INTEGER NOT NULL,
        to_user INTEGER NOT NULL,
        pros TEXT,
        cons TEXT,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        UNIQUE (session_id, from_user, to_user),
        FOREIGN KEY (session_id) REFERENCES gd_sessions (id),
        FOREIGN KEY (from_user) REFERENCES users (id),
        FOREIGN KEY (to_user) REFERENCES users (id)
    )''')
    c.execute('CREATE INDEX IF NOT EXISTS idx_gd_peer_feedback_target ON gd_peer_feedback (session_id, to_user)')

    c.execute('''CREATE TABLE IF NOT EXISTS gd_ai_evaluations (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        session_id INTEGER NOT NULL,
        user_id INTEGER NOT NULL,
        evaluation_json TEXT NOT NULL,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        UNIQUE (session_id, user_id),
        FOREIGN KEY (session_id) REFERENCES gd_sessions (id),
        FOREIGN KEY (user_id) REFERENCES users (id)
    )''')

    c.execute('''CREATE TABLE IF NOT EXISTS gd_invites (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        session_id INTEGER NOT NULL,
        from_user INTEGER NOT NULL,
        to_user INTEGER NOT NULL,
        status TEXT NOT NULL DEFAULT 'pending' CHECK(status IN ('pending', 'accepted', 'rejected', 'cancelled')),
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        UNIQUE (session_id, to_user),
        FOREIGN KEY (session_id) REFERENCES gd_sessions (id),
        FOREIGN KEY (from_user) REFERENCES users (id),
        FOREIGN KEY (to_user) REFERENCES users (id)
    )''')
    c.execute('CREATE INDEX IF NOT EXISTS idx_gd_invites_user_status ON gd_invites (to_user, status, created_at)')

    c.execute('''CREATE TABLE IF NOT EXISTS gd_join_requests (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        session_id INTEGER NOT NULL,
        requester_user_id INTEGER NOT NULL,
        requester_name TEXT NOT NULL,
        field TEXT,
        target_role TEXT,
        status TEXT NOT NULL DEFAULT 'pending' CHECK(status IN ('pending', 'approved', 'rejected', 'cancelled')),
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        UNIQUE (session_id, requester_user_id),
        FOREIGN KEY (session_id) REFERENCES gd_sessions (id),
        FOREIGN KEY (requester_user_id) REFERENCES users (id)
    )''')
    c.execute('CREATE INDEX IF NOT EXISTS idx_gd_join_requests_host ON gd_join_requests (session_id, status, created_at)')
    c.execute('CREATE INDEX IF NOT EXISTS idx_gd_join_requests_user ON gd_join_requests (requester_user_id, status, created_at)')

    c.execute('''CREATE TABLE IF NOT EXISTS gd_stop_requests (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        session_id INTEGER NOT NULL,
        requested_by INTEGER NOT NULL,
        status TEXT NOT NULL DEFAULT 'pending' CHECK(status IN ('pending', 'approved', 'rejected', 'cancelled')),
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        resolved_at DATETIME,
        FOREIGN KEY (session_id) REFERENCES gd_sessions (id),
        FOREIGN KEY (requested_by) REFERENCES users (id)
    )''')
    c.execute('CREATE INDEX IF NOT EXISTS idx_gd_stop_requests_session ON gd_stop_requests (session_id, status, created_at)')

    c.execute('''CREATE TABLE IF NOT EXISTS gd_stop_votes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        stop_request_id INTEGER NOT NULL,
        user_id INTEGER NOT NULL,
        vote TEXT NOT NULL CHECK(vote IN ('approve', 'reject')),
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        UNIQUE (stop_request_id, user_id),
        FOREIGN KEY (stop_request_id) REFERENCES gd_stop_requests (id),
        FOREIGN KEY (user_id) REFERENCES users (id)
    )''')
    c.execute('CREATE INDEX IF NOT EXISTS idx_gd_stop_votes_request ON gd_stop_votes (stop_request_id, vote)')

    c.execute('''CREATE TABLE IF NOT EXISTS gd_webrtc_signals (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        session_id INTEGER NOT NULL,
        from_user INTEGER NOT NULL,
        to_user INTEGER,
        signal_type TEXT NOT NULL,
        signal_payload TEXT NOT NULL,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (session_id) REFERENCES gd_sessions (id),
        FOREIGN KEY (from_user) REFERENCES users (id),
        FOREIGN KEY (to_user) REFERENCES users (id)
    )''')
    c.execute('CREATE INDEX IF NOT EXISTS idx_gd_signals_poll ON gd_webrtc_signals (session_id, id)')

    # --- Users Table ---
    c.execute('''CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT,
        email TEXT UNIQUE,
        password_hash TEXT,
        is_premium BOOLEAN DEFAULT 0,
        mentor_access BOOLEAN DEFAULT 0,
        premium_expiry DATETIME,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    )''')

    # --- Student Community Chat Tables ---
    c.execute('''CREATE TABLE IF NOT EXISTS student_connections (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        requester_id INTEGER NOT NULL,
        addressee_id INTEGER NOT NULL,
        status TEXT NOT NULL DEFAULT 'pending' CHECK(status IN ('pending', 'accepted', 'rejected')),
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (requester_id) REFERENCES users (id),
        FOREIGN KEY (addressee_id) REFERENCES users (id),
        UNIQUE (requester_id, addressee_id),
        CHECK (requester_id != addressee_id)
    )''')

    c.execute('''CREATE TABLE IF NOT EXISTS student_messages (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        connection_id INTEGER NOT NULL,
        sender_id INTEGER NOT NULL,
        receiver_id INTEGER NOT NULL,
        message TEXT NOT NULL,
        is_read INTEGER DEFAULT 0,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (connection_id) REFERENCES student_connections (id),
        FOREIGN KEY (sender_id) REFERENCES users (id),
        FOREIGN KEY (receiver_id) REFERENCES users (id)
    )''')
    c.execute('CREATE INDEX IF NOT EXISTS idx_student_connections_users ON student_connections (requester_id, addressee_id, status)')
    c.execute('CREATE INDEX IF NOT EXISTS idx_student_messages_connection ON student_messages (connection_id, created_at)')

    # --- Mentor Requests Table ---
    c.execute('''CREATE TABLE IF NOT EXISTS mentor_requests (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        utr TEXT,
        status TEXT DEFAULT 'pending' CHECK(status IN ('pending', 'approved', 'rejected')),
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (user_id) REFERENCES users (id)
    )''')

    # --- User Essentials Table ---
    c.execute('''CREATE TABLE IF NOT EXISTS user_essentials (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        name TEXT,
        category TEXT,
        price REAL,
        link TEXT,
        description TEXT,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (user_id) REFERENCES users (id)
    )''')

    # --- Todo Tasks Table ---
    c.execute('''CREATE TABLE IF NOT EXISTS todo_tasks (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        title TEXT NOT NULL,
        description TEXT,
        priority TEXT DEFAULT 'Medium' CHECK(priority IN ('Low', 'Medium', 'High')),
        status TEXT DEFAULT 'Pending' CHECK(status IN ('Pending', 'Completed')),
        deadline DATE,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        completed_at DATETIME,
        FOREIGN KEY (user_id) REFERENCES users (id)
    )''')

    # --- Internship Community Tables ---
    c.execute('''CREATE TABLE IF NOT EXISTS internships (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        company TEXT NOT NULL,
        role TEXT NOT NULL,
        city TEXT,
        mode TEXT,
        stipend TEXT NOT NULL DEFAULT 'Not Disclosed',
        apply_link TEXT,
        source TEXT NOT NULL DEFAULT 'student',
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        UNIQUE (company, role, city, mode)
    )''')

    c.execute('''CREATE TABLE IF NOT EXISTS internship_experiences (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        internship_id INTEGER,
        name TEXT,
        college TEXT NOT NULL,
        internship_company TEXT NOT NULL,
        city TEXT,
        mode TEXT,
        role TEXT NOT NULL,
        how_got TEXT NOT NULL,
        tips TEXT NOT NULL,
        interview_questions TEXT,
        apply_link TEXT,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (internship_id) REFERENCES internships (id)
    )''')

    # âœ… Add apply_link column if it doesn't exist
    columns = [row[1] for row in c.execute('PRAGMA table_info(internship_experiences)').fetchall()]
    if 'apply_link' not in columns:
        print("Adding apply_link column to internship_experiences...")
        c.execute('ALTER TABLE internship_experiences ADD COLUMN apply_link TEXT')
    if 'user_id' not in columns:
        print("Adding user_id column to internship_experiences...")
        c.execute('ALTER TABLE internship_experiences ADD COLUMN user_id INTEGER')

    internship_columns = [row[1] for row in c.execute('PRAGMA table_info(internships)').fetchall()]
    if 'apply_link' not in internship_columns:
        print("Adding apply_link column to internships...")
        c.execute('ALTER TABLE internships ADD COLUMN apply_link TEXT')

    # Backfill apply links for existing internships from shared experiences.
    c.execute(
        '''UPDATE internships
           SET apply_link = (
               SELECT ie.apply_link
               FROM internship_experiences ie
               WHERE ie.internship_id = internships.id
                 AND ie.apply_link IS NOT NULL
                 AND trim(ie.apply_link) != ''
               ORDER BY ie.created_at DESC, ie.id DESC
               LIMIT 1
           )
           WHERE (apply_link IS NULL OR trim(apply_link) = '')'''
    )

    conn.commit()
    conn.close()

# âœ… Run table creation before app starts
init_db()


# âœ… Connection helper
def get_db_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


# ----------------- Authentication helpers -----------------
def create_user(username, email, password):
    try:
        conn = get_db_connection()
        pw_hash = generate_password_hash(password)
        conn.execute('INSERT INTO users (username, email, password_hash) VALUES (?, ?, ?)',
                     (username, email, pw_hash))
        conn.commit()
        conn.close()
        return True
    except sqlite3.IntegrityError:
        return False
    except Exception as e:
        print(f"Create user error: {e}")
        return False


def authenticate_user(email, password):
    try:
        conn = get_db_connection()
        user = conn.execute('SELECT * FROM users WHERE email = ?', (email,)).fetchone()
        conn.close()
        if user and check_password_hash(user['password_hash'], password):
            return dict(user)
        return None
    except Exception as e:
        print(f"Auth error: {e}")
        return None


@app.before_request
def load_current_user():
    user_id = session.get('user_id')
    if user_id:
        try:
            conn = get_db_connection()
            user = conn.execute('SELECT id, username, email FROM users WHERE id = ?', (user_id,)).fetchone()
            conn.close()
            if user:
                # make available in templates
                from flask import g
                g.current_user = dict(user)
            else:
                session.pop('user_id', None)
        except Exception:
            session.pop('user_id', None)


# âœ… Activity logging helper
def log_activity(activity_type, module, description, metadata=None):
    """Log user activity for progress tracking"""
    try:
        conn = get_db_connection()
        user_id = None
        try:
            user_id = g.current_user.get('id') if getattr(g, 'current_user', None) else None
        except Exception:
            user_id = None

        conn.execute('INSERT INTO user_activity (activity_type, module, description, metadata, user_id) VALUES (?, ?, ?, ?, ?)',
                    (activity_type, module, description, metadata or '', user_id))
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"Activity logging error: {e}")


def _is_ai_provider_configured(provider):
    if provider == 'gemini':
        return bool(os.environ.get('GEMINI_API_KEY'))
    if provider == 'openai':
        return bool(os.environ.get('OPENAI_API_KEY'))
    return False


def get_configured_ai_providers():
    return [provider for provider in ('gemini', 'openai') if _is_ai_provider_configured(provider)]


def get_ai_provider(preferred=None):
    if preferred in ('gemini', 'openai') and _is_ai_provider_configured(preferred):
        return preferred

    configured = get_configured_ai_providers()
    if configured:
        return configured[0]

    return preferred if preferred in ('gemini', 'openai') else 'gemini'


def get_ai_provider_label(provider=None):
    provider = provider or get_ai_provider()
    return 'Gemini' if provider == 'gemini' else 'OpenAI'


def get_ai_model(provider=None):
    provider = provider or get_ai_provider()
    if provider == 'openai':
        return DEFAULT_OPENAI_MODEL
    return DEFAULT_GEMINI_MODEL


def get_openai_client(provider=None):
    from openai import OpenAI
    provider = provider if provider in ('gemini', 'openai') else get_ai_provider()
    gemini_api_key = os.environ.get('GEMINI_API_KEY')
    if provider == 'gemini':
        if not gemini_api_key:
            raise ValueError('GEMINI_API_KEY is not configured.')
        return OpenAI(
            api_key=gemini_api_key,
            base_url=GEMINI_OPENAI_BASE_URL
        )

    openai_api_key = os.environ.get('OPENAI_API_KEY')
    if provider == 'openai':
        if not openai_api_key:
            raise ValueError('OPENAI_API_KEY is not configured.')
        return OpenAI(api_key=openai_api_key)

    raise ValueError('No AI API key is configured. Set GEMINI_API_KEY (preferred) or OPENAI_API_KEY.')

def describe_openai_resume_error(error):
    """Convert provider SDK errors into short user-safe messages."""
    status_code = getattr(error, 'status_code', None)
    error_code = None
    response_body = getattr(error, 'body', None)
    error_message = str(error or '').lower()
    if isinstance(response_body, dict):
        error_code = response_body.get('error', {}).get('code')

    if isinstance(error, json.JSONDecodeError) or 'incomplete json' in error_message or 'malformed json' in error_message:
        return 'Real-time AI analysis is temporarily unavailable because the AI provider returned an incomplete structured response.'
    if error_code == 'insufficient_quota' or status_code == 429:
        return 'Real-time AI analysis is temporarily unavailable because the API quota or billing limit has been reached.'
    if status_code == 401:
        return 'Real-time AI analysis failed because the configured API key is invalid or unauthorized.'
    if status_code == 403:
        return 'Real-time AI analysis failed because this API key does not have access to the requested model or project.'
    if status_code in (408, 502, 503, 504):
        return 'Real-time AI analysis is temporarily unavailable due to an upstream service or network issue.'
    if error_code:
        return f'Real-time AI analysis failed ({error_code}).'
    return 'Real-time AI analysis failed. Verify API key, billing, and network, then try again.'


def _parse_structured_ai_json(raw, provider_label, context_label):
    raw = (raw or '').strip()
    if not raw:
        raise ValueError(f'{provider_label} returned an empty response for {context_label}.')

    try:
        return json.loads(raw)
    except json.JSONDecodeError as parse_error:
        print(f'{provider_label} {context_label} JSON decode error: {parse_error}')
        print(f'{provider_label} raw response sample: {raw[:500]}...')

        start = raw.find('{')
        end = raw.rfind('}')
        if start != -1 and end != -1 and end > start:
            try:
                return json.loads(raw[start:end + 1])
            except json.JSONDecodeError:
                pass

        if raw.count('{') > raw.count('}') or not raw.rstrip().endswith('}'):
            raise ValueError(f'{provider_label} returned incomplete JSON for {context_label}.') from parse_error
        raise ValueError(f'{provider_label} returned malformed JSON for {context_label}.') from parse_error


def _create_structured_ai_completion(client, provider, messages, *, temperature, max_tokens, context_label):
    provider_label = get_ai_provider_label(provider)
    request_plan = [(temperature, max_tokens)]

    retry_temperature = min(temperature, 0.2) if provider == 'gemini' else min(temperature, 0.3)
    retry_max_tokens = max(max_tokens, 5000 if provider == 'gemini' else 4000)
    if request_plan[0] != (retry_temperature, retry_max_tokens):
        request_plan.append((retry_temperature, retry_max_tokens))

    last_error = None
    for attempt_number, (attempt_temperature, attempt_max_tokens) in enumerate(request_plan, start=1):
        try:
            response = client.chat.completions.create(
                model=get_ai_model(provider=provider),
                messages=messages,
                temperature=attempt_temperature,
                max_tokens=attempt_max_tokens,
                response_format={'type': 'json_object'}
            )
            raw = (response.choices[0].message.content or '').strip()
            print(
                f'{provider_label} {context_label} response received: '
                f'{len(raw)} characters on attempt {attempt_number}'
            )
            return _parse_structured_ai_json(raw, provider_label, context_label)
        except Exception as completion_error:
            last_error = completion_error
            print(
                f'{provider_label} {context_label} attempt {attempt_number} failed: '
                f'{type(completion_error).__name__}: {completion_error}'
            )

    raise last_error

def extract_text_from_pdf(pdf_file):
    """Extract text from PDF file"""
    try:
        pdf_reader = PyPDF2.PdfReader(pdf_file)
        text = ""
        for page in pdf_reader.pages:
            text += page.extract_text() + "\n"
        return text.strip()
    except Exception as e:
        print(f"PDF extraction error: {e}")
        return None

def calculate_ats_score(resume_text, target_role, skills):
    """Calculate ATS compatibility score based on keywords and formatting"""
    score = 0
    max_score = 100
    
    # Basic checks
    if len(resume_text) > 500:  # Reasonable length
        score += 20
    
    # Check for contact info
    contact_keywords = ['email', '@', 'phone', 'mobile', 'contact']
    if any(keyword in resume_text.lower() for keyword in contact_keywords):
        score += 15
    
    # Check for skills section
    if 'skill' in resume_text.lower():
        score += 15
    
    # Check for experience section
    if 'experience' in resume_text.lower() or 'work' in resume_text.lower():
        score += 15
    
    # Check for education
    if 'education' in resume_text.lower() or 'degree' in resume_text.lower():
        score += 15
    
    # Keyword matching for target role
    target_keywords = target_role.lower().split()
    resume_lower = resume_text.lower()
    keyword_matches = sum(1 for keyword in target_keywords if keyword in resume_lower)
    score += min(keyword_matches * 5, 20)  # Up to 20 points for keywords
    
    return min(score, max_score)

def find_matching_internships(skills, target_role):
    """Find internships matching user's skills and target role"""
    try:
        conn = get_db_connection()
        
        # Get all internships
        internships = conn.execute('SELECT * FROM internships').fetchall()
        
        matches = []
        for internship in internships:
            score = 0
            
            # Check role match
            if target_role.lower() in internship['role'].lower():
                score += 30
            
            # Check company/role keywords
            role_keywords = internship['role'].lower().split()
            for skill in skills:
                if skill.lower() in role_keywords:
                    score += 10
            
            if score > 20:  # Minimum threshold
                matches.append({
                    'id': internship['id'],
                    'company': internship['company'],
                    'role': internship['role'],
                    'city': internship['city'],
                    'mode': internship['mode'],
                    'stipend': internship['stipend'],
                    'score': score
                })
        
        # Sort by score and return top 5
        matches.sort(key=lambda x: x['score'], reverse=True)
        conn.close()
        return matches[:5]
        
    except Exception as e:
        print(f"Internship matching error: {e}")
        return []

def build_resume_analysis_prompt(resume_text, target_role):
    return [
        {
            'role': 'system',
            'content': (
                'You are MargDarshak AI Career Engine, an intelligent career assistant for students. '
                'Respond ONLY with valid JSON that matches the exact schema provided. Do not include markdown, explanation text, or any extra fields. '
                'Use only the resume text and target role to generate the response. Extract structured information from the resume text. '
                'Provide resume-specific insights, unique strengths, concrete gaps, and practical next steps. '
                'If a skill or accomplishment is not present in the resume text, do not mention it. Focus on this candidate and this target role. '
                'Produce a short, unique analysis summary and make every section clearly tied to facts from the resume text. '
                'Keep it concise but advanced, with practical steps and measurable outcomes.'
            )
        },
        {
            'role': 'user',
            'content': (
                'Input:\n'
                f'resume_text: """{resume_text}"""\n'
                f'target_role: "{target_role}"\n'
                'Output JSON schema:\n'
                '{"profile":{"name":"","email":"","phone":"","skills":[],"education":[],"experience":[],"projects":[]},'
                '"skills_analysis":{"strong_skills":[],"missing_skills":[],"skill_levels":{}},'
                '"resume_improvements":[],"skill_gap":[],"internship_suggestions":[],"roadmap":{"3_month":[],"6_month":[],"12_month":[]},'
                '"platform_recommendations":[],"tools":[],"analysis_summary":"","ats_score":0}'
                '\n\n'
                'Rules:\n'
                '1) analysis_summary must be 2-3 short sentences and include one strength, one priority gap, and one next action.\n'
                '2) roadmap must be unique for this resume and target role with exactly 4 step-wise actions in each phase: 3_month, 6_month, 12_month.\n'
                '3) Every roadmap step must include a concrete deliverable or measurable outcome.\n'
                '4) Keep lists concise: strong_skills <= 8, missing_skills <= 6, resume_improvements <= 5, skill_gap <= 4, internship_suggestions <= 4.\n'
                '5) Avoid generic repeated statements and keep content directly tied to the provided resume text.\n'
                '6) Return JSON only.'
            )
        }
    ]


def _normalized_unique(items, max_items=5):
    cleaned_items = []
    seen = set()
    for item in items or []:
        value = re.sub(r'\s+', ' ', str(item or '')).strip(" \t\r\n-â€¢")
        if not value:
            continue
        key = value.lower()
        if key in seen:
            continue
        seen.add(key)
        cleaned_items.append(value)
        if len(cleaned_items) >= max_items:
            break
    return cleaned_items


def _extract_years_experience(resume_text):
    match = re.search(r'(\d+)\s*(?:\+)?\s*(?:years?|yrs?)\s*(?:of\s*)?(?:experience|work)', resume_text, re.IGNORECASE)
    if not match:
        return 0
    try:
        return int(match.group(1))
    except Exception:
        return 0


def _infer_domain(target_role, resume_text):
    text = f"{target_role} {resume_text}".lower()
    domain_signals = {
        'data': ['data', 'analytics', 'analyst', 'machine learning', 'python', 'sql', 'statistics', 'tableau'],
        'software': ['software', 'developer', 'engineer', 'backend', 'frontend', 'full stack', 'api', 'system design'],
        'web': ['web', 'frontend', 'react', 'angular', 'css', 'html', 'javascript', 'ui'],
        'cloud_devops': ['devops', 'cloud', 'aws', 'azure', 'gcp', 'docker', 'kubernetes', 'ci/cd'],
        'cybersecurity': ['security', 'cyber', 'soc', 'penetration', 'siem', 'network security'],
        'product': ['product manager', 'product', 'roadmap', 'stakeholder', 'go-to-market'],
        'design': ['designer', 'ux', 'ui', 'figma', 'prototype', 'user research'],
        'marketing': ['marketing', 'seo', 'content', 'campaign', 'growth', 'branding'],
        'finance': ['finance', 'accounting', 'financial', 'valuation', 'audit', 'excel'],
    }
    best_domain = 'general'
    best_score = 0
    for domain, keywords in domain_signals.items():
        score = sum(1 for keyword in keywords if keyword in text)
        if score > best_score:
            best_score = score
            best_domain = domain
    return best_domain


def _extract_resume_keywords(resume_text, target_role, max_items=10):
    stopwords = {
        'the', 'and', 'for', 'with', 'from', 'that', 'this', 'have', 'has', 'your', 'you', 'are', 'was', 'were',
        'will', 'can', 'about', 'into', 'using', 'used', 'work', 'project', 'projects', 'experience', 'education',
        'resume', 'role', 'skills', 'skill', 'team', 'month', 'year'
    }
    tokens = re.findall(r'[a-zA-Z][a-zA-Z0-9\+\#\.-]{2,}', f"{target_role} {resume_text}".lower())
    freq = {}
    for token in tokens:
        if token in stopwords:
            continue
        freq[token] = freq.get(token, 0) + 1
    ranked = sorted(freq.items(), key=lambda x: (-x[1], x[0]))
    return [token for token, _ in ranked[:max_items]]


def _build_dynamic_roadmap(target_role, strong_skills, missing_skills, resume_text):
    role = target_role.strip() or 'target role'
    top_strength = (strong_skills or ['your core strengths'])[0]
    missing = missing_skills or ['domain fundamentals', 'communication', 'project impact']
    first_gap = missing[0]
    second_gap = missing[1] if len(missing) > 1 else missing[0]
    third_gap = missing[2] if len(missing) > 2 else missing[0]
    years = _extract_years_experience(resume_text)
    domain = _infer_domain(target_role, resume_text)
    keywords = _extract_resume_keywords(resume_text, target_role, max_items=5)
    focus_hint = ', '.join(keywords[:2]) if keywords else role
    exp_prefix = f"Leverage your {years}+ year experience" if years > 0 else "Build practical experience"

    phase_3 = [
        f"Step 1: Rewrite resume bullets for {role} with 6-8 quantified outcomes (impact %, time saved, revenue, accuracy).",
        f"Step 2: Close priority gap '{first_gap}' by completing one focused course and publishing notes within 4 weeks.",
        f"Step 3: Build one role-aligned mini project using {top_strength} and publish code plus measurable results.",
        f"Step 4: Apply to 20 targeted {role} roles with a resume version optimized for {focus_hint}."
    ]

    phase_6 = [
        f"Step 1: Deepen '{second_gap}' through an intermediate project with production-like constraints.",
        f"Step 2: {exp_prefix} by completing one internship or freelance assignment with documented business impact.",
        f"Step 3: Complete 10 mock interviews and prepare concise STAR stories for achievements and problem-solving.",
        f"Step 4: Earn one recognized credential aligned to {role} and attach proof links in your resume."
    ]

    phase_12 = [
        f"Step 1: Master '{third_gap}' to advanced level and complete one capstone solving a real business problem.",
        f"Step 2: Build 3 flagship {role} portfolio projects with architecture, KPIs, and deployment/demo links.",
        f"Step 3: Publish 2 technical posts or talks to build credibility in the {role} community.",
        f"Step 4: Transition to higher-fit {role} opportunities by tracking interview conversion and offer metrics."
    ]

    if domain == 'data':
        phase_6[0] = f"Step 1: Deepen '{second_gap}' by building one end-to-end analytics or ML pipeline with evaluation metrics."
        phase_12[1] = f"Step 2: Build 3 flagship data projects with notebooks, dashboards, and reproducible results."
    elif domain in ('software', 'web'):
        phase_6[0] = f"Step 1: Deepen '{second_gap}' by shipping one full-stack feature with testing and monitoring."
        phase_12[1] = f"Step 2: Build 3 flagship engineering projects with CI/CD, architecture docs, and live demos."
    elif domain == 'cloud_devops':
        phase_6[0] = f"Step 1: Deepen '{second_gap}' by implementing IaC and CI/CD for one deployment workflow."
        phase_12[1] = f"Step 2: Build 3 cloud/devops projects with observability, autoscaling, and rollback strategy."
    elif domain == 'cybersecurity':
        phase_6[0] = f"Step 1: Deepen '{second_gap}' through one SOC-style detection and incident-response lab."
        phase_12[1] = f"Step 2: Build 3 security projects with threat models, hardening checklist, and findings reports."

    return {
        '3_month': _normalized_unique(phase_3, max_items=4),
        '6_month': _normalized_unique(phase_6, max_items=4),
        '12_month': _normalized_unique(phase_12, max_items=4)
    }


def _clamp_percentage(value):
    try:
        return max(0, min(100, int(round(float(value)))))
    except (TypeError, ValueError):
        return 0


def _build_readiness_insights(target_role, strong_skills, missing_skills, resume_text, ats_score):
    role = target_role.strip() or 'target role'
    resume_content = resume_text or ''
    primary_gap = missing_skills[0] if missing_skills else 'role-specific depth'
    secondary_gap = missing_skills[1] if len(missing_skills) > 1 else primary_gap
    tertiary_gap = missing_skills[2] if len(missing_skills) > 2 else primary_gap
    strength_hint = strong_skills[0] if strong_skills else 'your strongest existing skill'
    missing_top = missing_skills[:3]

    has_projects = bool(re.search(r'\b(project|internship|capstone|portfolio|freelance)\b', resume_content, re.IGNORECASE))
    has_quantified_impact = bool(re.search(r'(\d+\s*%|\b(increased|improved|reduced|optimized|launched|scaled)\b)', resume_content, re.IGNORECASE))
    has_dsa_signal = bool(re.search(r'\b(dsa|algorithm|data structures?|leetcode|competitive coding)\b', resume_content, re.IGNORECASE))
    has_aptitude_signal = bool(re.search(r'\b(aptitude|reasoning|quantitative|logical)\b', resume_content, re.IGNORECASE))
    has_comm_signal = bool(re.search(r'\b(communication|presentation|teamwork|leadership|stakeholder)\b', resume_content, re.IGNORECASE))

    base_job_score = 48 + (len(strong_skills) * 6) - (len(missing_skills) * 5)
    if has_projects:
        base_job_score += 8
    if has_quantified_impact:
        base_job_score += 6
    job_readiness_score = _clamp_percentage((base_job_score * 0.6) + (ats_score * 0.4))

    placement_bonus = (8 if has_dsa_signal else 0) + (6 if has_aptitude_signal else 0) + (5 if has_comm_signal else 0)
    placement_readiness_score = _clamp_percentage((job_readiness_score * 0.65) + (ats_score * 0.2) + placement_bonus - (2 if len(missing_skills) >= 4 else 0))

    if missing_top:
        missing_skills_brief = (
            f"For {role}, top missing skills are {', '.join(missing_top)}. "
            f"Start with {primary_gap} first, then close {secondary_gap} and {tertiary_gap} in sequence."
        )
    else:
        missing_skills_brief = (
            f"For {role}, major skill gaps are minimal. Focus on advanced projects, better measurable impact, and interview consistency."
        )

    job_ready_roadmap = _normalized_unique([
        f"Week 1-2: Close '{primary_gap}' with one focused course and complete all exercises.",
        f"Week 3-4: Build one {role}-aligned project using {strength_hint} + {primary_gap} with measurable output.",
        f"Month 2: Update resume for {role} using quantified bullets and missing-skill keywords from job descriptions.",
        f"Month 3: Apply to 20-30 targeted {role} roles and track interview conversion every week."
    ], max_items=4)

    placement_ready_roadmap = _normalized_unique([
        f"Week 1-2: Practice aptitude + core fundamentals daily for 45-60 minutes, especially '{secondary_gap}'.",
        f"Week 3-4: Solve 40-60 role-relevant coding/problem-solving questions and review weak patterns.",
        f"Month 2: Do 6 mock interviews (technical + HR) and prepare concise stories for projects and achievements.",
        f"Month 3: Prepare campus placement kit (resume, elevator pitch, project demos) and revise '{tertiary_gap}'."
    ], max_items=4)

    return {
        'job_readiness_score': job_readiness_score,
        'placement_readiness_score': placement_readiness_score,
        'missing_skills_brief': missing_skills_brief,
        'job_ready_roadmap': job_ready_roadmap,
        'placement_ready_roadmap': placement_ready_roadmap,
    }


def _normalize_analysis_payload(analysis, resume_text, target_role):
    profile = analysis.get('profile', {}) if isinstance(analysis.get('profile'), dict) else {}
    profile.setdefault('name', 'Candidate')
    profile.setdefault('email', '')
    profile.setdefault('phone', '')
    profile.setdefault('skills', [])
    profile.setdefault('education', [])
    profile.setdefault('experience', [])
    profile.setdefault('projects', [])
    analysis['profile'] = profile

    skills_analysis = analysis.get('skills_analysis', {}) if isinstance(analysis.get('skills_analysis'), dict) else {}
    strong_skills = _normalized_unique(skills_analysis.get('strong_skills', []), max_items=8)
    missing_skills = _normalized_unique(skills_analysis.get('missing_skills', []), max_items=6)
    skill_levels_raw = skills_analysis.get('skill_levels', {}) if isinstance(skills_analysis.get('skill_levels'), dict) else {}
    skill_levels = {}
    for skill in strong_skills:
        level = str(skill_levels_raw.get(skill, '')).strip().title() or 'Intermediate'
        if level not in ('Beginner', 'Intermediate', 'Advanced'):
            level = 'Intermediate'
        skill_levels[skill] = level
    skills_analysis['strong_skills'] = strong_skills
    skills_analysis['missing_skills'] = missing_skills
    skills_analysis['skill_levels'] = skill_levels
    analysis['skills_analysis'] = skills_analysis

    ats_score = analysis.get('ats_score')
    if not isinstance(ats_score, (int, float)):
        ats_score = calculate_ats_score(resume_text, target_role, strong_skills)
    ats_score = _clamp_percentage(ats_score)
    analysis['ats_score'] = ats_score

    analysis['resume_improvements'] = _normalized_unique(analysis.get('resume_improvements', []), max_items=5)
    analysis['skill_gap'] = _normalized_unique(analysis.get('skill_gap', []), max_items=4)
    analysis['internship_suggestions'] = _normalized_unique(analysis.get('internship_suggestions', []), max_items=4)
    analysis['platform_recommendations'] = _normalized_unique(analysis.get('platform_recommendations', []), max_items=4)
    analysis['tools'] = _normalized_unique(analysis.get('tools', []), max_items=5)

    generated_roadmap = _build_dynamic_roadmap(target_role, strong_skills, missing_skills, resume_text)
    roadmap = analysis.get('roadmap', {}) if isinstance(analysis.get('roadmap'), dict) else {}
    normalized_roadmap = {}
    for phase in ('3_month', '6_month', '12_month'):
        phase_steps = _normalized_unique(roadmap.get(phase, []), max_items=4)
        if len(phase_steps) < 4:
            phase_steps = _normalized_unique(phase_steps + generated_roadmap[phase], max_items=4)
        normalized_roadmap[phase] = phase_steps
    analysis['roadmap'] = normalized_roadmap

    readiness = _build_readiness_insights(target_role, strong_skills, missing_skills, resume_text, ats_score)
    analysis['job_readiness_score'] = readiness['job_readiness_score']
    analysis['placement_readiness_score'] = readiness['placement_readiness_score']
    analysis['missing_skills_brief'] = readiness['missing_skills_brief']
    analysis['job_ready_roadmap'] = readiness['job_ready_roadmap']
    analysis['placement_ready_roadmap'] = readiness['placement_ready_roadmap']

    summary = re.sub(r'\s+', ' ', str(analysis.get('analysis_summary', '') or '')).strip()
    role_hint = (target_role or '').strip()
    summary_is_generic = len(summary) < 25 or summary.lower().startswith('ai-driven career analysis')
    role_missing = bool(role_hint) and role_hint.split()[0].lower() not in summary.lower()
    if not summary or summary_is_generic or role_missing:
        top_strength = strong_skills[0] if strong_skills else 'core strengths'
        top_gap = missing_skills[0] if missing_skills else 'role-specific depth'
        next_action = analysis['roadmap']['3_month'][0] if analysis['roadmap']['3_month'] else f"Create a 30-day action plan for {target_role}."
        summary = f"For {role_hint or 'this target role'}, strongest area is {top_strength}. Priority gap is {top_gap}. Next action: {next_action}"
    analysis['analysis_summary'] = summary
    return analysis


def analyze_resume_fallback(resume_text, target_role):
    """Fallback resume analysis when live AI is unavailable"""
    resume_lower = resume_text.lower()
    lines = [line.strip() for line in resume_text.splitlines() if line.strip()]
    name = lines[0] if lines else "Candidate"

    email_match = re.search(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b', resume_text)
    email = email_match.group(0) if email_match else ""

    phone_match = re.search(r'\b\d{10}\b|\b\d{3}[-.]?\d{3}[-.]?\d{4}\b', resume_text)
    phone = phone_match.group(0) if phone_match else ""

    common_skills = [
        'python', 'java', 'javascript', 'typescript', 'sql', 'html', 'css', 'react', 'node', 'django', 'flask',
        'machine learning', 'data analysis', 'deep learning', 'nlp', 'tableau', 'power bi', 'excel',
        'git', 'aws', 'azure', 'gcp', 'docker', 'kubernetes', 'linux', 'c++', 'c#', 'figma', 'seo'
    ]
    found_skills = _normalized_unique([skill for skill in common_skills if skill in resume_lower], max_items=8)

    years = _extract_years_experience(resume_text)
    experience = f"{years} years" if years > 0 else "Not specified"

    education_keywords = ['bachelor', 'master', 'phd', 'degree', 'university', 'college', 'b.tech', 'm.tech', 'bsc', 'msc']
    education = "Not found"
    for line in lines:
        if any(keyword in line.lower() for keyword in education_keywords):
            education = line.strip()
            break

    inferred_role = target_role.strip() or 'the target role'
    domain = _infer_domain(target_role, resume_text)
    domain_core_gaps = {
        'data': ['statistics', 'pandas', 'data visualization', 'model evaluation', 'feature engineering'],
        'software': ['data structures', 'algorithms', 'system design', 'testing', 'api design'],
        'web': ['responsive design', 'state management', 'api integration', 'performance optimization', 'testing'],
        'cloud_devops': ['cloud architecture', 'ci/cd', 'infrastructure as code', 'monitoring', 'security hardening'],
        'cybersecurity': ['threat modeling', 'incident response', 'siem', 'security testing', 'risk assessment'],
        'product': ['product metrics', 'user research', 'prioritization', 'stakeholder communication', 'experimentation'],
        'design': ['user research', 'interaction design', 'design systems', 'accessibility', 'usability testing'],
        'marketing': ['campaign analytics', 'seo/sem', 'content strategy', 'a/b testing', 'funnel optimization'],
        'finance': ['financial modeling', 'valuation', 'risk analysis', 'excel automation', 'reporting'],
        'general': ['communication', 'project impact', 'domain knowledge', 'clarity', 'problem-solving'],
    }
    primary_gap = []
    for gap in domain_core_gaps.get(domain, domain_core_gaps['general']):
        if gap.lower() not in resume_lower:
            primary_gap.append(gap)

    if not primary_gap:
        primary_gap = ['clear project impact statements', 'measurable achievements', 'role-specific keywords']

    achievements = bool(re.search(r'\b(improved|increased|reduced|launched|built|designed|implemented|optimized|resulted in)\b', resume_lower))
    has_projects = bool(re.search(r'\b(project|internship|research|capstone|portfolio)\b', resume_lower))

    improvements = []
    if not achievements:
        improvements.append('Add one or two quantified achievements that show impact, such as percentages or outcomes.')
    if not has_projects:
        improvements.append('Include short project summaries with your role, tools used, and results.')
    if found_skills and any(skill in ['machine learning', 'data analysis'] for skill in found_skills) and 'sql' not in found_skills:
        improvements.append('Add SQL or database keywords if you are targeting data roles.')
    if 'summary' not in resume_lower and 'objective' not in resume_lower:
        improvements.append('Add a brief summary or objective at the top that matches the target role.')
    if len(found_skills) < 4:
        improvements.append('Expand the skills section with more role-specific tools and technologies.')
    if not email or not phone:
        improvements.append('Ensure your contact section includes a phone number and email address.')
    if not improvements:
        improvements.append('Review word choice and replace generic terms with specific role-related achievements.')
    improvements = _normalized_unique(improvements, max_items=5)

    keywords = _extract_resume_keywords(resume_text, target_role, max_items=5)
    keyword_hint = ', '.join(keywords[:2]) if keywords else inferred_role
    internship_suggestions = _normalized_unique([
        f'Apply to {inferred_role} internships that require {found_skills[0] if found_skills else "core role skills"}.',
        f'Target internships where projects in {keyword_hint} can be showcased during interviews.',
        'Prioritize openings that emphasize measurable deliverables and ownership.',
        f'Use a tailored resume version for each {inferred_role} application.'
    ], max_items=4)

    summary_fragments = []
    if found_skills:
        summary_fragments.append(f"Strong area: {', '.join(found_skills[:3])}.")
    if primary_gap:
        summary_fragments.append(f"Priority gap: {primary_gap[0]}.")
    if improvements:
        summary_fragments.append(f"Immediate action: {improvements[0]}")

    roadmap = _build_dynamic_roadmap(inferred_role, found_skills, primary_gap[:6], resume_text)

    analysis = {
        'analysis_mode': 'fallback',
        'profile': {
            'name': name,
            'email': email,
            'phone': phone,
            'experience': experience,
            'education': education
        },
        'skills_analysis': {
            'strong_skills': found_skills,
            'missing_skills': primary_gap[:4],
            'skill_levels': {skill: 'Intermediate' for skill in found_skills}
        },
        'resume_improvements': improvements,
        'skill_gap': [
            f'Main gap: {primary_gap[0]}',
            'Improve measurable results and role-specific keyword alignment.',
            f'Build stronger proof for {inferred_role} through outcomes-focused project bullets.',
            f'Close {primary_gap[1] if len(primary_gap) > 1 else primary_gap[0]} with guided practice.'
        ],
        'internship_suggestions': internship_suggestions[:4],
        'roadmap': roadmap,
        'platform_recommendations': [
            'AI Mock Interviewer â†’ Practice interviews with AI feedback',
            'Internship Section â†’ Apply to real internships on MargDarshak',
            'Skill Learning Module â†’ Learn missing skills with structured courses'
        ],
        'tools': [
            'VS Code for development with Python extensions',
            'Git for version control and GitHub portfolio',
            'Jupyter Notebook for project notes'
        ],
        'analysis_summary': ' '.join(summary_fragments).strip() or f'{name} should sharpen resume impact and add role-specific proof.'
    }

    skills = analysis.get('skills_analysis', {}).get('strong_skills', [])
    analysis['ats_score'] = calculate_ats_score(resume_text, target_role, skills)
    analysis['internship_matches'] = find_matching_internships(skills, target_role)

    return _normalize_analysis_payload(analysis, resume_text, target_role)

def analyze_resume_with_openai(resume_text, target_role, allow_fallback=True):
    prompt = build_resume_analysis_prompt(resume_text, target_role)
    providers = get_configured_ai_providers()
    if not providers:
        if allow_fallback:
            print('No AI API key configured. Using fallback analysis...')
            return analyze_resume_fallback(resume_text, target_role)
        raise ValueError('No AI API key is configured. Set GEMINI_API_KEY (preferred) or OPENAI_API_KEY.')

    last_error = None
    for provider in providers:
        provider_label = get_ai_provider_label(provider)
        try:
            client = get_openai_client(provider=provider)
            print(f'Calling {provider_label} API for resume analysis (target role: {target_role})')
            analysis = _create_structured_ai_completion(
                client,
                provider,
                prompt,
                temperature=0.35 if provider == 'gemini' else 0.55,
                max_tokens=5000 if provider == 'gemini' else 3200,
                context_label='resume analysis'
            )

            if not analysis.get('skills_analysis') or not isinstance(analysis.get('skills_analysis'), dict):
                raise ValueError('AI response did not contain valid skills_analysis.')

            analysis = _normalize_analysis_payload(analysis, resume_text, target_role)
            skills = analysis.get('skills_analysis', {}).get('strong_skills', [])
            analysis['ats_score'] = calculate_ats_score(resume_text, target_role, skills)
            analysis['internship_matches'] = find_matching_internships(skills, target_role)
            analysis['analysis_mode'] = 'ai'
            analysis['analysis_provider'] = provider
            analysis['analysis_generated_at'] = datetime.utcnow().isoformat() + 'Z'
            return analysis
        except Exception as e:
            last_error = e
            print(f'{provider_label} resume analysis error: {e}')
            print(f'Error type: {type(e).__name__}')
            print(f'Traceback: {traceback.format_exc()}')

    if allow_fallback:
        print('Falling back to basic analysis...')
        analysis = analyze_resume_fallback(resume_text, target_role)
        analysis['analysis_notice'] = describe_openai_resume_error(last_error)
        return analysis
    raise ValueError(describe_openai_resume_error(last_error))


def generate_pdf_report(analysis, target_role):
    """Generate a PDF report from the analysis data"""
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter)
    styles = getSampleStyleSheet()
    
    # Custom styles
    title_style = ParagraphStyle(
        'CustomTitle',
        parent=styles['Heading1'],
        fontSize=24,
        spaceAfter=30,
        alignment=1,  # Center alignment
        textColor=colors.HexColor('#4f46e5')
    )
    
    section_style = ParagraphStyle(
        'Section',
        parent=styles['Heading2'],
        fontSize=16,
        spaceAfter=15,
        textColor=colors.HexColor('#1f2937')
    )
    
    content_style = styles['Normal']
    content_style.spaceAfter = 10
    
    story = []
    
    # Title
    story.append(Paragraph("AI Career Analysis Report", title_style))
    story.append(Spacer(1, 20))
    
    # Profile Summary
    story.append(Paragraph("Profile Summary", section_style))
    profile = analysis.get('profile', {})
    if profile:
        profile_data = [
            f"Name: {profile.get('name', 'N/A')}",
            f"Email: {profile.get('email', 'N/A')}",
            f"Phone: {profile.get('phone', 'N/A')}",
            f"Experience: {profile.get('experience', 'N/A')}",
            f"Education: {profile.get('education', 'N/A')}"
        ]
        for item in profile_data:
            story.append(Paragraph(item, content_style))
    story.append(Spacer(1, 15))
    
    # Skills Analysis
    story.append(Paragraph("Skills Analysis", section_style))
    skills_analysis = analysis.get('skills_analysis', {})
    
    strong_skills = skills_analysis.get('strong_skills', [])
    if strong_skills:
        story.append(Paragraph("Strong Skills:", ParagraphStyle('Subsection', parent=styles['Heading3'])))
        for skill in strong_skills:
            story.append(Paragraph(f"â€¢ {skill.title()}", content_style))
    
    missing_skills = skills_analysis.get('missing_skills', [])
    if missing_skills:
        story.append(Paragraph("Skills to Improve:", ParagraphStyle('Subsection', parent=styles['Heading3'])))
        for skill in missing_skills:
            story.append(Paragraph(f"â€¢ {skill}", content_style))
    
    story.append(Spacer(1, 15))

    # Job and Placement Readiness
    story.append(Paragraph("Job & Placement Readiness", section_style))
    job_readiness_score = analysis.get('job_readiness_score', 0)
    placement_readiness_score = analysis.get('placement_readiness_score', 0)
    story.append(Paragraph(f"Job Readiness: {job_readiness_score}%", content_style))
    story.append(Paragraph(f"Placement Readiness: {placement_readiness_score}%", content_style))

    missing_skills_brief = str(analysis.get('missing_skills_brief', '') or '').strip()
    if missing_skills_brief:
        story.append(Paragraph(f"Missing Skills Brief: {missing_skills_brief}", content_style))

    job_ready_roadmap = analysis.get('job_ready_roadmap', [])
    if job_ready_roadmap:
        story.append(Paragraph("Job-Ready Roadmap:", ParagraphStyle('ReadinessSubsection', parent=styles['Heading3'])))
        for step in job_ready_roadmap[:4]:
            story.append(Paragraph(f"- {step}", content_style))

    placement_ready_roadmap = analysis.get('placement_ready_roadmap', [])
    if placement_ready_roadmap:
        story.append(Paragraph("Placement-Ready Roadmap:", ParagraphStyle('ReadinessSubsection2', parent=styles['Heading3'])))
        for step in placement_ready_roadmap[:4]:
            story.append(Paragraph(f"- {step}", content_style))

    story.append(Spacer(1, 15))
    
    # ATS Score
    ats_score = analysis.get('ats_score', 0)
    story.append(Paragraph("ATS Compatibility Score", section_style))
    story.append(Paragraph(f"Score: {ats_score}/100", ParagraphStyle('Score', parent=styles['Heading3'], textColor=colors.green if ats_score >= 70 else colors.orange)))
    story.append(Spacer(1, 15))
    
    # Resume Improvements
    improvements = analysis.get('resume_improvements', [])
    if improvements:
        story.append(Paragraph("Resume Improvement Suggestions", section_style))
        for improvement in improvements[:5]:  # Limit to 5 items for PDF
            story.append(Paragraph(f"â€¢ {improvement}", content_style))
        story.append(Spacer(1, 15))
    
    # Roadmap
    roadmap = analysis.get('roadmap', {})
    if roadmap:
        story.append(Paragraph("Career Roadmap", section_style))
        
        for phase, steps in roadmap.items():
            phase_title = phase.replace('_', ' ').title()
            story.append(Paragraph(phase_title, ParagraphStyle('Phase', parent=styles['Heading3'])))
            for step in steps[:3]:  # Limit steps per phase
                story.append(Paragraph(f"â€¢ {step}", content_style))
            story.append(Spacer(1, 10))
    
    # Build PDF
    doc.build(story)
    buffer.seek(0)
    return buffer

# ----------------- PDF Download Route -----------------
@app.route('/career/download-report', methods=['POST'])
@login_required
def download_pdf_report():
    try:
        data = request.get_json()
        analysis = data.get('analysis', {})
        target_role = data.get('target_role', 'Career')
        
        if not analysis:
            return jsonify({'success': False, 'error': 'No analysis data provided'}), 400
        
        # Generate PDF
        pdf_buffer = generate_pdf_report(analysis, target_role)
        
        # Return PDF as response
        from flask import send_file
        pdf_buffer.seek(0)
        return send_file(
            pdf_buffer,
            as_attachment=True,
            download_name=f'career_analysis_report_{target_role.lower().replace(" ", "_")}.pdf',
            mimetype='application/pdf'
        )
        
    except Exception as e:
        print(f"PDF generation error: {e}")
        return jsonify({'success': False, 'error': 'Failed to generate PDF report'}), 500

@app.route('/auth/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        username = request.form.get('username')
        email = request.form.get('email')
        password = request.form.get('password')

        if not username or not email or not password:
            flash('All fields are required', 'error')
            return render_template('auth/signup.html')

        ok = create_user(username, email, password)
        if not ok:
            flash('User already exists or error creating user', 'error')
            return render_template('auth/signup.html')

        flash('Account created. Please log in.', 'success')
        return redirect(url_for('login'))

    return render_template('auth/signup.html')


@app.route('/auth/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')

        user = authenticate_user(email, password)
        if user:
            session['user_id'] = user['id']
            flash('Logged in successfully', 'success')
            log_activity('login', 'auth', f'User logged in: {user["email"]}')
            return redirect(url_for('index'))
        else:
            flash('Invalid credentials', 'error')
            return render_template('auth/login.html')

    return render_template('auth/login.html')


@app.route('/auth/logout')
def logout():
    session.pop('user_id', None)
    flash('Logged out', 'info')
    return redirect(url_for('index'))

# ... rest of your routes
#
# ==================== HOME PAGE ====================
@app.route('/')
def index():
    """Homepage with 3 main modules"""
    try:
        conn = get_db_connection()

        career_count = conn.execute('SELECT COUNT(*) as count FROM careers').fetchone()['count']
        shloka_count = conn.execute('SELECT COUNT(*) as count FROM gyan_kosh').fetchone()['count']
        resource_count = conn.execute('SELECT COUNT(*) as count FROM learning_resources').fetchone()['count']
        mood_count = conn.execute('SELECT COUNT(*) as count FROM mood_entries').fetchone()['count']
        game_sessions = conn.execute("SELECT COUNT(*) as count FROM user_activity WHERE activity_type = 'mindfresh'").fetchone()['count']

        # Get todo notifications for logged-in users
        todo_notifications = []
        user_id = session.get('user_id')
        if user_id:
            try:
                today = datetime.now().strftime('%Y-%m-%d')
                tomorrow = (datetime.now() + timedelta(days=1)).strftime('%Y-%m-%d')

                # Get today's tasks
                today_tasks = conn.execute('''
                    SELECT title, priority, deadline FROM todo_tasks
                    WHERE user_id = ? AND status = 'Pending' AND DATE(deadline) = ?
                    ORDER BY
                        CASE priority
                            WHEN 'High' THEN 1
                            WHEN 'Medium' THEN 2
                            WHEN 'Low' THEN 3
                        END
                ''', (user_id, today)).fetchall()

                # Get overdue tasks
                overdue_tasks = conn.execute('''
                    SELECT title, priority, deadline FROM todo_tasks
                    WHERE user_id = ? AND status = 'Pending' AND DATE(deadline) < ?
                    ORDER BY deadline ASC
                ''', (user_id, today)).fetchall()

                # Get tomorrow's tasks
                tomorrow_tasks = conn.execute('''
                    SELECT title, priority, deadline FROM todo_tasks
                    WHERE user_id = ? AND status = 'Pending' AND DATE(deadline) = ?
                    ORDER BY
                        CASE priority
                            WHEN 'High' THEN 1
                            WHEN 'Medium' THEN 2
                            WHEN 'Low' THEN 3
                        END
                ''', (user_id, tomorrow)).fetchall()

                # Build notifications
                if overdue_tasks:
                    todo_notifications.append({
                        'type': 'overdue',
                        'count': len(overdue_tasks),
                        'message': f"You have {len(overdue_tasks)} overdue task{'s' if len(overdue_tasks) > 1 else ''}",
                        'tasks': [dict(task) for task in overdue_tasks[:3]],  # Show first 3
                        'icon': 'fas fa-exclamation-triangle',
                        'color': 'danger'
                    })

                if today_tasks:
                    todo_notifications.append({
                        'type': 'today',
                        'count': len(today_tasks),
                        'message': f"You have {len(today_tasks)} task{'s' if len(today_tasks) > 1 else ''} due today",
                        'tasks': [dict(task) for task in today_tasks[:3]],  # Show first 3
                        'icon': 'fas fa-calendar-day',
                        'color': 'warning'
                    })

                if tomorrow_tasks:
                    todo_notifications.append({
                        'type': 'tomorrow',
                        'count': len(tomorrow_tasks),
                        'message': f"You have {len(tomorrow_tasks)} task{'s' if len(tomorrow_tasks) > 1 else ''} due tomorrow",
                        'tasks': [dict(task) for task in tomorrow_tasks[:3]],  # Show first 3
                        'icon': 'fas fa-calendar-alt',
                        'color': 'info'
                    })

            except Exception as e:
                print(f"Todo notification error: {e}")

        conn.close()

        stats = {
            'careers': career_count,
            'shlokas': shloka_count,
            'resources': resource_count,
            'moods': mood_count,
            'games': game_sessions,
            'tools': len(TOOLS_CATALOG),  # Number of AI tools available
            'guides': 17  # Number of learning guides
        }

        return render_template('index.html', stats=stats, todo_notifications=todo_notifications)
    except Exception as e:
        print(f"Homepage error: {e}")
        return f"Error: {e}", 500

# ==================== CAREER MODULE ====================
@app.route('/career')
@login_required
def career_home():
    """Career guidance homepage"""
    log_activity('module_access', 'career', 'Accessed career module homepage')
    return render_template('career/quiz.html')

@app.route('/career/quiz', methods=['GET', 'POST'])
@login_required
def career_quiz():
    """Career interest quiz"""
    if request.method == 'POST':
        try:
            data = request.json
            print(f"Received quiz data: {data}")  # Debug
            
            interests = {
                'technical': data.get('technical', 0),
                'creative': data.get('creative', 0),
                'social': data.get('social', 0),
                'analytical': data.get('analytical', 0),
                'entrepreneurial': data.get('entrepreneurial', 0)
            }
            
            print(f"Interests: {interests}")  # Debug
            
            sorted_interests = sorted(interests.items(), key=lambda x: x[1], reverse=True)
            top_two = sorted_interests[:2]
            
            print(f"Top two interests: {top_two}")  # Debug
            
            conn = get_db_connection()
            careers = []
            
            category_mapping = {
                'technical': ['Technology', 'Engineering', 'Business'],
                'creative': ['Creative', 'Business'],
                'social': ['Business', 'Creative'],
                'analytical': ['Technology', 'Business'],
                'entrepreneurial': ['Business', 'Technology']
            }
            
            for interest, score in top_two:
                categories = category_mapping.get(interest, ['Technology'])
                for category in categories:
                    print(f"Querying category: {category} for interest: {interest}")  # Debug
                    results = conn.execute(
                        'SELECT * FROM careers WHERE category = ? LIMIT 2',
                        (category,)
                    ).fetchall()
                    print(f"Found {len(results)} careers in {category}")  # Debug
                    for row in results:
                        careers.append(dict(row))
            
            unique_careers = []
            seen_ids = set()
            for career in careers:
                if career['id'] not in seen_ids:
                    unique_careers.append(career)
                    seen_ids.add(career['id'])
            
            print(f"Total unique careers found: {len(unique_careers)}")  # Debug
            
            # If no careers found, return some default careers
            if not unique_careers:
                print("No careers found, returning default careers")
                default_careers = conn.execute('SELECT * FROM careers LIMIT 5').fetchall()
                unique_careers = [dict(row) for row in default_careers]
            
            conn.close()
            
            # Log career quiz activity
            log_activity('quiz_completed', 'career', 'Completed career interest assessment', 
                        f"Top interests: {', '.join([i[0] for i in top_two])}")
            
            return({
                'success': True,
                'interests': interests,
                'careers': unique_careers[:5]
            })
        except Exception as e:
            print(f"Quiz error: {e}")
            import traceback
            traceback.print_exc()
            return ({'success': False, 'error': str(e)}), 500
    
    return render_template('career/quiz.html')

@app.route('/career/resume-analysis', methods=['POST'])
@login_required
def career_resume_analysis():
    try:
        target_role = request.form.get('target_role', '').strip()
        resume_text = request.form.get('resume_text', '').strip()
        resume_file = request.files.get('resume_file')
        
        print(f"Resume analysis request: target_role='{target_role}', resume_text_length={len(resume_text)}, has_file={bool(resume_file and resume_file.filename)}")
        
        if not target_role:
            return jsonify({'success': False, 'error': 'Target role is required.'}), 400
        
        # Handle file upload
        if resume_file and resume_file.filename:
            if resume_file.filename.lower().endswith('.pdf'):
                extracted_text = extract_text_from_pdf(resume_file)
                if extracted_text is None:
                    return jsonify({'success': False, 'error': 'Failed to extract text from PDF.'}), 400
                resume_text = extracted_text
            elif resume_file.filename.lower().endswith('.txt'):
                resume_text = resume_file.read().decode('utf-8')
            else:
                return jsonify({'success': False, 'error': 'Only PDF and TXT files are supported.'}), 400
        elif not resume_text:
            print("No resume text or file provided")
            return jsonify({'success': False, 'error': 'Resume text or file is required.'}), 400
        
        # Default to graceful fallback so the resume review page still works when
        # the external AI service is rate-limited or temporarily unavailable.
        strict_ai_mode = os.environ.get('RESUME_ANALYSIS_STRICT_AI', '0') == '1'
        analysis = analyze_resume_with_openai(resume_text, target_role, allow_fallback=not strict_ai_mode)
        log_activity('resume_analysis', 'career', 'Performed resume analysis', f'Target role: {target_role}')
        return jsonify({'success': True, 'analysis': analysis})
    except ValueError as ve:
        return jsonify({'success': False, 'error': str(ve)}), 500
    except Exception as e:
        print(f"Resume analysis route error: {e}")
        return jsonify({'success': False, 'error': 'Unable to analyze resume at this time.'}), 500

@app.route('/career/resume-review')
@login_required
def career_resume_review():
    """Resume review page inside Career Compass"""
    log_activity('page_view', 'career', 'Accessed resume review page')
    return render_template('career/resume_review.html')

@app.route('/career/results')
@login_required
def career_results():
    """Display career quiz results"""
    log_activity('page_view', 'career', 'Viewed career quiz results')
    return render_template('career/results.html')

@app.route('/career/browse')
@login_required
def career_browse():
    """Browse all careers"""
    log_activity('page_view', 'career', 'Browsed career options')
    try:
        conn = get_db_connection()
        
        category = request.args.get('category', 'all')
        search_query = request.args.get('search', '').strip()
        
        # Base query
        query = 'SELECT * FROM careers'
        params = []
        
        # Build WHERE conditions
        conditions = []
        
        if category != 'all':
            conditions.append('category = ?')
            params.append(category)
        
        if search_query:
            conditions.append('title LIKE ?')
            params.append(f'%{search_query}%')
        
        if conditions:
            query += ' WHERE ' + ' AND '.join(conditions)
        
        query += ' ORDER BY title'
        
        careers = conn.execute(query, params).fetchall()
        categories = conn.execute('SELECT DISTINCT category FROM careers').fetchall()
        
        conn.close()
        
        career_list = []
        for row in careers:
            career_list.append(dict(row))
        
        category_list = []
        for row in categories:
            category_list.append(row['category'])
        
        return render_template('career/browse.html', 
                             careers=career_list,
                             categories=category_list,
                             selected_category=category,
                             search_query=search_query)
    except Exception as e:
        print(f"Browse error: {e}")
        return f"Error: {e}", 500

@app.route('/career/detail/<int:career_id>')
@login_required
def career_detail(career_id):
    """Detailed career view with roadmap"""
    try:
        conn = get_db_connection()
        career = conn.execute('SELECT * FROM careers WHERE id = ?', (career_id,)).fetchone()
        conn.close()
        
        if career:
            career_dict = dict(career)
            print(f"Career found: {career_dict['title']}")  # Debug
            
            # Log career exploration activity
            log_activity('career_viewed', 'career', f'Explored career: {career_dict["title"]}', 
                        f"Category: {career_dict['category']}")
            
            return render_template('career/detail.html', career=career_dict)
        else:
            print(f"Career not found: {career_id}")  # Debug
            return "Career not found", 404
    except Exception as e:
        print(f"Detail error: {e}")
        import traceback
        traceback.print_exc()
        return f"<h2>Error: {e}</h2><a href='/career/browse'>Back to Browse</a>", 500

# ==================== GYAN KOSH MODULE ====================
GYAN_MEDIA_LIBRARY = [
    {
        'id': 'spiritual-songs',
        'title': 'Spiritual Songs',
        'description': 'Listen to devotional chants and mantras that support peace, courage, and concentration.',
        'items': [
            {
                'title': 'Hanuman Chalisa',
                'info': 'Increases confidence, removes fear, and builds a strong mindset.',
                'embed_url': 'https://www.youtube.com/embed/AETFvQonfV8',
                'watch_url': 'https://www.youtube.com/watch?v=AETFvQonfV8',
            },
            {
                'title': 'Hanuman Ashtak',
                'info': 'Helps overcome problems and reduces stress.',
                'embed_url': 'https://www.youtube.com/embed/5g24iHE4umk',
                'watch_url': 'https://www.youtube.com/watch?v=5g24iHE4umk',
            },
            {
                'title': 'Bajrang Baan',
                'info': 'A powerful prayer for protection and mental strength.',
                'embed_url': 'https://www.youtube.com/embed/dXl2NdlmeIE',
                'watch_url': 'https://www.youtube.com/watch?v=dXl2NdlmeIE',
            },
            {
                'title': 'Shiv Tandav Stotram',
                'info': 'Boosts energy, focus, and a warrior mindset.',
                'embed_url': 'https://www.youtube.com/embed/hMBKmQEPNzI',
                'watch_url': 'https://www.youtube.com/watch?v=hMBKmQEPNzI',
            },
            {
                'title': 'Om Namah Shivaya Chant',
                'info': 'Calms the mind and improves concentration.',
                'embed_url': 'https://www.youtube.com/embed/ccBcAWE_lIY',
                'watch_url': 'https://www.youtube.com/watch?v=ccBcAWE_lIY',
            },
            {
                'title': 'Mahamrityunjaya Mantra',
                'info': 'A healing mantra for peace and inner strength.',
                'embed_url': 'https://www.youtube.com/embed/adyjwFgXRNY',
                'watch_url': 'https://www.youtube.com/watch?v=adyjwFgXRNY',
            },
            {
                'title': 'Rudrashtakam',
                'info': 'A devotional hymn for Lord Shiva that builds discipline and devotion.',
                'embed_url': 'https://www.youtube.com/embed/m3m1dXmTrJU',
                'watch_url': 'https://www.youtube.com/watch?v=m3m1dXmTrJU',
            },
            {
                'title': 'Ram Siya Ram',
                'info': 'Brings peace, emotional balance, and focus.',
                'embed_url': 'https://www.youtube.com/embed/Tl4bQBfOtbg',
                'watch_url': 'https://www.youtube.com/watch?v=Tl4bQBfOtbg',
            },
            {
                'title': 'Hare Krishna Maha Mantra',
                'info': 'Improves positivity and reduces anxiety.',
                'embed_url': 'https://www.youtube.com/embed/Zdcth9NndEA',
                'watch_url': 'https://www.youtube.com/watch?v=Zdcth9NndEA',
            },
            {
                'title': 'Krishna Flute Meditation',
                'info': 'Supports deep relaxation and study or coding focus.',
                'embed_url': 'https://www.youtube.com/embed/5jca-sWgemI',
                'watch_url': 'https://www.youtube.com/watch?v=5jca-sWgemI',
            },
        ],
    },
    {
        'id': 'informative-podcasts',
        'title': 'Informative Podcasts',
        'description': 'Explore podcasts and learning channels for mindset, communication, and education awareness.',
        'items': [
            {
                'title': 'Education System Deep Podcast (India Focus)',
                'info': 'Explores the reality of the Indian education system and encourages a mindset shift.',
                'embed_url': 'https://www.youtube.com/embed/fa_ZXlqwmSM',
                'watch_url': 'https://www.youtube.com/watch?v=fa_ZXlqwmSM',
            },
            {
                'title': 'Cambridge Grow Podcast',
                'info': 'Shares real-life stories, growth mindset lessons, and learning from failures.',
                'embed_url': 'https://www.youtube.com/embed/hpMbnwQPCqI',
                'watch_url': 'https://www.youtube.com/watch?v=hpMbnwQPCqI',
            },
            {
                'title': 'CrashCourse',
                'info': 'Makes science, history, and economics easy to understand.',
                'embed_url': 'https://www.youtube.com/embed?listType=user_uploads&list=crashcourse',
                'watch_url': 'https://www.youtube.com/@crashcourse',
            },
            {
                'title': "Luke's English Podcast",
                'info': 'Helps improve English speaking and communication skills.',
                'embed_url': 'https://www.youtube.com/embed?listType=user_uploads&list=LukesEnglishPodcast',
                'watch_url': 'https://www.youtube.com/@LukesEnglishPodcast',
            },
        ],
    },
]


def _extract_youtube_video_id(url):
    try:
        parsed = urlparse(url or '')
    except Exception:
        return None

    host = (parsed.netloc or '').lower()
    if 'youtu.be' in host:
        return parsed.path.strip('/') or None
    if 'youtube.com' in host:
        query_video = parse_qs(parsed.query).get('v', [None])[0]
        if query_video:
            return query_video
        path_parts = [part for part in parsed.path.split('/') if part]
        if len(path_parts) >= 2 and path_parts[0] == 'embed':
            return path_parts[1]
    return None


def _enrich_gyan_media_library(sections):
    enriched_sections = []
    for section in sections:
        section_copy = dict(section)
        enriched_items = []
        for item in section.get('items', []):
            item_copy = dict(item)
            video_id = item_copy.get('video_id') or _extract_youtube_video_id(item_copy.get('watch_url')) or _extract_youtube_video_id(item_copy.get('embed_url'))
            item_copy['video_id'] = video_id
            item_copy['thumbnail_url'] = (
                f'https://img.youtube.com/vi/{video_id}/hqdefault.jpg' if video_id else None
            )
            item_copy['can_embed_inline'] = bool(video_id and '/embed/' in str(item_copy.get('embed_url', '')))
            enriched_items.append(item_copy)
        section_copy['items'] = enriched_items
        enriched_sections.append(section_copy)
    return enriched_sections


GYAN_MEDIA_LIBRARY = _enrich_gyan_media_library(GYAN_MEDIA_LIBRARY)


@app.route('/gyan')
@login_required
def gyan_home():
    """Gyan Kosh homepage - Daily Shloka"""
    try:
        conn = get_db_connection()
        
        count = conn.execute('SELECT COUNT(*) as count FROM gyan_kosh').fetchone()['count']
        
        if count == 0:
            conn.close()
            return """
            <div style="text-align: center; padding: 50px;">
                <h2>No data available</h2>
                <p>Please run: <code>python database/load_csv_to_db.py</code></p>
                <a href="/" style="padding: 10px 20px; background: #667eea; color: white; text-decoration: none; border-radius: 5px;">Back to Home</a>
            </div>
            """, 500
        
        shloka = conn.execute('SELECT * FROM gyan_kosh ORDER BY RANDOM() LIMIT 1').fetchone()
        conn.close()
        
        if shloka:
            # Log daily wisdom activity
            log_activity('daily_wisdom', 'gyan', 'Read daily spiritual wisdom', 
                        f"Chapter {shloka['chapter']}, Verse {shloka['verse_number']}")
            
            return render_template(
                'gyan/daily.html',
                shloka=dict(shloka),
                media_library=GYAN_MEDIA_LIBRARY
            )
        else:
            return "No shlokas found", 500
            
    except Exception as e:
        print(f"Gyan home error: {e}")
        return f"<h2>Error: {e}</h2><a href='/'>Back to Home</a>", 500

@app.route('/gyan/search')
@login_required
def gyan_search():
    """Search shlokas"""
    try:
        query = request.args.get('q', '').strip()
        
        conn = get_db_connection()
        
        if query:
            search_pattern = f'%{query}%'
            shlokas = conn.execute('''
                SELECT * FROM gyan_kosh 
                WHERE hindi_meaning LIKE ? 
                OR english_meaning LIKE ? 
                OR practical_application LIKE ?
                OR tags LIKE ?
            ''', (search_pattern, search_pattern, search_pattern, search_pattern)).fetchall()
            
            # Log search activity
            log_activity('wisdom_search', 'gyan', f'Searched wisdom: "{query}"', 
                        f"Found {len(shlokas)} results")
        else:
            shlokas = conn.execute('SELECT * FROM gyan_kosh ORDER BY chapter, verse_number LIMIT 20').fetchall()
        
        conn.close()
        
        shloka_list = []
        for row in shlokas:
            shloka_list.append(dict(row))
        
        return render_template('gyan/search.html', 
                             shlokas=shloka_list,
                             query=query)
    except Exception as e:
        print(f"Search error: {e}")
        return f"Error: {e}", 500

@app.route('/gyan/detail/<int:shloka_id>')
@login_required
def gyan_detail(shloka_id):
    """Detailed shloka view"""
    try:
        conn = get_db_connection()
        shloka = conn.execute('SELECT * FROM gyan_kosh WHERE id = ?', (shloka_id,)).fetchone()
        conn.close()
        
        if shloka:
            # Log detailed wisdom reading
            log_activity('wisdom_detail', 'gyan', f'Read detailed wisdom: Chapter {shloka["chapter"]}, Verse {shloka["verse_number"]}', 
                        f"Title: {shloka['english_meaning'][:50]}...")
            
            return render_template('gyan/detail.html', shloka=dict(shloka))
        return "Shloka not found", 404
    except Exception as e:
        print(f"Gyan detail error: {e}")
        return f"Error: {e}", 500

APTITUDE_QUESTION_BANK = {
    'Quantitative Aptitude': [
        {'id': 'qa_1', 'topic': 'Quantitative Aptitude', 'question': 'A shopkeeper buys an item for 800 and sells it for 920. What is the profit percentage?', 'options': ['12%', '15%', '18%', '20%'], 'answer_index': 1, 'explanation': 'Profit = 920 - 800 = 120. Profit% = 120/800 x 100 = 15%.'},
        {'id': 'qa_2', 'topic': 'Quantitative Aptitude', 'question': 'Find the average of 12, 15, 18, 21 and 24.', 'options': ['16', '17', '18', '19'], 'answer_index': 2, 'explanation': 'Sum is 90. Average is 90/5 = 18.'},
        {'id': 'qa_3', 'topic': 'Quantitative Aptitude', 'question': 'Simple interest on 5000 at 8% per year for 2 years is:', 'options': ['600', '700', '800', '900'], 'answer_index': 2, 'explanation': 'SI = P x R x T / 100 = 5000 x 8 x 2 / 100 = 800.'},
        {'id': 'qa_4', 'topic': 'Quantitative Aptitude', 'question': 'If the ratio of boys to girls is 3:5 and total students are 40, number of boys is:', 'options': ['12', '15', '18', '20'], 'answer_index': 1, 'explanation': 'Total parts = 8. One part = 5. Boys = 3 x 5 = 15.'},
        {'id': 'qa_5', 'topic': 'Quantitative Aptitude', 'question': 'A car travels 150 km at 60 km/h. Time taken is:', 'options': ['2 hours', '2.5 hours', '3 hours', '3.5 hours'], 'answer_index': 1, 'explanation': 'Time = Distance/Speed = 150/60 = 2.5 hours.'},
        {'id': 'qa_6', 'topic': 'Quantitative Aptitude', 'question': 'If x + 2x + 3x = 72, then x =', 'options': ['10', '11', '12', '13'], 'answer_index': 2, 'explanation': '6x = 72, so x = 12.'},
        {'id': 'qa_7', 'topic': 'Quantitative Aptitude', 'question': 'After a 20% discount, an item costs 1200. Original price was:', 'options': ['1400', '1450', '1500', '1600'], 'answer_index': 2, 'explanation': '1200 is 80% of original. Original = 1200/0.8 = 1500.'},
        {'id': 'qa_8', 'topic': 'Quantitative Aptitude', 'question': '25% of a number is 45. The number is:', 'options': ['160', '170', '180', '190'], 'answer_index': 2, 'explanation': 'Number = 45/0.25 = 180.'},
        {'id': 'qa_9', 'topic': 'Quantitative Aptitude', 'question': 'If 30% of a 50 liter mixture is water, water quantity is:', 'options': ['10 L', '12 L', '15 L', '18 L'], 'answer_index': 2, 'explanation': '30% of 50 = 15 liters.'},
        {'id': 'qa_10', 'topic': 'Quantitative Aptitude', 'question': 'Compound interest on 1000 at 10% for 2 years is:', 'options': ['190', '200', '210', '220'], 'answer_index': 2, 'explanation': 'Amount = 1000 x (1.1)^2 = 1210. CI = 1210 - 1000 = 210.'}
    ],
    'Logical Reasoning': [
        {'id': 'lr_1', 'topic': 'Logical Reasoning', 'question': 'Find the next number in the series: 2, 6, 12, 20, 30, ?', 'options': ['36', '40', '42', '44'], 'answer_index': 2, 'explanation': 'Pattern is n(n+1): 1x2, 2x3, 3x4... next is 6x7 = 42.'},
        {'id': 'lr_2', 'topic': 'Logical Reasoning', 'question': 'Choose the odd one out.', 'options': ['Circle', 'Triangle', 'Square', 'Apple'], 'answer_index': 3, 'explanation': 'Apple is not a geometric shape.'},
        {'id': 'lr_3', 'topic': 'Logical Reasoning', 'question': 'All roses are flowers. Some flowers fade quickly. Which conclusion is definitely true?', 'options': ['All flowers are roses', 'Some roses may fade quickly', 'No rose fades quickly', 'Only roses fade quickly'], 'answer_index': 1, 'explanation': 'Since roses are flowers and some flowers fade, roses may be in that set.'},
        {'id': 'lr_4', 'topic': 'Logical Reasoning', 'question': 'If CAT is coded as DBU, DOG is coded as:', 'options': ['EPH', 'EOG', 'EPI', 'FQI'], 'answer_index': 0, 'explanation': 'Each letter shifts by +1: D O G -> E P H.'},
        {'id': 'lr_5', 'topic': 'Logical Reasoning', 'question': 'A person walks 5 km North, then 3 km East. How far is he from starting point?', 'options': ['8 km', '5.5 km', '6 km', '34 km'], 'answer_index': 1, 'explanation': 'Use Pythagoras: sqrt(5^2 + 3^2) = sqrt(34) about 5.83 km. Nearest is 5.5 km.'},
        {'id': 'lr_6', 'topic': 'Logical Reasoning', 'question': 'A is brother of B. C is sister of B. D is father of C. How is D related to A?', 'options': ['Uncle', 'Father', 'Grandfather', 'Brother'], 'answer_index': 1, 'explanation': 'If D is father of C and C is sibling of A, D is father of A.'},
        {'id': 'lr_7', 'topic': 'Logical Reasoning', 'question': 'If 1 January is Monday, what day is 1 February?', 'options': ['Tuesday', 'Wednesday', 'Thursday', 'Friday'], 'answer_index': 2, 'explanation': 'January has 31 days. 31 mod 7 = 3, so Monday + 3 = Thursday.'},
        {'id': 'lr_8', 'topic': 'Logical Reasoning', 'question': 'A is left of B and C is right of B. Who is in the middle?', 'options': ['A', 'B', 'C', 'Cannot say'], 'answer_index': 1, 'explanation': 'Order is A, B, C. B is in the middle.'},
        {'id': 'lr_9', 'topic': 'Logical Reasoning', 'question': 'At 3:30, the angle between hour and minute hands is:', 'options': ['60 degrees', '75 degrees', '90 degrees', '105 degrees'], 'answer_index': 1, 'explanation': 'Hour hand at 105 deg, minute hand at 180 deg, difference is 75 deg.'},
        {'id': 'lr_10', 'topic': 'Logical Reasoning', 'question': 'Choose the analogous pair: 4 : 16 :: 6 : ?', 'options': ['24', '30', '36', '42'], 'answer_index': 2, 'explanation': '16 = 4 squared, so 6 squared = 36.'}
    ],
    'Verbal Ability': [
        {'id': 'va_1', 'topic': 'Verbal Ability', 'question': 'Choose the synonym of "Diligent".', 'options': ['Lazy', 'Hardworking', 'Careless', 'Slow'], 'answer_index': 1, 'explanation': 'Diligent means hardworking and careful.'},
        {'id': 'va_2', 'topic': 'Verbal Ability', 'question': 'Choose the antonym of "Abundant".', 'options': ['Plentiful', 'Scarce', 'Enough', 'Large'], 'answer_index': 1, 'explanation': 'Abundant means plenty; opposite is scarce.'},
        {'id': 'va_3', 'topic': 'Verbal Ability', 'question': 'Fill in the blank: She ____ to school every day.', 'options': ['go', 'goes', 'gone', 'going'], 'answer_index': 1, 'explanation': 'For singular subject she, present tense verb is goes.'},
        {'id': 'va_4', 'topic': 'Verbal Ability', 'question': 'Choose the correct sentence.', 'options': ['He do not like tea.', 'He does not likes tea.', 'He does not like tea.', 'He not like tea.'], 'answer_index': 2, 'explanation': 'Correct structure: does not + base verb.'},
        {'id': 'va_5', 'topic': 'Verbal Ability', 'question': 'One word for "A person who loves books" is:', 'options': ['Bibliophile', 'Biologist', 'Philanthropist', 'Linguist'], 'answer_index': 0, 'explanation': 'Bibliophile means a book lover.'},
        {'id': 'va_6', 'topic': 'Verbal Ability', 'question': 'Choose the correctly spelled word.', 'options': ['Accomodate', 'Acommodate', 'Accommodate', 'Acomodate'], 'answer_index': 2, 'explanation': 'Correct spelling is Accommodate.'},
        {'id': 'va_7', 'topic': 'Verbal Ability', 'question': 'Idiom: "Hit the nail on the head" means:', 'options': ['To hurt someone', 'To say exactly right', 'To fix something', 'To make noise'], 'answer_index': 1, 'explanation': 'It means describing exactly what is causing a situation.'},
        {'id': 'va_8', 'topic': 'Verbal Ability', 'question': 'Fill in the blank: He is good ____ mathematics.', 'options': ['in', 'at', 'on', 'with'], 'answer_index': 1, 'explanation': 'The usual phrase is good at mathematics.'},
        {'id': 'va_9', 'topic': 'Verbal Ability', 'question': 'Choose the passive form: "They completed the project."', 'options': ['The project completed by them.', 'The project was completed by them.', 'The project is completed by them.', 'The project had completed by them.'], 'answer_index': 1, 'explanation': 'Simple past active converts to was/were + past participle.'},
        {'id': 'va_10', 'topic': 'Verbal Ability', 'question': 'Pick the sentence with correct punctuation.', 'options': ['Lets eat, Grandma!', 'Let us eat Grandma!', 'Lets eat Grandma!', 'Let us eat, Grandma.'], 'answer_index': 3, 'explanation': 'Comma before Grandma and correct apostrophe-free phrase make it clear and correct.'}
    ],
    'Data Interpretation': [
        {'id': 'di_1', 'topic': 'Data Interpretation', 'question': 'Sales in units are A=120, B=150, C=90. Which product has highest sales?', 'options': ['A', 'B', 'C', 'A and B'], 'answer_index': 1, 'explanation': '150 is the highest value, so B.'},
        {'id': 'di_2', 'topic': 'Data Interpretation', 'question': 'Given values 45, 55, 60 and 40, total is:', 'options': ['180', '190', '200', '210'], 'answer_index': 2, 'explanation': '45 + 55 + 60 + 40 = 200.'},
        {'id': 'di_3', 'topic': 'Data Interpretation', 'question': 'A value increases from 80 to 100. Percentage increase is:', 'options': ['20%', '25%', '30%', '40%'], 'answer_index': 1, 'explanation': 'Increase is 20. 20/80 x 100 = 25%.'},
        {'id': 'di_4', 'topic': 'Data Interpretation', 'question': 'If a pie chart sector is 25% and total is 400, the sector value is:', 'options': ['80', '90', '100', '120'], 'answer_index': 2, 'explanation': '25% of 400 is 100.'},
        {'id': 'di_5', 'topic': 'Data Interpretation', 'question': 'In a class, boys:girls = 3:2 and total is 50. Girls are:', 'options': ['18', '20', '22', '25'], 'answer_index': 1, 'explanation': 'Total parts 5, one part 10, girls 2 parts = 20.'},
        {'id': 'di_6', 'topic': 'Data Interpretation', 'question': 'Average of 10, 20, 30, 40 and 50 is:', 'options': ['25', '30', '35', '40'], 'answer_index': 1, 'explanation': 'Sum is 150, average is 150/5 = 30.'},
        {'id': 'di_7', 'topic': 'Data Interpretation', 'question': 'Revenue is 500 and cost is 420. Profit is:', 'options': ['60', '70', '80', '90'], 'answer_index': 2, 'explanation': 'Profit = Revenue - Cost = 80.'},
        {'id': 'di_8', 'topic': 'Data Interpretation', 'question': 'Month 1 students enrolled: 120, Month 2: 150. Difference is:', 'options': ['20', '25', '30', '35'], 'answer_index': 2, 'explanation': '150 - 120 = 30.'},
        {'id': 'di_9', 'topic': 'Data Interpretation', 'question': 'If 60 out of 75 students passed, pass percentage is:', 'options': ['75%', '80%', '85%', '90%'], 'answer_index': 1, 'explanation': '60/75 x 100 = 80%.'},
        {'id': 'di_10', 'topic': 'Data Interpretation', 'question': 'Dataset: 12, 14, 16, 18, 20. Median is:', 'options': ['14', '15', '16', '17'], 'answer_index': 2, 'explanation': 'Middle value in ordered set is 16.'}
    ]
}


def _safe_int(value, default=0):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _seeded_sample(items, count, seed_value):
    if not items:
        return []
    rng = random.Random(seed_value)
    if len(items) <= count:
        return list(items)
    return rng.sample(items, count)


def _daily_quiz_questions_for_topic(user_id, topic, question_count=10):
    selected_topic = topic if topic in APTITUDE_QUESTION_BANK else 'Random'
    if selected_topic == 'Random':
        pool = [q for topic_questions in APTITUDE_QUESTION_BANK.values() for q in topic_questions]
    else:
        pool = list(APTITUDE_QUESTION_BANK.get(selected_topic, []))

    date_key = datetime.now().strftime('%Y-%m-%d')
    seed_value = f"{date_key}:{user_id}:{selected_topic}"
    return _seeded_sample(pool, question_count, seed_value)


def _fallback_aptitude_questions(topic, user_id, mode='daily', question_count=10):
    selected_topic = topic if topic in APTITUDE_QUESTION_BANK else 'Random'

    if selected_topic == 'Random':
        pool = [q for topic_questions in APTITUDE_QUESTION_BANK.values() for q in topic_questions]
    else:
        pool = list(APTITUDE_QUESTION_BANK.get(selected_topic, []))
        if len(pool) < question_count:
            filler = [
                q for topic_name, topic_questions in APTITUDE_QUESTION_BANK.items()
                if topic_name != selected_topic
                for q in topic_questions
            ]
            pool.extend(filler)

    if mode == 'daily':
        date_key = datetime.now().strftime('%Y-%m-%d')
        seed_value = f"{date_key}:{user_id}:{selected_topic}:fallback"
        questions = _seeded_sample(pool, question_count, seed_value)
    else:
        questions = random.sample(pool, min(question_count, len(pool)))

    normalized = []
    for idx, q in enumerate(questions):
        normalized.append({
            'id': str(q.get('id') or f'q_{idx + 1}'),
            'topic': str(q.get('topic') or selected_topic),
            'question': str(q.get('question') or '').strip(),
            'options': list(q.get('options') or [])[:4],
            'answer_index': _safe_int(q.get('answer_index'), 0),
            'explanation': str(q.get('explanation') or 'Review this concept once more.').strip(),
            'difficulty': str(q.get('difficulty') or 'Medium').title()
        })
    return normalized[:question_count]


def _extract_aptitude_question_items(payload):
    if isinstance(payload, list):
        return payload
    if not isinstance(payload, dict):
        raise ValueError('AI response was not a JSON object or question list.')

    for key in ('questions', 'quiz', 'items', 'data', 'results'):
        candidate = payload.get(key)
        if isinstance(candidate, list):
            return candidate

    raise ValueError('AI response did not include a valid questions list.')


def _normalize_aptitude_options(options):
    if isinstance(options, dict):
        ordered = []
        for key in ('A', 'B', 'C', 'D', 'a', 'b', 'c', 'd', '1', '2', '3', '4'):
            value = options.get(key)
            if str(value or '').strip():
                ordered.append(value)
        if not ordered:
            ordered = list(options.values())
        options = ordered
    elif isinstance(options, str):
        options = re.split(r'\n+|[|;]', options)

    if not isinstance(options, list):
        return []

    cleaned = [re.sub(r'\s+', ' ', str(opt or '').strip()) for opt in options if str(opt or '').strip()]
    return cleaned[:4]


def _coerce_aptitude_answer_index(item, cleaned_options):
    answer_index = _safe_int(item.get('answer_index'), -1)
    if 0 <= answer_index < len(cleaned_options):
        return answer_index

    answer_value = str(item.get('answer') or item.get('correct_answer') or item.get('correct_option') or '').strip()
    if answer_value:
        upper_answer = answer_value.upper()
        if upper_answer in ('A', 'B', 'C', 'D'):
            letter_index = ord(upper_answer) - ord('A')
            if letter_index < len(cleaned_options):
                return letter_index

        normalized_answer = re.sub(r'^\s*[A-D][\).\:-]?\s*', '', answer_value, flags=re.IGNORECASE)
        normalized_answer = re.sub(r'\s+', ' ', normalized_answer).strip()
        if normalized_answer in cleaned_options:
            return cleaned_options.index(normalized_answer)

    return 0


def _merge_aptitude_question_sets(primary_questions, fallback_questions, question_count):
    merged = []
    seen = set()

    for question in list(primary_questions) + list(fallback_questions):
        if not isinstance(question, dict):
            continue
        question_text = re.sub(r'\s+', ' ', str(question.get('question') or '').strip()).lower()
        if not question_text or question_text in seen:
            continue
        seen.add(question_text)
        merged.append(question)
        if len(merged) >= question_count:
            break

    return merged[:question_count]


def _normalize_aptitude_questions(payload, requested_topic='Random', question_count=10):
    raw_questions = _extract_aptitude_question_items(payload)

    normalized = []
    seen_questions = set()
    for idx, item in enumerate(raw_questions):
        if not isinstance(item, dict):
            continue
        question_text = re.sub(r'\s+', ' ', str(item.get('question') or '').strip())
        if not question_text or question_text.lower() in seen_questions:
            continue
        seen_questions.add(question_text.lower())

        options = (
            item.get('options')
            or item.get('choices')
            or item.get('answers')
            or item.get('options_list')
        )
        cleaned_options = _normalize_aptitude_options(options)
        if len(cleaned_options) < 4:
            continue

        answer_index = _coerce_aptitude_answer_index(item, cleaned_options)

        topic = re.sub(r'\s+', ' ', str(item.get('topic') or requested_topic).strip()) or requested_topic
        difficulty = str(item.get('difficulty') or 'Medium').strip().title()
        if difficulty not in ('Easy', 'Medium', 'Hard'):
            difficulty = 'Medium'

        normalized.append({
            'id': str(item.get('id') or f'ai_q_{idx + 1}'),
            'topic': topic,
            'question': question_text,
            'options': cleaned_options,
            'answer_index': answer_index,
            'explanation': re.sub(r'\s+', ' ', str(item.get('explanation') or 'Review this concept once more.').strip()),
            'difficulty': difficulty
        })

    return normalized[:question_count]


def _generate_aptitude_questions_with_openai(topic, user_id, mode='daily', question_count=10, provider=None):
    selected_topic = topic if topic in APTITUDE_QUESTION_BANK else 'Random'
    date_key = datetime.now().strftime('%Y-%m-%d')
    nonce = random.randint(1000, 999999)

    topic_instruction = (
        "Mix questions from Quantitative Aptitude, Logical Reasoning, Verbal Ability, and Data Interpretation."
        if selected_topic == 'Random' else
        f"Create all questions only for this topic: {selected_topic}."
    )

    uniqueness_hint = (
        f"Generate a daily unique set for learner_id={user_id} on date={date_key}. Keep it stable for this date."
        if mode == 'daily' else
        f"Generate a fresh random set now using nonce={nonce}."
    )

    prompt = [
        {
            'role': 'system',
            'content': (
                'You are an aptitude quiz generator for students. '
                'Return only strict JSON. No markdown.'
            )
        },
        {
            'role': 'user',
            'content': (
                f'Build exactly {question_count} multiple-choice aptitude questions.\n'
                f'{topic_instruction}\n'
                f'{uniqueness_hint}\n'
                'Difficulty distribution: 3 Easy, 5 Medium, 2 Hard.\n'
                'Each question must have exactly 4 options and a single correct answer.\n'
                'Keep language simple and exam-oriented.\n'
                'JSON format only:\n'
                '{\n'
                '  "questions": [\n'
                '    {\n'
                '      "id": "q1",\n'
                '      "topic": "Quantitative Aptitude",\n'
                '      "difficulty": "Easy|Medium|Hard",\n'
                '      "question": "text",\n'
                '      "options": ["A", "B", "C", "D"],\n'
                '      "answer_index": 0,\n'
                '      "explanation": "short explanation"\n'
                '    }\n'
                '  ]\n'
                '}\n'
            )
        }
    ]

    provider = provider or get_ai_provider()
    client = get_openai_client(provider=provider)
    payload = _create_structured_ai_completion(
        client,
        provider,
        prompt,
        temperature=0.2 if provider == 'gemini' else (0.35 if mode == 'random' else 0.25),
        max_tokens=5000 if provider == 'gemini' else 3600,
        context_label='aptitude quiz generation'
    )
    normalized = _normalize_aptitude_questions(payload, requested_topic=selected_topic, question_count=question_count)
    if len(normalized) >= question_count:
        return normalized[:question_count]

    fallback_questions = _fallback_aptitude_questions(
        topic=selected_topic,
        user_id=user_id,
        mode=mode,
        question_count=question_count
    )
    merged = _merge_aptitude_question_sets(normalized, fallback_questions, question_count)
    if len(merged) < question_count:
        raise ValueError(f'AI returned only {len(normalized)} valid questions and fallback merge produced only {len(merged)}.')
    return merged


def _generate_aptitude_questions(topic, user_id, mode='daily', question_count=10):
    providers = get_configured_ai_providers()
    if not providers:
        raise ValueError('No AI API key is configured. Set GEMINI_API_KEY or OPENAI_API_KEY.')

    last_error = None
    for provider in providers:
        try:
            questions = _generate_aptitude_questions_with_openai(
                topic=topic,
                user_id=user_id,
                mode=mode,
                question_count=question_count,
                provider=provider
            )
            return questions, provider
        except Exception as provider_error:
            print(f"Aptitude quiz {provider} generation failed: {provider_error}")
            last_error = provider_error

    raise last_error or ValueError('Unable to generate aptitude quiz with configured AI providers.')


GD_GROUP_SIZE = 5
GD_DEFAULT_TOPICS = [
    'AI is creating more jobs than it is replacing.',
    'Start-up vs Corporate Job: what is better for freshers?',
    'Online education is better than offline education.',
    'Should companies prioritize skills over degrees in hiring?',
    'Social media helps students grow professionally.',
    'Remote work is better than office work for productivity.',
    'Is coding compulsory for all engineering students?',
    'Can AI tools improve interview preparation outcomes?',
    'Should internships be mandatory before graduation?',
    'Group discussions are a fair method for campus shortlisting.'
]


def _parse_db_datetime(value):
    if not value:
        return None
    text = str(value).strip()
    for fmt in ('%Y-%m-%d %H:%M:%S.%f', '%Y-%m-%d %H:%M:%S'):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    return None


def _sanitize_text(value, max_len=1200):
    text = re.sub(r'\s+', ' ', str(value or '').strip())
    return text[:max_len]


def _build_gd_room_id():
    return f"GD-{datetime.now().strftime('%Y%m%d%H%M%S')}-{random.randint(100, 999)}"


def _cleanup_stale_gd_queue(conn):
    conn.execute(
        """UPDATE gd_queue
           SET status = 'expired'
           WHERE status = 'waiting'
             AND created_at < datetime('now', '-45 minutes')"""
    )


def _generate_gd_topic(field_hint='', role_hint=''):
    field_hint = _sanitize_text(field_hint, max_len=80)
    role_hint = _sanitize_text(role_hint, max_len=80)
    try:
        client = get_openai_client()
        prompt = [
            {
                'role': 'system',
                'content': 'You create concise placement-focused group discussion topics for students.'
            },
            {
                'role': 'user',
                'content': (
                    f'Generate exactly one GD topic (max 16 words).\n'
                    f'Field hint: {field_hint or "General"}\n'
                    f'Target role hint: {role_hint or "General"}\n'
                    'Topic must be debate-friendly and suitable for campus placement rounds.\n'
                    'Return only the topic line, no numbering, no quotes.'
                )
            }
        ]
        result = client.chat.completions.create(
            model=get_ai_model(),
            messages=prompt,
            temperature=0.9,
            max_tokens=60
        )
        topic = _sanitize_text(result.choices[0].message.content or '', max_len=180)
        if topic:
            return topic
    except Exception as e:
        print(f"GD topic generation fallback: {e}")
    return random.choice(GD_DEFAULT_TOPICS)


def _sync_gd_session_status(conn, session_row):
    if not session_row:
        return None

    row = dict(session_row)
    status = row.get('status', 'active')
    now = datetime.now()
    # New host-managed flow: status transitions via started_at + duration_minutes
    started_at = _parse_db_datetime(row.get('started_at'))
    duration_minutes = max(1, _safe_int(row.get('duration_minutes'), 10))
    if status == 'active' and started_at:
        if now >= started_at + timedelta(minutes=duration_minutes):
            status = 'feedback'
            conn.execute(
                "UPDATE gd_sessions SET status = 'feedback', ended_at = CURRENT_TIMESTAMP WHERE id = ?",
                (row['id'],)
            )

    # Legacy fallback flow support
    discussion_end_at = _parse_db_datetime(row.get('discussion_end_at'))
    feedback_deadline_at = _parse_db_datetime(row.get('feedback_deadline_at'))
    if status == 'active' and discussion_end_at and now >= discussion_end_at:
        status = 'feedback'
        conn.execute("UPDATE gd_sessions SET status = 'feedback' WHERE id = ?", (row['id'],))
    if status == 'feedback' and feedback_deadline_at and now >= feedback_deadline_at:
        status = 'completed'
        conn.execute("UPDATE gd_sessions SET status = 'completed', completed_at = CURRENT_TIMESTAMP WHERE id = ?", (row['id'],))

    refreshed = conn.execute(
        "SELECT * FROM gd_sessions WHERE id = ?",
        (row['id'],)
    ).fetchone()
    return refreshed


def _calculate_gd_phase(session_row):
    if not session_row:
        return 'unknown', 0
    row = dict(session_row)
    status = row.get('status')
    now = datetime.now()
    if status == 'planning':
        return 'lobby', max(1, _safe_int(row.get('duration_minutes'), 10)) * 60
    if status == 'active':
        # New host-managed mode
        started_at = _parse_db_datetime(row.get('started_at'))
        duration_minutes = max(1, _safe_int(row.get('duration_minutes'), 10))
        if started_at:
            remaining = int((started_at + timedelta(minutes=duration_minutes) - now).total_seconds())
            if remaining > 0:
                return 'discussion', max(0, remaining)
            return 'feedback', 0

        # Legacy mode fallback
        thinking_end = _parse_db_datetime(row.get('thinking_end_at'))
        discussion_end = _parse_db_datetime(row.get('discussion_end_at'))
        if thinking_end and now < thinking_end:
            remaining = int((thinking_end - now).total_seconds())
            return 'thinking', max(0, remaining)
        if discussion_end and now < discussion_end:
            remaining = int((discussion_end - now).total_seconds())
            return 'discussion', max(0, remaining)
        return 'feedback', 0
    if status == 'feedback':
        deadline = _parse_db_datetime(row.get('feedback_deadline_at'))
        remaining = int((deadline - now).total_seconds()) if deadline else 0
        return 'feedback', max(0, remaining)
    if status == 'completed':
        return 'completed', 0
    return status, 0


def _attempt_gd_matchmaking(conn):
    _cleanup_stale_gd_queue(conn)
    waiting_rows = conn.execute(
        """SELECT * FROM gd_queue
           WHERE status = 'waiting'
           ORDER BY created_at ASC
           LIMIT ?""",
        (GD_GROUP_SIZE,)
    ).fetchall()
    if len(waiting_rows) < GD_GROUP_SIZE:
        return None

    room_id = _build_gd_room_id()
    fields = [str(row['field'] or '').strip() for row in waiting_rows if str(row['field'] or '').strip()]
    roles = [str(row['target_role'] or '').strip() for row in waiting_rows if str(row['target_role'] or '').strip()]
    field_hint = max(set(fields), key=fields.count) if fields else ''
    role_hint = max(set(roles), key=roles.count) if roles else ''
    topic = _generate_gd_topic(field_hint, role_hint)

    conn.execute(
        """INSERT INTO gd_sessions (topic, room_id, status, thinking_end_at, discussion_end_at, feedback_deadline_at)
           VALUES (?, ?, 'active', datetime('now', '+2 minutes'), datetime('now', '+10 minutes'), datetime('now', '+30 minutes'))""",
        (topic, room_id)
    )
    session_id = conn.execute("SELECT last_insert_rowid() as id").fetchone()['id']

    for row in waiting_rows:
        conn.execute(
            """INSERT OR IGNORE INTO gd_participants (session_id, user_id, name, field, target_role)
               VALUES (?, ?, ?, ?, ?)""",
            (session_id, row['user_id'], row['name'], row['field'], row['target_role'])
        )
        conn.execute(
            """UPDATE gd_queue
               SET status = 'matched', session_id = ?, room_id = ?, matched_at = CURRENT_TIMESTAMP
               WHERE id = ?""",
            (session_id, room_id, row['id'])
        )

    return {'session_id': session_id, 'room_id': room_id, 'topic': topic}


def _update_gd_session_completion(conn, session_id):
    participants_count = conn.execute(
        "SELECT COUNT(*) as c FROM gd_participants WHERE session_id = ?",
        (session_id,)
    ).fetchone()['c']
    responses_count = conn.execute(
        "SELECT COUNT(*) as c FROM gd_responses WHERE session_id = ?",
        (session_id,)
    ).fetchone()['c']
    feedback_count = conn.execute(
        "SELECT COUNT(*) as c FROM gd_peer_feedback WHERE session_id = ?",
        (session_id,)
    ).fetchone()['c']

    expected_feedback = participants_count * max(0, participants_count - 1)
    if participants_count > 0 and responses_count >= participants_count and feedback_count >= expected_feedback:
        conn.execute(
            "UPDATE gd_sessions SET status = 'completed', completed_at = CURRENT_TIMESTAMP WHERE id = ?",
            (session_id,)
        )
        return True
    return False


def _fallback_gd_evaluation(topic, response, experience, peer_feedback):
    peer_text = ' '.join(
        [f"{item.get('pros', '')} {item.get('cons', '')}" for item in (peer_feedback or [])]
    ).lower()
    response_text = (response or '').lower()
    confidence = 7 if len(response_text) > 180 else 5
    communication = 7 if 'example' in response_text or 'because' in response_text else 6
    logical = 7 if any(x in response_text for x in ['therefore', 'however', 'first', 'second']) else 6
    participation = 'High' if len(response_text) > 220 else 'Moderate'

    strengths = []
    weaknesses = []
    if 'confidence' in peer_text or 'clear' in peer_text:
        strengths.append('Good confidence and clear speaking style.')
    if 'example' in response_text:
        strengths.append('Used examples to support arguments.')
    if not strengths:
        strengths.append('Maintained relevant points around the GD topic.')

    if 'repeat' in peer_text or 'repetition' in peer_text:
        weaknesses.append('Repetition was noticed in some arguments.')
    if len(response_text) < 120:
        weaknesses.append('Could add more structured depth to arguments.')
    if not weaknesses:
        weaknesses.append('Need stronger structure while presenting key points.')

    improvements = [
        'Start early with a clear opening framework (Point -> Reason -> Example).',
        'Use concise rebuttals and avoid repeating previous statements.',
        'Close with a balanced summary highlighting practical impact.'
    ]

    return {
        'confidence': confidence,
        'communication': communication,
        'logical_thinking': logical,
        'participation': participation,
        'strengths': strengths[:3],
        'weaknesses': weaknesses[:3],
        'improvements': improvements[:3],
        'final_feedback': 'You performed well overall. Improve argument structure and timing for stronger GD impact.'
    }


def _generate_gd_ai_evaluation(topic, response, experience, peer_feedback):
    peer_feedback_text = '\n'.join(
        [f"Pros: {item.get('pros', '')} | Cons: {item.get('cons', '')}" for item in (peer_feedback or [])]
    )
    prompt = [
        {
            'role': 'system',
            'content': 'You are an AI evaluator in a group discussion platform. Return strict JSON only.'
        },
        {
            'role': 'user',
            'content': (
                f'Topic: {topic}\n'
                f'Student Response: {response}\n'
                f'Student Experience: {experience}\n'
                f'Peer Feedback: {peer_feedback_text}\n\n'
                'Evaluate and return JSON in this structure:\n'
                '{'
                '"confidence":0,'
                '"communication":0,'
                '"logical_thinking":0,'
                '"participation":"High|Moderate|Low",'
                '"strengths":[],'
                '"weaknesses":[],'
                '"improvements":[],'
                '"final_feedback":"..."'
                '}'
            )
        }
    ]
    client = get_openai_client()
    completion = client.chat.completions.create(
        model=get_ai_model(),
        messages=prompt,
        temperature=0.4,
        max_tokens=700,
        response_format={'type': 'json_object'}
    )
    raw = (completion.choices[0].message.content or '').strip()
    parsed = json.loads(raw)

    def _normalize_list(value):
        if isinstance(value, list):
            return [str(v).strip() for v in value if str(v).strip()]
        if isinstance(value, str):
            parts = [part.strip() for part in re.split(r'[;\n,]+', value) if part.strip()]
            return parts
        return []

    return {
        'confidence': max(0, min(10, _safe_int(parsed.get('confidence'), 6))),
        'communication': max(0, min(10, _safe_int(parsed.get('communication'), 6))),
        'logical_thinking': max(0, min(10, _safe_int(parsed.get('logical_thinking'), 6))),
        'participation': str(parsed.get('participation') or 'Moderate').title(),
        'strengths': _normalize_list(parsed.get('strengths'))[:4],
        'weaknesses': _normalize_list(parsed.get('weaknesses'))[:4],
        'improvements': _normalize_list(parsed.get('improvements'))[:4],
        'final_feedback': str(parsed.get('final_feedback') or '').strip() or 'Good effort. Keep improving your GD structure.'
    }


def _get_or_create_gd_evaluation(conn, session_id, user_id, topic, response, experience, peer_feedback):
    existing = conn.execute(
        "SELECT evaluation_json FROM gd_ai_evaluations WHERE session_id = ? AND user_id = ?",
        (session_id, user_id)
    ).fetchone()
    if existing:
        try:
            return json.loads(existing['evaluation_json'])
        except Exception:
            pass

    try:
        evaluation = _generate_gd_ai_evaluation(topic, response, experience, peer_feedback)
        source = get_ai_provider()
    except Exception as e:
        print(f"GD AI evaluation fallback: {e}")
        evaluation = _fallback_gd_evaluation(topic, response, experience, peer_feedback)
        source = 'fallback'

    evaluation['source'] = source
    conn.execute(
        """INSERT INTO gd_ai_evaluations (session_id, user_id, evaluation_json)
           VALUES (?, ?, ?)
           ON CONFLICT(session_id, user_id)
           DO UPDATE SET evaluation_json = excluded.evaluation_json, created_at = CURRENT_TIMESTAMP""",
        (session_id, user_id, json.dumps(evaluation))
    )
    return evaluation


def _build_template_gd_feedback(member_name, topic, response, experience, peer_feedback_rows, message_count):
    """Create consistent per-member feedback text without AI generation."""
    response_text = str(response or '').strip()
    experience_text = str(experience or '').strip()
    response_words = len(re.findall(r'\w+', response_text))
    peer_rows = peer_feedback_rows or []
    peer_text_pros = ' '.join(str(item.get('pros') or '') for item in peer_rows).lower()
    peer_text_cons = ' '.join(str(item.get('cons') or '') for item in peer_rows).lower()

    activity_score = (message_count * 2) + min(8, response_words // 30)
    if activity_score >= 12:
        participation_band = 'High'
    elif activity_score >= 6:
        participation_band = 'Moderate'
    else:
        participation_band = 'Needs Improvement'

    strengths = []
    if 'confiden' in peer_text_pros:
        strengths.append('Showed visible confidence while sharing points.')
    if 'clear' in peer_text_pros or 'clarity' in peer_text_pros:
        strengths.append('Explained ideas clearly and stayed understandable.')
    if any(token in response_text.lower() for token in ['because', 'therefore', 'however', 'for example']):
        strengths.append('Used reasoning words to support arguments.')
    if response_words >= 90:
        strengths.append('Contributed enough depth to the GD discussion.')
    if not strengths:
        strengths.append('Stayed connected to the GD topic and participated sincerely.')

    improvements = []
    if any(token in peer_text_cons for token in ['repeat', 'repetition']):
        improvements.append('Avoid repeating the same point multiple times.')
    if any(token in peer_text_cons for token in ['interrupt', 'timing', 'late']):
        improvements.append('Improve speaking timing and entry into the discussion.')
    if response_words < 60:
        improvements.append('Add more structured points with one clear example each.')
    if 'structure' in peer_text_cons or 'flow' in peer_text_cons:
        improvements.append('Use a fixed structure: Point -> Reason -> Example.')
    if not improvements:
        improvements.append('Strengthen rebuttals by linking your point to practical outcomes.')

    next_steps = [
        f"Prepare a 30-second opening on '{topic}' before the next GD.",
        'Share at least one data-backed or real-world example in your first two turns.',
        'Close with a concise summary instead of adding new points at the end.'
    ]

    summary = (
        f"{member_name} had {participation_band.lower()} participation. "
        f"Strongest area: {strengths[0]} "
        f"Primary improvement focus: {improvements[0]}"
    )
    if experience_text:
        summary += f" Self-reflection noted: {experience_text[:120]}"

    return {
        'participation_band': participation_band,
        'strengths': strengths[:3],
        'improvements': improvements[:3],
        'next_steps': next_steps,
        'summary': summary
    }


def _extract_gd_room_id(value):
    """Extract GD room id from plain code or URL."""
    text = str(value or '').strip()
    if not text:
        return ''
    code_match = re.search(r'(GD-\d{14}-\d{3})', text, flags=re.IGNORECASE)
    if code_match:
        return code_match.group(1).upper()
    try:
        parsed = urlparse(text)
        path = parsed.path or ''
        url_match = re.search(r'/gd/connect/(GD-\d{14}-\d{3})', path, flags=re.IGNORECASE)
        if url_match:
            return url_match.group(1).upper()
    except Exception:
        pass
    return ''


def _get_pending_gd_stop_request(conn, session_id, viewer_user_id=None):
    row = conn.execute(
        """SELECT sr.*,
                  u.username AS requester_name,
                  (SELECT COUNT(*) FROM gd_stop_votes sv WHERE sv.stop_request_id = sr.id AND sv.vote = 'approve') AS approvals,
                  (SELECT COUNT(*) FROM gd_stop_votes sv WHERE sv.stop_request_id = sr.id AND sv.vote = 'reject') AS rejects
           FROM gd_stop_requests sr
           JOIN users u ON u.id = sr.requested_by
           WHERE sr.session_id = ? AND sr.status = 'pending'
           ORDER BY sr.id DESC
           LIMIT 1""",
        (session_id,)
    ).fetchone()
    if not row:
        return None
    data = dict(row)
    if viewer_user_id:
        my_vote_row = conn.execute(
            "SELECT vote FROM gd_stop_votes WHERE stop_request_id = ? AND user_id = ?",
            (row['id'], viewer_user_id)
        ).fetchone()
        data['my_vote'] = my_vote_row['vote'] if my_vote_row else None
    else:
        data['my_vote'] = None
    return data

# ==================== SKILL SAATHI MODULE ====================
@app.route('/skill')
@login_required
def skill_home():
    """Skill Saathi homepage"""
    try:
        conn = get_db_connection()
        
        count = conn.execute('SELECT COUNT(*) as count FROM learning_resources').fetchone()['count']
        
        if count == 0:
            conn.close()
            return """
            <div style="text-align: center; padding: 50px;">
                <h2>No resources available</h2>
                <p>Please run: <code>python database/load_csv_to_db.py</code></p>
                <a href="/" style="padding: 10px 20px; background: #667eea; color: white; text-decoration: none; border-radius: 5px;">Back to Home</a>
            </div>
            """, 500
        
        total_resources = conn.execute('SELECT COUNT(*) as count FROM learning_resources').fetchone()['count']
        topics = conn.execute('SELECT DISTINCT topic FROM learning_resources ORDER BY topic').fetchall()
        platforms = conn.execute('SELECT DISTINCT platform FROM learning_resources ORDER BY platform').fetchall()
        languages = conn.execute('SELECT DISTINCT language FROM learning_resources ORDER BY language').fetchall()
        resource_types = conn.execute('SELECT DISTINCT resource_type FROM learning_resources ORDER BY resource_type').fetchall()
        resources = conn.execute('SELECT * FROM learning_resources ORDER BY quality_score DESC').fetchall()
        
        conn.close()
        
        topic_list = [row['topic'] for row in topics]
        platform_list = [row['platform'] for row in platforms]
        language_list = [row['language'] for row in languages]
        resource_type_list = [row['resource_type'] for row in resource_types]
        resource_list = [dict(row) for row in resources]
        
        return render_template('skill/browse.html', 
                             topics=topic_list,
                             platforms=platform_list,
                             languages=language_list,
                             resource_types=resource_type_list,
                             resources=resource_list,
                             total_resources=total_resources,
                             selected_topic='all',
                             selected_difficulty='all',
                             selected_platform='all',
                             selected_language='all',
                             selected_resource_type='all',
                             free_only=False,
                             search='')
                             
    except Exception as e:
        print(f"Skill home error: {e}")
        return f"<h2>Error: {e}</h2><a href='/'>Back to Home</a>", 500


@app.route('/skill/aptitude-quiz')
@login_required
def skill_aptitude_quiz():
    """Daily aptitude quiz with topic and random mode."""
    try:
        selected_topic = (request.args.get('topic') or 'Random').strip()
        topics = ['Random'] + list(APTITUDE_QUESTION_BANK.keys())
        if selected_topic not in topics:
            selected_topic = 'Random'

        log_activity(
            'page_view',
            'skill',
            'Opened aptitude quiz page',
            f"topic: {selected_topic}"
        )

        return render_template(
            'skill/aptitude_quiz.html',
            topics=topics,
            selected_topic=selected_topic,
            date_key=datetime.now().strftime('%Y-%m-%d'),
            user_id=g.current_user['id']
        )
    except Exception as e:
        print(f"Aptitude quiz page error: {e}")
        return f"Error: {e}", 500


@app.route('/skill/aptitude-quiz/generate', methods=['POST'])
@login_required
def generate_aptitude_quiz():
    """Generate real-time aptitude quiz using Gemini/OpenAI-compatible AI with daily caching."""
    try:
        data = request.get_json(silent=True) or {}
        topic = str(data.get('topic') or 'Random').strip()
        mode = str(data.get('mode') or 'daily').strip().lower()
        if mode not in ('daily', 'random'):
            mode = 'daily'

        topics = ['Random'] + list(APTITUDE_QUESTION_BANK.keys())
        if topic not in topics:
            topic = 'Random'

        user_id = g.current_user['id']
        today = datetime.now().strftime('%Y-%m-%d')

        if mode == 'daily':
            conn = get_db_connection()
            cached = conn.execute(
                '''SELECT questions_json, source
                   FROM daily_aptitude_quizzes
                   WHERE user_id = ? AND quiz_date = ? AND topic = ? AND mode = 'daily'
                   LIMIT 1''',
                (user_id, today, topic)
            ).fetchone()
            conn.close()

            if cached:
                try:
                    cached_questions = json.loads(cached['questions_json'])
                    if isinstance(cached_questions, list) and len(cached_questions) >= 10:
                        return jsonify({
                            'success': True,
                            'questions': cached_questions,
                            'topic': topic,
                            'mode': mode,
                            'source': 'cache',
                            'notice': 'Loaded your saved daily quiz for today.'
                        })
                except Exception:
                    pass

        source = get_ai_provider()
        notice = ''
        try:
            questions, source = _generate_aptitude_questions(
                topic=topic,
                user_id=user_id,
                mode=mode,
                question_count=10
            )
        except Exception as generation_error:
            print(f"Aptitude quiz AI generation failed for all configured providers: {generation_error}")
            questions = _fallback_aptitude_questions(topic=topic, user_id=user_id, mode=mode, question_count=10)
            source = 'fallback'
            notice = 'AI quiz is temporarily unavailable, so a backup quiz is shown.'

        if mode == 'daily' and source != 'fallback':
            conn = get_db_connection()
            conn.execute(
                '''INSERT INTO daily_aptitude_quizzes (user_id, quiz_date, topic, mode, questions_json, source)
                   VALUES (?, ?, ?, 'daily', ?, ?)
                   ON CONFLICT(user_id, quiz_date, topic, mode)
                   DO UPDATE SET questions_json = excluded.questions_json, source = excluded.source, created_at = CURRENT_TIMESTAMP''',
                (user_id, today, topic, json.dumps(questions), source)
            )
            conn.commit()
            conn.close()

        log_activity(
            'aptitude_quiz_generated',
            'skill',
            'Generated aptitude quiz',
            f"topic={topic}; mode={mode}; source={source}"
        )

        return jsonify({
            'success': True,
            'questions': questions,
            'topic': topic,
            'mode': mode,
            'source': source,
            'notice': notice
        })
    except Exception as e:
        print(f"Aptitude quiz generation route error: {e}")
        return jsonify({'success': False, 'error': 'Unable to generate quiz right now.'}), 500


@app.route('/skill/aptitude-quiz/submit', methods=['POST'])
@login_required
def submit_aptitude_quiz():
    """Store quiz completion summary for analytics and notifications."""
    try:
        data = request.get_json(silent=True) or {}
        score = _safe_int(data.get('score'), 0)
        total_questions = max(1, _safe_int(data.get('total_questions'), 10))
        time_taken_seconds = max(0, _safe_int(data.get('time_taken_seconds'), 0))
        topic = str(data.get('topic') or 'Random')
        mode = str(data.get('mode') or 'daily')
        source = str(data.get('source') or get_ai_provider())
        topic_breakdown = data.get('topic_breakdown') if isinstance(data.get('topic_breakdown'), dict) else {}

        accuracy = round((score / total_questions) * 100, 2)
        quiz_summary = {
            'topic': topic,
            'mode': mode,
            'source': source,
            'score': score,
            'total_questions': total_questions,
            'accuracy_percent': accuracy,
            'time_taken_seconds': time_taken_seconds,
            'topic_breakdown': topic_breakdown
        }

        log_activity(
            'aptitude_quiz_completed',
            'skill',
            'Completed aptitude quiz',
            json.dumps(quiz_summary)
        )

        return jsonify({'success': True, 'accuracy': accuracy})
    except Exception as e:
        print(f"Aptitude quiz submit error: {e}")
        return jsonify({'success': False, 'error': 'Unable to save quiz result.'}), 500


@app.route('/skill/browse')
@login_required
def skill_browse():
    """Browse learning resources with filters"""
    try:
        topic = request.args.get('topic', 'all')
        difficulty = request.args.get('difficulty', 'all')
        platform = request.args.get('platform', 'all')
        resource_type = request.args.get('resource_type', 'all')
        language = request.args.get('language', 'all')
        free_only = request.args.get('free', 'false') == 'true'
        search = request.args.get('search', '').strip()
        
        conn = get_db_connection()
        total_resources = conn.execute('SELECT COUNT(*) as count FROM learning_resources').fetchone()['count']
        
        query = 'SELECT * FROM learning_resources WHERE 1=1'
        params = []
        
        if topic != 'all':
            query += ' AND topic = ?'
            params.append(topic)
        
        if difficulty != 'all':
            query += ' AND difficulty = ?'
            params.append(difficulty)
        
        if platform != 'all':
            query += ' AND platform = ?'
            params.append(platform)
        
        if resource_type != 'all':
            query += ' AND resource_type = ?'
            params.append(resource_type)
        
        if language != 'all':
            query += ' AND language = ?'
            params.append(language)
        
        if free_only:
            query += ' AND is_free = 1'
        
        if search:
            search_term = f"%{search}%"
            query += ' AND (title LIKE ? OR topic LIKE ? OR platform LIKE ? OR resource_type LIKE ? OR difficulty LIKE ? OR language LIKE ? OR url LIKE ?)'
            params.extend([search_term] * 7)
        
        query += ' ORDER BY quality_score DESC'
        
        resources = conn.execute(query, params).fetchall()
        topics = conn.execute('SELECT DISTINCT topic FROM learning_resources ORDER BY topic').fetchall()
        platforms = conn.execute('SELECT DISTINCT platform FROM learning_resources ORDER BY platform').fetchall()
        languages = conn.execute('SELECT DISTINCT language FROM learning_resources ORDER BY language').fetchall()
        resource_types = conn.execute('SELECT DISTINCT resource_type FROM learning_resources ORDER BY resource_type').fetchall()
        
        conn.close()
        
        resource_list = [dict(row) for row in resources]
        topic_list = [row['topic'] for row in topics]
        platform_list = [row['platform'] for row in platforms]
        language_list = [row['language'] for row in languages]
        resource_type_list = [row['resource_type'] for row in resource_types]
        
        # Log skill browsing activity
        filters = []
        if topic != 'all':
            filters.append(f"topic: {topic}")
        if difficulty != 'all':
            filters.append(f"difficulty: {difficulty}")
        if platform != 'all':
            filters.append(f"platform: {platform}")
        if resource_type != 'all':
            filters.append(f"resource type: {resource_type}")
        if language != 'all':
            filters.append(f"language: {language}")
        if free_only:
            filters.append("free only")
        if search:
            filters.append(f"search: {search}")
        
        filter_desc = ", ".join(filters) if filters else "no filters"
        log_activity('skill_browse', 'skill', f'Browsed learning resources ({filter_desc})', 
                    f"Found {len(resource_list)} resources")
        
        return render_template('skill/browse.html',
                             resources=resource_list,
                             total_resources=total_resources,
                             topics=topic_list,
                             platforms=platform_list,
                             languages=language_list,
                             resource_types=resource_type_list,
                             selected_topic=topic,
                             selected_difficulty=difficulty,
                             selected_platform=platform,
                             selected_language=language,
                             selected_resource_type=resource_type,
                             free_only=free_only,
                             search=search)
    except Exception as e:
        print(f"Skill browse error: {e}")
        return f"Error: {e}", 500

# ==================== STUDENT GD CONNECT MODULE ====================
@app.route('/gd')
@login_required
def gd_home():
    """Student-managed GD home using Student Community connections."""
    try:
        user_id = g.current_user['id']
        conn = get_db_connection()

        connections = conn.execute(
            '''SELECT CASE WHEN sc.requester_id = ? THEN sc.addressee_id ELSE sc.requester_id END AS user_id,
                      u.username
               FROM student_connections sc
               JOIN users u ON u.id = CASE WHEN sc.requester_id = ? THEN sc.addressee_id ELSE sc.requester_id END
               WHERE sc.status = 'accepted'
                 AND (sc.requester_id = ? OR sc.addressee_id = ?)
               ORDER BY u.username COLLATE NOCASE''',
            (user_id, user_id, user_id, user_id)
        ).fetchall()

        pending_invites = conn.execute(
            '''SELECT gi.id, gi.session_id, gi.created_at,
                      gs.topic, gs.room_id, gs.duration_minutes, gs.max_participants, gs.status AS session_status,
                      u.username AS host_name,
                      (SELECT COUNT(*) FROM gd_participants gp WHERE gp.session_id = gs.id AND gp.status = 'accepted') AS joined_count
               FROM gd_invites gi
               JOIN gd_sessions gs ON gs.id = gi.session_id
               JOIN users u ON u.id = gi.from_user
               WHERE gi.to_user = ? AND gi.status = 'pending'
                 AND gs.status IN ('planning', 'active')
               ORDER BY gi.created_at DESC''',
            (user_id,)
        ).fetchall()

        incoming_join_requests = conn.execute(
            '''SELECT jr.id, jr.requester_user_id, jr.requester_name, jr.field, jr.target_role, jr.created_at,
                      gs.id AS session_id, gs.room_id, gs.topic, gs.max_participants,
                      (SELECT COUNT(*) FROM gd_participants gp WHERE gp.session_id = gs.id AND gp.status = 'accepted') AS joined_count
               FROM gd_join_requests jr
               JOIN gd_sessions gs ON gs.id = jr.session_id
               WHERE gs.host_user_id = ? AND jr.status = 'pending'
                 AND gs.status IN ('planning', 'active')
               ORDER BY jr.created_at DESC''',
            (user_id,)
        ).fetchall()

        my_sessions_raw = conn.execute(
            '''SELECT DISTINCT gs.*,
                      gp.role AS my_role,
                      (SELECT COUNT(*) FROM gd_participants p2 WHERE p2.session_id = gs.id AND p2.status = 'accepted') AS joined_count
               FROM gd_sessions gs
               JOIN gd_participants gp ON gp.session_id = gs.id
               WHERE gp.user_id = ? AND gp.status = 'accepted'
                 AND gs.status IN ('planning', 'active', 'feedback')
               ORDER BY gs.created_at DESC''',
            (user_id,)
        ).fetchall()

        my_sessions = []
        for row in my_sessions_raw:
            synced = _sync_gd_session_status(conn, row)
            phase, remaining_seconds = _calculate_gd_phase(synced)
            if not synced:
                continue
            item = dict(synced)
            item['phase'] = phase
            item['remaining_seconds'] = remaining_seconds
            item['my_role'] = row['my_role']
            item['joined_count'] = row['joined_count']
            my_sessions.append(item)

        conn.commit()
        conn.close()
        return render_template(
            'gd/home.html',
            connections=[dict(r) for r in connections],
            pending_invites=[dict(r) for r in pending_invites],
            incoming_join_requests=[dict(r) for r in incoming_join_requests],
            my_sessions=my_sessions
        )
    except Exception as e:
        print(f"GD home error: {e}")
        return f"Error: {e}", 500


@app.route('/gd/join', methods=['POST'])
@login_required
def gd_join_queue():
    """Create a student-managed GD meeting and invite selected connections."""
    try:
        user_id = g.current_user['id']
        name = _sanitize_text(request.form.get('name') or g.current_user.get('username') or 'Student', 80)
        field = _sanitize_text(request.form.get('field') or '', 80)
        target_role = _sanitize_text(request.form.get('target_role') or '', 80)
        duration_minutes = max(5, min(90, _safe_int(request.form.get('duration_minutes'), 12)))
        max_participants = max(2, min(60, _safe_int(request.form.get('max_participants'), 5)))
        topic = _sanitize_text(request.form.get('topic') or '', 180)

        invitee_ids_raw = request.form.getlist('invitee_ids')
        invitee_ids = []
        for raw in invitee_ids_raw:
            invitee_id = _safe_int(raw, 0)
            if invitee_id > 0 and invitee_id != user_id and invitee_id not in invitee_ids:
                invitee_ids.append(invitee_id)

        conn = get_db_connection()
        if not topic:
            topic = _generate_gd_topic(field, target_role)

        # Keep only accepted community connections for invitations.
        valid_invitees = []
        for invitee_id in invitee_ids:
            row = conn.execute(
                '''SELECT 1 FROM student_connections
                   WHERE status = 'accepted'
                     AND ((requester_id = ? AND addressee_id = ?)
                       OR (requester_id = ? AND addressee_id = ?))
                   LIMIT 1''',
                (user_id, invitee_id, invitee_id, user_id)
            ).fetchone()
            if row:
                valid_invitees.append(invitee_id)
        valid_invitees = valid_invitees[:max(0, max_participants - 1)]

        room_id = _build_gd_room_id()
        conn.execute(
            '''INSERT INTO gd_sessions
               (topic, room_id, status, host_user_id, max_participants, duration_minutes)
               VALUES (?, ?, 'planning', ?, ?, ?)''',
            (topic, room_id, user_id, max_participants, duration_minutes)
        )
        session_id = conn.execute('SELECT last_insert_rowid() AS id').fetchone()['id']

        conn.execute(
            '''INSERT INTO gd_participants
               (session_id, user_id, name, field, target_role, status, role)
               VALUES (?, ?, ?, ?, ?, 'accepted', 'host')''',
            (session_id, user_id, name, field, target_role)
        )

        for invitee_id in valid_invitees:
            conn.execute(
                '''INSERT INTO gd_invites (session_id, from_user, to_user, status)
                   VALUES (?, ?, ?, 'pending')
                   ON CONFLICT(session_id, to_user)
                   DO UPDATE SET status = 'pending', updated_at = CURRENT_TIMESTAMP''',
                (session_id, user_id, invitee_id)
            )

        conn.commit()
        conn.close()
        log_activity('gd_meeting_created', 'gd', 'Created student-managed GD meeting', f'room_id={room_id}; invites={len(valid_invitees)}')
        return redirect(url_for('gd_room', room_id=room_id))
    except Exception as e:
        print(f"GD create meeting error: {e}")
        flash('Unable to create GD meeting right now. Please try again.', 'error')
        return redirect(url_for('gd_home'))


@app.route('/gd/connect', methods=['POST'])
@login_required
def gd_connect_quick():
    """Quick join by room code or shared connection link."""
    room_input = request.form.get('room_input') or ''
    room_id = _extract_gd_room_id(room_input)
    if not room_id:
        flash('Please enter a valid GD room code or share link.', 'warning')
        return redirect(url_for('gd_home'))
    return redirect(url_for('gd_connect_link', room_id=room_id))


@app.route('/gd/create', methods=['POST'])
@login_required
def gd_create():
    """Alias for GD meeting creation endpoint."""
    return gd_join_queue()


@app.route('/gd/invite/respond', methods=['POST'])
@login_required
def gd_invite_respond():
    """Accept/reject invite and capture participant details."""
    try:
        user_id = g.current_user['id']
        invite_id = _safe_int(request.form.get('invite_id'), 0)
        action = (request.form.get('action') or 'accept').strip().lower()
        field = _sanitize_text(request.form.get('field') or '', 80)
        target_role = _sanitize_text(request.form.get('target_role') or '', 80)
        if action not in ('accept', 'reject'):
            action = 'accept'

        conn = get_db_connection()
        invite = conn.execute(
            "SELECT * FROM gd_invites WHERE id = ? AND to_user = ?",
            (invite_id, user_id)
        ).fetchone()
        if not invite:
            conn.close()
            flash('Invite not found.', 'warning')
            return redirect(url_for('gd_home'))

        session_row = conn.execute("SELECT * FROM gd_sessions WHERE id = ?", (invite['session_id'],)).fetchone()
        if not session_row:
            conn.close()
            flash('Meeting no longer exists.', 'warning')
            return redirect(url_for('gd_home'))

        session_row = _sync_gd_session_status(conn, session_row)
        if session_row['status'] not in ('planning', 'active'):
            conn.execute("UPDATE gd_invites SET status = 'cancelled', updated_at = CURRENT_TIMESTAMP WHERE id = ?", (invite_id,))
            conn.commit()
            conn.close()
            flash('This GD meeting is no longer accepting participants.', 'warning')
            return redirect(url_for('gd_home'))
        if action == 'reject':
            conn.execute("UPDATE gd_invites SET status = 'rejected', updated_at = CURRENT_TIMESTAMP WHERE id = ?", (invite_id,))
            conn.commit()
            conn.close()
            flash('Invite rejected.', 'info')
            return redirect(url_for('gd_home'))

        accepted_count = conn.execute(
            "SELECT COUNT(*) as c FROM gd_participants WHERE session_id = ? AND status = 'accepted'",
            (session_row['id'],)
        ).fetchone()['c']
        max_participants = max(2, _safe_int(session_row['max_participants'], 5))
        if accepted_count >= max_participants:
            conn.execute("UPDATE gd_invites SET status = 'cancelled', updated_at = CURRENT_TIMESTAMP WHERE id = ?", (invite_id,))
            conn.commit()
            conn.close()
            flash('This GD room is full.', 'warning')
            return redirect(url_for('gd_home'))

        user_row = conn.execute("SELECT username FROM users WHERE id = ?", (user_id,)).fetchone()
        name = _sanitize_text((user_row['username'] if user_row else 'Student'), 80)
        conn.execute(
            '''INSERT OR IGNORE INTO gd_participants
               (session_id, user_id, name, field, target_role, status, role)
               VALUES (?, ?, ?, ?, ?, 'accepted', 'participant')''',
            (session_row['id'], user_id, name, field, target_role)
        )
        conn.execute("UPDATE gd_invites SET status = 'accepted', updated_at = CURRENT_TIMESTAMP WHERE id = ?", (invite_id,))
        conn.commit()
        conn.close()
        return redirect(url_for('gd_room', room_id=session_row['room_id']))
    except Exception as e:
        print(f"GD invite respond error: {e}")
        flash('Unable to process invite right now.', 'error')
        return redirect(url_for('gd_home'))


@app.route('/gd/connect/<room_id>', methods=['GET', 'POST'])
@login_required
def gd_connect_link(room_id):
    """Join-by-link page for registered students to request access to a GD room."""
    try:
        user_id = g.current_user['id']
        conn = get_db_connection()
        session_row = conn.execute("SELECT * FROM gd_sessions WHERE room_id = ?", (room_id,)).fetchone()
        if not session_row:
            conn.close()
            return "GD room not found", 404

        session_row = _sync_gd_session_status(conn, session_row)
        if session_row['status'] not in ('planning', 'active'):
            conn.close()
            flash('This GD session is closed for new join requests.', 'warning')
            return redirect(url_for('gd_home'))

        existing_participant = conn.execute(
            "SELECT 1 FROM gd_participants WHERE session_id = ? AND user_id = ? AND status = 'accepted'",
            (session_row['id'], user_id)
        ).fetchone()
        if existing_participant:
            conn.close()
            return redirect(url_for('gd_room', room_id=room_id))

        joined_count = conn.execute(
            "SELECT COUNT(*) AS c FROM gd_participants WHERE session_id = ? AND status = 'accepted'",
            (session_row['id'],)
        ).fetchone()['c']
        max_participants = max(2, _safe_int(session_row['max_participants'], 5))
        host_user = conn.execute("SELECT username FROM users WHERE id = ?", (session_row['host_user_id'],)).fetchone()
        request_row = conn.execute(
            "SELECT * FROM gd_join_requests WHERE session_id = ? AND requester_user_id = ?",
            (session_row['id'], user_id)
        ).fetchone()

        if request.method == 'POST':
            if joined_count >= max_participants:
                conn.close()
                flash('This GD room is full right now.', 'warning')
                return redirect(url_for('gd_home'))

            field = _sanitize_text(request.form.get('field') or '', 80)
            target_role = _sanitize_text(request.form.get('target_role') or '', 80)
            name = _sanitize_text(g.current_user.get('username') or 'Student', 80)
            conn.execute(
                """INSERT INTO gd_join_requests (session_id, requester_user_id, requester_name, field, target_role, status)
                   VALUES (?, ?, ?, ?, ?, 'pending')
                   ON CONFLICT(session_id, requester_user_id)
                   DO UPDATE SET requester_name = excluded.requester_name,
                                 field = excluded.field,
                                 target_role = excluded.target_role,
                                 status = 'pending',
                                 updated_at = CURRENT_TIMESTAMP""",
                (session_row['id'], user_id, name, field, target_role)
            )
            conn.commit()
            request_row = conn.execute(
                "SELECT * FROM gd_join_requests WHERE session_id = ? AND requester_user_id = ?",
                (session_row['id'], user_id)
            ).fetchone()
            flash('Join request sent. You will get an update in notifications and GD page.', 'success')

        conn.close()
        return render_template(
            'gd/waiting.html',
            session=dict(session_row),
            host_name=(host_user['username'] if host_user else 'Host'),
            joined_count=joined_count,
            max_participants=max_participants,
            request_status=(request_row['status'] if request_row else None)
        )
    except Exception as e:
        print(f"GD connect link error: {e}")
        return f"Error: {e}", 500


@app.route('/gd/connect-status/<room_id>')
@login_required
def gd_connect_status(room_id):
    """Polling endpoint for quick join request status."""
    try:
        user_id = g.current_user['id']
        conn = get_db_connection()
        session_row = conn.execute("SELECT * FROM gd_sessions WHERE room_id = ?", (room_id,)).fetchone()
        if not session_row:
            conn.close()
            return jsonify({'success': False, 'error': 'Room not found'}), 404

        session_row = _sync_gd_session_status(conn, session_row)
        if session_row['status'] not in ('planning', 'active'):
            conn.close()
            return jsonify({'success': True, 'status': 'closed'})

        joined_count = conn.execute(
            "SELECT COUNT(*) AS c FROM gd_participants WHERE session_id = ? AND status = 'accepted'",
            (session_row['id'],)
        ).fetchone()['c']

        participant = conn.execute(
            "SELECT 1 FROM gd_participants WHERE session_id = ? AND user_id = ? AND status = 'accepted'",
            (session_row['id'], user_id)
        ).fetchone()
        if participant:
            conn.close()
            return jsonify({
                'success': True,
                'status': 'approved',
                'joined_count': joined_count,
                'room_url': url_for('gd_room', room_id=room_id)
            })

        req = conn.execute(
            "SELECT status FROM gd_join_requests WHERE session_id = ? AND requester_user_id = ?",
            (session_row['id'], user_id)
        ).fetchone()
        conn.close()
        return jsonify({
            'success': True,
            'status': (req['status'] if req else 'none'),
            'joined_count': joined_count
        })
    except Exception as e:
        print(f"GD connect status error: {e}")
        return jsonify({'success': False, 'error': 'Unable to fetch request status.'}), 500


@app.route('/gd/join-request/respond', methods=['POST'])
@login_required
def gd_join_request_respond():
    """Host approves or rejects join requests coming from shared room links."""
    try:
        user_id = g.current_user['id']
        request_id = _safe_int(request.form.get('request_id'), 0)
        action = (request.form.get('action') or 'approve').strip().lower()
        if action not in ('approve', 'reject'):
            action = 'approve'

        conn = get_db_connection()
        req = conn.execute("SELECT * FROM gd_join_requests WHERE id = ?", (request_id,)).fetchone()
        if not req:
            conn.close()
            flash('Join request not found.', 'warning')
            return redirect(url_for('gd_home'))

        session_row = conn.execute("SELECT * FROM gd_sessions WHERE id = ?", (req['session_id'],)).fetchone()
        if not session_row or session_row['host_user_id'] != user_id:
            conn.close()
            flash('You are not allowed to manage this request.', 'error')
            return redirect(url_for('gd_home'))

        session_row = _sync_gd_session_status(conn, session_row)
        if session_row['status'] not in ('planning', 'active'):
            conn.execute("UPDATE gd_join_requests SET status = 'cancelled', updated_at = CURRENT_TIMESTAMP WHERE id = ?", (request_id,))
            conn.commit()
            conn.close()
            flash('Meeting is closed for new participants.', 'warning')
            return redirect(url_for('gd_home'))

        if action == 'reject':
            conn.execute("UPDATE gd_join_requests SET status = 'rejected', updated_at = CURRENT_TIMESTAMP WHERE id = ?", (request_id,))
            conn.commit()
            conn.close()
            flash('Join request rejected.', 'info')
            return redirect(url_for('gd_home'))

        accepted_count = conn.execute(
            "SELECT COUNT(*) as c FROM gd_participants WHERE session_id = ? AND status = 'accepted'",
            (session_row['id'],)
        ).fetchone()['c']
        max_participants = max(2, _safe_int(session_row['max_participants'], 5))
        if accepted_count >= max_participants:
            conn.execute("UPDATE gd_join_requests SET status = 'cancelled', updated_at = CURRENT_TIMESTAMP WHERE id = ?", (request_id,))
            conn.commit()
            conn.close()
            flash('Cannot approve. Room is full.', 'warning')
            return redirect(url_for('gd_home'))

        conn.execute(
            """INSERT OR IGNORE INTO gd_participants
               (session_id, user_id, name, field, target_role, status, role)
               VALUES (?, ?, ?, ?, ?, 'accepted', 'participant')""",
            (session_row['id'], req['requester_user_id'], req['requester_name'], req['field'], req['target_role'])
        )
        conn.execute("UPDATE gd_join_requests SET status = 'approved', updated_at = CURRENT_TIMESTAMP WHERE id = ?", (request_id,))
        conn.commit()
        conn.close()
        flash('Join request approved.', 'success')
        return redirect(url_for('gd_home'))
    except Exception as e:
        print(f"GD join request respond error: {e}")
        flash('Unable to process join request.', 'error')
        return redirect(url_for('gd_home'))


@app.route('/gd/waiting')
@login_required
def gd_waiting_room():
    """Legacy waiting endpoint kept for compatibility."""
    return redirect(url_for('gd_home'))


@app.route('/gd/waiting-status')
@login_required
def gd_waiting_status():
    """Legacy waiting status endpoint kept for compatibility."""
    return jsonify({'success': True, 'status': 'managed'})


@app.route('/gd/room/<room_id>')
@login_required
def gd_room(room_id):
    """Live GD room with student-managed timer and WebRTC signaling."""
    try:
        user_id = g.current_user['id']
        conn = get_db_connection()
        session_row = conn.execute(
            "SELECT * FROM gd_sessions WHERE room_id = ?",
            (room_id,)
        ).fetchone()
        if not session_row:
            conn.close()
            return "GD room not found", 404

        participant = conn.execute(
            "SELECT * FROM gd_participants WHERE session_id = ? AND user_id = ?",
            (session_row['id'], user_id)
        ).fetchone()
        if not participant or participant['status'] != 'accepted':
            session_row = _sync_gd_session_status(conn, session_row)
            conn.close()
            if session_row and session_row['status'] in ('planning', 'active'):
                return redirect(url_for('gd_connect_link', room_id=room_id))
            return "You are not part of this GD room.", 403

        session_row = _sync_gd_session_status(conn, session_row)
        conn.commit()
        phase, remaining_seconds = _calculate_gd_phase(session_row)

        if phase == 'completed':
            conn.close()
            return redirect(url_for('gd_result', room_id=room_id))
        if phase == 'feedback':
            conn.close()
            return redirect(url_for('gd_feedback', room_id=room_id))

        participants = conn.execute(
            """SELECT user_id, name, field, target_role, role
               FROM gd_participants
               WHERE session_id = ? AND status = 'accepted'
               ORDER BY joined_at ASC""",
            (session_row['id'],)
        ).fetchall()
        messages = conn.execute(
            """SELECT m.id, m.message, m.created_at, p.name
               FROM gd_messages m
               JOIN gd_participants p ON p.session_id = m.session_id AND p.user_id = m.user_id
               WHERE m.session_id = ?
               ORDER BY m.id DESC LIMIT 40""",
            (session_row['id'],)
        ).fetchall()
        joined_count = len(participants)
        max_participants = max(2, _safe_int(session_row['max_participants'], 5))
        is_host = bool(session_row['host_user_id'] == user_id or participant['role'] == 'host')
        can_start_timer = is_host and phase == 'lobby' and joined_count >= 2
        can_stop_timer = is_host and phase == 'discussion'
        pending_stop_request = _get_pending_gd_stop_request(conn, session_row['id'], user_id)
        share_join_link = request.url_root.rstrip('/') + url_for('gd_connect_link', room_id=room_id)
        conn.close()

        return render_template(
            'gd/room.html',
            session=dict(session_row),
            participants=[dict(p) for p in participants],
            messages=[dict(m) for m in reversed(messages)],
            phase=phase,
            remaining_seconds=remaining_seconds,
            current_user_id=user_id,
            current_user_name=g.current_user.get('username', 'Student'),
            is_host=is_host,
            can_start_timer=can_start_timer,
            can_stop_timer=can_stop_timer,
            joined_count=joined_count,
            max_participants=max_participants,
            pending_stop_request=pending_stop_request,
            share_join_link=share_join_link
        )
    except Exception as e:
        print(f"GD room error: {e}")
        return f"Error: {e}", 500


@app.route('/gd/room/<room_id>/state')
@login_required
def gd_room_state(room_id):
    """Polling endpoint for room phase, timer and participants."""
    try:
        user_id = g.current_user['id']
        conn = get_db_connection()
        session_row = conn.execute("SELECT * FROM gd_sessions WHERE room_id = ?", (room_id,)).fetchone()
        if not session_row:
            conn.close()
            return jsonify({'success': False, 'error': 'Room not found'}), 404

        participant = conn.execute(
            "SELECT * FROM gd_participants WHERE session_id = ? AND user_id = ?",
            (session_row['id'], user_id)
        ).fetchone()
        if not participant or participant['status'] != 'accepted':
            conn.close()
            return jsonify({'success': False, 'error': 'Not authorized'}), 403

        session_row = _sync_gd_session_status(conn, session_row)
        participants = conn.execute(
            """SELECT user_id, name, field, target_role, role
               FROM gd_participants
               WHERE session_id = ? AND status = 'accepted'
               ORDER BY joined_at ASC""",
            (session_row['id'],)
        ).fetchall()
        joined_count = len(participants)
        max_participants = max(2, _safe_int(session_row['max_participants'], 5))
        pending_stop_request = _get_pending_gd_stop_request(conn, session_row['id'], user_id)
        is_host = bool(session_row['host_user_id'] == user_id or participant['role'] == 'host')
        conn.commit()
        phase, remaining_seconds = _calculate_gd_phase(session_row)
        conn.close()

        payload = {
            'success': True,
            'status': session_row['status'],
            'phase': phase,
            'remaining_seconds': remaining_seconds,
            'topic': session_row['topic'],
            'max_participants': max_participants,
            'joined_count': joined_count,
            'duration_minutes': _safe_int(session_row['duration_minutes'], 10),
            'participants': [dict(p) for p in participants],
            'can_start_timer': is_host and phase == 'lobby' and joined_count >= 2,
            'can_stop_timer': is_host and phase == 'discussion',
            'is_host': is_host,
            'stop_request': pending_stop_request
        }
        if phase == 'feedback':
            payload['redirect_url'] = url_for('gd_feedback', room_id=room_id)
        if phase == 'completed':
            payload['redirect_url'] = url_for('gd_result', room_id=room_id)
        return jsonify(payload)
    except Exception as e:
        print(f"GD room state error: {e}")
        return jsonify({'success': False, 'error': 'Unable to load room state'}), 500


@app.route('/gd/room/<room_id>/timer/start', methods=['POST'])
@login_required
def gd_start_timer(room_id):
    """Start discussion timer manually by host only."""
    try:
        user_id = g.current_user['id']
        data = request.get_json(silent=True) or {}
        requested_duration = _safe_int(data.get('duration_minutes'), 0)

        conn = get_db_connection()
        session_row = conn.execute("SELECT * FROM gd_sessions WHERE room_id = ?", (room_id,)).fetchone()
        if not session_row:
            conn.close()
            return jsonify({'success': False, 'error': 'Room not found'}), 404

        participant = conn.execute(
            "SELECT * FROM gd_participants WHERE session_id = ? AND user_id = ?",
            (session_row['id'], user_id)
        ).fetchone()
        if not participant or participant['status'] != 'accepted':
            conn.close()
            return jsonify({'success': False, 'error': 'Not authorized'}), 403
        is_host = bool(session_row['host_user_id'] == user_id or participant['role'] == 'host')
        if not is_host:
            conn.close()
            return jsonify({'success': False, 'error': 'Only host can start GD timer.'}), 403

        session_row = _sync_gd_session_status(conn, session_row)
        current_status = session_row['status']
        if current_status in ('feedback', 'completed'):
            conn.close()
            return jsonify({'success': False, 'error': 'Timer cannot be started now.'}), 400

        joined_count = conn.execute(
            "SELECT COUNT(*) AS c FROM gd_participants WHERE session_id = ? AND status = 'accepted'",
            (session_row['id'],)
        ).fetchone()['c']
        if joined_count < 2:
            conn.close()
            return jsonify({'success': False, 'error': 'At least 2 students are required to start GD.'}), 400

        duration_minutes = max(5, min(90, requested_duration if requested_duration > 0 else _safe_int(session_row['duration_minutes'], 10)))
        if current_status == 'planning':
            conn.execute(
                """UPDATE gd_sessions
                   SET status = 'active',
                       started_at = CURRENT_TIMESTAMP,
                       ended_at = NULL,
                       timer_started_by = ?,
                       duration_minutes = ?
                   WHERE id = ?""",
                (user_id, duration_minutes, session_row['id'])
            )
        elif current_status == 'active' and not session_row['started_at']:
            conn.execute(
                """UPDATE gd_sessions
                   SET started_at = CURRENT_TIMESTAMP,
                       timer_started_by = ?,
                       duration_minutes = ?
                   WHERE id = ?""",
                (user_id, duration_minutes, session_row['id'])
            )

        refreshed = conn.execute("SELECT * FROM gd_sessions WHERE id = ?", (session_row['id'],)).fetchone()
        conn.commit()
        phase, remaining_seconds = _calculate_gd_phase(refreshed)
        conn.close()

        return jsonify({
            'success': True,
            'phase': phase,
            'remaining_seconds': remaining_seconds,
            'status': refreshed['status']
        })
    except Exception as e:
        print(f"GD start timer error: {e}")
        return jsonify({'success': False, 'error': 'Unable to start timer.'}), 500


@app.route('/gd/room/<room_id>/timer/stop', methods=['POST'])
@login_required
def gd_stop_timer(room_id):
    """Stop discussion timer and move room to feedback phase (host only)."""
    try:
        user_id = g.current_user['id']
        conn = get_db_connection()
        session_row = conn.execute("SELECT * FROM gd_sessions WHERE room_id = ?", (room_id,)).fetchone()
        if not session_row:
            conn.close()
            return jsonify({'success': False, 'error': 'Room not found'}), 404

        participant = conn.execute(
            "SELECT * FROM gd_participants WHERE session_id = ? AND user_id = ?",
            (session_row['id'], user_id)
        ).fetchone()
        if not participant or participant['status'] != 'accepted':
            conn.close()
            return jsonify({'success': False, 'error': 'Not authorized'}), 403
        is_host = bool(session_row['host_user_id'] == user_id or participant['role'] == 'host')
        if not is_host:
            conn.close()
            return jsonify({'success': False, 'error': 'Only host can stop GD timer.'}), 403

        session_row = _sync_gd_session_status(conn, session_row)
        if session_row['status'] in ('completed',):
            conn.close()
            return jsonify({'success': True, 'phase': 'completed', 'redirect_url': url_for('gd_result', room_id=room_id)})

        conn.execute(
            "UPDATE gd_sessions SET status = 'feedback', ended_at = CURRENT_TIMESTAMP WHERE id = ?",
            (session_row['id'],)
        )
        conn.execute(
            "UPDATE gd_stop_requests SET status = 'cancelled', resolved_at = CURRENT_TIMESTAMP WHERE session_id = ? AND status = 'pending'",
            (session_row['id'],)
        )
        conn.commit()
        conn.close()
        return jsonify({'success': True, 'phase': 'feedback', 'redirect_url': url_for('gd_feedback', room_id=room_id)})
    except Exception as e:
        print(f"GD stop timer error: {e}")
        return jsonify({'success': False, 'error': 'Unable to stop timer.'}), 500


@app.route('/gd/room/<room_id>/stop-request', methods=['POST'])
@login_required
def gd_stop_request(room_id):
    """Legacy endpoint: now host stop only."""
    return gd_stop_timer(room_id)


@app.route('/gd/room/<room_id>/stop-request/vote', methods=['POST'])
@login_required
def gd_stop_request_vote(room_id):
    """Legacy endpoint no longer used in host-only timer control."""
    return jsonify({'success': False, 'error': 'Stop voting is disabled. Only host can stop GD.'}), 400


@app.route('/gd/room/<room_id>/signal', methods=['POST'])
@login_required
def gd_send_signal(room_id):
    """Store WebRTC signaling messages for polling-based delivery."""
    try:
        user_id = g.current_user['id']
        data = request.get_json(silent=True) or {}
        signal_type = _sanitize_text(data.get('signal_type') or '', 40).lower()
        to_user = _safe_int(data.get('to_user'), 0)
        to_user = to_user if to_user > 0 else None
        payload = data.get('payload')
        if payload is None:
            payload = {}
        if not signal_type:
            return jsonify({'success': False, 'error': 'signal_type is required.'}), 400

        payload_text = json.dumps(payload, ensure_ascii=False)
        if len(payload_text) > 50000:
            return jsonify({'success': False, 'error': 'Signal payload too large.'}), 400

        conn = get_db_connection()
        session_row = conn.execute("SELECT * FROM gd_sessions WHERE room_id = ?", (room_id,)).fetchone()
        if not session_row:
            conn.close()
            return jsonify({'success': False, 'error': 'Room not found'}), 404

        participant = conn.execute(
            "SELECT * FROM gd_participants WHERE session_id = ? AND user_id = ?",
            (session_row['id'], user_id)
        ).fetchone()
        if not participant or participant['status'] != 'accepted':
            conn.close()
            return jsonify({'success': False, 'error': 'Not authorized'}), 403

        if to_user:
            target = conn.execute(
                "SELECT 1 FROM gd_participants WHERE session_id = ? AND user_id = ? AND status = 'accepted'",
                (session_row['id'], to_user)
            ).fetchone()
            if not target:
                conn.close()
                return jsonify({'success': False, 'error': 'Target participant not found.'}), 404

        conn.execute(
            """INSERT INTO gd_webrtc_signals (session_id, from_user, to_user, signal_type, signal_payload)
               VALUES (?, ?, ?, ?, ?)""",
            (session_row['id'], user_id, to_user, signal_type, payload_text)
        )
        conn.execute(
            """DELETE FROM gd_webrtc_signals
               WHERE session_id = ? AND id < (
                    SELECT CASE WHEN MAX(id) > 1500 THEN MAX(id) - 1500 ELSE 0 END
                    FROM gd_webrtc_signals WHERE session_id = ?
               )""",
            (session_row['id'], session_row['id'])
        )
        conn.commit()
        conn.close()
        return jsonify({'success': True})
    except Exception as e:
        print(f"GD signal send error: {e}")
        return jsonify({'success': False, 'error': 'Unable to send signal.'}), 500


@app.route('/gd/room/<room_id>/signals')
@login_required
def gd_poll_signals(room_id):
    """Fetch WebRTC signals addressed to current participant."""
    try:
        user_id = g.current_user['id']
        after_id = max(0, _safe_int(request.args.get('after_id'), 0))
        limit = max(20, min(300, _safe_int(request.args.get('limit'), 120)))

        conn = get_db_connection()
        session_row = conn.execute("SELECT * FROM gd_sessions WHERE room_id = ?", (room_id,)).fetchone()
        if not session_row:
            conn.close()
            return jsonify({'success': False, 'signals': []}), 404

        participant = conn.execute(
            "SELECT * FROM gd_participants WHERE session_id = ? AND user_id = ?",
            (session_row['id'], user_id)
        ).fetchone()
        if not participant or participant['status'] != 'accepted':
            conn.close()
            return jsonify({'success': False, 'signals': []}), 403

        rows = conn.execute(
            """SELECT s.id, s.from_user, s.to_user, s.signal_type, s.signal_payload, s.created_at, u.username AS from_name
               FROM gd_webrtc_signals s
               LEFT JOIN users u ON u.id = s.from_user
               WHERE s.session_id = ?
                 AND s.id > ?
                 AND s.from_user != ?
                 AND (s.to_user IS NULL OR s.to_user = ?)
               ORDER BY s.id ASC
               LIMIT ?""",
            (session_row['id'], after_id, user_id, user_id, limit)
        ).fetchall()
        conn.close()

        signals = []
        for row in rows:
            item = dict(row)
            try:
                item['payload'] = json.loads(item.get('signal_payload') or '{}')
            except Exception:
                item['payload'] = {}
            item.pop('signal_payload', None)
            signals.append(item)
        return jsonify({'success': True, 'signals': signals})
    except Exception as e:
        print(f"GD poll signals error: {e}")
        return jsonify({'success': False, 'signals': []}), 500


@app.route('/gd/room/<room_id>/messages')
@login_required
def gd_room_messages(room_id):
    """Fetch new GD room messages."""
    try:
        user_id = g.current_user['id']
        after_id = _safe_int(request.args.get('after_id'), 0)
        conn = get_db_connection()
        session_row = conn.execute("SELECT * FROM gd_sessions WHERE room_id = ?", (room_id,)).fetchone()
        if not session_row:
            conn.close()
            return jsonify({'success': False, 'messages': []}), 404

        participant = conn.execute(
            "SELECT 1 FROM gd_participants WHERE session_id = ? AND user_id = ?",
            (session_row['id'], user_id)
        ).fetchone()
        if not participant:
            conn.close()
            return jsonify({'success': False, 'messages': []}), 403

        rows = conn.execute(
            """SELECT m.id, m.user_id, m.message, m.created_at, p.name
               FROM gd_messages m
               JOIN gd_participants p ON p.session_id = m.session_id AND p.user_id = m.user_id
               WHERE m.session_id = ? AND m.id > ?
               ORDER BY m.id ASC
               LIMIT 120""",
            (session_row['id'], after_id)
        ).fetchall()
        conn.close()
        return jsonify({'success': True, 'messages': [dict(r) for r in rows]})
    except Exception as e:
        print(f"GD messages error: {e}")
        return jsonify({'success': False, 'messages': []}), 500


@app.route('/gd/room/<room_id>/message', methods=['POST'])
@login_required
def gd_send_message(room_id):
    """Send message during discussion phase."""
    try:
        user_id = g.current_user['id']
        data = request.get_json(silent=True) or {}
        message = _sanitize_text(data.get('message') or '', max_len=500)
        if not message:
            return jsonify({'success': False, 'error': 'Message cannot be empty.'}), 400

        conn = get_db_connection()
        session_row = conn.execute("SELECT * FROM gd_sessions WHERE room_id = ?", (room_id,)).fetchone()
        if not session_row:
            conn.close()
            return jsonify({'success': False, 'error': 'Room not found'}), 404

        participant = conn.execute(
            "SELECT 1 FROM gd_participants WHERE session_id = ? AND user_id = ?",
            (session_row['id'], user_id)
        ).fetchone()
        if not participant:
            conn.close()
            return jsonify({'success': False, 'error': 'Not authorized'}), 403

        session_row = _sync_gd_session_status(conn, session_row)
        phase, _ = _calculate_gd_phase(session_row)
        if phase != 'discussion':
            conn.close()
            return jsonify({'success': False, 'error': 'Messages are allowed only during discussion phase.'}), 400

        conn.execute(
            "INSERT INTO gd_messages (session_id, user_id, message) VALUES (?, ?, ?)",
            (session_row['id'], user_id, message)
        )
        conn.commit()
        conn.close()
        return jsonify({'success': True})
    except Exception as e:
        print(f"GD send message error: {e}")
        return jsonify({'success': False, 'error': 'Unable to send message.'}), 500


@app.route('/gd/feedback/<room_id>', methods=['GET', 'POST'])
@login_required
def gd_feedback(room_id):
    """Feedback collection page after discussion."""
    try:
        user_id = g.current_user['id']
        conn = get_db_connection()
        session_row = conn.execute("SELECT * FROM gd_sessions WHERE room_id = ?", (room_id,)).fetchone()
        if not session_row:
            conn.close()
            return "GD session not found", 404

        participant = conn.execute(
            "SELECT * FROM gd_participants WHERE session_id = ? AND user_id = ?",
            (session_row['id'], user_id)
        ).fetchone()
        if not participant:
            conn.close()
            return "You are not part of this GD session.", 403

        session_row = _sync_gd_session_status(conn, session_row)
        conn.commit()
        phase, _ = _calculate_gd_phase(session_row)

        if phase in ('lobby', 'thinking', 'discussion'):
            conn.close()
            return redirect(url_for('gd_room', room_id=room_id))

        participants = conn.execute(
            "SELECT user_id, name, field, target_role FROM gd_participants WHERE session_id = ? ORDER BY joined_at ASC",
            (session_row['id'],)
        ).fetchall()
        peer_participants = [dict(p) for p in participants if p['user_id'] != user_id]

        if request.method == 'POST':
            experience = _sanitize_text(request.form.get('experience') or '', 1800)
            response_text = _sanitize_text(request.form.get('response') or '', 2200)
            if not response_text:
                conn.close()
                flash('Please add your points/response for AI evaluation.', 'warning')
                return redirect(url_for('gd_feedback', room_id=room_id))

            conn.execute(
                """INSERT INTO gd_responses (session_id, user_id, response, experience, updated_at)
                   VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
                   ON CONFLICT(session_id, user_id)
                   DO UPDATE SET response = excluded.response, experience = excluded.experience, updated_at = CURRENT_TIMESTAMP""",
                (session_row['id'], user_id, response_text, experience)
            )

            for peer in peer_participants:
                peer_user_id = peer['user_id']
                pros = _sanitize_text(request.form.get(f'pros_{peer_user_id}') or 'Good participation.', 600)
                cons = _sanitize_text(request.form.get(f'cons_{peer_user_id}') or 'Can improve structure and examples.', 600)
                conn.execute(
                    """INSERT INTO gd_peer_feedback (session_id, from_user, to_user, pros, cons, updated_at)
                       VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                       ON CONFLICT(session_id, from_user, to_user)
                       DO UPDATE SET pros = excluded.pros, cons = excluded.cons, updated_at = CURRENT_TIMESTAMP""",
                    (session_row['id'], user_id, peer_user_id, pros, cons)
                )

            _update_gd_session_completion(conn, session_row['id'])
            conn.commit()
            conn.close()

            log_activity('gd_feedback_submitted', 'gd', 'Submitted GD feedback', f'room_id={room_id}')
            return redirect(url_for('gd_result', room_id=room_id))

        existing_response = conn.execute(
            "SELECT * FROM gd_responses WHERE session_id = ? AND user_id = ?",
            (session_row['id'], user_id)
        ).fetchone()
        existing_feedback = conn.execute(
            "SELECT to_user, pros, cons FROM gd_peer_feedback WHERE session_id = ? AND from_user = ?",
            (session_row['id'], user_id)
        ).fetchall()
        feedback_map = {row['to_user']: {'pros': row['pros'], 'cons': row['cons']} for row in existing_feedback}
        conn.close()

        return render_template(
            'gd/feedback.html',
            session=dict(session_row),
            peer_participants=peer_participants,
            existing_response=dict(existing_response) if existing_response else None,
            feedback_map=feedback_map
        )
    except Exception as e:
        print(f"GD feedback error: {e}")
        return f"Error: {e}", 500


@app.route('/gd/result/<room_id>')
@login_required
def gd_result(room_id):
    """Show AI + peer GD evaluation."""
    try:
        user_id = g.current_user['id']
        conn = get_db_connection()
        session_row = conn.execute("SELECT * FROM gd_sessions WHERE room_id = ?", (room_id,)).fetchone()
        if not session_row:
            conn.close()
            return "GD session not found", 404

        participant = conn.execute(
            "SELECT * FROM gd_participants WHERE session_id = ? AND user_id = ?",
            (session_row['id'], user_id)
        ).fetchone()
        if not participant:
            conn.close()
            return "You are not part of this GD session.", 403

        session_row = _sync_gd_session_status(conn, session_row)
        conn.commit()

        response_row = conn.execute(
            "SELECT * FROM gd_responses WHERE session_id = ? AND user_id = ?",
            (session_row['id'], user_id)
        ).fetchone()
        if not response_row:
            conn.close()
            flash('Please submit your feedback first.', 'warning')
            return redirect(url_for('gd_feedback', room_id=room_id))

        peer_feedback_rows = conn.execute(
            """SELECT f.pros, f.cons, p.name AS from_name
               FROM gd_peer_feedback f
               JOIN gd_participants p ON p.session_id = f.session_id AND p.user_id = f.from_user
               WHERE f.session_id = ? AND f.to_user = ?
               ORDER BY f.id ASC""",
            (session_row['id'], user_id)
        ).fetchall()
        peer_feedback = [dict(r) for r in peer_feedback_rows]

        my_messages = conn.execute(
            """SELECT message FROM gd_messages
               WHERE session_id = ? AND user_id = ?
               ORDER BY id ASC LIMIT 40""",
            (session_row['id'], user_id)
        ).fetchall()
        message_points = '; '.join([row['message'] for row in my_messages])[:2500]
        response_text = (response_row['response'] or '').strip()
        if message_points:
            response_text = f"{response_text}\nKey discussion points: {message_points}".strip()

        evaluation = _get_or_create_gd_evaluation(
            conn=conn,
            session_id=session_row['id'],
            user_id=user_id,
            topic=session_row['topic'],
            response=response_text,
            experience=response_row['experience'] or '',
            peer_feedback=peer_feedback
        )

        participant_rows = conn.execute(
            """SELECT user_id, name, field, target_role, role
               FROM gd_participants
               WHERE session_id = ? AND status = 'accepted'
               ORDER BY joined_at ASC""",
            (session_row['id'],)
        ).fetchall()
        response_rows = conn.execute(
            "SELECT user_id, response, experience FROM gd_responses WHERE session_id = ?",
            (session_row['id'],)
        ).fetchall()
        message_rows = conn.execute(
            "SELECT user_id, message FROM gd_messages WHERE session_id = ? ORDER BY id ASC",
            (session_row['id'],)
        ).fetchall()
        message_count_rows = conn.execute(
            "SELECT user_id, COUNT(*) AS c FROM gd_messages WHERE session_id = ? GROUP BY user_id",
            (session_row['id'],)
        ).fetchall()
        peer_incoming_rows = conn.execute(
            "SELECT to_user, pros, cons FROM gd_peer_feedback WHERE session_id = ? ORDER BY id ASC",
            (session_row['id'],)
        ).fetchall()

        response_map = {row['user_id']: dict(row) for row in response_rows}
        message_text_map = {}
        for row in message_rows:
            uid = row['user_id']
            message_text_map.setdefault(uid, []).append(row['message'])
        message_text_map = {uid: '; '.join(parts)[:2500] for uid, parts in message_text_map.items()}
        message_count_map = {row['user_id']: row['c'] for row in message_count_rows}
        peer_received_map = {}
        for row in peer_incoming_rows:
            peer_received_map.setdefault(row['to_user'], []).append({'pros': row['pros'], 'cons': row['cons']})

        member_feedback_cards = []
        for member in participant_rows:
            member_dict = dict(member)
            member_id = member_dict['user_id']
            member_response = response_map.get(member_id, {})
            member_response_text = (member_response.get('response') or '').strip()
            member_message_points = message_text_map.get(member_id, '')
            if member_message_points:
                member_response_text = f"{member_response_text}\nKey discussion points: {member_message_points}".strip()
            member_experience = member_response.get('experience', '')
            member_peer_feedback = peer_received_map.get(member_id, [])

            card_feedback = _build_template_gd_feedback(
                member_name=member_dict.get('name') or 'Student',
                topic=session_row['topic'],
                response=member_response_text,
                experience=member_experience,
                peer_feedback_rows=member_peer_feedback,
                message_count=message_count_map.get(member_id, 0)
            )

            member_eval = None
            if member_id == user_id:
                member_eval = evaluation
            elif member_response_text or member_experience or member_peer_feedback:
                member_eval = _get_or_create_gd_evaluation(
                    conn=conn,
                    session_id=session_row['id'],
                    user_id=member_id,
                    topic=session_row['topic'],
                    response=member_response_text,
                    experience=member_experience,
                    peer_feedback=member_peer_feedback
                )

            member_dict.update(card_feedback)
            member_dict['ai_feedback_ready'] = bool(member_eval)
            member_dict['ai_confidence'] = member_eval.get('confidence') if member_eval else None
            member_dict['ai_communication'] = member_eval.get('communication') if member_eval else None
            member_dict['ai_logical_thinking'] = member_eval.get('logical_thinking') if member_eval else None
            member_dict['ai_participation'] = member_eval.get('participation') if member_eval else member_dict.get('participation_band')
            member_dict['ai_final_feedback'] = (member_eval.get('final_feedback') if member_eval else member_dict.get('summary'))
            member_dict['ai_strengths'] = member_eval.get('strengths', []) if member_eval else member_dict.get('strengths', [])
            member_dict['ai_improvements'] = member_eval.get('improvements', []) if member_eval else member_dict.get('improvements', [])
            member_dict['ai_source'] = (member_eval.get('source') if member_eval else 'template')
            member_dict['submitted'] = bool(member_response)
            member_feedback_cards.append(member_dict)

        total_participants = conn.execute(
            "SELECT COUNT(*) as c FROM gd_participants WHERE session_id = ?",
            (session_row['id'],)
        ).fetchone()['c']
        responses_submitted = conn.execute(
            "SELECT COUNT(*) as c FROM gd_responses WHERE session_id = ?",
            (session_row['id'],)
        ).fetchone()['c']

        conn.commit()
        conn.close()

        log_activity('gd_result_viewed', 'gd', 'Viewed GD result', f'room_id={room_id}')
        return render_template(
            'gd/result.html',
            session=dict(session_row),
            response=dict(response_row),
            peer_feedback=peer_feedback,
            evaluation=evaluation,
            total_participants=total_participants,
            responses_submitted=responses_submitted,
            member_feedback_cards=member_feedback_cards
        )
    except Exception as e:
        print(f"GD result error: {e}")
        return f"Error: {e}", 500

# ==================== MENTAL HEALTH MODULE ====================
@app.route('/mental')
@login_required
def mental_home():
    """Mental Health homepage - Dashboard"""
    try:
        conn = get_db_connection()
        # Get recent mood entries (personal if logged in)
        if getattr(g, 'current_user', None):
            uid = g.current_user['id']
            recent_moods = conn.execute('SELECT * FROM mood_entries WHERE user_id = ? ORDER BY timestamp DESC LIMIT 5', (uid,)).fetchall()
            total_entries = conn.execute('SELECT COUNT(*) as count FROM mood_entries WHERE user_id = ?', (uid,)).fetchone()['count']
            mood_stats = {}
            if total_entries > 0:
                moods = conn.execute('SELECT mood, COUNT(*) as count FROM mood_entries WHERE user_id = ? GROUP BY mood', (uid,)).fetchall()
                for row in moods:
                    mood_stats[row['mood']] = row['count']
        else:
            recent_moods = conn.execute('SELECT * FROM mood_entries ORDER BY timestamp DESC LIMIT 5').fetchall()
            total_entries = conn.execute('SELECT COUNT(*) as count FROM mood_entries').fetchone()['count']
            mood_stats = {}
            if total_entries > 0:
                moods = conn.execute('SELECT mood, COUNT(*) as count FROM mood_entries GROUP BY mood').fetchall()
                for row in moods:
                    mood_stats[row['mood']] = row['count']
        
        conn.close()
        
        mood_list = []
        for row in recent_moods:
            mood_list.append(dict(row))
        
        return render_template('mental/home.html', 
                             recent_moods=mood_list,
                             mood_stats=mood_stats,
                             total_entries=total_entries)
                             
    except Exception as e:
        print(f"Mental home error: {e}")
        return f"<h2>Error: {e}</h2><a href='/'>Back to Home</a>", 500

@app.route('/mental/breathing')
@login_required
def mental_breathing():
    """Guided breathing exercise"""
    # Log breathing exercise access
    log_activity('breathing_started', 'mental', 'Started guided breathing exercise')
    
    return render_template('mental/breathing.html')

@app.route('/mental/mood', methods=['GET', 'POST'])
@login_required
def mental_mood():
    """Mood assessment questionnaire"""
    mood = None
    suggestion = None
    features = None
    form_data = None

    if request.method == 'POST':
        try:
            date = request.form.get('date')
            q1 = int(request.form.get('q1'))  # How are you feeling (1-5)
            q2 = int(request.form.get('q2'))  # Energy level (1-5)
            q3 = int(request.form.get('q3'))  # Stress level (1-5)
            q4 = int(request.form.get('q4'))  # Anxiety level (1-5)
            q5 = int(request.form.get('q5'))  # Optimism (1-5)
            notes = request.form.get('notes', '')
            
            if not date:
                return "Date is required", 400
            
            # Calculate mood based on answers
            mood = analyze_mood(q1, q2, q3, q4, q5)
            form_data = request.form
            suggestion_info = get_mood_recommendations(mood)
            suggestion = suggestion_info['suggestion']
            features = suggestion_info['features']
            
            # Store assessment data as notes for reference
            assessment_notes = f"Assessment: Q1={q1}, Q2={q2}, Q3={q3}, Q4={q4}, Q5={q5}. {notes}".strip()
            
            conn = get_db_connection()
            user_id = g.current_user.get('id') if getattr(g, 'current_user', None) else None
            conn.execute('INSERT INTO mood_entries (date, mood, notes, user_id) VALUES (?, ?, ?, ?)',
                        (date, mood, assessment_notes, user_id))
            conn.commit()
            conn.close()
            
            # Log mood assessment activity
            log_activity('mood_assessment', 'mental', f'Completed mood assessment: {mood}', 
                        f"Date: {date}")
        except Exception as e:
            print(f"Mood assessment error: {e}")
            return f"Error: {e}", 500
    
    return render_template('mental/mood.html', mood=mood, suggestion=suggestion,
                           features=features, form_data=form_data)

def analyze_mood(q1, q2, q3, q4, q5):
    """
    Analyze mood based on questionnaire answers
    q1: How are you feeling (1=Very Bad, 5=Very Good)
    q2: Energy level (1=Very Low, 5=Very High)
    q3: Stress level (1=Not at all, 5=Extremely)
    q4: Anxiety level (1=Not at all, 5=Extremely)
    q5: Optimism (1=Very Pessimistic, 5=Very Optimistic)
    """
    
    # Calculate weighted scores
    overall_feeling = q1  # Direct feeling
    energy = q2
    stress = 6 - q3  # Invert stress (high stress = low positive mood)
    anxiety = 6 - q4  # Invert anxiety
    optimism = q5
    
    # Weighted average (feeling and optimism have higher weight)
    mood_score = (overall_feeling * 2 + energy + stress + anxiety + optimism * 2) / 7
    
    # Determine mood based on score ranges
    if mood_score >= 4.5:
        return "Happy"
    elif mood_score >= 4.0:
        return "Excited"
    elif mood_score >= 3.5:
        return "Calm"
    elif mood_score >= 3.0:
        return "Content"
    elif mood_score >= 2.5:
        return "Neutral"
    elif mood_score >= 2.0:
        return "Tired"
    elif mood_score >= 1.5:
        return "Anxious"
    elif mood_score >= 1.0:
        return "Sad"
    else:
        return "Angry"


def get_mood_recommendations(mood):
    default = {
        'suggestion': 'Keep tracking your mood and choose the activity that feels right for you today.',
        'features': [
            {'name': 'Guided Breathing', 'url': url_for('mental_breathing')},
            {'name': 'Yoga Practice', 'url': url_for('mental_yoga')},
            {'name': 'Mood History', 'url': url_for('mental_history')}
        ]
    }

    if mood in ['Happy', 'Excited', 'Calm', 'Content']:
        return {
            'suggestion': 'You are in a good space. Keep the positive momentum with gentle self-care and learning.',
            'features': [
                {'name': 'Yoga Practice', 'url': url_for('mental_yoga')},
                {'name': 'Guided Meditation', 'url': url_for('mental_meditation')},
                {'name': 'Mood History', 'url': url_for('mental_history')}
            ]
        }
    if mood == 'Neutral':
        return {
            'suggestion': 'Your mood is steady. Try a short breathing session or a calming yoga flow to stay balanced.',
            'features': [
                {'name': 'Guided Breathing', 'url': url_for('mental_breathing')},
                {'name': 'Yoga Practice', 'url': url_for('mental_yoga')},
                {'name': 'Mood History', 'url': url_for('mental_history')}
            ]
        }
    if mood == 'Tired':
        return {
            'suggestion': 'You may need rest and gentle movement. A short yoga stretch or breathing practice can help recharge you.',
            'features': [
                {'name': 'Yoga Practice', 'url': url_for('mental_yoga')},
                {'name': 'Guided Breathing', 'url': url_for('mental_breathing')}
            ]
        }
    if mood in ['Anxious', 'Sad', 'Angry']:
        return {
            'suggestion': 'You may benefit from calming support. Start with breathing and mindfulness, then review your mood history.',
            'features': [
                {'name': 'Guided Breathing', 'url': url_for('mental_breathing')},
                {'name': 'Guided Meditation', 'url': url_for('mental_meditation')},
                {'name': 'Mood History', 'url': url_for('mental_history')}
            ]
        }

    return default

@app.route('/mental/history')
@login_required
def mental_history():
    """Mood history"""
    log_activity('page_view', 'mental', 'Viewed mood history')
    try:
        conn = get_db_connection()
        if getattr(g, 'current_user', None):
            moods = conn.execute('SELECT * FROM mood_entries WHERE user_id = ? ORDER BY date DESC', (g.current_user['id'],)).fetchall()
        else:
            moods = conn.execute('SELECT * FROM mood_entries ORDER BY date DESC').fetchall()
        conn.close()
        
        mood_list = []
        for row in moods:
            mood_list.append(dict(row))
        
        return render_template('mental/history.html', moods=mood_list)
    except Exception as e:
        print(f"Mood history error: {e}")
        return f"Error: {e}", 500

@app.route('/mental/meditation')
@login_required
def mental_meditation():
    """Guided Meditation Sessions"""
    log_activity('page_view', 'mental', 'Accessed meditation')
    return render_template('mental/meditation.html')

@app.route('/mental/yoga')
@login_required
def mental_yoga():
    """Yoga Poses and Sequences"""
    log_activity('page_view', 'mental', 'Accessed yoga')
    return render_template('mental/yoga.html')

# ==================== PROGRESS DASHBOARD ====================
@app.route('/progress')
@login_required
def progress_dashboard():
    """Personal Progress Dashboard"""
    log_activity('page_view', 'progress', 'Viewed progress dashboard')
    try:
        conn = get_db_connection()
        # If user logged in, show personal stats, otherwise show global stats
        if getattr(g, 'current_user', None):
            uid = g.current_user['id']
            total_activities = conn.execute('SELECT COUNT(*) as count FROM user_activity WHERE user_id = ?', (uid,)).fetchone()['count']

            module_stats = {}
            modules = conn.execute('SELECT module, COUNT(*) as count FROM user_activity WHERE user_id = ? GROUP BY module', (uid,)).fetchall()
            for row in modules:
                module_stats[row['module']] = row['count']

            activity_types = {}
            types = conn.execute('SELECT activity_type, COUNT(*) as count FROM user_activity WHERE user_id = ? GROUP BY activity_type', (uid,)).fetchall()
            for row in types:
                activity_types[row['activity_type']] = row['count']

            recent_activities = conn.execute('SELECT * FROM user_activity WHERE user_id = ? ORDER BY timestamp DESC LIMIT 10', (uid,)).fetchall()
        else:
            # global
            total_activities = conn.execute('SELECT COUNT(*) as count FROM user_activity').fetchone()['count']

            module_stats = {}
            modules = conn.execute('SELECT module, COUNT(*) as count FROM user_activity GROUP BY module').fetchall()
            for row in modules:
                module_stats[row['module']] = row['count']

            activity_types = {}
            types = conn.execute('SELECT activity_type, COUNT(*) as count FROM user_activity GROUP BY activity_type').fetchall()
            for row in types:
                activity_types[row['activity_type']] = row['count']

            recent_activities = conn.execute('SELECT * FROM user_activity ORDER BY timestamp DESC LIMIT 10').fetchall()
        
        # Learning streaks (consecutive days with activity)
        if getattr(g, 'current_user', None):
            streak_data = conn.execute('''
                SELECT DATE(timestamp) as date, COUNT(*) as activities 
                FROM user_activity 
                WHERE user_id = ?
                GROUP BY DATE(timestamp) 
                ORDER BY date DESC 
                LIMIT 30
            ''', (g.current_user['id'],)).fetchall()
        else:
            streak_data = conn.execute('''
                SELECT DATE(timestamp) as date, COUNT(*) as activities 
                FROM user_activity 
                GROUP BY DATE(timestamp) 
                ORDER BY date DESC 
                LIMIT 30
            ''').fetchall()
        
        # Calculate current streak
        current_streak = 0
        if streak_data:
            from datetime import datetime, timedelta
            today = datetime.now().date()
            
            for row in streak_data:
                activity_date = datetime.strptime(row['date'], '%Y-%m-%d').date()
                if activity_date == today - timedelta(days=current_streak):
                    current_streak += 1
                else:
                    break
        
        # Achievement badges
        badges = []
        if total_activities >= 1:
            badges.append({'name': 'First Steps', 'icon': 'ðŸ‘¶', 'description': 'Started your journey'})
        if total_activities >= 10:
            badges.append({'name': 'Explorer', 'icon': 'ðŸ—ºï¸', 'description': 'Explored 10+ activities'})
        if total_activities >= 50:
            badges.append({'name': 'Dedicated Learner', 'icon': 'ðŸ“š', 'description': '50+ learning activities'})
        if current_streak >= 7:
            badges.append({'name': 'Consistency King', 'icon': 'ðŸ‘‘', 'description': '7+ day learning streak'})
        if module_stats.get('career', 0) >= 5:
            badges.append({'name': 'Career Explorer', 'icon': 'ðŸŽ¯', 'description': 'Explored 5+ careers'})
        if module_stats.get('gyan', 0) >= 10:
            badges.append({'name': 'Wisdom Seeker', 'icon': 'ðŸ§˜', 'description': 'Read 10+ spiritual verses'})
        if module_stats.get('mental', 0) >= 5:
            badges.append({'name': 'Mindful Soul', 'icon': 'ðŸŒ¸', 'description': 'Completed 5+ mental wellness activities'})
        
        conn.close()
        
        activity_list = []
        for row in recent_activities:
            activity_list.append(dict(row))
        
        streak_list = []
        for row in streak_data:
            streak_list.append({'date': row['date'], 'activities': row['activities']})
        
        return render_template('progress/dashboard.html',
                             total_activities=total_activities,
                             module_stats=module_stats,
                             activity_types=activity_types,
                             recent_activities=activity_list,
                             current_streak=current_streak,
                             streak_data=streak_list,
                             badges=badges)
                             
    except Exception as e:
        print(f"Progress dashboard error: {e}")
        return f"<h2>Error: {e}</h2><a href='/'>Back to Home</a>", 500

# ==================== API ROUTES ====================
    """API endpoint for statistics"""
    try:
        conn = get_db_connection()
        
        stats = {
            'careers': conn.execute('SELECT COUNT(*) as count FROM careers').fetchone()['count'],
            'shlokas': conn.execute('SELECT COUNT(*) as count FROM gyan_kosh').fetchone()['count'],
            'resources': conn.execute('SELECT COUNT(*) as count FROM learning_resources').fetchone()['count'],
            'moods': conn.execute('SELECT COUNT(*) as count FROM mood_entries').fetchone()['count']
        }
        
        categories = conn.execute('SELECT DISTINCT category FROM careers').fetchall()
        stats['categories'] = len(categories)
        
        conn.close()
        
        return (stats)
    except Exception as e:
        return ({'error': str(e)}), 500

# ==================== AI TOOLS MODULE ====================
# Simple catalog of helpful AI and learning tools for students
TOOLS_CATALOG = {
    'expense_tracker': {
        'name': 'AI Expense Tracker',
        'url': 'https://expense-tracker-margdarshak.vercel.app/',
        'description': 'Smart expense tracking and budgeting tool for students.',
        'purpose': 'Productivity'
    },
    'mock_interview': {
        'name': 'AI Mock Interviewer',
        'url': 'https://aimockinterviewer-one.vercel.app/',
        'description': 'Practice mock interviews with AI for job preparation.',
        'purpose': 'Career'
    },
    'leetcode': {
        'name': 'LeetCode',
        'url': 'https://leetcode.com',
        'description': 'Practice data structures and algorithms with coding problems.',
        'purpose': 'Coding'
    },
    'wolfram': {
        'name': 'WolframAlpha',
        'url': 'https://www.wolframalpha.com',
        'description': 'Powerful computation engine for math, science, and data.',
        'purpose': 'Research'
    },
    'khan': {
        'name': 'Khan Academy',
        'url': 'https://www.khanacademy.org',
        'description': 'Free video lessons and practice exercises across subjects.',
        'purpose': 'Learning'
    },
    'coursera': {
        'name': 'Coursera',
        'url': 'https://www.coursera.org',
        'description': 'Online courses from top universities (some free options).',
        'purpose': 'Learning'
    },
    'stackoverflow': {
        'name': 'Stack Overflow',
        'url': 'https://stackoverflow.com',
        'description': 'Community Q&A for programming and development questions.',
        'purpose': 'Coding'
    },
    'grammarly': {
        'name': 'Grammarly',
        'url': 'https://www.grammarly.com',
        'description': 'Writing assistant for grammar, clarity, and tone.',
        'purpose': 'Writing'
    },
    'replit': {
        'name': 'Replit',
        'url': 'https://replit.com',
        'description': 'In-browser coding environment to write and test code quickly.',
        'purpose': 'Coding'
    },
    'gamma': {
        'name': 'Gamma',
        'url': 'https://gamma.app',
        'description': 'AI-powered presentation maker for creating stunning slides.',
        'purpose': 'Design'
    },
    'napkin': {
        'name': 'Napkin AI',
        'url': 'https://napkin.ai',
        'description': 'AI tool for creating flowcharts, diagrams, and visual ideas.',
        'purpose': 'Design'
    },
    'chatgpt': {
        'name': 'ChatGPT',
        'url': 'https://chat.openai.com',
        'description': 'Conversational AI for answering questions and generating text.',
        'purpose': 'General'
    },
    'deepseek': {
        'name': 'DeepSeek',
        'url': 'https://chat.deepseek.com',
        'description': 'AI chat tool for research, coding, and creative tasks.',
        'purpose': 'Research'
    },
    'notebooklm': {
        'name': 'NotebookLM',
        'url': 'https://notebooklm.google.com',
        'description': 'AI-powered notebook for organizing and summarizing notes.',
        'purpose': 'Learning'
    },
    'gemini': {
        'name': 'Gemini AI',
        'url': 'https://gemini.google.com',
        'description': 'Google\'s multimodal AI for text, images, and more.',
        'purpose': 'General'
    },
    'ppt_to_word': {
        'name': 'PPT to Word',
        'url': 'https://www.ilovepdf.com/ppt-to-word',
        'description': 'Convert PowerPoint presentations to Word documents online.',
        'purpose': 'Document'
    },
    'word_to_ppt': {
        'name': 'Word to PPT',
        'url': 'https://www.ilovepdf.com/word-to-ppt',
        'description': 'Convert Word documents to PowerPoint presentations.',
        'purpose': 'Document'
    },
    'word_to_pdf': {
        'name': 'Word to PDF',
        'url': 'https://www.ilovepdf.com/word-to-pdf',
        'description': 'Convert Word documents to PDF format easily.',
        'purpose': 'Document'
    },
    'quadratic': {
        'name': 'Quadratic',
        'url': 'https://app.quadratichq.com/',
        'description': 'AI-powered spreadsheet with Python integration for data analysis and visualization.',
        'purpose': 'Data'
    },
    'perplexity': {
        'name': 'Perplexity AI',
        'url': 'https://www.perplexity.ai',
        'description': 'AI search engine that provides sourced answers to complex questions.',
        'purpose': 'Research'
    },
    'mermaid': {
        'name': 'Mermaid Live Editor',
        'url': 'https://mermaid.live',
        'description': 'Create diagrams and flowcharts using simple text-based syntax.',
        'purpose': 'Design'
    },
    'excalidraw': {
        'name': 'Excalidraw',
        'url': 'https://excalidraw.com',
        'description': 'Hand-drawn style collaborative whiteboard for sketching ideas.',
        'purpose': 'Design'
    },
    'figma': {
        'name': 'Figma',
        'url': 'https://www.figma.com',
        'description': 'Collaborative interface design tool for UI/UX prototyping.',
        'purpose': 'Design'
    },
    'canva': {
        'name': 'Canva',
        'url': 'https://www.canva.com',
        'description': 'Design tool for creating graphics, presentations, and social media content.',
        'purpose': 'Design'
    },
    'notion': {
        'name': 'Notion',
        'url': 'https://www.notion.so',
        'description': 'All-in-one workspace for notes, docs, and project management.',
        'purpose': 'Productivity'
    },
    'obsidian': {
        'name': 'Obsidian',
        'url': 'https://obsidian.md',
        'description': 'Knowledge management tool for connecting and organizing notes.',
        'purpose': 'Productivity'
    },
    'anki': {
        'name': 'Anki',
        'url': 'https://apps.ankiweb.net',
        'description': 'Flashcard app using spaced repetition for efficient learning.',
        'purpose': 'Learning'
    },
    'duolingo': {
        'name': 'Duolingo',
        'url': 'https://www.duolingo.com',
        'description': 'Gamified language learning platform for multiple languages.',
        'purpose': 'Learning'
    },
    'codecademy': {
        'name': 'Codecademy',
        'url': 'https://www.codecademy.com',
        'description': 'Interactive coding lessons for learning programming languages.',
        'purpose': 'Learning'
    },
    'freecodecamp': {
        'name': 'freeCodeCamp',
        'url': 'https://www.freecodecamp.org',
        'description': 'Free coding bootcamp with interactive lessons and certifications.',
        'purpose': 'Learning'
    },
    'glitch': {
        'name': 'Glitch',
        'url': 'https://glitch.com',
        'description': 'Collaborative coding platform for building and hosting web apps.',
        'purpose': 'Development'
    },
    'vercel': {
        'name': 'Vercel',
        'url': 'https://vercel.com',
        'description': 'Platform for deploying and hosting web applications globally.',
        'purpose': 'Development'
    },
    'netlify': {
        'name': 'Netlify',
        'url': 'https://www.netlify.com',
        'description': 'Web hosting and serverless backend services for modern web projects.',
        'purpose': 'Development'
    },
    'supabase': {
        'name': 'Supabase',
        'url': 'https://supabase.com',
        'description': 'Open source Firebase alternative with database and authentication.',
        'purpose': 'Development'
    },
    'planetscale': {
        'name': 'PlanetScale',
        'url': 'https://planetscale.com',
        'description': 'Serverless MySQL platform for modern application development.',
        'purpose': 'Development'
    },
    'railway': {
        'name': 'Railway',
        'url': 'https://railway.app',
        'description': 'Infrastructure platform for deploying applications without DevOps.',
        'purpose': 'Development'
    },
    'cursor': {
        'name': 'Cursor',
        'url': 'https://cursor.sh',
        'description': 'AI-first code editor built on VS Code with advanced AI features.',
        'purpose': 'Development'
    },
    'windsor': {
        'name': 'Windsor',
        'url': 'https://windsor.io',
        'description': 'Data integration platform for connecting marketing and business tools.',
        'purpose': 'Business'
    }
}

@app.route('/ai/tools')
@login_required
def ai_tools():
    try:
        search_query = request.args.get('search', '').strip().lower()
        purpose_query = request.args.get('purpose', '').strip().lower()

        filtered_tools = {}
        for tid, tool in TOOLS_CATALOG.items():
            title = tool.get('name', '').lower()
            description = tool.get('description', '').lower()
            purpose = tool.get('purpose', '').lower()

            matches_search = True
            matches_purpose = True

            if search_query:
                matches_search = search_query in title or search_query in description or search_query in purpose
            if purpose_query:
                matches_purpose = purpose_query in purpose or purpose_query in title or purpose_query in description

            if matches_search and matches_purpose:
                filtered_tools[tid] = tool

        return render_template('ai/tools.html', tools=filtered_tools, tool_count=len(TOOLS_CATALOG), search_query=search_query, purpose_query=purpose_query)
    except Exception as e:
        print(f"AI tools page error: {e}")
        return f"Error: {e}", 500


@app.route('/ai/tools/add', methods=['POST'])
@login_required
def ai_tools_add():
    try:
        name = (request.form.get('name') or '').strip()
        url = (request.form.get('url') or '').strip()
        description = (request.form.get('description') or '').strip()
        purpose = (request.form.get('purpose') or '').strip() or 'General'

        if not name or not url or not description:
            flash('Please provide name, URL, and description for the AI tool.', 'warning')
            return redirect(url_for('ai_tools'))

        import re
        tool_key = re.sub(r'[^a-z0-9]+', '_', name.lower()).strip('_')
        if not tool_key:
            tool_key = f"tool_{len(TOOLS_CATALOG) + 1}"

        original_key = tool_key
        index = 1
        while tool_key in TOOLS_CATALOG:
            tool_key = f"{original_key}_{index}"
            index += 1

        TOOLS_CATALOG[tool_key] = {
            'name': name,
            'url': url,
            'description': description,
            'purpose': purpose
        }

        flash('Your AI tool suggestion has been added successfully.', 'success')
        return redirect(url_for('ai_tools'))
    except Exception as e:
        print(f"AI tool add error: {e}")
        flash('Could not add the AI tool. Please try again.', 'danger')
        return redirect(url_for('ai_tools'))


@app.route('/ai/launch/<tool_id>')
@login_required
def ai_launch(tool_id):
    tool = TOOLS_CATALOG.get(tool_id)
    if not tool:
        return "Tool not found", 404

    # Log usage; if user logged in, user_id will be stored by log_activity
    log_activity('ai_tool_launched', 'ai', f"Launched {tool['name']}")

    return redirect(tool['url'])


@app.route('/ai')
def ai_redirect():
    return redirect('/ai/tools')


# ==================== LEARNING MODULE ====================
@app.route('/learn')
@login_required
def learn_home():
    log_activity('module_access', 'learn', 'Accessed learning module homepage')
    platforms = [
        {'id': 'linkedin', 'name': 'LinkedIn', 'icon': 'ðŸ’¼', 'description': 'Professional networking platform'},
        {'id': 'github', 'name': 'GitHub', 'icon': 'ðŸ“', 'description': 'Code sharing and collaboration'},
        {'id': 'leetcode', 'name': 'LeetCode', 'icon': 'ðŸ’»', 'description': 'Coding practice platform'},
        {'id': 'vscode', 'name': 'VS Code', 'icon': 'ðŸ› ï¸', 'description': 'Code editor for development'},
        {'id': 'git_vscode', 'name': 'GitHub + VS Code', 'icon': 'ðŸ”—', 'description': 'Basic workflow together'},
        {'id': 'email_google', 'name': 'Email & Google Account', 'icon': 'ðŸ“§', 'description': 'Professional communication'},
        {'id': 'resume_portfolio', 'name': 'Resume & Portfolio', 'icon': 'ðŸ“„', 'description': 'Building your online presence'},
        {'id': 'coursera', 'name': 'Coursera', 'icon': 'ðŸŽ“', 'description': 'Online learning platform'},
        {'id': 'stackoverflow', 'name': 'Stack Overflow', 'icon': 'â“', 'description': 'Programming Q&A community'},
        {'id': 'apply_guide', 'name': 'Internship Apply Guide', 'icon': 'ðŸŒ', 'description': 'Trusted internship companies and official apply links'},
        {'id': 'youtube', 'name': 'YouTube Learning', 'icon': 'ðŸ“º', 'description': 'Free educational videos'},
        {'id': 'bca', 'name': 'BCA Students', 'icon': 'ðŸ’»', 'description': 'IT & Computer Applications guidance'},
        {'id': 'bsc', 'name': 'BSc Students', 'icon': 'ðŸ”¬', 'description': 'Science stream career guidance'},
        {'id': 'pharmacy', 'name': 'Pharmacy Students', 'icon': 'ðŸ’Š', 'description': 'Pharmaceutical career platforms'},
        {'id': 'medical', 'name': 'Medical Students', 'icon': 'ðŸ¥', 'description': 'MBBS & Allied Health guidance'},
        {'id': 'agriculture', 'name': 'Agriculture Students', 'icon': 'ðŸŒ¾', 'description': 'Agri-tech & farming platforms'},
        {'id': 'mpsc', 'name': 'MPSC Aspirants', 'icon': 'ðŸ“‹', 'description': 'Maharashtra PSC exam preparation'},
        {'id': 'upsc', 'name': 'UPSC Aspirants', 'icon': 'ðŸ‡®ðŸ‡³', 'description': 'Civil services exam guidance'}
    ]
    return render_template('learn/index.html', platforms=platforms)

@app.route('/learn/<platform>')
def learn_platform(platform):
    log_activity('guide_view', 'learn', f'Viewed learning guide for {platform}')
    guides = {
        'linkedin': {
            'title': 'LinkedIn - Professional Networking',
            'content': '''
            <h3>à¤•à¥à¤¯à¤¾ à¤¹à¥ˆ LinkedIn? (What is LinkedIn?)</h3>
            <p>LinkedIn à¤à¤• professional social media platform à¤¹à¥ˆ, à¤œà¤¹à¤¾à¤ à¤†à¤ª à¤…à¤ªà¤¨à¥‡ field à¤•à¥‡ à¤²à¥‹à¤—à¥‹à¤‚ à¤¸à¥‡ connect à¤•à¤° à¤¸à¤•à¤¤à¥‡ à¤¹à¥ˆà¤‚, jobs à¤–à¥‹à¤œ à¤¸à¤•à¤¤à¥‡ à¤¹à¥ˆà¤‚, à¤”à¤° à¤…à¤ªà¤¨à¥€ skills à¤¦à¤¿à¤–à¤¾ à¤¸à¤•à¤¤à¥‡ à¤¹à¥ˆà¤‚à¥¤ Think of it as Facebook for professionals!</p>

            <h3>à¤•à¥à¤¯à¥‹à¤‚ use à¤•à¤°à¥‡à¤‚? (Why use it?)</h3>
            <p>As a student, LinkedIn à¤†à¤ªà¤•à¥‹ professional network à¤¬à¤¨à¤¾à¤¨à¥‡ à¤®à¥‡à¤‚ à¤®à¤¦à¤¦ à¤•à¤°à¤¤à¤¾ à¤¹à¥ˆ, internships à¤®à¤¿à¤²à¤¤à¥€ à¤¹à¥ˆà¤‚, à¤”à¤° à¤†à¤ª different careers à¤•à¥‡ à¤¬à¤¾à¤°à¥‡ à¤®à¥‡à¤‚ learn à¤•à¤° à¤¸à¤•à¤¤à¥‡ à¤¹à¥ˆà¤‚à¥¤ à¤¯à¤¹ à¤†à¤ªà¤•à¥‡ resume à¤¸à¥‡ à¤œà¥à¤¯à¤¾à¤¦à¤¾ powerful à¤¹à¥ˆ!</p>

            <h3>Account à¤•à¥ˆà¤¸à¥‡ à¤¬à¤¨à¤¾à¤à¤? (How to create account)</h3>
            <ol>
                <li>linkedin.com à¤ªà¤° à¤œà¤¾à¤à¤ à¤”à¤° "Join now" click à¤•à¤°à¥‡à¤‚</li>
                <li>à¤…à¤ªà¤¨à¤¾ college email à¤”à¤° strong password use à¤•à¤°à¥‡à¤‚</li>
                <li>Profile complete à¤•à¤°à¥‡à¤‚ - photo, education, skills add à¤•à¤°à¥‡à¤‚</li>
                <li>Connections send à¤•à¤°à¥‡à¤‚ - teachers, seniors à¤¸à¥‡ start à¤•à¤°à¥‡à¤‚</li>
            </ol>

            <h3>Daily à¤•à¥ˆà¤¸à¥‡ use à¤•à¤°à¥‡à¤‚? (How to use daily)</h3>
            <p>Daily 10-15 minutes à¤®à¥‡à¤‚:
            <ul>
                <li>Posts à¤ªà¤¢à¤¼à¥‡à¤‚ à¤”à¤° like/comment à¤•à¤°à¥‡à¤‚</li>
                <li>1-2 connections à¤¬à¤¨à¤¾à¤à¤</li>
                <li>à¤…à¤ªà¤¨à¥€ skills à¤¯à¤¾ projects update à¤•à¤°à¥‡à¤‚</li>
                <li>Jobs section à¤®à¥‡à¤‚ internships à¤¦à¥‡à¤–à¥‡à¤‚</li>
            </ul></p>

            <h3>Common Beginner Mistakes</h3>
            <ul>
                <li>Profile incomplete à¤›à¥‹à¤¡à¤¼à¤¨à¤¾</li>
                <li>Spam messages à¤­à¥‡à¤œà¤¨à¤¾</li>
                <li>Bad profile photo use à¤•à¤°à¤¨à¤¾</li>
                <li>Connections à¤•à¥‹ ignore à¤•à¤°à¤¨à¤¾</li>
            </ul>

            <h3>Best Practices for Freshers</h3>
            <ul>
                <li>Regular updates à¤•à¤°à¥‡à¤‚ - weekly at least</li>
                <li>Meaningful connections à¤¬à¤¨à¤¾à¤à¤, not random</li>
                <li>Learn à¤•à¤°à¤¨à¥‡ à¤•à¤¾ attitude à¤°à¤–à¥‡à¤‚ - ask questions</li>
                <li>Endorsements à¤”à¤° recommendations collect à¤•à¤°à¥‡à¤‚</li>
                <li>Groups join à¤•à¤°à¥‡à¤‚ related to your field</li>
            </ul>

            <div class="alert alert-info">
                <strong>Pro Tip:</strong> LinkedIn à¤ªà¤° "Student" badge à¤®à¤¿à¤²à¤¤à¤¾ à¤¹à¥ˆà¥¤ Use it to get free premium features!
            </div>
            '''
        },
        'github': {
            'title': 'GitHub - Code Sharing Platform',
            'content': '''
            <h3>à¤•à¥à¤¯à¤¾ à¤¹à¥ˆ GitHub? (What is GitHub?)</h3>
            <p>GitHub à¤à¤• platform à¤¹à¥ˆ à¤œà¤¹à¤¾à¤ developers à¤…à¤ªà¤¨à¤¾ code share à¤•à¤°à¤¤à¥‡ à¤¹à¥ˆà¤‚, collaborate à¤•à¤°à¤¤à¥‡ à¤¹à¥ˆà¤‚, à¤”à¤° projects manage à¤•à¤°à¤¤à¥‡ à¤¹à¥ˆà¤‚à¥¤ à¤¯à¤¹ coding à¤•à¤¾ Facebook à¤¹à¥ˆ!</p>

            <h3>à¤•à¥à¤¯à¥‹à¤‚ use à¤•à¤°à¥‡à¤‚? (Why use it?)</h3>
            <p>à¤¯à¤¹ à¤†à¤ªà¤•à¥‡ coding skills à¤•à¥‹ showcase à¤•à¤°à¤¨à¥‡ à¤•à¤¾ best way à¤¹à¥ˆà¥¤ Companies à¤†à¤ªà¤•à¥‡ GitHub profile à¤¦à¥‡à¤–à¤¤à¥€ à¤¹à¥ˆà¤‚à¥¤ Plus, à¤†à¤ª open source projects à¤®à¥‡à¤‚ contribute à¤•à¤°à¤•à¥‡ learn à¤•à¤° à¤¸à¤•à¤¤à¥‡ à¤¹à¥ˆà¤‚ à¤”à¤° experience gain à¤•à¤° à¤¸à¤•à¤¤à¥‡ à¤¹à¥ˆà¤‚à¥¤</p>

            <h3>Account à¤•à¥ˆà¤¸à¥‡ à¤¬à¤¨à¤¾à¤à¤? (How to create account)</h3>
            <ol>
                <li>github.com à¤ªà¤° à¤œà¤¾à¤à¤</li>
                <li>"Sign up" click à¤•à¤°à¥‡à¤‚</li>
                <li>Unique username choose à¤•à¤°à¥‡à¤‚ (professional wala)</li>
                <li>Email verify à¤•à¤°à¥‡à¤‚</li>
                <li>Profile setup à¤•à¤°à¥‡à¤‚ - bio, photo add à¤•à¤°à¥‡à¤‚</li>
            </ol>

            <h3>Daily à¤•à¥ˆà¤¸à¥‡ use à¤•à¤°à¥‡à¤‚? (How to use daily)</h3>
            <p>Start small:
            <ul>
                <li>à¤…à¤ªà¤¨à¤¾ first repository à¤¬à¤¨à¤¾à¤à¤</li>
                <li>à¤•à¥à¤› simple code upload à¤•à¤°à¥‡à¤‚</li>
                <li>Other people's repositories explore à¤•à¤°à¥‡à¤‚</li>
                <li>Star interesting projects</li>
                <li>Issues à¤®à¥‡à¤‚ help try à¤•à¤°à¥‡à¤‚</li>
            </ul></p>

            <h3>Common Beginner Mistakes</h3>
            <ul>
                <li>Private repos à¤•à¥‹ accidentally public à¤•à¤°à¤¨à¤¾</li>
                <li>Proper commit messages à¤¨ à¤²à¤¿à¤–à¤¨à¤¾</li>
                <li>README file à¤¨ à¤¬à¤¨à¤¾à¤¨à¤¾</li>
                <li>Code à¤•à¥‹ organize à¤¨ à¤•à¤°à¤¨à¤¾</li>
            </ul>

            <h3>Best Practices for Freshers</h3>
            <ul>
                <li>Regular contributions à¤•à¤°à¥‡à¤‚ (daily if possible)</li>
                <li>README.md file à¤œà¤°à¥‚à¤° à¤¬à¤¨à¤¾à¤à¤ with project description</li>
                <li>Projects à¤•à¥‹ meaningful names à¤¦à¥‡à¤‚</li>
                <li>Contribute to open source - start with documentation</li>
                <li>Follow other developers in your field</li>
            </ul>

            <div class="alert alert-success">
                <strong>Motivation:</strong> Many students got internships just because of their GitHub profile!
            </div>
            '''
        },
        'leetcode': {
            'title': 'LeetCode - Coding Practice',
            'content': '''
            <h3>à¤•à¥à¤¯à¤¾ à¤¹à¥ˆ LeetCode? (What is LeetCode?)</h3>
            <p>LeetCode à¤à¤• platform à¤¹à¥ˆ à¤œà¤¹à¤¾à¤ à¤†à¤ª coding problems solve à¤•à¤° à¤¸à¤•à¤¤à¥‡ à¤¹à¥ˆà¤‚, à¤œà¥‹ real interviews à¤®à¥‡à¤‚ à¤ªà¥‚à¤›à¥‡ à¤œà¤¾à¤¤à¥‡ à¤¹à¥ˆà¤‚à¥¤ à¤¯à¤¹ coding à¤•à¤¾ gym à¤¹à¥ˆ!</p>

            <h3>à¤•à¥à¤¯à¥‹à¤‚ use à¤•à¤°à¥‡à¤‚? (Why use it?)</h3>
            <p>à¤¯à¤¹ à¤†à¤ªà¤•à¥‡ problem-solving skills à¤•à¥‹ improve à¤•à¤°à¤¤à¤¾ à¤¹à¥ˆ à¤”à¤° coding interviews à¤•à¥€ preparation à¤®à¥‡à¤‚ à¤®à¤¦à¤¦ à¤•à¤°à¤¤à¤¾ à¤¹à¥ˆà¥¤ Companies like Google, Amazon à¤†à¤ªà¤•à¥‡ LeetCode performance à¤¦à¥‡à¤–à¤¤à¥€ à¤¹à¥ˆà¤‚à¥¤</p>

            <h3>Account à¤•à¥ˆà¤¸à¥‡ à¤¬à¤¨à¤¾à¤à¤? (How to create account)</h3>
            <ol>
                <li>leetcode.com à¤ªà¤° à¤œà¤¾à¤à¤</li>
                <li>"Sign up" click à¤•à¤°à¥‡à¤‚</li>
                <li>Email à¤”à¤° password enter à¤•à¤°à¥‡à¤‚</li>
                <li>Programming language select à¤•à¤°à¥‡à¤‚ (Python recommend for beginners)</li>
            </ol>

            <h3>Daily à¤•à¥ˆà¤¸à¥‡ use à¤•à¤°à¥‡à¤‚? (How to use daily)</h3>
            <p>Consistency is key:
            <ul>
                <li>Daily 1 problem solve à¤•à¤°à¥‡à¤‚</li>
                <li>Easy à¤¸à¥‡ start à¤•à¤°à¥‡à¤‚</li>
                <li>Solution à¤•à¥‹ analyze à¤•à¤°à¥‡à¤‚</li>
                <li>Discussion section à¤ªà¤¢à¤¼à¥‡à¤‚</li>
                <li>Weekly contests à¤®à¥‡à¤‚ participate à¤•à¤°à¥‡à¤‚</li>
            </ul></p>

            <h3>Common Beginner Mistakes</h3>
            <ul>
                <li>à¤¸à¤­à¥€ solutions copy à¤•à¤°à¤¨à¤¾</li>
                <li>Time complexity à¤•à¥‹ ignore à¤•à¤°à¤¨à¤¾</li>
                <li>Only easy problems à¤•à¤°à¤¨à¤¾</li>
                <li>Without understanding submit à¤•à¤°à¤¨à¤¾</li>
            </ul>

            <h3>Best Practices for Freshers</h3>
            <ul>
                <li>Consistent practice à¤•à¤°à¥‡à¤‚ - daily 1 hour</li>
                <li>Different topics cover à¤•à¤°à¥‡à¤‚ (arrays, strings, trees, etc.)</li>
                <li>Multiple approaches try à¤•à¤°à¥‡à¤‚</li>
                <li>Streak maintain à¤•à¤°à¥‡à¤‚</li>
                <li>Study plans follow à¤•à¤°à¥‡à¤‚</li>
            </ul>

            <div class="alert alert-warning">
                <strong>Remember:</strong> Quality over quantity. à¤¸à¤®à¤à¤•à¤° solve à¤•à¤°à¥‡à¤‚!
            </div>
            '''
        },
        'vscode': {
            'title': 'VS Code - Code Editor',
            'content': '''
            <h3>à¤•à¥à¤¯à¤¾ à¤¹à¥ˆ VS Code? (What is VS Code?)</h3>
            <p>VS Code à¤à¤• free, powerful code editor à¤¹à¥ˆ à¤œà¥‹ developers use à¤•à¤°à¤¤à¥‡ à¤¹à¥ˆà¤‚ code à¤²à¤¿à¤–à¤¨à¥‡, debug à¤•à¤°à¤¨à¥‡, à¤”à¤° projects manage à¤•à¤°à¤¨à¥‡ à¤•à¥‡ à¤²à¤¿à¤à¥¤ à¤¯à¤¹ coding à¤•à¤¾ Swiss Army knife à¤¹à¥ˆ!</p>

            <h3>à¤•à¥à¤¯à¥‹à¤‚ use à¤•à¤°à¥‡à¤‚? (Why use it?)</h3>
            <p>à¤¯à¤¹ easy to learn à¤¹à¥ˆ, à¤¸à¤­à¥€ programming languages support à¤•à¤°à¤¤à¤¾ à¤¹à¥ˆ, à¤”à¤° extensions à¤¸à¥‡ super powerful à¤¬à¤¨ à¤œà¤¾à¤¤à¤¾ à¤¹à¥ˆà¥¤ Professional developers à¤•à¤¾ favorite tool à¤¹à¥ˆà¥¤</p>

            <h3>à¤•à¥ˆà¤¸à¥‡ install à¤•à¤°à¥‡à¤‚? (How to install)</h3>
            <ol>
                <li>code.visualstudio.com à¤ªà¤° à¤œà¤¾à¤à¤</li>
                <li>"Download" click à¤•à¤°à¥‡à¤‚ (right version for your OS)</li>
                <li>Install à¤•à¤°à¥‡à¤‚ (next-next finish)</li>
                <li>Open à¤•à¤°à¥‡à¤‚ à¤”à¤° "Get Started" tour à¤•à¤°à¥‡à¤‚</li>
            </ol>

            <h3>Daily à¤•à¥ˆà¤¸à¥‡ use à¤•à¤°à¥‡à¤‚? (How to use daily)</h3>
            <p>Make it your daily companion:
            <ul>
                <li>Coding practice à¤•à¤°à¥‡à¤‚</li>
                <li>Extensions explore à¤•à¤°à¥‡à¤‚</li>
                <li>Keyboard shortcuts learn à¤•à¤°à¥‡à¤‚</li>
                <li>Themes change à¤•à¤°à¥‡à¤‚ for fun</li>
            </ul></p>

            <h3>Common Beginner Mistakes</h3>
            <ul>
                <li>Too many extensions install à¤•à¤°à¤¨à¤¾</li>
                <li>Settings à¤•à¥‹ customize à¤¨ à¤•à¤°à¤¨à¤¾</li>
                <li>Keyboard shortcuts à¤¨ learn à¤•à¤°à¤¨à¤¾</li>
                <li>Files à¤•à¥‹ unsaved à¤›à¥‹à¤¡à¤¼à¤¨à¤¾</li>
            </ul>

            <h3>Best Practices for Freshers</h3>
            <ul>
                <li>Essential extensions install à¤•à¤°à¥‡à¤‚ (Python, Git, etc.)</li>
                <li>Settings customize à¤•à¤°à¥‡à¤‚ (font size, theme)</li>
                <li>Keyboard shortcuts master à¤•à¤°à¥‡à¤‚</li>
                <li>Projects à¤•à¥‹ organized folders à¤®à¥‡à¤‚ à¤°à¤–à¥‡à¤‚</li>
                <li>Version control (Git) integrate à¤•à¤°à¥‡à¤‚</li>
            </ul>

            <div class="alert alert-info">
                <strong>Pro Tip:</strong> VS Code has built-in terminal, debugger, and Git integration!
            </div>
            '''
        },
        'git_vscode': {
            'title': 'GitHub + VS Code Workflow',
            'content': '''
            <h3>à¤•à¥à¤¯à¤¾ à¤¹à¥ˆ à¤¯à¤¹ workflow? (What is this workflow?)</h3>
            <p>GitHub à¤”à¤° VS Code à¤•à¥‹ together use à¤•à¤°à¤•à¥‡ à¤†à¤ª code à¤²à¤¿à¤– à¤¸à¤•à¤¤à¥‡ à¤¹à¥ˆà¤‚, changes track à¤•à¤° à¤¸à¤•à¤¤à¥‡ à¤¹à¥ˆà¤‚, à¤”à¤° online share à¤•à¤° à¤¸à¤•à¤¤à¥‡ à¤¹à¥ˆà¤‚à¥¤ à¤¯à¤¹ modern development à¤•à¤¾ standard way à¤¹à¥ˆ!</p>

            <h3>à¤•à¥à¤¯à¥‹à¤‚ use à¤•à¤°à¥‡à¤‚? (Why use it?)</h3>
            <p>à¤¯à¤¹ version control à¤”à¤° collaboration à¤•à¥‹ easy à¤¬à¤¨à¤¾à¤¤à¤¾ à¤¹à¥ˆà¥¤ à¤†à¤ª à¤…à¤ªà¤¨à¥‡ code à¤•à¥‹ safely store à¤•à¤° à¤¸à¤•à¤¤à¥‡ à¤¹à¥ˆà¤‚ à¤”à¤° team à¤®à¥‡à¤‚ work à¤•à¤° à¤¸à¤•à¤¤à¥‡ à¤¹à¥ˆà¤‚à¥¤</p>

            <h3>à¤•à¥ˆà¤¸à¥‡ setup à¤•à¤°à¥‡à¤‚? (How to setup)</h3>
            <ol>
                <li>VS Code à¤®à¥‡à¤‚ Git extension install à¤•à¤°à¥‡à¤‚ (usually pre-installed)</li>
                <li>GitHub à¤¸à¥‡ repository clone à¤•à¤°à¥‡à¤‚ (VS Code à¤®à¥‡à¤‚ Ctrl+Shift+P â†’ Git: Clone)</li>
                <li>Code à¤²à¤¿à¤–à¥‡à¤‚ à¤”à¤° save à¤•à¤°à¥‡à¤‚</li>
                <li>Changes commit à¤•à¤°à¥‡à¤‚ (Source Control panel à¤®à¥‡à¤‚)</li>
                <li>Push à¤•à¤°à¥‡à¤‚ to GitHub</li>
            </ol>

            <h3>Daily à¤•à¥ˆà¤¸à¥‡ use à¤•à¤°à¥‡à¤‚? (How to use daily)</h3>
            <p>Simple routine:
            <ul>
                <li>Morning: Pull latest changes</li>
                <li>Code à¤²à¤¿à¤–à¥‡à¤‚ à¤”à¤° test à¤•à¤°à¥‡à¤‚</li>
                <li>Evening: Commit à¤”à¤° push à¤•à¤°à¥‡à¤‚</li>
                <li>Issues check à¤•à¤°à¥‡à¤‚ à¤”à¤° help à¤•à¤°à¥‡à¤‚</li>
            </ul></p>

            <h3>Common Beginner Mistakes</h3>
            <ul>
                <li>Merge conflicts à¤•à¥‹ fear à¤•à¤°à¤¨à¤¾</li>
                <li>Large files commit à¤•à¤°à¤¨à¤¾</li>
                <li>Commit messages à¤®à¥‡à¤‚ "fixed" à¤²à¤¿à¤–à¤¨à¤¾</li>
                <li>Push à¤•à¤°à¤¨à¥‡ à¤¸à¥‡ à¤ªà¤¹à¤²à¥‡ test à¤¨ à¤•à¤°à¤¨à¤¾</li>
            </ul>

            <h3>Best Practices for Freshers</h3>
            <ul>
                <li>Small, frequent commits à¤•à¤°à¥‡à¤‚</li>
                <li>Descriptive commit messages à¤²à¤¿à¤–à¥‡à¤‚</li>
                <li>Before push, code review à¤•à¤°à¥‡à¤‚</li>
                <li>Branching learn à¤•à¤°à¥‡à¤‚ for features</li>
                <li>README à¤”à¤° .gitignore à¤œà¤°à¥‚à¤° à¤¬à¤¨à¤¾à¤à¤</li>
            </ul>

            <div class="alert alert-success">
                <strong>Power Combo:</strong> VS Code + GitHub = Professional Developer Setup!
            </div>
            '''
        },
        'email_google': {
            'title': 'Email & Google Account',
            'content': '''
            <h3>à¤•à¥à¤¯à¤¾ à¤¹à¥ˆ Professional Email? (What is Professional Email?)</h3>
            <p>Professional communication à¤•à¥‡ à¤²à¤¿à¤ separate email accountà¥¤ à¤¯à¤¹ à¤†à¤ªà¤•à¥‡ personal à¤”à¤° work emails à¤•à¥‹ separate à¤°à¤–à¤¤à¤¾ à¤¹à¥ˆà¥¤</p>

            <h3>à¤•à¥à¤¯à¥‹à¤‚ use à¤•à¤°à¥‡à¤‚? (Why use it?)</h3>
            <p>Companies à¤”à¤° professors à¤†à¤ªà¤•à¥‡ email à¤¸à¥‡ à¤†à¤ªà¤•à¤¾ impression à¤¬à¤¨à¤¾à¤¤à¥‡ à¤¹à¥ˆà¤‚à¥¤ Professional email à¤¸à¥‡ à¤†à¤ª serious à¤”à¤° organized à¤²à¤—à¤¤à¥‡ à¤¹à¥ˆà¤‚à¥¤</p>

            <h3>à¤•à¥ˆà¤¸à¥‡ setup à¤•à¤°à¥‡à¤‚? (How to setup)</h3>
            <ol>
                <li>gmail.com à¤ªà¤° à¤œà¤¾à¤à¤</li>
                <li>"Create account" click à¤•à¤°à¥‡à¤‚</li>
                <li>Professional name use à¤•à¤°à¥‡à¤‚ (first.last or something)</li>
                <li>Recovery email à¤”à¤° phone add à¤•à¤°à¥‡à¤‚</li>
                <li>Signature setup à¤•à¤°à¥‡à¤‚ with your name and contact</li>
            </ol>

            <h3>Daily à¤•à¥ˆà¤¸à¥‡ use à¤•à¤°à¥‡à¤‚? (How to use daily)</h3>
            <p>Professional habits:
            <ul>
                <li>Morning à¤®à¥‡à¤‚ emails check à¤•à¤°à¥‡à¤‚</li>
                <li>Within 24 hours reply à¤•à¤°à¥‡à¤‚</li>
                <li>Spam folder clean à¤•à¤°à¥‡à¤‚</li>
                <li>Important emails à¤•à¥‹ label à¤•à¤°à¥‡à¤‚</li>
            </ul></p>

            <h3>Common Beginner Mistakes</h3>
            <ul>
                <li>Funny email addresses use à¤•à¤°à¤¨à¤¾</li>
                <li>Emails à¤•à¥‹ unread à¤›à¥‹à¤¡à¤¼à¤¨à¤¾</li>
                <li>Personal à¤”à¤° professional mix à¤•à¤°à¤¨à¤¾</li>
                <li>Bad subject lines à¤²à¤¿à¤–à¤¨à¤¾</li>
            </ul>

            <h3>Best Practices for Freshers</h3>
            <ul>
                <li>Clear, professional subject lines use à¤•à¤°à¥‡à¤‚</li>
                <li>Proper greeting à¤”à¤° closing use à¤•à¤°à¥‡à¤‚</li>
                <li>Grammar check à¤•à¤°à¥‡à¤‚ before sending</li>
                <li>Attachments à¤•à¥‹ properly name à¤•à¤°à¥‡à¤‚</li>
                <li>Follow-up emails à¤­à¥‡à¤œà¥‡à¤‚ if needed</li>
            </ul>

            <div class="alert alert-info">
                <strong>Pro Tip:</strong> Use Google Calendar for scheduling and Google Drive for file sharing!
            </div>
            '''
        },
        'resume_portfolio': {
            'title': 'Resume & Portfolio',
            'content': '''
            <h3>à¤•à¥à¤¯à¤¾ à¤¹à¥ˆ Resume à¤”à¤° Portfolio? (What are Resume and Portfolio?)</h3>
            <p>Resume à¤†à¤ªà¤•à¥‡ skills à¤”à¤° experience à¤•à¤¾ 1-page summary à¤¹à¥ˆà¥¤ Portfolio à¤†à¤ªà¤•à¥‡ work à¤•à¤¾ detailed showcase à¤¹à¥ˆ - projects, achievements, etc.</p>

            <h3>à¤•à¥à¤¯à¥‹à¤‚ à¤¬à¤¨à¤¾à¤à¤? (Why create them?)</h3>
            <p>Jobs, internships, à¤”à¤° admissions à¤•à¥‡ à¤²à¤¿à¤ essential à¤¹à¥ˆà¤‚à¥¤ Resume à¤¸à¥‡ companies à¤†à¤ªà¤•à¤¾ overview à¤®à¤¿à¤²à¤¤à¤¾ à¤¹à¥ˆ, portfolio à¤¸à¥‡ proof!</p>

            <h3>à¤•à¥ˆà¤¸à¥‡ à¤¬à¤¨à¤¾à¤à¤? (How to create)</h3>
            <h4>Resume:</h4>
            <ol>
                <li>Simple format choose à¤•à¤°à¥‡à¤‚ (Google Docs à¤¯à¤¾ Canva)</li>
                <li>Contact info, education, skills add à¤•à¤°à¥‡à¤‚</li>
                <li>Projects à¤”à¤° achievements highlight à¤•à¤°à¥‡à¤‚</li>
                <li>PDF format à¤®à¥‡à¤‚ save à¤•à¤°à¥‡à¤‚</li>
            </ol>

            <h4>Portfolio:</h4>
            <ol>
                <li>GitHub Pages use à¤•à¤°à¥‡à¤‚ (free)</li>
                <li>à¤…à¤ªà¤¨à¥‡ projects showcase à¤•à¤°à¥‡à¤‚</li>
                <li>About à¤”à¤° contact page add à¤•à¤°à¥‡à¤‚</li>
                <li>Live link share à¤•à¤°à¥‡à¤‚</li>
            </ol>

            <h3>Common Beginner Mistakes</h3>
            <ul>
                <li>Resume à¤•à¥‹ 2+ pages à¤¬à¤¨à¤¾à¤¨à¤¾</li>
                <li>Too much information add à¤•à¤°à¤¨à¤¾</li>
                <li>Portfolio à¤•à¥‹ incomplete à¤›à¥‹à¤¡à¤¼à¤¨à¤¾</li>
                <li>Bad design choose à¤•à¤°à¤¨à¤¾</li>
            </ul>

            <h3>Best Practices for Freshers</h3>
            <ul>
                <li>Keep resume to 1 page</li>
                <li>Use action words (Developed, Created, etc.)</li>
                <li>Quantify achievements (numbers use à¤•à¤°à¥‡à¤‚)</li>
                <li>Regularly update à¤•à¤°à¥‡à¤‚</li>
                <li>Tailor for each application</li>
            </ul>

            <div class="alert alert-success">
                <strong>Remember:</strong> Your portfolio is your digital business card!
            </div>
            '''
        },
        'coursera': {
            'title': 'Coursera - Online Learning',
            'content': '''
            <h3>à¤•à¥à¤¯à¤¾ à¤¹à¥ˆ Coursera? (What is Coursera?)</h3>
            <p>Coursera à¤à¤• online learning platform à¤¹à¥ˆ à¤œà¤¹à¤¾à¤ top universities à¤•à¥‡ courses à¤®à¤¿à¤²à¤¤à¥‡ à¤¹à¥ˆà¤‚à¥¤ à¤¯à¤¹ college à¤•à¤¾ extension à¤¹à¥ˆ!</p>

            <h3>à¤•à¥à¤¯à¥‹à¤‚ use à¤•à¤°à¥‡à¤‚? (Why use it?)</h3>
            <p>à¤¯à¤¹ à¤†à¤ªà¤•à¥‹ world-class education à¤¦à¥‡à¤¤à¤¾ à¤¹à¥ˆà¥¤ Certificates à¤®à¤¿à¤²à¤¤à¥‡ à¤¹à¥ˆà¤‚ à¤œà¥‹ resume à¤®à¥‡à¤‚ add à¤¹à¥‹ à¤¸à¤•à¤¤à¥‡ à¤¹à¥ˆà¤‚à¥¤</p>

            <h3>à¤•à¥ˆà¤¸à¥‡ start à¤•à¤°à¥‡à¤‚? (How to start)</h3>
            <ol>
                <li>coursera.org à¤ªà¤° à¤œà¤¾à¤à¤</li>
                <li>Free account à¤¬à¤¨à¤¾à¤à¤</li>
                <li>Courses browse à¤•à¤°à¥‡à¤‚</li>
                <li>Audit mode à¤®à¥‡à¤‚ free access à¤²à¥‡à¤‚</li>
            </ol>

            <h3>Best Practices</h3>
            <ul>
                <li>Weekly schedule à¤¬à¤¨à¤¾à¤à¤</li>
                <li>Assignments complete à¤•à¤°à¥‡à¤‚</li>
                <li>Discussion forums à¤®à¥‡à¤‚ participate à¤•à¤°à¥‡à¤‚</li>
            </ul>
            '''
        },
        'stackoverflow': {
            'title': 'Stack Overflow - Programming Q&A',
            'content': '''
            <h3>à¤•à¥à¤¯à¤¾ à¤¹à¥ˆ Stack Overflow? (What is Stack Overflow?)</h3>
            <p>Programming à¤•à¤¾ largest Q&A communityà¥¤ à¤œà¤¬ à¤­à¥€ stuck à¤¹à¥‹à¤‚, à¤¯à¤¹à¤¾à¤ answer à¤®à¤¿à¤²à¥‡à¤—à¤¾!</p>

            <h3>à¤•à¥à¤¯à¥‹à¤‚ use à¤•à¤°à¥‡à¤‚? (Why use it?)</h3>
            <p>Learn à¤•à¤°à¤¨à¥‡ à¤•à¥‡ à¤²à¤¿à¤ best placeà¥¤ Questions à¤ªà¥‚à¤›à¥‡à¤‚ à¤”à¤° answers à¤¦à¥‡à¤‚à¥¤</p>

            <h3>à¤•à¥ˆà¤¸à¥‡ use à¤•à¤°à¥‡à¤‚? (How to use)</h3>
            <ol>
                <li>stackoverflow.com à¤ªà¤° à¤œà¤¾à¤à¤</li>
                <li>Account à¤¬à¤¨à¤¾à¤à¤</li>
                <li>Questions search à¤•à¤°à¥‡à¤‚</li>
                <li>Helpful answers upvote à¤•à¤°à¥‡à¤‚</li>
            </ol>

            <h3>Best Practices</h3>
            <ul>
                <li>Proper questions à¤ªà¥‚à¤›à¥‡à¤‚</li>
                <li>Answers à¤•à¥‹ research à¤•à¤°à¥‡à¤‚</li>
                <li>Helpful à¤¬à¤¨à¥‡à¤‚</li>
            </ul>
            '''
        },
        'apply_guide': {
            'title': 'Internship Apply Guide - Trusted Companies & Official Links',
            'content': '''
            <h3>About this Apply Guide</h3>
            <p>This page provides a curated and professional roadmap for internship applications across major industries and Maharashtra regions. It is designed to help students identify reputable companies, use verified career pages, and make more informed application decisions.</p>

            <h3>How to use this guide</h3>
            <ul>
                <li>Choose the industry that best fits your skills and interests.</li>
                <li>Visit the official career page for each company before applying.</li>
                <li>Use platforms such as Internshala, LinkedIn, Naukri.com and AngelList carefully for verified listings.</li>
                <li>Apply early, prepare a polished resume, and write a concise cover note.</li>
            </ul>

            <h3>Top companies by field</h3>
            <div class="company-section">
                <p><strong>Technology & IT:</strong> Google, Microsoft, Amazon, Adobe, IBM</p>
                <p><strong>Core Engineering:</strong> Larsen & Toubro (L&T), Tata Motors, Mahindra & Mahindra, Siemens, Bosch</p>
                <p><strong>Finance & Consulting:</strong> Deloitte, EY, PwC, KPMG, Goldman Sachs</p>
                <p><strong>Pharma & Healthcare:</strong> Sun Pharma, Dr. Reddy's Laboratories, Cipla, Apollo Hospitals</p>
                <p><strong>Marketing & Business:</strong> Unilever, Procter & Gamble (P&G), Zomato, Swiggy</p>
            </div>

            <h3>Trusted internship platforms</h3>
            <div class="company-section">
                <ul>
                    <li><strong>Internshala</strong> - Student-focused internship listings</li>
                    <li><strong>LinkedIn</strong> - Professional networking and job opportunities</li>
                    <li><strong>Naukri.com</strong> - Comprehensive job and internship portal</li>
                    <li><strong>AngelList (Wellfound)</strong> - Startup and tech company listings</li>
                </ul>
            </div>

            <h3>Strong Maharashtra internship hubs</h3>
            <div class="row">
                <div class="col-md-4">
                    <div class="company-section">
                        <h4>Pune</h4>
                        <ul>
                            <li>Persistent Systems</li>
                            <li>KPIT Technologies</li>
                            <li>Zensar Technologies</li>
                            <li>Cybage</li>
                            <li>Veritas Technologies</li>
                            <li>PubMatic</li>
                            <li>MindTickle</li>
                            <li>Icertis</li>
                        </ul>
                    </div>
                </div>
                <div class="col-md-4">
                    <div class="company-section">
                        <h4>Mumbai</h4>
                        <ul>
                            <li>Morgan Stanley</li>
                            <li>JPMorgan Chase</li>
                            <li>Nomura</li>
                            <li>CRISIL</li>
                            <li>Tata Capital</li>
                            <li>Aditya Birla Group</li>
                            <li>Nykaa</li>
                            <li>BookMyShow</li>
                        </ul>
                    </div>
                </div>
                <div class="col-md-4">
                    <div class="company-section">
                        <h4>Nashik</h4>
                        <ul>
                            <li>Mahindra Sanyo Special Steel</li>
                            <li>Kirloskar Oil Engines</li>
                            <li>CEAT</li>
                            <li>Hindustan Aeronautics Limited (HAL)</li>
                            <li>Crompton Greaves</li>
                            <li>Bosch India</li>
                        </ul>
                    </div>
                </div>
            </div>

            <h3>Industry strengths in Maharashtra</h3>
            <div class="company-section">
                <p><strong>Manufacturing & Industrial:</strong> Bajaj Auto, Thermax, Forbes Marshall, Finolex Industries</p>
                <p><strong>Analytics, Data & Product:</strong> Fractal Analytics, Mu Sigma, Quantiphi, Tredence</p>
                <p><strong>Fast-growing startups:</strong> Razorpay, CRED, Meesho, Upstox</p>
            </div>

            <h3>Why this list matters</h3>
            <ul>
                <li>Combines local and national companies with high internship potential.</li>
                <li>Focuses on safe application behavior and verified opportunities.</li>
                <li>Helps students select employers that match their skills and goals.</li>
                <li>Supports Maharashtra students with regional company recommendations.</li>
            </ul>

            <h3>Application best practices</h3>
            <div class="company-section">
                <ul>
                    <li><strong>Official channels only:</strong> Always use official career pages or trusted employer websites.</li>
                    <li><strong>Avoid suspicious links:</strong> Do not use unknown, suspicious, or unverified links.</li>
                    <li><strong>Tailored applications:</strong> Customize your resume and cover note for each internship.</li>
                    <li><strong>Track applications:</strong> Maintain a tracking sheet for applications, interviews and follow-ups.</li>
                    <li><strong>Balance opportunities:</strong> Apply to both large firms and strong startups.</li>
                </ul>
            </div>
            '''
        },
        'youtube': {
            'title': 'YouTube Learning Channels',
            'content': '''
            <h3>à¤•à¥à¤¯à¤¾ à¤¹à¥ˆ YouTube Learning? (What is YouTube Learning?)</h3>
            <p>YouTube à¤ªà¤° free educational content à¤•à¤¾ ocean à¤¹à¥ˆà¥¤ Videos à¤¸à¥‡ learn à¤•à¤°à¤¨à¤¾ easy à¤¹à¥ˆ!</p>

            <h3>à¤•à¥à¤¯à¥‹à¤‚ use à¤•à¤°à¥‡à¤‚? (Why use it?)</h3>
            <p>Visual learning best à¤¹à¥ˆà¥¤ Free resources à¤®à¤¿à¤²à¤¤à¥‡ à¤¹à¥ˆà¤‚à¥¤</p>

            <h3>Recommended Channels</h3>
            <ul>
                <li>freeCodeCamp</li>
                <li>Traversy Media</li>
                <li>CS Dojo</li>
                <li>Programming with Mosh</li>
            </ul>

            <h3>Best Practices</h3>
            <ul>
                <li>Playlist follow à¤•à¤°à¥‡à¤‚</li>
                <li>Notes à¤¬à¤¨à¤¾à¤¤à¥‡ à¤œà¤¾à¤à¤</li>
                <li>Practice à¤•à¤°à¤¤à¥‡ à¤œà¤¾à¤à¤</li>
            </ul>
            '''
        },
        'bca': {
            'title': 'BCA Students - IT Career Guidance',
            'content': '''
            <h3>BCA à¤•à¥à¤¯à¤¾ à¤¹à¥ˆ? (What is BCA?)</h3>
            <p>BCA (Bachelor of Computer Applications) computer science à¤•à¤¾ graduation course à¤¹à¥ˆà¥¤ à¤¯à¤¹ IT field à¤®à¥‡à¤‚ strong foundation à¤¦à¥‡à¤¤à¤¾ à¤¹à¥ˆà¥¤</p>

            <h3>à¤•à¥ˆà¤°à¤¿à¤¯à¤° à¤•à¥‡ à¤²à¤¿à¤ à¤œà¤°à¥‚à¤°à¥€ Platforms (Essential Platforms for Career)</h3>

            <h4>1. LinkedIn</h4>
            <p>IT jobs à¤•à¥‡ à¤²à¤¿à¤ mustà¥¤ Profile à¤¬à¤¨à¤¾à¤à¤ à¤”à¤° IT companies follow à¤•à¤°à¥‡à¤‚à¥¤</p>

            <h4>2. GitHub</h4>
            <p>Code showcase à¤•à¤°à¤¨à¥‡ à¤•à¥‡ à¤²à¤¿à¤à¥¤ Mini projects upload à¤•à¤°à¥‡à¤‚à¥¤</p>

            <h4>3. LeetCode / HackerRank</h4>
            <p>Coding skills improve à¤•à¤°à¤¨à¥‡ à¤•à¥‡ à¤²à¤¿à¤à¥¤ Daily practice à¤•à¤°à¥‡à¤‚à¥¤</p>

            <h4>4. Coursera / Udemy</h4>
            <p>IT certifications à¤•à¥‡ à¤²à¤¿à¤à¥¤ Python, Java, Web Development courses à¤²à¥‡à¤‚à¥¤</p>

            <h4>5. Stack Overflow</h4>
            <p>Programming doubts solve à¤•à¤°à¤¨à¥‡ à¤•à¥‡ à¤²à¤¿à¤à¥¤</p>

            <h3>Daily Routine à¤¬à¤¨à¤¾à¤à¤ (Create Daily Routine)</h3>
            <ul>
                <li>1 hour coding practice</li>
                <li>LinkedIn à¤ªà¤° 10 posts à¤ªà¤¢à¤¼à¥‡à¤‚</li>
                <li>1 new technology learn à¤•à¤°à¥‡à¤‚</li>
                <li>GitHub à¤ªà¤° code upload à¤•à¤°à¥‡à¤‚</li>
            </ul>

            <h3>Common Mistakes BCA Students Do</h3>
            <ul>
                <li>Only theory à¤ªà¤¢à¤¼à¤¨à¤¾, practical à¤•à¤® à¤•à¤°à¤¨à¤¾</li>
                <li>Resume à¤®à¥‡à¤‚ projects à¤¨ à¤¡à¤¾à¤²à¤¨à¤¾</li>
                <li>Soft skills ignore à¤•à¤°à¤¨à¤¾</li>
                <li>Internships à¤¨ à¤•à¤°à¤¨à¤¾</li>
            </ul>

            <h3>Best Career Tips</h3>
            <ul>
                <li>6th semester à¤®à¥‡à¤‚ internship à¤œà¤°à¥‚à¤° à¤•à¤°à¥‡à¤‚</li>
                <li>Multiple programming languages learn à¤•à¤°à¥‡à¤‚</li>
                <li>Real projects à¤¬à¤¨à¤¾à¤à¤</li>
                <li>Networking à¤•à¤°à¥‡à¤‚ - tech events attend à¤•à¤°à¥‡à¤‚</li>
                <li>English communication improve à¤•à¤°à¥‡à¤‚</li>
            </ul>

            <div class="alert alert-success">
                <strong>Pro Tip:</strong> BCA à¤•à¥‡ à¤¬à¤¾à¤¦ MCA à¤¯à¤¾ IT jobs - à¤¦à¥‹à¤¨à¥‹à¤‚ options open à¤¹à¥ˆà¤‚!
            </div>
            '''
        },
        'bsc': {
            'title': 'BSc Students - Science Career Guidance',
            'content': '''
            <h3>BSc à¤•à¥à¤¯à¤¾ à¤¹à¥ˆ? (What is BSc?)</h3>
            <p>BSc (Bachelor of Science) science subjects à¤®à¥‡à¤‚ specialization à¤¦à¥‡à¤¤à¤¾ à¤¹à¥ˆ - Physics, Chemistry, Mathematics, Biology, etc.</p>

            <h3>Domain-wise Career Platforms</h3>

            <h4>For Mathematics/Statistics:</h4>
            <ul>
                <li>Kaggle - Data science competitions</li>
                <li>Coursera - Data Science courses</li>
                <li>LinkedIn - Analytics job connections</li>
            </ul>

            <h4>For Physics/Chemistry:</h4>
            <ul>
                <li>ResearchGate - Research papers</li>
                <li>Google Scholar - Academic papers</li>
                <li>LinkedIn - R&D job opportunities</li>
            </ul>

            <h4>For Biology/Microbiology:</h4>
            <ul>
                <li>PubMed - Medical research</li>
                <li>NCBI databases</li>
                <li>Biotech company websites</li>
            </ul>

            <h3>Essential Skills to Learn</h3>
            <ul>
                <li>MS Excel advanced</li>
                <li>Basic programming (Python/R)</li>
                <li>Research paper writing</li>
                <li>Laboratory techniques</li>
                <li>Scientific communication</li>
            </ul>

            <h3>Career Options After BSc</h3>
            <ul>
                <li>MSc continuation</li>
                <li>Teaching jobs</li>
                <li>Research assistant</li>
                <li>Quality control in industries</li>
                <li>Data analyst roles</li>
            </ul>

            <h3>Common Mistakes</h3>
            <ul>
                <li>Only classroom learning</li>
                <li>No practical exposure</li>
                <li>Ignoring competitive exams</li>
                <li>Not building networks</li>
            </ul>

            <h3>Best Practices</h3>
            <ul>
                <li>Summer internships à¤•à¤°à¥‡à¤‚</li>
                <li>Scientific journals à¤ªà¤¢à¤¼à¥‡à¤‚</li>
                <li>Projects à¤”à¤° research work à¤•à¤°à¥‡à¤‚</li>
                <li>English à¤”à¤° communication skills develop à¤•à¤°à¥‡à¤‚</li>
                <li>Online certifications à¤²à¥‡à¤‚</li>
            </ul>

            <div class="alert alert-info">
                <strong>Remember:</strong> BSc flexible degree à¤¹à¥ˆ - many career paths open!
            </div>
            '''
        },
        'pharmacy': {
            'title': 'Pharmacy Students - Pharmaceutical Career Guidance',
            'content': '''
            <h3>Pharmacy Course à¤•à¥à¤¯à¤¾ à¤¹à¥ˆ? (What is Pharmacy?)</h3>
            <p>Pharmacy medicines, drugs, à¤”à¤° healthcare à¤¸à¥‡ related field à¤¹à¥ˆà¥¤ B.Pharm à¤¯à¤¾ D.Pharm à¤¸à¥‡ career options à¤¬à¤¹à¥à¤¤ à¤¹à¥ˆà¤‚à¥¤</p>

            <h3>Essential Platforms for Pharmacy Students</h3>

            <h4>1. LinkedIn</h4>
            <p>Pharma companies, hospitals, medical representatives à¤•à¥‡ à¤¸à¤¾à¤¥ connect à¤•à¤°à¥‡à¤‚à¥¤</p>

            <h4>2. Research Platforms</h4>
            <ul>
                <li>PubMed - Medical research papers</li>
                <li>Google Scholar - Academic research</li>
                <li>ClinicalTrials.gov - Drug trials</li>
            </ul>

            <h4>3. Pharma Job Portals</h4>
            <ul>
                <li>PharmaJobs.com</li>
                <li> Naukri.com (Pharma section)</li>
                <li>Monster India</li>
            </ul>

            <h4>4. Learning Platforms</h4>
            <ul>
                <li>Coursera - Pharmacology courses</li>
                <li>edX - Pharmacy certifications</li>
                <li>YouTube - Pharma lectures</li>
            </ul>

            <h3>Daily Learning Routine</h3>
            <ul>
                <li>Drug information study à¤•à¤°à¥‡à¤‚</li>
                <li>Medical news à¤ªà¤¢à¤¼à¥‡à¤‚</li>
                <li>Case studies analyze à¤•à¤°à¥‡à¤‚</li>
                <li>Soft skills develop à¤•à¤°à¥‡à¤‚</li>
            </ul>

            <h3>Career Options</h3>
            <ul>
                <li>Medical Representative</li>
                <li>Pharmacist in hospitals</li>
                <li>Drug Inspector</li>
                <li>Quality Control in pharma companies</li>
                <li>Research & Development</li>
                <li>Academics (teaching)</li>
            </ul>

            <h3>Common Mistakes</h3>
            <ul>
                <li>Only theory focus à¤•à¤°à¤¨à¤¾</li>
                <li>Communication skills ignore à¤•à¤°à¤¨à¤¾</li>
                <li>No industry exposure</li>
                <li>Licensing exams ignore à¤•à¤°à¤¨à¤¾</li>
            </ul>

            <h3>Best Practices</h3>
            <ul>
                <li>Hospital pharmacy internships à¤•à¤°à¥‡à¤‚</li>
                <li>Drug information centers à¤®à¥‡à¤‚ volunteer à¤•à¤°à¥‡à¤‚</li>
                <li>Pharma conferences attend à¤•à¤°à¥‡à¤‚</li>
                <li>English communication improve à¤•à¤°à¥‡à¤‚</li>
                <li>Computer skills learn à¤•à¤°à¥‡à¤‚</li>
            </ul>

            <div class="alert alert-warning">
                <strong>Important:</strong> Pharmacy Council registration à¤œà¤°à¥‚à¤°à¥€ à¤¹à¥ˆ!
            </div>
            '''
        },
        'medical': {
            'title': 'Medical Students - MBBS & Allied Health Guidance',
            'content': '''
            <h3>Medical Education à¤•à¥à¤¯à¤¾ à¤¹à¥ˆ? (What is Medical Education?)</h3>
            <p>MBBS doctors à¤¬à¤¨à¤¨à¥‡ à¤•à¤¾ course à¤¹à¥ˆà¥¤ Allied health (Nursing, Physiotherapy, etc.) à¤­à¥€ medical field à¤•à¤¾ important part à¤¹à¥ˆà¥¤</p>

            <h3>Essential Platforms for Medical Students</h3>

            <h4>1. Medical Research Platforms</h4>
            <ul>
                <li>PubMed - Medical research database</li>
                <li>Cochrane Library - Evidence-based medicine</li>
                <li>NEJM (New England Journal of Medicine)</li>
                <li>Lancet - Medical journal</li>
            </ul>

            <h4>2. Medical Education Platforms</h4>
            <ul>
                <li>Medscape - Medical news & education</li>
                <li>WebMD - Medical information</li>
                <li>BMJ Learning - Medical education</li>
                <li>Coursera - Medical courses</li>
            </ul>

            <h4>3. Professional Networks</h4>
            <ul>
                <li>LinkedIn - Medical professionals network</li>
                <li>ResearchGate - Research collaboration</li>
                <li>Medical council websites</li>
            </ul>

            <h4>4. Exam Preparation</h4>
            <ul>
                <li>USMLE forums (for PG aspirants)</li>
                <li>NEET PG preparation sites</li>
                <li>Medical MCQ apps</li>
            </ul>

            <h3>Daily Learning Routine</h3>
            <ul>
                <li>Medical journals à¤ªà¤¢à¤¼à¥‡à¤‚</li>
                <li>Case discussions à¤•à¤°à¥‡à¤‚</li>
                <li>Clinical skills practice à¤•à¤°à¥‡à¤‚</li>
                <li>Research papers study à¤•à¤°à¥‡à¤‚</li>
            </ul>

            <h3>Career Options</h3>
            <ul>
                <li>MBBS: Clinical practice, Surgery, Medicine</li>
                <li>Allied Health: Nursing, Physiotherapy, Radiology</li>
                <li>Research & Academics</li>
                <li>Public Health</li>
                <li>Medical Administration</li>
            </ul>

            <h3>Common Mistakes</h3>
            <ul>
                <li>Only mugging, no understanding</li>
                <li>No clinical exposure</li>
                <li>Ignoring research</li>
                <li>Poor communication skills</li>
            </ul>

            <h3>Best Practices</h3>
            <ul>
                <li>Regular hospital postings attend à¤•à¤°à¥‡à¤‚</li>
                <li>Medical conferences participate à¤•à¤°à¥‡à¤‚</li>
                <li>Research projects à¤•à¤°à¥‡à¤‚</li>
                <li>Professional networking à¤•à¤°à¥‡à¤‚</li>
                <li>Continuous learning maintain à¤•à¤°à¥‡à¤‚</li>
            </ul>

            <div class="alert alert-success">
                <strong>Remember:</strong> Medicine à¤®à¥‡à¤‚ lifelong learning à¤œà¤°à¥‚à¤°à¥€ à¤¹à¥ˆ!
            </div>
            '''
        },
        'agriculture': {
            'title': 'Agriculture Students - Agri-Tech Career Guidance',
            'content': '''
            <h3>Agriculture Course à¤•à¥à¤¯à¤¾ à¤¹à¥ˆ? (What is Agriculture?)</h3>
            <p>Agriculture farming, crop science, à¤”à¤° modern agri-tech à¤¸à¥‡ related field à¤¹à¥ˆà¥¤ B.Sc Agriculture à¤¸à¥‡ traditional à¤”à¤° modern career options à¤®à¤¿à¤²à¤¤à¥‡ à¤¹à¥ˆà¤‚à¥¤</p>

            <h3>Essential Platforms for Agriculture Students</h3>

            <h4>1. Government Agriculture Portals</h4>
            <ul>
                <li>agricoop.nic.in - Agriculture cooperation</li>
                <li>agmarknet.gov.in - Market prices</li>
                <li>pmkisan.gov.in - Farmer schemes</li>
                <li>icar.org.in - Indian Council of Agricultural Research</li>
            </ul>

            <h4>2. Agri-Tech Platforms</h4>
            <ul>
                <li>Krishi Jagran - Agriculture news</li>
                <li>Agriculture.com - Farming community</li>
                <li>FarmLogs - Farm management software</li>
                <li>Climate FieldView - Precision agriculture</li>
            </ul>

            <h4>3. Research & Education</h4>
            <ul>
                <li>ResearchGate - Agricultural research</li>
                <li>Coursera - Agri-business courses</li>
                <li>edX - Sustainable agriculture</li>
            </ul>

            <h4>4. Job Portals</h4>
            <ul>
                <li>LinkedIn - Agri-business jobs</li>
                <li>Naukri.com (Agriculture section)</li>
                <li>AgriJobs.com</li>
            </ul>

            <h3>Modern Agriculture Skills</h3>
            <ul>
                <li>GIS & Remote Sensing</li>
                <li>Drone technology for farming</li>
                <li>Data analytics for crops</li>
                <li>Sustainable farming practices</li>
                <li>Agri-business management</li>
            </ul>

            <h3>Career Options</h3>
            <ul>
                <li>Agricultural Officer (govt jobs)</li>
                <li>Agri-business management</li>
                <li>Seed technology</li>
                <li>Organic farming consultant</li>
                <li>Research & Development</li>
                <li>Farm management</li>
            </ul>

            <h3>Common Mistakes</h3>
            <ul>
                <li>Only traditional farming focus</li>
                <li>No technology adoption</li>
                <li>Ignoring market trends</li>
                <li>No practical farm training</li>
            </ul>

            <h3>Best Practices</h3>
            <ul>
                <li>Farm internships à¤•à¤°à¥‡à¤‚</li>
                <li>Krishi Vigyan Kendras visit à¤•à¤°à¥‡à¤‚</li>
                <li>Agriculture exhibitions attend à¤•à¤°à¥‡à¤‚</li>
                <li>Modern farming techniques learn à¤•à¤°à¥‡à¤‚</li>
                <li>English communication develop à¤•à¤°à¥‡à¤‚</li>
            </ul>

            <div class="alert alert-info">
                <strong>Future Scope:</strong> Agri-tech à¤®à¥‡à¤‚ huge opportunities à¤¹à¥ˆà¤‚!
            </div>
            '''
        },
        'mpsc': {
            'title': 'MPSC Aspirants - Maharashtra PSC Exam Guidance',
            'content': '''
            <h3>MPSC à¤•à¥à¤¯à¤¾ à¤¹à¥ˆ? (What is MPSC?)</h3>
            <p>MPSC (Maharashtra Public Service Commission) Maharashtra government à¤®à¥‡à¤‚ administrative posts à¤•à¥‡ à¤²à¤¿à¤ competitive exam à¤¹à¥ˆà¥¤</p>

            <h3>Essential Platforms for MPSC Preparation</h3>

            <h4>1. Official MPSC Website</h4>
            <p>mpsc.gov.in - à¤¸à¤­à¥€ notifications, syllabus, à¤”à¤° exam dates à¤¯à¤¹à¤¾à¤ à¤®à¤¿à¤²à¥‡à¤‚à¤—à¥‡à¥¤</p>

            <h4>2. Exam Preparation Platforms</h4>
            <ul>
                <li>BYJU'S Exam Prep</li>
                <li>Unacademy - MPSC courses</li>
                <li>Adda247 - Online coaching</li>
                <li>Gradeup - MPSC mock tests</li>
            </ul>

            <h4>3. Study Material Platforms</h4>
            <ul>
                <li>PDF drive - Free books</li>
                <li>Archive.org - Old question papers</li>
                <li>MPSC preparation apps</li>
            </ul>

            <h4>4. Current Affairs</h4>
            <ul>
                <li>The Hindu newspaper</li>
                <li>Indian Express</li>
                <li>Daily current affairs apps</li>
                <li>Maharashtra state news</li>
            </ul>

            <h4>5. Online Communities</h4>
            <ul>
                <li>Reddit r/MPSC</li>
                <li>Telegram groups</li>
                <li>ForumIAS discussion forums</li>
            </ul>

            <h3>MPSC Exam Pattern</h3>
            <ul>
                <li>Prelims: General Studies + CSAT</li>
                <li>Mains: 6 papers (Marathi, English, GS papers)</li>
                <li>Interview: Personality test</li>
            </ul>

            <h3>Daily Study Routine</h3>
            <ul>
                <li>2-3 hours newspaper reading</li>
                <li>1 hour Marathi practice</li>
                <li>Mock tests weekly</li>
                <li>Revision daily</li>
            </ul>

            <h3>Common Mistakes</h3>
            <ul>
                <li>Only last-minute preparation</li>
                <li>Ignoring Marathi language</li>
                <li>No mock test practice</li>
                <li>Following too many sources</li>
            </ul>

            <h3>Best Preparation Tips</h3>
            <ul>
                <li>Consistent study schedule à¤¬à¤¨à¤¾à¤à¤</li>
                <li>Previous year papers solve à¤•à¤°à¥‡à¤‚</li>
                <li>Join test series</li>
                <li>Stay updated with Maharashtra news</li>
                <li>Answer writing practice à¤•à¤°à¥‡à¤‚</li>
            </ul>

            <div class="alert alert-warning">
                <strong>Important:</strong> MPSC à¤®à¥‡à¤‚ Marathi language à¤œà¤°à¥‚à¤°à¥€ à¤¹à¥ˆ!
            </div>
            '''
        },
        'upsc': {
            'title': 'UPSC Aspirants - Civil Services Exam Guidance',
            'content': '''
            <h3>UPSC à¤•à¥à¤¯à¤¾ à¤¹à¥ˆ? (What is UPSC?)</h3>
            <p>UPSC (Union Public Service Commission) India à¤•à¥‡ top administrative services (IAS, IPS, IFS, etc.) à¤•à¥‡ à¤²à¤¿à¤ entrance exam à¤¹à¥ˆà¥¤</p>

            <h3>Essential Platforms for UPSC Preparation</h3>

            <h4>1. Official UPSC Website</h4>
            <p>upsc.gov.in - à¤¸à¤­à¥€ notifications, syllabus, à¤”à¤° exam details à¤¯à¤¹à¤¾à¤ à¤®à¤¿à¤²à¥‡à¤‚à¤—à¥‡à¥¤</p>

            <h4>2. Exam Preparation Platforms</h4>
            <ul>
                <li>Unacademy - Best for UPSC</li>
                <li>BYJU'S Exam Prep</li>
                <li>Vision IAS</li>
                <li>Drishti IAS</li>
                <li>Gradeup - Mock tests</li>
            </ul>

            <h4>3. Current Affairs Platforms</h4>
            <ul>
                <li>The Hindu newspaper</li>
                <li>Indian Express</li>
                <li>PIB (Press Information Bureau)</li>
                <li>All India Radio news</li>
                <li>Daily current affairs apps</li>
            </ul>

            <h4>4. Study Material</h4>
            <ul>
                <li>NCERT books (6th to 12th)</li>
                <li>Standard reference books</li>
                <li>Online PDF resources</li>
                <li>Previous year question papers</li>
            </ul>

            <h4>5. Online Communities</h4>
            <ul>
                <li>Reddit r/UPSC</li>
                <li>Telegram groups</li>
                <li>ForumIAS</li>
                <li>IAS baba forums</li>
            </ul>

            <h3>UPSC Exam Stages</h3>
            <ul>
                <li>Prelims: General Studies + CSAT</li>
                <li>Mains: 9 papers (Essay, GS papers, Optional)</li>
                <li>Interview: Personality test</li>
            </ul>

            <h3>Daily Study Routine</h3>
            <ul>
                <li>3-4 hours newspaper reading</li>
                <li>2 hours static subjects</li>
                <li>1 hour answer writing</li>
                <li>Mock tests weekly</li>
                <li>Revision time</li>
            </ul>

            <h3>Common Mistakes</h3>
            <ul>
                <li>Too many coaching classes</li>
                <li>Ignoring revision</li>
                <li>No answer writing practice</li>
                <li>Following unreliable sources</li>
                <li>Health neglect à¤•à¤°à¤¨à¤¾</li>
            </ul>

            <h3>Best Preparation Tips</h3>
            <ul>
                <li>NCERT books à¤¸à¥‡ foundation strong à¤•à¤°à¥‡à¤‚</li>
                <li>Consistent study schedule follow à¤•à¤°à¥‡à¤‚</li>
                <li>Daily answer writing practice à¤•à¤°à¥‡à¤‚</li>
                <li>Multiple mock tests à¤¦à¥‡à¤‚</li>
                <li>Stay updated with current affairs</li>
                <li>Physical and mental health maintain à¤•à¤°à¥‡à¤‚</li>
            </ul>

            <div class="alert alert-success">
                <strong>Motivation:</strong> UPSC clear à¤•à¤°à¤¨à¥‡ à¤•à¥‡ à¤²à¤¿à¤ consistency à¤”à¤° smart work à¤œà¤°à¥‚à¤°à¥€ à¤¹à¥ˆ!
            </div>
            '''
        }
    }

    guide = guides.get(platform)
    if not guide:
        return "Guide not found", 404

    log_activity('learning_guide_viewed', 'learn', f'Viewed guide for {platform}')
    return render_template('learn/guide.html', guide=guide)


# ==================== CHATBOT MODULE ====================
@app.route('/chatbot')
@login_required
def chatbot_home():
    log_activity('module_access', 'chatbot', 'Accessed AI chatbot')
    return render_template('chatbot/index.html')

@app.route('/chatbot/message', methods=['POST'])
@login_required
def chatbot_message():
    try:
        data = request.get_json(silent=True) or {}
        user_message = (data.get('message') or '').strip()
        history = data.get('history') if isinstance(data.get('history'), list) else []

        if not user_message:
            return jsonify({'response': '', 'success': False, 'error': 'Message is required.'}), 400

        response = get_advanced_local_chatbot_response(user_message, history)
        return jsonify({'response': response, 'success': True, 'mode': 'local'})
    except Exception as e:
        print(f"Chatbot error: {e}")
        print(f"Chatbot traceback: {traceback.format_exc()}")
        return jsonify({
            'response': 'I hit a local processing issue. Please retry with a shorter question.',
            'success': False
        }), 500

_LOCAL_SITE_TOPICS = [
    {
        'keywords': ('career quiz', 'quiz', 'career test', 'interest test'),
        'response': (
            'Take the career quiz here: /career/quiz\n'
            '1. Answer all questions honestly\n'
            '2. Submit to view role suggestions\n'
            '3. Open /career/browse to compare options'
        )
    },
    {
        'keywords': ('career browse', 'browse careers', 'career options', 'career path'),
        'response': 'Explore careers here: /career/browse. Use filters for category, difficulty, and growth.'
    },
    {
        'keywords': ('resume', 'cv', 'portfolio', 'resume review'),
        'response': (
            'Use resume review at /career/resume-review.\n'
            'Share your target role and resume text, then apply top suggestions with measurable impact bullets.'
        )
    },
    {
        'keywords': ('internship', 'internships', 'apply internship'),
        'response': (
            'Internship pages:\n'
            '- Browse: /internships/browse\n'
            '- Community stories: /internships/community\n'
            '- Share your experience: /internships/share'
        )
    },
    {
        'keywords': ('skills', 'learning resources', 'course', 'upskill', 'skill saathi'),
        'response': 'Find courses and skill resources at /skill/browse. Filter by topic and difficulty.'
    },
    {
        'keywords': ('ai tools', 'tool recommendations', 'chatgpt', 'copilot'),
        'response': 'Explore curated AI tools at /ai/tools by category and use case.'
    },
    {
        'keywords': ('mental health', 'stress', 'mood', 'breathing'),
        'response': 'Mental wellness tools: mood tracking at /mental/mood and guided breathing at /mental/breathing.'
    },
    {
        'keywords': ('gyan', 'wisdom', 'gita', 'shloka'),
        'response': 'Spiritual learning: daily wisdom at /gyan/daily and search at /gyan/search.'
    },
    {
        'keywords': ('mentor', 'mentoring', 'expert guidance'),
        'response': 'Mentor support is available at /mentor-connect for requests and guidance.'
    },
    {
        'keywords': ('todo', 'task', 'productivity'),
        'response': 'Manage your tasks at /todo with priority and deadline tracking.'
    },
    {
        'keywords': ('progress', 'dashboard', 'activity'),
        'response': 'Track your learning and activity at /progress.'
    },
    {
        'keywords': ('student community', 'community chat', 'connect students'),
        'response': 'Connect and chat with peers at /student-community.'
    }
]

_FIELD_GUIDES = [
    {
        'keywords': ('python', 'django', 'flask', 'backend'),
        'response': (
            'Python roadmap:\n'
            '1. Learn core Python, OOP, and file handling\n'
            '2. Build Flask or Django CRUD apps\n'
            '3. Learn SQL + APIs + deployment\n'
            '4. Ship 3 portfolio projects with README and metrics'
        )
    },
    {
        'keywords': ('data science', 'data analyst', 'analytics', 'sql', 'power bi'),
        'response': (
            'Data path:\n'
            '1. Excel + SQL + Python basics\n'
            '2. Statistics + EDA + visualization\n'
            '3. Build dashboards (Power BI/Tableau)\n'
            '4. Publish 2 end-to-end case studies'
        )
    },
    {
        'keywords': ('machine learning', 'ai', 'ml', 'deep learning'),
        'response': (
            'AI/ML plan:\n'
            '1. Python + linear algebra + probability\n'
            '2. Scikit-learn models and evaluation\n'
            '3. Deep learning basics (PyTorch/TensorFlow)\n'
            '4. Deploy one ML app with API and UI'
        )
    },
    {
        'keywords': ('web development', 'full stack', 'frontend', 'react', 'javascript'),
        'response': (
            'Web dev plan:\n'
            '1. HTML/CSS/JavaScript fundamentals\n'
            '2. React for frontend + Flask/Node for backend\n'
            '3. Auth, database, and API integration\n'
            '4. Deploy full-stack projects and document tradeoffs'
        )
    },
    {
        'keywords': ('cyber security', 'cybersecurity', 'network security', 'ethical hacking'),
        'response': (
            'Cybersecurity track:\n'
            '1. Networking + Linux fundamentals\n'
            '2. Web security basics (OWASP Top 10)\n'
            '3. Practice labs (CTF, TryHackMe)\n'
            '4. Build a security portfolio and write reports'
        )
    },
    {
        'keywords': ('cloud', 'aws', 'azure', 'devops'),
        'response': (
            'Cloud/DevOps path:\n'
            '1. Linux + networking + scripting\n'
            '2. AWS/Azure core services\n'
            '3. CI/CD + Docker basics\n'
            '4. Deploy a monitored production-style app'
        )
    },
    {
        'keywords': ('finance', 'trading', 'investment', 'accounting'),
        'response': (
            'Finance growth plan:\n'
            '1. Core accounting and valuation concepts\n'
            '2. Excel modeling and market basics\n'
            '3. Risk management and portfolio thinking\n'
            '4. Build a thesis-based project and track outcomes'
        )
    }
]

_ALLOWED_MATH_BINOPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
    ast.FloorDiv: operator.floordiv
}

_ALLOWED_MATH_UNARYOPS = {
    ast.UAdd: operator.pos,
    ast.USub: operator.neg
}

def _absolute_link(path):
    base = request.host_url.rstrip('/') if has_request_context() and request.host_url else 'http://127.0.0.1:5000'
    if not path.startswith('/'):
        path = f'/{path}'
    return f'{base}{path}'

def _absolutize_links_in_text(text):
    if not text:
        return text
    pattern = re.compile(r'(?<![A-Za-z0-9_])(\/[-a-zA-Z0-9_./]+)')

    def _replace(match):
        raw = match.group(1)
        if raw.startswith('//'):
            return raw
        if match.start() > 0 and text[match.start() - 1] == ':':
            return raw
        prefix = text[max(0, match.start() - 8):match.start()].lower()
        if prefix.endswith('http://') or prefix.endswith('https://'):
            return raw
        cleaned = raw.rstrip('.,;:!?')
        tail = raw[len(cleaned):]
        return f'{_absolute_link(cleaned)}{tail}'

    return pattern.sub(_replace, text)

def _split_multi_values(value):
    if not value:
        return []
    parts = re.split(r'[;,/]| and ', str(value), flags=re.IGNORECASE)
    return [p.strip() for p in parts if p and p.strip()]

def _parse_roadmap_field(query):
    q = _clean_chat_text(query).lower()
    patterns = [
        r'(?:roadmap|plan|path)\s*(?:for|to become|to be|for becoming)?\s*([a-z0-9\+\-\/\s]{2,})',
        r'how\s+to\s+become\s+(?:a|an)?\s*([a-z0-9\+\-\/\s]{2,})',
        r'career\s+in\s+([a-z0-9\+\-\/\s]{2,})',
        r'([a-z0-9\+\-\/\s]{2,})\s+(?:roadmap|plan|path)$'
    ]
    for pattern in patterns:
        m = re.search(pattern, q)
        if m:
            field = m.group(1).strip(' .?')
            field = re.sub(
                r'\b(?:please|give|create|make|me|a|an|the|i|want|need|for|to|become|career|roadmap|plan|path)\b',
                '',
                field
            ).strip()
            field = re.sub(r'\s+', ' ', field).strip()
            if len(field) >= 2:
                return field
    return ''

def _get_career_candidates(field, limit=6):
    conn = get_db_connection()
    try:
        term = field.lower().strip()
        like = f'%{term}%'
        rows = conn.execute(
            '''
            SELECT title, category, description, required_skills, education_required, growth_rate, difficulty_level, job_roles
            FROM careers
            WHERE lower(title) LIKE ?
               OR lower(category) LIKE ?
               OR lower(description) LIKE ?
               OR lower(required_skills) LIKE ?
               OR lower(job_roles) LIKE ?
            LIMIT 30
            ''',
            (like, like, like, like, like)
        ).fetchall()

        if rows:
            return rows[:limit]

        tokens = [t for t in re.findall(r'[a-z0-9\+#]+', term) if len(t) > 2]
        if not tokens:
            return []

        conditions = []
        params = []
        for token in tokens[:5]:
            token_like = f'%{token}%'
            conditions.append(
                '(lower(title) LIKE ? OR lower(category) LIKE ? OR lower(description) LIKE ? OR lower(required_skills) LIKE ? OR lower(job_roles) LIKE ?)'
            )
            params.extend([token_like, token_like, token_like, token_like, token_like])
        sql = f'''
            SELECT title, category, description, required_skills, education_required, growth_rate, difficulty_level, job_roles
            FROM careers
            WHERE {' OR '.join(conditions)}
            LIMIT 30
        '''
        token_rows = conn.execute(sql, params).fetchall()
        return token_rows[:limit]
    finally:
        conn.close()

def _build_dynamic_field_roadmap(field, candidates):
    if not candidates:
        return (
            f'I could not find an exact match for "{field}" in the career dataset.\n'
            'Try a close career title and I will generate a role-specific roadmap.\n'
            f'You can explore all careers here: {_absolute_link("/career/browse")}'
        )

    top = candidates[0]
    skills = []
    roles = []
    education = []
    growth_signals = []
    for row in candidates:
        skills.extend(_split_multi_values(row['required_skills']))
        roles.extend(_split_multi_values(row['job_roles']))
        if row['education_required']:
            education.append(str(row['education_required']).strip())
        if row['growth_rate']:
            growth_signals.append(str(row['growth_rate']).strip())

    def _top_unique(items, limit=6):
        seen = set()
        ordered = []
        for item in items:
            key = item.lower()
            if key and key not in seen:
                seen.add(key)
                ordered.append(item)
            if len(ordered) >= limit:
                break
        return ordered

    top_skills = _top_unique(skills, 6)
    top_roles = _top_unique(roles, 5)
    top_education = _top_unique(education, 3)
    top_growth = _top_unique(growth_signals, 2)

    skills_line = ', '.join(top_skills) if top_skills else 'core domain fundamentals'
    roles_line = ', '.join(top_roles) if top_roles else top['title']
    education_line = '; '.join(top_education) if top_education else 'role-aligned degree or certification'
    growth_line = ', '.join(top_growth) if top_growth else 'steady growth'

    return (
        f'Roadmap for {field.title()} (based on Career Browse data):\n'
        f'Target roles: {roles_line}\n'
        f'Primary skills: {skills_line}\n'
        f'Education path: {education_line}\n'
        f'Growth outlook: {growth_line}\n\n'
        'Phase 1 (Month 1-2): Build foundation\n'
        '- Learn the top 3 skills and complete one mini project\n'
        '- Create notes and weekly practice schedule\n\n'
        'Phase 2 (Month 3-4): Build portfolio\n'
        '- Build 2 role-specific projects with measurable outcomes\n'
        '- Add project summaries and proof links\n\n'
        'Phase 3 (Month 5-6): Job readiness\n'
        '- Prepare resume for target role and practice interviews\n'
        '- Apply to internships/jobs with tailored applications\n\n'
        f'Direct links:\n- Career Browse: {_absolute_link("/career/browse")}\n- Resume Review: {_absolute_link("/career/resume-review")}'
    )

def _clean_chat_text(text):
    return re.sub(r'\s+', ' ', (text or '')).strip()

def _extract_last_user_query(history):
    for item in reversed(history or []):
        if isinstance(item, dict) and (item.get('role') == 'user'):
            value = _clean_chat_text(item.get('content', ''))
            if value:
                return value
    return ''

def _merge_with_context(message, history):
    msg = _clean_chat_text(message)
    if len(msg.split()) > 4:
        return msg
    if any(token in msg.lower() for token in ('and', 'also', 'same', 'more', 'next', 'this')):
        prev = _extract_last_user_query(history)
        if prev:
            return f'{prev} {msg}'
    return msg

def _safe_eval_math(expr):
    node = ast.parse(expr, mode='eval')

    def _eval(n):
        if isinstance(n, ast.Expression):
            return _eval(n.body)
        if isinstance(n, ast.Constant) and isinstance(n.value, (int, float)):
            return n.value
        if isinstance(n, ast.UnaryOp) and type(n.op) in _ALLOWED_MATH_UNARYOPS:
            return _ALLOWED_MATH_UNARYOPS[type(n.op)](_eval(n.operand))
        if isinstance(n, ast.BinOp) and type(n.op) in _ALLOWED_MATH_BINOPS:
            return _ALLOWED_MATH_BINOPS[type(n.op)](_eval(n.left), _eval(n.right))
        raise ValueError('Unsupported expression')

    return _eval(node)

def _try_math_response(message):
    cleaned = message.lower().replace('calculate', '').replace('what is', '').strip(' ?')
    if not cleaned:
        return None
    if not re.fullmatch(r'[0-9\.\+\-\*\/%\(\)\s\^]+', cleaned):
        return None
    expr = cleaned.replace('^', '**')
    try:
        result = _safe_eval_math(expr)
        if isinstance(result, float):
            result = round(result, 6)
        return f'The answer is {result}.'
    except Exception:
        return None

def _topic_match_score(query, keywords):
    query_lower = query.lower()
    score = 0
    for kw in keywords:
        kw_l = kw.lower()
        if kw_l in query_lower:
            score += 3 if ' ' in kw_l else 2
    query_tokens = set(re.findall(r'[a-z0-9\+#]+', query_lower))
    keyword_tokens = set()
    for kw in keywords:
        keyword_tokens.update(re.findall(r'[a-z0-9\+#]+', kw.lower()))
    score += len(query_tokens.intersection(keyword_tokens))
    return score

def _match_site_topic(query):
    best_response = None
    best_score = 0
    for topic in _LOCAL_SITE_TOPICS:
        score = _topic_match_score(query, topic['keywords'])
        if score > best_score:
            best_score = score
            best_response = topic['response']
    return best_response if best_score >= 2 else None

def _match_field_guide(query):
    best_response = None
    best_score = 0
    for guide in _FIELD_GUIDES:
        score = _topic_match_score(query, guide['keywords'])
        if score > best_score:
            best_score = score
            best_response = guide['response']
    return best_response if best_score >= 2 else None

def _generic_explanation_response(query):
    lower = query.lower()
    prefixes = ('what is ', 'explain ', 'define ', 'tell me about ')
    topic = ''
    for prefix in prefixes:
        if lower.startswith(prefix):
            topic = query[len(prefix):].strip(' ?.')
            break
    if not topic or len(topic) < 2:
        return None
    return (
        f'{topic} is an important concept. Here is a practical way to understand it:\n'
        f'1. Definition: understand the core purpose and vocabulary of {topic}\n'
        f'2. Why it matters: connect it to real projects or career outcomes\n'
        f'3. First practice: complete one beginner task using {topic}\n'
        f'4. Progress step: build one mini project and review what improved'
    )

def _looks_like_placement_coach_request(query):
    q = (query or '').lower()
    return (
        'you are an ai placement coach' in q
        or (
            'student profile' in q
            and 'target role' in q
            and 'current status' in q
            and 'placement readiness score' in q
        )
    )

def _extract_profile_field(text, label):
    pattern = rf'^\s*{re.escape(label)}\s*:\s*(.*?)\s*(?:\([^)]*\)\s*)?$'
    match = re.search(pattern, text or '', flags=re.IGNORECASE | re.MULTILINE)
    return _clean_chat_text(match.group(1)) if match else ''

def _is_missing_or_placeholder(value):
    cleaned = _clean_chat_text(str(value or ''))
    if not cleaned:
        return True
    if re.fullmatch(r'\{[^{}]+\}', cleaned):
        return True
    return cleaned.lower() in {'na', 'n/a', 'none', 'unknown', '-'}

def _normalize_level(value, default='medium'):
    cleaned = _clean_chat_text(str(value or '')).lower()
    if cleaned in {'low', 'medium', 'high'}:
        return cleaned
    return default

def _normalize_yes_no(value):
    cleaned = _clean_chat_text(str(value or '')).lower()
    if cleaned in {'yes', 'y', 'true', '1'}:
        return 'yes'
    if cleaned in {'no', 'n', 'false', '0'}:
        return 'no'
    return ''

def _choose_aptitude_topic(aptitude_level):
    if aptitude_level == 'low':
        return 'Percentages'
    if aptitude_level == 'high':
        return 'Data Interpretation'
    return 'Time and Work'

def _get_aptitude_practice(topic):
    banks = {
        'Percentages': [
            {
                'q': 'A number increases from 200 to 260. What is the percentage increase?',
                'a': '30%',
                'e': 'Increase is 60. Percentage increase = (60/200)*100 = 30%.'
            },
            {
                'q': 'The price of an item is reduced by 20% from 500. What is the new price?',
                'a': '400',
                'e': '20% of 500 is 100. New price = 500 - 100 = 400.'
            },
            {
                'q': 'A student scores 72 out of 90. What is the score percentage?',
                'a': '80%',
                'e': 'Percentage = (72/90)*100 = 80%.'
            },
            {
                'q': 'If x is increased by 25% and becomes 100, what is x?',
                'a': '80',
                'e': '100 = 125% of x, so x = 100/1.25 = 80.'
            },
            {
                'q': 'After two successive discounts of 10% and 20%, what is the net discount?',
                'a': '28%',
                'e': 'Effective factor = 0.9 * 0.8 = 0.72, so net discount = 28%.'
            }
        ],
        'Time and Work': [
            {
                'q': 'A can finish a task in 12 days and B in 18 days. In how many days together?',
                'a': '7.2 days',
                'e': 'Combined rate = 1/12 + 1/18 = 5/36. Time = 36/5 = 7.2 days.'
            },
            {
                'q': 'If 8 workers complete a job in 15 days, how many days for 12 workers?',
                'a': '10 days',
                'e': 'Work = 8*15 = 120 worker-days. Days with 12 workers = 120/12 = 10.'
            },
            {
                'q': 'A alone does a job in 20 days. After 5 days, B joins and they finish in 5 more days. B alone takes?',
                'a': '20 days',
                'e': 'A did 5/20 = 1/4 work. Remaining 3/4 done by A+B in 5 days => rate 3/20. B rate = 3/20 - 1/20 = 1/10.'
            },
            {
                'q': 'P is twice as efficient as Q. If Q takes 30 days, P takes how many days?',
                'a': '15 days',
                'e': 'Double efficiency means half time.'
            },
            {
                'q': 'A tap fills a tank in 6 hours and another in 8 hours. Together they fill in?',
                'a': '24/7 hours (about 3.43 hours)',
                'e': 'Rate = 1/6 + 1/8 = 7/24. Time = 24/7 hours.'
            }
        ],
        'Data Interpretation': [
            {
                'q': 'Sales were 120, 150, 180 in three months. Find average sales.',
                'a': '150',
                'e': 'Average = (120+150+180)/3 = 450/3 = 150.'
            },
            {
                'q': 'A pie chart shows 25% for category A out of total 800. Value of A?',
                'a': '200',
                'e': '25% of 800 = 200.'
            },
            {
                'q': 'A value rises from 250 to 300. Find percentage growth.',
                'a': '20%',
                'e': 'Growth = 50. Percentage = (50/250)*100 = 20%.'
            },
            {
                'q': 'Company X has revenue 500 and profit 50. Profit margin?',
                'a': '10%',
                'e': 'Margin = (50/500)*100 = 10%.'
            },
            {
                'q': 'If ratio of boys:girls is 3:2 in class of 50, number of girls?',
                'a': '20',
                'e': 'Total parts = 5. Each part = 10. Girls = 2 parts = 20.'
            }
        ]
    }
    return banks.get(topic, banks['Time and Work'])

def _infer_field(field, target_role):
    if not _is_missing_or_placeholder(field):
        return field.strip()
    role = (target_role or '').lower()
    if any(token in role for token in ('analyst', 'data', 'ml', 'ai')):
        return 'Data'
    if any(token in role for token in ('engineer', 'developer', 'software', 'web', 'cloud', 'devops')):
        return 'Tech'
    return 'Non-Tech'

def _build_project_suggestion(field, target_role, target_company):
    role = target_role if not _is_missing_or_placeholder(target_role) else 'target role'
    company = target_company if not _is_missing_or_placeholder(target_company) else 'your target company'
    field_lower = (field or '').lower()

    if field_lower.startswith('tech'):
        return (
            f'Build a "{role} Preparation Tracker" web app for {company}: create aptitude mock tests, '
            'track DSA/subject progress, and add analytics for weak-topic trends. Include login, dashboard, '
            'and weekly improvement reports to demonstrate full-stack and problem-solving ability.'
        )
    if field_lower.startswith('data'):
        return (
            f'Build a "{role} Hiring Insights Dashboard" for {company}: collect job-post data, clean it, and '
            'analyze skill demand, salary bands, and location patterns. Add interactive visuals and one predictive '
            'model for role fit scoring to show end-to-end data skills.'
        )
    if field_lower.startswith('core'):
        return (
            f'Build a "{role} Process Optimizer" project aligned to {company}: model a real core-domain workflow, '
            'measure bottlenecks, and propose efficiency improvements with clear KPIs, simulation results, '
            'and implementation recommendations.'
        )
    return (
        f'Build a "{role} Placement Strategy System" for {company}: include company research sheets, application '
        'tracking, mock interview notes, and communication improvement logs. Show measurable outcomes like increased '
        'shortlisting rate and better interview response quality.'
    )

def _placement_readiness_score(aptitude_level, skill_level, dsa_knowledge, projects_done, resume_ready):
    score = 20
    score += {'low': 8, 'medium': 16, 'high': 24}.get(aptitude_level, 12)
    score += {'low': 5, 'medium': 10, 'high': 15}.get(skill_level, 8)
    if dsa_knowledge == 'yes':
        score += 15
    if projects_done == 'yes':
        score += 20
    if resume_ready == 'yes':
        score += 15
    return max(0, min(100, score))

def _get_readiness_status(score):
    if score < 40:
        return 'Not Ready'
    if score < 70:
        return 'Improving'
    return 'Placement Ready'

def _placement_coach_response(query):
    if not _looks_like_placement_coach_request(query):
        return None

    name = _extract_profile_field(query, 'Name')
    branch = _extract_profile_field(query, 'Branch')
    year = _extract_profile_field(query, 'Year')
    field = _extract_profile_field(query, 'Field')
    skills = _extract_profile_field(query, 'Skills')
    skill_level = _normalize_level(_extract_profile_field(query, 'Skill Level'), default='medium')
    target_role = _extract_profile_field(query, 'Target Role')
    target_company = _extract_profile_field(query, 'Target Company')
    aptitude_level = _normalize_level(_extract_profile_field(query, 'Aptitude Level'), default='medium')
    dsa_knowledge = _normalize_yes_no(_extract_profile_field(query, 'DSA Knowledge'))
    projects_done = _normalize_yes_no(_extract_profile_field(query, 'Projects Done'))
    resume_ready = _normalize_yes_no(_extract_profile_field(query, 'Resume Ready'))

    inferred_field = _infer_field(field, target_role)
    skill_text = skills if not _is_missing_or_placeholder(skills) else 'basic domain skills'
    role_text = target_role if not _is_missing_or_placeholder(target_role) else 'target role'

    strengths = []
    if not _is_missing_or_placeholder(branch):
        strengths.append(f'Branch alignment: {branch} provides a solid base for {role_text}.')
    strengths.append(f'Current skill set identified: {skill_text}.')
    if aptitude_level in {'medium', 'high'}:
        strengths.append(f'Aptitude baseline is {aptitude_level}, which supports placement test performance.')
    if dsa_knowledge == 'yes':
        strengths.append('DSA foundation is present, useful for screening and coding rounds.')
    if projects_done == 'yes':
        strengths.append('Project experience exists, which strengthens practical interview discussions.')
    if resume_ready == 'yes':
        strengths.append('Resume is already prepared and can be optimized for target roles quickly.')
    if not strengths:
        strengths.append('You are actively planning your placement journey, which is a strong starting point.')

    weaknesses = []
    if aptitude_level == 'low':
        weaknesses.append('Aptitude is currently a bottleneck and needs daily timed practice.')
    elif aptitude_level == 'medium':
        weaknesses.append('Aptitude needs stronger speed and accuracy under time pressure.')
    if inferred_field.lower().startswith('tech') and dsa_knowledge != 'yes':
        weaknesses.append('DSA preparation is missing for tech hiring rounds.')
    if projects_done != 'yes':
        weaknesses.append('Project proof of skills is missing; this can reduce shortlist chances.')
    if resume_ready != 'yes':
        weaknesses.append('Resume is not interview-ready yet and needs role-specific improvements.')
    if _is_missing_or_placeholder(skill_text):
        weaknesses.append('Skill details are unclear; define 3-5 measurable core skills immediately.')
    if not weaknesses:
        weaknesses.append('Main gap is consistency in mock tests and interview simulation.')

    daily_plan = [
        f'Aptitude (Main Focus): Solve 25 mixed questions on {_choose_aptitude_topic(aptitude_level)} and review all mistakes in a formula/error log.',
        'Aptitude Speed Drill: Attempt 1 timed mini-mock (20-30 min) and target accuracy above 80%.'
    ]
    if inferred_field.lower().startswith('tech'):
        daily_plan.append('Technical Task: Solve 2 coding problems (1 easy, 1 medium) and revise one key concept for interviews.')
    if projects_done != 'yes':
        daily_plan.append('Project Improvement: Spend 60 minutes building one measurable feature and document impact in README.')
    else:
        daily_plan.append('Resume/Project Polish: Add quantified outcomes to one project bullet and align it with target role keywords.')
    daily_plan.append('Communication Task: Practice a 2-minute self-introduction and one GD summary response aloud.')

    aptitude_topic = _choose_aptitude_topic(aptitude_level)
    aptitude_set = _get_aptitude_practice(aptitude_topic)

    resume_tips = [
        f'Customize headline and summary for {role_text} with 4-6 matching keywords from job descriptions.',
        'Convert project bullets to impact format: Action + Tool + Result (with numbers).',
        'Keep resume one page, remove generic statements, and prioritize strongest work in top half.'
    ]

    gd_topic = 'Should AI-based assessments be used as the primary filter in campus placements?'
    gd_for = [
        'AI assessments scale quickly and evaluate large applicant pools consistently.',
        'They reduce manual bias in early screening when designed well.',
        'They provide faster feedback loops to students and recruiters.'
    ]
    gd_against = [
        'Over-reliance on AI may miss creativity, communication, and real potential.',
        'Algorithm bias or poor test design can unfairly impact candidates.',
        'Many students have unequal access to tools and preparation environments.'
    ]

    mock_questions = [
        'Tell me about yourself and why you are interested in this role.',
        'Describe a challenge you faced and how you handled it under pressure.'
    ]

    readiness_score = _placement_readiness_score(
        aptitude_level=aptitude_level,
        skill_level=skill_level,
        dsa_knowledge=dsa_knowledge,
        projects_done=projects_done,
        resume_ready=resume_ready
    )
    readiness_status = _get_readiness_status(readiness_score)

    immediate_actions = []
    if aptitude_level != 'high':
        immediate_actions.append('start daily timed aptitude practice with strict error tracking')
    if inferred_field.lower().startswith('tech') and dsa_knowledge != 'yes':
        immediate_actions.append('begin core DSA topics (arrays, strings, hashing, recursion) this week')
    if projects_done != 'yes':
        immediate_actions.append('complete one role-aligned project milestone in the next 7 days')
    if resume_ready != 'yes':
        immediate_actions.append('finish and review a role-specific resume this week')
    if not immediate_actions:
        immediate_actions.append('increase mock interview frequency and improve answer structure using STAR')

    profile_note = ''
    if any(
        _is_missing_or_placeholder(v)
        for v in (name, branch, year, field, skills, target_role, target_company)
    ):
        profile_note = 'Some profile fields are placeholders, so this plan is generated as a baseline template.\n\n'

    lines = []
    if profile_note:
        lines.append(profile_note.strip())
        lines.append('')

    lines.extend([
        'Strengths:',
        *[f'- {item}' for item in strengths[:5]],
        '',
        'Weaknesses:',
        *[f'- {item}' for item in weaknesses[:5]],
        '',
        'Daily Plan:',
        *[f'- {item}' for item in daily_plan],
        '',
        'Aptitude Practice:',
    ])

    for idx, item in enumerate(aptitude_set[:5], start=1):
        lines.extend([
            f'Q{idx}: {item["q"]}',
            f'Answer: {item["a"]}',
            f'Explanation: {item["e"]}'
        ])

    lines.extend([
        '',
        'Project Suggestion:',
        _build_project_suggestion(inferred_field, target_role, target_company),
        '',
        'Resume Tips:',
        *[f'- {tip}' for tip in resume_tips],
        '',
        'Group Discussion Topic:',
        f'Topic: {gd_topic}',
        'For:',
        *[f'- {point}' for point in gd_for],
        'Against:',
        *[f'- {point}' for point in gd_against],
        '',
        'Mock Interview Questions:',
        f'1. {mock_questions[0]}',
        f'2. {mock_questions[1]}',
        '',
        'Performance Insight:',
        f'Immediate priority: {", ".join(immediate_actions)}.',
        '',
        'Placement Readiness Score:',
        f'Score: {readiness_score}/100',
        f'Status: {readiness_status}'
    ])

    return '\n'.join(lines)

def _local_capabilities_response():
    return (
        'I can answer questions without any API key.\n'
        'Website help:\n'
        '- Career quiz and role exploration\n'
        '- Resume review and internships\n'
        '- Skills, mentor, mood, gyan, todo, progress\n'
        '- Student community and chatbot support\n'
        f'- Feature hub: {_absolute_link("/")} \n'
        f'- Career quiz: {_absolute_link("/career/quiz")} \n'
        f'- Career browse: {_absolute_link("/career/browse")} \n'
        f'- Resume review: {_absolute_link("/career/resume-review")} \n'
        f'- Internships: {_absolute_link("/internships/browse")} \n'
        f'- Skills: {_absolute_link("/skill/browse")} \n'
        f'- AI tools: {_absolute_link("/ai/tools")} \n'
        f'- Mentor connect: {_absolute_link("/mentor-connect")} \n'
        f'- Mood tracker: {_absolute_link("/mental/mood")} \n'
        f'- Student community: {_absolute_link("/student-community")} \n'
        'General help:\n'
        '- Learning roadmaps for tech and non-tech fields\n'
        '- Interview and study planning\n'
        '- Basic math calculations and concept explanations'
    )

def get_advanced_local_chatbot_response(message, history=None):
    resolved = _merge_with_context(message, history or [])
    lower = resolved.lower()

    placement_reply = _placement_coach_response(resolved)
    if placement_reply:
        return _absolutize_links_in_text(placement_reply)

    if any(greet in lower for greet in ('hello', 'hi', 'hey', 'namaste', 'good morning', 'good evening')):
        return _absolutize_links_in_text(
            (
            'Hello! I am your Marg Darshak offline assistant.\n'
            'Ask me about any website feature, career path, or learning plan, and I will guide you step by step.\n'
            f'You can start from: {_absolute_link("/chatbot")}'
            )
        )

    if any(key in lower for key in ('help', 'what can you do', 'how can you help', 'features', 'all features')):
        return _absolutize_links_in_text(_local_capabilities_response())

    math_reply = _try_math_response(resolved)
    if math_reply:
        return _absolutize_links_in_text(math_reply)

    roadmap_field = _parse_roadmap_field(resolved)
    if roadmap_field:
        candidates = _get_career_candidates(roadmap_field, limit=6)
        return _absolutize_links_in_text(_build_dynamic_field_roadmap(roadmap_field, candidates))

    site_reply = _match_site_topic(resolved)
    if site_reply:
        return _absolutize_links_in_text(site_reply)

    field_reply = _match_field_guide(resolved)
    if field_reply:
        return _absolutize_links_in_text(field_reply + f'\n\nExplore related roles: {_absolute_link("/career/browse")}')

    concept_reply = _generic_explanation_response(resolved)
    if concept_reply:
        return _absolutize_links_in_text(concept_reply)

    return _absolutize_links_in_text(
        (
        'I can help with this. Share one clear goal, your current level, and timeline.\n'
        'Example: "I am a beginner in data science and want an internship in 3 months."\n'
        'Then I will give you a detailed step-by-step plan.\n'
        f'If you want, start with Career Browse: {_absolute_link("/career/browse")}'
        )
    )

def get_chatbot_response(message):
    """Simple rule-based chatbot for Marg Darshak guidance"""
    
    # Greeting responses
    greetings = ['hello', 'hi', 'hey', 'namaste', 'good morning', 'good evening']
    if any(greet in message for greet in greetings):
        return "à¤¨à¤®à¤¸à¥à¤¤à¥‡! à¤®à¥ˆà¤‚ à¤†à¤ªà¤•à¤¾ à¤®à¤¾à¤°à¥à¤—à¤¦à¤°à¥à¤¶à¤• à¤¹à¥‚à¤‚à¥¤ à¤®à¥ˆà¤‚ à¤†à¤ªà¤•à¥€ career, education, mental health, wisdom, skills, AI tools, mentoring, productivity, à¤”à¤° overall development à¤®à¥‡à¤‚ à¤®à¤¦à¤¦ à¤•à¤° à¤¸à¤•à¤¤à¤¾ à¤¹à¥‚à¤‚à¥¤ à¤†à¤ª à¤•à¥à¤¯à¤¾ à¤œà¤¾à¤¨à¤¨à¤¾ à¤šà¤¾à¤¹à¥‡à¤‚à¤—à¥‡? (Hello! I'm your Marg Darshak guide. I can help you with career, education, mental health, wisdom, skills, AI tools, mentoring, productivity, and overall development. What would you like to know?)"
    
    # Career related queries
    if any(word in message for word in ['career', 'job', 'profession', 'à¤•à¥ˆà¤°à¤¿à¤¯à¤°', 'à¤¨à¥Œà¤•à¤°à¥€']):
        if 'quiz' in message or 'test' in message:
            return """<strong>Career Quiz à¤¦à¥‡à¤¨à¥‡ à¤•à¥‡ à¤²à¤¿à¤:</strong><br>
1. <a href="/career/quiz" target="_blank" class="btn btn-primary btn-sm">Career Quiz</a> à¤ªà¤° à¤œà¤¾à¤à¤‚<br>
2. Questions answer à¤•à¤°à¥‡à¤‚<br>
3. Results à¤¦à¥‡à¤–à¥‡à¤‚ à¤”à¤° career suggestions à¤ªà¤¾à¤à¤‚<br><br>
à¤¯à¤¹ quiz à¤†à¤ªà¤•à¥€ interests à¤•à¥‡ à¤†à¤§à¤¾à¤° à¤ªà¤° suitable careers suggest à¤•à¤°à¥‡à¤—à¤¾!"""
        
        elif 'browse' in message or 'careers' in message:
            return """<strong>à¤¸à¤­à¥€ careers browse à¤•à¤°à¤¨à¥‡ à¤•à¥‡ à¤²à¤¿à¤:</strong><br>
<a href="/career/browse" target="_blank" class="btn btn-success btn-sm">Browse Careers</a> à¤ªà¤° à¤œà¤¾à¤à¤‚<br>
â€¢ Category select à¤•à¤°à¥‡à¤‚ (Technology, Business, Creative, etc.)<br>
â€¢ Difficulty level choose à¤•à¤°à¥‡à¤‚<br>
â€¢ Interesting careers à¤ªà¤° click à¤•à¤°à¥‡à¤‚ à¤”à¤° details à¤ªà¤¢à¤¼à¥‡à¤‚<br><br>
à¤¹à¤° career à¤•à¥€ salary, skills, à¤”à¤° growth information à¤®à¤¿à¤²à¥‡à¤—à¥€!"""
        
        else:
            return """<strong>Career guidance à¤•à¥‡ à¤²à¤¿à¤ à¤†à¤ª à¤¯à¥‡ à¤•à¤° à¤¸à¤•à¤¤à¥‡ à¤¹à¥ˆà¤‚:</strong><br>
â€¢ <a href="/career/quiz" target="_blank">Career Interest Quiz</a> à¤¦à¥‡à¤‚<br>
â€¢ <a href="/career/browse" target="_blank">à¤¸à¤­à¥€ careers browse</a> à¤•à¤°à¥‡à¤‚<br>
â€¢ Specific career details à¤¦à¥‡à¤–à¥‡à¤‚<br>
â€¢ Resume à¤”à¤° portfolio à¤¬à¤¨à¤¾à¤à¤‚<br><br>
à¤®à¥ˆà¤‚ à¤†à¤ªà¤•à¥€ help à¤•à¤° à¤¸à¤•à¤¤à¤¾ à¤¹à¥‚à¤‚ - à¤¬à¤¤à¤¾à¤à¤‚ à¤†à¤ª à¤•à¤¿à¤¸ field à¤®à¥‡à¤‚ interested à¤¹à¥ˆà¤‚?"""
    
    # Education/Platforms queries
    if any(word in message for word in ['learn', 'education', 'platform', 'tool', 'study', 'à¤¸à¥€à¤–à¤¨à¤¾', 'à¤ªà¥à¤²à¥‡à¤Ÿà¤«à¥‰à¤°à¥à¤®']):
        if 'github' in message:
            return """<strong>GitHub use à¤•à¤°à¤¨à¥‡ à¤•à¥‡ à¤²à¤¿à¤ step-by-step guide:</strong><br>
1. <a href="https://github.com" target="_blank">github.com</a> à¤ªà¤° à¤œà¤¾à¤à¤‚ à¤”à¤° account à¤¬à¤¨à¤¾à¤à¤‚<br>
2. Profile complete à¤•à¤°à¥‡à¤‚ (bio, photo add à¤•à¤°à¥‡à¤‚)<br>
3. First repository à¤¬à¤¨à¤¾à¤à¤‚ ("New repository" click à¤•à¤°à¥‡à¤‚)<br>
4. Code files upload à¤•à¤°à¥‡à¤‚ à¤¯à¤¾ create à¤•à¤°à¥‡à¤‚<br>
5. README.md file add à¤•à¤°à¥‡à¤‚ project description à¤•à¥‡ à¤¸à¤¾à¤¥<br><br>
Practice projects upload à¤•à¤°à¤•à¥‡ à¤…à¤ªà¤¨à¤¾ portfolio strong à¤¬à¤¨à¤¾à¤à¤‚!"""
        
        elif 'linkedin' in message:
            return """<strong>LinkedIn profile à¤¬à¤¨à¤¾à¤¨à¥‡ à¤•à¥‡ à¤²à¤¿à¤:</strong><br>
1. <a href="https://linkedin.com" target="_blank">linkedin.com</a> à¤ªà¤° sign up à¤•à¤°à¥‡à¤‚<br>
2. Professional photo à¤”à¤° headline add à¤•à¤°à¥‡à¤‚<br>
3. Education à¤”à¤° experience à¤­à¤°à¥‡à¤‚<br>
4. Skills section à¤®à¥‡à¤‚ à¤…à¤ªà¤¨à¥€ skills add à¤•à¤°à¥‡à¤‚<br>
5. Connections send à¤•à¤°à¥‡à¤‚ (colleagues, seniors)<br><br>
Daily 10-15 minutes à¤®à¥‡à¤‚ posts à¤ªà¤¢à¤¼à¥‡à¤‚ à¤”à¤° networking à¤•à¤°à¥‡à¤‚!"""
        
        elif 'leetcode' in message or 'coding' in message:
            return """<strong>Coding practice à¤•à¥‡ à¤²à¤¿à¤ LeetCode:</strong><br>
1. <a href="https://leetcode.com" target="_blank">leetcode.com</a> à¤ªà¤° account à¤¬à¤¨à¤¾à¤à¤‚<br>
2. Easy problems à¤¸à¥‡ start à¤•à¤°à¥‡à¤‚<br>
3. à¤¹à¤° problem à¤•à¥‹ understand à¤•à¤°à¥‡à¤‚ à¤”à¤° solve à¤•à¤°à¥‡à¤‚<br>
4. Solutions analyze à¤•à¤°à¥‡à¤‚<br>
5. Daily 1-2 problems practice à¤•à¤°à¥‡à¤‚<br><br>
Consistent practice à¤¸à¥‡ interview ready à¤¬à¤¨à¥‡à¤‚à¤—à¥‡!"""
        
        else:
            return """<strong>Learning à¤•à¥‡ à¤²à¤¿à¤ à¤¹à¤®à¤¾à¤°à¥‡ à¤ªà¤¾à¤¸ à¤¹à¥ˆà¤‚:</strong><br>
â€¢ <a href="/ai/tools" target="_blank">AI Tools</a> - ChatGPT, Coursera, YouTube, etc.<br>
â€¢ Learning Guides - Platform-wise tutorials<br>
â€¢ <a href="/skill/browse" target="_blank">Skill Saathi</a> - Curated learning resources<br><br>
à¤†à¤ª à¤•à¥Œà¤¨ à¤¸à¤¾ subject à¤¯à¤¾ skill learn à¤•à¤°à¤¨à¤¾ à¤šà¤¾à¤¹à¤¤à¥‡ à¤¹à¥ˆà¤‚? à¤®à¥ˆà¤‚ guide à¤•à¤° à¤¸à¤•à¤¤à¤¾ à¤¹à¥‚à¤‚!"""
    
    # Mental health queries
    if any(word in message for word in ['mental', 'health', 'stress', 'mood', 'à¤®à¤¨', 'à¤¤à¤¨à¤¾à¤µ', 'à¤®à¤¨à¥‹à¤¦à¤¶à¤¾']):
        if 'breathing' in message or 'à¤¸à¤¾à¤‚à¤¸' in message:
            return """<strong>Guided breathing exercise à¤•à¥‡ à¤²à¤¿à¤:</strong><br>
<a href="/mental/breathing" target="_blank" class="btn btn-info btn-sm">Breathing Exercise</a> à¤ªà¤° à¤œà¤¾à¤à¤‚<br>
â€¢ Instructions follow à¤•à¤°à¥‡à¤‚<br>
â€¢ Deep breaths à¤²à¥‡à¤‚ à¤”à¤° relax à¤•à¤°à¥‡à¤‚<br><br>
Daily 5-10 minutes à¤•à¤¾ practice mental health à¤•à¥‹ strong à¤¬à¤¨à¤¾à¤¤à¤¾ à¤¹à¥ˆ!"""
        
        elif 'mood' in message or 'track' in message:
            return """<strong>Mood tracking à¤•à¤°à¤¨à¥‡ à¤•à¥‡ à¤²à¤¿à¤:</strong><br>
<a href="/mental/mood" target="_blank" class="btn btn-warning btn-sm">Mood Assessment</a> à¤ªà¤° à¤œà¤¾à¤à¤‚<br>
â€¢ Date select à¤•à¤°à¥‡à¤‚<br>
â€¢ Questions answer à¤•à¤°à¥‡à¤‚ (energy, stress, optimism)<br>
â€¢ Notes add à¤•à¤°à¥‡à¤‚<br>
â€¢ Submit à¤•à¤°à¥‡à¤‚<br><br>
à¤†à¤ªà¤•à¤¾ mood history track à¤¹à¥‹ à¤œà¤¾à¤à¤—à¤¾ à¤”à¤° patterns à¤¦à¥‡à¤– à¤¸à¤•à¤¤à¥‡ à¤¹à¥ˆà¤‚!"""
        
        else:
            return """<strong>Mental wellness à¤•à¥‡ à¤²à¤¿à¤:</strong><br>
â€¢ <a href="/mental/mood" target="_blank">Daily mood tracking</a> à¤•à¤°à¥‡à¤‚<br>
â€¢ <a href="/mental/breathing" target="_blank">Guided breathing exercises</a> à¤•à¤°à¥‡à¤‚<br>
â€¢ Stress management tips follow à¤•à¤°à¥‡à¤‚<br>
â€¢ Regular breaks à¤²à¥‡à¤‚ à¤”à¤° exercise à¤•à¤°à¥‡à¤‚<br><br>
à¤†à¤ªà¤•à¥‹ à¤•à¥à¤¯à¤¾ help à¤šà¤¾à¤¹à¤¿à¤ - breathing, mood tracking, à¤¯à¤¾ general tips?"""
    
    # Wisdom/Spiritual queries
    if any(word in message for word in ['wisdom', 'gyan', 'spiritual', 'shloka', 'à¤—à¥€à¤¤à¤¾', 'à¤œà¥à¤žà¤¾à¤¨']):
        if 'daily' in message:
            return """<strong>Daily wisdom à¤ªà¤¾à¤¨à¥‡ à¤•à¥‡ à¤²à¤¿à¤:</strong><br>
<a href="/gyan/daily" target="_blank" class="btn btn-secondary btn-sm">Daily Wisdom</a> à¤ªà¤° à¤œà¤¾à¤à¤‚<br>
â€¢ Bhagavad Gita à¤•à¤¾ random shloka à¤®à¤¿à¤²à¥‡à¤—à¤¾<br>
â€¢ Hindi/English meaning à¤ªà¤¢à¤¼à¥‡à¤‚<br>
â€¢ Practical application à¤¸à¤®à¤à¥‡à¤‚<br><br>
Daily spiritual wisdom à¤¸à¥‡ motivation à¤®à¤¿à¤²à¤¤à¥€ à¤¹à¥ˆ!"""
        
        elif 'search' in message:
            return """<strong>Shloka search à¤•à¤°à¤¨à¥‡ à¤•à¥‡ à¤²à¤¿à¤:</strong><br>
<a href="/gyan/search" target="_blank" class="btn btn-dark btn-sm">Search Shlokas</a> à¤ªà¤° à¤œà¤¾à¤à¤‚<br>
â€¢ Keyword enter à¤•à¤°à¥‡à¤‚ (peace, karma, dharma, etc.)<br>
â€¢ Results à¤¦à¥‡à¤–à¥‡à¤‚<br>
â€¢ Detailed view à¤®à¥‡à¤‚ click à¤•à¤°à¥‡à¤‚<br><br>
Spiritual guidance à¤•à¥‡ à¤²à¤¿à¤ perfect tool à¤¹à¥ˆ!"""
        
        else:
            return """<strong>Spiritual guidance à¤•à¥‡ à¤²à¤¿à¤:</strong><br>
â€¢ <a href="/gyan/daily" target="_blank">Daily Bhagavad Gita shlokas</a> à¤ªà¤¢à¤¼à¥‡à¤‚<br>
â€¢ <a href="/gyan/search" target="_blank">Search à¤•à¤°à¥‡à¤‚</a> specific topics à¤ªà¤°<br>
â€¢ Practical applications à¤¸à¤®à¤à¥‡à¤‚<br>
â€¢ Daily practice à¤®à¥‡à¤‚ implement à¤•à¤°à¥‡à¤‚<br><br>
à¤†à¤ª à¤•à¤¿à¤¸ topic à¤ªà¤° guidance à¤šà¤¾à¤¹à¤¤à¥‡ à¤¹à¥ˆà¤‚?"""
    
    # Skills/Resources queries
    if any(word in message for word in ['skill', 'resource', 'course', 'learning', 'à¤¸à¥à¤•à¤¿à¤²', 'à¤°à¤¿à¤¸à¥‹à¤°à¥à¤¸']):
        return """<strong>Learning resources à¤•à¥‡ à¤²à¤¿à¤:</strong><br>
<a href="/skill/browse" target="_blank" class="btn btn-warning btn-sm">Skill Saathi</a> à¤ªà¤° à¤œà¤¾à¤à¤‚<br>
â€¢ Topic select à¤•à¤°à¥‡à¤‚ (Programming, Design, Business, etc.)<br>
â€¢ Difficulty level choose à¤•à¤°à¥‡à¤‚<br>
â€¢ Free resources filter à¤•à¤°à¥‡à¤‚<br>
â€¢ Best courses à¤”à¤° tutorials à¤®à¤¿à¤²à¥‡à¤‚à¤—à¥‡<br><br>
à¤¸à¤­à¥€ resources quality score à¤•à¥‡ à¤¸à¤¾à¤¥ ranked à¤¹à¥ˆà¤‚!"""
    
    # AI Tools queries
    if any(word in message for word in ['ai', 'tool', 'chatgpt', 'artificial', 'à¤à¤†à¤ˆ', 'à¤Ÿà¥‚à¤²']):
        return """<strong>AI tools à¤•à¥‡ recommendations à¤•à¥‡ à¤²à¤¿à¤:</strong><br>
<a href="/ai/tools" target="_blank" class="btn btn-secondary btn-sm">AI Tools</a> à¤ªà¤° à¤œà¤¾à¤à¤‚<br>
â€¢ Category select à¤•à¤°à¥‡à¤‚ (Writing, Coding, Design, etc.)<br>
â€¢ Free/Paid filter apply à¤•à¤°à¥‡à¤‚<br>
â€¢ Tool details à¤”à¤° tutorials à¤¦à¥‡à¤–à¥‡à¤‚<br>
â€¢ Best tools try à¤•à¤°à¥‡à¤‚<br><br>
ChatGPT, GitHub Copilot, Canva, etc. à¤œà¥ˆà¤¸à¥‡ tools à¤®à¤¿à¤²à¥‡à¤‚à¤—à¥‡!"""
    
    # Mentor queries
    if any(word in message for word in ['mentor', 'guidance', 'teacher', 'expert', 'à¤®à¥‡à¤‚à¤Ÿà¤°']):
        if 'connect' in message or 'chat' in message:
            return """<strong>Mentor à¤¸à¥‡ connect à¤•à¤°à¤¨à¥‡ à¤•à¥‡ à¤²à¤¿à¤:</strong><br>
<a href="/mentor/connect" target="_blank" class="btn btn-danger btn-sm">Mentor Connect</a> à¤ªà¤° à¤œà¤¾à¤à¤‚<br>
â€¢ Available mentors browse à¤•à¤°à¥‡à¤‚<br>
â€¢ Profile à¤¦à¥‡à¤–à¥‡à¤‚ à¤”à¤° message send à¤•à¤°à¥‡à¤‚<br>
â€¢ Chat à¤¶à¥à¤°à¥‚ à¤•à¤°à¥‡à¤‚<br>
â€¢ <a href="/mentor/payment" target="_blank">Payment</a> à¤”à¤° <a href="/mentor/upgrade" target="_blank">upgrade</a> options check à¤•à¤°à¥‡à¤‚<br><br>
Personalized guidance à¤®à¤¿à¤²à¥‡à¤—à¥€!"""
        
        else:
            return """<strong>Mentor guidance à¤•à¥‡ à¤²à¤¿à¤:</strong><br>
â€¢ <a href="/mentor/connect" target="_blank">Available experts à¤¸à¥‡ chat</a> à¤•à¤°à¥‡à¤‚<br>
â€¢ Career advice à¤²à¥‡à¤‚<br>
â€¢ Resume review à¤•à¤°à¤µà¤¾à¤à¤‚<br>
â€¢ Interview preparation à¤•à¤°à¥‡à¤‚<br><br>
à¤†à¤ª à¤•à¤¿à¤¸ field à¤®à¥‡à¤‚ mentor à¤šà¤¾à¤¹à¤¤à¥‡ à¤¹à¥ˆà¤‚?"""
    
    # Todo/Productivity queries
    if any(word in message for word in ['todo', 'task', 'productivity', 'list', 'à¤Ÿà¥‚à¤¡à¥‚', 'à¤Ÿà¤¾à¤¸à¥à¤•']):
        return """<strong>Todo list manage à¤•à¤°à¤¨à¥‡ à¤•à¥‡ à¤²à¤¿à¤:</strong><br>
<a href="/todo" target="_blank" class="btn btn-light text-dark btn-sm">Todo List</a> à¤ªà¤° à¤œà¤¾à¤à¤‚<br>
â€¢ New task add à¤•à¤°à¥‡à¤‚<br>
â€¢ Priority set à¤•à¤°à¥‡à¤‚ (High, Medium, Low)<br>
â€¢ Deadline set à¤•à¤°à¥‡à¤‚<br>
â€¢ Tasks complete mark à¤•à¤°à¥‡à¤‚<br><br>
à¤†à¤ªà¤•à¥€ productivity track à¤¹à¥‹ à¤œà¤¾à¤à¤—à¥€!"""
    
    # Games/Mind fresh queries
    if any(word in message for word in ['game', 'fun', 'joke', 'relax', 'à¤®à¤¨à¥‹à¤°à¤‚à¤œà¤¨']):
        return """<strong>Mind refresh à¤•à¤°à¤¨à¥‡ à¤•à¥‡ à¤²à¤¿à¤:</strong><br>
<a href="/mindfresh" target="_blank" class="btn btn-success btn-sm">Mind Fresh</a> à¤ªà¤° à¤œà¤¾à¤à¤‚<br>
â€¢ Fun games play à¤•à¤°à¥‡à¤‚ (Riddles, Jokes, Puzzles)<br>
â€¢ Daily challenges complete à¤•à¤°à¥‡à¤‚<br>
â€¢ Scores track à¤•à¤°à¥‡à¤‚<br><br>
Short breaks à¤®à¥‡à¤‚ creativity à¤”à¤° energy boost à¤®à¤¿à¤²à¤¤à¤¾ à¤¹à¥ˆ!"""
    
    # Progress/Dashboard queries
    if any(word in message for word in ['progress', 'dashboard', 'activity', 'à¤ªà¥à¤°à¤—à¤¤à¤¿']):
        return """<strong>à¤†à¤ªà¤•à¥€ progress à¤¦à¥‡à¤–à¤¨à¥‡ à¤•à¥‡ à¤²à¤¿à¤:</strong><br>
<a href="/progress" target="_blank" class="btn btn-info btn-sm">Progress Dashboard</a> à¤ªà¤° à¤œà¤¾à¤à¤‚<br>
â€¢ Total activities à¤¦à¥‡à¤–à¥‡à¤‚<br>
â€¢ Module-wise stats check à¤•à¤°à¥‡à¤‚<br>
â€¢ Recent activities à¤¦à¥‡à¤–à¥‡à¤‚<br>
â€¢ Badges à¤”à¤° streaks celebrate à¤•à¤°à¥‡à¤‚<br><br>
à¤†à¤ªà¤•à¤¾ learning journey track à¤¹à¥‹à¤¤à¤¾ à¤¹à¥ˆ!"""
    
    # Student Essentials queries
    if any(word in message for word in ['essential', 'student', 'study', 'notes', 'à¤à¤¸à¥‡à¤‚à¤¶à¤¿à¤¯à¤²', 'à¤¸à¥à¤Ÿà¥‚à¤¡à¥‡à¤‚à¤Ÿ']):
        return """<strong>Student essentials à¤•à¥‡ à¤²à¤¿à¤:</strong><br>
<a href="/essentials" target="_blank" class="btn btn-primary btn-sm">Student Essentials</a> à¤ªà¤° à¤œà¤¾à¤à¤‚<br>
â€¢ Study materials download à¤•à¤°à¥‡à¤‚<br>
â€¢ Important notes à¤”à¤° guides access à¤•à¤°à¥‡à¤‚<br>
â€¢ Exam preparation resources use à¤•à¤°à¥‡à¤‚<br>
â€¢ Academic tools explore à¤•à¤°à¥‡à¤‚<br><br>
à¤¸à¤­à¥€ essential resources à¤à¤• à¤œà¤—à¤¹ à¤®à¤¿à¤²à¥‡à¤‚à¤—à¥‡!"""
    
    # Download/App queries
    if any(word in message for word in ['download', 'app', 'apk', 'mobile', 'à¤¡à¤¾à¤‰à¤¨à¤²à¥‹à¤¡', 'à¤à¤ª']):
        return """<strong>Marg Darshak App download à¤•à¤°à¤¨à¥‡ à¤•à¥‡ à¤²à¤¿à¤:</strong><br>
<strong>Available on:</strong><br>
â€¢ <a href="https://play.google.com/store/search?q=margdarshak" target="_blank" class="btn btn-danger btn-sm"><i class="fab fa-google-play"></i> Google Play Store</a><br>
â€¢ <a href="https://apkpure.com/search?q=margdarshak" target="_blank" class="btn btn-primary btn-sm"><i class="fas fa-store"></i> APKPure</a><br>
â€¢ <a href="https://en.uptodown.com/android/search/margdarshak" target="_blank" class="btn btn-success btn-sm"><i class="fas fa-mobile-alt"></i> Uptodown</a><br>
â€¢ <a href="/static/MargDarshak-App.apk" download class="btn btn-warning btn-sm"><i class="fas fa-file-download"></i> Direct APK</a><br><br>
<strong>Features:</strong> Offline access, push notifications, enhanced mobile experience!<br>
<strong>Trusted app</strong> - Also coming soon on APKPure & Uptodown and Play Store."""
    
    # Roadmap/Career path queries
    if any(word in message for word in ['roadmap', 'path', 'career path', 'à¤°à¥‹à¤¡à¤®à¥ˆà¤ª', 'à¤ªà¤¥']):
        return """<strong>Career roadmap à¤¬à¤¨à¤¾à¤¨à¥‡ à¤•à¥‡ à¤²à¤¿à¤:</strong><br>
<a href="/career/browse" target="_blank" class="btn btn-info btn-sm">Career Browse</a> à¤ªà¤° à¤œà¤¾à¤à¤‚ à¤”à¤° à¤…à¤ªà¤¨à¥€ interested career select à¤•à¤°à¥‡à¤‚<br><br>
<strong>General roadmap steps:</strong><br>
1. <strong>Self-assessment:</strong> Skills à¤”à¤° interests identify à¤•à¤°à¥‡à¤‚<br>
2. <strong>Education:</strong> Required qualifications complete à¤•à¤°à¥‡à¤‚<br>
3. <strong>Skills development:</strong> <a href="/skill/browse" target="_blank">Skill Saathi</a> à¤¸à¥‡ learn à¤•à¤°à¥‡à¤‚<br>
4. <strong>Experience:</strong> Internships/projects à¤•à¤°à¥‡à¤‚<br>
5. <strong>Networking:</strong> <a href="/mentor/connect" target="_blank">Mentors</a> à¤¸à¥‡ connect à¤•à¤°à¥‡à¤‚<br>
6. <strong>Continuous learning:</strong> <a href="/ai/tools" target="_blank">AI tools</a> use à¤•à¤°à¥‡à¤‚<br><br>
à¤®à¥ˆà¤‚ à¤†à¤ªà¤•à¥€ specific career à¤•à¥‡ à¤²à¤¿à¤ detailed roadmap à¤¬à¤¨à¤¾ à¤¸à¤•à¤¤à¤¾ à¤¹à¥‚à¤‚!"""
    
    # Resume/Portfolio queries
    if any(word in message for word in ['resume', 'cv', 'portfolio', 'à¤°à¤¿à¤œà¥à¤¯à¥‚à¤®', 'à¤ªà¥‹à¤°à¥à¤Ÿà¤«à¥‹à¤²à¤¿à¤¯à¥‹']):
        return """<strong>Resume à¤”à¤° portfolio à¤¬à¤¨à¤¾à¤¨à¥‡ à¤•à¥‡ à¤²à¤¿à¤ tips:</strong><br>
1. <strong>Format:</strong> Clean, professional layout use à¤•à¤°à¥‡à¤‚<br>
2. <strong>Content:</strong> Achievements quantify à¤•à¤°à¥‡à¤‚<br>
3. <strong>Skills:</strong> Relevant skills highlight à¤•à¤°à¥‡à¤‚<br>
4. <strong>Projects:</strong> <a href="https://github.com" target="_blank">GitHub</a> links add à¤•à¤°à¥‡à¤‚<br>
5. <strong>LinkedIn:</strong> <a href="https://linkedin.com" target="_blank">Profile</a> optimize à¤•à¤°à¥‡à¤‚<br><br>
<strong>Tools:</strong> Canva, Google Docs, or professional templates use à¤•à¤°à¥‡à¤‚<br>
<a href="/mentor/connect" target="_blank">Mentors à¤¸à¥‡ resume review</a> à¤•à¤°à¤µà¤¾ à¤¸à¤•à¤¤à¥‡ à¤¹à¥ˆà¤‚!"""
    
    # Help/General queries
    if any(word in message for word in ['help', 'how', 'what', 'à¤®à¤¦à¤¦', 'à¤•à¥ˆà¤¸à¥‡']):
        return """à¤®à¥ˆà¤‚ à¤†à¤ªà¤•à¥€ à¤¯à¥‡ à¤®à¤¦à¤¦ à¤•à¤° à¤¸à¤•à¤¤à¤¾ à¤¹à¥‚à¤‚:
â€¢ Career guidance, quiz, à¤”à¤° roadmap
â€¢ Platform tutorials (GitHub, LinkedIn, LeetCode)
â€¢ Mental health tips à¤”à¤° mood tracking
â€¢ Daily wisdom shlokas à¤”à¤° spiritual guidance
â€¢ Learning resources à¤”à¤° skill development
â€¢ AI tools recommendations
â€¢ Mentor connections à¤”à¤° personalized guidance
â€¢ Student essentials à¤”à¤° study materials
â€¢ Student essentials à¤”à¤° study materials
â€¢ Fun games à¤”à¤° mind refresh activities
â€¢ Progress tracking à¤”à¤° dashboard analytics
â€¢ App download à¤”à¤° mobile features
â€¢ Career roadmaps à¤”à¤° resume building tips
â€¢ Step-by-step instructions for all features

à¤†à¤ª à¤•à¥à¤¯à¤¾ à¤œà¤¾à¤¨à¤¨à¤¾ à¤šà¤¾à¤¹à¤¤à¥‡ à¤¹à¥ˆà¤‚? à¤¬à¤¤à¤¾à¤à¤‚! ðŸ˜Š"""
    
    # Default response
    if not any(keyword in message.lower() for keyword in [
        'career', 'job', 'profession', 'à¤•à¥ˆà¤°à¤¿à¤¯à¤°', 'à¤¨à¥Œà¤•à¤°à¥€', 'quiz', 'test', 'browse', 'careers',
        'learn', 'education', 'platform', 'tool', 'study', 'à¤¸à¥€à¤–à¤¨à¤¾', 'à¤ªà¥à¤²à¥‡à¤Ÿà¤«à¥‰à¤°à¥à¤®', 'github', 'linkedin', 'leetcode', 'coding',
        'mental', 'health', 'stress', 'mood', 'à¤®à¤¨', 'à¤¤à¤¨à¤¾à¤µ', 'à¤®à¤¨à¥‹à¤¦à¤¶à¤¾', 'breathing', 'à¤¸à¤¾à¤‚à¤¸', 'track',
        'wisdom', 'gyan', 'spiritual', 'shloka', 'à¤—à¥€à¤¤à¤¾', 'à¤œà¥à¤žà¤¾à¤¨', 'daily', 'search',
        'skill', 'resource', 'course', 'learning', 'à¤¸à¥à¤•à¤¿à¤²', 'à¤°à¤¿à¤¸à¥‹à¤°à¥à¤¸',
        'ai', 'chatgpt', 'artificial', 'à¤à¤†à¤ˆ', 'à¤Ÿà¥‚à¤²',
        'mentor', 'guidance', 'teacher', 'expert', 'à¤®à¥‡à¤‚à¤Ÿà¤°', 'connect', 'chat',
        'todo', 'task', 'productivity', 'list', 'à¤Ÿà¥‚à¤¡à¥‚', 'à¤Ÿà¤¾à¤¸à¥à¤•',
        'game', 'fun', 'joke', 'relax', 'à¤®à¤¨à¥‹à¤°à¤‚à¤œà¤¨',
        'progress', 'dashboard', 'activity', 'à¤ªà¥à¤°à¤—à¤¤à¤¿',
        'essential', 'student', 'notes', 'à¤à¤¸à¥‡à¤‚à¤¶à¤¿à¤¯à¤²', 'à¤¸à¥à¤Ÿà¥‚à¤¡à¥‡à¤‚à¤Ÿ',
        'download', 'app', 'apk', 'mobile', 'à¤¡à¤¾à¤‰à¤¨à¤²à¥‹à¤¡', 'à¤à¤ª',
        'roadmap', 'path', 'à¤°à¥‹à¤¡à¤®à¥ˆà¤ª', 'à¤ªà¤¥',
        'resume', 'cv', 'portfolio', 'à¤°à¤¿à¤œà¥à¤¯à¥‚à¤®', 'à¤ªà¥‹à¤°à¥à¤Ÿà¤«à¥‹à¤²à¤¿à¤¯à¥‹',
        'help', 'how', 'what', 'à¤®à¤¦à¤¦', 'à¤•à¥ˆà¤¸à¥‡'
    ]):
        # Fallback to helpful response for general questions
        return """<strong>à¤®à¥ˆà¤‚ à¤†à¤ªà¤•à¤¾ à¤®à¤¾à¤°à¥à¤—à¤¦à¤°à¥à¤¶à¤• à¤¹à¥‚à¤‚!</strong> à¤®à¥ˆà¤‚ career, education, mental health, wisdom, skills, AI tools, mentoring, productivity, à¤”à¤° overall development à¤®à¥‡à¤‚ help à¤•à¤° à¤¸à¤•à¤¤à¤¾ à¤¹à¥‚à¤‚à¥¤ 

<strong>à¤•à¥à¤› specific à¤ªà¥‚à¤›à¥‡à¤‚ à¤œà¥ˆà¤¸à¥‡:</strong><br>
â€¢ <a href="/career/quiz" target="_blank">Career quiz à¤•à¥ˆà¤¸à¥‡ à¤¦à¥‡à¤‚?</a><br>
â€¢ "GitHub à¤•à¥ˆà¤¸à¥‡ use à¤•à¤°à¥‡à¤‚?"<br>
â€¢ <a href="/mental/mood" target="_blank">Mental health tips</a><br>
â€¢ <a href="/ai/tools" target="_blank">AI tools recommendations</a><br>
â€¢ <a href="/mentor/connect" target="_blank">Mentor à¤•à¥ˆà¤¸à¥‡ connect à¤•à¤°à¥‡à¤‚?</a><br>
â€¢ <a href="/gyan/daily" target="_blank">Daily wisdom à¤•à¥ˆà¤¸à¥‡ à¤ªà¤¾à¤à¤‚?</a><br>
â€¢ <a href="/todo" target="_blank">Todo list à¤•à¥ˆà¤¸à¥‡ manage à¤•à¤°à¥‡à¤‚?</a><br><br>
à¤¯à¤¾ à¤•à¥‹à¤ˆ à¤­à¥€ question à¤ªà¥‚à¤› à¤¸à¤•à¤¤à¥‡ à¤¹à¥ˆà¤‚ - à¤®à¥ˆà¤‚ step-by-step guide à¤¦à¥‚à¤‚à¤—à¤¾! ðŸ¤"""
    # Fallback default response for unmatched specific queries
    return """<strong>à¤®à¥ˆà¤‚ à¤†à¤ªà¤•à¤¾ à¤®à¤¾à¤°à¥à¤—à¤¦à¤°à¥à¤¶à¤• à¤¹à¥‚à¤‚!</strong> à¤®à¥ˆà¤‚ career, education, mental health, wisdom, skills, AI tools, mentoring, productivity, à¤”à¤° overall development à¤®à¥‡à¤‚ help à¤•à¤° à¤¸à¤•à¤¤à¤¾ à¤¹à¥‚à¤‚à¥¤ 

<strong>à¤•à¥à¤› specific à¤ªà¥‚à¤›à¥‡à¤‚ à¤œà¥ˆà¤¸à¥‡:</strong><br>
â€¢ <a href="/career/quiz" target="_blank">"Career quiz à¤•à¥ˆà¤¸à¥‡ à¤¦à¥‡à¤‚?"</a><br>
â€¢ "GitHub à¤•à¥ˆà¤¸à¥‡ use à¤•à¤°à¥‡à¤‚?"<br>
â€¢ <a href="/mental/mood" target="_blank">"Mental health tips"</a><br>
â€¢ <a href="/ai/tools" target="_blank">"AI tools recommendations"</a><br>
â€¢ <a href="/mentor/connect" target="_blank">"Mentor à¤•à¥ˆà¤¸à¥‡ connect à¤•à¤°à¥‡à¤‚?"</a><br>
â€¢ <a href="/gyan/daily" target="_blank">"Daily wisdom à¤•à¥ˆà¤¸à¥‡ à¤ªà¤¾à¤à¤‚?"</a><br>
â€¢ <a href="/todo" target="_blank">"Todo list à¤•à¥ˆà¤¸à¥‡ manage à¤•à¤°à¥‡à¤‚?"</a><br><br>
à¤¯à¤¾ à¤•à¥‹à¤ˆ à¤­à¥€ question à¤ªà¥‚à¤› à¤¸à¤•à¤¤à¥‡ à¤¹à¥ˆà¤‚ - à¤®à¥ˆà¤‚ step-by-step guide à¤¦à¥‚à¤‚à¤—à¤¾! ðŸ¤"""

# ==================== MIND FRESH GAME MODULE ====================
@app.route('/mindfresh')
@login_required
def mindfresh_game():
    try:
        return render_template('mindfresh/game.html')
    except Exception as e:
        print(f"Mind fresh game error: {e}")
        return f"Error: {e}", 500


@app.route('/mindfresh/log', methods=['POST'])
def mindfresh_log():
    log_activity('joke_viewed', 'mindfresh', 'Viewed a joke in mind fresh game')
    return '', 204


# ==================== STUDENT ESSENTIALS MODULE ====================
@app.route('/essentials')
@login_required
def essentials():
    try:
        # Get user-added essentials
        conn = get_db_connection()
        user_essentials = conn.execute('SELECT * FROM user_essentials WHERE user_id = ? ORDER BY created_at DESC', 
                                     (g.current_user['id'],)).fetchall()
        conn.close()
        
        user_essentials_list = [dict(row) for row in user_essentials]
        return render_template('essentials/index.html', user_essentials=user_essentials_list)
    except Exception as e:
        print(f"Essentials error: {e}")
        return f"Error: {e}", 500

@app.route('/essentials/add', methods=['GET', 'POST'])
@login_required
def add_essential():
    if request.method == 'POST':
        name = request.form.get('name')
        category = request.form.get('category')
        price = request.form.get('price')
        link = request.form.get('link')
        description = request.form.get('description')
        
        if not name or not category:
            flash('Name and category are required', 'error')
            return redirect(url_for('add_essential'))
        
        try:
            conn = get_db_connection()
            conn.execute('INSERT INTO user_essentials (user_id, name, category, price, link, description) VALUES (?, ?, ?, ?, ?, ?)',
                        (g.current_user['id'], name, category, price, link, description))
            conn.commit()
            conn.close()
            
            log_activity('essential_added', 'essentials', f'Added essential: {name}', 
                        f'Category: {category}, Price: {price}')
            
            flash('Essential added successfully!', 'success')
            return redirect(url_for('essentials'))
        except Exception as e:
            print(f"Add essential error: {e}")
            flash('Error adding essential', 'error')
            return redirect(url_for('add_essential'))
    
    return render_template('essentials/add.html')

@app.route('/essentials/delete/<int:essential_id>', methods=['POST'])
@login_required
def delete_essential(essential_id):
    try:
        conn = get_db_connection()
        # Check if the essential belongs to the current user
        essential = conn.execute('SELECT * FROM user_essentials WHERE id = ? AND user_id = ?', 
                               (essential_id, g.current_user['id'])).fetchone()
        
        if essential:
            conn.execute('DELETE FROM user_essentials WHERE id = ?', (essential_id,))
            conn.commit()
            log_activity('essential_deleted', 'essentials', f'Deleted essential: {essential["name"]}')
            flash('Essential deleted successfully!', 'success')
        else:
            flash('Essential not found', 'error')
        
        conn.close()
        return redirect(url_for('essentials'))
    except Exception as e:
        print(f"Delete essential error: {e}")
        flash('Error deleting essential', 'error')
        return redirect(url_for('essentials'))


# ==================== TO-DO LIST MODULE ====================
@app.route('/todo')
@login_required
def todo():
    try:
        conn = get_db_connection()
        user_id = session.get('user_id', 1)  # Default to user 1 for demo
        
        # Get today's tasks
        today = datetime.now().strftime('%Y-%m-%d')
        today_tasks = conn.execute('''
            SELECT * FROM todo_tasks 
            WHERE user_id = ? AND DATE(deadline) = ?
            ORDER BY 
                CASE priority 
                    WHEN 'High' THEN 1 
                    WHEN 'Medium' THEN 2 
                    WHEN 'Low' THEN 3 
                END, created_at DESC
        ''', (user_id, today)).fetchall()
        
        # Get all pending tasks for this week
        week_start = (datetime.now() - timedelta(days=datetime.now().weekday())).strftime('%Y-%m-%d')
        week_end = (datetime.now() + timedelta(days=6-datetime.now().weekday())).strftime('%Y-%m-%d')
        
        weekly_tasks = conn.execute('''
            SELECT * FROM todo_tasks 
            WHERE user_id = ? AND status = 'Pending' 
            AND DATE(deadline) BETWEEN ? AND ?
            ORDER BY deadline, 
                CASE priority 
                    WHEN 'High' THEN 1 
                    WHEN 'Medium' THEN 2 
                    WHEN 'Low' THEN 3 
                END
        ''', (user_id, week_start, week_end)).fetchall()
        
        # Get completed tasks count for today
        completed_today = conn.execute('''
            SELECT COUNT(*) FROM todo_tasks 
            WHERE user_id = ? AND status = 'Completed' 
            AND DATE(completed_at) = ?
        ''', (user_id, today)).fetchone()[0]
        
        # Get total tasks for today
        total_today = len(today_tasks)
        
        conn.close()
        
        return render_template('todo/index.html', 
                             today_tasks=today_tasks, 
                             weekly_tasks=weekly_tasks,
                             completed_today=completed_today,
                             total_today=total_today)
    except Exception as e:
        print(f"To-do error: {e}")
        return f"Error: {e}", 500


@app.route('/todo/add', methods=['GET', 'POST'])
@login_required
def add_task():
    if request.method == 'POST':
        try:
            user_id = session.get('user_id', 1)  # Default to user 1 for demo
            title = request.form['title']
            description = request.form.get('description', '')
            category = request.form['category']
            priority = request.form['priority']
            deadline = request.form['deadline']
            
            conn = get_db_connection()
            conn.execute('''
                INSERT INTO todo_tasks (user_id, title, description, category, priority, deadline)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (user_id, title, description, category, priority, deadline))
            conn.commit()
            conn.close()
            
            flash('Task added successfully! ðŸŽ‰', 'success')
            return redirect(url_for('todo'))
        except Exception as e:
            print(f"Add task error: {e}")
            flash('Error adding task. Please try again.', 'error')
            return redirect(url_for('todo'))
    
    return render_template('todo/add.html')


@app.route('/todo/edit/<int:task_id>', methods=['GET', 'POST'])
@login_required
def edit_task(task_id):
    try:
        user_id = session.get('user_id', 1)  # Default to user 1 for demo
        conn = get_db_connection()
        
        if request.method == 'POST':
            title = request.form['title']
            description = request.form.get('description', '')
            category = request.form['category']
            priority = request.form['priority']
            deadline = request.form['deadline']
            
            conn.execute('''
                UPDATE todo_tasks 
                SET title = ?, description = ?, category = ?, priority = ?, deadline = ?
                WHERE id = ? AND user_id = ?
            ''', (title, description, category, priority, deadline, task_id, user_id))
            conn.commit()
            flash('Task updated successfully! âœï¸', 'success')
            return redirect(url_for('todo'))
        
        # GET request - show edit form
        task = conn.execute('SELECT * FROM todo_tasks WHERE id = ? AND user_id = ?', 
                          (task_id, user_id)).fetchone()
        conn.close()
        
        if not task:
            flash('Task not found.', 'error')
            return redirect(url_for('todo'))
            
        return render_template('todo/edit.html', task=task)
        
    except Exception as e:
        print(f"Edit task error: {e}")
        flash('Error updating task. Please try again.', 'error')
        return redirect(url_for('todo'))


@app.route('/todo/delete/<int:task_id>', methods=['POST'])
@login_required
def delete_task(task_id):
    try:
        user_id = session.get('user_id', 1)  # Default to user 1 for demo
        conn = get_db_connection()
        conn.execute('DELETE FROM todo_tasks WHERE id = ? AND user_id = ?', (task_id, user_id))
        conn.commit()
        conn.close()
        
        flash('Task deleted successfully! ðŸ—‘ï¸', 'success')
        return redirect(url_for('todo'))
    except Exception as e:
        print(f"Delete task error: {e}")
        flash('Error deleting task. Please try again.', 'error')
        return redirect(url_for('todo'))


@app.route('/todo/complete/<int:task_id>', methods=['POST'])
@login_required
def complete_task(task_id):
    try:
        user_id = session.get('user_id', 1)  # Default to user 1 for demo
        conn = get_db_connection()
        
        # Check if task exists and belongs to user
        task = conn.execute('SELECT * FROM todo_tasks WHERE id = ? AND user_id = ?', 
                          (task_id, user_id)).fetchone()
        
        if task:
            if task['status'] == 'Pending':
                # Mark as completed
                conn.execute('''
                    UPDATE todo_tasks 
                    SET status = 'Completed', completed_at = CURRENT_TIMESTAMP 
                    WHERE id = ?
                ''', (task_id,))
                flash('Great job! Task completed! ðŸŽ‰', 'success')
            else:
                # Mark as pending
                conn.execute('''
                    UPDATE todo_tasks 
                    SET status = 'Pending', completed_at = NULL 
                    WHERE id = ?
                ''', (task_id,))
                flash('Task marked as pending.', 'info')
        
        conn.commit()
        conn.close()
        return redirect(url_for('todo'))
        
    except Exception as e:
        print(f"Complete task error: {e}")
        flash('Error updating task. Please try again.', 'error')
        return redirect(url_for('todo'))


# ==================== PRIVACY POLICY ====================
@app.route("/privacy-policy")
def privacy_policy():
    return render_template("privacy.html")


# ==================== PWA ROUTES ====================
@app.route("/manifest.json")
def manifest():
    return send_from_directory("static", "manifest.json")

@app.route("/service-worker.js")
def service_worker():
    return send_from_directory("static", "service-worker.js")


# ==================== MENTOR CONNECT ====================

@app.route('/mentor')
@login_required
def mentor_redirect():
    return redirect('/mentor-connect')


@app.route('/mentor-connect')
@login_required
def mentor_connect():
    user = g.current_user
    is_admin = user.get('email') == 'yashshelke98320@gmail.com'

    conn = get_db_connection()
    user_row = conn.execute(
        'SELECT mentor_access FROM users WHERE id = ?',
        (user['id'],)
    ).fetchone()

    if user_row and user_row['mentor_access']:
        # User has mentor access
        if is_admin:
            users = conn.execute(
                'SELECT id, username, email, is_premium, mentor_access, created_at FROM users'
            ).fetchall()

            requests = conn.execute('''
                SELECT mr.id, u.username, u.email, mr.utr, mr.status, mr.created_at
                FROM mentor_requests mr
                JOIN users u ON mr.user_id = u.id
                ORDER BY mr.created_at DESC
            ''').fetchall()

            conn.close()

            return render_template(
                'mentor/connect.html',
                users=users,
                requests=requests,
                is_admin=True
            )
        else:
            conn.close()
            return render_template('mentor/chat.html')
    else:
        conn.close()
        return render_template('mentor/payment.html')


@app.route('/mentor-request', methods=['POST'])
@login_required
def mentor_request():
    utr = request.form.get('utr')

    if not utr:
        flash('UTR is required.', 'danger')
        return redirect('/mentor-connect')

    conn = get_db_connection()
    conn.execute(
        'INSERT INTO mentor_requests (user_id, utr) VALUES (?, ?)',
        (g.current_user['id'], utr)
    )
    conn.commit()
    conn.close()

    flash(
        'Payment request submitted! We will verify and activate your access within 24 hours.',
        'success'
    )
    return redirect('/mentor-connect')


# ==================== ADMIN PANEL ====================
# ==================== ADMIN PANEL ====================

@app.route('/admin', methods=['GET', 'POST'])
def admin_panel():
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')

        if email == 'yashshelke98320@gmail.com' and password == 'Yash9353':
            session['admin_logged_in'] = True
            return redirect('/admin')
        else:
            flash('Invalid credentials.', 'danger')
            return render_template('admin/login.html')

    if not session.get('admin_logged_in'):
        return render_template('admin/login.html')

    conn = get_db_connection()

    users = conn.execute(
        'SELECT id, username, email, is_premium, mentor_access, created_at FROM users'
    ).fetchall()

    requests = conn.execute('''
        SELECT mr.id, u.username, u.email, mr.utr, mr.created_at, mr.status
        FROM mentor_requests mr
        JOIN users u ON mr.user_id = u.id
        ORDER BY mr.created_at DESC
    ''').fetchall()

    conn.close()

    return render_template('admin/panel.html', users=users, requests=requests)


@app.route('/admin/logout')
def admin_logout():
    session.pop('admin_logged_in', None)
    flash('Logged out from admin panel.', 'info')
    return redirect('/admin')


@app.route('/admin/mentor-request/<int:request_id>/approve')
def approve_mentor_request(request_id):
    if not session.get('admin_logged_in'):
        flash('Access denied.', 'danger')
        return redirect('/admin')

    conn = get_db_connection()

    row = conn.execute(
        'SELECT user_id FROM mentor_requests WHERE id = ?',
        (request_id,)
    ).fetchone()

    if row:
        user_id = row['user_id']

        conn.execute(
            'UPDATE users SET mentor_access = 1 WHERE id = ?',
            (user_id,)
        )
        conn.execute(
            'UPDATE mentor_requests SET status = "approved" WHERE id = ?',
            (request_id,)
        )
        conn.commit()
        flash('Mentor access approved!', 'success')
    else:
        flash('Request not found.', 'danger')

    conn.close()
    return redirect('/admin')


@app.route('/admin/mentor-request/<int:request_id>/reject')
def reject_mentor_request(request_id):
    if not session.get('admin_logged_in'):
        flash('Access denied.', 'danger')
        return redirect('/admin')

    conn = get_db_connection()
    conn.execute(
        'UPDATE mentor_requests SET status = "rejected" WHERE id = ?',
        (request_id,)
    )
    conn.commit()
    conn.close()

    flash('Mentor request rejected.', 'warning')
    return redirect('/admin')


@app.route('/admin/user/<int:user_id>/toggle_premium')
def toggle_premium(user_id):
    if not session.get('admin_logged_in'):
        flash('Access denied.', 'danger')
        return redirect('/admin')

    conn = get_db_connection()

    row = conn.execute(
        'SELECT is_premium FROM users WHERE id = ?',
        (user_id,)
    ).fetchone()

    if row:
        new_status = 0 if row['is_premium'] else 1
        conn.execute(
            'UPDATE users SET is_premium = ? WHERE id = ?',
            (new_status, user_id)
        )
        conn.commit()
        flash(
            f'Premium access {"granted" if new_status else "revoked"} for user.',
            'success'
        )

    conn.close()
    return redirect('/admin')


@app.route('/admin/user/<int:user_id>/toggle_mentor')
def toggle_mentor(user_id):
    if not session.get('admin_logged_in'):
        flash('Access denied.', 'danger')
        return redirect('/admin')

    conn = get_db_connection()

    row = conn.execute(
        'SELECT mentor_access FROM users WHERE id = ?',
        (user_id,)
    ).fetchone()

    if row:
        new_status = 0 if row['mentor_access'] else 1
        conn.execute(
            'UPDATE users SET mentor_access = ? WHERE id = ?',
            (new_status, user_id)
        )
        conn.commit()
        flash(
            f'Mentor access {"granted" if new_status else "revoked"} for user.',
            'success'
        )

    conn.close()
    return redirect('/admin')



# ==================== INTERNSHIP MODULE ====================
def normalize_apply_link(raw_link):
    """Return a normalized apply link (http/https/mailto) or '' if not provided."""
    link = (raw_link or '').strip()
    if not link:
        return ''

    # Disallow script-style links.
    if link.lower().startswith(('javascript:', 'data:', 'vbscript:')):
        return None

    if link.lower().startswith('mailto:'):
        email = link[7:].strip()
        if '@' in email:
            return f'mailto:{email}'
        return None

    candidate = link if '://' in link else f'https://{link}'
    parsed = urlparse(candidate)
    if parsed.scheme not in ('http', 'https') or not parsed.netloc:
        return None
    return candidate


def get_or_create_internship_record(conn, internship_company, role, city, mode, apply_link=''):
    normalized_company = internship_company.lower()
    normalized_role = role.lower()
    normalized_city = city.lower()
    normalized_mode = mode.lower()

    internship = conn.execute(
        'SELECT id, apply_link FROM internships WHERE lower(company)=? AND lower(role)=? AND lower(city)=? AND lower(mode)=?',
        (normalized_company, normalized_role, normalized_city, normalized_mode)
    ).fetchone()

    if internship:
        internship_id = internship['id']
        existing_link = (internship['apply_link'] or '').strip() if 'apply_link' in internship.keys() else ''
        if apply_link and (not existing_link):
            conn.execute('UPDATE internships SET apply_link = ? WHERE id = ?', (apply_link, internship_id))
        return internship_id

    cursor = conn.execute(
        'INSERT INTO internships (company, role, city, mode, stipend, apply_link, source) VALUES (?, ?, ?, ?, ?, ?, ?)',
        (internship_company, role, city, mode, 'Not Disclosed', apply_link, 'student')
    )
    return cursor.lastrowid


@app.route('/internships')
@login_required
def internships_page():
    log_activity('page_view', 'internships', 'Browsed internships')
    try:
        # Get search parameter
        search_query = request.args.get('search', '').strip()

        conn = get_db_connection()
        internship_count = conn.execute('SELECT COUNT(*) as count FROM internships').fetchone()['count']
        experience_count = conn.execute('SELECT COUNT(*) as count FROM internship_experiences').fetchone()['count']
        conn.close()

        return render_template('internships/browse.html',
                             internship_count=internship_count,
                             experience_count=experience_count,
                             search_query=search_query)
    except Exception as e:
        print(f"Internships page count error: {e}")
        return render_template('internships/browse.html',
                             internship_count=0,
                             experience_count=0,
                             search_query='')

@app.route('/internships/share-experience')
@login_required
def share_experience_page():
    log_activity('page_view', 'internship_experience', 'Viewed internship experience form')
    return render_template('internships/share_experience.html')

@app.route('/internships/community')
@login_required
def internship_community():
    log_activity('page_view', 'internship_community', 'Viewed internship community')
    return render_template('internships/community.html')

@app.route('/add-experience', methods=['POST'])
@login_required
def add_experience():
    data = request.get_json() if request.is_json else request.form
    name = (data.get('name') or '').strip() or g.current_user.get('username', '')
    college = (data.get('college') or '').strip()
    internship_company = (data.get('internship_company') or '').strip()
    city = (data.get('city') or '').strip()
    mode = (data.get('mode') or '').strip().title()
    role = (data.get('role') or '').strip()
    how_got = (data.get('how_got') or '').strip()
    tips = (data.get('tips') or '').strip()
    interview_questions = (data.get('interview_questions') or '').strip()
    apply_link = normalize_apply_link(data.get('apply_link'))

    if not college:
        return jsonify({'error': 'College is required.'}), 400
    if not internship_company:
        return jsonify({'error': 'Internship Company is required.'}), 400
    if not role:
        return jsonify({'error': 'Role is required.'}), 400
    if not how_got:
        return jsonify({'error': 'How they got the internship is required.'}), 400
    if not tips:
        return jsonify({'error': 'Tips are required.'}), 400
    if apply_link is None:
        return jsonify({'error': 'Please provide a valid apply link (http/https or mailto).'}), 400

    conn = get_db_connection()
    internship_id = get_or_create_internship_record(
        conn,
        internship_company=internship_company,
        role=role,
        city=city,
        mode=mode,
        apply_link=apply_link or ''
    )

    conn.execute(
        'INSERT INTO internship_experiences (internship_id, user_id, name, college, internship_company, city, mode, role, how_got, tips, interview_questions, apply_link) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)',
        (internship_id, g.current_user['id'], name, college, internship_company, city, mode, role, how_got, tips, interview_questions, apply_link or '')
    )
    conn.commit()
    conn.close()

    return jsonify({'success': True, 'message': 'Your experience has been shared successfully.'})


@app.route('/update-experience/<int:experience_id>', methods=['POST', 'PUT'])
@login_required
def update_experience(experience_id):
    data = request.get_json() if request.is_json else request.form
    name = (data.get('name') or '').strip() or g.current_user.get('username', '')
    college = (data.get('college') or '').strip()
    internship_company = (data.get('internship_company') or '').strip()
    city = (data.get('city') or '').strip()
    mode = (data.get('mode') or '').strip().title()
    role = (data.get('role') or '').strip()
    how_got = (data.get('how_got') or '').strip()
    tips = (data.get('tips') or '').strip()
    interview_questions = (data.get('interview_questions') or '').strip()
    apply_link = normalize_apply_link(data.get('apply_link'))

    if not college:
        return jsonify({'error': 'College is required.'}), 400
    if not internship_company:
        return jsonify({'error': 'Internship Company is required.'}), 400
    if not role:
        return jsonify({'error': 'Role is required.'}), 400
    if not how_got:
        return jsonify({'error': 'How they got the internship is required.'}), 400
    if not tips:
        return jsonify({'error': 'Tips are required.'}), 400
    if apply_link is None:
        return jsonify({'error': 'Please provide a valid apply link (http/https or mailto).'}), 400

    conn = get_db_connection()
    existing = conn.execute(
        'SELECT id, user_id FROM internship_experiences WHERE id = ?',
        (experience_id,)
    ).fetchone()
    if not existing:
        conn.close()
        return jsonify({'error': 'Story not found.'}), 404
    if existing['user_id'] != g.current_user['id']:
        conn.close()
        return jsonify({'error': 'You can edit only your own story.'}), 403

    internship_id = get_or_create_internship_record(
        conn,
        internship_company=internship_company,
        role=role,
        city=city,
        mode=mode,
        apply_link=apply_link or ''
    )

    conn.execute(
        '''UPDATE internship_experiences
           SET internship_id = ?, name = ?, college = ?, internship_company = ?, city = ?, mode = ?,
               role = ?, how_got = ?, tips = ?, interview_questions = ?, apply_link = ?
           WHERE id = ?''',
        (internship_id, name, college, internship_company, city, mode, role, how_got, tips, interview_questions, apply_link or '', experience_id)
    )
    conn.commit()
    conn.close()
    return jsonify({'success': True, 'message': 'Your story has been updated successfully.'})

@app.route('/get-experiences')
@login_required
def get_experiences():
    try:
        company = request.args.get('company', '').strip().lower()
        city = request.args.get('city', '').strip().lower()
        mode = request.args.get('mode', '').strip().lower()

        query = 'SELECT * FROM internship_experiences WHERE 1=1'
        params = []
        if company:
            query += ' AND lower(internship_company) LIKE ?'
            params.append(f'%{company}%')
        if city and city != 'all':
            query += ' AND lower(city) LIKE ?'
            params.append(f'%{city}%')
        if mode and mode != 'all':
            query += ' AND lower(mode) LIKE ?'
            params.append(f'%{mode}%')

        query += ' ORDER BY created_at DESC'

        conn = get_db_connection()
        rows = conn.execute(query, params).fetchall()
        conn.close()

        data = []
        for row in rows:
            owner_id = row['user_id'] if 'user_id' in row.keys() else None
            data.append({
                'id': row['id'],
                'name': row['name'],
                'college': row['college'],
                'internship_company': row['internship_company'],
                'city': row['city'],
                'mode': row['mode'],
                'role': row['role'],
                'how_got': row['how_got'],
                'tips': row['tips'],
                'interview_questions': row['interview_questions'],
                'apply_link': row['apply_link'],
                'created_at': row['created_at'],
                'can_edit': bool(owner_id and owner_id == g.current_user['id'])
            })

        return jsonify({'count': len(data), 'data': data})
    except Exception as e:
        print(f"Error fetching internship experiences: {e}")
        return jsonify({'count': 0, 'data': [], 'error': str(e)}), 500


# ==================== STUDENT COMMUNITY CHAT MODULE ====================
def get_student_connection(conn, user_a, user_b):
    return conn.execute(
        '''SELECT * FROM student_connections
           WHERE (requester_id = ? AND addressee_id = ?)
              OR (requester_id = ? AND addressee_id = ?)
           ORDER BY id DESC
           LIMIT 1''',
        (user_a, user_b, user_b, user_a)
    ).fetchone()


def get_accepted_connection(conn, user_a, user_b):
    return conn.execute(
        '''SELECT * FROM student_connections
           WHERE status = 'accepted'
             AND ((requester_id = ? AND addressee_id = ?)
               OR (requester_id = ? AND addressee_id = ?))
           LIMIT 1''',
        (user_a, user_b, user_b, user_a)
    ).fetchone()


def get_student_connection_ids(conn, user_id):
    rows = conn.execute(
        '''SELECT requester_id, addressee_id FROM student_connections
           WHERE status = 'accepted'
             AND (requester_id = ? OR addressee_id = ?)''',
        (user_id, user_id)
    ).fetchall()
    return {row['addressee_id'] if row['requester_id'] == user_id else row['requester_id'] for row in rows}


def serialize_student_user(conn, user, viewer_connections=None):
    current_user_id = g.current_user['id']
    other_id = user['id']
    connection = get_student_connection(conn, current_user_id, other_id)
    other_connections = get_student_connection_ids(conn, other_id)
    viewer_connections = viewer_connections if viewer_connections is not None else get_student_connection_ids(conn, current_user_id)

    status = 'none'
    direction = 'none'
    request_id = None
    if connection:
        status = connection['status']
        request_id = connection['id']
        if status == 'pending':
            direction = 'sent' if connection['requester_id'] == current_user_id else 'received'
        elif status == 'accepted':
            direction = 'connected'
        else:
            direction = 'rejected'

    return {
        'id': other_id,
        'username': user['username'] or 'Student',
        'connection_status': status,
        'request_direction': direction,
        'request_id': request_id,
        'connection_count': len(other_connections),
        'mutual_count': len(viewer_connections.intersection(other_connections)),
        'joined_at': user['created_at']
    }


@app.route('/student-community')
@login_required
def student_community():
    log_activity('page_view', 'student_community', 'Viewed student community chat')
    return render_template('community/student.html')


@app.route('/api/student-community/users')
@login_required
def student_community_users():
    try:
        query = (request.args.get('q') or '').strip().lower()
        current_user_id = g.current_user['id']
        conn = get_db_connection()
        viewer_connections = get_student_connection_ids(conn, current_user_id)

        if query:
            rows = conn.execute(
                '''SELECT id, username, email, created_at FROM users
                   WHERE id != ?
                     AND (lower(username) LIKE ? OR lower(email) LIKE ?)
                   ORDER BY username COLLATE NOCASE
                   LIMIT 60''',
                (current_user_id, f'%{query}%', f'%{query}%')
            ).fetchall()
        else:
            rows = conn.execute(
                '''SELECT id, username, email, created_at FROM users
                   WHERE id != ?
                   ORDER BY created_at DESC
                   LIMIT 60''',
                (current_user_id,)
            ).fetchall()

        users = [serialize_student_user(conn, row, viewer_connections) for row in rows]
        conn.close()
        return jsonify({'users': users})
    except Exception as e:
        print(f"Student community users error: {e}")
        return jsonify({'error': 'Unable to load students.'}), 500


@app.route('/api/student-community/requests', methods=['GET'])
@login_required
def student_connection_requests():
    try:
        current_user_id = g.current_user['id']
        conn = get_db_connection()
        rows = conn.execute(
            '''SELECT sc.id, sc.created_at, u.id AS user_id, u.username, u.created_at AS joined_at
               FROM student_connections sc
               JOIN users u ON u.id = sc.requester_id
               WHERE sc.addressee_id = ? AND sc.status = 'pending'
               ORDER BY sc.created_at DESC''',
            (current_user_id,)
        ).fetchall()
        requests_data = []
        for row in rows:
            requests_data.append({
                'id': row['id'],
                'user_id': row['user_id'],
                'username': row['username'] or 'Student',
                'created_at': row['created_at'],
                'joined_at': row['joined_at']
            })
        conn.close()
        return jsonify({'requests': requests_data})
    except Exception as e:
        print(f"Student connection requests error: {e}")
        return jsonify({'error': 'Unable to load requests.'}), 500


@app.route('/api/student-community/connect/<int:user_id>', methods=['POST'])
@login_required
def send_student_connection_request(user_id):
    current_user_id = g.current_user['id']
    if user_id == current_user_id:
        return jsonify({'error': 'You cannot connect with yourself.'}), 400

    try:
        conn = get_db_connection()
        target = conn.execute('SELECT id FROM users WHERE id = ?', (user_id,)).fetchone()
        if not target:
            conn.close()
            return jsonify({'error': 'Student not found.'}), 404

        existing = get_student_connection(conn, current_user_id, user_id)
        if existing:
            if existing['status'] == 'accepted':
                conn.close()
                return jsonify({'message': 'You are already connected.', 'status': 'accepted'})
            if existing['status'] == 'pending' and existing['requester_id'] == current_user_id:
                conn.close()
                return jsonify({'message': 'Connection request already sent.', 'status': 'pending'})
            if existing['status'] == 'pending' and existing['addressee_id'] == current_user_id:
                conn.execute(
                    "UPDATE student_connections SET status = 'accepted', updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                    (existing['id'],)
                )
                conn.commit()
                conn.close()
                return jsonify({'message': 'Connection accepted.', 'status': 'accepted'})
            if existing['status'] == 'rejected':
                conn.execute(
                    '''UPDATE student_connections
                       SET requester_id = ?, addressee_id = ?, status = 'pending', updated_at = CURRENT_TIMESTAMP
                       WHERE id = ?''',
                    (current_user_id, user_id, existing['id'])
                )
                conn.commit()
                conn.close()
                return jsonify({'message': 'Connection request sent again.', 'status': 'pending'})

        conn.execute(
            'INSERT INTO student_connections (requester_id, addressee_id, status) VALUES (?, ?, ?)',
            (current_user_id, user_id, 'pending')
        )
        conn.commit()
        conn.close()
        return jsonify({'message': 'Connection request sent.', 'status': 'pending'})
    except Exception as e:
        print(f"Send connection request error: {e}")
        return jsonify({'error': 'Unable to send connection request.'}), 500


@app.route('/api/student-community/requests/<int:request_id>/<action>', methods=['POST'])
@login_required
def handle_student_connection_request(request_id, action):
    if action not in ('accept', 'reject'):
        return jsonify({'error': 'Invalid action.'}), 400

    try:
        current_user_id = g.current_user['id']
        new_status = 'accepted' if action == 'accept' else 'rejected'
        conn = get_db_connection()
        request_row = conn.execute(
            '''SELECT id FROM student_connections
               WHERE id = ? AND addressee_id = ? AND status = 'pending' ''',
            (request_id, current_user_id)
        ).fetchone()
        if not request_row:
            conn.close()
            return jsonify({'error': 'Request not found.'}), 404

        conn.execute(
            'UPDATE student_connections SET status = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?',
            (new_status, request_id)
        )
        conn.commit()
        conn.close()
        return jsonify({'message': f'Request {new_status}.', 'status': new_status})
    except Exception as e:
        print(f"Handle connection request error: {e}")
        return jsonify({'error': 'Unable to update request.'}), 500


@app.route('/api/student-community/connections')
@login_required
def student_connections():
    try:
        current_user_id = g.current_user['id']
        conn = get_db_connection()
        viewer_connections = get_student_connection_ids(conn, current_user_id)
        rows = conn.execute(
            '''SELECT sc.id AS connection_id,
                      CASE WHEN sc.requester_id = ? THEN sc.addressee_id ELSE sc.requester_id END AS user_id,
                      u.username,
                      u.created_at AS joined_at,
                      sc.updated_at,
                      (
                        SELECT message FROM student_messages sm
                        WHERE sm.connection_id = sc.id
                        ORDER BY sm.created_at DESC, sm.id DESC
                        LIMIT 1
                      ) AS last_message,
                      (
                        SELECT created_at FROM student_messages sm
                        WHERE sm.connection_id = sc.id
                        ORDER BY sm.created_at DESC, sm.id DESC
                        LIMIT 1
                      ) AS last_message_at,
                      (
                        SELECT COUNT(*) FROM student_messages sm
                        WHERE sm.connection_id = sc.id
                          AND sm.receiver_id = ?
                          AND sm.is_read = 0
                      ) AS unread_count
               FROM student_connections sc
               JOIN users u ON u.id = CASE WHEN sc.requester_id = ? THEN sc.addressee_id ELSE sc.requester_id END
               WHERE sc.status = 'accepted'
                 AND (sc.requester_id = ? OR sc.addressee_id = ?)
               ORDER BY COALESCE(last_message_at, sc.updated_at) DESC''',
            (current_user_id, current_user_id, current_user_id, current_user_id, current_user_id)
        ).fetchall()

        data = []
        for row in rows:
            other_connections = get_student_connection_ids(conn, row['user_id'])
            data.append({
                'connection_id': row['connection_id'],
                'user_id': row['user_id'],
                'username': row['username'] or 'Student',
                'joined_at': row['joined_at'],
                'connected_at': row['updated_at'],
                'last_message': row['last_message'],
                'last_message_at': row['last_message_at'],
                'unread_count': row['unread_count'],
                'connection_count': len(other_connections),
                'mutual_count': len(viewer_connections.intersection(other_connections))
            })
        conn.close()
        return jsonify({'connections': data, 'count': len(data)})
    except Exception as e:
        print(f"Student connections error: {e}")
        return jsonify({'error': 'Unable to load connections.'}), 500


@app.route('/api/student-community/messages/<int:user_id>', methods=['GET', 'POST'])
@login_required
def student_messages(user_id):
    current_user_id = g.current_user['id']
    if user_id == current_user_id:
        return jsonify({'error': 'Choose another student to chat with.'}), 400

    try:
        conn = get_db_connection()
        connection = get_accepted_connection(conn, current_user_id, user_id)
        if not connection:
            conn.close()
            return jsonify({'error': 'You can chat only after the connection is accepted.'}), 403

        if request.method == 'POST':
            data = request.get_json() if request.is_json else request.form
            message = (data.get('message') or '').strip()
            if not message:
                conn.close()
                return jsonify({'error': 'Message cannot be empty.'}), 400
            if len(message) > 1000:
                conn.close()
                return jsonify({'error': 'Message is too long.'}), 400

            conn.execute(
                '''INSERT INTO student_messages (connection_id, sender_id, receiver_id, message)
                   VALUES (?, ?, ?, ?)''',
                (connection['id'], current_user_id, user_id, message)
            )
            conn.commit()

        conn.execute(
            '''UPDATE student_messages
               SET is_read = 1
               WHERE connection_id = ? AND receiver_id = ?''',
            (connection['id'], current_user_id)
        )
        conn.commit()

        rows = conn.execute(
            '''SELECT id, sender_id, receiver_id, message, is_read, created_at
               FROM student_messages
               WHERE connection_id = ?
               ORDER BY created_at ASC, id ASC
               LIMIT 200''',
            (connection['id'],)
        ).fetchall()
        messages = []
        for row in rows:
            messages.append({
                'id': row['id'],
                'sender_id': row['sender_id'],
                'receiver_id': row['receiver_id'],
                'message': row['message'],
                'is_own': row['sender_id'] == current_user_id,
                'is_read': bool(row['is_read']),
                'created_at': row['created_at']
            })
        conn.close()
        return jsonify({'messages': messages})
    except Exception as e:
        print(f"Student messages error: {e}")
        return jsonify({'error': 'Unable to load messages.'}), 500


@app.route('/api/internships')
def get_internships_api():
    try:
        print("API: Starting request...")
        file_path = os.path.join(BASE_DIR, 'data', 'internships_300_updated-1.xlsx')

        title = request.args.get('title', '').strip().lower()
        domain = request.args.get('domain', '').strip().lower()
        field = request.args.get('field', '').strip().lower()
        city = request.args.get('city', '').strip().lower()
        mode = request.args.get('mode', '').strip().lower()
        stipend_filter = request.args.get('stipend', '').strip().lower()

        excel_rows = []
        if os.path.exists(file_path):
            try:
                print("API: Reading Excel...")
                df = pd.read_excel(file_path, engine="openpyxl")
                print("API: Excel loaded.")
                df.columns = df.columns.str.strip()
                df = df.fillna('')

                records = df.to_dict(orient='records')
                for row in records:
                    if title and title not in str(row.get('Title', '')).lower():
                        continue
                    if domain and domain not in str(row.get('Company Name', '')).lower():
                        continue
                    if field and field not in str(row.get('Field', '')).lower():
                        continue
                    r_city = str(row.get('City', '')).lower()
                    if city and city != 'all' and city not in r_city:
                        continue
                    r_mode = str(row.get('Mode', '')).lower()
                    if mode and mode != 'all' and mode not in r_mode:
                        continue

                    stipend_val = str(row.get('Stipend', '')).strip().lower()
                    is_unpaid = (not stipend_val or stipend_val == '0' or stipend_val == 'unpaid' or stipend_val == 'none')
                    if stipend_filter == 'paid' and is_unpaid:
                        continue
                    if stipend_filter == 'unpaid' and not is_unpaid:
                        continue

                    excel_rows.append({
                        'Title': row.get('Title', ''),
                        'Company Name': row.get('Company Name', ''),
                        'City': row.get('City', ''),
                        'Mode': row.get('Mode', ''),
                        'Field': row.get('Field', ''),
                        'Stipend': row.get('Stipend', ''),
                        'Duration': row.get('Duration', ''),
                        'Skills Required': row.get('Skills Required', ''),
                        'Apply Link': row.get('Apply Link', ''),
                        'How to Apply': row.get('How to Apply', ''),
                        'Source': row.get('Source', ''),
                        'Verified': row.get('Verified', ''),
                        'student_added': False
                    })
            except Exception as excel_error:
                print(f"API: Error reading Excel file: {excel_error}")

        conn = get_db_connection()
        db_query = 'SELECT * FROM internships WHERE 1=1'
        db_params = []
        if title:
            db_query += ' AND lower(role) LIKE ?'
            db_params.append(f'%{title}%')
        if domain:
            db_query += ' AND lower(company) LIKE ?'
            db_params.append(f'%{domain}%')
        if city and city != 'all':
            db_query += ' AND lower(city) LIKE ?'
            db_params.append(f'%{city}%')
        if mode and mode != 'all':
            db_query += ' AND lower(mode) LIKE ?'
            db_params.append(f'%{mode}%')
        if stipend_filter == 'paid':
            db_query += ' AND lower(stipend) NOT IN (?, ?, ?)' 
            db_params.extend(['', '0', 'not disclosed'])
        elif stipend_filter == 'unpaid':
            db_query += ' AND lower(stipend) IN (?, ?, ?, ?)' 
            db_params.extend(['', '0', 'unpaid', 'not disclosed'])

        student_rows = []
        db_rows = conn.execute(db_query, db_params).fetchall()
        conn.close()
        for row in db_rows:
            stipend_val = str(row['stipend'] or '').strip()
            student_rows.append({
                'Title': row['role'],
                'Company Name': row['company'],
                'City': row['city'],
                'Mode': row['mode'],
                'Field': '',
                'Stipend': stipend_val or 'Not Disclosed',
                'Duration': '',
                'Skills Required': '',
                'Apply Link': row['apply_link'] if 'apply_link' in row.keys() else '',
                'How to Apply': '',
                'Source': 'Student',
                'Verified': 'No',
                'student_added': True
            })

        combined = excel_rows + student_rows
        return jsonify({'count': len(combined), 'data': combined})
    except Exception as e:
        print(f"Error reading internships API: {e}")
        return jsonify({'count': 0, 'data': [], 'error': str(e)}), 500


@app.route('/api/notifications')
@login_required
def get_notifications_api():
    """Lightweight real-time notifications for header popup."""
    try:
        user_id = g.current_user['id']
        conn = get_db_connection()

        notifications = []

        # Pending student connection requests.
        pending_count = conn.execute(
            'SELECT COUNT(*) AS c FROM student_connections WHERE addressee_id = ? AND status = ?',
            (user_id, 'pending')
        ).fetchone()['c']
        if pending_count:
            notifications.append({
                'id': f'pending-requests-{pending_count}',
                'title': 'Student Community',
                'message': f'You have {pending_count} pending connection request(s).',
                'link': '/student-community'
            })

        # Pending GD invites for current user.
        pending_gd_invites = conn.execute(
            '''SELECT COUNT(*) AS c
               FROM gd_invites gi
               JOIN gd_sessions gs ON gs.id = gi.session_id
               WHERE gi.to_user = ?
                 AND gi.status = 'pending'
                 AND gs.status IN ('planning', 'active')''',
            (user_id,)
        ).fetchone()['c']
        if pending_gd_invites:
            notifications.append({
                'id': f'pending-gd-invites-{pending_gd_invites}',
                'title': 'GD Invite',
                'message': f'You have {pending_gd_invites} pending GD invite(s).',
                'link': '/gd'
            })

        # Join requests on rooms hosted by current user.
        pending_join_requests = conn.execute(
            '''SELECT COUNT(*) AS c
               FROM gd_join_requests jr
               JOIN gd_sessions gs ON gs.id = jr.session_id
               WHERE gs.host_user_id = ?
                 AND jr.status = 'pending'
                 AND gs.status IN ('planning', 'active')''',
            (user_id,)
        ).fetchone()['c']
        if pending_join_requests:
            notifications.append({
                'id': f'pending-gd-join-requests-{pending_join_requests}',
                'title': 'GD Join Requests',
                'message': f'{pending_join_requests} student(s) requested to join your GD room.',
                'link': '/gd'
            })

        # Unread community chat messages.
        unread_count = conn.execute(
            'SELECT COUNT(*) AS c FROM student_messages WHERE receiver_id = ? AND is_read = 0',
            (user_id,)
        ).fetchone()['c']
        if unread_count:
            latest_message = conn.execute(
                '''SELECT sm.message, u.username
                   FROM student_messages sm
                   JOIN users u ON u.id = sm.sender_id
                   WHERE sm.receiver_id = ? AND sm.is_read = 0
                   ORDER BY sm.created_at DESC, sm.id DESC
                   LIMIT 1''',
                (user_id,)
            ).fetchone()
            preview = (latest_message['message'][:55] + '...') if latest_message and latest_message['message'] and len(latest_message['message']) > 55 else (latest_message['message'] if latest_message else '')
            sender = latest_message['username'] if latest_message else 'a student'
            notifications.append({
                'id': f'unread-messages-{unread_count}',
                'title': 'New Messages',
                'message': f'{unread_count} unread message(s). Latest from {sender}: {preview}',
                'link': '/student-community'
            })

        # New internship stories in last 24 hours (community pulse).
        recent_stories = conn.execute(
            "SELECT COUNT(*) AS c FROM internship_experiences WHERE created_at >= datetime('now', '-1 day')"
        ).fetchone()['c']
        if recent_stories:
            notifications.append({
                'id': f'recent-stories-{recent_stories}',
                'title': 'Internship Community',
                'message': f'{recent_stories} new internship story(s) shared in the last 24 hours.',
                'link': '/internships/community'
            })

        # Daily aptitude quiz reminder.
        today_quiz_done = conn.execute(
            '''SELECT COUNT(*) AS c
               FROM user_activity
               WHERE user_id = ?
                 AND activity_type = 'aptitude_quiz_completed'
                 AND date(timestamp, 'localtime') = date('now', 'localtime')''',
            (user_id,)
        ).fetchone()['c']
        if not today_quiz_done:
            notifications.append({
                'id': 'daily-aptitude-reminder',
                'title': 'Daily Aptitude Quiz',
                'message': 'Please solve today\'s aptitude quiz (10 questions) to boost placement readiness.',
                'link': '/skill/aptitude-quiz'
            })

        conn.close()
        return jsonify({
            'success': True,
            'unread_count': len(notifications),
            'notifications': notifications,
            'generated_at': datetime.utcnow().isoformat() + 'Z'
        })
    except Exception as e:
        print(f"Notifications API error: {e}")
        return jsonify({'success': False, 'notifications': [], 'unread_count': 0}), 500

# ==================== ERROR HANDLERS ====================
@app.errorhandler(404)
def page_not_found(e):
    return render_template('404.html'), 404

@app.errorhandler(500)
def internal_error(e):
    return render_template('500.html'), 500




# ==================== RUN APP ====================
if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
# trigger reload
