import json
import os
from datetime import datetime, timedelta
from collections import defaultdict

TASK_FILE = 'tasks.json'
RESET = "\033[0m"
 
CATEGORY_COLORS = [
    "\033[38;2;255;99;132m",   # red
    "\033[38;2;255;159;64m",   # orange
    "\033[38;2;255;206;86m",   # yellow
    "\033[38;2;54;162;235m",   # blue
    "\033[38;2;153;102;255m",  # purple

]

def load_tasks():
    if os.path.exists(TASK_FILE):
        with open(TASK_FILE, 'r') as f:
            return json.load(f)
    return []

def save_tasks(tasks):
    with open(TASK_FILE, 'w') as f:
        json.dump(tasks, f, indent=4)

def format_due(task):
    if task.get("due_date"):
        date_str = task["due_date"]
        time_str = task.get("due_time", "")
        return f"{date_str} {time_str}".strip()
    return "（期限なし）"

#タスクに日付時刻とカテゴリがつきます

def add_task(tasks):
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

def complete_task(tasks):
    show_tasks(tasks)
    try:
        index = int(input("完了にするタスク番号: ")) - 1
        if 0 <= index < len(tasks):
            tasks[index]['done'] = True
            print("タスクを完了にしました。")
        else:
            print("無効な番号です。")
    except ValueError:
        print("数字を入力してください。")


#24時間以内に期限がくるタスクが起動時に見えたらいいかなという...

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

#通常モードだと日付で分けてる

def show_tasks(tasks):
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

#タスクで分けられて一気に見える

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

#任意のカテゴリをえらべる

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



def delete_task(tasks):
    show_tasks(tasks)
    try:
        index = int(input("削除するタスク番号: ")) - 1
        if 0 <= index < len(tasks):
            removed = tasks.pop(index)
            print(f"タスク「{removed['title']}」を削除しました。")
        else:
            print("無効な番号です。")
    except ValueError:
        print("数字を入力してください。")

def main():
    tasks = load_tasks()
    show_due_within_24h(tasks)

    while True:
        print("\n--- タスク管理 ---")
        print("1. タスク一覧表示")
        print("2. カテゴリごとに表示")
        print("3. 特定カテゴリを表示")
        print("4. タスク追加")
        print("5. 完了マーク")
        print("6. タスク削除")
        print("7. 終了")

        choice = input("選択肢を入力してください: ")

        if choice == '1':
            show_tasks(tasks)
        elif choice == '2':
            show_tasks_grouped_by_category(tasks)
        elif choice == '3':
            show_tasks_by_category(tasks)
        elif choice == '4':
            add_task(tasks)
        elif choice == '5':
            complete_task(tasks)
        elif choice == '6':
            delete_task(tasks)
        elif choice == '7':
            save_tasks(tasks)
            print("保存して終了します。")
            break
        else:
            print("無効な選択です。")

if __name__ == '__main__':
    main()