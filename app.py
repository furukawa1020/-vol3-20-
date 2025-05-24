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

def get_db_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
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
    
    # タスクテーブル（user_idを追加）
    conn.execute('''
    CREATE TABLE IF NOT EXISTS tasks (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT NOT NULL,
        description TEXT,
        due_date TEXT,
        category TEXT,
        priority TEXT,
        completed INTEGER DEFAULT 0,
        user_id INTEGER,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (user_id) REFERENCES users (id)
    )
    ''')
    
    conn.commit()
    conn.close()

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
        # 認証ユーザーのタスクのみ取得
        conn = get_db_connection()
        tasks = conn.execute('SELECT * FROM tasks WHERE user_id = ? ORDER BY completed, due_date ASC', 
                           (user_id,)).fetchall()
        conn.close()
    else:
        # ゲストモードの場合、セッション内のタスクを使用
        tasks = session.get('guest_tasks', [])
    
    is_guest = 'guest_mode' in session
    return render_template('index.html', tasks=tasks, is_guest=is_guest)

@app.route('/add', methods=['GET', 'POST'])
@login_required
def add_task():
    if request.method == 'POST':
        title = request.form['title']
        description = request.form.get('description', '')
        due_date = request.form.get('due_date', '')
        category = request.form.get('category', '')
        priority = request.form.get('priority', 'medium')
        
        user_id = get_current_user_id()
        
        if user_id:
            # 認証ユーザーの場合、データベースに保存
            conn = get_db_connection()
            conn.execute('INSERT INTO tasks (title, description, due_date, category, priority, user_id) VALUES (?, ?, ?, ?, ?, ?)',
                        (title, description, due_date, category, priority, user_id))
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
                'category': category,
                'priority': priority,
                'completed': 0,
                'created_at': datetime.now().isoformat()
            }
            
            guest_tasks = session['guest_tasks'].copy()
            guest_tasks.append(new_task)
            session['guest_tasks'] = guest_tasks
        
        flash('タスクを追加しました！', 'success')
        return redirect(url_for('index'))
    
    return render_template('add_task.html')

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
            category = request.form.get('category', '')
            priority = request.form.get('priority', 'medium')
            
            conn.execute('UPDATE tasks SET title = ?, description = ?, due_date = ?, category = ?, priority = ? WHERE id = ? AND user_id = ?',
                        (title, description, due_date, category, priority, id, user_id))
            conn.commit()
            conn.close()
            
            flash('タスクを更新しました！', 'success')
            return redirect(url_for('index'))
        
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
            category = request.form.get('category', '')
            priority = request.form.get('priority', 'medium')
            
            # ゲストタスクを更新
            guest_tasks = session['guest_tasks'].copy()
            for i, t in enumerate(guest_tasks):
                if t['id'] == id:
                    guest_tasks[i].update({
                        'title': title,
                        'description': description,
                        'due_date': due_date,
                        'category': category,
                        'priority': priority
                    })
                    break
            
            session['guest_tasks'] = guest_tasks
            flash('タスクを更新しました！', 'success')
            return redirect(url_for('index'))
    
    return render_template('edit_task.html', task=task)

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
        tasks = conn.execute('SELECT * FROM tasks WHERE user_id = ?', (user_id,)).fetchall()
        conn.close()
    else:
        tasks = session.get('guest_tasks', [])
    
    # タスク統計の計算
    total_tasks = len(tasks)
    completed_tasks = sum(1 for task in tasks if task['completed'])
    incomplete_tasks = total_tasks - completed_tasks
    
    # カテゴリ別統計
    category_stats = defaultdict(lambda: {'total': 0, 'completed': 0})
    for task in tasks:
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
        category_counts[task['category']] += 1
    
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
        category = task['category']
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
        tasks = conn.execute('SELECT * FROM tasks WHERE user_id = ?', (user_id,)).fetchall()
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
        tasks = conn.execute('SELECT * FROM tasks WHERE user_id = ?', (user_id,)).fetchall()
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
            'category': task['category'] or '',
            'priority': task['priority'] or 'medium',
            'completed': bool(task['completed']),
            'created_at': task.get('created_at', '')
        }
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

if __name__ == '__main__':
    app.run(debug=True)
