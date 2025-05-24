from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
import sqlite3
from datetime import datetime, timedelta
import os
import json
from collections import defaultdict
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

def generate_category_pie_chart(tasks, font_prop):
    """カテゴリ別円グラフ"""
    category_counts = defaultdict(int)
    for task in tasks:
        category_counts[task['category']] += 1
    
    if not category_counts:
        return create_empty_chart("データがありません")
    
    plt.figure(figsize=(10, 8))
    labels = list(category_counts.keys())
    sizes = list(category_counts.values())
    colors = plt.cm.Set3(range(len(labels)))
    
    plt.pie(sizes, labels=labels, colors=colors, autopct='%1.1f%%', startangle=90)
    plt.title('カテゴリ別タスク分布', fontproperties=font_prop, fontsize=16)
    
    return create_chart_response()

def generate_priority_bar_chart(tasks, font_prop):
    """優先度別棒グラフ"""
    priority_counts = defaultdict(int)
    for task in tasks:
        priority_counts[task['priority']] += 1
    
    if not priority_counts:
        return create_empty_chart("データがありません")
    
    plt.figure(figsize=(10, 6))
    priorities = ['high', 'medium', 'low']
    counts = [priority_counts[p] for p in priorities]
    colors = ['#FF6B6B', '#4ECDC4', '#45B7D1']
    
    bars = plt.bar(priorities, counts, color=colors)
    plt.title('優先度別タスク数', fontproperties=font_prop, fontsize=16)
    plt.xlabel('優先度', fontproperties=font_prop)
    plt.ylabel('タスク数', fontproperties=font_prop)
    
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
        return create_empty_chart("データがありません")
    
    plt.figure(figsize=(8, 8))
    labels = ['完了', '未完了']
    sizes = [completed, incomplete]
    colors = ['#4CAF50', '#FF9800']
    
    plt.pie(sizes, labels=labels, colors=colors, autopct='%1.1f%%', startangle=90)
    plt.title('タスク完了状況', fontproperties=font_prop, fontsize=16)
    
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
        return create_empty_chart("データがありません")
    
    plt.figure(figsize=(12, 6))
    categories = list(category_data.keys())
    completed_counts = [category_data[cat]['completed'] for cat in categories]
    incomplete_counts = [category_data[cat]['incomplete'] for cat in categories]
    
    width = 0.6
    p1 = plt.bar(categories, completed_counts, width, label='完了', color='#4CAF50')
    p2 = plt.bar(categories, incomplete_counts, width, bottom=completed_counts, label='未完了', color='#FF9800')
    
    plt.title('カテゴリ別完了状況', fontproperties=font_prop, fontsize=16)
    plt.xlabel('カテゴリ', fontproperties=font_prop)
    plt.ylabel('タスク数', fontproperties=font_prop)
    plt.legend()
    
    if font_prop:
        plt.xticks(fontproperties=font_prop, rotation=45)
        plt.yticks(fontproperties=font_prop)
    
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

# CLI用の定数
TASK_FILE = 'tasks.json'
RESET = "\033[0m"
CATEGORY_COLORS = [
    "\033[38;2;255;99;132m",   # red
    "\033[38;2;255;159;64m",   # orange
    "\033[38;2;255;206;86m",   # yellow
    "\033[38;2;54;162;235m",   # blue
    "\033[38;2;153;102;255m",  # purple
]

# グラフ描画用の関数
def setup_japanese_font():
    """日本語フォントの設定"""
    try:
        # Windows用フォント
        if os.name == 'nt':
            font_candidates = [
                "C:/Windows/Fonts/msgothic.ttc",
                "C:/Windows/Fonts/meiryo.ttc", 
                "C:/Windows/Fonts/NotoSansCJK-Regular.ttc"
            ]
            for font_path in font_candidates:
                if os.path.exists(font_path):
                    return fm.FontProperties(fname=font_path)
        # macOS用フォント
        else:
            font_path = "/System/Library/Fonts/ヒラギノ角ゴシック W3.ttc"
            if os.path.exists(font_path):
                return fm.FontProperties(fname=font_path)
        
        # デフォルトで利用可能な日本語フォントを探す
        japanese_fonts = [font for font in fm.findSystemFonts() if 'jp' in font.lower() or 'japan' in font.lower()]
        if japanese_fonts:
            return fm.FontProperties(fname=japanese_fonts[0])
            
    except Exception as e:
        print(f"フォント設定でエラーが発生しました: {e}")
    
    return None

def draw_stacked_bar_from_tasks(tasks):
    """タスクデータから積み上げ棒グラフを作成"""
    if not tasks:
        print("タスクがないため、グラフを表示できません。")
        return
    
    font_prop = setup_japanese_font()
    
    # カテゴリとサブタスクのデータを準備
    categories = list(set(task.get('category', '未分類') for task in tasks if task.get('category')))
    if not categories:
        categories = ['未分類']
    categories.sort()
    
    subtask_times = defaultdict(lambda: [0] * len(categories))
    
    for task in tasks:
        category = task.get('category', '未分類')
        if not category:
            category = '未分類'
        title = task.get('title', 'タスク')
        
        # 仮の時間計算（実際のアプリでは実際の時間データを使用）
        estimated_time = len(title) * 5  # タイトルの長さに基づく仮の時間
        if task.get('done', False):
            estimated_time = max(estimated_time, 15)  # 完了タスクは最低15分
        
        try:
            cat_index = categories.index(category)
            subtask_times[title][cat_index] = estimated_time
        except ValueError:
            continue
    
    plt.figure(figsize=(12, 8))
    bottom = [0] * len(categories)
    
    colors = plt.cm.Set3(range(len(subtask_times)))
    
    for i, (subtask, times) in enumerate(subtask_times.items()):
        bars = plt.bar(categories, times, bottom=bottom, label=subtask[:10], color=colors[i])
        
        # サブタスク名をバー内に表示
        for j, (cat, time) in enumerate(zip(categories, times)):
            if time > 0:
                plt.text(j, bottom[j] + time / 2, subtask[:6], 
                        ha='center', va='center', fontsize=8, 
                        fontproperties=font_prop, rotation=0)
        
        bottom = [b + t for b, t in zip(bottom, times)]
    
    plt.title('カテゴリ別タスク実行時間（積み上げ）', fontproperties=font_prop, fontsize=14)
    plt.xlabel('カテゴリ', fontproperties=font_prop)
    plt.ylabel('時間（分）', fontproperties=font_prop)
    
    if font_prop:
        plt.xticks(fontproperties=font_prop)
        plt.yticks(fontproperties=font_prop)
    
    plt.grid(axis='y', linestyle='--', alpha=0.7)
    plt.tight_layout()
    plt.show()

def draw_task_statistics(tasks):
    """タスクの統計グラフを描画"""
    if not tasks:
        print("タスクがないため、グラフを表示できません。")
        return
    
    font_prop = setup_japanese_font()
    
    # カテゴリ別のデータを準備
    category_data = defaultdict(int)
    for task in tasks:
        category = task.get('category', '未分類')
        if not category:
            category = '未分類'
        estimated_time = len(task.get('title', '')) * 3  # 仮の時間計算
        if task.get('done', False):
            estimated_time = max(estimated_time, 10)
        category_data[category] += estimated_time
    
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 10))
    
    # カテゴリ別の合計時間を棒グラフで表示
    categories = list(category_data.keys())
    times = [category_data[cat] for cat in categories]
    
    bars = ax1.bar(categories, times)
    ax1.set_title('カテゴリ別推定作業時間', fontproperties=font_prop, fontsize=14)
    ax1.set_xlabel('カテゴリ', fontproperties=font_prop)
    ax1.set_ylabel('時間（分）', fontproperties=font_prop)
    
    # 各バーに値を表示
    for bar, time in zip(bars, times):
        height = bar.get_height()
        ax1.text(bar.get_x() + bar.get_width()/2., height,
                f'{int(height)}分', ha='center', va='bottom', fontproperties=font_prop)
    
    if font_prop:
        ax1.tick_params(axis='x', labelsize=10)
        ax1.tick_params(axis='y', labelsize=10)
    
    # タスク完了状況の円グラフ
    completed_count = sum(1 for task in tasks if task.get('done', False))
    incomplete_count = len(tasks) - completed_count
    
    if completed_count > 0 or incomplete_count > 0:
        labels = ['完了', '未完了']
        sizes = [completed_count, incomplete_count]
        colors = ['#4CAF50', '#FF9800']
        
        ax2.pie(sizes, labels=labels, colors=colors, autopct='%1.1f%%', startangle=90)
        ax2.set_title('タスク完了状況', fontproperties=font_prop, fontsize=14)
    
    plt.tight_layout()
    plt.show()

def export_task_stats_json(tasks):
    """タスク統計をJSON形式で出力"""
    # カテゴリとサブタスクのデータを準備
    categories = list(set(task.get('category', '未分類') for task in tasks if task.get('category')))
    if not categories:
        categories = ['未分類']
    categories.sort()
    
    subtask_times = {}
    category_data = defaultdict(int)
    
    for task in tasks:
        category = task.get('category', '未分類')
        if not category:
            category = '未分類'
        title = task.get('title', 'タスク')
        estimated_time = len(title) * 3
        
        if task.get('done', False):
            estimated_time = max(estimated_time, 10)
        
        category_data[category] += estimated_time
        
        if title not in subtask_times:
            subtask_times[title] = [0] * len(categories)
        
        try:
            cat_index = categories.index(category)
            subtask_times[title][cat_index] = estimated_time
        except ValueError:
            continue
    
    # JSON形式でのデータ構造
    stats_data = {
        "categories": categories,
        "subtasks": subtask_times,
        "summary": {
            "total_tasks": len(tasks),
            "completed_tasks": sum(1 for task in tasks if task.get('done', False)),
            "total_estimated_time": sum(category_data.values())
        }
    }
    
    # JSONファイルとして保存
    stats_file = 'task_stats.json'
    with open(stats_file, 'w', encoding='utf-8') as f:
        json.dump(stats_data, f, indent=2, ensure_ascii=False)
    
    print(f"統計データを {stats_file} に保存しました。")
    return stats_data

# CLI用の関数群
def load_tasks_json():
    if os.path.exists(TASK_FILE):
        with open(TASK_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return []

def save_tasks_json(tasks):
    with open(TASK_FILE, 'w', encoding='utf-8') as f:
        json.dump(tasks, f, indent=4, ensure_ascii=False)

def format_due(task):
    if task.get("due_date"):
        date_str = task["due_date"]
        time_str = task.get("due_time", "")
        return f"{date_str} {time_str}".strip()
    return "（期限なし）"

def add_task_cli(tasks):
    title = input("タスクのタイトル: ")
    due_date = input("期限日 (例: 20XX-0X-XX): ").strip()
    due_time = input("期限時刻(例: 0X:XX): ").strip()

    existing_categories = sorted({task['category'] for task in tasks if task.get('category')})
    category_input = ""
    if existing_categories:
        print("📂 既存カテゴリ:")
        for i, cat in enumerate(existing_categories):
            color = CATEGORY_COLORS[i % len(CATEGORY_COLORS)]
            print(f"  {i + 1}. {color}{cat}{RESET}")
        sel = input("番号で選択 or 新しいカテゴリを直接入力: ").strip()
        if sel.isdigit():
            index = int(sel) - 1
            if 0 <= index < len(existing_categories):
                category_input = existing_categories[index]
            else:
                print("番号が無効です。カテゴリなしで登録します。")
        else:
            category_input = sel
    else:
        category_input = input("カテゴリ（新規または空欄(カテゴリなし)）: ").strip()

    if due_date:
        try:
            datetime.strptime(due_date, "%Y-%m-%d")
        except ValueError:
            print("日付の形式が不正です（YYYY-MM-DD）")
            return

    if due_time:
        try:
            datetime.strptime(due_time, "%H:%M")
        except ValueError:
            print("時刻の形式が不正です（HH:MM）")
            return

    tasks.append({
        "title": title,
        "due_date": due_date,
        "due_time": due_time,
        "category": category_input,
        "done": False
    })
    print("✅ タスクを追加しました。")

def complete_task_cli(tasks):
    show_tasks_cli(tasks)
    try:
        index = int(input("完了にするタスク番号: ")) - 1
        if 0 <= index < len(tasks):
            tasks[index]['done'] = True
            print("タスクを完了にしました。")
        else:
            print("無効な番号です。")
    except ValueError:
        print("数字を入力してください。")

def show_due_within_24h(tasks):
    now = datetime.now()
    limit = now + timedelta(hours=24)
    upcoming_tasks = []
    overdue_tasks = []

    for i, task in enumerate(tasks, start=1):
        due_date = task.get("due_date", "")
        due_time = task.get("due_time", "")
        if not due_date:
            continue
        try:
            dt_str = due_date + " " + (due_time if due_time else "23:59")
            due_dt = datetime.strptime(dt_str.strip(), "%Y-%m-%d %H:%M")
            if not task.get('done', False):
                if now <= due_dt <= limit:
                    upcoming_tasks.append((i, task, due_dt))
                elif due_dt < now:
                    overdue_tasks.append((i, task, due_dt))
        except ValueError:
            continue

    if overdue_tasks:
        print("\n⚠️ 期限切れの未完了タスク:")
        for i, task, due in overdue_tasks:
            category = task.get('category') or "（カテゴリなし）"
            print(f"{i}. ❌ {task['title']} - 期限: {due.strftime('%Y-%m-%d %H:%M')} - カテゴリ: {category}")

    if upcoming_tasks:
        print("\n⏰ 24時間以内に期限が来る未完了タスク:")
        for i, task, due in upcoming_tasks:
            category = task.get('category') or "（カテゴリなし）"
            print(f"{i}. ⏳ {task['title']} - 期限: {due.strftime('%Y-%m-%d %H:%M')} - カテゴリ: {category}")
    elif not overdue_tasks:
        print("\n⏰ 24時間以内に期限が来る未完了タスクはありません。")

def show_tasks_cli(tasks):
    if not tasks:
        print("タスクはありません。")
        return

    grouped = defaultdict(list)
    for i, task in enumerate(tasks, start=1):
        date = task.get('due_date') or "（期限なし）"
        grouped[date].append((i, task))

    sorted_dates = sorted(grouped.keys())
    for date in sorted_dates:
        print(f"\n📅 日付: {date}")
        for i, task in grouped[date]:
            status = "✅" if task['done'] else "❌"
            due = format_due(task)
            category = task['category'] if task['category'] else "（カテゴリなし）"
            print(f"{i}. [{status}] {task['title']} - 期限: {due} - カテゴリ: {category}")

def show_tasks_grouped_by_category(tasks):
    if not tasks:
        print("タスクはありません。")
        return

    grouped = defaultdict(list)
    for i, task in enumerate(tasks, start=1):
        cat = task['category'] if task['category'] else "（カテゴリなし）"
        grouped[cat].append((i, task))

    sorted_categories = sorted(grouped.keys())
    for idx, category in enumerate(sorted_categories):
        color = CATEGORY_COLORS[idx % len(CATEGORY_COLORS)]
        print(f"\n📂 カテゴリ: {color}{category}{RESET}")
        for i, task in grouped[category]:
            status = "✅" if task['done'] else "❌"
            due = format_due(task)
            print(f"{i}. [{status}] {task['title']} - 期限: {due}")

def show_tasks_by_category(tasks):
    existing_categories = sorted({task['category'] for task in tasks if task.get('category')})
    category_input = ""

    if existing_categories:
        print("📂 既存カテゴリ:")
        for i, cat in enumerate(existing_categories):
            color = CATEGORY_COLORS[i % len(CATEGORY_COLORS)]
            print(f"  {i + 1}. {color}{cat}{RESET}")
        sel = input("番号で選択 or カテゴリ名を直接入力or空白: ").strip()

        if sel.isdigit():
            index = int(sel) - 1
            if 0 <= index < len(existing_categories):
                category_input = existing_categories[index]
            else:
                print("番号が無効です。")
                return
        else:
            category_input = sel
    else:
        category_input = input("表示したいカテゴリor空白を入力してください: ").strip()

    category_to_match = category_input if category_input else ""

    matched_tasks = [
        (i + 1, task)
        for i, task in enumerate(tasks)
        if (task.get('category') or "") == category_to_match
    ]

    if not matched_tasks:
        print(f"カテゴリ「{category_input or '（カテゴリなし）'}」に該当するタスクはありません。")
    else:
        print(f"\n📂 カテゴリ: {category_input or '（カテゴリなし）'}")
        for i, task in matched_tasks:
            status = "✅" if task['done'] else "❌"
            due = format_due(task)
            print(f"{i}. [{status}] {task['title']} - 期限: {due}")

def delete_task_cli(tasks):
    show_tasks_cli(tasks)
    try:
        index = int(input("削除するタスク番号: ")) - 1
        if 0 <= index < len(tasks):
            removed = tasks.pop(index)
            print(f"タスク「{removed['title']}」を削除しました。")
        else:
            print("無効な番号です。")
    except ValueError:
        print("数字を入力してください。")

def cli_main():
    tasks = load_tasks_json()
    show_due_within_24h(tasks)

    while True:
        print("\n--- タスク管理 ---")
        print("1. タスク一覧表示")
        print("2. カテゴリごとに表示")
        print("3. 特定カテゴリを表示")
        print("4. タスク追加")
        print("5. 完了マーク")
        print("6. タスク削除")
        print("7. 統計グラフ表示")
        print("8. 積み上げグラフ表示")
        print("9. 統計データエクスポート")
        print("0. 終了")

        choice = input("選択肢を入力してください: ")

        if choice == '1':
            show_tasks_cli(tasks)
        elif choice == '2':
            show_tasks_grouped_by_category(tasks)
        elif choice == '3':
            show_tasks_by_category(tasks)
        elif choice == '4':
            add_task_cli(tasks)
        elif choice == '5':
            complete_task_cli(tasks)
        elif choice == '6':
            delete_task_cli(tasks)
        elif choice == '7':
            draw_task_statistics(tasks)
        elif choice == '8':
            draw_stacked_bar_from_tasks(tasks)
        elif choice == '9':
            export_task_stats_json(tasks)
        elif choice == '0':
            save_tasks_json(tasks)
            print("保存して終了します。")
            break
        else:
            print("無効な選択です。")

if __name__ == '__main__':
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == 'cli':
        cli_main()
    else:
        app.run(debug=True)
