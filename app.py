from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, session
import sqlite3
from datetime import datetime, timedelta
import os
import json
from collections import defaultdict
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps

# matplotlib設定をインポート前に行う
import matplotlib
matplotlib.use('Agg')  # GUI不要のバックエンドを設定
# フォント警告を無効にする
matplotlib.rcParams['font.family'] = 'DejaVu Sans'
import matplotlib.pyplot as plt
import io
import base64

# Create the Flask application
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
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    try:
        # データベースディレクトリの作成
        db_dir = os.path.dirname(DB_PATH)
        if db_dir and not os.path.exists(db_dir):
            os.makedirs(db_dir, exist_ok=True)
            
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
        
        # カテゴリテーブル（新規追加）
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
        
        # タスクテーブル（category_idを追加）
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
            completed INTEGER DEFAULT 0,
            user_id INTEGER,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users (id),
            FOREIGN KEY (category_id) REFERENCES categories (id)
        )
        ''')
        
        # 既存のテーブルに新しいカラムを追加（既存データ対応）
        try:
            conn.execute('ALTER TABLE tasks ADD COLUMN due_time TEXT')
        except sqlite3.OperationalError as e:
            if "duplicate column name" not in str(e).lower():
                print(f"Warning: Could not add due_time column: {e}")
        
        try:
            conn.execute('ALTER TABLE tasks ADD COLUMN category_id INTEGER')
        except sqlite3.OperationalError as e:
            if "duplicate column name" not in str(e).lower():
                print(f"Warning: Could not add category_id column: {e}")
        
        # デフォルトカテゴリの作成（グローバル）
        try:
            existing_global_categories = conn.execute('SELECT COUNT(*) FROM categories WHERE user_id IS NULL').fetchone()[0]
            if existing_global_categories == 0:
                default_categories = [
                    ('仕事', DEFAULT_COLORS[0], None),
                    ('個人', DEFAULT_COLORS[1], None),
                    ('勉強', DEFAULT_COLORS[2], None)
                ]
                conn.executemany('INSERT INTO categories (name, color, user_id) VALUES (?, ?, ?)', default_categories)
                print("Default categories created successfully")
        except Exception as e:
            print(f"Warning: Could not create default categories: {e}")
        
        conn.commit()
        conn.close()
        print("Database initialized successfully")
        
    except Exception as e:
        print(f"Database initialization error: {e}")
        # エラーが発生してもアプリを継続実行
        pass

# アプリケーション起動前のヘルスチェック
def health_check():
    """アプリケーションの基本的なヘルスチェック"""
    try:
        # データベース接続テスト
        conn = get_db_connection()
        conn.execute('SELECT 1')
        conn.close()
        return True
    except Exception as e:
        print(f"Health check failed: {e}")
        return False

# 初期化フラグ（重複実行防止）
_initialized = False

def ensure_initialization():
    """初期化の実行を保証（重複実行防止）"""
    global _initialized
    if not _initialized:
        print("Performing one-time initialization...")
        init_db()
        _initialized = True
        print("Initialization completed")

# Flaskアプリケーションのエラーハンドラー
@app.errorhandler(500)
def internal_error(error):
    """内部サーバーエラーのハンドリング"""
    print(f"Internal server error: {error}")
    return "Internal Server Error", 500

@app.errorhandler(404)
def not_found(error):
    """404エラーのハンドリング"""
    return "Page Not Found", 404

# ヘルスチェックエンドポイント（Render用）
@app.route('/health')
def health():
    """ヘルスチェックエンドポイント"""
    try:
        # 初期化を確認
        ensure_initialization()
        
        # データベース接続テスト
        conn = get_db_connection()
        conn.execute('SELECT 1')
        conn.close()
        return {"status": "healthy", "timestamp": datetime.now().isoformat()}, 200
    except Exception as e:
        return {"status": "unhealthy", "error": str(e)}, 500

# 最初のリクエスト前に初期化実行（Flask 2.2以降対応）
def initialize_on_first_request():
    """最初のリクエスト前にデータベースを初期化"""
    ensure_initialization()

# Flask 2.2以降の方式でリクエスト前処理
@app.before_request
def before_request():
    """各リクエスト前に実行（初回のみ初期化）"""
    ensure_initialization()

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session and 'guest_mode' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

@app.route('/')
def landing():
    """ランディングページ"""
    return render_template('landing.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        
        conn = get_db_connection()
        user = conn.execute('SELECT * FROM users WHERE username = ?', (username,)).fetchone()
        conn.close()
        
        if user and check_password_hash(user['password_hash'], password):
            session['user_id'] = user['id']
            session['username'] = user['username']
            flash('ログインしました！', 'success')
            return redirect(url_for('index'))
        else:
            flash('ユーザー名またはパスワードが正しくありません。', 'error')
    
    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
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
            conn.execute('INSERT INTO users (username, email, password_hash) VALUES (?, ?, ?)',
                        (username, email, password_hash))
            conn.commit()
            conn.close()
            flash('アカウントが作成されました！ログインしてください。', 'success')
            return redirect(url_for('login'))
        except sqlite3.IntegrityError:
            conn.close()
            flash('このユーザー名またはメールアドレスは既に使用されています。', 'error')
    
    return render_template('register.html')

@app.route('/guest')
def guest_mode():
    """ゲストモードで開始"""
    session['guest_mode'] = True
    flash('ゲストモードで開始しました。データは保存されません。', 'info')
    return redirect(url_for('index'))

@app.route('/logout')
def logout():
    session.clear()
    flash('ログアウトしました。', 'info')
    return redirect(url_for('landing'))

@app.route('/dashboard')
@login_required
def landing():
    """ランディングページ"""
    return render_template('landing.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        
        conn = get_db_connection()
        taskss = conn.execute('SELECT * FROMtaskss WHERE use_id = ? ORDER BY completed, due_date ASC', 
                          RDER B_idmplefetchall_date ASC', 
                           (user_id,)).fetchall()
        conn.close()
        
        if user and check_password_hash(user['password_hash'], password):
            session['user_id'] = user['id']
            session['username'] = user['username']
            flash('ログインしました！', 'success')
            return redirect(url_for('index'))
        else:
            # ログインユーザー：データベースに追加
            conn = get_db_connection()
            try:
                conn.execute(
                    'INSERT INTO categories (name, color, user_id) VALUES (?, ?, ?)',
                    (name, color, session.get('user_id'))
                )
                conn.commit()
                conn.close()
                flash('カテゴリを追加しました。', 'success')
            except sqlite3.IntegrityError:
                conn.close()
                flash('同じ名前のカテゴリが既に存在します。', 'error')
    
    except Exception as e:
        print(f"Add category error: {e}")
        flash(f'カテゴリの追加に失敗しました: {str(e)}', 'error')
    
    return redirect(url_for('categories'))

@app.route('/add', methods=['GET', 'POST'])
@login_required
def add_task():
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
            conn.execute('INSERT INTO users (username, email, password_hash) VALUES (?, ?, ?)',
                        (username, email, password_hash))
            conn.commit()
            conn.close()
            flash('アカウントが作成されました！ログインしてください。', 'success')
            return redirect(url_for('login'))
        except sqlite3.IntegrityError:
            conn.close()
            flash('このユーザー名またはメールアドレスは既に使用されています。', 'error')
    
    return render_template('register.html')

@app.route('/guest')
def guest_mode():
    """ゲストモードで開始"""
    session['guest_mode'] = True
    flash('ゲストモードで開始しました。データは保存されません。', 'info')
    return redirect(url_for('index'))

@app.route('/logout')
def logout():
    session.clear()
    flash('ログアウトしました。', 'info')
    return redirect(url_for('landing'))

@app.route('/dashboard')
@login_required
def index():
    user_id = get_current_user_id()
    
    if user_id:
        # 認証ユーザーのタスクとカテゴリ色を取得
        conn = get_db_connection()
        tasks = conn.execute('''
            SELECT t.*, c.color as category_color 
            FROM tasks t 
            LEFT JOIN categories c ON t.category_id = c.id 
            WHERE t.user_id = ? 
            ORDER BY t.completed, t.due_date ASC
        ''', (user_id,)).fetchall()
        conn.close()
    else:
        # ゲストモードの場合、セッション内のタスクを使用
        tasks = session.get('guest_tasks', [])
        
        # ゲストタスクにカテゴリ色を追加
        if tasks:
            # カテゴリ情報を取得
            conn = get_db_connection()
            db_categories = conn.execute('SELECT * FROM categories WHERE user_id IS NULL').fetchall()
            conn.close()
            
            all_categories = {}
            for cat in db_categories:
                all_categories[cat['id']] = cat['color']
            
            for cat in session.get('guest_categories', []):
                all_categories[cat['id']] = cat['color']
            
            # タスクにカテゴリ色を追加
            for task in tasks:
                task['category_color'] = all_categories.get(task.get('category_id'), '#6c757d')
    
    is_guest = 'guest_mode' in session
    return render_template('index.html', tasks=tasks, is_guest=is_guest)

@app.route('/login')
def login():
    """ログインページ"""
    try:
        return "<h1>Login Page</h1><p>Please implement login functionality</p><a href='/'>Back to Home</a>"
    except Exception as e:
        print(f"Login route error: {e}")
        return f"Error: {str(e)}", 500

@app.route('/test')
def test():
    """テストエンドポイント"""
    try:
        # データベース接続テスト
        conn = get_db_connection()
        tables = conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        
        # 各テーブルの件数も確認
        table_info = {}
        for table in tables:
            count = conn.execute(f"SELECT COUNT(*) FROM {table['name']}").fetchone()[0]
            table_info[table['name']] = count
        
        conn.close()
        
        return {
            "status": "success",
            "message": "Application is working",
            "tables": table_info,
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}, 500

# アプリケーション起動時に初期化を実行
print("Starting application initialization...")
ensure_initialization()
print("Application initialization completed")

# gunicorn用のアプリケーションオブジェクト
application = app

# 開発環境での直接実行
if __name__ == '__main__':
    try:
        port = int(os.environ.get('PORT', 5000))
        host = '0.0.0.0'
        
        print(f"Starting Flask app on {host}:{port}")
        
        debug_mode = os.environ.get('FLASK_ENV') == 'development'
        
        app.run(
            host=host,
            port=port,
            debug=debug_mode,
            threaded=True
        )
    except Exception as e:
        print(f"Error starting application: {e}")
        exit(1)
