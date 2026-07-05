import json
import numpy as np
import pandas as pd  # 確保有安裝: pip install pandas
from nltk.translate.bleu_score import sentence_bleu, SmoothingFunction
from rouge_score import rouge_scorer
from bert_score import score as bert_score_func
from google import genai
import os
from datetime import datetime

# --- 1. 配置 (請填入你的金鑰) ---
API_KEY = "APIkey"
client = genai.Client(api_key=API_KEY)
MODEL_NAME = "gemini-flash-latest" 

# --- 2. 評估器類別 ---
class StoryEvaluator:
    def __init__(self):
        self.rouge_scorer = rouge_scorer.RougeScorer(['rouge1', 'rougeL'], use_stemmer=True)
        self.smoothie = SmoothingFunction().method1

    def check_structural_integrity(self, generated_data):
        results = {"scene_count": 0, "dead_ends": 0, "ending_count": 0, "logical_pass": False}
        if not generated_data or "scenes" not in generated_data:
            return results
        
        scenes = generated_data.get("scenes", {})
        results["scene_count"] = len(scenes)
        valid_scene_ids = set(scenes.keys())
        
        for sid, content in scenes.items():
            options = content.get("options", [])
            if not options:
                results["ending_count"] += 1
            else:
                for opt in options:
                    if opt.get("next_scene") not in valid_scene_ids:
                        results["dead_ends"] += 1
        
        # 及格標準：20場景、0死路、至少1個結局
        if (results["scene_count"] == 20 and results["dead_ends"] == 0 and results["ending_count"] >= 1):
            results["logical_pass"] = True
        return results

    def calculate_metrics(self, reference_text, candidate_text):
        if not candidate_text:
            return {"bleu": 0, "rouge1": 0, "rougeL": 0, "bert_f1": 0}
        ref_for_rouge = " ".join(list(reference_text))
        can_for_rouge = " ".join(list(candidate_text))
        ref_tokens = list(reference_text)
        can_tokens = list(candidate_text)
        bleu = sentence_bleu([ref_tokens], can_tokens, smoothing_function=self.smoothie)
        rouge = self.rouge_scorer.score(ref_for_rouge, can_for_rouge)
        P, R, F1 = bert_score_func([candidate_text], [reference_text], lang="zh", verbose=False)
        
        return {
            "bleu": bleu,
            "rouge1": rouge['rouge1'].fmeasure,
            "rougeL": rouge['rougeL'].fmeasure,
            "bert_f1": F1.item()
        }

# --- 3. 模型對接轉接器 ---
def adapter_generate(config):
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
        clean_text = raw_text.replace("```json", "").replace("```", "").strip()
        start, end = clean_text.find('{'), clean_text.rfind('}') + 1
        return json.loads(clean_text[start:end])
    except:
        return {}

# --- 4. 批次執行與存檔邏輯 ---
def run_benchmark(jsonl_file):
    evaluator = StoryEvaluator()
    gold_data = []
    
    with open(jsonl_file, 'r', encoding='utf-8') as f:
        for line in f:
            item = json.loads(line)
            gold_data.append((item["input"], item["gold_output"]))

    rows = [] # 用於存入 CSV 的細節
    pass_count = 0

    print(f"🚀 開始評估 Gemini 模型 ({len(gold_data)} 筆案例)...")

    for i, (config, gold_json) in enumerate(gold_data):
        print(f"[{i+1}/{len(gold_data)}] 測試角色: {config['name']}...", end=" ", flush=True)
        
        gen_json = adapter_generate(config)
        struct = evaluator.check_structural_integrity(gen_json)
        
        gold_text = "".join([s["description"] for s in gold_json["scenes"].values()])
        gen_text = "".join([s.get("description", "") for s in gen_json.get("scenes", {}).values()])
        
        metrics = evaluator.calculate_metrics(gold_text, gen_text)
        
        if struct["logical_pass"]: pass_count += 1
        
        # 紀錄結果
        rows.append({
            "角色": config["name"],
            "結構及格": "是" if struct["logical_pass"] else "否",
            "場景數": struct["scene_count"],
            "BERTScore": round(metrics["bert_f1"], 4),
            "ROUGE-1": round(metrics["rouge1"], 4),
            "ROUGE-L": round(metrics["rougeL"], 4),
            "BLEU": round(metrics["bleu"], 4)
        })
        print("完成！")

    # 5. 輸出報告與匯出 CSV
    df = pd.DataFrame(rows)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    csv_filename = f"evaluation_report_{timestamp}.csv"
    df.to_csv(csv_filename, index=False, encoding="utf-8-sig")

    print("\n" + "="*40)
    print("📈 評估最終彙整")
    print(f"結構合格率: {pass_count / len(gold_data):.2%}")
    print(f"平均 BERTScore: {df['BERTScore'].mean():.4f}")
    print(f"平均 ROUGE-1:  {df['ROUGE-1'].mean():.4f}")
    print(f"平均 ROUGE-L:  {df['ROUGE-L'].mean():.4f}")
    print(f"平均 BLEU:     {df['BLEU'].mean():.4f}")
    print(f"詳細報表已存為: {csv_filename}")
    print("="*40)

if __name__ == "__main__":
    run_benchmark("gold_standard_qwen.jsonl")
