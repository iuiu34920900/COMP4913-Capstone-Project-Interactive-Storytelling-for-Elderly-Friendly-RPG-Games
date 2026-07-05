import json
import time
import sys
import io
from openai import OpenAI

# 強制解決 Windows 環境下的編碼問題
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

# --- API 金鑰配置 ---
# 請檢查您的 Key 是否有複製完整，建議將 Key 放入環境變數或確保無特殊字元
OPENAI_API_KEY = "Input your key" 
DEEPSEEK_API_KEY = "Imput key"

def get_prompt(config):
    return f"""
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

    【寫作風格】：
    - 每段 80-130 字，溫柔且富有畫面感的中文口語。
    - 禁止使用雙引號 (")，請用單引號 (')。
    - **嚴禁回傳 Markdown 標籤**，只回傳純 JSON。

    格式：{{ "scenes": {{ "scene_1": {{ "description": "...", "options": [ {{ "text": "...", "next_scene": "..." }} ] }} }} }}
    """

# --- 模型調用邏輯 ---

def call_model(config, provider="gpt4"):
    if provider == "gpt4":
        client = OpenAI(api_key=OPENAI_API_KEY)
        # 將模型更改為 gpt-4o，這是目前最穩定且具備 JSON Mode 的模型
        model_name = "gpt-4o" 
        base_url = None
    else:
        client = OpenAI(api_key=DEEPSEEK_API_KEY, base_url="https://api.deepseek.com")
        model_name = "deepseek-chat"
    
    try:
        response = client.chat.completions.create(
            model=model_name,
            messages=[{"role": "user", "content": get_prompt(config)}],
            # 確保模型輸出結構化的 JSON
            response_format={"type": "json_object"},
            temperature=0.7
        )
        content = response.choices[0].message.content
        return json.loads(content)
    except Exception as e:
        print(f"[{provider}] 錯誤: {str(e)}")
        # 如果是模型找不到，嘗試使用備用名稱 gpt-4-turbo
        if "model_not_found" in str(e) and provider == "gpt4":
            print("嘗試使用備用模型 gpt-4-turbo...")
            # 遞迴嘗試一次備用模型
            return call_model(config, provider="gpt4_backup") 
        return None

# 為了支援備用模型，稍微修改一下邏輯
def call_model_backup(config, model_name="gpt-4-turbo"):
    client = OpenAI(api_key=OPENAI_API_KEY)
    try:
        response = client.chat.completions.create(
            model=model_name,
            messages=[{"role": "user", "content": get_prompt(config)}],
            response_format={"type": "json_object"},
            temperature=0.7
        )
        return json.loads(response.choices[0].message.content)
    except:
        return None

# --- 執行生成並存檔 ---
def build_dataset(scenarios, provider="gpt4"):
    filename = f"gold_standard_{provider}.jsonl"
    print(f"\n🚀 開始使用 {provider} 生成黃金標準資料集...")
    
    # 使用 'a' 模式以便斷點續傳
    with open(filename, "a", encoding="utf-8") as f:
        for i, cfg in enumerate(scenarios):
            print(f"正在處理第 {i+1}/{len(scenarios)} 組: {cfg['name']} - {cfg['world']}")
            
            gold_json = call_model(cfg, provider=provider)
            
            if gold_json:
                data_pair = {"input": cfg, "gold_output": gold_json, "provider": provider}
                # 確保寫入時強制使用 utf-8
                f.write(json.dumps(data_pair, ensure_ascii=False) + "\n")
                f.flush() # 立即寫入硬碟
                print(f"✅ {cfg['name']} 儲存成功。")
            else:
                print(f"❌ {cfg['name']} 跳過。")
            
            time.sleep(1) 

# --- 測試案例 ---
scenarios = [
    {"name": "陳日", "personality": "勇敢", "world": "西方奇幻世界", "goal": "拯救被魔王囚禁的公主"},
    {"name": "李小龍", "personality": "十分看重人情", "world": "東方武俠世界", "goal": "成為武林盟主"},
    {"name": "圓堂", "personality": "永不放棄", "world": "現實足球場", "goal": "成為世界第一足球選手"},
    {"name": "莫克", "personality": "冷靜睿智", "world": "賽博龐克廢土", "goal": "修復城市最後的淨水系統"},
    {"name": "白婆婆", "personality": "慈祥且富有耐心", "world": "童話森林", "goal": "為迷路的小動物們舉辦慶典"},
    {"name": "林克", "personality": "好奇心旺盛", "world": "神秘地底王國", "goal": "尋找永恆之光"},
    {"name": "葉問", "personality": "低調內斂", "world": "近代佛山街道", "goal": "守護鄰里安全"},
    {"name": "艾莉絲", "personality": "充滿正義感", "world": "蒸氣龐克都市", "goal": "揭開工廠污染真相"},
    {"name": "老沈", "personality": "勤勞樸實", "world": "懷舊農村", "goal": "將荒廢梯田變為美果園"},
    {"name": "星海", "personality": "樂觀豁達", "world": "星際殖民艦", "goal": "尋找適合居住的新地球"}
]

# --- 執行 ---
if __name__ == "__main__":
    # 如果 DeepSeek 餘額不足，請先註解掉下面那行
    build_dataset(scenarios, provider="gpt4")
    # build_dataset(scenarios, provider="deepseek")
