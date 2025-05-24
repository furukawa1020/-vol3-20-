from flask import Flask, render_template, request, redirect, url_for, flash
import sqlite3
from datetime import datetime
import os

# Create the Flask application
app = Flask(__name__)
app.config['SECRET_KEY'] = 'your-secret-key'

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

@app.route("/about")
def about():
    return render_template("about.html")

if __name__ == '__main__':
    app.run(debug=True)
