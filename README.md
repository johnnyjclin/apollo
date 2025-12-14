# 🏷️ Apollo - AI Agent 拍賣遊戲 PoC

> 驗證 AI Agent 的 Payment Intent 行為與信任層必要性

## 📋 目錄

- [專案介紹](#專案介紹)
- [安裝步驟](#安裝步驟)
- [使用方式](#使用方式)
- [專案結構](#專案結構)
- [觀察重點](#觀察重點)

---

## 專案介紹

這個 PoC 透過**拍賣遊戲**來觀察 AI Agent 的行為：

1. **多個 Agent 競標物品** - 買家 vs 賣家
2. **談判過程 (Negotiation)** - 出價、還價、接受/拒絕
3. **支付決策** - 觀察 Agent 的 Payment Intent 是否正確

### 目標

驗證 AI Agent 可能產生的 Intent 錯誤，證明**信任層 (Trust Layer)** 的必要性。

---

## 安裝步驟

### 1. 安裝 Ollama

Ollama 是本地運行的 LLM，**免費且無限制**。

#### macOS

```bash
# 使用 Homebrew
brew install ollama

# 或從官網下載
# https://ollama.com/download
```

#### Linux

```bash
curl -fsSL https://ollama.com/install.sh | sh
```

#### Windows

從官網下載安裝程式：https://ollama.com/download

### 2. 下載模型

```bash
# 拉取 Llama 3.2 模型 (約 2GB)
ollama pull llama3.2
```

### 3. 啟動 Ollama 服務

```bash
# 在終端運行 (保持開啟)
ollama serve
```

### 4. 安裝 Python 依賴

```bash
cd apollo

# 建議使用虛擬環境
python -m venv venv
source venv/bin/activate  # macOS/Linux
# venv\Scripts\activate  # Windows

# 安裝依賴
pip install -r requirements.txt
```

### 5. 驗證安裝

```bash
# 檢查 Ollama 是否運行
curl http://localhost:11434/api/tags

# 應該看到類似輸出：
# {"models":[{"name":"llama3.2:latest",...}]}
```

---

## 使用方式

### 基本執行

```bash
# 確保 Ollama 正在運行
ollama serve  # 在另一個終端

# 運行拍賣遊戲
python run_auction.py
```

### 參數選項

```bash
# 模擬模式 (不使用 LLM，用於測試)
python run_auction.py --mock

# 設定物品底價
python run_auction.py --price 200

# 批次執行多場拍賣
python run_auction.py --batch 5
```

### 使用其他模型

```bash
# 設定環境變數使用不同模型
export OLLAMA_MODEL=llama3.1
python run_auction.py
```

---

## 專案結構

```
apollo/
├── agents/
│   ├── auction_agent.py    # 賣家/買家 Agent
│   └── base_agent.py       # 基礎 Agent 類
│
├── games/
│   └── auction.py          # 拍賣遊戲邏輯 (含 Negotiation)
│
├── wallet/
│   └── mock_wallet.py      # 模擬錢包
│
├── config/
│   └── env_example.txt     # 環境變數範本
│
├── run_auction.py          # 主程式
├── requirements.txt        # Python 依賴
└── README.md
```

---

## 觀察重點

### Agent 可能產生的 Intent 錯誤

| 錯誤類型 | 描述 | 範例 |
|----------|------|------|
| **金額錯誤** | 支付金額與成交價不符 | 成交 $150，卻要付 $200 |
| **收款方錯誤** | 付給錯誤對象 | 應付給賣家，卻付給另一個買家 |
| **邏輯錯誤** | 違反基本規則 | 賣家還價比買家出價更低 |
| **格式錯誤** | LLM 回應格式不正確 | 返回純文字而非 JSON |

### 實驗結果分析

運行後會看到：

```
📊 行為分析
============================================================

🤝 談判行為分析:
   接受次數: 1
   拒絕次數: 2
   還價次數: 5

💰 出價行為分析:
   總出價次數: 8
   最低出價: $100
   最高出價: $180

💳 Payment Intent 分析:
   選擇幣種: USDC
   支付金額: 150.05 USDC
   收款方: Seller_Alice
```

### 這些錯誤證明了什麼？

**信任層 (Trust Layer) 的必要性**：

- AI Agent 會產生不合理的決策
- LLM 輸出可能格式錯誤
- 需要驗證層來攔截錯誤的 Payment Intent

---

## 常見問題

### Ollama 連接失敗

```bash
# 確認 Ollama 正在運行
ps aux | grep ollama

# 重新啟動
ollama serve
```

### 模型下載太慢

```bash
# 使用較小的模型
ollama pull llama3.2:1b  # 1B 參數版本，約 700MB
export OLLAMA_MODEL=llama3.2:1b
```

### 記憶體不足

```bash
# 使用更小的模型
ollama pull phi3:mini
export OLLAMA_MODEL=phi3:mini
```

---

## 授權

MIT License

---

*專案代號: Apollo*
*建立日期: 2024-12*

