import subprocess
import sys


def install_dependencies():
    """使用內建庫檢查並自動安裝缺失組件"""
    requirements_path = "requirements.txt"
    try:
        from importlib.metadata import version, PackageNotFoundError
    except ImportError:
  
        print("正在為系統準備基礎工具...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "setuptools"])
        from importlib.metadata import version, PackageNotFoundError

    try:
        with open(requirements_path, "r", encoding="utf-8") as f:
   
            required = [line.strip() for line in f if line.strip() and not line.startswith("#")]
        
        missing = []
        for pkg in required:
   
            clean_pkg = pkg.split('==')[0].split('>=')[0].strip()
            try:
                version(clean_pkg)
            except PackageNotFoundError:
                missing.append(pkg)

        if missing:
            print(f" 偵測到缺失組件: {missing}")
            print(" 正在為您自動安裝，請稍候...")
            subprocess.check_call([sys.executable, "-m", "pip", "install", *missing])
            print(" 安裝完成！正在啟動程式...\n" + "="*30)
    except FileNotFoundError:
        print(" 找不到 requirements.txt，將跳過檢查。")
    except Exception as e:
        print(f"自動安裝失敗: {e}")

install_dependencies()
import json
import tkinter as tk
from tkinter import messagebox, scrolledtext
from google import genai
import os
import io
from datetime import datetime
import asyncio
import edge_tts
import pygame
import threading  
import time       
import speech_recognition as sr #  Speech recognition library
from google.genai import types

# --- 1.Environment Stability Layer  ---
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

# --- 2. Configuration Management Layer ---
API_KEY = "Please input you APU KEY"
client = genai.Client(api_key=API_KEY)


MODEL_NAME = "gemini-flash-latest" 
SCENES_FILE = "scenes.json"
BACKUP_DIR = "backups"
SAVE_DIR = "saves"
SCRIPTS_DIR = "scripts" 

# --- 3. Data Handling Layer ---
def save_json(file_path, data):
    try:
        if not os.path.exists(BACKUP_DIR): os.makedirs(BACKUP_DIR)
        if "save_slot" not in file_path and os.path.exists(file_path):
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            os.rename(file_path, os.path.join(BACKUP_DIR, f"backup_{timestamp}.json"))
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=4)
    except: pass

def load_json(file_path, default):
    if not os.path.exists(file_path): return default
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data if isinstance(data, dict) else default
    except: return default

# --- 4. AI Generation Engine  ---
def generate_full_story(config):
    prompt = f"""
    你是一位暖心故事作家。請生成一個包含 20 個場景的 JSON 網狀敘事劇本。
    
    【核心目標】：
    將 20 個場景根據結局數量分配為幾條完整、連續的故事長鏈。
    
    【故事設定】：
    - 角色：{config['name']} ({config['personality']})
    - 目標：{config['goal']} | 世界：{config['world']}

    【劇本結構與邏輯規範】：
    1. **正向簡單結局**：必須且只能生成 2 到 3 個結局場景 (如 scene_18, 19, 20)。結局必須是簡單、正向、充滿希望且溫馨的，體現善有善報或努力有成的美德。
    2. **路徑分配機制**：
       - 根據結局數量，將大部分場景 (約 15-17 個) 用於構建完整的故事主線。
       - 分歧點與選項必須設計為：『解決當前事件或問題的不同方法』。
       - 例如：遇到斷掉的小橋，選項 A 是『動手修復』，選項 B 是『向鄰居求助』。不同的方法會引導至不同的因果場景，但最終都要組成連貫的故事。
    3. **因果連續性**：嚴格遵守上下文邏輯。場景描述必須明確回應玩家選擇的方法所產生的直接影響。
    4. **禁止劇情穿越**：嚴禁提及玩家未經歷的路徑事實。
    5. **分段檢查**：要求模型在生成時，內部自我檢查場景編號是否連續。
    6. **JSON 完整性**：明確規定 scene_1 到 scene_20 必須全部出現，缺一不可。

    【寫作風格】：
    - 每段 80-130 字，溫柔且富有畫面感的中文口語。
    - 禁止使用雙引號 (")，請用單引號 (')。
    - **嚴禁回傳 Markdown 標籤**，只回傳純 JSON。

    格式：{{ "scenes": {{ "scene_1": {{ "description": "...", "options": [ {{ "text": "...", "next_scene": "..." }} ] }} }} }}
    """
    try:
        response = client.models.generate_content(model=MODEL_NAME, contents=prompt)
        raw_text = response.text.strip()
        
        # Parsing Enhancement: Ensure accurate JSON extraction during long postbacks.
        clean_text = raw_text.replace("```json", "").replace("```", "").strip()
        start = clean_text.find('{')
        end = clean_text.rfind('}') + 1
        
        if start == -1 or end == 0: return None
        
        result = json.loads(clean_text[start:end])
        if isinstance(result, list): result = result[0]
        return result if isinstance(result, dict) and "scenes" in result else None
    except:
        return None

# --- 5. GUI Interaction Layer ---
class AdventureGame:
    def __init__(self, root):
        self.root = root
        self.root.title("精彩人生冒險")
        self.root.geometry("1400x1000")
        self.root.configure(bg="#FDFCF0")
        
        # pygame voice
        pygame.mixer.init()
        
        self.voice_on = True 
        self.current_engine = None
        self.font_size_mod = 0 
        
        # history
        self.history = [] 
        # return step
        self.path_history = [] 
        
        self.update_fonts()
        
        self.story_data = {}
        self.current_scene_id = "scene_1"
        if not os.path.exists(SAVE_DIR): os.makedirs(SAVE_DIR)
        if not os.path.exists(SCRIPTS_DIR): os.makedirs(SCRIPTS_DIR) 
        self.show_main_menu()

    def update_fonts(self):
        self.fonts = {
            "title": ("Microsoft JhengHei", 64 + self.font_size_mod, "bold"),
            "text": ("Microsoft JhengHei", 36 + self.font_size_mod),
            "btn": ("Microsoft JhengHei", 30 + self.font_size_mod, "bold"),
            "small": ("Microsoft JhengHei", 18 + self.font_size_mod)
        }

    def change_font_size(self, delta, current_view):
        if -20 <= self.font_size_mod + delta <= 60: 
            self.font_size_mod += delta
            self.update_fonts()
            if current_view == "menu":
                self.show_main_menu()
            elif current_view == "scene":
                self.show_scene(skip_speak=True)

    def show_history(self):
        history_win = tk.Toplevel(self.root)
        history_win.title("往事回顧")
        history_win.geometry("1000x800")
        history_win.configure(bg="#FDFCF0")
        
        tk.Label(history_win, text="📜 歷程回顧", font=self.fonts["btn"], bg="#FDFCF0").pack(pady=20)
        
        text_area = scrolledtext.ScrolledText(history_win, font=("Microsoft JhengHei", 24), wrap=tk.WORD, bg="white", padx=20, pady=20)
        text_area.pack(expand=True, fill="both", padx=30, pady=10)
        
        if not self.history:
            text_area.insert(tk.END, "尚無故事紀錄。")
        else:
            for i, entry in enumerate(self.history):
                text_area.insert(tk.END, f"【第 {i+1} 幕故事】\n", ("bold",))
                text_area.insert(tk.END, f"{entry['desc']}\n")
                if entry['choice']:
                    text_area.insert(tk.END, f"➔ 您的選擇：{entry['choice']}\n", ("choice",))
                text_area.insert(tk.END, "\n" + "-"*30 + "\n\n")
        
        text_area.tag_configure("bold", font=("Microsoft JhengHei", 24, "bold"))
        text_area.tag_configure("choice", foreground="#2E7D32", font=("Microsoft JhengHei", 24, "italic"))
        
        text_area.configure(state='disabled')
        tk.Button(history_win, text="關閉視窗", font=("Microsoft JhengHei", 20), command=history_win.destroy).pack(pady=20)

    def undo_move(self):
        if len(self.path_history) > 0:
            self.current_scene_id = self.path_history.pop()
            if self.history: self.history.pop()
            self.show_scene()
        else:
            messagebox.showinfo("提示", "已經回到故事的最開頭了。")

    def start_voice_input(self, scene_options):
        def recognition_task():
            r = sr.Recognizer()
            with sr.Microphone() as source:
                self.speak_text("請說出您的選擇...")
                try:
                    audio = r.listen(source, timeout=5, phrase_time_limit=5)
                    command = r.recognize_google(audio, language="zh-TW")
                    self.process_voice_command(command, scene_options)
                except sr.UnknownValueError:
                    self.speak_text("抱歉，我沒聽清楚，請再試一次。")
                except Exception as e:
                    self.speak_text("語音功能暫時無法使用。")

        threading.Thread(target=recognition_task, daemon=True).start()

    def process_voice_command(self, text, options):
        found_id = None
        found_text = ""
        
        for i, opt in enumerate(options):
            opt_txt = opt.get("text", "")
            if str(i+1) in text or "一" in text and i==0 or "二" in text and i==1 or opt_txt in text:
                found_id = opt.get("next_scene")
                found_text = opt_txt
                break
        
        if found_id:
            self.root.after(0, lambda: self.go_to(found_id, found_text))
        else:
            self.speak_text(f"您說的是：{text}，但我找不到對應的選項，請手動點選或重新再試。")

    # --- voice function ---
    def _speak_task(self, text):
        async def generate_and_play():
            try:
                voice = "zh-HK-HiuGaaiNeural"
                output_path = f"speech_temp_{int(time.time()*1000)}.mp3"
                communicate = edge_tts.Communicate(text, voice)
                await communicate.save(output_path)
                
                if os.path.exists(output_path):
                    #clear pygame 
                    try: pygame.mixer.music.unload() 
                    except: pass
                    
                    pygame.mixer.music.load(output_path)
                    pygame.mixer.music.play()
                    while pygame.mixer.music.get_busy():
                        if not self.voice_on:
                            pygame.mixer.music.stop()
                            break
                        time.sleep(0.1)
                        
                    try: pygame.mixer.music.unload()
                    except: pass
                    try: os.remove(output_path)
                    except: pass
            except: pass

        new_loop = asyncio.new_event_loop()
        asyncio.set_event_loop(new_loop)
        new_loop.run_until_complete(generate_and_play())
        new_loop.close() 

    def speak_text(self, text):
        if self.voice_on:
            if pygame.mixer.music.get_busy():
                pygame.mixer.music.stop()
                try: pygame.mixer.music.unload()
                except: pass
            self.root.after(300, lambda: threading.Thread(target=self._speak_task, args=(text,), daemon=True).start())

    def toggle_voice(self):
        self.voice_on = not self.voice_on
        if not self.voice_on:
            if pygame.mixer.music.get_busy():
                pygame.mixer.music.stop()
                try: pygame.mixer.music.unload() 
                except: pass
        self.show_main_menu()

    def show_main_menu(self):
        if pygame.mixer.music.get_busy(): 
            pygame.mixer.music.stop()
            try: pygame.mixer.music.unload() 
            except: pass
            
        for w in self.root.winfo_children(): w.destroy()
        
        self.history = [] 
        self.path_history = [] 
        
        ctrl_frame = tk.Frame(self.root, bg="#FDFCF0")
        ctrl_frame.pack(fill="x", padx=20, pady=10)
        tk.Button(ctrl_frame, text="A+ 放大文字", font=("Microsoft JhengHei", 16), command=lambda: self.change_font_size(4, "menu")).pack(side="right", padx=5)
        tk.Button(ctrl_frame, text="A- 縮小文字", font=("Microsoft JhengHei", 16), command=lambda: self.change_font_size(-4, "menu")).pack(side="right", padx=5)

        tk.Label(self.root, text="🌞 精彩人生冒險", font=self.fonts["title"], bg="#FDFCF0", fg="#4A4A4A").pack(pady=40)
        v_txt = "🔊 語音朗讀：開啟" if self.voice_on else "🔇 語音朗讀：關閉"
        v_bg = "#C8E6C9" if self.voice_on else "#FFCDD2"
        tk.Button(self.root, text=v_txt, font=self.fonts["btn"], bg=v_bg, command=self.toggle_voice).pack(pady=10)
        tk.Button(self.root, text="🆕 開始新故事", font=self.fonts["btn"], width=30, height=2, bg="#FFF9C4", command=self.setup_story).pack(pady=10)
        tk.Button(self.root, text="📜 選擇已存劇本", font=self.fonts["btn"], width=30, height=2, bg="#E1F5FE", command=self.show_script_menu).pack(pady=10)
        tk.Button(self.root, text="📂 讀取遊戲進度", font=self.fonts["btn"], width=30, height=2, bg="#C8E6C9", command=self.show_load_menu).pack(pady=10)

    def setup_story(self):
        setup_win = tk.Toplevel(self.root)
        setup_win.title("故事背景設定")
        setup_win.geometry("1300x1000")
        setup_win.configure(bg="#F0F4C3")
        fields = [("世界背景", "world", "西方奇幻世界"), ("角色名字", "name", "陳日"), ("性格描述", "personality", "勇敢且熱心腸"), ("角色目標", "goal", "拯救被魔王囚禁的公主")]
        entries = {}
        for label_text, key_name, hint in fields:
            tk.Label(setup_win, text=label_text, font=self.fonts["text"], bg="#F0F4C3").pack(pady=5)
            ent = tk.Entry(setup_win, font=self.fonts["text"], width=60)
            ent.insert(0, hint)
            ent.pack(pady=5)
            entries[key_name] = ent
        def confirm_start():
            cfg = {k: v.get() for k, v in entries.items()}
            setup_win.destroy()
            self.create_story(cfg)
        tk.Button(setup_win, text="生成劇本", font=self.fonts["btn"], bg="#8BC34A", fg="white", command=confirm_start).pack(pady=30)

    def create_story(self, config):
        for w in self.root.winfo_children(): w.destroy()
        tk.Label(self.root, text="正在為您撰寫劇本...\n請稍候片刻。", font=self.fonts["text"], bg="#FDFCF0").pack(pady=150)
        self.root.update()
        new_data = generate_full_story(config)
        if new_data:
            self.story_data = new_data
            save_json(SCENES_FILE, self.story_data)
            if messagebox.askyesno("保存劇本", "這個劇本生成成功了！您想將它收藏起來以便日後再次遊玩嗎？"):
                self.show_save_script_menu()
            else:
                self.current_scene_id = "scene_1"
                self.show_scene()
        else:
            messagebox.showwarning("提示", "AI 解析失敗。請再試一次。")
            self.show_main_menu()

    def show_scene(self, skip_speak=False):
        for w in self.root.winfo_children(): w.destroy()
        scene = self.story_data.get("scenes", {}).get(self.current_scene_id)
        if not scene:
            self.show_main_menu()
            return

        # top control bar
        ctrl_frame = tk.Frame(self.root, bg="#FDFCF0")
        ctrl_frame.pack(fill="x", padx=20, pady=5)
        tk.Button(ctrl_frame, text="A+ 放大", font=("Microsoft JhengHei", 16), command=lambda: self.change_font_size(4, "scene")).pack(side="right", padx=5)
        tk.Button(ctrl_frame, text="A- 縮小", font=("Microsoft JhengHei", 16), command=lambda: self.change_font_size(-4, "scene")).pack(side="right", padx=5)
        tk.Button(ctrl_frame, text="📜 查閱往事", font=("Microsoft JhengHei", 16), bg="#FFF9C4", command=self.show_history).pack(side="right", padx=15)
        
        # voice 語音控制
        tk.Button(ctrl_frame, text="🎤 語音控制", font=("Microsoft JhengHei", 16), bg="#BBDEFB", 
                  command=lambda: self.start_voice_input(scene.get("options", []))).pack(side="right", padx=5)
        
        if len(self.path_history) > 0:
            tk.Button(ctrl_frame, text="🔙 時光倒流", font=("Microsoft JhengHei", 16), bg="#FFCCBC", command=self.undo_move).pack(side="right", padx=5)

        tk.Label(ctrl_frame, text=f"位置：{self.current_scene_id}", font=("Arial", 10), bg="#FDFCF0", fg="gray").pack(side="left")

        # Canvas and Scrollbar
        canvas = tk.Canvas(self.root, bg="#FDFCF0", highlightthickness=0)
        scrollbar = tk.Scrollbar(self.root, orient="vertical", command=canvas.yview)
        scrollable_frame = tk.Frame(canvas, bg="#FDFCF0")

        scrollable_frame.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((700, 0), window=scrollable_frame, anchor="n") 
        canvas.configure(yscrollcommand=scrollbar.set)

        def _on_mousewheel(event):
            canvas.yview_scroll(int(-1*(event.delta/120)), "units")
        canvas.bind_all("<MouseWheel>", _on_mousewheel)

        scrollbar.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)

        description = scene.get("description", "")
        
        # History
        if not skip_speak and (not self.history or self.history[-1]['desc'] != description):
            self.history.append({"desc": description, "choice": ""})
            if len(self.history) > 10: self.history.pop(0)

        tk.Label(scrollable_frame, text=description, font=self.fonts["text"], 
                  bg="#FDFCF0", wraplength=1100, justify="left", padx=50, pady=30).pack()

        read_text = description
        options = scene.get("options", [])
        if options and isinstance(options, list):
            read_text += "。請從以下選項中選擇："
            for i, opt in enumerate(options):
                opt_text = opt.get("text", "探索下一步")
                read_text += f"。選項{i+1}：{opt_text}"
                tk.Button(scrollable_frame, text=opt_text, font=self.fonts["btn"], bg="#E1F5FE", height=2, width=40,
                          command=lambda s=opt.get("next_scene"), t=opt_text: self.go_to(s, t)).pack(pady=10, padx=100)
            
            tk.Button(scrollable_frame, text="💾 儲存目前進度", font=self.fonts["btn"], bg="#C8E6C9", height=1, width=40,
                      command=self.show_save_menu).pack(pady=15, padx=100)
            tk.Button(scrollable_frame, text="回主選單", font=self.fonts["btn"], bg="#FFCCBC", height=1, width=40,
                      command=self.show_main_menu).pack(pady=5)
        else:
            read_text += "。旅程圓滿完結。"
            tk.Label(scrollable_frame, text="旅程圓滿完結 ", font=self.fonts["btn"], fg="#4CAF50", bg="#FDFCF0").pack(pady=30)
            tk.Button(scrollable_frame, text="回主選單", font=self.fonts["btn"], command=self.show_main_menu).pack(pady=10)

        if not skip_speak:
            self.speak_text(read_text)

    def go_to(self, next_id, choice_text=""):
        if next_id in self.story_data.get("scenes", {}):
            self.path_history.append(self.current_scene_id)
            if self.history:
                self.history[-1]['choice'] = choice_text
            self.current_scene_id = next_id
            self.show_scene()
        else: self.show_main_menu()

    # function ---
    def show_save_script_menu(self):
        for w in self.root.winfo_children(): w.destroy()
        tk.Label(self.root, text="📜 選擇劇本收藏位置", font=self.fonts["title"], bg="#FDFCF0").pack(pady=50)
        for i in range(1, 5):
            path = os.path.join(SCRIPTS_DIR, f"script_slot_{i}.json")
            status = "(已有劇本)" if os.path.exists(path) else "(空)"
            tk.Button(self.root, text=f"劇本位置 {i} {status}", font=self.fonts["btn"], width=30, 
                      command=lambda s=i: self.perform_save_script(s)).pack(pady=10)
        tk.Button(self.root, text="直接開始不保存", font=self.fonts["btn"], bg="#FFCCBC", command=self.show_scene).pack(pady=30)

    def perform_save_script(self, slot):
        path = os.path.join(SCRIPTS_DIR, f"script_slot_{slot}.json")
        save_json(path, self.story_data)
        messagebox.showinfo("成功", f"劇本已收藏至 位置 {slot}！")
        self.current_scene_id = "scene_1"
        self.show_scene()

    def show_script_menu(self):
        for w in self.root.winfo_children(): w.destroy()
        tk.Label(self.root, text="📜 我的劇本收藏", font=self.fonts["title"], bg="#FDFCF0").pack(pady=50)
        found = False
        for i in range(1, 5):
            path = os.path.join(SCRIPTS_DIR, f"script_slot_{i}.json")
            if os.path.exists(path):
                found = True
                tk.Button(self.root, text=f"重玩劇本 {i}", font=self.fonts["btn"], width=30, bg="#FFF9C4",
                          command=lambda p=path: self.load_script_and_start(p)).pack(pady=10)
        if not found: tk.Label(self.root, text="目前還沒有收藏的劇本喔！", font=self.fonts["text"], bg="#FDFCF0").pack(pady=20)
        tk.Button(self.root, text="返回主選單", font=self.fonts["btn"], bg="#FFCCBC", command=self.show_main_menu).pack(pady=30)

    def load_script_and_start(self, path):
        data = load_json(path, {})
        if "scenes" in data:
            self.story_data = data
            self.current_scene_id = "scene_1"
            self.show_scene()

    def show_save_menu(self):
        for w in self.root.winfo_children(): w.destroy()
        tk.Label(self.root, text="💾 選擇儲存位置", font=self.fonts["title"], bg="#FDFCF0", fg="#4A4A4A").pack(pady=50)
        for i in range(1, 5):
            slot_file = os.path.join(SAVE_DIR, f"save_slot_{i}.json")
            btn_text = f"存檔 {i} {'(已有進度)' if os.path.exists(slot_file) else '(空)'}"
            tk.Button(self.root, text=btn_text, font=self.fonts["btn"], width=30, height=2, bg="#E8F5E9",
                      command=lambda slot=i: self.perform_save(slot)).pack(pady=10)
        tk.Button(self.root, text="取消並返回遊戲", font=self.fonts["btn"], width=30, height=2, bg="#FFCCBC", command=self.show_scene).pack(pady=30)

    def perform_save(self, slot):
        slot_file = os.path.join(SAVE_DIR, f"save_slot_{slot}.json")
        save_data = {"story_data": self.story_data, "current_scene_id": self.current_scene_id}
        save_json(slot_file, save_data)
        messagebox.showinfo("成功", f"進度已儲存至 存檔 {slot}！")
        self.show_scene()

    def show_load_menu(self):
        for w in self.root.winfo_children(): w.destroy()
        tk.Label(self.root, text="📂 讀取遊戲進度", font=self.fonts["title"], bg="#FDFCF0").pack(pady=50)
        for i in range(1, 5):
            slot_file = os.path.join(SAVE_DIR, f"save_slot_{i}.json")
            if os.path.exists(slot_file):
                tk.Button(self.root, text=f"讀取 存檔 {i}", font=self.fonts["btn"], width=30, height=2, bg="#FFF9C4",
                          command=lambda slot=i: self.perform_load(slot)).pack(pady=10)
            else:
                tk.Button(self.root, text=f"存檔 {i} (空)", font=self.fonts["btn"], width=30, height=2, bg="#E0E0E0", state=tk.DISABLED).pack(pady=10)
        tk.Button(self.root, text="回主選單", font=self.fonts["btn"], width=30, height=2, bg="#FFCCBC", command=self.show_main_menu).pack(pady=30)

    def perform_load(self, slot):
        slot_file = os.path.join(SAVE_DIR, f"save_slot_{slot}.json")
        data = load_json(slot_file, {})
        if "story_data" in data:
            self.story_data = data["story_data"]
            self.current_scene_id = data["current_scene_id"]
            self.show_scene()
        else: messagebox.showerror("錯誤", "無效存檔")

if __name__ == "__main__":
    root = tk.Tk()
    AdventureGame(root)
    root.mainloop()
