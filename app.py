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
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm
import io
import base64

# Create the Flask application
app = Flask(__name__)
app.secret_key = 'your-secret-key-here-change-in-production'

# Database setup
DB_PATH = 'tasks.db'

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
            conn.commit()
        except sqlite3.OperationalError:
            pass
        
        try:
            conn.execute('ALTER TABLE tasks ADD COLUMN category_id INTEGER')
            conn.commit()
        except sqlite3.OperationalError:
            pass
        
        # デフォルトカテゴリの作成（グローバル）
        existing_global_categories = conn.execute('SELECT COUNT(*) FROM categories WHERE user_id IS NULL').fetchone()[0]
        if existing_global_categories == 0:
            default_categories = [
                ('仕事', DEFAULT_COLORS[0], None),
                ('個人', DEFAULT_COLORS[1], None),
                ('勉強', DEFAULT_COLORS[2], None)
            ]
            conn.executemany('INSERT INTO categories (name, color, user_id) VALUES (?, ?, ?)', default_categories)
            conn.commit()
        
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"Database initialization error: {e}")
        # エラーが発生してもアプリを継続実行
        pass

# Initialize the database
init_db()

# 認証デコレータ
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session and 'guest_mode' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

def get_current_user_id():
    """現在のユーザーIDを取得（ゲストの場合はNone）"""
    if 'guest_mode' in session:
        return None
    return session.get('user_id')

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
        # 認証ユーザーのタスクをカテゴリ情報と一緒に取得
        conn = get_db_connection()
        tasks = conn.execute('''
            SELECT tasks.*, categories.name AS category_name, categories.color AS category_color
            FROM tasks 
            LEFT JOIN categories ON tasks.category_id = categories.id
            WHERE tasks.user_id = ? 
            ORDER BY completed, due_date ASC
        ''', (user_id,)).fetchall()
        conn.close()
    else:
        # ゲストモードの場合、セッション内のタスクを使用
        tasks = session.get('guest_tasks', [])
    
    is_guest = 'guest_mode' in session
    return render_template('index.html', tasks=tasks, is_guest=is_guest)

@app.route('/categories', methods=['GET', 'POST'])
@login_required
def categories():
    if request.method == 'POST':
        name = request.form.get('name')
        color = request.form.get('color')
        
        print(f"受信データ: name={name}, color={color}")  # デバッグ用
        
        if not name or not color:
            flash('カテゴリ名と色を選択してください。', 'error')
            return redirect(url_for('categories'))
        
        try:
            if 'guest_mode' in session:
                # ゲストモード：セッションに保存
                if 'guest_categories' not in session:
                    session['guest_categories'] = []
                
                # 重複チェック
                existing_names = [cat['name'].lower() for cat in session['guest_categories']]
                if name.lower() in existing_names:
                    flash(f'カテゴリ「{name}」は既に存在します。', 'error')
                    return redirect(url_for('categories'))
                
                # カテゴリを追加
                new_category = {
                    'id': len(session['guest_categories']) + 1000,  # ゲスト用のID
                    'name': name,
                    'color': color,
                    'user_id': None
                }
                session['guest_categories'].append(new_category)
                session.modified = True
                
                print(f"ゲストカテゴリ追加: {new_category}")  # デバッグ用
                flash(f'カテゴリ「{name}」を追加しました。（ゲストモード）', 'success')
                
            else:
                # ログインユーザー：データベースに保存
                conn = get_db_connection()
                
                # 重複チェック
                existing = conn.execute(
                    'SELECT id FROM categories WHERE LOWER(name) = LOWER(?)', 
                    (name,)
                ).fetchone()
                
                if existing:
                    flash(f'カテゴリ「{name}」は既に存在します。', 'error')
                    conn.close()
                    return redirect(url_for('categories'))
                
                # カテゴリを追加
                user_id = session.get('user_id')
                cursor = conn.execute(
                    'INSERT INTO categories (name, color, user_id) VALUES (?, ?, ?)',
                    (name, color, user_id)
                )
                conn.commit()
                
                print(f"ユーザーカテゴリ追加: ID={cursor.lastrowid}")  # デバッグ用
                conn.close()
                
                flash(f'カテゴリ「{name}」を追加しました。', 'success')
                
        except Exception as e:
            print(f"Error: {e}")  # デバッグ用
            flash(f'エラーが発生しました: {str(e)}', 'error')
        
        return redirect(url_for('categories'))
    
    # GET request - カテゴリ一覧を表示
    try:
        conn = get_db_connection()
        
        if 'guest_mode' in session:
            # ゲストモード：標準カテゴリ + ゲスト作成カテゴリ
            # 標準カテゴリを取得
            db_categories = conn.execute(
                'SELECT * FROM categories WHERE user_id IS NULL ORDER BY name'
            ).fetchall()
            
            # セッションからゲストカテゴリを取得
            guest_categories = session.get('guest_categories', [])
            
            # 合成（標準カテゴリ + ゲストカテゴリ）
            categories = []
            
            # 標準カテゴリをRow形式に変換
            for cat in db_categories:
                categories.append({
                    'id': cat['id'],
                    'name': cat['name'],
                    'color': cat['color'],
                    'user_id': cat['user_id']
                })
            
            # ゲストカテゴリを追加
            for cat in guest_categories:
                categories.append(cat)
                
        else:
            # ログインユーザー：自分のカテゴリ + 標準カテゴリ
            user_id = session.get('user_id')
            db_categories = conn.execute(
                'SELECT * FROM categories WHERE user_id IS NULL OR user_id = ? ORDER BY user_id IS NULL DESC, name ASC',
                (user_id,)
            ).fetchall()
            
            categories = []
            for cat in db_categories:
                categories.append({
                    'id': cat['id'],
                    'name': cat['name'],
                    'color': cat['color'],
                    'user_id': cat['user_id']
                })
        
        print(f"取得したカテゴリ数: {len(categories)}")  # デバッグ用
        
        # カテゴリ別タスク数を取得
        categorized_tasks = {}
        for category in categories:
            if 'guest_mode' in session:
                # ゲストのタスクから検索
                guest_tasks = session.get('guest_tasks', [])
                tasks = [task for task in guest_tasks if task.get('category') == category['name']]
            else:
                # データベースから検索
                tasks = conn.execute(
                    'SELECT * FROM tasks WHERE category_id = ? OR category = ?',
                    (category['id'], category['name'])
                ).fetchall()
            
            categorized_tasks[category['name']] = tasks
        
        conn.close()
        
        # ゲストモード判定
        is_guest = 'guest_mode' in session
        
        return render_template('categories.html', 
                             categories=categories, 
                             categorized_tasks=categorized_tasks,
                             is_guest=is_guest)
    
    except Exception as e:
        print(f"GET Error: {e}")  # デバッグ用
        flash(f'データの取得に失敗しました: {str(e)}', 'error')
        return redirect(url_for('index'))

@app.route('/add', methods=['GET', 'POST'])
@login_required
def add_task():
    if request.method == 'POST':
        title = request.form['title']
        description = request.form.get('description', '')
        due_date = request.form.get('due_date', '')
        due_time = request.form.get('due_time', '')
        category = request.form.get('category', '')
        category_id = request.form.get('category_id')  # 新規追加
        priority = request.form.get('priority', 'medium')
        
        # category_idが空文字列の場合はNoneに変換
        if category_id == '':
            category_id = None
        
        user_id = get_current_user_id()
        
        if user_id:
            # 認証ユーザーの場合、データベースに保存
            conn = get_db_connection()
            conn.execute('INSERT INTO tasks (title, description, due_date, due_time, category, category_id, priority, user_id) VALUES (?, ?, ?, ?, ?, ?, ?, ?)',
                        (title, description, due_date, due_time, category, category_id, priority, user_id))
            conn.commit()
            conn.close()
        else:
            # ゲストモードの場合、セッションに保存
            if 'guest_tasks' not in session:
                session['guest_tasks'] = []
            
            # 一意のIDを生成
            existing_ids = [task['id'] for task in session['guest_tasks']]
            new_id = max(existing_ids, default=0) + 1
            
            new_task = {
                'id': new_id,
                'title': title,
                'description': description,
                'due_date': due_date,
                'due_time': due_time,
                'category': category,
                'category_id': category_id,
                'priority': priority,
                'completed': 0,
                'created_at': datetime.now().isoformat()
            }
            
            guest_tasks = session['guest_tasks'].copy()
            guest_tasks.append(new_task)
            session['guest_tasks'] = guest_tasks
        
        flash('タスクを追加しました！', 'success')
        return redirect(url_for('index'))
    
    # カテゴリ一覧を取得
    user_id = get_current_user_id()
    conn = get_db_connection()
    if user_id:
        categories = conn.execute('''
            SELECT * FROM categories 
            WHERE user_id IS NULL OR user_id = ? 
            ORDER BY user_id IS NULL DESC, name ASC
        ''', (user_id,)).fetchall()
    else:
        categories = conn.execute('SELECT * FROM categories WHERE user_id IS NULL ORDER BY name ASC').fetchall()
    conn.close()
    
    return render_template('add_task.html', categories=categories)

@app.route('/edit/<int:id>', methods=['GET', 'POST'])
@login_required
def edit_task(id):
    user_id = get_current_user_id()
    
    if user_id:
        # 認証ユーザーの場合
        conn = get_db_connection()
        task = conn.execute('SELECT * FROM tasks WHERE id = ? AND user_id = ?', (id, user_id)).fetchone()
        
        if task is None:
            conn.close()
            flash('タスクが見つかりません！', 'error')
            return redirect(url_for('index'))
        
        if request.method == 'POST':
            title = request.form['title']
            description = request.form.get('description', '')
            due_date = request.form.get('due_date', '')
            due_time = request.form.get('due_time', '')
            category = request.form.get('category', '')
            category_id = request.form.get('category_id')
            priority = request.form.get('priority', 'medium')
            
            # category_idが空文字列の場合はNoneに変換
            if category_id == '':
                category_id = None
            
            conn.execute('UPDATE tasks SET title = ?, description = ?, due_date = ?, due_time = ?, category = ?, category_id = ?, priority = ? WHERE id = ? AND user_id = ?',
                        (title, description, due_date, due_time, category, category_id, priority, id, user_id))
            conn.commit()
            
            # カテゴリ一覧を取得
            categories = conn.execute('''
                SELECT * FROM categories 
                WHERE user_id IS NULL OR user_id = ? 
                ORDER BY user_id IS NULL DESC, name ASC
            ''', (user_id,)).fetchall()
            conn.close()
            
            flash('タスクを更新しました！', 'success')
            return redirect(url_for('index'))
        
        # カテゴリ一覧を取得
        categories = conn.execute('''
            SELECT * FROM categories 
            WHERE user_id IS NULL OR user_id = ? 
            ORDER BY user_id IS NULL DESC, name ASC
        ''', (user_id,)).fetchall()
        conn.close()
    else:
        # ゲストモードの場合
        guest_tasks = session.get('guest_tasks', [])
        task = next((t for t in guest_tasks if t['id'] == id), None)
        
        if task is None:
            flash('タスクが見つかりません！', 'error')
            return redirect(url_for('index'))
        
        if request.method == 'POST':
            title = request.form['title']
            description = request.form.get('description', '')
            due_date = request.form.get('due_date', '')
            due_time = request.form.get('due_time', '')
            category = request.form.get('category', '')
            category_id = request.form.get('category_id')
            priority = request.form.get('priority', 'medium')
            
            # ゲストタスクを更新
            guest_tasks = session['guest_tasks'].copy()
            for i, t in enumerate(guest_tasks):
                if t['id'] == id:
                    guest_tasks[i].update({
                        'title': title,
                        'description': description,
                        'due_date': due_date,
                        'due_time': due_time,
                        'category': category,
                        'category_id': category_id,
                        'priority': priority
                    })
                    break
            
            session['guest_tasks'] = guest_tasks
            flash('タスクを更新しました！', 'success')
            return redirect(url_for('index'))
        
        # ゲストモード用のカテゴリ一覧
        conn = get_db_connection()
        categories = conn.execute('SELECT * FROM categories WHERE user_id IS NULL ORDER BY name ASC').fetchall()
        conn.close()
    
    return render_template('edit_task.html', task=task, categories=categories)

@app.route('/delete/<int:id>')
@login_required
def delete_task(id):
    user_id = get_current_user_id()
    
    if user_id:
        # 認証ユーザーの場合
        conn = get_db_connection()
        conn.execute('DELETE FROM tasks WHERE id = ? AND user_id = ?', (id, user_id))
        conn.commit()
        conn.close()
    else:
        # ゲストモードの場合
        guest_tasks = session.get('guest_tasks', [])
        session['guest_tasks'] = [t for t in guest_tasks if t['id'] != id]
    
    flash('タスクを削除しました！', 'success')
    return redirect(url_for('index'))

@app.route('/complete/<int:id>')
@login_required
def complete_task(id):
    user_id = get_current_user_id()
    
    if user_id:
        # 認証ユーザーの場合
        conn = get_db_connection()
        task = conn.execute('SELECT completed FROM tasks WHERE id = ? AND user_id = ?', (id, user_id)).fetchone()
        
        if task is None:
            conn.close()
            flash('タスクが見つかりません！', 'error')
            return redirect(url_for('index'))
        
        new_status = 0 if task['completed'] else 1
        conn.execute('UPDATE tasks SET completed = ? WHERE id = ? AND user_id = ?', (new_status, id, user_id))
        conn.commit()
        conn.close()
    else:
        # ゲストモードの場合
        guest_tasks = session.get('guest_tasks', [])
        guest_tasks_copy = guest_tasks.copy()
        for i, task in enumerate(guest_tasks_copy):
            if task['id'] == id:
                guest_tasks_copy[i]['completed'] = 0 if task['completed'] else 1
                break
        session['guest_tasks'] = guest_tasks_copy
    
    return redirect(url_for('index'))

@app.route('/analytics')
@login_required
def analytics():
    """統計・分析ページ"""
    user_id = get_current_user_id()
    
    if user_id:
        conn = get_db_connection()
        # カテゴリ情報も含めて取得
        tasks = conn.execute('''
            SELECT tasks.*, categories.name AS category_name, categories.color AS category_color
            FROM tasks 
            LEFT JOIN categories ON tasks.category_id = categories.id
            WHERE tasks.user_id = ?
        ''', (user_id,)).fetchall()
        conn.close()
    else:
        tasks = session.get('guest_tasks', [])
    
    # タスク統計の計算
    total_tasks = len(tasks)
    completed_tasks = sum(1 for task in tasks if task['completed'])
    incomplete_tasks = total_tasks - completed_tasks
    
    # カテゴリ別統計（新しいカテゴリシステム対応）
    category_stats = defaultdict(lambda: {'total': 0, 'completed': 0})
    for task in tasks:
        if hasattr(task, 'category_name') and task['category_name']:
            category = task['category_name']
        else:
            category = task['category'] if task['category'] else '未分類'
        
        category_stats[category]['total'] += 1
        if task['completed']:
            category_stats[category]['completed'] += 1
    
    # 優先度別統計
    priority_stats = defaultdict(lambda: {'total': 0, 'completed': 0})
    for task in tasks:
        priority = task['priority'] if task['priority'] else 'medium'
        priority_stats[priority]['total'] += 1
        if task['completed']:
            priority_stats[priority]['completed'] += 1
    
    is_guest = 'guest_mode' in session
    return render_template('analytics.html', 
                         total_tasks=total_tasks,
                         completed_tasks=completed_tasks,
                         incomplete_tasks=incomplete_tasks,
                         category_stats=dict(category_stats),
                         priority_stats=dict(priority_stats),
                         is_guest=is_guest)

def setup_japanese_font():
    """日本語フォントの設定"""
    try:
        plt.rcParams['font.family'] = 'DejaVu Sans'
        return None
    except Exception as e:
        print(f"フォント設定でエラーが発生しました: {e}")
        return None

def generate_category_pie_chart(tasks, font_prop):
    """カテゴリ別円グラフ"""
    category_counts = defaultdict(int)
    for task in tasks:
        # 新しいカテゴリシステムに対応
        if hasattr(task, 'category_name') and task['category_name']:
            category = task['category_name']
        else:
            category = task['category'] if task['category'] else '未分類'
        category_counts[category] += 1
    
    if not category_counts:
        return create_empty_chart("No data available")
    
    plt.figure(figsize=(10, 8))
    labels = list(category_counts.keys())
    sizes = list(category_counts.values())
    colors = plt.cm.Set3(range(len(labels)))
    
    plt.pie(sizes, labels=labels, colors=colors, autopct='%1.1f%%', startangle=90)
    plt.title('Category Distribution', fontsize=16)
    
    return create_chart_response()

def generate_priority_bar_chart(tasks, font_prop):
    """優先度別棒グラフ"""
    priority_counts = defaultdict(int)
    for task in tasks:
        priority_counts[task['priority']] += 1
    
    if not priority_counts:
        return create_empty_chart("No data available")
    
    plt.figure(figsize=(10, 6))
    priorities = ['high', 'medium', 'low']
    counts = [priority_counts[p] for p in priorities]
    colors = ['#FF6B6B', '#4ECDC4', '#45B7D1']
    
    bars = plt.bar(priorities, counts, color=colors)
    plt.title('Tasks by Priority', fontsize=16)
    plt.xlabel('Priority')
    plt.ylabel('Number of Tasks')
    
    for bar, count in zip(bars, counts):
        height = bar.get_height()
        plt.text(bar.get_x() + bar.get_width()/2., height,
                f'{count}', ha='center', va='bottom', fontsize=12)
    
    return create_chart_response()

def generate_completion_status_chart(tasks, font_prop):
    """完了状況の円グラフ"""
    completed = sum(1 for task in tasks if task['completed'])
    incomplete = len(tasks) - completed
    
    if completed == 0 and incomplete == 0:
        return create_empty_chart("No data available")
    
    plt.figure(figsize=(8, 8))
    labels = ['Completed', 'Incomplete']
    sizes = [completed, incomplete]
    colors = ['#4CAF50', '#FF9800']
    
    plt.pie(sizes, labels=labels, colors=colors, autopct='%1.1f%%', startangle=90)
    plt.title('Task Completion Status', fontsize=16)
    
    return create_chart_response()

def generate_category_stacked_chart(tasks, font_prop):
    """カテゴリ別積み上げ棒グラフ（完了/未完了）"""
    category_data = defaultdict(lambda: {'completed': 0, 'incomplete': 0})
    
    for task in tasks:
        # 新しいカテゴリシステムに対応
        if hasattr(task, 'category_name') and task['category_name']:
            category = task['category_name']
        else:
            category = task['category'] if task['category'] else '未分類'
            
        if task['completed']:
            category_data[category]['completed'] += 1
        else:
            category_data[category]['incomplete'] += 1
    
    if not category_data:
        return create_empty_chart("No data available")
    
    plt.figure(figsize=(12, 6))
    categories = list(category_data.keys())
    completed_counts = [category_data[cat]['completed'] for cat in categories]
    incomplete_counts = [category_data[cat]['incomplete'] for cat in categories]
    
    width = 0.6
    p1 = plt.bar(categories, completed_counts, width, label='Completed', color='#4CAF50')
    p2 = plt.bar(categories, incomplete_counts, width, bottom=completed_counts, label='Incomplete', color='#FF9800')
    
    plt.title('Completion Status by Category', fontsize=16)
    plt.xlabel('Category')
    plt.ylabel('Number of Tasks')
    plt.legend()
    plt.xticks(rotation=45)
    
    return create_chart_response()

def create_chart_response():
    """グラフをBase64エンコードしてレスポンス作成"""
    img = io.BytesIO()
    plt.tight_layout()
    plt.savefig(img, format='png', dpi=150, bbox_inches='tight')
    img.seek(0)
    
    plot_url = base64.b64encode(img.getvalue()).decode()
    plt.close()
    
    return f'data:image/png;base64,{plot_url}'

def create_empty_chart(message):
    """空のチャートを作成"""
    plt.figure(figsize=(8, 6))
    plt.text(0.5, 0.5, message, ha='center', va='center', fontsize=16)
    plt.axis('off')
    return create_chart_response()

@app.route('/chart/<chart_type>')
@login_required
def generate_chart(chart_type):
    """チャート画像を生成"""
    user_id = get_current_user_id()
    
    if user_id:
        conn = get_db_connection()
        tasks = conn.execute('''
            SELECT tasks.*, categories.name AS category_name, categories.color AS category_color
            FROM tasks 
            LEFT JOIN categories ON tasks.category_id = categories.id
            WHERE tasks.user_id = ?
        ''', (user_id,)).fetchall()
        conn.close()
    else:
        tasks = session.get('guest_tasks', [])
    
    # タスクデータをリスト形式に変換
    task_list = []
    for task in tasks:
        task_dict = {
            'title': task['title'],
            'category': task['category'] if task['category'] else '未分類',
            'priority': task['priority'] if task['priority'] else 'medium',
            'completed': bool(task['completed']),
            'due_date': task['due_date']
        }
        
        # 新しいカテゴリシステムに対応
        if hasattr(task, 'category_name') and task['category_name']:
            task_dict['category_name'] = task['category_name']
        
        task_list.append(task_dict)
    
    # matplotlib設定
    plt.style.use('default')
    font_prop = setup_japanese_font()
    
    if chart_type == 'category_pie':
        return generate_category_pie_chart(task_list, font_prop)
    elif chart_type == 'priority_bar':
        return generate_priority_bar_chart(task_list, font_prop)
    elif chart_type == 'completion_status':
        return generate_completion_status_chart(task_list, font_prop)
    elif chart_type == 'category_stacked':
        return generate_category_stacked_chart(task_list, font_prop)
    
    return '', 404

@app.route('/export_stats')
@login_required
def export_stats():
    """統計データをJSONでエクスポート"""
    user_id = get_current_user_id()
    
    if user_id:
        conn = get_db_connection()
        tasks = conn.execute('''
            SELECT tasks.*, categories.name AS category_name, categories.color AS category_color
            FROM tasks 
            LEFT JOIN categories ON tasks.category_id = categories.id
            WHERE tasks.user_id = ?
        ''', (user_id,)).fetchall()
        conn.close()
    else:
        tasks = session.get('guest_tasks', [])
    
    # タスクデータを辞書形式に変換
    task_list = []
    for task in tasks:
        task_dict = {
            'id': task['id'],
            'title': task['title'],
            'description': task['description'] or '',
            'due_date': task['due_date'] or '',
            'due_time': task.get('due_time', '') or '',
            'category': task['category'] or '',
            'priority': task['priority'] or 'medium',
            'completed': bool(task['completed']),
            'created_at': task.get('created_at', '')
        }
        
        # 新しいカテゴリ情報を追加
        if hasattr(task, 'category_name') and task['category_name']:
            task_dict['category_name'] = task['category_name']
            task_dict['category_color'] = task.get('category_color', '')
        
        task_list.append(task_dict)
    
    # 統計データを作成
    stats_data = {
        "export_date": datetime.now().isoformat(),
        "tasks": task_list,
        "summary": {
            "total_tasks": len(task_list),
            "completed_tasks": sum(1 for task in task_list if task['completed']),
            "categories": list(set(task['category'] for task in task_list if task['category'])),
            "priorities": list(set(task['priority'] for task in task_list if task['priority']))
        }
    }
    
    return jsonify(stats_data)

@app.route('/delete_category/<int:category_id>', methods=['POST'])
@login_required
def delete_category(category_id):
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
            
            # カテゴリを取得してチェック
            category = conn.execute(
                'SELECT * FROM categories WHERE id = ?', (category_id,)
            ).fetchone()
            
            if not category:
                flash('カテゴリが見つかりません。', 'error')
                conn.close()
                return redirect(url_for('categories'))
            
            # このカテゴリを使用しているタスクのカテゴリをクリア
            conn.execute(
                'UPDATE tasks SET category_id = NULL, category = NULL WHERE category_id = ? OR category = ?',
                (category_id, category['name'])
            )
            
            # カテゴリを削除
            conn.execute('DELETE FROM categories WHERE id = ?', (category_id,))
            conn.commit()
            conn.close()
            
            flash(f'カテゴリ「{category["name"]}」を削除しました。', 'success')
    
    except Exception as e:
        print(f"Delete category error: {e}")
        flash(f'カテゴリの削除に失敗しました: {str(e)}', 'error')
    
    return redirect(url_for('categories'))

# add_taskルートでカテゴリ選択を改善
@app.route('/add_task', methods=['GET', 'POST'])
@login_required
def add_task():
    if request.method == 'POST':
        title = request.form.get('title')
        description = request.form.get('description')
        due_date = request.form.get('due_date')
        due_time = request.form.get('due_time')
        priority = request.form.get('priority', 'medium')
        category_id = request.form.get('category_id')
        new_category = request.form.get('new_category')
        
        if not title:
            flash('タスクタイトルを入力してください。', 'error')
            return redirect(url_for('add_task'))
        
        try:
            # 新規カテゴリの場合
            if category_id == 'other' and new_category:
                if 'guest_mode' in session:
                    # ゲストモード：セッションに追加
                    if 'guest_categories' not in session:
                        session['guest_categories'] = []
                    
                    # 新しいカテゴリを作成
                    new_cat_id = len(session['guest_categories']) + 1000
                    new_cat = {
                        'id': new_cat_id,
                        'name': new_category,
                        'color': '#007bff',  # デフォルト色
                        'user_id': None
                    }
                    session['guest_categories'].append(new_cat)
                    session.modified = True
                    category_name = new_category
                else:
                    # データベースに追加
                    conn = get_db_connection()
                    cursor = conn.execute(
                        'INSERT INTO categories (name, color, user_id) VALUES (?, ?, ?)',
                        (new_category, '#007bff', session.get('user_id'))
                    )
                    category_id = cursor.lastrowid
                    category_name = new_category
                    conn.commit()
                    conn.close()
            
            # 既存カテゴリの場合
            elif category_id and category_id != 'other':
                if 'guest_mode' in session:
                    # ゲストモード：カテゴリ名を取得
                    all_categories = []
                    # デフォルトカテゴリ
                    conn = get_db_connection()
                    db_cats = conn.execute('SELECT * FROM categories WHERE user_id IS NULL').fetchall()
                    all_categories.extend([{'id': cat['id'], 'name': cat['name'], 'color': cat['color']} for cat in db_cats])
                    conn.close()
                    # ゲストカテゴリ
                    all_categories.extend(session.get('guest_categories', []))
                    
                    selected_cat = next((cat for cat in all_categories if str(cat['id']) == str(category_id)), None)
                    category_name = selected_cat['name'] if selected_cat else None
                else:
                    # データベースからカテゴリ名を取得
                    conn = get_db_connection()
                    cat = conn.execute('SELECT name FROM categories WHERE id = ?', (category_id,)).fetchone()
                    category_name = cat['name'] if cat else None
                    conn.close()
            else:
                category_name = None
            
            # タスクを追加
            if 'guest_mode' in session:
                # ゲストモード：セッションに保存
                if 'guest_tasks' not in session:
                    session['guest_tasks'] = []
                
                task = {
                    'id': len(session['guest_tasks']) + 1,
                    'title': title,
                    'description': description,
                    'due_date': due_date,
                    'due_time': due_time,
                    'priority': priority,
                    'category': category_name,
                    'completed': False,
                    'created_at': datetime.now().isoformat()
                }
                session['guest_tasks'].append(task)
                session.modified = True
            else:
                # データベースに保存
                conn = get_db_connection()
                conn.execute('''
                    INSERT INTO tasks (title, description, due_date, due_time, priority, category_id, category, user_id)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ''', (title, description, due_date, due_time, priority, category_id, category_name, session.get('user_id')))
                conn.commit()
                conn.close()
            
            flash('タスクを追加しました。', 'success')
            return redirect(url_for('index'))
        
        except Exception as e:
            print(f"Add task error: {e}")
            flash(f'タスクの追加に失敗しました: {str(e)}', 'error')
    
    # GET request：カテゴリ一覧を取得
    try:
        if 'guest_mode' in session:
            # ゲストモード
            conn = get_db_connection()
            db_categories = conn.execute('SELECT * FROM categories WHERE user_id IS NULL ORDER BY name').fetchall()
            conn.close()
            
            categories = [{'id': cat['id'], 'name': cat['name'], 'color': cat['color']} for cat in db_categories]
            categories.extend(session.get('guest_categories', []))
        else:
            # ログインユーザー
            conn = get_db_connection()
            user_id = session.get('user_id')
            db_categories = conn.execute(
                'SELECT * FROM categories WHERE user_id IS NULL OR user_id = ? ORDER BY user_id IS NULL DESC, name ASC',
                (user_id,)
            ).fetchall()
            conn.close()
            
            categories = [{'id': cat['id'], 'name': cat['name'], 'color': cat['color']} for cat in db_categories]
        
        return render_template('add_task.html', categories=categories)
    
    except Exception as e:
        print(f"Get categories error: {e}")
        flash(f'カテゴリの取得に失敗しました: {str(e)}', 'error')
        return render_template('add_task.html', categories=[])
