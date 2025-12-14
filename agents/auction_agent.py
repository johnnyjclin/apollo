"""
拍賣 Agent - 支援多種 LLM

包含：
1. SellerAgent - 賣家 Agent
2. BuyerAgent - 買家 Agent

支援的 LLM：
- Groq (免費，推薦) - GROQ_API_KEY
- Google Gemini - GOOGLE_API_KEY
"""

import os
import json
import re
from typing import Optional
from dataclasses import dataclass

from langchain_core.messages import HumanMessage, SystemMessage

# Ollama 導入 (本地運行，無限制)
try:
    from langchain_ollama import ChatOllama
    OLLAMA_AVAILABLE = True
except ImportError:
    OLLAMA_AVAILABLE = False

# Groq 導入 (免費且快速，部分地區限制)
try:
    from langchain_groq import ChatGroq
    GROQ_AVAILABLE = True
except ImportError:
    GROQ_AVAILABLE = False

# Gemini 導入
try:
    from langchain_google_genai import ChatGoogleGenerativeAI
    GEMINI_AVAILABLE = True
except ImportError:
    GEMINI_AVAILABLE = False

from wallet.mock_wallet import MockWallet, ExchangeRateService


def check_ollama_running() -> bool:
    """檢查 Ollama 是否在運行"""
    try:
        import urllib.request
        req = urllib.request.Request("http://localhost:11434/api/tags", method="GET")
        with urllib.request.urlopen(req, timeout=2) as response:
            return response.status == 200
    except:
        return False


def create_llm(api_key: str = None, provider: str = "auto"):
    """
    創建 LLM 實例
    
    優先順序: Ollama (本地) > Groq > Gemini
    
    Args:
        api_key: API Key (可選，會自動從環境變數讀取)
        provider: 指定提供者 (auto, ollama, groq, gemini)
    
    Returns:
        LLM 實例或 None
    """
    # 嘗試 Ollama (本地運行，無限制) - 自動檢測
    if (provider in ["auto", "ollama"]) and OLLAMA_AVAILABLE:
        if check_ollama_running():
            try:
                model = os.getenv("OLLAMA_MODEL", "llama3.2")
                llm = ChatOllama(
                    model=model,
                    temperature=0.7
                )
                # 測試連接
                return llm
            except Exception as e:
                print(f"⚠️ Ollama 初始化失敗: {e}")
        elif provider == "ollama":
            print("⚠️ Ollama 未運行！請先啟動: ollama serve")
    
    # 嘗試 Groq (免費且快，部分地區限制)
    groq_key = api_key if provider == "groq" else os.getenv("GROQ_API_KEY")
    if (provider in ["auto", "groq"]) and GROQ_AVAILABLE and groq_key:
        try:
            return ChatGroq(
                model="llama-3.1-8b-instant",
                temperature=0.7,
                api_key=groq_key
            )
        except Exception as e:
            print(f"⚠️ Groq 初始化失敗: {e}")
    
    # 嘗試 Gemini
    gemini_key = api_key if provider == "gemini" else os.getenv("GOOGLE_API_KEY")
    if (provider in ["auto", "gemini"]) and GEMINI_AVAILABLE and gemini_key:
        try:
            return ChatGoogleGenerativeAI(
                model="gemini-2.0-flash",
                temperature=0.7,
                google_api_key=gemini_key
            )
        except Exception as e:
            print(f"⚠️ Gemini 初始化失敗: {e}")
    
    return None


@dataclass
class AgentConfig:
    name: str
    personality: str  # aggressive, conservative, balanced
    budget: float  # 最大預算 (USD)


class BaseAuctionAgent:
    """拍賣 Agent 基類"""
    
    def __init__(
        self,
        name: str,
        wallet: MockWallet,
        exchange_service: ExchangeRateService,
        personality: str = "balanced",
        api_key: Optional[str] = None,
        provider: str = "auto"
    ):
        self.name = name
        self.wallet = wallet
        self.exchange_service = exchange_service
        self.personality = personality
        
        # 設置 LLM (自動選擇可用的提供者)
        self.llm = create_llm(api_key=api_key, provider=provider)
        
        if self.llm:
            provider_name = type(self.llm).__name__
            print(f"✅ {name}: 使用 {provider_name}")
        else:
            print(f"⚠️ {name}: 無可用 LLM，使用模擬模式")
    
    def _parse_json_response(self, content: str) -> dict:
        """解析 LLM 回應中的 JSON"""
        # 嘗試找到 JSON
        json_match = re.search(r'\{[^{}]*\}', content, re.DOTALL)
        if json_match:
            try:
                return json.loads(json_match.group())
            except json.JSONDecodeError:
                pass
        return {}
    
    def get_wallet_info(self) -> str:
        """獲取錢包信息字符串"""
        rates = self.exchange_service.get_all_rates()
        info = f"錢包餘額:\n"
        total = 0
        for token, balance in self.wallet.balances.items():
            rate = rates.get(token, 0)
            usd = balance * rate
            total += usd
            info += f"  {token}: {balance:.4f} (≈${usd:.2f})\n"
        info += f"總價值: ${total:.2f}"
        return info


class SellerAgent(BaseAuctionAgent):
    """
    賣家 Agent
    
    負責：
    1. 設定底價
    2. 回應出價（接受/拒絕/還價）
    3. 談判策略
    """
    
    def __init__(self, *args, min_acceptable_price: float = 0, **kwargs):
        super().__init__(*args, **kwargs)
        self.min_acceptable_price = min_acceptable_price
        
        self.system_prompt = f"""你是 {self.name}，一個拍賣賣家 Agent。

你的性格: {self.personality}
- aggressive: 追求最高價，不輕易降價
- conservative: 傾向快速成交，願意接受合理價格
- balanced: 平衡考慮

你的目標是賣出物品並獲得好價格。

在談判時，你需要決定：
1. accept - 接受出價
2. reject - 拒絕出價
3. counter - 還價

回覆格式 (JSON):
{{
    "action": "accept" 或 "reject" 或 "counter",
    "counter_amount": 還價金額 (只有 counter 時需要),
    "message": "你的理由"
}}
"""
    
    async def respond_to_bid(self, bid, item, reserve_price: float) -> dict:
        """
        回應買家出價
        """
        if not self.llm:
            return self._fallback_respond_to_bid(bid, reserve_price)
        
        prompt = f"""
有買家出價購買你的物品。

物品: {item.name}
底價: ${reserve_price}
買家: {bid.bidder}
出價: ${bid.amount}
買家理由: {bid.message}

請決定你的回應 (accept/reject/counter)。
如果選擇 counter，請給出你的還價金額。

回覆 JSON 格式:
{{
    "action": "accept" 或 "reject" 或 "counter",
    "counter_amount": 數字 (只有 counter 時需要),
    "message": "你的理由"
}}
"""
        
        try:
            response = await self.llm.ainvoke([
                SystemMessage(content=self.system_prompt),
                HumanMessage(content=prompt)
            ])
            
            result = self._parse_json_response(response.content)
            
            if not result.get("action"):
                result["action"] = "reject"
                result["message"] = response.content[:200]
            
            return result
            
        except Exception as e:
            print(f"  ⚠️ LLM 調用失敗: {e}")
            return self._fallback_respond_to_bid(bid, reserve_price)
    
    def _fallback_respond_to_bid(self, bid, reserve_price: float) -> dict:
        """無 LLM 時的備用邏輯"""
        if bid.amount >= reserve_price:
            return {
                "action": "accept",
                "message": "[模擬] 出價達到底價，接受"
            }
        elif bid.amount >= reserve_price * 0.9:
            return {
                "action": "counter",
                "counter_amount": reserve_price,
                "message": "[模擬] 出價接近底價，還價到底價"
            }
        else:
            return {
                "action": "reject",
                "message": "[模擬] 出價太低，拒絕"
            }


class BuyerAgent(BaseAuctionAgent):
    """
    買家 Agent
    
    負責：
    1. 評估物品價值
    2. 出價
    3. 回應還價
    4. 創建 Payment Intent
    """
    
    def __init__(self, *args, max_budget: float = 1000, **kwargs):
        super().__init__(*args, **kwargs)
        self.max_budget = max_budget
        
        self.system_prompt = f"""你是 {self.name}，一個拍賣買家 Agent。

你的性格: {self.personality}
- aggressive: 積極出價，願意付高價
- conservative: 謹慎出價，追求低價
- balanced: 平衡考慮

你的預算: ${self.max_budget}
{self.get_wallet_info()}

在出價時，考慮：
1. 物品的價值
2. 你的預算限制
3. 你的錢包餘額
4. 其他買家的競爭

回覆必須是 JSON 格式。
"""
    
    async def make_bid(self, item, current_price: float, bid_history: list) -> Optional[dict]:
        """
        對物品出價
        """
        if not self.llm:
            return self._fallback_make_bid(item, current_price)
        
        history_str = "\n".join([
            f"  - {b.bidder}: ${b.amount} ({b.status.value})"
            for b in bid_history[-5:]  # 只顯示最近 5 筆
        ]) if bid_history else "無"
        
        prompt = f"""
你正在參與拍賣。

物品: {item.name}
描述: {item.description}
當前價格: ${current_price}
你的預算: ${self.max_budget}

最近出價歷史:
{history_str}

{self.get_wallet_info()}

請決定你的出價。如果不想出價，回覆 null。

回覆 JSON 格式:
{{
    "amount": 出價金額 (數字),
    "reasoning": "你的出價理由"
}}

或者如果不出價:
null
"""
        
        try:
            response = await self.llm.ainvoke([
                SystemMessage(content=self.system_prompt),
                HumanMessage(content=prompt)
            ])
            
            content = response.content.strip()
            
            if content.lower() == "null" or "不出價" in content:
                return None
            
            result = self._parse_json_response(content)
            
            if not result.get("amount"):
                return None
            
            # 確保金額在預算內
            if result["amount"] > self.max_budget:
                result["amount"] = self.max_budget
                result["reasoning"] += " (已調整至預算上限)"
            
            return result
            
        except Exception as e:
            print(f"  ⚠️ LLM 調用失敗: {e}")
            return self._fallback_make_bid(item, current_price)
    
    def _fallback_make_bid(self, item, current_price: float) -> Optional[dict]:
        """無 LLM 時的備用邏輯"""
        import random
        
        # 隨機決定是否出價
        if random.random() < 0.3:
            return None
        
        # 出價比當前價格高 5-15%
        increase = random.uniform(0.05, 0.15)
        amount = min(current_price * (1 + increase), self.max_budget)
        
        return {
            "amount": round(amount, 2),
            "reasoning": f"[模擬] 在當前價格基礎上加價 {increase*100:.0f}%"
        }
    
    async def respond_to_counter(
        self,
        counter_amount: float,
        item,
        original_bid: float
    ) -> dict:
        """
        回應賣家還價
        """
        if not self.llm:
            return self._fallback_respond_to_counter(counter_amount, original_bid)
        
        prompt = f"""
賣家對你的出價進行了還價。

物品: {item.name}
你的原始出價: ${original_bid}
賣家還價: ${counter_amount}
你的預算: ${self.max_budget}

請決定你的回應：
1. accept - 接受還價，成交
2. reject - 拒絕，退出談判
3. counter - 繼續談判，給出新出價

回覆 JSON 格式:
{{
    "action": "accept" 或 "reject" 或 "counter",
    "new_amount": 新出價金額 (只有 counter 時需要),
    "message": "你的理由"
}}
"""
        
        try:
            response = await self.llm.ainvoke([
                SystemMessage(content=self.system_prompt),
                HumanMessage(content=prompt)
            ])
            
            result = self._parse_json_response(response.content)
            
            if not result.get("action"):
                result["action"] = "reject"
                result["message"] = response.content[:200]
            
            return result
            
        except Exception as e:
            print(f"  ⚠️ LLM 調用失敗: {e}")
            return self._fallback_respond_to_counter(counter_amount, original_bid)
    
    def _fallback_respond_to_counter(self, counter_amount: float, original_bid: float) -> dict:
        """無 LLM 時的備用邏輯"""
        if counter_amount <= self.max_budget:
            # 接受還價
            return {
                "action": "accept",
                "message": "[模擬] 還價在預算內，接受"
            }
        else:
            # 嘗試折中
            middle = (original_bid + counter_amount) / 2
            if middle <= self.max_budget:
                return {
                    "action": "counter",
                    "new_amount": round(middle, 2),
                    "message": "[模擬] 嘗試折中價格"
                }
            else:
                return {
                    "action": "reject",
                    "message": "[模擬] 超出預算，拒絕"
                }
    
    async def create_payment_intent(
        self,
        amount_usd: float,
        recipient: str,
        item_name: str,
        auction_id: str
    ) -> dict:
        """
        創建支付意圖
        
        這是觀察 Payment Intent 錯誤的關鍵點
        """
        rates = self.exchange_service.get_all_rates()
        
        # 計算可用支付選項
        options = []
        for token, balance in self.wallet.balances.items():
            rate = rates.get(token, 0)
            if rate <= 0:
                continue
            required = amount_usd / rate
            if balance >= required:
                options.append({
                    "token": token,
                    "required": round(required, 6),
                    "balance": round(balance, 6),
                    "rate": round(rate, 4)
                })
        
        if not self.llm:
            return self._fallback_payment_intent(amount_usd, recipient, options)
        
        prompt = f"""
你需要支付拍賣款項。

拍賣物品: {item_name}
拍賣ID: {auction_id}
應付金額: ${amount_usd} USD
收款方: {recipient}

你的支付選項:
{json.dumps(options, indent=2, ensure_ascii=False)}

{self.get_wallet_info()}

請選擇支付方式。

回覆 JSON 格式:
{{
    "token": "選擇的幣種",
    "amount": 支付數量,
    "amount_usd": 等值 USD,
    "recipient": "收款方",
    "reasoning": "選擇理由"
}}
"""
        
        try:
            response = await self.llm.ainvoke([
                SystemMessage(content=self.system_prompt),
                HumanMessage(content=prompt)
            ])
            
            result = self._parse_json_response(response.content)
            
            # 確保必要欄位存在
            if not result.get("token") and options:
                result["token"] = options[0]["token"]
            if not result.get("amount") and options:
                result["amount"] = options[0]["required"]
            if not result.get("amount_usd"):
                result["amount_usd"] = amount_usd
            if not result.get("recipient"):
                result["recipient"] = recipient
            if not result.get("reasoning"):
                result["reasoning"] = response.content[:200]
            
            return result
            
        except Exception as e:
            print(f"  ⚠️ LLM 調用失敗: {e}")
            return self._fallback_payment_intent(amount_usd, recipient, options)
    
    def _fallback_payment_intent(
        self,
        amount_usd: float,
        recipient: str,
        options: list
    ) -> dict:
        """無 LLM 時的備用邏輯"""
        if not options:
            return {
                "token": "USDC",
                "amount": amount_usd,
                "amount_usd": amount_usd,
                "recipient": recipient,
                "reasoning": "[模擬] 餘額不足"
            }
        
        # 優先穩定幣
        priority = {"USDT": 1, "USDC": 2, "DAI": 3, "ETH": 10}
        sorted_opts = sorted(options, key=lambda x: priority.get(x["token"], 5))
        chosen = sorted_opts[0]
        
        return {
            "token": chosen["token"],
            "amount": chosen["required"],
            "amount_usd": amount_usd,
            "recipient": recipient,
            "reasoning": f"[模擬] 優先使用穩定幣 {chosen['token']}"
        }


def create_auction_agents(
    seller_name: str = "Seller",
    buyer_names: list[str] = None,
    api_key: Optional[str] = None
):
    """
    創建拍賣 Agents
    """
    from wallet.mock_wallet import (
        MockWallet, 
        ExchangeRateService, 
        DEFAULT_EXCHANGE_RATES
    )
    
    if buyer_names is None:
        buyer_names = ["Buyer_A", "Buyer_B"]
    
    exchange_service = ExchangeRateService(DEFAULT_EXCHANGE_RATES)
    
    # 賣家
    seller_wallet = MockWallet.create(
        owner=seller_name,
        initial_balances={"USDC": 100.0}  # 賣家不需要太多
    )
    
    seller = SellerAgent(
        name=seller_name,
        wallet=seller_wallet,
        exchange_service=exchange_service,
        personality="balanced",
        min_acceptable_price=100,
        api_key=api_key
    )
    
    # 買家
    buyers = []
    personalities = ["aggressive", "conservative", "balanced"]
    
    for i, name in enumerate(buyer_names):
        wallet = MockWallet.create(
            owner=name,
            initial_balances={
                "ETH": 0.5,
                "USDC": 500.0,
                "DAI": 300.0,
            }
        )
        
        buyer = BuyerAgent(
            name=name,
            wallet=wallet,
            exchange_service=exchange_service,
            personality=personalities[i % len(personalities)],
            max_budget=300 + i * 100,  # 不同預算
            api_key=api_key
        )
        buyers.append(buyer)
    
    print(f"✅ 創建賣家: {seller_name}")
    for buyer in buyers:
        print(f"✅ 創建買家: {buyer.name} (預算: ${buyer.max_budget}, 性格: {buyer.personality})")
    
    return seller, buyers, exchange_service

