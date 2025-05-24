from flask import Flask, render_template, request, redirect, url_for, flash
import sqlite3
from datetime import datetime
import os

# Create the Flask application
app = Flask(__name__)
app.config['SECRET_KEY'] = 'your-secret-key'

# Database setup
DB_PATH = 'tasks.db'

DEFAULT_COLORS = [
    "#F82A1B", "#FF9800", "#FFDD02", "#53EB38", "#03A9F4",
    "#2635FF", "#902DEE", "#FF80CC", "#795548", "#7DA0B2"
]

def get_db_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db_connection()
    # task
    conn.execute('''
    CREATE TABLE IF NOT EXISTS tasks (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT NOT NULL,
        description TEXT,
        due_date TEXT,
        category_id INTEGER,
        priority TEXT,
        completed INTEGER DEFAULT 0,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    )
    ''')
    #category
    conn.execute('''
    CREATE TABLE IF NOT EXISTS categories (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL UNIQUE,
        color TEXT NOT NULL
        )
    ''')

    conn.commit()

    existing = conn.execute('SELECT COUNT(*) FROM categories').fetchone()[0]
    if existing == 0:
        default_categories = [('仕事', DEFAULT_COLORS[0]), ('個人', DEFAULT_COLORS[1]), ('勉強', DEFAULT_COLORS[2])]
        conn.executemany('INSERT INTO categories (name, color) VALUES (?, ?)', default_categories)
        conn.commit()

    conn.close()

# Initialize the database
init_db()

@app.route('/')
def index():
    conn = get_db_connection()
    tasks = conn.execute('''SELECT tasks.*, categories.name AS category_name, categories.color AS category_color
    FROM tasks 
    LEFT JOIN categories ON tasks.category_id = categories.id
    ORDER BY completed, due_date ASC''').fetchall()
    conn.close()
    return render_template('index.html', tasks=tasks)

@app.route('/add', methods=['GET', 'POST'])
def add_task():
    conn = get_db_connection()
    categories = conn.execute('SELECT * FROM categories').fetchall()
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
        
        category_id = request.form.get('category_id')
        priority = request.form.get('priority', 'medium')
        
        conn = get_db_connection()
        conn.execute('INSERT INTO tasks (title, description, due_date, category_id, priority) VALUES (?, ?, ?, ?, ?)',
                    (title, description, due_date, category_id, priority))
        conn.commit()
        conn.close()
        
        flash('Task added successfully!', 'success')
        return redirect(url_for('index'))
    
    return render_template('add_task.html', categories=categories)

@app.route('/categories', methods=['GET', 'POST'])
def categories():
    conn = get_db_connection()

    if request.method == 'POST':
        name = request.form['name']
        color = request.form['color']
    
        try:
            conn.execute('INSERT INTO categories (name, color) VALUES (?, ?)', (name, color))
            conn.commit()
            flash('Category added successfully!', 'success')
        except sqlite3.IntegrityError:
            flash('Category already exist.', 'error')
        conn.close()
        return redirect(url_for('categories'))
    
    categories = conn.execute('SELECT * FROM categories').fetchall()
    conn.close()
    return render_template('categories.html', categories=categories, colors=DEFAULT_COLORS)


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
        
        category_id = request.form.get('category_id')
        priority = request.form.get('priority', 'medium')
        
        conn.execute('UPDATE tasks SET title = ?, description = ?, due_date = ?, category_id = ?, priority = ? WHERE id = ?',
                    (title, description, due_date, category_id, priority, id))
        conn.commit()
        conn.close()
        
        flash('Task updated successfully!', 'success')
        return redirect(url_for('index'))
    categories = conn.execute('SELECT * FROM categories').fetchall()
    conn.close()
    return render_template('edit_task.html', task=task, categories=categories)

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

if __name__ == '__main__':
    app.run(debug=True)
