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
        import traceback
        traceback.print_exc()
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

# データベース初期化（アプリ起動時）
print("Initializing database...")
init_db()

# ヘルスチェック
if not health_check():
    print("Warning: Health check failed, but continuing...")

print("Flask application ready to start")

# gunicorn用のアプリケーション設定
def create_app():
    """アプリケーションファクトリー（gunicorn用）"""
    return app

# Renderでgunicornを使用する場合、この部分をコメントアウトまたは条件分岐
if __name__ == '__main__':
    try:
        # 開発環境でのみ直接実行
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
        import traceback
        traceback.print_exc()
        exit(1)

# gunicorn用のアプリケーションオブジェクト
application = app

# 遅延初期化でデータベースセットアップ
@app.before_first_request
def initialize_database():
    """最初のリクエスト前にデータベースを初期化"""
    print("Initializing database before first request...")
    init_db()
    
    if not health_check():
        print("Warning: Health check failed, but continuing...")
    
    print("Flask application ready")

# または、gunicorn環境では即座に初期化
try:
    # 本番環境（gunicorn）では即座に初期化
    if os.environ.get('SERVER_SOFTWARE', '').startswith('gunicorn'):
        print("Running under gunicorn, initializing database...")
        init_db()
        health_check()
except Exception as e:
    print(f"Startup initialization error: {e}")

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
        # データベース接続テスト
        conn = get_db_connection()
        conn.execute('SELECT 1')
        conn.close()
        return {"status": "healthy", "timestamp": datetime.now().isoformat()}, 200
    except Exception as e:
        return {"status": "unhealthy", "error": str(e)}, 500

# データベース初期化関数を呼び出し
try:
    print("Application startup: initializing database...")
    init_db()
    print("Database initialization completed")
except Exception as e:
    print(f"Failed to initialize database during startup: {e}")
