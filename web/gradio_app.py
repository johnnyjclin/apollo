#!/usr/bin/env python3
"""
🎨 Apollo - AI Agent 拍賣遊戲 (Web UI)

用途：
- 視覺化展示 AI Agent 的拍賣談判
- 即時觀察 Payment Intent 決策
- 方便 Demo 和演示

功能：
1. 可調參數：買家數量、回合數、加價幅度等
2. 市場事件：隨機匯率波動、手續費變化
3. 支付決策分析：比較 Agent 選擇 vs 最佳選擇
4. Intent Error 檢測：標記不合理的決策

觀察重點：
- Agent 選擇了哪個幣種支付？
- 是否選擇了手續費最低的幣種？
- 多付了多少錢？(Intent Error)

執行方式：
    python web/gradio_app.py
    # 打開 http://localhost:7860
"""

import asyncio
import sys
import random
from pathlib import Path
from datetime import datetime
from typing import Optional, List, Dict

# 確保路徑正確
sys.path.insert(0, str(Path(__file__).parent.parent))

import gradio as gr

# 載入 .env
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from games.auction import AuctionGame, AuctionItem, AuctionStatus, Bid
from agents.auction_agent import create_auction_agents, SellerAgent, BuyerAgent
from wallet.mock_wallet import MockWallet, ExchangeRateService, DEFAULT_EXCHANGE_RATES, TOKEN_FEES, IntentValidator


# ============================================================
# 遊戲配置
# ============================================================

class GameConfig:
    """遊戲配置"""
    def __init__(
        self,
        item_name: str = "稀有 NFT 藝術品",
        reserve_price: float = 100,
        max_rounds: int = 5,
        num_buyers: int = 2,
        min_bid_increment: float = 5,  # 最低加價百分比
        max_negotiation_rounds: int = 3,
        enable_market_events: bool = True,
        buyer_personalities: List[str] = None,
        volatility: float = 0.02,
    ):
        self.item_name = item_name
        self.reserve_price = reserve_price
        self.max_rounds = max_rounds
        self.num_buyers = num_buyers
        self.min_bid_increment = min_bid_increment
        self.max_negotiation_rounds = max_negotiation_rounds
        self.enable_market_events = enable_market_events
        self.buyer_personalities = buyer_personalities or ["aggressive", "conservative", "balanced"]
        self.volatility = volatility


# ============================================================
# 市場事件系統
# ============================================================

MARKET_EVENTS = [
    {"name": "📈 市場利好", "effect": "ETH 匯率上漲 5%", "token": "ETH", "change": 0.05},
    {"name": "📉 市場恐慌", "effect": "ETH 匯率下跌 5%", "token": "ETH", "change": -0.05},
    {"name": "💰 穩定幣脫鉤警告", "effect": "USDT 手續費臨時提高", "token": "USDT", "fee_change": 0.5},
    {"name": "🔥 Gas 費暴漲", "effect": "所有交易手續費 +0.2%", "all_fee_change": 0.2},
    {"name": "🎉 促銷活動", "effect": "USDC 手續費減半", "token": "USDC", "fee_change": -0.05},
    {"name": "⚡ 網絡擁堵", "effect": "交易確認時間延長", "delay": True},
]


def apply_market_event(exchange_service: ExchangeRateService, event: dict):
    """應用市場事件"""
    if "token" in event and "change" in event:
        token = event["token"]
        if token in exchange_service.base_rates:
            exchange_service.base_rates[token] *= (1 + event["change"])
    
    if "all_fee_change" in event:
        for token in TOKEN_FEES:
            TOKEN_FEES[token] += event["all_fee_change"]
    
    if "token" in event and "fee_change" in event:
        token = event["token"]
        if token in TOKEN_FEES:
            TOKEN_FEES[token] = max(0.01, TOKEN_FEES[token] + event["fee_change"])


# ============================================================
# 支付決策分析
# ============================================================

def analyze_payment_decision(
    buyer_name: str,
    amount_usd: float,
    chosen_token: str,
    wallet: MockWallet,
    exchange_service: ExchangeRateService
) -> dict:
    """
    分析 Agent 的支付決策是否最佳
    
    這是觀察 Payment Intent 的核心功能！
    檢查 Agent 是否選擇了最優的支付方式。
    """
    # 計算 Agent 選擇的成本
    chosen_rate = exchange_service.get_rate(chosen_token)
    chosen_amount = amount_usd / chosen_rate
    chosen_fee_pct = TOKEN_FEES.get(chosen_token, 0.5)
    chosen_fee = chosen_amount * (chosen_fee_pct / 100)
    chosen_total = chosen_amount + chosen_fee
    chosen_total_usd = chosen_total * chosen_rate
    
    # 找出最佳選擇
    options = wallet.get_payment_options(amount_usd, exchange_service)
    affordable = [o for o in options if o.is_affordable]
    
    result = {
        "buyer": buyer_name,
        "amount_usd": amount_usd,
        "chosen": {
            "token": chosen_token,
            "amount": chosen_amount,
            "fee": chosen_fee,
            "fee_pct": chosen_fee_pct,
            "total": chosen_total,
            "total_usd": chosen_total_usd,
            "rate": chosen_rate
        },
        "optimal": None,
        "all_options": [],
        "is_optimal": True,
        "extra_cost_usd": 0,
        "extra_cost_pct": 0,
        "error_type": None,
        "analysis": ""
    }
    
    # 記錄所有選項
    for opt in options:
        total_usd = (opt.total_amount) * opt.rate
        result["all_options"].append({
            "token": opt.token,
            "amount": opt.required_amount,
            "fee": opt.fee_amount,
            "fee_pct": opt.fee_percent,
            "total": opt.total_amount,
            "total_usd": total_usd,
            "rate": opt.rate,
            "affordable": opt.is_affordable
        })
    
    if not affordable:
        result["error_type"] = "NO_AFFORDABLE_OPTION"
        result["analysis"] = "⚠️ 沒有任何幣種能負擔此金額"
        return result
    
    # 找最佳選項 (總成本最低)
    best = min(affordable, key=lambda x: (x.total_amount * x.rate))
    best_total_usd = best.total_amount * best.rate
    
    result["optimal"] = {
        "token": best.token,
        "amount": best.required_amount,
        "fee": best.fee_amount,
        "fee_pct": best.fee_percent,
        "total": best.total_amount,
        "total_usd": best_total_usd,
        "rate": best.rate
    }
    
    # 比較
    if chosen_token != best.token:
        extra_cost = chosen_total_usd - best_total_usd
        if extra_cost > 0.01:  # 超過 $0.01 算有差異
            result["is_optimal"] = False
            result["extra_cost_usd"] = extra_cost
            result["extra_cost_pct"] = (extra_cost / amount_usd) * 100
            result["error_type"] = "SUBOPTIMAL_TOKEN_CHOICE"
            result["analysis"] = f"❌ Agent 選擇了 {chosen_token}，但 {best.token} 更划算！多付了 ${extra_cost:.2f} ({result['extra_cost_pct']:.1f}%)"
        else:
            result["analysis"] = f"✅ 選擇接近最優 (差異 < $0.01)"
    else:
        result["analysis"] = f"✅ Agent 選擇了最優的幣種 {chosen_token}"
    
    return result


def format_payment_analysis(analysis: dict) -> str:
    """格式化支付決策分析為 Markdown"""
    lines = []
    lines.append("### 💳 支付決策分析")
    lines.append("")
    lines.append(f"**買家**: {analysis['buyer']}")
    lines.append(f"**成交價**: ${analysis['amount_usd']:.2f}")
    lines.append("")
    
    # Agent 的選擇
    chosen = analysis["chosen"]
    lines.append("#### Agent 選擇")
    if analysis["is_optimal"]:
        lines.append(f"✅ **{chosen['token']}**")
    else:
        lines.append(f"❌ **{chosen['token']}** (非最優)")
    lines.append(f"- 匯率: ${chosen['rate']:.2f}")
    lines.append(f"- 需支付: {chosen['amount']:.4f} {chosen['token']}")
    lines.append(f"- 手續費: {chosen['fee']:.4f} ({chosen['fee_pct']}%)")
    lines.append(f"- **總計**: {chosen['total']:.4f} {chosen['token']} ≈ **${chosen['total_usd']:.2f}**")
    lines.append("")
    
    # 最佳選擇
    if analysis["optimal"] and not analysis["is_optimal"]:
        opt = analysis["optimal"]
        lines.append("#### 最佳選擇")
        lines.append(f"✅ **{opt['token']}**")
        lines.append(f"- 匯率: ${opt['rate']:.2f}")
        lines.append(f"- 需支付: {opt['amount']:.4f} {opt['token']}")
        lines.append(f"- 手續費: {opt['fee']:.4f} ({opt['fee_pct']}%)")
        lines.append(f"- **總計**: {opt['total']:.4f} {opt['token']} ≈ **${opt['total_usd']:.2f}**")
        lines.append("")
    
    # Intent Error 警告
    if not analysis["is_optimal"]:
        lines.append("#### ⚠️ INTENT ERROR 檢測")
        lines.append(f"```")
        lines.append(f"錯誤類型: {analysis['error_type']}")
        lines.append(f"多付金額: ${analysis['extra_cost_usd']:.2f} ({analysis['extra_cost_pct']:.1f}%)")
        lines.append(f"```")
        lines.append("")
        lines.append(f"> {analysis['analysis']}")
        lines.append("")
        lines.append("**這就是 Payment Intent 可能「走偏」的例子！**")
        lines.append("Agent 沒有選擇手續費最低的幣種，導致多付了錢。")
    else:
        lines.append(f"> {analysis['analysis']}")
    
    # 所有選項比較表
    lines.append("")
    lines.append("#### 📊 所有支付選項比較")
    lines.append("")
    lines.append("| 幣種 | 匯率 | 手續費 | 總成本(USD) | 狀態 |")
    lines.append("|------|------|--------|-------------|------|")
    
    for opt in sorted(analysis["all_options"], key=lambda x: x["total_usd"]):
        status = ""
        if opt["token"] == analysis["chosen"]["token"]:
            status = "← Agent選擇"
        if analysis["optimal"] and opt["token"] == analysis["optimal"]["token"]:
            if status:
                status = "← Agent選擇 ✅最優"
            else:
                status = "✅ 最優"
        if not opt["affordable"]:
            status = "❌ 餘額不足"
        
        lines.append(f"| {opt['token']} | ${opt['rate']:.2f} | {opt['fee_pct']}% | ${opt['total_usd']:.2f} | {status} |")
    
    return "\n".join(lines)


# ============================================================
# 主要遊戲邏輯
# ============================================================

def format_message(role: str, name: str, action: str, amount: float = None, message: str = "", token: str = None):
    """格式化聊天消息"""
    emoji = "🏪" if role == "seller" else "🛒"
    
    token_info = f" ({token})" if token else ""
    
    action_text = {
        "bid": f"💰 出價 ${amount:.2f}{token_info}" if amount else "💰 出價",
        "accept": f"✅ 接受 ${amount:.2f}" if amount else "✅ 接受",
        "reject": "❌ 拒絕",
        "counter": f"🔄 還價 ${amount:.2f}" if amount else "🔄 還價"
    }.get(action, action)
    
    msg = f"{emoji} **{name}**: {action_text}"
    if message:
        msg += f"\n> _{message[:150]}..._" if len(message) > 150 else f"\n> _{message}_"
    
    return msg


async def run_auction_async(
    item_name: str,
    reserve_price: float,
    max_rounds: int,
    num_buyers: int,
    min_bid_increment: float,
    max_negotiation_rounds: int,
    enable_market_events: bool,
    volatility: float,
    llm_provider: str = "auto",
    progress=gr.Progress()
):
    """執行拍賣"""
    
    messages = []
    chat_history = []
    intent_validator = IntentValidator()
    
    def add_message(msg):
        messages.append(msg)
        return "\n\n---\n\n".join(messages)
    
    # 初始化
    progress(0.05, desc="初始化...")
    add_message("🔧 **正在初始化 AI Agents...**")
    yield add_message(""), [], None
    
    # 創建匯率服務（帶波動性）
    exchange_service = ExchangeRateService(
        base_rates=DEFAULT_EXCHANGE_RATES.copy(),
        volatility=volatility
    )
    
    # 創建賣家錢包
    seller_wallet = MockWallet.create(
        owner="Seller",
        initial_balances={"USDC": 100.0, "ETH": 0.5}
    )
    
    # 創建賣家 Agent
    from agents.auction_agent import create_llm
    llm = create_llm(provider=llm_provider)
    
    # 顯示使用的 LLM
    if llm:
        provider_name = type(llm).__name__
        add_message(f"🤖 **使用 LLM**: {provider_name}")
    else:
        add_message("🤖 **模擬模式** (無 LLM)")
    yield "\n\n---\n\n".join(messages), [], None
    
    seller = SellerAgent(
        name="Seller",
        wallet=seller_wallet,
        exchange_service=exchange_service,
        personality="balanced",
        min_acceptable_price=reserve_price,
        provider=llm_provider
    )
    
    # 創建買家
    buyers = []
    personalities = ["aggressive", "conservative", "balanced", "careless"]
    
    for i in range(num_buyers):
        personality = personalities[i % len(personalities)]
        
        # 不同買家有不同的幣種組合
        if i == 0:
            balances = {"USDC": 500.0, "ETH": 0.05, "DAI": 100.0}
        elif i == 1:
            balances = {"ETH": 0.15, "USDC": 100.0, "USDT": 300.0}
        elif i == 2:
            balances = {"USDC": 200.0, "DAI": 200.0, "ETH": 0.08}
        else:
            balances = {"USDT": 400.0, "DAI": 100.0, "USDC": 50.0}
        
        wallet = MockWallet.create(
            owner=f"Buyer_{chr(65+i)}",
            initial_balances=balances,
            budget=sum(balances.get(t, 0) * DEFAULT_EXCHANGE_RATES.get(t, 1) for t in balances) * 0.8
        )
        
        buyer = BuyerAgent(
            name=f"Buyer_{chr(65+i)}",
            wallet=wallet,
            exchange_service=exchange_service,
            personality=personality,
            max_budget=wallet.budget_limit,
            provider=llm_provider
        )
        buyers.append(buyer)
    
    # 顯示 Agents 信息
    llm_name = type(llm).__name__ if llm else "模擬模式"
    agents_info = f"""### 🤖 Agents 準備就緒 ({llm_name})

**賣家**: {seller.name}
- 底價: ${reserve_price}

**買家** ({num_buyers} 位):
"""
    for b in buyers:
        total_value = b.wallet.get_total_value_usd(exchange_service.base_rates)
        agents_info += f"- **{b.name}** (性格: {b.personality}, 資產: ${total_value:.0f})\n"
        agents_info += f"  錢包: {', '.join([f'{t}: {a:.2f}' for t, a in b.wallet.balances.items()])}\n"
    
    add_message(agents_info)
    
    # 顯示規則
    rules_info = f"""### 📋 遊戲規則

| 規則 | 設定值 |
|------|--------|
| 最大回合數 | {max_rounds} |
| 最低加價幅度 | {min_bid_increment}% |
| 最大談判輪數 | {max_negotiation_rounds} |
| 市場事件 | {'開啟' if enable_market_events else '關閉'} |
| 匯率波動 | ±{volatility*100:.1f}% |

**手續費表**:
"""
    for token, fee in TOKEN_FEES.items():
        rules_info += f"- {token}: {fee}%\n"
    
    add_message(rules_info)
    yield "\n\n---\n\n".join(messages), [], None
    
    # 創建拍賣物品
    item = AuctionItem(
        item_id=f"item_{datetime.now().strftime('%H%M%S')}",
        name=item_name,
        description="一件具有收藏價值的稀有物品",
        reserve_price=reserve_price,
        seller=seller.name
    )
    
    # 創建遊戲
    game = AuctionGame(
        seller_agent=seller,
        buyer_agents=buyers,
        item=item,
        max_rounds=max_rounds
    )
    
    add_message(f"""### 🏷️ 拍賣開始!

**物品**: {item_name}  
**底價**: ${reserve_price}
**最低出價**: ${reserve_price * (1 + min_bid_increment/100):.2f} (底價 + {min_bid_increment}%)
""")
    yield "\n\n---\n\n".join(messages), chat_history, None
    
    # 追蹤統計
    stats = {
        "total_bids": 0,
        "rejected_bids": 0,
        "intent_errors": 0,
        "market_events": 0
    }
    
    # 執行拍賣
    game.state.status = AuctionStatus.OPEN
    current_min_bid = reserve_price * (1 + min_bid_increment/100)
    
    for round_num in range(1, max_rounds + 1):
        game.current_round = round_num
        progress(0.1 + round_num * 0.15, desc=f"回合 {round_num}/{max_rounds}")
        
        # 市場事件
        if enable_market_events and random.random() < 0.3:
            event = random.choice(MARKET_EVENTS)
            apply_market_event(exchange_service, event)
            stats["market_events"] += 1
            add_message(f"### 🎲 市場事件: {event['name']}\n{event['effect']}")
            yield "\n\n---\n\n".join(messages), chat_history, None
        
        add_message(f"### 📍 回合 {round_num}/{max_rounds}\n當前最低出價: ${current_min_bid:.2f}")
        yield "\n\n---\n\n".join(messages), chat_history, None
        
        # 收集出價
        round_bids = []
        
        for buyer in buyers:
            bid_response = await buyer.make_bid(
                item=game.item,
                current_price=game.state.current_price or reserve_price,
                bid_history=game.state.bids
            )
            
            if bid_response:
                amount = bid_response.get("amount", 0)
                token = bid_response.get("token", "USDC")
                reasoning = bid_response.get("reasoning", "")
                
                stats["total_bids"] += 1
                
                # 驗證出價
                validation = intent_validator.validate_payment(
                    wallet=buyer.wallet,
                    token=token,
                    amount=exchange_service.convert_from_usd(token, amount),
                    amount_usd=amount,
                    exchange_service=exchange_service,
                    context={"min_bid": current_min_bid}
                )
                
                # 創建 Bid
                bid = Bid(
                    bid_id=f"bid_{round_num}_{buyer.name}",
                    bidder=buyer.name,
                    amount=amount,
                    timestamp=datetime.now(),
                    token=token,
                    message=reasoning,
                    validation_errors=validation["errors"],
                    validation_warnings=validation["warnings"]
                )
                
                if validation["errors"]:
                    stats["intent_errors"] += len(validation["errors"])
                    game.state.intent_errors.extend(validation["errors"])
                
                if validation["warnings"]:
                    game.state.intent_warnings.extend(validation["warnings"])
                
                game.state.bids.append(bid)
                
                # 檢查是否符合最低出價
                if amount < current_min_bid:
                    bid.status = "rejected"
                    stats["rejected_bids"] += 1
                    error_msg = f"❌ 出價被拒絕 (${amount:.2f} < 最低 ${current_min_bid:.2f})"
                    add_message(f"**{buyer.name}** {error_msg}")
                    chat_history.append({"role": "user", "content": f"**{buyer.name}**: {error_msg}"})
                else:
                    round_bids.append(bid)
                    msg = f"💰 出價 ${amount:.2f} ({token})"
                    add_message(f"**{buyer.name}**: {msg}\n> _{reasoning[:80]}..._")
                    chat_history.append({"role": "user", "content": f"**{buyer.name}**: {msg}\n\n_{reasoning[:100]}_"})
                
                # 顯示驗證問題
                if validation["errors"] or validation["warnings"]:
                    issue_msg = ""
                    for err in validation["errors"]:
                        issue_msg += f"\n  ❌ {err['type']}: {err['message'][:50]}"
                    for warn in validation["warnings"]:
                        issue_msg += f"\n  ⚠️ {warn['type']}: {warn['message'][:50]}"
                    add_message(f"**Intent 檢測**:{issue_msg}")
                
                yield "\n\n---\n\n".join(messages), chat_history, None
            else:
                add_message(f"**{buyer.name}**: ⏭️ 不出價")
                yield "\n\n---\n\n".join(messages), chat_history, None
        
        if not round_bids:
            add_message("😢 本回合無有效出價")
            continue
        
        # 找最高出價
        highest_bid = max(round_bids, key=lambda b: b.amount)
        game.state.current_price = highest_bid.amount
        game.state.highest_bidder = highest_bid.bidder
        
        add_message(f"📊 **最高出價**: {highest_bid.bidder} - ${highest_bid.amount:.2f}")
        
        # 更新最低出價
        current_min_bid = highest_bid.amount * (1 + min_bid_increment/100)
        
        # 談判
        add_message(f"### 🤝 談判: {seller.name} vs {highest_bid.bidder}")
        yield "\n\n---\n\n".join(messages), chat_history, None
        
        # 談判循環
        current_bid = highest_bid
        buyer_agent = next(b for b in buyers if b.name == highest_bid.bidder)
        negotiation_round = 0
        
        while negotiation_round < max_negotiation_rounds:
            negotiation_round += 1
            
            # 賣家回應
            seller_response = await seller.respond_to_bid(
                bid=current_bid,
                item=game.item,
                reserve_price=reserve_price
            )
            
            action = seller_response.get("action", "reject")
            
            if action == "accept":
                add_message(f"✅ **{seller.name}** 接受出價 ${current_bid.amount:.2f}!")
                chat_history.append({"role": "assistant", "content": f"**{seller.name}**: ✅ 接受出價!"})
                
                # 處理支付
                game.state.winner = current_bid.bidder
                game.state.final_price = current_bid.amount
                game.state.payment_token = current_bid.token
                game.state.status = AuctionStatus.SOLD
                
                # 計算支付金額
                rate = exchange_service.get_rate(current_bid.token)
                token_amount = current_bid.amount / rate
                fee = token_amount * (TOKEN_FEES.get(current_bid.token, 0.5) / 100)
                
                game.state.payment_token_amount = token_amount
                game.state.payment_fee = fee
                
                break
            
            elif action == "reject":
                reason = seller_response.get("reasoning", "")
                add_message(f"❌ **{seller.name}** 拒絕出價\n> _{reason}_")
                chat_history.append({"role": "assistant", "content": f"**{seller.name}**: ❌ 拒絕\n\n_{reason}_"})
                break
            
            elif action == "counter":
                counter_amount = seller_response.get("counter_amount", current_bid.amount * 1.1)
                reason = seller_response.get("reasoning", "")
                
                # 驗證還價邏輯
                counter_validation = intent_validator.validate_counter_offer(
                    counter_amount=counter_amount,
                    original_amount=current_bid.amount,
                    is_seller=True
                )
                
                if counter_validation["errors"]:
                    game.state.intent_errors.extend(counter_validation["errors"])
                    stats["intent_errors"] += len(counter_validation["errors"])
                    add_message(f"⚠️ **Intent Error**: 賣家還價 ${counter_amount:.2f} 低於買家出價 ${current_bid.amount:.2f}!")
                
                add_message(f"🔄 **{seller.name}** 還價 ${counter_amount:.2f}\n> _{reason}_")
                chat_history.append({"role": "assistant", "content": f"**{seller.name}**: 🔄 還價 ${counter_amount:.2f}"})
                yield "\n\n---\n\n".join(messages), chat_history, None
                
                # 買家回應
                buyer_response = await buyer_agent.respond_to_counter(
                    counter_amount=counter_amount,
                    item=game.item,
                    original_bid=current_bid.amount
                )
                
                buyer_action = buyer_response.get("action", "reject")
                
                if buyer_action == "accept":
                    add_message(f"✅ **{buyer_agent.name}** 接受還價 ${counter_amount:.2f}!")
                    chat_history.append({"role": "user", "content": f"**{buyer_agent.name}**: ✅ 接受!"})
                    
                    game.state.winner = buyer_agent.name
                    game.state.final_price = counter_amount
                    game.state.payment_token = current_bid.token
                    game.state.status = AuctionStatus.SOLD
                    
                    rate = exchange_service.get_rate(current_bid.token)
                    token_amount = counter_amount / rate
                    fee = token_amount * (TOKEN_FEES.get(current_bid.token, 0.5) / 100)
                    
                    game.state.payment_token_amount = token_amount
                    game.state.payment_fee = fee
                    break
                
                elif buyer_action == "reject":
                    reason = buyer_response.get("reasoning", "")
                    add_message(f"❌ **{buyer_agent.name}** 拒絕還價\n> _{reason}_")
                    chat_history.append({"role": "user", "content": f"**{buyer_agent.name}**: ❌ 拒絕"})
                    break
                
                elif buyer_action == "counter":
                    new_amount = buyer_response.get("new_amount") or buyer_response.get("amount") or (current_bid.amount * 1.05)
                    new_token = buyer_response.get("token") or current_bid.token or "USDC"
                    reason = buyer_response.get("reasoning", "")
                    
                    # 確保 new_amount 是數字
                    if new_amount is None:
                        new_amount = current_bid.amount * 1.05
                    
                    # 驗證
                    counter_validation = intent_validator.validate_counter_offer(
                        counter_amount=new_amount,
                        original_amount=current_bid.amount,
                        is_seller=False
                    )
                    
                    if counter_validation["warnings"]:
                        game.state.intent_warnings.extend(counter_validation["warnings"])
                    
                    add_message(f"🔄 **{buyer_agent.name}** 再出價 ${new_amount:.2f}")
                    chat_history.append({"role": "user", "content": f"**{buyer_agent.name}**: 🔄 ${new_amount:.2f}"})
                    
                    # 更新 bid
                    current_bid = Bid(
                        bid_id=f"bid_{round_num}_{buyer_agent.name}_counter",
                        bidder=buyer_agent.name,
                        amount=new_amount,
                        timestamp=datetime.now(),
                        token=new_token,
                        message=reason
                    )
                    game.state.bids.append(current_bid)
                    
                yield "\n\n---\n\n".join(messages), chat_history, None
        
        if game.state.status == AuctionStatus.SOLD:
            break
        
        yield "\n\n---\n\n".join(messages), chat_history, None
    
    # 結果
    progress(0.95, desc="生成結果...")
    
    payment_analysis_md = ""
    
    if game.state.status == AuctionStatus.SOLD:
        # 🔍 支付決策分析 - 這是觀察 Payment Intent 的核心！
        winner_agent = next((b for b in buyers if b.name == game.state.winner), None)
        if winner_agent and game.state.payment_token:
            analysis = analyze_payment_decision(
                buyer_name=game.state.winner,
                amount_usd=game.state.final_price,
                chosen_token=game.state.payment_token,
                wallet=winner_agent.wallet,
                exchange_service=exchange_service
            )
            payment_analysis_md = format_payment_analysis(analysis)
            
            # 如果有 Intent Error，記錄到統計
            if not analysis["is_optimal"]:
                stats["intent_errors"] += 1
                game.state.intent_errors.append({
                    "type": analysis["error_type"],
                    "message": f"多付了 ${analysis['extra_cost_usd']:.2f} ({analysis['extra_cost_pct']:.1f}%)"
                })
        
        result_md = f"""## 🎉 拍賣成功!

### 📋 交易詳情

| 項目 | 內容 |
|------|------|
| 得標者 | **{game.state.winner}** |
| 成交價 | **${game.state.final_price:.2f}** |
| 支付幣種 | {game.state.payment_token} |
| 代幣數量 | {game.state.payment_token_amount:.4f} |
| 手續費 | {game.state.payment_fee:.4f} ({TOKEN_FEES.get(game.state.payment_token, 0.5)}%) |

---

{payment_analysis_md}

---

### 📊 統計

| 指標 | 數值 |
|------|------|
| 總出價次數 | {stats['total_bids']} |
| 被拒絕出價 | {stats['rejected_bids']} |
| 市場事件 | {stats['market_events']} |
| Intent Errors | {stats['intent_errors']} |
"""
        
        if game.state.intent_errors:
            result_md += "\n### ⚠️ 所有 Intent Errors\n"
            for err in game.state.intent_errors[:10]:
                result_md += f"- ❌ **{err['type']}**: {err['message']}\n"
        
        if game.state.intent_warnings:
            result_md += "\n### ⚡ 警告\n"
            for warn in game.state.intent_warnings[:5]:
                result_md += f"- ⚠️ **{warn['type']}**: {warn['message']}\n"
    else:
        result_md = f"""## 😢 拍賣失敗

沒有買家願意出價或談判破裂

### 📊 統計

| 指標 | 數值 |
|------|------|
| 總出價次數 | {stats['total_bids']} |
| 被拒絕出價 | {stats['rejected_bids']} |
| Intent Errors | {stats['intent_errors']} |
"""
    
    add_message(result_md)
    progress(1.0, desc="完成!")
    yield "\n\n---\n\n".join(messages), chat_history, result_md


def run_auction_wrapper(
    item_name,
    reserve_price,
    max_rounds,
    num_buyers,
    min_bid_increment,
    max_negotiation_rounds,
    enable_market_events,
    volatility,
    llm_provider
):
    """同步包裝器"""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
    try:
        async_gen = run_auction_async(
            item_name,
            reserve_price,
            max_rounds,
            num_buyers,
            min_bid_increment,
            max_negotiation_rounds,
            enable_market_events,
            volatility,
            llm_provider
        )
        
        while True:
            try:
                result = loop.run_until_complete(async_gen.__anext__())
                yield result
            except StopAsyncIteration:
                break
    finally:
        loop.close()


# ============================================================
# Gradio UI
# ============================================================

with gr.Blocks(
    title="Apollo - AI Agent 拍賣遊戲"
) as demo:
    
    gr.Markdown("""
    # 🏷️ Apollo - AI Agent 拍賣遊戲
    
    **觀察 AI Agents 的談判行為與 Payment Intent 錯誤**
    
    這個 PoC 讓多個 AI Agent 進行複雜的拍賣談判，觀察它們可能產生的錯誤決策。
    """)
    
    with gr.Row():
        with gr.Column(scale=1):
            gr.Markdown("### ⚙️ 基本設定")
            
            item_name = gr.Textbox(
                label="物品名稱",
                value="稀有 NFT 藝術品",
                placeholder="輸入拍賣物品名稱"
            )
            
            reserve_price = gr.Slider(
                label="底價 (USD)",
                minimum=50,
                maximum=1000,
                value=100,
                step=10
            )
            
            num_buyers = gr.Slider(
                label="買家數量",
                minimum=2,
                maximum=5,
                value=3,
                step=1
            )
            
            gr.Markdown("### 🎮 遊戲規則")
            
            max_rounds = gr.Slider(
                label="最大回合數",
                minimum=3,
                maximum=10,
                value=5,
                step=1
            )
            
            min_bid_increment = gr.Slider(
                label="最低加價幅度 (%)",
                minimum=1,
                maximum=20,
                value=5,
                step=1
            )
            
            max_negotiation_rounds = gr.Slider(
                label="最大談判輪數",
                minimum=1,
                maximum=5,
                value=3,
                step=1
            )
            
            gr.Markdown("### 📈 市場設定")
            
            enable_market_events = gr.Checkbox(
                label="啟用市場事件 (匯率波動、手續費變化)",
                value=True
            )
            
            volatility = gr.Slider(
                label="匯率波動程度 (%)",
                minimum=0,
                maximum=10,
                value=2,
                step=0.5
            )
            
            gr.Markdown("### 🤖 LLM 設定")
            
            llm_provider = gr.Dropdown(
                label="LLM 提供者",
                choices=["auto", "ollama", "gemini", "groq", "mock"],
                value="auto",
                info="auto = Ollama > Groq > Gemini"
            )
            
            start_btn = gr.Button("🚀 開始拍賣", variant="primary", size="lg")
            
            gr.Markdown("""
            ---
            ### 📝 觀察重點
            
            - **幣種選擇**: Agent 是否選擇手續費低的幣種?
            - **出價邏輯**: 是否符合最低加價規則?
            - **還價合理性**: 賣家還價是否低於買家出價?
            - **預算控制**: 是否超出預算?
            """)
        
        with gr.Column(scale=2):
            gr.Markdown("### 📜 拍賣過程")
            
            output_log = gr.Markdown(
                value="設定參數後點擊「開始拍賣」...",
                label="拍賣記錄"
            )
            
            with gr.Accordion("💬 談判對話", open=True):
                chat_display = gr.Chatbot(
                    label="賣家 ↔ 買家",
                    height=400
                )
            
            result_display = gr.Markdown(
                label="結果",
                visible=True
            )
    
    # 綁定事件
    start_btn.click(
        fn=run_auction_wrapper,
        inputs=[
            item_name,
            reserve_price,
            max_rounds,
            num_buyers,
            min_bid_increment,
            max_negotiation_rounds,
            enable_market_events,
            volatility,
            llm_provider
        ],
        outputs=[output_log, chat_display, result_display]
    )


if __name__ == "__main__":
    print("\n" + "="*60)
    print("🏷️  Apollo - AI Agent 拍賣遊戲 (進階版)")
    print("="*60)
    print("\n📍 啟動後會自動打開瀏覽器")
    print("   按 Ctrl+C 停止服務器\n")
    
    demo.launch(
        server_name="0.0.0.0",
        server_port=7860,
        share=False
    )
