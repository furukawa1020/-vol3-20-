from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, session, Response
import sqlite3
from datetime import datetime, timedelta
import os
import json
from collections import defaultdict
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps

# matplotlib設定を最初に行う
import matplotlib
matplotlib.use('Agg')

# 日本語フォント設定
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm
import io
import base64

# 日本語フォントの設定
def setup_japanese_font():
    """日本語フォントを設定"""
    try:
        # システムに応じたフォント設定
        import platform
        system = platform.system()
        
        if system == "Darwin":  # macOS
            font_paths = [
                "/System/Library/Fonts/ヒラギノ角ゴシック W3.ttc",
                "/Library/Fonts/Arial Unicode MS.ttf"
            ]
        elif system == "Linux":  # Linux (Render等)
            font_paths = [
                "/usr/share/fonts/truetype/noto-cjk/NotoSansCJK-Regular.ttc",
                "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf"
            ]
        elif system == "Windows":  # Windows
            font_paths = [
                "C:/Windows/Fonts/msgothic.ttc",
                "C:/Windows/Fonts/arial.ttf"
            ]
        else:
            font_paths = []
        
        for font_path in font_paths:
            if os.path.exists(font_path):
                font_prop = fm.FontProperties(fname=font_path)
                plt.rcParams['font.family'] = font_prop.get_name()
                return font_prop
        
        # フォールバック：DejaVu Sans
        plt.rcParams['font.family'] = 'DejaVu Sans'
        return None
        
    except Exception as e:
        print(f"Font setup error: {e}")
        plt.rcParams['font.family'] = 'DejaVu Sans'
        return None

# フォント設定を実行
font_prop = setup_japanese_font()

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
    else:
        # ゲストモードの場合
        guest_tasks = session.get('guest_tasks', [])
        original_length = len(guest_tasks)
        session['guest_tasks'] = [task for task in guest_tasks if task['id'] != id]
        
        if len(session['guest_tasks']) < original_length:
            session.modified = True
            flash('タスクを削除しました！', 'success')
        else:
            flash('タスクが見つかりません！', 'error')
    
    return redirect(url_for('index'))

@app.route('/categories')
@login_required
def categories():
    """カテゴリ管理ページ"""
    try:
        if 'guest_mode' in session:
            # ゲストモード：デフォルトカテゴリ + セッションカテゴリ
            conn = get_db_connection()
            db_categories = conn.execute('SELECT * FROM categories WHERE user_id IS NULL ORDER BY name').fetchall()
            conn.close()
            
            categories = [{'id': cat['id'], 'name': cat['name'], 'color': cat['color']} for cat in db_categories]
            categories.extend(session.get('guest_categories', []))
            
            # ゲストモードのタスク数計算
            guest_tasks = session.get('guest_tasks', [])
            task_counts = {}
            for task in guest_tasks:
                category_name = task.get('category', '')
                if category_name:
                    task_counts[category_name] = task_counts.get(category_name, 0) + 1
            
        else:
            # ログインユーザー：全カテゴリ
            conn = get_db_connection()
            user_id = session.get('user_id')
            
            # カテゴリとタスク数を一緒に取得
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
                categories.append({
                    'id': cat['id'],
                    'name': cat['name'],
                    'color': cat['color']
                })
                task_counts[cat['name']] = cat['task_count']
        
        is_guest = 'guest_mode' in session
        
        return render_template('categories.html', 
                             categories=categories, 
                             task_counts=task_counts,
                             default_colors=DEFAULT_COLORS,
                             is_guest=is_guest)
    
    except Exception as e:
        print(f"Categories route error: {e}")
        flash(f'カテゴリの取得に失敗しました: {str(e)}', 'error')
        return render_template('categories.html', 
                             categories=[], 
                             task_counts={},
                             default_colors=DEFAULT_COLORS,
                             is_guest='guest_mode' in session)

@app.route('/add_category', methods=['GET', 'POST'])
@login_required
def add_category():
    if request.method == 'GET':
        return redirect(url_for('categories'))
    
    try:
        name = request.form.get('name')
        color = request.form.get('color', '#007bff')
        
        if not name:
            flash('カテゴリ名を入力してください。', 'error')
            return redirect(url_for('categories'))
        
        if 'guest_mode' in session:
            # ゲストモード：セッションに追加
            if 'guest_categories' not in session:
                session['guest_categories'] = []
            
            guest_categories = session.get('guest_categories', [])
            if any(cat['name'] == name for cat in guest_categories):
                flash('同じ名前のカテゴリが既に存在します。', 'error')
                return redirect(url_for('categories'))
            
            new_cat_id = max([cat['id'] for cat in guest_categories], default=1000) + 1
            new_category = {
                'id': new_cat_id,
                'name': name,
                'color': color,
                'user_id': None
            }
            
            guest_categories.append(new_category)
            session['guest_categories'] = guest_categories
            session.modified = True
            flash('カテゴリを追加しました。（ゲストモード）', 'success')
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

@app.route('/delete_category/<int:category_id>', methods=['POST'])
@login_required
def delete_category(category_id):
    """カテゴリを削除"""
    try:
        if 'guest_mode' in session:
            # ゲストモード：セッションから削除
            guest_categories = session.get('guest_categories', [])
            session['guest_categories'] = [cat for cat in guest_categories if cat['id'] != category_id]
            session.modified = True
            flash('カテゴリを削除しました。（ゲストモード）', 'success')
        else:
            # ログインユーザー：データベースから削除
            conn = get_db_connection()
            user_id = session.get('user_id')
            
            result = conn.execute(
                'DELETE FROM categories WHERE id = ? AND user_id = ?',
                (category_id, user_id)
            )
            
            if result.rowcount > 0:
                conn.commit()
                flash('カテゴリを削除しました。', 'success')
            else:
                flash('削除できませんでした。デフォルトカテゴリまたは他のユーザーのカテゴリは削除できません。', 'error')
            
            conn.close()
    
    except Exception as e:
        return {"status": "error", "message": str(e)}, 500

# チャート生成エンドポイントを修正
@app.route('/chart/<chart_type>')
@login_required
def generate_chart(chart_type):
    user_id = get_current_user_id()
    
    try:
        if chart_type == 'category_pie':
            chart_data = get_category_data(user_id)
            if not chart_data:
                return create_no_data_response("カテゴリ別データがありません")
            
            image_data = create_pie_chart(chart_data, 'カテゴリ別タスク分布')
            return Response(image_data, mimetype='image/png')
            
        elif chart_type == 'priority_bar':
            chart_data = get_priority_data(user_id)
            if not chart_data:
                return create_no_data_response("優先度別データがありません")
            
            image_data = create_bar_chart(chart_data, '優先度別タスク分布')
            return Response(image_data, mimetype='image/png')
            
        elif chart_type == 'completion_status':
            chart_data = get_completion_data(user_id)
            if not chart_data:
                return create_no_data_response("完了状況データがありません")
            
            image_data = create_pie_chart(chart_data, 'タスク完了状況')
            return Response(image_data, mimetype='image/png')
            
        elif chart_type == 'category_stacked':
            chart_data = get_category_detailed_data(user_id)
            if not chart_data:
                return create_no_data_response("カテゴリ別詳細データがありません")
            
            image_data = create_stacked_bar_chart(chart_data, 'カテゴリ別詳細統計')
            return Response(image_data, mimetype='image/png')
        
        else:
            return create_no_data_response("不正なチャートタイプです")
            
    except Exception as e:
        print(f"Chart generation error: {e}")
        import traceback
        traceback.print_exc()
        return create_no_data_response(f"グラフ生成エラー: {str(e)}")

def get_category_data(user_id):
    """カテゴリ別データを取得"""
    try:
        if user_id:
            conn = get_db_connection()
            data = conn.execute('''
                SELECT c.name, c.color, COUNT(t.id) as count
                FROM categories c
                LEFT JOIN tasks t ON c.id = t.category_id AND t.user_id = ?
                WHERE (c.user_id IS NULL OR c.user_id = ?)
                GROUP BY c.id, c.name, c.color
                HAVING COUNT(t.id) > 0
                ORDER BY COUNT(t.id) DESC
            ''', (user_id, user_id)).fetchall()
            conn.close()
            
            return [{'name': row['name'], 'count': row['count'], 'color': row['color']} for row in data]
        else:
            guest_tasks = session.get('guest_tasks', [])
            if not guest_tasks:
                return []
            
            category_counts = {}
            for task in guest_tasks:
                category = task.get('category', 'Uncategorized')
                category_counts[category] = category_counts.get(category, 0) + 1
            
            return [{'name': name, 'count': count, 'color': '#6c757d'} for name, count in category_counts.items()]
    except Exception as e:
        print(f"Error getting category data: {e}")
        return []

def get_priority_data(user_id):
    """優先度別データを取得"""
    try:
        if user_id:
            conn = get_db_connection()
            data = conn.execute('SELECT priority, COUNT(*) as count FROM tasks WHERE user_id = ? GROUP BY priority ORDER BY count DESC', (user_id,)).fetchall()
            conn.close()
            return [{'priority': row['priority'], 'count': row['count']} for row in data]
        else:
            guest_tasks = session.get('guest_tasks', [])
            if not guest_tasks:
                return []
            
            priority_counts = {}
            for task in guest_tasks:
                priority = task.get('priority', 'medium')
                priority_counts[priority] = priority_counts.get(priority, 0) + 1
            
            return [{'priority': k, 'count': v} for k, v in priority_counts.items()]
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
            guest_tasks = session.get('guest_tasks', [])
            completed = sum(1 for task in guest_tasks if task.get('completed'))
            incomplete = len(guest_tasks) - completed
        
        if completed == 0 and incomplete == 0:
            return []
        
        return [
            {'name': '完了', 'count': completed, 'color': '#28a745'},
            {'name': '未完了', 'count': incomplete, 'color': '#ffc107'}
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
            
            return [{'name': row['name'], 'completed': row['completed'], 'incomplete': row['incomplete'], 'color': row['color']} for row in data]
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
        filtered_data = [item for item in data if item['count'] > 0]
        if not filtered_data:
            return create_no_data_image(title)
        
        labels = [item['name'] for item in filtered_data]
        sizes = [item['count'] for item in filtered_data]
        colors = [item.get('color', '#6c757d') for item in filtered_data]
        
        fig, ax = plt.subplots(figsize=(10, 8))
        
        # 日本語表示のための設定
        if font_prop:
            wedges, texts, autotexts = ax.pie(sizes, labels=labels, colors=colors, 
                                             autopct='%1.1f%%', startangle=90,
                                             textprops={'fontproperties': font_prop, 'fontsize': 10})
            ax.set_title(title, fontproperties=font_prop, fontsize=16, fontweight='bold', pad=20)
        else:
            # フォールバック（英語表示）
            english_labels = [f"Category {i+1}" for i in range(len(labels))]
            wedges, texts, autotexts = ax.pie(sizes, labels=english_labels, colors=colors, 
                                             autopct='%1.1f%%', startangle=90,
                                             textprops={'fontsize': 10})
            ax.set_title(title, fontsize=16, fontweight='bold', pad=20)
        
        for autotext in autotexts:
            autotext.set_color('white')
            autotext.set_fontweight('bold')
        
        plt.tight_layout()
        
        img = io.BytesIO()
        plt.savefig(img, format='png', bbox_inches='tight', facecolor='white', dpi=150)
        img.seek(0)
        image_data = img.getvalue()
        plt.close()
        
        return image_data
    except Exception as e:
        print(f"Pie chart generation error: {e}")
        return create_no_data_image(title)

def create_bar_chart(data, title):
    """棒グラフを作成"""
    try:
        if not data:
            return create_no_data_image(title)
        
        labels = [item['priority'] for item in data]
        values = [item['count'] for item in data]
        
        # 優先度別の色設定
        colors = []
        for label in labels:
            if label == 'high':
                colors.append('#dc3545')
            elif label == 'medium':
                colors.append('#ffc107')
            elif label == 'low':
                colors.append('#17a2b8')
            else:
                colors.append('#6c757d')
        
        fig, ax = plt.subplots(figsize=(10, 6))
        bars = ax.bar(labels, values, color=colors)
        
        # 日本語表示のための設定
        if font_prop:
            ax.set_title(title, fontproperties=font_prop, fontsize=16, fontweight='bold', pad=20)
            ax.set_xlabel('優先度', fontproperties=font_prop, fontsize=12)
            ax.set_ylabel('タスク数', fontproperties=font_prop, fontsize=12)
        else:
            ax.set_title(title, fontsize=16, fontweight='bold', pad=20)
            ax.set_xlabel('Priority', fontsize=12)
            ax.set_ylabel('Number of Tasks', fontsize=12)
        
        # 値をバーの上に表示
        for bar in bars:
            height = bar.get_height()
            ax.text(bar.get_x() + bar.get_width()/2., height + 0.1,
                   f'{int(height)}', ha='center', va='bottom', fontweight='bold')
        
        ax.grid(axis='y', linestyle='--', alpha=0.7)
        plt.tight_layout()
        
        img = io.BytesIO()
        plt.savefig(img, format='png', bbox_inches='tight', facecolor='white', dpi=150)
        img.seek(0)
        image_data = img.getvalue()
        plt.close()
        
        return image_data
    except Exception as e:
        print(f"Bar chart generation error: {e}")
        return create_no_data_image(title)

def create_stacked_bar_chart(data, title):
    """積み上げ棒グラフを作成（提供されたコードを参考）"""
    try:
        if not data:
            return create_no_data_image(title)
        
        categories = [item['name'] for item in data]
        completed = [item['completed'] for item in data]
        incomplete = [item['incomplete'] for item in data]
        
        fig, ax = plt.subplots(figsize=(12, 6))
        
        x = range(len(categories))
        width = 0.6
        
        # 完了タスクの棒グラフ
        bars1 = ax.bar(x, completed, width, label='完了', color='#28a745')
        # 未完了タスクの棒グラフ（完了タスクの上に積み上げ）
        bars2 = ax.bar(x, incomplete, width, bottom=completed, label='未完了', color='#ffc107')
        
        # 日本語表示のための設定
        if font_prop:
            ax.set_title(title, fontproperties=font_prop, fontsize=16, fontweight='bold', pad=20)
            ax.set_xlabel('カテゴリ', fontproperties=font_prop, fontsize=12)
            ax.set_ylabel('タスク数', fontproperties=font_prop, fontsize=12)
            ax.set_xticklabels([''] + categories, fontproperties=font_prop, rotation=45, ha='right')
            ax.legend(prop=font_prop)
        else:
            ax.set_title(title, fontsize=16, fontweight='bold', pad=20)
            ax.set_xlabel('Category', fontsize=12)
            ax.set_ylabel('Number of Tasks', fontsize=12)
            ax.set_xticklabels([''] + [f"Cat{i+1}" for i in range(len(categories))], rotation=45, ha='right')
            ax.legend()
        
        ax.set_xticks(x)
        
        # 各セクションにラベルを表示
        for i, (comp, incomp) in enumerate(zip(completed, incomplete)):
            # 完了部分のラベル
            if comp > 0:
                ax.text(i, comp / 2, '完了' if font_prop else 'Done', 
                       ha='center', va='center', fontweight='bold', 
                       fontproperties=font_prop if font_prop else None,
                       color='white', fontsize=9)
            
            # 未完了部分のラベル
            if incomp > 0:
                ax.text(i, comp + incomp / 2, '未完了' if font_prop else 'Todo', 
                       ha='center', va='center', fontweight='bold',
                       fontproperties=font_prop if font_prop else None,
                       color='black', fontsize=9)
            
            # 合計値をバーの上に表示
            total = comp + incomp
            if total > 0:
                ax.text(i, total + 0.1, str(total), ha='center', va='bottom', fontweight='bold')
        
        ax.grid(axis='y', linestyle='--', alpha=0.7)
        plt.tight_layout()
        
        img = io.BytesIO()
        plt.savefig(img, format='png', bbox_inches='tight', facecolor='white', dpi=150)
        img.seek(0)
        image_data = img.getvalue()
        plt.close()
        
        return image_data
    except Exception as e:
        print(f"Stacked bar chart generation error: {e}")
        return create_no_data_image(title)

def create_no_data_image(title):
    """データがない場合の画像を生成"""
    try:
        fig, ax = plt.subplots(figsize=(8, 6))
        
        message = 'データがありません'
        if font_prop:
            ax.text(0.5, 0.5, message, horizontalalignment='center', verticalalignment='center',
                    transform=ax.transAxes, fontsize=16, color='gray', fontproperties=font_prop)
            ax.set_title(title, fontproperties=font_prop, fontsize=14)
        else:
            ax.text(0.5, 0.5, 'No Data Available', horizontalalignment='center', verticalalignment='center',
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
        return b''

def create_no_data_response(message):
    """データがない場合のレスポンスを作成"""
    image_data = create_no_data_image(message)
    return Response(image_data, mimetype='image/png')

def get_current_user_id():
    return session.get('user_id') if 'guest_mode' not in session else None

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
