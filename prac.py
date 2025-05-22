# import tkinter as tk
# import platform
# import math
# from tkinter import font as tkfont
# from datetime import datetime, timedelta
# import os

# def get_screen_size():
#     system = platform.system()
#     if system == "Windows":
#         import ctypes
#         user32 = ctypes.windll.user32
#         return user32.GetSystemMetrics(0), user32.GetSystemMetrics(1)
#     elif system == "Darwin":
#         try:
#             import AppKit
#             frame = AppKit.NSScreen.mainScreen().frame()
#             return int(frame.size.width), int(frame.size.height)
#         except:
#             pass
#     root = tk.Tk()
#     return root.winfo_screenwidth(), root.winfo_screenheight()

# # ✅ カスタマイズ可能パラメータ

# border_size = 2
# circle_padding = 10
# circle_size = 200
# circle_border_size = 1

# bg_color = "#DEB887"
# circle_color = "#FFFFFF"
# circle_outline_color = "black"
# dot_color = "black"
# screen_padding = 10

# font_name = "Oranienbaum"
# font_size = 20

# hour_hand_color = "black"
# minute_hand_color = "black"
# hour_hand_width = 4
# minute_hand_width = 2
# hour_hand_length_ratio = 0.30
# minute_hand_length_ratio = 0.42

# task_file = "task.txt"
# task_dot_radius = 4

# # -----------------------------------------------------

# bg_size = circle_size + circle_padding * 2
# window_size = bg_size + border_size * 2

# screen_width, screen_height = get_screen_size()
# x = screen_width - window_size - screen_padding
# y = screen_padding

# root = tk.Tk()
# root.overrideredirect(True)
# root.attributes("-topmost", True)
# root.configure(bg="black")
# root.geometry(f"{window_size}x{window_size}+{x}+{y}")

# frame = tk.Frame(root, bg=bg_color, width=bg_size, height=bg_size)
# frame.place(x=border_size, y=border_size)

# canvas = tk.Canvas(frame, width=bg_size, height=bg_size,
#                    highlightthickness=0, bg=bg_color)
# canvas.pack()

# offset = circle_padding
# cx = offset + circle_size / 2
# cy = offset + circle_size / 2

# custom_font = tkfont.Font(family=font_name, size=font_size)

# tooltip = None

# def draw_static_elements():
#     canvas.create_oval(
#         offset, offset,
#         offset + circle_size, offset + circle_size,
#         fill=circle_color,
#         outline=circle_outline_color,
#         width=circle_border_size
#     )
#     canvas.create_rectangle(cx - 1, cy - 1, cx + 1, cy + 1,
#                             fill=dot_color, outline=dot_color)

#     positions = {
#         "12": 270,
#         "3": 0,
#         "6": 90,
#         "9": 180
#     }
#     radius = circle_size / 2 - 10 - 3
#     for label, angle_deg in positions.items():
#         angle_rad = math.radians(angle_deg)
#         tx = cx + radius * math.cos(angle_rad)
#         ty = cy + radius * math.sin(angle_rad)
#         canvas.create_text(tx, ty, text=label, font=custom_font, fill="black")

# def draw_clock_hands():
#     canvas.delete("hands")

#     now = datetime.now()
#     minute = now.minute
#     rounded_minute = round(minute / 5) * 5
#     if rounded_minute == 60:
#         rounded_minute = 0
#         hour = (now.hour + 1) % 24
#     else:
#         hour = now.hour

#     minute_angle_deg = rounded_minute * 6
#     hour_angle_deg = (hour % 12) * 30 + rounded_minute * 0.5

#     # 分針
#     minute_length = circle_size * minute_hand_length_ratio
#     angle_rad = math.radians(minute_angle_deg - 90)
#     mx = cx + minute_length * math.cos(angle_rad)
#     my = cy + minute_length * math.sin(angle_rad)
#     canvas.create_line(cx, cy, mx, my,
#                        width=minute_hand_width,
#                        fill=minute_hand_color,
#                        tags="hands")

#     # 時針
#     hour_length = circle_size * hour_hand_length_ratio
#     angle_rad = math.radians(hour_angle_deg - 90)
#     hx = cx + hour_length * math.cos(angle_rad)
#     hy = cy + hour_length * math.sin(angle_rad)
#     canvas.create_line(cx, cy, hx, hy,
#                        width=hour_hand_width,
#                        fill=hour_hand_color,
#                        tags="hands")

#     # タスク描画
#     draw_tasks()

#     # 1分後に更新
#     root.after(60000, draw_clock_hands)

# def draw_tasks():
#     canvas.delete("task")
#     now = datetime.now()
#     try:
#         with open(task_file, "r", encoding="utf-8") as f:
#             for line in f:
#                 line = line.strip()
#                 if not line:
#                     continue
#                 try:
#                     date_str, name, color = line.split(",")
#                     task_time = datetime.strptime(date_str, "%Y%m%d%H%M")
#                     if 0 <= (task_time - now).total_seconds() <= 43200:
#                         hour = task_time.hour % 12
#                         minute = task_time.minute
#                         angle_deg = (hour + minute / 60) * 30
#                         angle_rad = math.radians(angle_deg - 90)
#                         radius = circle_size / 2 * 0.5
#                         tx = cx + radius * math.cos(angle_rad)
#                         ty = cy + radius * math.sin(angle_rad)
#                         dot = canvas.create_oval(
#                             tx - task_dot_radius, ty - task_dot_radius,
#                             tx + task_dot_radius, ty + task_dot_radius,
#                             fill=color, outline="black", tags="task"
#                         )
#                         bind_task_tooltip(dot, name, date_str)
#                 except Exception as e:
#                     print("task line error:", e)
#     except FileNotFoundError:
#         pass

# def bind_task_tooltip(item, text, datetime_str):
#     def show_tooltip(event):
#         global tooltip
#         try:
#             formatted_time = datetime.strptime(datetime_str, "%Y%m%d%H%M").strftime("%Y/%m/%d %H:%M")
#         except:
#             formatted_time = datetime_str
#         tooltip_text = f"{text}\n{formatted_time}"
#         x = event.x - 50
#         y = event.y + 15

#         padding = 4
#         text_id = canvas.create_text(x, y, text=tooltip_text,
#                                      font=(font_name, 11),
#                                      fill="black", anchor="nw",
#                                      tags="tooltip")
#         bbox = canvas.bbox(text_id)
#         canvas.delete(text_id)

#         if bbox:
#             x0, y0, x1, y1 = bbox
#             canvas.create_rectangle(
#                 x0 - padding, y0 - padding,
#                 x1 + padding, y1 + padding,
#                 fill="white", outline="black", tags="tooltip"
#             )
#             canvas.create_text(
#                 x, y, text=tooltip_text,
#                 font=(font_name, 11),
#                 fill="black", anchor="nw",
#                 tags="tooltip"
#             )

#     def hide_tooltip(event):
#         canvas.delete("tooltip")

#     canvas.tag_bind(item, "<Enter>", show_tooltip)
#     canvas.tag_bind(item, "<Leave>", hide_tooltip)

# draw_static_elements()
# draw_clock_hands()

# root.bind("<Escape>", lambda e: root.destroy())
# root.mainloop()
# import tkinter as tk
# import platform
# import math
# from tkinter import font as tkfont
# from datetime import datetime, timedelta
# import os

# def get_screen_size():
#     system = platform.system()
#     if system == "Windows":
#         import ctypes
#         user32 = ctypes.windll.user32
#         return user32.GetSystemMetrics(0), user32.GetSystemMetrics(1)
#     elif system == "Darwin":
#         try:
#             import AppKit
#             frame = AppKit.NSScreen.mainScreen().frame()
#             return int(frame.size.width), int(frame.size.height)
#         except:
#             pass
#     root = tk.Tk()
#     return root.winfo_screenwidth(), root.winfo_screenheight()

# # ✅ カスタマイズ可能なパラメータ
# border_size = 2
# circle_padding = 10
# circle_size = 200
# circle_border_size = 1

# bg_color = "#DEB887"
# circle_color = "#FFFFFF"
# circle_outline_color = "black"
# dot_color = "black"
# screen_padding = 10

# font_name = "Oranienbaum"
# font_size = 20

# hour_hand_color = "black"
# minute_hand_color = "black"
# hour_hand_width = 4
# minute_hand_width = 2
# hour_hand_length_ratio = 0.30
# minute_hand_length_ratio = 0.42

# task_file = "task.txt"
# task_dot_radius = 4

# # -----------------------------------------------------
# bg_size = circle_size + circle_padding * 2
# window_size = bg_size + border_size * 2
# screen_width, screen_height = get_screen_size()
# x = screen_width - window_size - screen_padding
# y = screen_padding

# root = tk.Tk()
# root.overrideredirect(True)
# root.attributes("-topmost", True)
# root.configure(bg="black")
# root.geometry(f"{window_size}x{window_size}+{x}+{y}")

# frame = tk.Frame(root, bg=bg_color, width=bg_size, height=bg_size)
# frame.place(x=border_size, y=border_size)

# canvas = tk.Canvas(frame, width=bg_size, height=bg_size,
#                    highlightthickness=0, bg=bg_color)
# canvas.pack()

# offset = circle_padding
# cx = offset + circle_size / 2
# cy = offset + circle_size / 2

# custom_font = tkfont.Font(family=font_name, size=font_size)
# tooltip = None

# def draw_static_elements():
#     canvas.create_oval(
#         offset, offset,
#         offset + circle_size, offset + circle_size,
#         fill=circle_color,
#         outline=circle_outline_color,
#         width=circle_border_size
#     )
#     canvas.create_rectangle(cx - 1, cy - 1, cx + 1, cy + 1,
#                             fill=dot_color, outline=dot_color)

#     positions = {
#         "12": 270,
#         "3": 0,
#         "6": 90,
#         "9": 180
#     }
#     radius = circle_size / 2 - 10 - 3
#     for label, angle_deg in positions.items():
#         angle_rad = math.radians(angle_deg)
#         tx = cx + radius * math.cos(angle_rad)
#         ty = cy + radius * math.sin(angle_rad)
#         canvas.create_text(tx, ty, text=label, font=custom_font, fill="black")

# def draw_clock_hands():
#     canvas.delete("hands")
#     now = datetime.now()
#     minute = now.minute
#     rounded_minute = round(minute / 5) * 5
#     if rounded_minute == 60:
#         rounded_minute = 0
#         hour = (now.hour + 1) % 24
#     else:
#         hour = now.hour

#     minute_angle_deg = rounded_minute * 6
#     hour_angle_deg = (hour % 12) * 30 + rounded_minute * 0.5

#     # 分針
#     minute_length = circle_size * minute_hand_length_ratio
#     angle_rad = math.radians(minute_angle_deg - 90)
#     mx = cx + minute_length * math.cos(angle_rad)
#     my = cy + minute_length * math.sin(angle_rad)
#     canvas.create_line(cx, cy, mx, my,
#                        width=minute_hand_width,
#                        fill=minute_hand_color,
#                        tags="hands")

#     # 時針
#     hour_length = circle_size * hour_hand_length_ratio
#     angle_rad = math.radians(hour_angle_deg - 90)
#     hx = cx + hour_length * math.cos(angle_rad)
#     hy = cy + hour_length * math.sin(angle_rad)
#     canvas.create_line(cx, cy, hx, hy,
#                        width=hour_hand_width,
#                        fill=hour_hand_color,
#                        tags="hands")

#     draw_tasks()
#     root.after(60000, draw_clock_hands)

# def draw_tasks():
#     canvas.delete("task")
#     now = datetime.now()
#     try:
#         with open(task_file, "r", encoding="utf-8") as f:
#             for line in f:
#                 line = line.strip()
#                 if not line:
#                     continue
#                 try:
#                     date_str, name, color = line.split(",")
#                     task_time = datetime.strptime(date_str, "%Y%m%d%H%M")
#                     if 0 <= (task_time - now).total_seconds() <= 43200:
#                         hour = task_time.hour % 12
#                         minute = task_time.minute
#                         angle_deg = (hour + minute / 60) * 30
#                         angle_rad = math.radians(angle_deg - 90)
#                         radius = circle_size / 2 * 0.5  # 中心から50%
#                         tx = cx + radius * math.cos(angle_rad)
#                         ty = cy + radius * math.sin(angle_rad)
#                         dot = canvas.create_oval(
#                             tx - task_dot_radius, ty - task_dot_radius,
#                             tx + task_dot_radius, ty + task_dot_radius,
#                             fill=color, outline="black", tags="task"
#                         )
#                         bind_task_tooltip(dot, name, task_time)
#                 except Exception as e:
#                     print("task line error:", e)
#     except FileNotFoundError:
#         pass

# def bind_task_tooltip(item, name, task_time):
#     def show_tooltip(event):
#         global tooltip
#         ol = "black"
#         # 時間帯による背景色決定
#         hours_remaining = (task_time - datetime.now()).total_seconds() / 3600
#         if hours_remaining <= 2:
#             bg_color = "red"
#             ol = "white"
#         elif hours_remaining <= 6:
#             bg_color = "yellow"
#         else:
#             bg_color = "white"

#         # 日時文字列整形
#         month = task_time.strftime("%m").lstrip("0")
#         day = task_time.strftime("%d").lstrip("0")
#         display_time = f"{month}月{day}日 {task_time.strftime('%H:%M')}"

#         # 吹き出しテキスト
#         tooltip = canvas.create_text(
#             event.x - 50, event.y + 10,
#             text=f"{name}\n{display_time}",
#             fill=ol,
#             font=(font_name, 12),
#             anchor="nw",
#             tags="tooltip"
#         )

#         # 背景の白（または色付き）四角
#         bbox = canvas.bbox(tooltip)
#         if bbox:
#             x1, y1, x2, y2 = bbox
#             rect = canvas.create_rectangle(
#                 x1 - 2, y1 - 2, x2 + 2, y2 + 2,
#                 fill=bg_color, outline="black", tags="tooltip_bg"
#             )
#             canvas.tag_lower(rect, tooltip)

#     def hide_tooltip(event):
#         canvas.delete("tooltip")
#         canvas.delete("tooltip_bg")

#     canvas.tag_bind(item, "<Enter>", show_tooltip)
#     canvas.tag_bind(item, "<Leave>", hide_tooltip)



# draw_static_elements()
# draw_clock_hands()
# root.bind("<Escape>", lambda e: root.destroy())
# root.mainloop()
import tkinter as tk
import platform
import math
from tkinter import font as tkfont
from datetime import datetime
import os

def get_screen_size():
    system = platform.system()
    if system == "Windows":
        import ctypes
        user32 = ctypes.windll.user32
        return user32.GetSystemMetrics(0), user32.GetSystemMetrics(1)
    elif system == "Darwin":
        try:
            import AppKit
            frame = AppKit.NSScreen.mainScreen().frame()
            return int(frame.size.width), int(frame.size.height)
        except:
            pass
    root = tk.Tk()
    root.withdraw()
    return root.winfo_screenwidth(), root.winfo_screenheight()

def main(
    circle_size=200,
    circle_padding=10,
    border_size=2,
    circle_border_size=1,
    bg_color="#DEB887",
    circle_color="#FFFFFF",
    circle_outline_color="black",
    dot_color="black",
    screen_padding=10,
    font_name="Oranienbaum",
    font_size=20,
    hour_hand_color="black",
    minute_hand_color="black",
    hour_hand_width=4,
    minute_hand_width=2,
    hour_hand_length_ratio=0.30,
    minute_hand_length_ratio=0.42,
    task_file="task.txt",
    task_dot_radius=4,
    pos_x=None,
    pos_y=None
):
    bg_size = circle_size + circle_padding * 2
    window_size = bg_size + border_size * 2
    screen_width, screen_height = get_screen_size()
    x = pos_x if pos_x is not None else screen_width - window_size - screen_padding
    y = pos_y if pos_y is not None else screen_padding

    root = tk.Tk()
    root.overrideredirect(True)
    root.attributes("-topmost", True)
    root.configure(bg="black")
    root.geometry(f"{window_size}x{window_size}+{x}+{y}")

    frame = tk.Frame(root, bg=bg_color, width=bg_size, height=bg_size)
    frame.place(x=border_size, y=border_size)

    canvas = tk.Canvas(frame, width=bg_size, height=bg_size,
                       highlightthickness=0, bg=bg_color)
    canvas.pack()

    offset = circle_padding
    cx = offset + circle_size / 2
    cy = offset + circle_size / 2

    custom_font = tkfont.Font(family=font_name, size=font_size)

    def draw_static_elements():
        canvas.create_oval(
            offset, offset,
            offset + circle_size, offset + circle_size,
            fill=circle_color,
            outline=circle_outline_color,
            width=circle_border_size
        )
        canvas.create_rectangle(cx - 1, cy - 1, cx + 1, cy + 1,
                                fill=dot_color, outline=dot_color)

        positions = {
            "12": 270,
            "3": 0,
            "6": 90,
            "9": 180
        }
        radius = circle_size / 2 - 10 - 3
        for label, angle_deg in positions.items():
            angle_rad = math.radians(angle_deg)
            tx = cx + radius * math.cos(angle_rad)
            ty = cy + radius * math.sin(angle_rad)
            canvas.create_text(tx, ty, text=label, font=custom_font, fill="black")

    def draw_clock_hands():
        canvas.delete("hands")
        now = datetime.now()
        minute = now.minute
        rounded_minute = round(minute / 5) * 5
        if rounded_minute == 60:
            rounded_minute = 0
            hour = (now.hour + 1) % 24
        else:
            hour = now.hour

        minute_angle_deg = rounded_minute * 6
        hour_angle_deg = (hour % 12) * 30 + rounded_minute * 0.5

        # 分針
        minute_length = circle_size * minute_hand_length_ratio
        angle_rad = math.radians(minute_angle_deg - 90)
        mx = cx + minute_length * math.cos(angle_rad)
        my = cy + minute_length * math.sin(angle_rad)
        canvas.create_line(cx, cy, mx, my,
                           width=minute_hand_width,
                           fill=minute_hand_color,
                           tags="hands")

        # 時針
        hour_length = circle_size * hour_hand_length_ratio
        angle_rad = math.radians(hour_angle_deg - 90)
        hx = cx + hour_length * math.cos(angle_rad)
        hy = cy + hour_length * math.sin(angle_rad)
        canvas.create_line(cx, cy, hx, hy,
                           width=hour_hand_width,
                           fill=hour_hand_color,
                           tags="hands")

        draw_tasks()
        root.after(60000, draw_clock_hands)

    def draw_tasks():
        canvas.delete("task")
        now = datetime.now()
        try:
            with open(task_file, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        date_str, name, color = line.split(",")
                        task_time = datetime.strptime(date_str, "%Y%m%d%H%M")
                        if 0 <= (task_time - now).total_seconds() <= 43200:
                            hour = task_time.hour % 12
                            minute = task_time.minute
                            angle_deg = (hour + minute / 60) * 30
                            angle_rad = math.radians(angle_deg - 90)
                            radius = circle_size / 2 * 0.5
                            tx = cx + radius * math.cos(angle_rad)
                            ty = cy + radius * math.sin(angle_rad)
                            dot = canvas.create_oval(
                                tx - task_dot_radius, ty - task_dot_radius,
                                tx + task_dot_radius, ty + task_dot_radius,
                                fill=color, outline="black", tags="task"
                            )
                            bind_task_tooltip(dot, name, task_time)
                    except Exception as e:
                        print("task line error:", e)
        except FileNotFoundError:
            pass

    def bind_task_tooltip(item, name, task_time):
        def show_tooltip(event):
            nonlocal tooltip
            ol = "black"
            hours_remaining = (task_time - datetime.now()).total_seconds() / 3600
            if hours_remaining <= 2:
                bg = "red"
                ol = "white"
            elif hours_remaining <= 6:
                bg = "yellow"
            else:
                bg = "white"

            month = task_time.strftime("%m").lstrip("0")
            day = task_time.strftime("%d").lstrip("0")
            display_time = f"{month}月{day}日 {task_time.strftime('%H:%M')}"

            tooltip = canvas.create_text(
                event.x - 50, event.y + 10,
                text=f"{name}\n{display_time}",
                fill=ol,
                font=(font_name, 12),
                anchor="nw",
                tags="tooltip"
            )

            bbox = canvas.bbox(tooltip)
            if bbox:
                x1, y1, x2, y2 = bbox
                rect = canvas.create_rectangle(
                    x1 - 2, y1 - 2, x2 + 2, y2 + 2,
                    fill=bg, outline="black", tags="tooltip_bg"
                )
                canvas.tag_lower(rect, tooltip)

        def hide_tooltip(event):
            canvas.delete("tooltip")
            canvas.delete("tooltip_bg")

        tooltip = None
        canvas.tag_bind(item, "<Enter>", show_tooltip)
        canvas.tag_bind(item, "<Leave>", hide_tooltip)

    draw_static_elements()
    draw_clock_hands()
    root.bind("<Escape>", lambda e: root.destroy())
    root.mainloop()
