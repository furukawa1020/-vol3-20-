from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
import sqlite3
from datetime import datetime, timedelta
import os
import json
from collections import defaultdict

# matplotlib設定をインポート前に行う
import matplotlib
matplotlib.use('Agg')  # GUI不要のバックエンドを設定
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm
import io
import base64

# Create the Flask application
app = Flask(__name__)
app.secret_key = 'your-secret-key-here'

# Database setup
DB_PATH = 'tasks.db'

def get_db_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db_connection()
    conn.execute('''
    CREATE TABLE IF NOT EXISTS tasks (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT NOT NULL,
        description TEXT,
        due_date TEXT,
        category TEXT,
        priority TEXT,
        completed INTEGER DEFAULT 0,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    )
    ''')
    conn.commit()
    conn.close()

# Initialize the database
init_db()

@app.route('/')
def index():
    conn = get_db_connection()
    tasks = conn.execute('SELECT * FROM tasks ORDER BY completed, due_date ASC').fetchall()
    conn.close()
    return render_template('index.html', tasks=tasks)

@app.route('/add', methods=['GET', 'POST'])
def add_task():
    if request.method == 'POST':
        title = request.form['title']
        description = request.form.get('description', '')
        
        due_date_str = request.form.get('due_date', '')
        due_date = None
        if due_date_str:
            try:
                # Store date as string in the database
                due_date = due_date_str
            except ValueError:
                flash('Invalid date format. Please use YYYY-MM-DD.', 'error')
                return redirect(url_for('add_task'))
        
        category = request.form.get('category', '')
        priority = request.form.get('priority', 'medium')
        
        conn = get_db_connection()
        conn.execute('INSERT INTO tasks (title, description, due_date, category, priority) VALUES (?, ?, ?, ?, ?)',
                    (title, description, due_date, category, priority))
        conn.commit()
        conn.close()
        
        flash('Task added successfully!', 'success')
        return redirect(url_for('index'))
    
    return render_template('add_task.html')

@app.route('/edit/<int:id>', methods=['GET', 'POST'])
def edit_task(id):
    conn = get_db_connection()
    task = conn.execute('SELECT * FROM tasks WHERE id = ?', (id,)).fetchone()
    
    if task is None:
        conn.close()
        flash('Task not found!', 'error')
        return redirect(url_for('index'))
    
    if request.method == 'POST':
        title = request.form['title']
        description = request.form.get('description', '')
        
        due_date_str = request.form.get('due_date', '')
        due_date = None
        if due_date_str:
            try:
                # Store date as string
                due_date = due_date_str
            except ValueError:
                flash('Invalid date format. Please use YYYY-MM-DD.', 'error')
                return redirect(url_for('edit_task', id=id))
        
        category = request.form.get('category', '')
        priority = request.form.get('priority', 'medium')
        
        conn.execute('UPDATE tasks SET title = ?, description = ?, due_date = ?, category = ?, priority = ? WHERE id = ?',
                    (title, description, due_date, category, priority, id))
        conn.commit()
        conn.close()
        
        flash('Task updated successfully!', 'success')
        return redirect(url_for('index'))
    
    conn.close()
    return render_template('edit_task.html', task=task)

@app.route('/delete/<int:id>')
def delete_task(id):
    conn = get_db_connection()
    conn.execute('DELETE FROM tasks WHERE id = ?', (id,))
    conn.commit()
    conn.close()
    flash('Task deleted successfully!', 'success')
    return redirect(url_for('index'))

@app.route('/complete/<int:id>')
def complete_task(id):
    conn = get_db_connection()
    task = conn.execute('SELECT completed FROM tasks WHERE id = ?', (id,)).fetchone()
    
    if task is None:
        conn.close()
        flash('Task not found!', 'error')
        return redirect(url_for('index'))
    
    # Toggle completed status (0 -> 1, 1 -> 0)
    new_status = 0 if task['completed'] else 1
    conn.execute('UPDATE tasks SET completed = ? WHERE id = ?', (new_status, id))
    conn.commit()
    conn.close()
    return redirect(url_for('index'))

@app.route('/analytics')
def analytics():
    """統計・分析ページ"""
    conn = get_db_connection()
    tasks = conn.execute('SELECT * FROM tasks').fetchall()
    conn.close()
    
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
    
    return render_template('analytics.html', 
                         total_tasks=total_tasks,
                         completed_tasks=completed_tasks,
                         incomplete_tasks=incomplete_tasks,
                         category_stats=dict(category_stats),
                         priority_stats=dict(priority_stats))

@app.route('/chart/<chart_type>')
def generate_chart(chart_type):
    """チャート画像を生成"""
    conn = get_db_connection()
    tasks = conn.execute('SELECT * FROM tasks').fetchall()
    conn.close()
    
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

def setup_japanese_font():
    """日本語フォントの設定"""
    try:
        # Renderの環境ではフォントが制限されているため、シンプルに
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
    
    # バーに値を表示
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

@app.route('/export_stats')
def export_stats():
    """統計データをJSONでエクスポート"""
    conn = get_db_connection()
    tasks = conn.execute('SELECT * FROM tasks').fetchall()
    conn.close()
    
    # タスクデータを辞書形式に変換
    task_list = []
    for task in tasks:
        task_dict = {
            'id': task['id'],
            'title': task['title'],
            'description': task['description'],
            'due_date': task['due_date'],
            'category': task['category'],
            'priority': task['priority'],
            'completed': bool(task['completed']),
            'created_at': task['created_at']
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
