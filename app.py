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
    
    # タスクテーブル（due_timeを追加）
    conn.execute('''
    CREATE TABLE IF NOT EXISTS tasks (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT NOT NULL,
        description TEXT,
        due_date TEXT,
        due_time TEXT,
        category TEXT,
        priority TEXT,
        completed INTEGER DEFAULT 0,
        user_id INTEGER,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (user_id) REFERENCES users (id)
    )
    ''')
    
    # 既存のテーブルにdue_timeカラムを追加（既存データ対応）
    try:
        conn.execute('ALTER TABLE tasks ADD COLUMN due_time TEXT')
        conn.commit()
    except sqlite3.OperationalError:
        # カラムが既に存在する場合は無視
        pass
    
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
        due_time = request.form.get('due_time', '')  # 新しく追加
        category = request.form.get('category', '')
        priority = request.form.get('priority', 'medium')
        
        user_id = get_current_user_id()
        
        if user_id:
            # 認証ユーザーの場合、データベースに保存
            conn = get_db_connection()
            conn.execute('INSERT INTO tasks (title, description, due_date, due_time, category, priority, user_id) VALUES (?, ?, ?, ?, ?, ?, ?)',
                        (title, description, due_date, due_time, category, priority, user_id))
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
                'due_time': due_time,  # 新しく追加
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
            due_time = request.form.get('due_time', '')  # 新しく追加
            category = request.form.get('category', '')
            priority = request.form.get('priority', 'medium')
            
            conn.execute('UPDATE tasks SET title = ?, description = ?, due_date = ?, due_time = ?, category = ?, priority = ? WHERE id = ? AND user_id = ?',
                        (title, description, due_date, due_time, category, priority, id, user_id))
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
            due_time = request.form.get('due_time', '')  # 新しく追加
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
                        'due_time': due_time,  # 新しく追加
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

if __name__ == '__main__':
    app.run(debug=True)
