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
matplotlib.use('Agg')  # GUIバックエンドを無効化

# 日本語フォント設定
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm
import io
import base64

# 日本語フォントの設定を簡素化
def setup_japanese_font():
    """日本語フォントを設定"""
    try:
        # Renderなどのクラウド環境では基本的にDejaVu Sansを使用
        plt.rcParams['font.family'] = ['DejaVu Sans']
        plt.rcParams['axes.unicode_minus'] = False
        return None
        
    except Exception as e:
        print(f"Font setup error: {e}")
        plt.rcParams['font.family'] = ['DejaVu Sans']
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

def get_current_user_id():
    return session.get('user_id') if 'guest_mode' not in session else None

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
        
        # タスクテーブル
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
        
        # 既存のテーブルに新しいカラムを追加
        try:
            conn.execute('ALTER TABLE tasks ADD COLUMN due_time TEXT')
        except sqlite3.OperationalError:
            pass
        
        try:
            conn.execute('ALTER TABLE tasks ADD COLUMN category_id INTEGER')
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
        except Exception as e:
            print(f"Warning: Could not create default categories: {e}")
        
        conn.commit()
        conn.close()
        print("Database initialized successfully")
        
    except Exception as e:
        print(f"Database initialization error: {e}")

# 初期化フラグ
_initialized = False

def ensure_initialization():
    global _initialized
    if not _initialized:
        init_db()
        _initialized = True

@app.before_request
def before_request():
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
            session.pop('guest_mode', None)
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
            conn.execute('INSERT INTO users (username, email, password_hash) VALUES (?, ?, ?)', (username, email, password_hash))
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
    session.clear()
    session['guest_mode'] = True
    flash('ゲストモードで開始しました。データは保存されません。', 'info')
    return redirect(url_for('index'))

@app.route('/logout')
def logout():
    session.clear()
    flash('ログアウトしました。', 'info')
    return redirect(url_for('landing'))

@app.route('/dashboard')
@app.route('/index')
@login_required
def index():
    user_id = get_current_user_id()
    
    if user_id:
        conn = get_db_connection()
        tasks = conn.execute('SELECT t.*, c.color as category_color FROM tasks t LEFT JOIN categories c ON t.category_id = c.id WHERE t.user_id = ? ORDER BY t.completed, t.due_date ASC', (user_id,)).fetchall()
        conn.close()
    else:
        tasks = session.get('guest_tasks', [])
        
        if tasks:
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
    
    is_guest = 'guest_mode' in session
    return render_template('index.html', tasks=tasks, is_guest=is_guest)

@app.route('/add', methods=['GET', 'POST'])
@login_required
def add_task():
    if request.method == 'POST':
        title = request.form['title']
        description = request.form.get('description', '')
        due_date = request.form.get('due_date', '')
        due_time = request.form.get('due_time', '')
        category_id = request.form.get('category_id', '')
        new_category = request.form.get('new_category', '')
        priority = request.form.get('priority', 'medium')
        
        user_id = get_current_user_id()
        final_category_id = None
        final_category_name = ''
        
        try:
            if category_id == 'other' and new_category:
                if user_id:
                    conn = get_db_connection()
                    try:
                        cursor = conn.execute('INSERT INTO categories (name, color, user_id) VALUES (?, ?, ?)', (new_category, DEFAULT_COLORS[0], user_id))
                        final_category_id = cursor.lastrowid
                        final_category_name = new_category
                        conn.commit()
                        conn.close()
                    except sqlite3.IntegrityError:
                        conn.close()
                        flash('同じ名前のカテゴリが既に存在します。', 'error')
                        return redirect(url_for('add_task'))
                else:
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
            
            elif category_id and category_id != 'other':
                final_category_id = int(category_id)
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
            
            if user_id:
                conn = get_db_connection()
                conn.execute('INSERT INTO tasks (title, description, due_date, due_time, category, category_id, priority, user_id) VALUES (?, ?, ?, ?, ?, ?, ?, ?)', (title, description, due_date, due_time, final_category_name, final_category_id, priority, user_id))
                conn.commit()
                conn.close()
            else:
                if 'guest_tasks' not in session:
                    session['guest_tasks'] = []
                
                existing_ids = [task['id'] for task in session['guest_tasks']]
                new_id = max(existing_ids, default=0) + 1
                
                new_task = {'id': new_id, 'title': title, 'description': description, 'due_date': due_date, 'due_time': due_time, 'category': final_category_name, 'category_id': final_category_id, 'priority': priority, 'completed': 0, 'created_at': datetime.now().isoformat()}
                
                guest_tasks = session['guest_tasks'].copy()
                guest_tasks.append(new_task)
                session['guest_tasks'] = guest_tasks
                session.modified = True
            
            flash('タスクを追加しました！', 'success')
            return redirect(url_for('index'))
            
        except Exception as e:
            print(f"Add task error: {e}")
            flash(f'タスクの追加に失敗しました: {str(e)}', 'error')
    
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
    
    return render_template('add_task.html', categories=categories)

@app.route('/complete/<int:id>')
@login_required
def complete_task(id):
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

@app.route('/delete/<int:id>')
@login_required
def delete_task(id):
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
            
            categories_with_counts = conn.execute('SELECT c.id, c.name, c.color, COUNT(t.id) as task_count FROM categories c LEFT JOIN tasks t ON c.id = t.category_id AND t.user_id = ? WHERE c.user_id IS NULL OR c.user_id = ? GROUP BY c.id, c.name, c.color ORDER BY c.user_id IS NULL DESC, c.name ASC', (user_id, user_id)).fetchall()
            
            conn.close()
            
            categories = []
            task_counts = {}
            for cat in categories_with_counts:
                categories.append({'id': cat['id'], 'name': cat['name'], 'color': cat['color']})
                task_counts[cat['name']] = cat['task_count']
        
        is_guest = 'guest_mode' in session
        
        return render_template('categories.html', categories=categories, task_counts=task_counts, default_colors=DEFAULT_COLORS, is_guest=is_guest)
    
    except Exception as e:
        print(f"Categories route error: {e}")
        flash(f'カテゴリの取得に失敗しました: {str(e)}', 'error')
        return render_template('categories.html', categories=[], task_counts={}, default_colors=DEFAULT_COLORS, is_guest='guest_mode' in session)

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
                flash('同じ名前のカテゴリが既に存在します。', 'error')
    
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
            
            # ゲストタスクからカテゴリ統計を計算
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
            
            # 優先度統計を計算
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
        # エラーが発生した場合はデフォルト値で表示
        return render_template('analytics.html', 
                             total_tasks=0, 
                             completed_tasks=0, 
                             incomplete_tasks=0, 
                             category_stats={}, 
                             priority_stats={}, 
                             is_guest='guest_mode' in session,
                             error_message=f"データの読み込みに失敗しました: {str(e)}")

# チャート生成エンドポイント
@app.route('/chart/<chart_type>')
@login_required
def generate_chart(chart_type):
    try:
        user_id = get_current_user_id()
        
        if chart_type == 'category_pie':
            data = get_category_data(user_id)
            image_data = create_pie_chart(data, "カテゴリ別タスク分布")
        elif chart_type == 'priority_bar':
            data = get_priority_data(user_id)
            image_data = create_bar_chart(data, "優先度別タスク分布")
        elif chart_type == 'completion_status':
            data = get_completion_data(user_id)
            image_data = create_pie_chart(data, "タスク完了状況")
        elif chart_type == 'category_stacked':
            data = get_category_data(user_id)
            image_data = create_bar_chart(data, "カテゴリ別詳細")
        else:
            return create_no_data_response("不明なチャートタイプです")
        
        return Response(image_data, mimetype='image/png')
        
    except Exception as e:
        print(f"Chart generation error: {e}")
        return Response(create_simple_error_image(), mimetype='image/png')

def get_category_data(user_id):
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
            ''', (user_id, user_id)).fetchall()
            conn.close()
            
            return [{'name': row['name'], 'count': row['count'], 'color': row['color']} for row in data]
        else:
            # ゲストモード
            guest_tasks = session.get('guest_tasks', [])
            category_counts = {}
            for task in guest_tasks:
                category = task.get('category', 'Uncategorized')
                category_counts[category] = category_counts.get(category, 0) + 1
            
            return [{'name': cat, 'count': count, 'color': '#6c757d'} 
                   for cat, count in category_counts.items()]
        
    except Exception as e:
        print(f"Category data error: {e}")
        return []

def get_priority_data(user_id):
    try:
        if user_id:
            conn = get_db_connection()
            data = conn.execute('''
                SELECT priority, COUNT(*) as count 
                FROM tasks WHERE user_id = ? 
                GROUP BY priority
            ''', (user_id,)).fetchall()
            conn.close()
            
            return [{'priority': row['priority'], 'count': row['count']} for row in data]
        else:
            # ゲストモード
            guest_tasks = session.get('guest_tasks', [])
            priority_counts = {}
            for task in guest_tasks:
                priority = task.get('priority', 'medium')
                priority_counts[priority] = priority_counts.get(priority, 0) + 1
            
            return [{'priority': pri, 'count': count} 
                   for pri, count in priority_counts.items()]
        
    except Exception as e:
        print(f"Priority data error: {e}")
        return []

def get_completion_data(user_id):
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
        
        return [
            {'name': 'Completed', 'count': completed, 'color': '#28a745'},
            {'name': 'Incomplete', 'count': incomplete, 'color': '#ffc107'}
        ]
        
    except Exception as e:
        print(f"Completion data error: {e}")
        return []

def create_pie_chart(data, title):
    try:
        filtered_data = [item for item in data if item['count'] > 0]
        if not filtered_data:
            return create_no_data_image(title)
        
        labels = [item['name'] for item in filtered_data]
        sizes = [item['count'] for item in filtered_data]
        colors = [item.get('color', '#6c757d') for item in filtered_data]
        
        fig, ax = plt.subplots(figsize=(8, 6))
        
        # 日本語ではなく英語ラベルを使用（Render対応）
        english_labels = [f"Category {i+1}" for i in range(len(labels))]
        wedges, texts, autotexts = ax.pie(sizes, labels=english_labels, colors=colors, 
                                        autopct='%1.1f%%', startangle=90, textprops={'fontsize': 10})
        ax.set_title('Task Distribution by Category', fontsize=14, fontweight='bold', pad=20)
        
        for autotext in autotexts:
            autotext.set_color('white')
            autotext.set_fontweight('bold')
        
        plt.tight_layout()
        
        img = io.BytesIO()
        plt.savefig(img, format='png', bbox_inches='tight', facecolor='white', dpi=100)
        img.seek(0)
        image_data = img.getvalue()
        plt.close()
        
        return image_data
        
    except Exception as e:
        print(f"Pie chart generation error: {e}")
        return create_simple_error_image()

def create_bar_chart(data, title):
    try:
        if not data:
            return create_simple_error_image()
        
        labels = [item['priority'] for item in data]
        values = [item['count'] for item in data]
        
        # 英語ラベルに変換
        english_labels = []
        for label in labels:
            if label == 'high':
                english_labels.append('High')
            elif label == 'medium':
                english_labels.append('Medium')
            elif label == 'low':
                english_labels.append('Low')
            else:
                english_labels.append(label)
        
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
        
        fig, ax = plt.subplots(figsize=(8, 6))
        bars = ax.bar(english_labels, values, color=colors)
        
        ax.set_title('Task Distribution by Priority', fontsize=14, fontweight='bold', pad=20)
        ax.set_xlabel('Priority', fontsize=12)
        ax.set_ylabel('Number of Tasks', fontsize=12)
        
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
        
        return image_data
        
    except Exception as e:
        print(f"Bar chart generation error: {e}")
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
        return b''

def create_no_data_image(title):
    try:
        fig, ax = plt.subplots(figsize=(8, 6))
        
        message = 'データがありません'
        if font_prop:
            ax.text(0.5, 0.5, message, horizontalalignment='center', verticalalignment='center', transform=ax.transAxes, fontsize=16, color='gray', fontproperties=font_prop)
            ax.set_title(title, fontproperties=font_prop, fontsize=14)
        else:
            ax.text(0.5, 0.5, 'No Data Available', horizontalalignment='center', verticalalignment='center', transform=ax.transAxes, fontsize=16, color='gray')
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
    image_data = create_no_data_image(message)
    return Response(image_data, mimetype='image/png')

@app.route('/test')
def test():
    try:
        conn = get_db_connection()
        tables = conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        
        table_info = {}
        for table in tables:
            count = conn.execute(f"SELECT COUNT(*) FROM {table['name']}").fetchone()[0]
            table_info[table['name']] = count
        
        conn.close()
        
        return {
            "status": "OK",
            "tables": table_info,
            "session": dict(session),
            "font_available": font_prop is not None
        }
    except Exception as e:
        return {"status": "error", "error": str(e)}, 500

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
    return "Internal Server Error", 500

@app.errorhandler(404)
def not_found(error):
    return "Page Not Found", 404

ensure_initialization()

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=os.environ.get('FLASK_ENV') == 'development')
