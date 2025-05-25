# -*- coding: utf-8 -*-
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, session
import sqlite3
from datetime import datetime, timedelta
import os
import json
from collections import defaultdict
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps

import matplotlib
matplotlib.use('Agg')
matplotlib.rcParams['font.family'] = 'DejaVu Sans'
import matplotlib.pyplot as plt
import io
import base64

app = Flask(__name__)

app.secret_key = os.environ.get('SECRET_KEY', 'your-secret-key-here-change-in-production')
app.config['SESSION_COOKIE_SECURE'] = os.environ.get('FLASK_ENV') == 'production'
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'

DB_PATH = os.environ.get('DATABASE_URL', 'tasks.db')

DEFAULT_COLORS = ["#F82A1B", "#FF9800", "#FFDD02", "#53EB38", "#03A9F4", "#2635FF", "#902DEE", "#FF80CC", "#795548", "#7DA0B2"]

def get_db_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def get_current_user_id():
    return session.get('user_id') if 'guest_mode' not in session else None

def init_db():
    try:
        db_dir = os.path.dirname(DB_PATH)
        if db_dir and not os.path.exists(db_dir):
            os.makedirs(db_dir, exist_ok=True)
            
        conn = get_db_connection()
        
        conn.execute('CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT UNIQUE NOT NULL, email TEXT UNIQUE NOT NULL, password_hash TEXT NOT NULL, created_at TEXT DEFAULT CURRENT_TIMESTAMP)')
        conn.execute('CREATE TABLE IF NOT EXISTS categories (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL UNIQUE, color TEXT NOT NULL DEFAULT "#007bff", user_id INTEGER, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, FOREIGN KEY (user_id) REFERENCES users (id))')
        conn.execute('CREATE TABLE IF NOT EXISTS tasks (id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT NOT NULL, description TEXT, due_date TEXT, due_time TEXT, category TEXT, category_id INTEGER, priority TEXT DEFAULT "medium", completed INTEGER DEFAULT 0, user_id INTEGER, created_at TEXT DEFAULT CURRENT_TIMESTAMP, FOREIGN KEY (user_id) REFERENCES users (id), FOREIGN KEY (category_id) REFERENCES categories (id))')
        
        try:
            conn.execute('ALTER TABLE tasks ADD COLUMN due_time TEXT')
        except sqlite3.OperationalError:
            pass
        
        try:
            conn.execute('ALTER TABLE tasks ADD COLUMN category_id INTEGER')
        except sqlite3.OperationalError:
            pass
        
        try:
            existing_global_categories = conn.execute('SELECT COUNT(*) FROM categories WHERE user_id IS NULL').fetchone()[0]
            if existing_global_categories == 0:
                default_categories = [('Work', DEFAULT_COLORS[0], None), ('Personal', DEFAULT_COLORS[1], None), ('Study', DEFAULT_COLORS[2], None)]
                conn.executemany('INSERT INTO categories (name, color, user_id) VALUES (?, ?, ?)', default_categories)
        except Exception as e:
            print(f"Warning: Could not create default categories: {e}")
        
        conn.commit()
        conn.close()
        print("Database initialized successfully")
        
    except Exception as e:
        print(f"Database initialization error: {e}")

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
            flash('Login successful!', 'success')
            return redirect(url_for('index'))
        else:
            flash('Invalid username or password.', 'error')
    
    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        email = request.form['email']
        password = request.form['password']
        confirm_password = request.form['confirm_password']
        
        if password != confirm_password:
            flash('Passwords do not match.', 'error')
            return render_template('register.html')
        
        if len(password) < 6:
            flash('Password must be at least 6 characters.', 'error')
            return render_template('register.html')
        
        password_hash = generate_password_hash(password)
        
        conn = get_db_connection()
        try:
            conn.execute('INSERT INTO users (username, email, password_hash) VALUES (?, ?, ?)', (username, email, password_hash))
            conn.commit()
            conn.close()
            flash('Account created! Please login.', 'success')
            return redirect(url_for('login'))
        except sqlite3.IntegrityError:
            conn.close()
            flash('Username or email already exists.', 'error')
    
    return render_template('register.html')

@app.route('/guest')
def guest_mode():
    session.clear()
    session['guest_mode'] = True
    flash('Started in guest mode. Data is stored in session only.', 'info')
    return redirect(url_for('index'))

@app.route('/logout')
def logout():
    session.clear()
    flash('Logged out.', 'info')
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
                        flash('Category with same name already exists.', 'error')
                        return redirect(url_for('add_task'))
                else:
                    if 'guest_categories' not in session:
                        session['guest_categories'] = []
                    
                    guest_categories = session.get('guest_categories', [])
                    if any(cat['name'] == new_category for cat in guest_categories):
                        flash('Category with same name already exists.', 'error')
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
            
            flash('Task added successfully!', 'success')
            return redirect(url_for('index'))
            
        except Exception as e:
            print(f"Add task error: {e}")
            flash(f'Failed to add task: {str(e)}', 'error')
    
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

@app.route('/edit/<int:id>', methods=['GET', 'POST'])
@login_required
def edit_task(id):
    user_id = get_current_user_id()
    
    if user_id:
        conn = get_db_connection()
        task = conn.execute('SELECT * FROM tasks WHERE id = ? AND user_id = ?', (id, user_id)).fetchone()
        
        if task is None:
            conn.close()
            flash('Task not found!', 'error')
            return redirect(url_for('index'))
        
        if request.method == 'POST':
            title = request.form['title']
            description = request.form.get('description', '')
            due_date = request.form.get('due_date', '')
            due_time = request.form.get('due_time', '')
            category_id = request.form.get('category_id', '')
            priority = request.form.get('priority', 'medium')
            
            category_name = ''
            if category_id:
                cat = conn.execute('SELECT name FROM categories WHERE id = ?', (category_id,)).fetchone()
                category_name = cat['name'] if cat else ''
            
            conn.execute('UPDATE tasks SET title = ?, description = ?, due_date = ?, due_time = ?, category = ?, category_id = ?, priority = ? WHERE id = ? AND user_id = ?', (title, description, due_date, due_time, category_name, category_id, priority, id, user_id))
            conn.commit()
            conn.close()
            
            flash('Task updated successfully!', 'success')
            return redirect(url_for('index'))
        
        categories = conn.execute('SELECT * FROM categories WHERE user_id IS NULL OR user_id = ? ORDER BY user_id IS NULL DESC, name ASC', (user_id,)).fetchall()
        conn.close()
    else:
        guest_tasks = session.get('guest_tasks', [])
        task = next((t for t in guest_tasks if t['id'] == id), None)
        
        if task is None:
            flash('Task not found!', 'error')
            return redirect(url_for('index'))
        
        conn = get_db_connection()
        db_categories = conn.execute('SELECT * FROM categories WHERE user_id IS NULL ORDER BY name').fetchall()
        conn.close()
        
        categories = list(db_categories)
        categories.extend(session.get('guest_categories', []))
        
        if request.method == 'POST':
            title = request.form['title']
            description = request.form.get('description', '')
            due_date = request.form.get('due_date', '')
            due_time = request.form.get('due_time', '')
            category_id = request.form.get('category_id', '')
            priority = request.form.get('priority', 'medium')
            
            category_name = ''
            if category_id:
                for cat in categories:
                    if str(cat['id']) == str(category_id):
                        category_name = cat['name']
                        break
            
            guest_tasks = session['guest_tasks'].copy()
            for i, t in enumerate(guest_tasks):
                if t['id'] == id:
                    guest_tasks[i].update({'title': title, 'description': description, 'due_date': due_date, 'due_time': due_time, 'category': category_name, 'category_id': int(category_id) if category_id else None, 'priority': priority})
                    break
            
            session['guest_tasks'] = guest_tasks
            session.modified = True
            flash('Task updated successfully!', 'success')
            return redirect(url_for('index'))
    
    return render_template('edit_task.html', task=task, categories=categories)

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
            
            status_text = "completed" if new_status else "pending"
            flash(f'Task marked as {status_text}!', 'success')
        else:
            conn.close()
            flash('Task not found!', 'error')
    else:
        guest_tasks = session.get('guest_tasks', [])
        for task in guest_tasks:
            if task['id'] == id:
                task['completed'] = 0 if task['completed'] else 1
                session.modified = True
                status_text = "completed" if task['completed'] else "pending"
                flash(f'Task marked as {status_text}!', 'success')
                break
        else:
            flash('Task not found!', 'error')
    
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
            flash('Task deleted successfully!', 'success')
        else:
            flash('Task not found!', 'error')
        
        conn.close()
    else:
        guest_tasks = session.get('guest_tasks', [])
        original_length = len(guest_tasks)
        session['guest_tasks'] = [task for task in guest_tasks if task['id'] != id]
        
        if len(session['guest_tasks']) < original_length:
            session.modified = True
            flash('Task deleted successfully!', 'success')
        else:
            flash('Task not found!', 'error')
    
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
        flash(f'Failed to get categories: {str(e)}', 'error')
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
            flash('Please enter category name.', 'error')
            return redirect(url_for('categories'))
        
        if 'guest_mode' in session:
            if 'guest_categories' not in session:
                session['guest_categories'] = []
            
            guest_categories = session.get('guest_categories', [])
            if any(cat['name'] == name for cat in guest_categories):
                flash('Category with same name already exists.', 'error')
                return redirect(url_for('categories'))
            
            new_cat_id = max([cat['id'] for cat in guest_categories], default=1000) + 1
            new_category = {'id': new_cat_id, 'name': name, 'color': color, 'user_id': None}
            
            guest_categories.append(new_category)
            session['guest_categories'] = guest_categories
            session.modified = True
            flash('Category added (guest mode).', 'success')
        else:
            conn = get_db_connection()
            try:
                conn.execute('INSERT INTO categories (name, color, user_id) VALUES (?, ?, ?)', (name, color, session.get('user_id')))
                conn.commit()
                conn.close()
                flash('Category added successfully.', 'success')
            except sqlite3.IntegrityError:
                conn.close()
                flash('Category with same name already exists.', 'error')
    
    except Exception as e:
        print(f"Add category error: {e}")
        flash(f'Failed to add category: {str(e)}', 'error')
    
    return redirect(url_for('categories'))

@app.route('/delete_category/<int:category_id>', methods=['POST'])
@login_required
def delete_category(category_id):
    try:
        if 'guest_mode' in session:
            guest_categories = session.get('guest_categories', [])
            session['guest_categories'] = [cat for cat in guest_categories if cat['id'] != category_id]
            session.modified = True
            flash('Category deleted (guest mode).', 'success')
        else:
            conn = get_db_connection()
            user_id = session.get('user_id')
            
            result = conn.execute('DELETE FROM categories WHERE id = ? AND user_id = ?', (category_id, user_id))
            
            if result.rowcount > 0:
                conn.commit()
                flash('Category deleted successfully.', 'success')
            else:
                flash('Cannot delete. Default categories or other users categories cannot be deleted.', 'error')
            
            conn.close()
    
    except Exception as e:
        print(f"Delete category error: {e}")
        flash(f'Failed to delete category: {str(e)}', 'error')
    
    return redirect(url_for('categories'))

@app.route('/analytics')
@login_required
def analytics():
    user_id = get_current_user_id()
    
    try:
        if user_id:
            conn = get_db_connection()
            
            total_tasks = conn.execute('SELECT COUNT(*) FROM tasks WHERE user_id = ?', (user_id,)).fetchone()[0]
            completed_tasks = conn.execute('SELECT COUNT(*) FROM tasks WHERE user_id = ? AND completed = 1', (user_id,)).fetchone()[0]
            incomplete_tasks = total_tasks - completed_tasks
            
            # カテゴリ別統計（詳細）
            category_data = conn.execute('''
                SELECT c.name, c.color,
                       COUNT(t.id) as total,
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
            
            # 優先度別統計
            priority_data = conn.execute('''
                SELECT priority,
                       COUNT(*) as total,
                       SUM(CASE WHEN completed = 1 THEN 1 ELSE 0 END) as completed
                FROM tasks 
                WHERE user_id = ?
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
            # ゲストモード
            guest_tasks = session.get('guest_tasks', [])
            total_tasks = len(guest_tasks)
            completed_tasks = sum(1 for task in guest_tasks if task.get('completed'))
            incomplete_tasks = total_tasks - completed_tasks
            
            # カテゴリ別統計
            category_counts = {}
            category_completed = {}
            for task in guest_tasks:
                category = task.get('category', 'Uncategorized')
                category_counts[category] = category_counts.get(category, 0) + 1
                if task.get('completed'):
                    category_completed[category] = category_completed.get(category, 0) + 1
            
            category_stats = {}
            for category, total in category_counts.items():
                category_stats[category] = {
                    'total': total,
                    'completed': category_completed.get(category, 0),
                    'color': '#6c757d'  # デフォルト色
                }
            
            # 優先度別統計
            priority_counts = {}
            priority_completed = {}
            for task in guest_tasks:
                priority = task.get('priority', 'medium')
                priority_counts[priority] = priority_counts.get(priority, 0) + 1
                if task.get('completed'):
                    priority_completed[priority] = priority_completed.get(priority, 0) + 1
            
            priority_stats = {}
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
        flash(f'Failed to get analytics data: {str(e)}', 'error')
        return render_template('analytics.html',
                             total_tasks=0,
                             completed_tasks=0,
                             incomplete_tasks=0,
                             category_stats={},
                             priority_stats={},
                             is_guest='guest_mode' in session)

# チャート生成エンドポイントを追加
@app.route('/chart/<chart_type>')
@login_required
def generate_chart(chart_type):
    user_id = get_current_user_id()
    
    try:
        if chart_type == 'category_pie':
            # カテゴリ別円グラフ
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
            else:
                guest_tasks = session.get('guest_tasks', [])
                category_counts = {}
                for task in guest_tasks:
                    category = task.get('category', 'Uncategorized')
                    category_counts[category] = category_counts.get(category, 0) + 1
                
                data = [{'name': name, 'count': count, 'color': '#6c757d'} for name, count in category_counts.items()]
            
            chart_url = create_pie_chart(data, 'Category Distribution')
            return f"data:image/png;base64,{chart_url}"
            
        elif chart_type == 'priority_bar':
            # 優先度別棒グラフ
            if user_id:
                conn = get_db_connection()
                data = conn.execute('SELECT priority, COUNT(*) as count FROM tasks WHERE user_id = ? GROUP BY priority', (user_id,)).fetchall()
                conn.close()
            else:
                guest_tasks = session.get('guest_tasks', [])
                priority_counts = {}
                for task in guest_tasks:
                    priority = task.get('priority', 'medium')
                    priority_counts[priority] = priority_counts.get(priority, 0) + 1
                data = [{'priority': k, 'count': v} for k, v in priority_counts.items()]
            
            chart_url = create_bar_chart(data, 'Priority Distribution')
            return f"data:image/png;base64,{chart_url}"
            
        else:
            return "data:image/png;base64,", 400
            
    except Exception as e:
        print(f"Chart generation error: {e}")
        return "data:image/png;base64,", 500

def create_pie_chart(data, title):
    try:
        if not data:
            return None
        
        labels = [item['name'] for item in data]
        sizes = [item['count'] for item in data]
        colors = [item.get('color', '#6c757d') for item in data]
        
        fig, ax = plt.subplots(figsize=(10, 8))
        wedges, texts, autotexts = ax.pie(sizes, labels=labels, colors=colors, autopct='%1.1f%%', startangle=90)
        
        for text in texts:
            text.set_fontsize(12)
        for autotext in autotexts:
            autotext.set_color('white')
            autotext.set_fontweight('bold')
            autotext.set_fontsize(10)
        
        ax.set_title(title, fontsize=16, fontweight='bold', pad=20)
        
        img = io.BytesIO()
        plt.savefig(img, format='png', bbox_inches='tight', facecolor='white', dpi=150)
        img.seek(0)
        chart_url = base64.b64encode(img.getvalue()).decode()
        plt.close()
        
        return chart_url
    except Exception as e:
        print(f"Pie chart generation error: {e}")
        return None

def create_bar_chart(data, title):
    try:
        if not data:
            return None
        
        labels = [item['priority'] for item in data]
        values = [item['count'] for item in data]
        
        colors = []
        for label in labels:
            if label == 'high':
                colors.append('#dc3545')
            elif label == 'medium':
                colors.append('#ffc107')
            else:
                colors.append('#17a2b8')
        
        fig, ax = plt.subplots(figsize=(10, 6))
        bars = ax.bar(labels, values, color=colors)
        
        ax.set_title(title, fontsize=16, fontweight='bold', pad=20)
        ax.set_xlabel('Priority', fontsize=12)
        ax.set_ylabel('Number of Tasks', fontsize=12)
        
        # 値をバーの上に表示
        for bar in bars:
            height = bar.get_height()
            ax.text(bar.get_x() + bar.get_width()/2., height + 0.1,
                   f'{int(height)}', ha='center', va='bottom', fontweight='bold')
        
        img = io.BytesIO()
        plt.savefig(img, format='png', bbox_inches='tight', facecolor='white', dpi=150)
        img.seek(0)
        chart_url = base64.b64encode(img.getvalue()).decode()
        plt.close()
        
        return chart_url
    except Exception as e:
        print(f"Bar chart generation error: {e}")
        return None

# エクスポート機能を追加
@app.route('/export_stats')
@login_required
def export_stats():
    user_id = get_current_user_id()
    
    try:
        if user_id:
            conn = get_db_connection()
            tasks = conn.execute('SELECT * FROM tasks WHERE user_id = ?', (user_id,)).fetchall()
            categories = conn.execute('SELECT * FROM categories WHERE user_id IS NULL OR user_id = ?', (user_id,)).fetchall()
            conn.close()
            
            export_data = {
                'tasks': [dict(task) for task in tasks],
                'categories': [dict(cat) for cat in categories],
                'exported_at': datetime.now().isoformat()
            }
        else:
            export_data = {
                'tasks': session.get('guest_tasks', []),
                'categories': session.get('guest_categories', []),
                'exported_at': datetime.now().isoformat(),
                'note': 'Guest mode data'
            }
        
        response = jsonify(export_data)
        response.headers['Content-Disposition'] = 'attachment; filename=task_stats.json'
        response.headers['Content-Type'] = 'application/json'
        return response
        
    except Exception as e:
        print(f"Export error: {e}")
        return jsonify({'error': 'Export failed'}), 500
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
