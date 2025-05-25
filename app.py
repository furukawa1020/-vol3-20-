from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, session, Response
import sqlite3
from datetime import datetime, timedelta
import os
import json
from collections import defaultdict
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps

# matplotlib設定（Render対応）
import matplotlib
matplotlib.use('Agg')  # GUIバックエンドを無効化
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm
import io
import base64

# シンプルなフォント設定
def setup_japanese_font():
    """日本語フォントを設定（Render対応）"""
    try:
        # Renderなどのクラウド環境では基本的にDejaVu Sansを使用
        plt.rcParams['font.family'] = ['DejaVu Sans']
        plt.rcParams['axes.unicode_minus'] = False
        print("Font configured: DejaVu Sans")
        return True
        
    except Exception as e:
        print(f"Font setup error: {e}")
        plt.rcParams['font.family'] = ['DejaVu Sans']
        return False

# フォント設定を実行
font_configured = setup_japanese_font()

app = Flask(__name__)

# 本番環境向けのシークレットキー設定
app.secret_key = os.environ.get('SECRET_KEY', 'your-secret-key-here-change-in-production')

# セッション設定
app.config['SESSION_COOKIE_SECURE'] = os.environ.get('FLASK_ENV') == 'production'
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'

# Database setup
DB_PATH = os.environ.get('DATABASE_URL', 'tasks.db')

# デフォルトカテゴリカラー
DEFAULT_COLORS = [
    "#F82A1B", "#FF9800", "#FFDD02", "#53EB38", "#03A9F4",
    "#2635FF", "#902DEE", "#FF80CC", "#795548", "#7DA0B2"
]

def get_db_connection():
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        return conn
    except Exception as e:
        print(f"Database connection error: {e}")
        raise

def get_current_user_id():
    return session.get('user_id') if 'guest_mode' not in session else None

def init_db():
    try:
        print("Initializing database...")
        
        # データベースディレクトリの作成
        db_dir = os.path.dirname(DB_PATH)
        if db_dir and not os.path.exists(db_dir):
            os.makedirs(db_dir, exist_ok=True)
            print(f"Created database directory: {db_dir}")
            
        conn = get_db_connection()
        
        # ユーザーテーブル
        conn.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            email TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
        ''')
        
        # カテゴリテーブル
        conn.execute('''
        CREATE TABLE IF NOT EXISTS categories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            color TEXT NOT NULL DEFAULT '#007bff',
            user_id INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users (id)
        )
        ''')
        
        # タスクテーブル（estimated_hoursカラムを追加）
        conn.execute('''
        CREATE TABLE IF NOT EXISTS tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            description TEXT,
            due_date TEXT,
            due_time TEXT,
            category TEXT,
            category_id INTEGER,
            priority TEXT,
            estimated_hours REAL DEFAULT 2.0,
            completed INTEGER DEFAULT 0,
            user_id INTEGER,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users (id),
            FOREIGN KEY (category_id) REFERENCES categories (id)
        )
        ''')
        
        # 実働時間セッションテーブル（新規追加）
        conn.execute('''
        CREATE TABLE IF NOT EXISTS work_sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task_id INTEGER NOT NULL,
            user_id INTEGER,
            start_time TEXT NOT NULL,
            end_time TEXT,
            focus_seconds INTEGER DEFAULT 0,
            break_seconds INTEGER DEFAULT 0,
            is_active INTEGER DEFAULT 1,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (task_id) REFERENCES tasks (id),
            FOREIGN KEY (user_id) REFERENCES users (id)
        )
        ''')
        
        # 中断記録テーブル（新規追加）
        conn.execute('''
        CREATE TABLE IF NOT EXISTS interruptions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id INTEGER NOT NULL,
            start_time TEXT NOT NULL,
            end_time TEXT,
            reason TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (session_id) REFERENCES work_sessions (id)
        )
        ''')
        
        # 既存のテーブルに新しいカラムを追加
        try:
            conn.execute('ALTER TABLE tasks ADD COLUMN due_time TEXT')
        except sqlite3.OperationalError:
            pass
        
        try:
            conn.execute('ALTER TABLE tasks ADD COLUMN category_id INTEGER')
        except sqlite3.OperationalError:
            pass
            
        try:
            conn.execute('ALTER TABLE tasks ADD COLUMN estimated_hours REAL DEFAULT 2.0')
        except sqlite3.OperationalError:
            pass
        
        # デフォルトカテゴリの作成
        try:
            existing_global_categories = conn.execute('SELECT COUNT(*) FROM categories WHERE user_id IS NULL').fetchone()[0]
            if existing_global_categories == 0:
                default_categories = [
                    ('仕事', DEFAULT_COLORS[0], None),
                    ('個人', DEFAULT_COLORS[1], None),
                    ('勉強', DEFAULT_COLORS[2], None)
                ]
                conn.executemany('INSERT INTO categories (name, color, user_id) VALUES (?, ?, ?)', default_categories)
                print("Created default categories")
        except Exception as e:
            print(f"Warning: Could not create default categories: {e}")
        
        conn.commit()
        conn.close()
        print("Database initialized successfully")
        
    except Exception as e:
        print(f"Database initialization error: {e}")
        import traceback
        traceback.print_exc()
        raise

# 初期化フラグ
_initialized = False

def ensure_initialization():
    global _initialized
    if not _initialized:
        try:
            init_db()
            _initialized = True
            print("App initialization completed")
        except Exception as e:
            print(f"Initialization failed: {e}")
            import traceback
            traceback.print_exc()
            raise

@app.before_request
def before_request():
    try:
        ensure_initialization()
    except Exception as e:
        print(f"Before request error: {e}")
        import traceback
        traceback.print_exc()
        return f"Initialization Error: {str(e)}", 500

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session and 'guest_mode' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

@app.route('/')
def landing():
    try:
        return render_template('landing.html')
    except Exception as e:
        print(f"Landing page error: {e}")
        return f"Landing page error: {str(e)}", 500

@app.route('/login', methods=['GET', 'POST'])
def login():
    try:
        if request.method == 'POST':
            username = request.form['username']
            password = request.form['password']
            
            conn = get_db_connection()
            user = conn.execute('SELECT * FROM users WHERE username = ?', (username,)).fetchone()
            conn.close()
            
            if user and check_password_hash(user['password_hash'], password):
                session['user_id'] = user['id']
                session['username'] = user['username']
                session.pop('guest_mode', None)
                flash('ログインしました！', 'success')
                return redirect(url_for('index'))
            else:
                flash('ユーザー名またはパスワードが正しくありません。', 'error')
        
        return render_template('login.html')
    except Exception as e:
        print(f"Login error: {e}")
        return f"Login error: {str(e)}", 500

@app.route('/register', methods=['GET', 'POST'])
def register():
    try:
        if request.method == 'POST':
            username = request.form['username']
            email = request.form['email']
            password = request.form['password']
            confirm_password = request.form['confirm_password']
            
            if password != confirm_password:
                flash('パスワードが一致しません。', 'error')
                return render_template('register.html')
            
            if len(password) < 6:
                flash('パスワードは6文字以上で入力してください。', 'error')
                return render_template('register.html')
            
            password_hash = generate_password_hash(password)
            
            conn = get_db_connection()
            try:
                conn.execute('INSERT INTO users (username, email, password_hash) VALUES (?, ?, ?)', (username, email, password_hash))
                conn.commit()
                conn.close()
                flash('アカウントが作成されました！ログインしてください。', 'success')
                return redirect(url_for('login'))
            except sqlite3.IntegrityError:
                conn.close()
                flash('このユーザー名またはメールアドレスは既に使用されています。', 'error')
        
        return render_template('register.html')
    except Exception as e:
        print(f"Register error: {e}")
        return f"Register error: {str(e)}", 500

@app.route('/guest')
def guest_mode():
    try:
        session.clear()
        session['guest_mode'] = True
        flash('ゲストモードで開始しました。データは保存されません。', 'info')
        return redirect(url_for('index'))
    except Exception as e:
        print(f"Guest mode error: {e}")
        return f"Guest mode error: {str(e)}", 500

@app.route('/logout')
def logout():
    try:
        session.clear()
        flash('ログアウトしました。', 'info')
        return redirect(url_for('landing'))
    except Exception as e:
        print(f"Logout error: {e}")
        return f"Logout error: {str(e)}", 500

@app.route('/dashboard')
@app.route('/index')
@login_required
def index():
    try:
        print(f"Index route called, session: {dict(session)}")
        
        user_id = get_current_user_id()
        print(f"User ID: {user_id}")
        
        if user_id:
            conn = get_db_connection()
            tasks = conn.execute('''
                SELECT t.*, c.color as category_color 
                FROM tasks t 
                LEFT JOIN categories c ON t.category_id = c.id 
                WHERE t.user_id = ? 
                ORDER BY t.completed, t.due_date ASC
            ''', (user_id,)).fetchall()
            conn.close()
            print(f"Retrieved {len(tasks)} tasks from database")
            
            # Row オブジェクトを辞書に変換
            tasks = [dict(task) for task in tasks]
        else:
            tasks = session.get('guest_tasks', [])
            print(f"Guest mode: {len(tasks)} tasks in session")
            
            if tasks:
                try:
                    conn = get_db_connection()
                    db_categories = conn.execute('SELECT * FROM categories WHERE user_id IS NULL').fetchall()
                    conn.close()
                    
                    all_categories = {}
                    for cat in db_categories:
                        all_categories[cat['id']] = cat['color']
                    
                    for cat in session.get('guest_categories', []):
                        all_categories[cat['id']] = cat['color']
                    
                    for task in tasks:
                        task['category_color'] = all_categories.get(task.get('category_id'), '#6c757d')
                except Exception as e:
                    print(f"Error processing guest tasks: {e}")
                    for task in tasks:
                        task['category_color'] = '#6c757d'
        
        is_guest = 'guest_mode' in session
        print(f"Rendering index with {len(tasks)} tasks, guest mode: {is_guest}")
        
        return render_template('index.html', tasks=tasks, is_guest=is_guest)
        
    except Exception as e:
        print(f"Index route error: {e}")
        import traceback
        traceback.print_exc()
        return f"Index page error: {str(e)}", 500

# チャート生成機能を復活
@app.route('/chart/<chart_type>')
@login_required
def generate_chart(chart_type):
    try:
        print(f"Generating chart: {chart_type}")
        user_id = get_current_user_id()
        
        if chart_type == 'category_pie':
            data = get_category_data(user_id)
            if not data:
                return create_no_data_response("No category data available")
            image_data = create_pie_chart(data, "Task Distribution by Category")
            
        elif chart_type == 'priority_bar':
            data = get_priority_data(user_id)
            if not data:
                return create_no_data_response("No priority data available")
            image_data = create_bar_chart(data, "Task Distribution by Priority")
            
        elif chart_type == 'completion_status':
            data = get_completion_data(user_id)
            if not data:
                return create_no_data_response("No completion data available")
            image_data = create_pie_chart(data, "Task Completion Status")
            
        elif chart_type == 'category_stacked':
            data = get_category_detailed_data(user_id)
            if not data:
                return create_no_data_response("No detailed category data available")
            image_data = create_stacked_bar_chart(data, "Detailed Category Statistics")
            
        else:
            return create_no_data_response("Invalid chart type")
        
        if not image_data:
            return create_no_data_response("Chart generation failed")
            
        return Response(image_data, mimetype='image/png')
        
    except Exception as e:
        print(f"Chart generation error: {e}")
        import traceback
        traceback.print_exc()
        return create_no_data_response(f"Chart error: {str(e)}")

def get_category_data(user_id):
    """カテゴリ別データを取得"""
    try:
        if user_id:
            conn = get_db_connection()
            data = conn.execute('''
                SELECT c.name, c.color, COUNT(t.id) as count 
                FROM categories c 
                LEFT JOIN tasks t ON c.id = t.category_id AND t.user_id = ? 
                WHERE c.user_id IS NULL OR c.user_id = ? 
                GROUP BY c.id, c.name, c.color 
                HAVING COUNT(t.id) > 0
                ORDER BY COUNT(t.id) DESC
            ''', (user_id, user_id)).fetchall()
            conn.close()
            
            return [{'name': row['name'], 'count': row['count'], 'color': row['color']} for row in data]
        else:
            # ゲストモード
            guest_tasks = session.get('guest_tasks', [])
            if not guest_tasks:
                return []
            
            category_counts = {}
            for task in guest_tasks:
                category = task.get('category', 'Uncategorized')
                category_counts[category] = category_counts.get(category, 0) + 1
            
            return [{'name': cat, 'count': count, 'color': '#6c757d'} 
                   for cat, count in category_counts.items()]
        
    except Exception as e:
        print(f"Error getting category data: {e}")
        return []

def get_priority_data(user_id):
    """優先度別データを取得"""
    try:
        if user_id:
            conn = get_db_connection()
            data = conn.execute('''
                SELECT priority, COUNT(*) as count 
                FROM tasks WHERE user_id = ? 
                GROUP BY priority
                ORDER BY count DESC
            ''', (user_id,)).fetchall()
            conn.close()
            
            return [{'priority': row['priority'], 'count': row['count']} for row in data]
        else:
            # ゲストモード
            guest_tasks = session.get('guest_tasks', [])
            if not guest_tasks:
                return []
            
            priority_counts = {}
            for task in guest_tasks:
                priority = task.get('priority', 'medium')
                priority_counts[priority] = priority_counts.get(priority, 0) + 1
            
            return [{'priority': pri, 'count': count} 
                   for pri, count in priority_counts.items()]
        
    except Exception as e:
        print(f"Error getting priority data: {e}")
        return []

def get_completion_data(user_id):
    """完了状況データを取得"""
    try:
        if user_id:
            conn = get_db_connection()
            completed = conn.execute('SELECT COUNT(*) FROM tasks WHERE user_id = ? AND completed = 1', (user_id,)).fetchone()[0]
            incomplete = conn.execute('SELECT COUNT(*) FROM tasks WHERE user_id = ? AND completed = 0', (user_id,)).fetchone()[0]
            conn.close()
        else:
            # ゲストモード
            guest_tasks = session.get('guest_tasks', [])
            completed = sum(1 for task in guest_tasks if task.get('completed'))
            incomplete = len(guest_tasks) - completed
        
        if completed == 0 and incomplete == 0:
            return []
        
        return [
            {'name': 'Completed', 'count': completed, 'color': '#28a745'},
            {'name': 'Incomplete', 'count': incomplete, 'color': '#ffc107'}
        ]
        
    except Exception as e:
        print(f"Error getting completion data: {e}")
        return []

def get_category_detailed_data(user_id):
    """カテゴリ別詳細データを取得"""
    try:
        if user_id:
            conn = get_db_connection()
            data = conn.execute('''
                SELECT c.name, c.color,
                       SUM(CASE WHEN t.completed = 1 THEN 1 ELSE 0 END) as completed,
                       SUM(CASE WHEN t.completed = 0 THEN 1 ELSE 0 END) as incomplete
                FROM categories c
                LEFT JOIN tasks t ON c.id = t.category_id AND t.user_id = ?
                WHERE (c.user_id IS NULL OR c.user_id = ?)
                GROUP BY c.id, c.name, c.color
                HAVING (completed > 0 OR incomplete > 0)
                ORDER BY (completed + incomplete) DESC
            ''', (user_id, user_id)).fetchall()
            conn.close()
            
            return [{'name': row['name'], 'completed': row['completed'], 
                    'incomplete': row['incomplete'], 'color': row['color']} for row in data]
        else:
            guest_tasks = session.get('guest_tasks', [])
            if not guest_tasks:
                return []
            
            category_stats = {}
            for task in guest_tasks:
                category = task.get('category', 'Uncategorized')
                if category not in category_stats:
                    category_stats[category] = {'completed': 0, 'incomplete': 0, 'color': '#6c757d'}
                
                if task.get('completed'):
                    category_stats[category]['completed'] += 1
                else:
                    category_stats[category]['incomplete'] += 1
            
            return [{'name': k, 'completed': v['completed'], 'incomplete': v['incomplete'], 'color': v['color']} 
                   for k, v in category_stats.items()]
    except Exception as e:
        print(f"Error getting category detailed data: {e}")
        return []

def create_pie_chart(data, title):
    """円グラフを作成"""
    try:
        print(f"Creating pie chart with {len(data)} items")
        
        filtered_data = [item for item in data if item['count'] > 0]
        if not filtered_data:
            return create_no_data_image(title)
        
        labels = [item['name'] for item in filtered_data]
        sizes = [item['count'] for item in filtered_data]
        colors = [item.get('color', '#6c757d') for item in filtered_data]
        
        # 英語ラベルに変換（日本語フォント対応なしのため）
        english_labels = [f"Item {i+1}" for i in range(len(labels))]
        
        fig, ax = plt.subplots(figsize=(8, 6))
        
        wedges, texts, autotexts = ax.pie(sizes, labels=english_labels, colors=colors, 
                                        autopct='%1.1f%%', startangle=90, 
                                        textprops={'fontsize': 10})
        ax.set_title(title, fontsize=14, fontweight='bold', pad=20)
        
        for autotext in autotexts:
            autotext.set_color('white')
            autotext.set_fontweight('bold')
        
        plt.tight_layout()
        
        img = io.BytesIO()
        plt.savefig(img, format='png', bbox_inches='tight', facecolor='white', dpi=100)
        img.seek(0)
        image_data = img.getvalue()
        plt.close()
        
        print("Pie chart created successfully")
        return image_data
        
    except Exception as e:
        print(f"Pie chart generation error: {e}")
        import traceback
        traceback.print_exc()
        return create_simple_error_image()

def create_bar_chart(data, title):
    """棒グラフを作成"""
    try:
        print(f"Creating bar chart with {len(data)} items")
        
        if not data:
            return create_no_data_image(title)
        
        labels = [item['priority'] for item in data]
        values = [item['count'] for item in data]
        
        # 英語ラベルに変換
        english_labels = []
        colors = []
        for label in labels:
            if label == 'high':
                english_labels.append('High')
                colors.append('#dc3545')
            elif label == 'medium':
                english_labels.append('Medium')
                colors.append('#ffc107')
            elif label == 'low':
                english_labels.append('Low')
                colors.append('#17a2b8')
            else:
                english_labels.append(label)
                colors.append('#6c757d')
        
        fig, ax = plt.subplots(figsize=(8, 6))
        bars = ax.bar(english_labels, values, color=colors)
        
        ax.set_title(title, fontsize=14, fontweight='bold', pad=20)
        ax.set_xlabel('Priority', fontsize=12)
        ax.set_ylabel('Number of Tasks', fontsize=12)
        
        # バーの上に値を表示
        for bar in bars:
            height = bar.get_height()
            ax.text(bar.get_x() + bar.get_width()/2., height + 0.1, 
                   f'{int(height)}', ha='center', va='bottom', fontweight='bold')
        
        ax.grid(axis='y', linestyle='--', alpha=0.7)
        plt.tight_layout()
        
        img = io.BytesIO()
        plt.savefig(img, format='png', bbox_inches='tight', facecolor='white', dpi=100)
        img.seek(0)
        image_data = img.getvalue()
        plt.close()
        
        print("Bar chart created successfully")
        return image_data
        
    except Exception as e:
        print(f"Bar chart generation error: {e}")
        import traceback
        traceback.print_exc()
        return create_simple_error_image()

def create_stacked_bar_chart(data, title):
    """積み上げ棒グラフを作成"""
    try:
        print(f"Creating stacked bar chart with {len(data)} items")
        
        if not data:
            return create_no_data_image(title)
        
        categories = [item['name'] for item in data]
        completed = [item['completed'] for item in data]
        incomplete = [item['incomplete'] for item in data]
        
        # 英語ラベルに変換
        english_categories = [f"Cat{i+1}" for i in range(len(categories))]
        
        fig, ax = plt.subplots(figsize=(10, 6))
        
        x = range(len(english_categories))
        width = 0.6
        
        # 積み上げ棒グラフ
        bars1 = ax.bar(x, completed, width, label='Completed', color='#28a745')
        bars2 = ax.bar(x, incomplete, width, bottom=completed, label='Incomplete', color='#ffc107')
        
        ax.set_title(title, fontsize=14, fontweight='bold', pad=20)
        ax.set_xlabel('Category', fontsize=12)
        ax.set_ylabel('Number of Tasks', fontsize=12)
        ax.set_xticks(x)
        ax.set_xticklabels(english_categories, rotation=45, ha='right')
        ax.legend()
        
        # 各セクションにラベルを表示
        for i, (comp, incomp) in enumerate(zip(completed, incomplete)):
            # 合計値をバーの上に表示
            total = comp + incomp
            if total > 0:
                ax.text(i, total + 0.1, str(total), ha='center', va='bottom', fontweight='bold')
        
        ax.grid(axis='y', linestyle='--', alpha=0.7)
        plt.tight_layout()
        
        img = io.BytesIO()
        plt.savefig(img, format='png', bbox_inches='tight', facecolor='white', dpi=100)
        img.seek(0)
        image_data = img.getvalue()
        plt.close()
        
        print("Stacked bar chart created successfully")
        return image_data
        
    except Exception as e:
        print(f"Stacked bar chart generation error: {e}")
        import traceback
        traceback.print_exc()
        return create_simple_error_image()

def create_no_data_image(title):
    """データがない場合の画像を生成"""
    try:
        fig, ax = plt.subplots(figsize=(6, 4))
        
        ax.text(0.5, 0.5, 'No Data Available', 
               horizontalalignment='center', verticalalignment='center', 
               transform=ax.transAxes, fontsize=16, color='gray')
        ax.set_title(title, fontsize=14)
        
        ax.set_xlim(0, 1)
        ax.set_ylim(0, 1)
        ax.axis('off')
        
        img = io.BytesIO()
        plt.savefig(img, format='png', bbox_inches='tight', facecolor='white', dpi=100)
        img.seek(0)
        image_data = img.getvalue()
        plt.close()
        
        return image_data
    except Exception as e:
        print(f"Error creating no-data image: {e}")
        return create_simple_error_image()

def create_simple_error_image():
    """シンプルなエラー画像を生成"""
    try:
        fig, ax = plt.subplots(figsize=(6, 4))
        ax.text(0.5, 0.5, 'Chart Generation Error', 
               horizontalalignment='center', verticalalignment='center', 
               transform=ax.transAxes, fontsize=14, color='red')
        ax.set_xlim(0, 1)
        ax.set_ylim(0, 1)
        ax.axis('off')
        
        img = io.BytesIO()
        plt.savefig(img, format='png', bbox_inches='tight', facecolor='white', dpi=100)
        img.seek(0)
        image_data = img.getvalue()
        plt.close()
        
        return image_data
    except:
        # 最終的なフォールバック：空のバイナリ
        return b''

def create_no_data_response(message):
    """データがない場合のレスポンスを作成"""
    image_data = create_no_data_image(message)
    return Response(image_data, mimetype='image/png')

# デフォルトルート
@app.route('/edit/<int:id>')
@login_required
def edit_task(id):
    # 編集機能は後で実装、今は一覧画面にリダイレクト
    flash('編集機能は開発中です。', 'info')
    return redirect(url_for('index'))

# 以下、既存のルートを維持（analytics除く、その他のルートはそのまま）
@app.route('/add', methods=['GET', 'POST'])
@login_required
def add_task():
    try:
        print(f"add_task called with method: {request.method}")
        
        if request.method == 'POST':
            try:
                print(f"Form data: {dict(request.form)}")
                
                title = request.form.get('title', '').strip()
                description = request.form.get('description', '').strip()
                due_date = request.form.get('due_date', '').strip()
                due_time = request.form.get('due_time', '').strip()
                category_id = request.form.get('category_id', '').strip()
                new_category = request.form.get('new_category', '').strip()
                priority = request.form.get('priority', 'medium')
                estimated_hours = request.form.get('estimated_hours', '2')
                
                # estimated_hoursの処理
                try:
                    estimated_hours = float(estimated_hours)
                    if estimated_hours <= 0:
                        estimated_hours = 2.0
                except (ValueError, TypeError):
                    estimated_hours = 2.0
                
                print(f"Parsed data - title: {title}, category_id: {category_id}, priority: {priority}, estimated_hours: {estimated_hours}")
                
                if not title:
                    flash('タスクのタイトルは必須です。', 'error')
                    return redirect(url_for('add_task'))
                
                user_id = get_current_user_id()
                print(f"User ID: {user_id}")
                
                final_category_id = None
                final_category_name = ''
                
                # カテゴリ処理
                if category_id == 'other' and new_category:
                    print(f"Creating new category: {new_category}")
                    if user_id:
                        conn = get_db_connection()
                        try:
                            cursor = conn.execute('INSERT INTO categories (name, color, user_id) VALUES (?, ?, ?)', 
                                                (new_category, DEFAULT_COLORS[0], user_id))
                            final_category_id = cursor.lastrowid
                            final_category_name = new_category
                            conn.commit()
                            conn.close()
                            print(f"New category created with ID: {final_category_id}")
                        except sqlite3.IntegrityError as e:
                            conn.close()
                            print(f"Category creation failed: {e}")
                            flash('同じ名前のカテゴリが既に存在します。', 'error')
                            return redirect(url_for('add_task'))
                        except Exception as e:
                            if 'conn' in locals():
                                conn.close()
                            print(f"Database error in category creation: {e}")
                            flash('カテゴリの作成でエラーが発生しました。', 'error')
                            return redirect(url_for('add_task'))
                    else:
                        # ゲストモード処理
                        if 'guest_categories' not in session:
                            session['guest_categories'] = []
                        
                        guest_categories = session.get('guest_categories', [])
                        if any(cat['name'] == new_category for cat in guest_categories):
                            flash('同じ名前のカテゴリが既に存在します。', 'error')
                            return redirect(url_for('add_task'))
                        
                        new_cat_id = max([cat['id'] for cat in guest_categories], default=1000) + 1
                        new_category_obj = {'id': new_cat_id, 'name': new_category, 'color': DEFAULT_COLORS[0], 'user_id': None}
                        guest_categories.append(new_category_obj)
                        session['guest_categories'] = guest_categories
                        session.modified = True
                        
                        final_category_id = new_cat_id
                        final_category_name = new_category
                        print(f"Guest category created with ID: {final_category_id}")
                
                elif category_id and category_id != 'other':
                    try:
                        final_category_id = int(category_id)
                        print(f"Using existing category ID: {final_category_id}")
                        
                        if user_id:
                            conn = get_db_connection()
                            cat = conn.execute('SELECT name FROM categories WHERE id = ?', (final_category_id,)).fetchone()
                            final_category_name = cat['name'] if cat else ''
                            conn.close()
                        else:
                            all_categories = []
                            conn = get_db_connection()
                            db_categories = conn.execute('SELECT * FROM categories WHERE user_id IS NULL').fetchall()
                            conn.close()
                            all_categories.extend(db_categories)
                            all_categories.extend(session.get('guest_categories', []))
                            
                            for cat in all_categories:
                                if cat['id'] == final_category_id:
                                    final_category_name = cat['name']
                                    break
                        
                        print(f"Category name resolved: {final_category_name}")
                        
                    except (ValueError, TypeError) as e:
                        print(f"Invalid category ID: {e}")
                        flash('無効なカテゴリが選択されました。', 'error')
                        return redirect(url_for('add_task'))
                
                # タスクの保存（estimated_hoursを追加）
                print(f"Saving task - user_id: {user_id}")
                
                if user_id:
                    conn = get_db_connection()
                    try:
                        conn.execute('''INSERT INTO tasks (title, description, due_date, due_time, category, category_id, priority, estimated_hours, user_id) 
                                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)''', 
                                   (title, description, due_date, due_time, final_category_name, final_category_id, priority, estimated_hours, user_id))
                        conn.commit()
                        conn.close()
                        print("Task saved successfully to database")
                    except Exception as e:
                        conn.close()
                        print(f"Database error in task creation: {e}")
                        import traceback
                        traceback.print_exc()
                        flash(f'タスクの保存でエラーが発生しました: {str(e)}', 'error')
                        return redirect(url_for('add_task'))
                else:
                    # ゲストモード
                    try:
                        if 'guest_tasks' not in session:
                            session['guest_tasks'] = []
                        
                        existing_ids = [task['id'] for task in session['guest_tasks']]
                        new_id = max(existing_ids, default=0) + 1
                        
                        new_task = {
                            'id': new_id, 
                            'title': title, 
                            'description': description, 
                            'due_date': due_date, 
                            'due_time': due_time, 
                            'category': final_category_name, 
                            'category_id': final_category_id, 
                            'priority': priority, 
                            'estimated_hours': estimated_hours,
                            'completed': 0, 
                            'created_at': datetime.now().isoformat()
                        }
                        
                        guest_tasks = session['guest_tasks'].copy()
                        guest_tasks.append(new_task)
                        session['guest_tasks'] = guest_tasks
                        session.modified = True
                        print(f"Task saved successfully to session: {new_task}")
                    except Exception as e:
                        print(f"Session error in task creation: {e}")
                        import traceback
                        traceback.print_exc()
                        flash(f'タスクの保存でエラーが発生しました: {str(e)}', 'error')
                        return redirect(url_for('add_task'))
                
                flash('タスクを追加しました！', 'success')
                print("Task creation completed successfully")
                return redirect(url_for('index'))
                
            except Exception as e:
                print(f"General error in add_task: {e}")
                import traceback
                traceback.print_exc()
                flash(f'タスクの追加でエラーが発生しました: {str(e)}', 'error')
                return redirect(url_for('add_task'))
        
        # GET request
        try:
            print("Loading add_task form")
            
            if 'guest_mode' in session:
                conn = get_db_connection()
                db_categories = conn.execute('SELECT * FROM categories WHERE user_id IS NULL ORDER BY name').fetchall()
                conn.close()
                
                categories = list(db_categories)
                categories.extend(session.get('guest_categories', []))
            else:
                conn = get_db_connection()
                user_id = session.get('user_id')
                categories = conn.execute('SELECT * FROM categories WHERE user_id IS NULL OR user_id = ? ORDER BY user_id IS NULL DESC, name ASC', (user_id,)).fetchall()
                conn.close()
            
            print(f"Categories loaded: {len(categories)}")
            return render_template('add_task.html', categories=categories)
        
        except Exception as e:
            print(f"Error loading add_task form: {e}")
            import traceback
            traceback.print_exc()
            flash('フォームの読み込みでエラーが発生しました。', 'error')
            return render_template('add_task.html', categories=[])
    
    except Exception as e:
        print(f"Add task route error: {e}")
        import traceback
        traceback.print_exc()
        return f"Add task error: {str(e)}", 500

@app.route('/complete/<int:id>')
@login_required
def complete_task(id):
    try:
        user_id = get_current_user_id()
        
        if user_id:
            conn = get_db_connection()
            task = conn.execute('SELECT * FROM tasks WHERE id = ? AND user_id = ?', (id, user_id)).fetchone()
            
            if task:
                new_status = 0 if task['completed'] else 1
                conn.execute('UPDATE tasks SET completed = ? WHERE id = ? AND user_id = ?', (new_status, id, user_id))
                conn.commit()
                conn.close()
                
                status_text = "完了" if new_status else "未完了"
                flash(f'タスクを{status_text}にしました！', 'success')
            else:
                conn.close()
                flash('タスクが見つかりません！', 'error')
        else:
            guest_tasks = session.get('guest_tasks', [])
            for task in guest_tasks:
                if task['id'] == id:
                    task['completed'] = 0 if task['completed'] else 1
                    session.modified = True
                    status_text = "完了" if task['completed'] else "未完了"
                    flash(f'タスクを{status_text}にしました！', 'success')
                    break
            else:
                flash('タスクが見つかりません！', 'error')
        
        return redirect(url_for('index'))
    except Exception as e:
        print(f"Complete task error: {e}")
        return f"Complete task error: {str(e)}", 500

@app.route('/delete/<int:id>')
@login_required
def delete_task(id):
    try:
        user_id = get_current_user_id()
        
        if user_id:
            conn = get_db_connection()
            result = conn.execute('DELETE FROM tasks WHERE id = ? AND user_id = ?', (id, user_id))
            
            if result.rowcount > 0:
                conn.commit()
                flash('タスクを削除しました！', 'success')
            else:
                flash('タスクが見つかりません！', 'error')
            
            conn.close()
        else:
            guest_tasks = session.get('guest_tasks', [])
            original_length = len(guest_tasks)
            session['guest_tasks'] = [task for task in guest_tasks if task['id'] != id]
            
            if len(session['guest_tasks']) < original_length:
                session.modified = True
                flash('タスクを削除しました！', 'success')
            else:
                flash('タスクが見つかりません！', 'error')
        
        return redirect(url_for('index'))
    except Exception as e:
        print(f"Delete task error: {e}")
        return f"Delete task error: {str(e)}", 500

# 分析ページを簡素化
@app.route('/analytics')
@login_required
def analytics():
    try:
        user_id = get_current_user_id()
        
        if user_id:
            conn = get_db_connection()
            
            total_tasks = conn.execute('SELECT COUNT(*) FROM tasks WHERE user_id = ?', (user_id,)).fetchone()[0]
            completed_tasks = conn.execute('SELECT COUNT(*) FROM tasks WHERE user_id = ? AND completed = 1', (user_id,)).fetchone()[0]
            incomplete_tasks = total_tasks - completed_tasks
            
            category_data = conn.execute('''
                SELECT c.name, c.color, COUNT(t.id) as total, 
                       SUM(CASE WHEN t.completed = 1 THEN 1 ELSE 0 END) as completed 
                FROM categories c 
                LEFT JOIN tasks t ON c.id = t.category_id AND t.user_id = ? 
                WHERE c.user_id IS NULL OR c.user_id = ? 
                GROUP BY c.id, c.name, c.color 
                HAVING COUNT(t.id) > 0 
                ORDER BY COUNT(t.id) DESC
            ''', (user_id, user_id)).fetchall()
            
            category_stats = {}
            for cat in category_data:
                category_stats[cat['name']] = {
                    'total': cat['total'], 
                    'completed': cat['completed'], 
                    'color': cat['color']
                }
            
            priority_data = conn.execute('''
                SELECT priority, COUNT(*) as total, 
                       SUM(CASE WHEN completed = 1 THEN 1 ELSE 0 END) as completed 
                FROM tasks WHERE user_id = ? 
                GROUP BY priority
            ''', (user_id,)).fetchall()
            
            priority_stats = {}
            for pri in priority_data:
                priority_stats[pri['priority']] = {
                    'total': pri['total'], 
                    'completed': pri['completed']
                }
            
            conn.close()
            
        else:
            # ゲストモードの処理
            guest_tasks = session.get('guest_tasks', [])
            total_tasks = len(guest_tasks)
            completed_tasks = sum(1 for task in guest_tasks if task.get('completed'))
            incomplete_tasks = total_tasks - completed_tasks
            
            category_stats = {}
            priority_stats = {}
            
            category_counts = {}
            category_completed = {}
            for task in guest_tasks:
                category = task.get('category', 'Uncategorized')
                category_counts[category] = category_counts.get(category, 0) + 1
                if task.get('completed'):
                    category_completed[category] = category_completed.get(category, 0) + 1
            
            for category, total in category_counts.items():
                category_stats[category] = {
                    'total': total, 
                    'completed': category_completed.get(category, 0), 
                    'color': '#6c757d'
                }
            
            priority_counts = {}
            priority_completed = {}
            for task in guest_tasks:
                priority = task.get('priority', 'medium')
                priority_counts[priority] = priority_counts.get(priority, 0) + 1
                if task.get('completed'):
                    priority_completed[priority] = priority_completed.get(priority, 0) + 1
            
            for priority, total in priority_counts.items():
                priority_stats[priority] = {
                    'total': total, 
                    'completed': priority_completed.get(priority, 0)
                }
        
        return render_template('analytics.html', 
                             total_tasks=total_tasks, 
                             completed_tasks=completed_tasks, 
                             incomplete_tasks=incomplete_tasks, 
                             category_stats=category_stats, 
                             priority_stats=priority_stats, 
                             is_guest='guest_mode' in session)
    
    except Exception as e:
        print(f"Analytics error: {e}")
        import traceback
        traceback.print_exc()
        return render_template('analytics.html', 
                             total_tasks=0, 
                             completed_tasks=0, 
                             incomplete_tasks=0, 
                             category_stats={}, 
                             priority_stats={}, 
                             is_guest='guest_mode' in session,
                             error_message=f"データの読み込みに失敗しました: {str(e)}")

@app.route('/categories')
@login_required
def categories():
    try:
        if 'guest_mode' in session:
            conn = get_db_connection()
            db_categories = conn.execute('SELECT * FROM categories WHERE user_id IS NULL ORDER BY name').fetchall()
            conn.close()
            
            categories = [{'id': cat['id'], 'name': cat['name'], 'color': cat['color']} for cat in db_categories]
            categories.extend(session.get('guest_categories', []))
            
            guest_tasks = session.get('guest_tasks', [])
            task_counts = {}
            for task in guest_tasks:
                category_name = task.get('category', '')
                if category_name:
                    task_counts[category_name] = task_counts.get(category_name, 0) + 1
            
        else:
            conn = get_db_connection()
            user_id = session.get('user_id')
            
            categories_with_counts = conn.execute('''
                SELECT c.id, c.name, c.color, COUNT(t.id) as task_count 
                FROM categories c 
                LEFT JOIN tasks t ON c.id = t.category_id AND t.user_id = ? 
                WHERE c.user_id IS NULL OR c.user_id = ? 
                GROUP BY c.id, c.name, c.color 
                ORDER BY c.user_id IS NULL DESC, c.name ASC
            ''', (user_id, user_id)).fetchall()
            
            conn.close()
            
            categories = []
            task_counts = {}
            for cat in categories_with_counts:
                categories.append({'id': cat['id'], 'name': cat['name'], 'color': cat['color']})
                task_counts[cat['name']] = cat['task_count']
        
        is_guest = 'guest_mode' in session
        
        return render_template('categories.html', 
                             categories=categories, 
                             task_counts=task_counts, 
                             default_colors=DEFAULT_COLORS, 
                             is_guest=is_guest)
    
    except Exception as e:
        print(f"Categories route error: {e}")
        import traceback
        traceback.print_exc()
        return render_template('categories.html', 
                             categories=[], 
                             task_counts={}, 
                             default_colors=DEFAULT_COLORS, 
                             is_guest='guest_mode' in session)

@app.route('/add_category', methods=['GET', 'POST'])
@login_required
def add_category():
    try:
        if request.method == 'GET':
            return redirect(url_for('categories'))
        
        name = request.form.get('name')
        color = request.form.get('color', '#007bff')
        
        if not name:
            flash('カテゴリ名を入力してください。', 'error')
            return redirect(url_for('categories'))
        
        if 'guest_mode' in session:
            if 'guest_categories' not in session:
                session['guest_categories'] = []
            
            guest_categories = session.get('guest_categories', [])
            if any(cat['name'] == name for cat in guest_categories):
                flash('同じ名前のカテゴリが既に存在します。', 'error')
                return redirect(url_for('categories'))
            
            new_cat_id = max([cat['id'] for cat in guest_categories], default=1000) + 1
            new_category = {'id': new_cat_id, 'name': name, 'color': color, 'user_id': None}
            
            guest_categories.append(new_category)
            session['guest_categories'] = guest_categories
            session.modified = True
            flash('カテゴリを追加しました。（ゲストモード）', 'success')
        else:
            conn = get_db_connection()
            try:
                conn.execute('INSERT INTO categories (name, color, user_id) VALUES (?, ?, ?)', (name, color, session.get('user_id')))
                conn.commit()
                conn.close()
                flash('カテゴリを追加しました。', 'success')
            except sqlite3.IntegrityError:
                conn.close()
                flash('同じ名前のカテゴリは既に存在します。', 'error')
    
    except Exception as e:
        print(f"Add category error: {e}")
        flash(f'カテゴリの追加に失敗しました: {str(e)}', 'error')
    
    return redirect(url_for('categories'))

@app.route('/delete_category/<int:category_id>', methods=['POST'])
@login_required
def delete_category(category_id):
    try:
        if 'guest_mode' in session:
            guest_categories = session.get('guest_categories', [])
            session['guest_categories'] = [cat for cat in guest_categories if cat['id'] != category_id]
            session.modified = True
            flash('カテゴリを削除しました。（ゲストモード）', 'success')
        else:
            conn = get_db_connection()
            user_id = session.get('user_id')
            
            result = conn.execute('DELETE FROM categories WHERE id = ? AND user_id = ?', (category_id, user_id))
            
            if result.rowcount > 0:
                conn.commit()
                flash('カテゴリを削除しました。', 'success')
            else:
                flash('削除できませんでした。', 'error')
            
            conn.close()
    
    except Exception as e:
        print(f"Delete category error: {e}")
        flash(f'カテゴリの削除に失敗しました: {str(e)}', 'error')
    
    return redirect(url_for('categories'))

@app.route('/debug')
def debug():
    try:
        debug_info = {
            "status": "OK",
            "session": dict(session),
            "db_path": DB_PATH,
            "db_exists": os.path.exists(DB_PATH),
            "environment": {
                "PORT": os.environ.get('PORT'),
                "SECRET_KEY": "***" if os.environ.get('SECRET_KEY') else None,
                "DATABASE_URL": os.environ.get('DATABASE_URL')
            }
        }
        
        try:
            conn = get_db_connection()
            tables = conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
            debug_info["tables"] = [table['name'] for table in tables]
            
            for table_name in debug_info["tables"]:
                count = conn.execute(f"SELECT COUNT(*) FROM {table_name}").fetchone()[0]
                debug_info[f"{table_name}_count"] = count
            
            conn.close()
        except Exception as e:
            debug_info["db_error"] = str(e)
        
        return jsonify(debug_info)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/health')
def health():
    try:
        ensure_initialization()
        
        conn = get_db_connection()
        conn.execute('SELECT 1')
        conn.close()
        return {"status": "healthy", "timestamp": datetime.now().isoformat()}, 200
    except Exception as e:
        return {"status": "unhealthy", "error": str(e)}, 500

@app.errorhandler(500)
def internal_error(error):
    print(f"500 error: {error}")
    import traceback
    traceback.print_exc()
    return f"Internal Server Error: {str(error)}", 500

@app.errorhandler(404)
def not_found(error):
    print(f"404 error: {error}")
    return "Page Not Found", 404

@app.errorhandler(Exception)
def handle_exception(e):
    print(f"Unhandled exception: {e}")
    import traceback
    traceback.print_exc()
    return f"Server Error: {str(e)}", 500

ensure_initialization()

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=os.environ.get('FLASK_ENV') == 'development')

# 実働時間管理のAPIエンドポイント群

@app.route('/api/work_session/start', methods=['POST'])
@login_required
def start_work_session():
    """作業セッションを開始"""
    try:
        data = request.get_json()
        task_id = data.get('task_id')
        
        if not task_id:
            return jsonify({'error': 'Task ID is required'}), 400
            
        user_id = get_current_user_id()
        current_time = datetime.now().isoformat()
        
        if user_id:
            # データベースユーザー
            conn = get_db_connection()
            
            # 既存のアクティブセッションを終了
            conn.execute('''
                UPDATE work_sessions 
                SET is_active = 0, end_time = ? 
                WHERE task_id = ? AND user_id = ? AND is_active = 1
            ''', (current_time, task_id, user_id))
            
            # 新しいセッションを開始
            cursor = conn.execute('''
                INSERT INTO work_sessions (task_id, user_id, start_time) 
                VALUES (?, ?, ?)
            ''', (task_id, user_id, current_time))
            
            session_id = cursor.lastrowid
            conn.commit()
            conn.close()
            
        else:
            # ゲストモード
            if 'guest_work_sessions' not in session:
                session['guest_work_sessions'] = {}
            
            # 既存セッションを終了
            guest_sessions = session.get('guest_work_sessions', {})
            if str(task_id) in guest_sessions:
                guest_sessions[str(task_id)]['is_active'] = False
                guest_sessions[str(task_id)]['end_time'] = current_time
            
            # 新しいセッションを開始
            session_id = len(guest_sessions) + 1
            guest_sessions[str(task_id)] = {
                'id': session_id,
                'task_id': task_id,
                'start_time': current_time,
                'focus_seconds': 0,
                'break_seconds': 0,
                'is_active': True,
                'interruptions': []
            }
            
            session['guest_work_sessions'] = guest_sessions
            session.modified = True
        
        return jsonify({
            'success': True, 
            'session_id': session_id,
            'start_time': current_time
        })
        
    except Exception as e:
        print(f"Error starting work session: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/work_session/pause', methods=['POST'])
@login_required
def pause_work_session():
    """作業セッションを一時停止"""
    try:
        data = request.get_json()
        task_id = data.get('task_id')
        focus_seconds = data.get('focus_seconds', 0)
        
        if not task_id:
            return jsonify({'error': 'Task ID is required'}), 400
            
        user_id = get_current_user_id()
        current_time = datetime.now().isoformat()
        
        if user_id:
            # データベースユーザー
            conn = get_db_connection()
            
            # アクティブセッションを更新
            conn.execute('''
                UPDATE work_sessions 
                SET focus_seconds = focus_seconds + ? 
                WHERE task_id = ? AND user_id = ? AND is_active = 1
            ''', (focus_seconds, task_id, user_id))
            
            # 中断記録を開始
            conn.execute('''
                INSERT INTO interruptions (session_id, start_time) 
                SELECT id, ? FROM work_sessions 
                WHERE task_id = ? AND user_id = ? AND is_active = 1
            ''', (current_time, task_id, user_id))
            
            conn.commit()
            conn.close()
            
        else:
            # ゲストモード
            guest_sessions = session.get('guest_work_sessions', {})
            if str(task_id) in guest_sessions and guest_sessions[str(task_id)]['is_active']:
                guest_sessions[str(task_id)]['focus_seconds'] += focus_seconds
                guest_sessions[str(task_id)]['interruptions'].append({
                    'start_time': current_time,
                    'end_time': None
                })
                session['guest_work_sessions'] = guest_sessions
                session.modified = True
        
        return jsonify({'success': True, 'pause_time': current_time})
        
    except Exception as e:
        print(f"Error pausing work session: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/work_session/resume', methods=['POST'])
@login_required
def resume_work_session():
    """作業セッションを再開"""
    try:
        data = request.get_json()
        task_id = data.get('task_id')
        break_seconds = data.get('break_seconds', 0)
        
        if not task_id:
            return jsonify({'error': 'Task ID is required'}), 400
            
        user_id = get_current_user_id()
        current_time = datetime.now().isoformat()
        
        if user_id:
            # データベースユーザー
            conn = get_db_connection()
            
            # 中断時間を更新
            conn.execute('''
                UPDATE work_sessions 
                SET break_seconds = break_seconds + ? 
                WHERE task_id = ? AND user_id = ? AND is_active = 1
            ''', (break_seconds, task_id, user_id))
            
            # 最新の中断記録を終了
            conn.execute('''
                UPDATE interruptions 
                SET end_time = ? 
                WHERE session_id = (
                    SELECT id FROM work_sessions 
                    WHERE task_id = ? AND user_id = ? AND is_active = 1
                ) AND end_time IS NULL
            ''', (current_time, task_id, user_id))
            
            conn.commit()
            conn.close()
            
        else:
            # ゲストモード
            guest_sessions = session.get('guest_work_sessions', {})
            if str(task_id) in guest_sessions and guest_sessions[str(task_id)]['is_active']:
                guest_sessions[str(task_id)]['break_seconds'] += break_seconds
                
                # 最新の中断を終了
                interruptions = guest_sessions[str(task_id)]['interruptions']
                if interruptions and interruptions[-1]['end_time'] is None:
                    interruptions[-1]['end_time'] = current_time
                
                session['guest_work_sessions'] = guest_sessions
                session.modified = True
        
        return jsonify({'success': True, 'resume_time': current_time})
        
    except Exception as e:
        print(f"Error resuming work session: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/work_session/end', methods=['POST'])
@login_required
def end_work_session():
    """作業セッションを終了"""
    try:
        data = request.get_json()
        task_id = data.get('task_id')
        focus_seconds = data.get('focus_seconds', 0)
        
        if not task_id:
            return jsonify({'error': 'Task ID is required'}), 400
            
        user_id = get_current_user_id()
        current_time = datetime.now().isoformat()
        
        if user_id:
            # データベースユーザー
            conn = get_db_connection()
            
            # セッションを終了
            conn.execute('''
                UPDATE work_sessions 
                SET is_active = 0, end_time = ?, focus_seconds = focus_seconds + ? 
                WHERE task_id = ? AND user_id = ? AND is_active = 1
            ''', (current_time, focus_seconds, task_id, user_id))
            
            conn.commit()
            conn.close()
            
        else:
            # ゲストモード
            guest_sessions = session.get('guest_work_sessions', {})
            if str(task_id) in guest_sessions:
                guest_sessions[str(task_id)]['is_active'] = False
                guest_sessions[str(task_id)]['end_time'] = current_time
                guest_sessions[str(task_id)]['focus_seconds'] += focus_seconds
                session['guest_work_sessions'] = guest_sessions
                session.modified = True
        
        return jsonify({'success': True, 'end_time': current_time})
        
    except Exception as e:
        print(f"Error ending work session: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/work_session/stats/<int:task_id>')
@login_required
def get_work_stats(task_id):
    """タスクの実働時間統計を取得"""
    try:
        user_id = get_current_user_id()
        
        if user_id:
            # データベースユーザー
            conn = get_db_connection()
            
            # 総実働時間とセッション情報を取得
            stats = conn.execute('''
                SELECT 
                    SUM(focus_seconds) as total_focus_seconds,
                    SUM(break_seconds) as total_break_seconds,
                    COUNT(*) as session_count,
                    AVG(focus_seconds) as avg_focus_seconds
                FROM work_sessions 
                WHERE task_id = ? AND user_id = ?
            ''', (task_id, user_id)).fetchone()
            
            # 中断回数を取得
            interruption_count = conn.execute('''
                SELECT COUNT(*) FROM interruptions i
                JOIN work_sessions ws ON i.session_id = ws.id
                WHERE ws.task_id = ? AND ws.user_id = ?
            ''', (task_id, user_id)).fetchone()[0]
            
            conn.close()
            
            return jsonify({
                'total_focus_seconds': stats['total_focus_seconds'] or 0,
                'total_break_seconds': stats['total_break_seconds'] or 0,
                'session_count': stats['session_count'] or 0,
                'interruption_count': interruption_count,
                'avg_focus_seconds': stats['avg_focus_seconds'] or 0,
                'focus_percentage': round((stats['total_focus_seconds'] or 0) / max((stats['total_focus_seconds'] or 0) + (stats['total_break_seconds'] or 0), 1) * 100, 1)
            })
            
        else:
            # ゲストモード
            guest_sessions = session.get('guest_work_sessions', {})
            task_session = guest_sessions.get(str(task_id))
            
            if task_session:
                total_focus = task_session['focus_seconds']
                total_break = task_session['break_seconds']
                interruption_count = len(task_session['interruptions'])
                
                return jsonify({
                    'total_focus_seconds': total_focus,
                    'total_break_seconds': total_break,
                    'session_count': 1,
                    'interruption_count': interruption_count,
                    'avg_focus_seconds': total_focus,
                    'focus_percentage': round(total_focus / max(total_focus + total_break, 1) * 100, 1)
                })
            else:
                return jsonify({
                    'total_focus_seconds': 0,
                    'total_break_seconds': 0,
                    'session_count': 0,
                    'interruption_count': 0,
                    'avg_focus_seconds': 0,
                    'focus_percentage': 100
                })
        
    except Exception as e:
        print(f"Error getting work stats: {e}")
        return jsonify({'error': str(e)}), 500
