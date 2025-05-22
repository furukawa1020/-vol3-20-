import json
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm

# ヒラギノフォントのパス（macOS用）
font_path = "/System/Library/Fonts/ヒラギノ角ゴシック W3.ttc"
font_prop = fm.FontProperties(fname=font_path)

# JSONデータ（文字列として埋め込み）
json_str = '''
{
  "categories": ["雑務", "授業", "勉強", "ミーティング", "研究"],
  "subtasks": {
    "メール":    [30, 0, 0, 0, 0],
    "講義準備":  [0, 90, 0, 0, 0],
    "数学":     [0, 0, 40, 0, 0],
    "英語":     [0, 0, 20, 0, 0],
    "打ち合わせ": [0, 0, 0, 45, 0],
    "実験":     [0, 0, 0, 0, 40]
  }
}
'''

# JSONを辞書に変換
data = json.loads(json_str)

def draw_stacked_bar(data):
    category_labels = data["categories"]
    subtask_times = data["subtasks"]

    plt.figure(figsize=(10, 6))
    bottom = [0] * len(category_labels)

    for subtask, times in subtask_times.items():
        bars = plt.bar(category_labels, times, bottom=bottom, label=subtask)
        for i, (x, y) in enumerate(zip(category_labels, times)):
            if y > 0:
                plt.text(i, bottom[i] + y / 2, subtask, ha='center', va='center', fontsize=9, fontproperties=font_prop)
        bottom = [b + t for b, t in zip(bottom, times)]

    plt.title('ToDo実行時間（積み上げ）', fontproperties=font_prop)
    plt.xlabel('カテゴリ', fontproperties=font_prop)
    plt.ylabel('時間（分）', fontproperties=font_prop)
    plt.xticks(fontproperties=font_prop)
    plt.yticks(fontproperties=font_prop)
    plt.grid(axis='y', linestyle='--', alpha=0.7)
    plt.tight_layout()
    plt.show()

if __name__ == '__main__':
    draw_stacked_bar(data)