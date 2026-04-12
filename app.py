import os
import sqlite3
from datetime import datetime, timedelta
from flask import Flask, render_template, request, redirect, url_for, session, flash, g, send_from_directory
from werkzeug.security import generate_password_hash, check_password_hash
import pandas as pd
from functools import wraps

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'dev_secret_change_me')

# ✅ Login Required Decorator
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not getattr(g, 'current_user', None):
            flash('Please log in to access this feature.', 'warning')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

# ✅ Correct absolute path for DB inside "database" folder
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "database", "marg_darshak.db")

# ✅ Auto-create tables if not exist and load data if empty
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
            print(f"✅ Loaded {len(careers_df)} careers")
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
            print(f"✅ Loaded {len(gyan_df)} gyan kosh entries")
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
            print(f"✅ Loaded {len(resources_df)} learning resources")
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

    conn.commit()
    conn.close()

# ✅ Run table creation before app starts
init_db()


# ✅ Connection helper
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


# ✅ Activity logging helper
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


# ----------------- Auth routes -----------------
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
            'tools': 17,  # Number of AI tools available
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
        
        if category == 'all':
            careers = conn.execute('SELECT * FROM careers ORDER BY title').fetchall()
        else:
            careers = conn.execute('SELECT * FROM careers WHERE category = ? ORDER BY title', (category,)).fetchall()
        
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
                             selected_category=category)
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
            
            return render_template('gyan/daily.html', shloka=dict(shloka))
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
            badges.append({'name': 'First Steps', 'icon': '👶', 'description': 'Started your journey'})
        if total_activities >= 10:
            badges.append({'name': 'Explorer', 'icon': '🗺️', 'description': 'Explored 10+ activities'})
        if total_activities >= 50:
            badges.append({'name': 'Dedicated Learner', 'icon': '📚', 'description': '50+ learning activities'})
        if current_streak >= 7:
            badges.append({'name': 'Consistency King', 'icon': '👑', 'description': '7+ day learning streak'})
        if module_stats.get('career', 0) >= 5:
            badges.append({'name': 'Career Explorer', 'icon': '🎯', 'description': 'Explored 5+ careers'})
        if module_stats.get('gyan', 0) >= 10:
            badges.append({'name': 'Wisdom Seeker', 'icon': '🧘', 'description': 'Read 10+ spiritual verses'})
        if module_stats.get('mental', 0) >= 5:
            badges.append({'name': 'Mindful Soul', 'icon': '🌸', 'description': 'Completed 5+ mental wellness activities'})
        
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
        'description': 'Smart expense tracking and budgeting tool for students.'
    },
    'mock_interview': {
        'name': 'AI Mock Interviewer',
        'url': 'https://aimockinterviewer-one.vercel.app/',
        'description': 'Practice mock interviews with AI for job preparation.'
    },
    'leetcode': {
        'name': 'LeetCode',
        'url': 'https://leetcode.com',
        'description': 'Practice data structures and algorithms with coding problems.'
    },
    'wolfram': {
        'name': 'WolframAlpha',
        'url': 'https://www.wolframalpha.com',
        'description': 'Powerful computation engine for math, science, and data.'
    },
    'khan': {
        'name': 'Khan Academy',
        'url': 'https://www.khanacademy.org',
        'description': 'Free video lessons and practice exercises across subjects.'
    },
    'coursera': {
        'name': 'Coursera',
        'url': 'https://www.coursera.org',
        'description': 'Online courses from top universities (some free options).'
    },
    'stackoverflow': {
        'name': 'Stack Overflow',
        'url': 'https://stackoverflow.com',
        'description': 'Community Q&A for programming and development questions.'
    },
    'grammarly': {
        'name': 'Grammarly',
        'url': 'https://www.grammarly.com',
        'description': 'Writing assistant for grammar, clarity, and tone.'
    },
    'replit': {
        'name': 'Replit',
        'url': 'https://replit.com',
        'description': 'In-browser coding environment to write and test code quickly.'
    },
    'gamma': {
        'name': 'Gamma',
        'url': 'https://gamma.app',
        'description': 'AI-powered presentation maker for creating stunning slides.'
    },
    'napkin': {
        'name': 'Napkin AI',
        'url': 'https://napkin.ai',
        'description': 'AI tool for creating flowcharts, diagrams, and visual ideas.'
    },
    'chatgpt': {
        'name': 'ChatGPT',
        'url': 'https://chat.openai.com',
        'description': 'Conversational AI for answering questions and generating text.'
    },
    'deepseek': {
        'name': 'DeepSeek',
        'url': 'https://chat.deepseek.com',
        'description': 'AI chat tool for research, coding, and creative tasks.'
    },
    'notebooklm': {
        'name': 'NotebookLM',
        'url': 'https://notebooklm.google.com',
        'description': 'AI-powered notebook for organizing and summarizing notes.'
    },
    'gemini': {
        'name': 'Gemini AI',
        'url': 'https://gemini.google.com',
        'description': 'Google\'s multimodal AI for text, images, and more.'
    },
    'ppt_to_word': {
        'name': 'PPT to Word',
        'url': 'https://www.ilovepdf.com/ppt-to-word',
        'description': 'Convert PowerPoint presentations to Word documents online.'
    },
    'word_to_ppt': {
        'name': 'Word to PPT',
        'url': 'https://www.ilovepdf.com/word-to-ppt',
        'description': 'Convert Word documents to PowerPoint presentations.'
    },
    'word_to_pdf': {
        'name': 'Word to PDF',
        'url': 'https://www.ilovepdf.com/word-to-pdf',
        'description': 'Convert Word documents to PDF format easily.'
    }
}

@app.route('/ai/tools')
@login_required
def ai_tools():
    try:
        return render_template('ai/tools.html', tools=TOOLS_CATALOG)
    except Exception as e:
        print(f"AI tools page error: {e}")
        return f"Error: {e}", 500


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
        {'id': 'linkedin', 'name': 'LinkedIn', 'icon': '💼', 'description': 'Professional networking platform'},
        {'id': 'github', 'name': 'GitHub', 'icon': '📁', 'description': 'Code sharing and collaboration'},
        {'id': 'leetcode', 'name': 'LeetCode', 'icon': '💻', 'description': 'Coding practice platform'},
        {'id': 'vscode', 'name': 'VS Code', 'icon': '🛠️', 'description': 'Code editor for development'},
        {'id': 'git_vscode', 'name': 'GitHub + VS Code', 'icon': '🔗', 'description': 'Basic workflow together'},
        {'id': 'email_google', 'name': 'Email & Google Account', 'icon': '📧', 'description': 'Professional communication'},
        {'id': 'resume_portfolio', 'name': 'Resume & Portfolio', 'icon': '📄', 'description': 'Building your online presence'},
        {'id': 'coursera', 'name': 'Coursera', 'icon': '🎓', 'description': 'Online learning platform'},
        {'id': 'stackoverflow', 'name': 'Stack Overflow', 'icon': '❓', 'description': 'Programming Q&A community'},
        {'id': 'youtube', 'name': 'YouTube Learning', 'icon': '📺', 'description': 'Free educational videos'},
        {'id': 'bca', 'name': 'BCA Students', 'icon': '💻', 'description': 'IT & Computer Applications guidance'},
        {'id': 'bsc', 'name': 'BSc Students', 'icon': '🔬', 'description': 'Science stream career guidance'},
        {'id': 'pharmacy', 'name': 'Pharmacy Students', 'icon': '💊', 'description': 'Pharmaceutical career platforms'},
        {'id': 'medical', 'name': 'Medical Students', 'icon': '🏥', 'description': 'MBBS & Allied Health guidance'},
        {'id': 'agriculture', 'name': 'Agriculture Students', 'icon': '🌾', 'description': 'Agri-tech & farming platforms'},
        {'id': 'mpsc', 'name': 'MPSC Aspirants', 'icon': '📋', 'description': 'Maharashtra PSC exam preparation'},
        {'id': 'upsc', 'name': 'UPSC Aspirants', 'icon': '🇮🇳', 'description': 'Civil services exam guidance'}
    ]
    return render_template('learn/index.html', platforms=platforms)

@app.route('/learn/<platform>')
def learn_platform(platform):
    log_activity('guide_view', 'learn', f'Viewed learning guide for {platform}')
    guides = {
        'linkedin': {
            'title': 'LinkedIn - Professional Networking',
            'content': '''
            <h3>क्या है LinkedIn? (What is LinkedIn?)</h3>
            <p>LinkedIn एक professional social media platform है, जहाँ आप अपने field के लोगों से connect कर सकते हैं, jobs खोज सकते हैं, और अपनी skills दिखा सकते हैं। Think of it as Facebook for professionals!</p>

            <h3>क्यों use करें? (Why use it?)</h3>
            <p>As a student, LinkedIn आपको professional network बनाने में मदद करता है, internships मिलती हैं, और आप different careers के बारे में learn कर सकते हैं। यह आपके resume से ज्यादा powerful है!</p>

            <h3>Account कैसे बनाएँ? (How to create account)</h3>
            <ol>
                <li>linkedin.com पर जाएँ और "Join now" click करें</li>
                <li>अपना college email और strong password use करें</li>
                <li>Profile complete करें - photo, education, skills add करें</li>
                <li>Connections send करें - teachers, seniors से start करें</li>
            </ol>

            <h3>Daily कैसे use करें? (How to use daily)</h3>
            <p>Daily 10-15 minutes में:
            <ul>
                <li>Posts पढ़ें और like/comment करें</li>
                <li>1-2 connections बनाएँ</li>
                <li>अपनी skills या projects update करें</li>
                <li>Jobs section में internships देखें</li>
            </ul></p>

            <h3>Common Beginner Mistakes</h3>
            <ul>
                <li>Profile incomplete छोड़ना</li>
                <li>Spam messages भेजना</li>
                <li>Bad profile photo use करना</li>
                <li>Connections को ignore करना</li>
            </ul>

            <h3>Best Practices for Freshers</h3>
            <ul>
                <li>Regular updates करें - weekly at least</li>
                <li>Meaningful connections बनाएँ, not random</li>
                <li>Learn करने का attitude रखें - ask questions</li>
                <li>Endorsements और recommendations collect करें</li>
                <li>Groups join करें related to your field</li>
            </ul>

            <div class="alert alert-info">
                <strong>Pro Tip:</strong> LinkedIn पर "Student" badge मिलता है। Use it to get free premium features!
            </div>
            '''
        },
        'github': {
            'title': 'GitHub - Code Sharing Platform',
            'content': '''
            <h3>क्या है GitHub? (What is GitHub?)</h3>
            <p>GitHub एक platform है जहाँ developers अपना code share करते हैं, collaborate करते हैं, और projects manage करते हैं। यह coding का Facebook है!</p>

            <h3>क्यों use करें? (Why use it?)</h3>
            <p>यह आपके coding skills को showcase करने का best way है। Companies आपके GitHub profile देखती हैं। Plus, आप open source projects में contribute करके learn कर सकते हैं और experience gain कर सकते हैं।</p>

            <h3>Account कैसे बनाएँ? (How to create account)</h3>
            <ol>
                <li>github.com पर जाएँ</li>
                <li>"Sign up" click करें</li>
                <li>Unique username choose करें (professional wala)</li>
                <li>Email verify करें</li>
                <li>Profile setup करें - bio, photo add करें</li>
            </ol>

            <h3>Daily कैसे use करें? (How to use daily)</h3>
            <p>Start small:
            <ul>
                <li>अपना first repository बनाएँ</li>
                <li>कुछ simple code upload करें</li>
                <li>Other people's repositories explore करें</li>
                <li>Star interesting projects</li>
                <li>Issues में help try करें</li>
            </ul></p>

            <h3>Common Beginner Mistakes</h3>
            <ul>
                <li>Private repos को accidentally public करना</li>
                <li>Proper commit messages न लिखना</li>
                <li>README file न बनाना</li>
                <li>Code को organize न करना</li>
            </ul>

            <h3>Best Practices for Freshers</h3>
            <ul>
                <li>Regular contributions करें (daily if possible)</li>
                <li>README.md file जरूर बनाएँ with project description</li>
                <li>Projects को meaningful names दें</li>
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
            <h3>क्या है LeetCode? (What is LeetCode?)</h3>
            <p>LeetCode एक platform है जहाँ आप coding problems solve कर सकते हैं, जो real interviews में पूछे जाते हैं। यह coding का gym है!</p>

            <h3>क्यों use करें? (Why use it?)</h3>
            <p>यह आपके problem-solving skills को improve करता है और coding interviews की preparation में मदद करता है। Companies like Google, Amazon आपके LeetCode performance देखती हैं।</p>

            <h3>Account कैसे बनाएँ? (How to create account)</h3>
            <ol>
                <li>leetcode.com पर जाएँ</li>
                <li>"Sign up" click करें</li>
                <li>Email और password enter करें</li>
                <li>Programming language select करें (Python recommend for beginners)</li>
            </ol>

            <h3>Daily कैसे use करें? (How to use daily)</h3>
            <p>Consistency is key:
            <ul>
                <li>Daily 1 problem solve करें</li>
                <li>Easy से start करें</li>
                <li>Solution को analyze करें</li>
                <li>Discussion section पढ़ें</li>
                <li>Weekly contests में participate करें</li>
            </ul></p>

            <h3>Common Beginner Mistakes</h3>
            <ul>
                <li>सभी solutions copy करना</li>
                <li>Time complexity को ignore करना</li>
                <li>Only easy problems करना</li>
                <li>Without understanding submit करना</li>
            </ul>

            <h3>Best Practices for Freshers</h3>
            <ul>
                <li>Consistent practice करें - daily 1 hour</li>
                <li>Different topics cover करें (arrays, strings, trees, etc.)</li>
                <li>Multiple approaches try करें</li>
                <li>Streak maintain करें</li>
                <li>Study plans follow करें</li>
            </ul>

            <div class="alert alert-warning">
                <strong>Remember:</strong> Quality over quantity. समझकर solve करें!
            </div>
            '''
        },
        'vscode': {
            'title': 'VS Code - Code Editor',
            'content': '''
            <h3>क्या है VS Code? (What is VS Code?)</h3>
            <p>VS Code एक free, powerful code editor है जो developers use करते हैं code लिखने, debug करने, और projects manage करने के लिए। यह coding का Swiss Army knife है!</p>

            <h3>क्यों use करें? (Why use it?)</h3>
            <p>यह easy to learn है, सभी programming languages support करता है, और extensions से super powerful बन जाता है। Professional developers का favorite tool है।</p>

            <h3>कैसे install करें? (How to install)</h3>
            <ol>
                <li>code.visualstudio.com पर जाएँ</li>
                <li>"Download" click करें (right version for your OS)</li>
                <li>Install करें (next-next finish)</li>
                <li>Open करें और "Get Started" tour करें</li>
            </ol>

            <h3>Daily कैसे use करें? (How to use daily)</h3>
            <p>Make it your daily companion:
            <ul>
                <li>Coding practice करें</li>
                <li>Extensions explore करें</li>
                <li>Keyboard shortcuts learn करें</li>
                <li>Themes change करें for fun</li>
            </ul></p>

            <h3>Common Beginner Mistakes</h3>
            <ul>
                <li>Too many extensions install करना</li>
                <li>Settings को customize न करना</li>
                <li>Keyboard shortcuts न learn करना</li>
                <li>Files को unsaved छोड़ना</li>
            </ul>

            <h3>Best Practices for Freshers</h3>
            <ul>
                <li>Essential extensions install करें (Python, Git, etc.)</li>
                <li>Settings customize करें (font size, theme)</li>
                <li>Keyboard shortcuts master करें</li>
                <li>Projects को organized folders में रखें</li>
                <li>Version control (Git) integrate करें</li>
            </ul>

            <div class="alert alert-info">
                <strong>Pro Tip:</strong> VS Code has built-in terminal, debugger, and Git integration!
            </div>
            '''
        },
        'git_vscode': {
            'title': 'GitHub + VS Code Workflow',
            'content': '''
            <h3>क्या है यह workflow? (What is this workflow?)</h3>
            <p>GitHub और VS Code को together use करके आप code लिख सकते हैं, changes track कर सकते हैं, और online share कर सकते हैं। यह modern development का standard way है!</p>

            <h3>क्यों use करें? (Why use it?)</h3>
            <p>यह version control और collaboration को easy बनाता है। आप अपने code को safely store कर सकते हैं और team में work कर सकते हैं।</p>

            <h3>कैसे setup करें? (How to setup)</h3>
            <ol>
                <li>VS Code में Git extension install करें (usually pre-installed)</li>
                <li>GitHub से repository clone करें (VS Code में Ctrl+Shift+P → Git: Clone)</li>
                <li>Code लिखें और save करें</li>
                <li>Changes commit करें (Source Control panel में)</li>
                <li>Push करें to GitHub</li>
            </ol>

            <h3>Daily कैसे use करें? (How to use daily)</h3>
            <p>Simple routine:
            <ul>
                <li>Morning: Pull latest changes</li>
                <li>Code लिखें और test करें</li>
                <li>Evening: Commit और push करें</li>
                <li>Issues check करें और help करें</li>
            </ul></p>

            <h3>Common Beginner Mistakes</h3>
            <ul>
                <li>Merge conflicts को fear करना</li>
                <li>Large files commit करना</li>
                <li>Commit messages में "fixed" लिखना</li>
                <li>Push करने से पहले test न करना</li>
            </ul>

            <h3>Best Practices for Freshers</h3>
            <ul>
                <li>Small, frequent commits करें</li>
                <li>Descriptive commit messages लिखें</li>
                <li>Before push, code review करें</li>
                <li>Branching learn करें for features</li>
                <li>README और .gitignore जरूर बनाएँ</li>
            </ul>

            <div class="alert alert-success">
                <strong>Power Combo:</strong> VS Code + GitHub = Professional Developer Setup!
            </div>
            '''
        },
        'email_google': {
            'title': 'Email & Google Account',
            'content': '''
            <h3>क्या है Professional Email? (What is Professional Email?)</h3>
            <p>Professional communication के लिए separate email account। यह आपके personal और work emails को separate रखता है।</p>

            <h3>क्यों use करें? (Why use it?)</h3>
            <p>Companies और professors आपके email से आपका impression बनाते हैं। Professional email से आप serious और organized लगते हैं।</p>

            <h3>कैसे setup करें? (How to setup)</h3>
            <ol>
                <li>gmail.com पर जाएँ</li>
                <li>"Create account" click करें</li>
                <li>Professional name use करें (first.last or something)</li>
                <li>Recovery email और phone add करें</li>
                <li>Signature setup करें with your name and contact</li>
            </ol>

            <h3>Daily कैसे use करें? (How to use daily)</h3>
            <p>Professional habits:
            <ul>
                <li>Morning में emails check करें</li>
                <li>Within 24 hours reply करें</li>
                <li>Spam folder clean करें</li>
                <li>Important emails को label करें</li>
            </ul></p>

            <h3>Common Beginner Mistakes</h3>
            <ul>
                <li>Funny email addresses use करना</li>
                <li>Emails को unread छोड़ना</li>
                <li>Personal और professional mix करना</li>
                <li>Bad subject lines लिखना</li>
            </ul>

            <h3>Best Practices for Freshers</h3>
            <ul>
                <li>Clear, professional subject lines use करें</li>
                <li>Proper greeting और closing use करें</li>
                <li>Grammar check करें before sending</li>
                <li>Attachments को properly name करें</li>
                <li>Follow-up emails भेजें if needed</li>
            </ul>

            <div class="alert alert-info">
                <strong>Pro Tip:</strong> Use Google Calendar for scheduling and Google Drive for file sharing!
            </div>
            '''
        },
        'resume_portfolio': {
            'title': 'Resume & Portfolio',
            'content': '''
            <h3>क्या है Resume और Portfolio? (What are Resume and Portfolio?)</h3>
            <p>Resume आपके skills और experience का 1-page summary है। Portfolio आपके work का detailed showcase है - projects, achievements, etc.</p>

            <h3>क्यों बनाएँ? (Why create them?)</h3>
            <p>Jobs, internships, और admissions के लिए essential हैं। Resume से companies आपका overview मिलता है, portfolio से proof!</p>

            <h3>कैसे बनाएँ? (How to create)</h3>
            <h4>Resume:</h4>
            <ol>
                <li>Simple format choose करें (Google Docs या Canva)</li>
                <li>Contact info, education, skills add करें</li>
                <li>Projects और achievements highlight करें</li>
                <li>PDF format में save करें</li>
            </ol>

            <h4>Portfolio:</h4>
            <ol>
                <li>GitHub Pages use करें (free)</li>
                <li>अपने projects showcase करें</li>
                <li>About और contact page add करें</li>
                <li>Live link share करें</li>
            </ol>

            <h3>Common Beginner Mistakes</h3>
            <ul>
                <li>Resume को 2+ pages बनाना</li>
                <li>Too much information add करना</li>
                <li>Portfolio को incomplete छोड़ना</li>
                <li>Bad design choose करना</li>
            </ul>

            <h3>Best Practices for Freshers</h3>
            <ul>
                <li>Keep resume to 1 page</li>
                <li>Use action words (Developed, Created, etc.)</li>
                <li>Quantify achievements (numbers use करें)</li>
                <li>Regularly update करें</li>
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
            <h3>क्या है Coursera? (What is Coursera?)</h3>
            <p>Coursera एक online learning platform है जहाँ top universities के courses मिलते हैं। यह college का extension है!</p>

            <h3>क्यों use करें? (Why use it?)</h3>
            <p>यह आपको world-class education देता है। Certificates मिलते हैं जो resume में add हो सकते हैं।</p>

            <h3>कैसे start करें? (How to start)</h3>
            <ol>
                <li>coursera.org पर जाएँ</li>
                <li>Free account बनाएँ</li>
                <li>Courses browse करें</li>
                <li>Audit mode में free access लें</li>
            </ol>

            <h3>Best Practices</h3>
            <ul>
                <li>Weekly schedule बनाएँ</li>
                <li>Assignments complete करें</li>
                <li>Discussion forums में participate करें</li>
            </ul>
            '''
        },
        'stackoverflow': {
            'title': 'Stack Overflow - Programming Q&A',
            'content': '''
            <h3>क्या है Stack Overflow? (What is Stack Overflow?)</h3>
            <p>Programming का largest Q&A community। जब भी stuck हों, यहाँ answer मिलेगा!</p>

            <h3>क्यों use करें? (Why use it?)</h3>
            <p>Learn करने के लिए best place। Questions पूछें और answers दें।</p>

            <h3>कैसे use करें? (How to use)</h3>
            <ol>
                <li>stackoverflow.com पर जाएँ</li>
                <li>Account बनाएँ</li>
                <li>Questions search करें</li>
                <li>Helpful answers upvote करें</li>
            </ol>

            <h3>Best Practices</h3>
            <ul>
                <li>Proper questions पूछें</li>
                <li>Answers को research करें</li>
                <li>Helpful बनें</li>
            </ul>
            '''
        },
        'youtube': {
            'title': 'YouTube Learning Channels',
            'content': '''
            <h3>क्या है YouTube Learning? (What is YouTube Learning?)</h3>
            <p>YouTube पर free educational content का ocean है। Videos से learn करना easy है!</p>

            <h3>क्यों use करें? (Why use it?)</h3>
            <p>Visual learning best है। Free resources मिलते हैं।</p>

            <h3>Recommended Channels</h3>
            <ul>
                <li>freeCodeCamp</li>
                <li>Traversy Media</li>
                <li>CS Dojo</li>
                <li>Programming with Mosh</li>
            </ul>

            <h3>Best Practices</h3>
            <ul>
                <li>Playlist follow करें</li>
                <li>Notes बनाते जाएँ</li>
                <li>Practice करते जाएँ</li>
            </ul>
            '''
        },
        'bca': {
            'title': 'BCA Students - IT Career Guidance',
            'content': '''
            <h3>BCA क्या है? (What is BCA?)</h3>
            <p>BCA (Bachelor of Computer Applications) computer science का graduation course है। यह IT field में strong foundation देता है।</p>

            <h3>कैरियर के लिए जरूरी Platforms (Essential Platforms for Career)</h3>

            <h4>1. LinkedIn</h4>
            <p>IT jobs के लिए must। Profile बनाएँ और IT companies follow करें।</p>

            <h4>2. GitHub</h4>
            <p>Code showcase करने के लिए। Mini projects upload करें।</p>

            <h4>3. LeetCode / HackerRank</h4>
            <p>Coding skills improve करने के लिए। Daily practice करें।</p>

            <h4>4. Coursera / Udemy</h4>
            <p>IT certifications के लिए। Python, Java, Web Development courses लें।</p>

            <h4>5. Stack Overflow</h4>
            <p>Programming doubts solve करने के लिए।</p>

            <h3>Daily Routine बनाएँ (Create Daily Routine)</h3>
            <ul>
                <li>1 hour coding practice</li>
                <li>LinkedIn पर 10 posts पढ़ें</li>
                <li>1 new technology learn करें</li>
                <li>GitHub पर code upload करें</li>
            </ul>

            <h3>Common Mistakes BCA Students Do</h3>
            <ul>
                <li>Only theory पढ़ना, practical कम करना</li>
                <li>Resume में projects न डालना</li>
                <li>Soft skills ignore करना</li>
                <li>Internships न करना</li>
            </ul>

            <h3>Best Career Tips</h3>
            <ul>
                <li>6th semester में internship जरूर करें</li>
                <li>Multiple programming languages learn करें</li>
                <li>Real projects बनाएँ</li>
                <li>Networking करें - tech events attend करें</li>
                <li>English communication improve करें</li>
            </ul>

            <div class="alert alert-success">
                <strong>Pro Tip:</strong> BCA के बाद MCA या IT jobs - दोनों options open हैं!
            </div>
            '''
        },
        'bsc': {
            'title': 'BSc Students - Science Career Guidance',
            'content': '''
            <h3>BSc क्या है? (What is BSc?)</h3>
            <p>BSc (Bachelor of Science) science subjects में specialization देता है - Physics, Chemistry, Mathematics, Biology, etc.</p>

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
                <li>Summer internships करें</li>
                <li>Scientific journals पढ़ें</li>
                <li>Projects और research work करें</li>
                <li>English और communication skills develop करें</li>
                <li>Online certifications लें</li>
            </ul>

            <div class="alert alert-info">
                <strong>Remember:</strong> BSc flexible degree है - many career paths open!
            </div>
            '''
        },
        'pharmacy': {
            'title': 'Pharmacy Students - Pharmaceutical Career Guidance',
            'content': '''
            <h3>Pharmacy Course क्या है? (What is Pharmacy?)</h3>
            <p>Pharmacy medicines, drugs, और healthcare से related field है। B.Pharm या D.Pharm से career options बहुत हैं।</p>

            <h3>Essential Platforms for Pharmacy Students</h3>

            <h4>1. LinkedIn</h4>
            <p>Pharma companies, hospitals, medical representatives के साथ connect करें।</p>

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
                <li>Drug information study करें</li>
                <li>Medical news पढ़ें</li>
                <li>Case studies analyze करें</li>
                <li>Soft skills develop करें</li>
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
                <li>Only theory focus करना</li>
                <li>Communication skills ignore करना</li>
                <li>No industry exposure</li>
                <li>Licensing exams ignore करना</li>
            </ul>

            <h3>Best Practices</h3>
            <ul>
                <li>Hospital pharmacy internships करें</li>
                <li>Drug information centers में volunteer करें</li>
                <li>Pharma conferences attend करें</li>
                <li>English communication improve करें</li>
                <li>Computer skills learn करें</li>
            </ul>

            <div class="alert alert-warning">
                <strong>Important:</strong> Pharmacy Council registration जरूरी है!
            </div>
            '''
        },
        'medical': {
            'title': 'Medical Students - MBBS & Allied Health Guidance',
            'content': '''
            <h3>Medical Education क्या है? (What is Medical Education?)</h3>
            <p>MBBS doctors बनने का course है। Allied health (Nursing, Physiotherapy, etc.) भी medical field का important part है।</p>

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
                <li>Medical journals पढ़ें</li>
                <li>Case discussions करें</li>
                <li>Clinical skills practice करें</li>
                <li>Research papers study करें</li>
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
                <li>Regular hospital postings attend करें</li>
                <li>Medical conferences participate करें</li>
                <li>Research projects करें</li>
                <li>Professional networking करें</li>
                <li>Continuous learning maintain करें</li>
            </ul>

            <div class="alert alert-success">
                <strong>Remember:</strong> Medicine में lifelong learning जरूरी है!
            </div>
            '''
        },
        'agriculture': {
            'title': 'Agriculture Students - Agri-Tech Career Guidance',
            'content': '''
            <h3>Agriculture Course क्या है? (What is Agriculture?)</h3>
            <p>Agriculture farming, crop science, और modern agri-tech से related field है। B.Sc Agriculture से traditional और modern career options मिलते हैं।</p>

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
                <li>Farm internships करें</li>
                <li>Krishi Vigyan Kendras visit करें</li>
                <li>Agriculture exhibitions attend करें</li>
                <li>Modern farming techniques learn करें</li>
                <li>English communication develop करें</li>
            </ul>

            <div class="alert alert-info">
                <strong>Future Scope:</strong> Agri-tech में huge opportunities हैं!
            </div>
            '''
        },
        'mpsc': {
            'title': 'MPSC Aspirants - Maharashtra PSC Exam Guidance',
            'content': '''
            <h3>MPSC क्या है? (What is MPSC?)</h3>
            <p>MPSC (Maharashtra Public Service Commission) Maharashtra government में administrative posts के लिए competitive exam है।</p>

            <h3>Essential Platforms for MPSC Preparation</h3>

            <h4>1. Official MPSC Website</h4>
            <p>mpsc.gov.in - सभी notifications, syllabus, और exam dates यहाँ मिलेंगे।</p>

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
                <li>Consistent study schedule बनाएँ</li>
                <li>Previous year papers solve करें</li>
                <li>Join test series</li>
                <li>Stay updated with Maharashtra news</li>
                <li>Answer writing practice करें</li>
            </ul>

            <div class="alert alert-warning">
                <strong>Important:</strong> MPSC में Marathi language जरूरी है!
            </div>
            '''
        },
        'upsc': {
            'title': 'UPSC Aspirants - Civil Services Exam Guidance',
            'content': '''
            <h3>UPSC क्या है? (What is UPSC?)</h3>
            <p>UPSC (Union Public Service Commission) India के top administrative services (IAS, IPS, IFS, etc.) के लिए entrance exam है।</p>

            <h3>Essential Platforms for UPSC Preparation</h3>

            <h4>1. Official UPSC Website</h4>
            <p>upsc.gov.in - सभी notifications, syllabus, और exam details यहाँ मिलेंगे।</p>

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
                <li>Health neglect करना</li>
            </ul>

            <h3>Best Preparation Tips</h3>
            <ul>
                <li>NCERT books से foundation strong करें</li>
                <li>Consistent study schedule follow करें</li>
                <li>Daily answer writing practice करें</li>
                <li>Multiple mock tests दें</li>
                <li>Stay updated with current affairs</li>
                <li>Physical and mental health maintain करें</li>
            </ul>

            <div class="alert alert-success">
                <strong>Motivation:</strong> UPSC clear करने के लिए consistency और smart work जरूरी है!
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
def chatbot_message():
    try:
        data = request.json
        user_message = data.get('message', '').strip().lower()
        
        # Get chatbot response
        response = get_chatbot_response(user_message)
        
        return {'response': response, 'success': True}
    except Exception as e:
        print(f"Chatbot error: {e}")
        return {'response': 'Sorry, I encountered an error. Please try again!', 'success': False}, 500

def get_chatbot_response(message):
    """Simple rule-based chatbot for Marg Darshak guidance"""
    
    # Greeting responses
    greetings = ['hello', 'hi', 'hey', 'namaste', 'good morning', 'good evening']
    if any(greet in message for greet in greetings):
        return "नमस्ते! मैं आपका मार्गदर्शक हूं। मैं आपकी career, education, mental health, wisdom, skills, AI tools, mentoring, productivity, और overall development में मदद कर सकता हूं। आप क्या जानना चाहेंगे? (Hello! I'm your Marg Darshak guide. I can help you with career, education, mental health, wisdom, skills, AI tools, mentoring, productivity, and overall development. What would you like to know?)"
    
    # Career related queries
    if any(word in message for word in ['career', 'job', 'profession', 'कैरियर', 'नौकरी']):
        if 'quiz' in message or 'test' in message:
            return """<strong>Career Quiz देने के लिए:</strong><br>
1. <a href="/career/quiz" target="_blank" class="btn btn-primary btn-sm">Career Quiz</a> पर जाएं<br>
2. Questions answer करें<br>
3. Results देखें और career suggestions पाएं<br><br>
यह quiz आपकी interests के आधार पर suitable careers suggest करेगा!"""
        
        elif 'browse' in message or 'careers' in message:
            return """<strong>सभी careers browse करने के लिए:</strong><br>
<a href="/career/browse" target="_blank" class="btn btn-success btn-sm">Browse Careers</a> पर जाएं<br>
• Category select करें (Technology, Business, Creative, etc.)<br>
• Difficulty level choose करें<br>
• Interesting careers पर click करें और details पढ़ें<br><br>
हर career की salary, skills, और growth information मिलेगी!"""
        
        else:
            return """<strong>Career guidance के लिए आप ये कर सकते हैं:</strong><br>
• <a href="/career/quiz" target="_blank">Career Interest Quiz</a> दें<br>
• <a href="/career/browse" target="_blank">सभी careers browse</a> करें<br>
• Specific career details देखें<br>
• Resume और portfolio बनाएं<br><br>
मैं आपकी help कर सकता हूं - बताएं आप किस field में interested हैं?"""
    
    # Education/Platforms queries
    if any(word in message for word in ['learn', 'education', 'platform', 'tool', 'study', 'सीखना', 'प्लेटफॉर्म']):
        if 'github' in message:
            return """<strong>GitHub use करने के लिए step-by-step guide:</strong><br>
1. <a href="https://github.com" target="_blank">github.com</a> पर जाएं और account बनाएं<br>
2. Profile complete करें (bio, photo add करें)<br>
3. First repository बनाएं ("New repository" click करें)<br>
4. Code files upload करें या create करें<br>
5. README.md file add करें project description के साथ<br><br>
Practice projects upload करके अपना portfolio strong बनाएं!"""
        
        elif 'linkedin' in message:
            return """<strong>LinkedIn profile बनाने के लिए:</strong><br>
1. <a href="https://linkedin.com" target="_blank">linkedin.com</a> पर sign up करें<br>
2. Professional photo और headline add करें<br>
3. Education और experience भरें<br>
4. Skills section में अपनी skills add करें<br>
5. Connections send करें (colleagues, seniors)<br><br>
Daily 10-15 minutes में posts पढ़ें और networking करें!"""
        
        elif 'leetcode' in message or 'coding' in message:
            return """<strong>Coding practice के लिए LeetCode:</strong><br>
1. <a href="https://leetcode.com" target="_blank">leetcode.com</a> पर account बनाएं<br>
2. Easy problems से start करें<br>
3. हर problem को understand करें और solve करें<br>
4. Solutions analyze करें<br>
5. Daily 1-2 problems practice करें<br><br>
Consistent practice से interview ready बनेंगे!"""
        
        else:
            return """<strong>Learning के लिए हमारे पास हैं:</strong><br>
• <a href="/ai/tools" target="_blank">AI Tools</a> - ChatGPT, Coursera, YouTube, etc.<br>
• Learning Guides - Platform-wise tutorials<br>
• <a href="/skill/browse" target="_blank">Skill Saathi</a> - Curated learning resources<br><br>
आप कौन सा subject या skill learn करना चाहते हैं? मैं guide कर सकता हूं!"""
    
    # Mental health queries
    if any(word in message for word in ['mental', 'health', 'stress', 'mood', 'मन', 'तनाव', 'मनोदशा']):
        if 'breathing' in message or 'सांस' in message:
            return """<strong>Guided breathing exercise के लिए:</strong><br>
<a href="/mental/breathing" target="_blank" class="btn btn-info btn-sm">Breathing Exercise</a> पर जाएं<br>
• Instructions follow करें<br>
• Deep breaths लें और relax करें<br><br>
Daily 5-10 minutes का practice mental health को strong बनाता है!"""
        
        elif 'mood' in message or 'track' in message:
            return """<strong>Mood tracking करने के लिए:</strong><br>
<a href="/mental/mood" target="_blank" class="btn btn-warning btn-sm">Mood Assessment</a> पर जाएं<br>
• Date select करें<br>
• Questions answer करें (energy, stress, optimism)<br>
• Notes add करें<br>
• Submit करें<br><br>
आपका mood history track हो जाएगा और patterns देख सकते हैं!"""
        
        else:
            return """<strong>Mental wellness के लिए:</strong><br>
• <a href="/mental/mood" target="_blank">Daily mood tracking</a> करें<br>
• <a href="/mental/breathing" target="_blank">Guided breathing exercises</a> करें<br>
• Stress management tips follow करें<br>
• Regular breaks लें और exercise करें<br><br>
आपको क्या help चाहिए - breathing, mood tracking, या general tips?"""
    
    # Wisdom/Spiritual queries
    if any(word in message for word in ['wisdom', 'gyan', 'spiritual', 'shloka', 'गीता', 'ज्ञान']):
        if 'daily' in message:
            return """<strong>Daily wisdom पाने के लिए:</strong><br>
<a href="/gyan/daily" target="_blank" class="btn btn-secondary btn-sm">Daily Wisdom</a> पर जाएं<br>
• Bhagavad Gita का random shloka मिलेगा<br>
• Hindi/English meaning पढ़ें<br>
• Practical application समझें<br><br>
Daily spiritual wisdom से motivation मिलती है!"""
        
        elif 'search' in message:
            return """<strong>Shloka search करने के लिए:</strong><br>
<a href="/gyan/search" target="_blank" class="btn btn-dark btn-sm">Search Shlokas</a> पर जाएं<br>
• Keyword enter करें (peace, karma, dharma, etc.)<br>
• Results देखें<br>
• Detailed view में click करें<br><br>
Spiritual guidance के लिए perfect tool है!"""
        
        else:
            return """<strong>Spiritual guidance के लिए:</strong><br>
• <a href="/gyan/daily" target="_blank">Daily Bhagavad Gita shlokas</a> पढ़ें<br>
• <a href="/gyan/search" target="_blank">Search करें</a> specific topics पर<br>
• Practical applications समझें<br>
• Daily practice में implement करें<br><br>
आप किस topic पर guidance चाहते हैं?"""
    
    # Skills/Resources queries
    if any(word in message for word in ['skill', 'resource', 'course', 'learning', 'स्किल', 'रिसोर्स']):
        return """<strong>Learning resources के लिए:</strong><br>
<a href="/skill/browse" target="_blank" class="btn btn-warning btn-sm">Skill Saathi</a> पर जाएं<br>
• Topic select करें (Programming, Design, Business, etc.)<br>
• Difficulty level choose करें<br>
• Free resources filter करें<br>
• Best courses और tutorials मिलेंगे<br><br>
सभी resources quality score के साथ ranked हैं!"""
    
    # AI Tools queries
    if any(word in message for word in ['ai', 'tool', 'chatgpt', 'artificial', 'एआई', 'टूल']):
        return """<strong>AI tools के recommendations के लिए:</strong><br>
<a href="/ai/tools" target="_blank" class="btn btn-secondary btn-sm">AI Tools</a> पर जाएं<br>
• Category select करें (Writing, Coding, Design, etc.)<br>
• Free/Paid filter apply करें<br>
• Tool details और tutorials देखें<br>
• Best tools try करें<br><br>
ChatGPT, GitHub Copilot, Canva, etc. जैसे tools मिलेंगे!"""
    
    # Mentor queries
    if any(word in message for word in ['mentor', 'guidance', 'teacher', 'expert', 'मेंटर']):
        if 'connect' in message or 'chat' in message:
            return """<strong>Mentor से connect करने के लिए:</strong><br>
<a href="/mentor/connect" target="_blank" class="btn btn-danger btn-sm">Mentor Connect</a> पर जाएं<br>
• Available mentors browse करें<br>
• Profile देखें और message send करें<br>
• Chat शुरू करें<br>
• <a href="/mentor/payment" target="_blank">Payment</a> और <a href="/mentor/upgrade" target="_blank">upgrade</a> options check करें<br><br>
Personalized guidance मिलेगी!"""
        
        else:
            return """<strong>Mentor guidance के लिए:</strong><br>
• <a href="/mentor/connect" target="_blank">Available experts से chat</a> करें<br>
• Career advice लें<br>
• Resume review करवाएं<br>
• Interview preparation करें<br><br>
आप किस field में mentor चाहते हैं?"""
    
    # Todo/Productivity queries
    if any(word in message for word in ['todo', 'task', 'productivity', 'list', 'टूडू', 'टास्क']):
        return """<strong>Todo list manage करने के लिए:</strong><br>
<a href="/todo" target="_blank" class="btn btn-light text-dark btn-sm">Todo List</a> पर जाएं<br>
• New task add करें<br>
• Priority set करें (High, Medium, Low)<br>
• Deadline set करें<br>
• Tasks complete mark करें<br><br>
आपकी productivity track हो जाएगी!"""
    
    # Games/Mind fresh queries
    if any(word in message for word in ['game', 'fun', 'joke', 'relax', 'मनोरंजन']):
        return """<strong>Mind refresh करने के लिए:</strong><br>
<a href="/mindfresh" target="_blank" class="btn btn-success btn-sm">Mind Fresh</a> पर जाएं<br>
• Fun games play करें (Riddles, Jokes, Puzzles)<br>
• Daily challenges complete करें<br>
• Scores track करें<br><br>
Short breaks में creativity और energy boost मिलता है!"""
    
    # Progress/Dashboard queries
    if any(word in message for word in ['progress', 'dashboard', 'activity', 'प्रगति']):
        return """<strong>आपकी progress देखने के लिए:</strong><br>
<a href="/progress" target="_blank" class="btn btn-info btn-sm">Progress Dashboard</a> पर जाएं<br>
• Total activities देखें<br>
• Module-wise stats check करें<br>
• Recent activities देखें<br>
• Badges और streaks celebrate करें<br><br>
आपका learning journey track होता है!"""
    
    # Student Essentials queries
    if any(word in message for word in ['essential', 'student', 'study', 'notes', 'एसेंशियल', 'स्टूडेंट']):
        return """<strong>Student essentials के लिए:</strong><br>
<a href="/essentials" target="_blank" class="btn btn-primary btn-sm">Student Essentials</a> पर जाएं<br>
• Study materials download करें<br>
• Important notes और guides access करें<br>
• Exam preparation resources use करें<br>
• Academic tools explore करें<br><br>
सभी essential resources एक जगह मिलेंगे!"""
    
    # Download/App queries
    if any(word in message for word in ['download', 'app', 'apk', 'mobile', 'डाउनलोड', 'ऐप']):
        return """<strong>Marg Darshak App download करने के लिए:</strong><br>
<strong>Available on:</strong><br>
• <a href="https://play.google.com/store/search?q=margdarshak" target="_blank" class="btn btn-danger btn-sm"><i class="fab fa-google-play"></i> Google Play Store</a><br>
• <a href="https://apkpure.com/search?q=margdarshak" target="_blank" class="btn btn-primary btn-sm"><i class="fas fa-store"></i> APKPure</a><br>
• <a href="https://en.uptodown.com/android/search/margdarshak" target="_blank" class="btn btn-success btn-sm"><i class="fas fa-mobile-alt"></i> Uptodown</a><br>
• <a href="/static/MargDarshak-App.apk" download class="btn btn-warning btn-sm"><i class="fas fa-file-download"></i> Direct APK</a><br><br>
<strong>Features:</strong> Offline access, push notifications, enhanced mobile experience!<br>
<strong>Trusted app</strong> - Also coming soon on APKPure & Uptodown and Play Store."""
    
    # Roadmap/Career path queries
    if any(word in message for word in ['roadmap', 'path', 'career path', 'रोडमैप', 'पथ']):
        return """<strong>Career roadmap बनाने के लिए:</strong><br>
<a href="/career/browse" target="_blank" class="btn btn-info btn-sm">Career Browse</a> पर जाएं और अपनी interested career select करें<br><br>
<strong>General roadmap steps:</strong><br>
1. <strong>Self-assessment:</strong> Skills और interests identify करें<br>
2. <strong>Education:</strong> Required qualifications complete करें<br>
3. <strong>Skills development:</strong> <a href="/skill/browse" target="_blank">Skill Saathi</a> से learn करें<br>
4. <strong>Experience:</strong> Internships/projects करें<br>
5. <strong>Networking:</strong> <a href="/mentor/connect" target="_blank">Mentors</a> से connect करें<br>
6. <strong>Continuous learning:</strong> <a href="/ai/tools" target="_blank">AI tools</a> use करें<br><br>
मैं आपकी specific career के लिए detailed roadmap बना सकता हूं!"""
    
    # Resume/Portfolio queries
    if any(word in message for word in ['resume', 'cv', 'portfolio', 'रिज्यूम', 'पोर्टफोलियो']):
        return """<strong>Resume और portfolio बनाने के लिए tips:</strong><br>
1. <strong>Format:</strong> Clean, professional layout use करें<br>
2. <strong>Content:</strong> Achievements quantify करें<br>
3. <strong>Skills:</strong> Relevant skills highlight करें<br>
4. <strong>Projects:</strong> <a href="https://github.com" target="_blank">GitHub</a> links add करें<br>
5. <strong>LinkedIn:</strong> <a href="https://linkedin.com" target="_blank">Profile</a> optimize करें<br><br>
<strong>Tools:</strong> Canva, Google Docs, or professional templates use करें<br>
<a href="/mentor/connect" target="_blank">Mentors से resume review</a> करवा सकते हैं!"""
    
    # Help/General queries
    if any(word in message for word in ['help', 'how', 'what', 'मदद', 'कैसे']):
        return """मैं आपकी ये मदद कर सकता हूं:
• Career guidance, quiz, और roadmap
• Platform tutorials (GitHub, LinkedIn, LeetCode)
• Mental health tips और mood tracking
• Daily wisdom shlokas और spiritual guidance
• Learning resources और skill development
• AI tools recommendations
• Mentor connections और personalized guidance
• Student essentials और study materials
• Student essentials और study materials
• Fun games और mind refresh activities
• Progress tracking और dashboard analytics
• App download और mobile features
• Career roadmaps और resume building tips
• Step-by-step instructions for all features

आप क्या जानना चाहते हैं? बताएं! 😊"""
    
    # Default response
    if not any(keyword in message.lower() for keyword in [
        'career', 'job', 'profession', 'कैरियर', 'नौकरी', 'quiz', 'test', 'browse', 'careers',
        'learn', 'education', 'platform', 'tool', 'study', 'सीखना', 'प्लेटफॉर्म', 'github', 'linkedin', 'leetcode', 'coding',
        'mental', 'health', 'stress', 'mood', 'मन', 'तनाव', 'मनोदशा', 'breathing', 'सांस', 'track',
        'wisdom', 'gyan', 'spiritual', 'shloka', 'गीता', 'ज्ञान', 'daily', 'search',
        'skill', 'resource', 'course', 'learning', 'स्किल', 'रिसोर्स',
        'ai', 'chatgpt', 'artificial', 'एआई', 'टूल',
        'mentor', 'guidance', 'teacher', 'expert', 'मेंटर', 'connect', 'chat',
        'todo', 'task', 'productivity', 'list', 'टूडू', 'टास्क',
        'game', 'fun', 'joke', 'relax', 'मनोरंजन',
        'progress', 'dashboard', 'activity', 'प्रगति',
        'essential', 'student', 'notes', 'एसेंशियल', 'स्टूडेंट',
        'download', 'app', 'apk', 'mobile', 'डाउनलोड', 'ऐप',
        'roadmap', 'path', 'रोडमैप', 'पथ',
        'resume', 'cv', 'portfolio', 'रिज्यूम', 'पोर्टफोलियो',
        'help', 'how', 'what', 'मदद', 'कैसे'
    ]):
        # Fallback to helpful response for general questions
        return """<strong>मैं आपका मार्गदर्शक हूं!</strong> मैं career, education, mental health, wisdom, skills, AI tools, mentoring, productivity, और overall development में help कर सकता हूं। 

<strong>कुछ specific पूछें जैसे:</strong><br>
• <a href="/career/quiz" target="_blank">Career quiz कैसे दें?</a><br>
• "GitHub कैसे use करें?"<br>
• <a href="/mental/mood" target="_blank">Mental health tips</a><br>
• <a href="/ai/tools" target="_blank">AI tools recommendations</a><br>
• <a href="/mentor/connect" target="_blank">Mentor कैसे connect करें?</a><br>
• <a href="/gyan/daily" target="_blank">Daily wisdom कैसे पाएं?</a><br>
• <a href="/todo" target="_blank">Todo list कैसे manage करें?</a><br><br>
या कोई भी question पूछ सकते हैं - मैं step-by-step guide दूंगा! 🤝"""
    # Fallback default response for unmatched specific queries
    return """<strong>मैं आपका मार्गदर्शक हूं!</strong> मैं career, education, mental health, wisdom, skills, AI tools, mentoring, productivity, और overall development में help कर सकता हूं। 

<strong>कुछ specific पूछें जैसे:</strong><br>
• <a href="/career/quiz" target="_blank">"Career quiz कैसे दें?"</a><br>
• "GitHub कैसे use करें?"<br>
• <a href="/mental/mood" target="_blank">"Mental health tips"</a><br>
• <a href="/ai/tools" target="_blank">"AI tools recommendations"</a><br>
• <a href="/mentor/connect" target="_blank">"Mentor कैसे connect करें?"</a><br>
• <a href="/gyan/daily" target="_blank">"Daily wisdom कैसे पाएं?"</a><br>
• <a href="/todo" target="_blank">"Todo list कैसे manage करें?"</a><br><br>
या कोई भी question पूछ सकते हैं - मैं step-by-step guide दूंगा! 🤝"""

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
            
            flash('Task added successfully! 🎉', 'success')
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
            flash('Task updated successfully! ✏️', 'success')
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
        
        flash('Task deleted successfully! 🗑️', 'success')
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
                flash('Great job! Task completed! 🎉', 'success')
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