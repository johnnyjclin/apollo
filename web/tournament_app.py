#!/usr/bin/env python3
"""
🏆 Apollo - AI 拍賣錦標賽 (Tournament Mode)

4 個不同 AI Model 對戰的拍賣遊戲
觀察 Payment Intent 和決策行為

執行方式：
    python web/tournament_app.py
"""

import asyncio
import sys
import os
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

from games.tournament import (
    TournamentEngine, 
    TournamentItem, 
    PlayerState,
    GamePhase,
    BidResult,
    IntentErrorType
)


# ============================================================
# 遊戲風格 CSS
# ============================================================

CUSTOM_CSS = """
/* 遊戲主題風格 */
.gradio-container {
    background: linear-gradient(135deg, #1a1a2e 0%, #16213e 50%, #0f3460 100%) !important;
    min-height: 100vh;
}

/* 修復輸入框文字顏色 - 白底黑字 */
input[type="text"], textarea {
    background-color: #ffffff !important;
    color: #000000 !important;
}

/* 下拉選單樣式 */
select, .wrap.svelte-1gfkn6j {
    background-color: #ffffff !important;
    color: #000000 !important;
}

/* Gradio 輸入框 */
.gr-input, .gr-text-input {
    background-color: #ffffff !important;
    color: #000000 !important;
}

/* 標題樣式 */
.title-text {
    background: linear-gradient(90deg, #ffd700, #ff6b6b, #4ecdc4);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    font-size: 2.5em !important;
    font-weight: bold;
    text-align: center;
    padding: 20px;
    text-shadow: 2px 2px 4px rgba(0,0,0,0.3);
}

/* 玩家卡片 */
.player-card {
    background: linear-gradient(145deg, #2d2d44, #1a1a2e);
    border-radius: 15px;
    padding: 15px;
    margin: 10px;
    border: 2px solid #4ecdc4;
    box-shadow: 0 4px 15px rgba(78, 205, 196, 0.3);
}

/* 物品卡片 */
.item-card {
    background: linear-gradient(145deg, #3d3d5c, #2d2d44);
    border-radius: 20px;
    padding: 20px;
    margin: 15px auto;
    max-width: 400px;
    border: 3px solid #ffd700;
    box-shadow: 0 6px 20px rgba(255, 215, 0, 0.4);
    text-align: center;
}

/* 按鈕樣式 */
.game-btn {
    background: linear-gradient(145deg, #4ecdc4, #44a3aa) !important;
    border: none !important;
    border-radius: 25px !important;
    padding: 15px 30px !important;
    font-size: 1.2em !important;
    font-weight: bold !important;
    color: white !important;
    cursor: pointer;
    transition: all 0.3s ease;
    box-shadow: 0 4px 15px rgba(78, 205, 196, 0.5);
}

.game-btn:hover {
    transform: translateY(-2px);
    box-shadow: 0 6px 20px rgba(78, 205, 196, 0.7);
}

/* 排行榜 */
.leaderboard {
    background: linear-gradient(145deg, #2d2d44, #1a1a2e);
    border-radius: 15px;
    padding: 20px;
    border: 2px solid #ffd700;
}

/* Intent Error 警告 */
.intent-error {
    background: linear-gradient(145deg, #ff6b6b, #ee5a5a);
    border-radius: 10px;
    padding: 10px 15px;
    margin: 5px 0;
    color: white;
    font-weight: bold;
}

/* 成功訊息 */
.success-msg {
    background: linear-gradient(145deg, #4ecdc4, #44a3aa);
    border-radius: 10px;
    padding: 10px 15px;
    margin: 5px 0;
    color: white;
}

/* 回合指示器 */
.round-indicator {
    font-size: 1.5em;
    font-weight: bold;
    color: #ffd700;
    text-align: center;
    padding: 10px;
    border-bottom: 2px solid #ffd700;
    margin-bottom: 15px;
}

/* 金額顯示 */
.money {
    color: #4ecdc4;
    font-weight: bold;
    font-family: 'Courier New', monospace;
}

/* 玩家頭像 */
.player-avatar {
    width: 60px;
    height: 60px;
    border-radius: 50%;
    display: inline-block;
    text-align: center;
    line-height: 60px;
    font-size: 2em;
    margin-right: 10px;
}

/* 動畫效果 */
@keyframes pulse {
    0% { transform: scale(1); }
    50% { transform: scale(1.05); }
    100% { transform: scale(1); }
}

.winning {
    animation: pulse 1s infinite;
    border-color: #ffd700 !important;
}

/* 破產效果 */
.bankrupt {
    opacity: 0.5;
    filter: grayscale(100%);
}
"""


# ============================================================
# AI Agent 包裝器
# ============================================================

class TournamentAgent:
    """錦標賽 AI Agent"""
    
    def __init__(self, name: str, model_type: str, player_id: str):
        self.name = name
        self.model_type = model_type
        self.player_id = player_id
        self.llm = None
        self._init_llm()
    
    def _init_llm(self):
        """初始化 LLM"""
        # 支援不同 Ollama 模型
        if self.model_type.startswith("ollama:"):
            # 格式: ollama:llama3.2, ollama:mistral, etc.
            ollama_model = self.model_type.split(":")[1]
            try:
                from langchain_ollama import ChatOllama
                self.llm = ChatOllama(model=ollama_model, temperature=0.7)
                print(f"✅ {self.name}: 使用 Ollama ({ollama_model})")
                return
            except Exception as e:
                print(f"⚠️ {self.name}: Ollama 初始化失敗: {e}")
        
        # 其他 provider
        from agents.auction_agent import create_llm
        self.llm = create_llm(provider=self.model_type)
        
        if self.llm:
            print(f"✅ {self.name}: 使用 {type(self.llm).__name__}")
        else:
            print(f"⚠️ {self.name}: 使用模擬模式")
    
    async def decide_bid(
        self, 
        item: TournamentItem, 
        cash: float,
        other_players: List[Dict],
        round_num: int,
        total_rounds: int
    ) -> Dict:
        """決定出價"""
        if not self.llm:
            # 模擬模式
            return self._fallback_bid(item, cash)
        
        from langchain_core.messages import HumanMessage, SystemMessage
        
        # 構建 prompt
        others_info = "\n".join([
            f"  - {p['name']} ({p['model']}): 現金 ${p['cash']:.0f}, 物品 {p['items']} 件"
            for p in other_players
        ])
        
        prompt = f"""你是拍賣錦標賽的參賽者 {self.name}。

【當前狀態】
- 回合: {round_num}/{total_rounds}
- 你的現金: ${cash:.2f}

【本輪物品】
- 名稱: {item.name}
- 描述: {item.description}
- 專家提示: {item.hint}
- 估價範圍: ${item.estimate_low:.0f} - ${item.estimate_high:.0f}

【其他玩家】
{others_info}

【規則提醒】
1. 出價不能超過你的現金
2. 最高出價者得標
3. 物品真實價值在遊戲結束時揭曉
4. ⚠️ 重要：真實價值可能遠高於估價（賺錢）或遠低於估價（虧錢）
5. 遊戲結束時，現金 + 物品真實價值 = 總分

根據描述和提示，判斷這件物品值不值得競標，以及願意出多少價。

回覆 JSON 格式:
{{
    "bid": 出價金額 (數字，0 表示不出價),
    "reasoning": "出價理由 (簡短說明你的判斷)"
}}
"""
        
        try:
            response = await self.llm.ainvoke([
                SystemMessage(content="你是一個精明的拍賣競標者，目標是最大化最終得分。請務必用正確的 JSON 格式回覆。"),
                HumanMessage(content=prompt)
            ])
            
            content = response.content.strip()
            print(f"  📝 {self.name} 回應: {content[:100]}...")
            
            # 解析 JSON - 更強健的解析
            import json
            import re
            
            # 嘗試多種 JSON 提取方式
            result = None
            
            # 方式 1: 標準 JSON
            json_match = re.search(r'\{[^{}]*\}', content, re.DOTALL)
            if json_match:
                try:
                    result = json.loads(json_match.group())
                except:
                    pass
            
            # 方式 2: 修復常見錯誤（單引號改雙引號）
            if not result:
                try:
                    fixed = content.replace("'", '"')
                    json_match = re.search(r'\{[^{}]*\}', fixed, re.DOTALL)
                    if json_match:
                        result = json.loads(json_match.group())
                except:
                    pass
            
            # 方式 3: 提取數字
            if not result:
                bid_match = re.search(r'bid["\s:]+(\d+(?:\.\d+)?)', content, re.IGNORECASE)
                if bid_match:
                    result = {
                        "bid": float(bid_match.group(1)),
                        "reasoning": "從回應中提取"
                    }
            
            if result:
                return {
                    "bid": float(result.get("bid", 0)),
                    "reasoning": result.get("reasoning", "")[:100]
                }
                
        except Exception as e:
            print(f"  ⚠️ {self.name} LLM 錯誤: {e}")
        
        return self._fallback_bid(item, cash)
    
    def _fallback_bid(self, item: TournamentItem, cash: float) -> Dict:
        """備用出價邏輯"""
        # 隨機決定是否出價
        if random.random() < 0.2:
            return {"bid": 0, "reasoning": "觀望中"}
        
        # 出價在估價範圍內
        min_bid = item.estimate_low * 0.8
        max_bid = min(item.estimate_high, cash * 0.6)
        
        if max_bid < min_bid:
            return {"bid": 0, "reasoning": "資金不足"}
        
        bid = random.uniform(min_bid, max_bid)
        
        return {
            "bid": round(bid, 2),
            "reasoning": "策略性出價"
        }


# ============================================================
# 遊戲管理器
# ============================================================

class TournamentManager:
    """錦標賽管理器"""
    
    def __init__(self):
        self.engine: Optional[TournamentEngine] = None
        self.agents: Dict[str, TournamentAgent] = {}
    
    def create_game(
        self,
        player_configs: List[Dict],  # [{"name": "...", "model": "..."}]
        total_rounds: int = 10,
        starting_cash: float = 1000.0
    ):
        """創建遊戲"""
        self.engine = TournamentEngine(
            total_rounds=total_rounds,
            starting_cash=starting_cash,
            enable_negotiation=True
        )
        self.agents = {}
        
        for config in player_configs:
            player = self.engine.add_player(
                name=config["name"],
                model=config["model"]
            )
            
            agent = TournamentAgent(
                name=config["name"],
                model_type=config["model"],
                player_id=player.player_id
            )
            self.agents[player.player_id] = agent
        
        return self.engine.state
    
    async def run_round(self) -> Dict:
        """執行一個回合"""
        if not self.engine:
            raise ValueError("遊戲未初始化")
        
        state = self.engine.state
        item = state.current_item
        
        round_log = []
        round_log.append(f"## 🎯 第 {state.current_round} 輪 / {state.total_rounds}")
        round_log.append("")
        round_log.append("### 📦 拍賣物品")
        round_log.append(f"**{item.name}**")
        round_log.append("")
        round_log.append(f"📝 **描述**: {item.description}")
        round_log.append("")
        round_log.append(f"💡 **專家提示**: _{item.hint}_")
        round_log.append("")
        round_log.append(f"💵 **估價範圍**: ${item.estimate_low:.0f} - ${item.estimate_high:.0f}")
        round_log.append("")
        round_log.append(f"❓ **真實價值**: ??? (可能高於或低於估價)")
        round_log.append("")
        
        # 顯示當前玩家狀態
        round_log.append("### 👥 玩家狀態")
        round_log.append("| 玩家 | Model | 現金 | 物品 | 狀態 |")
        round_log.append("|------|-------|------|------|------|")
        for p in state.players.values():
            status = "💀" if p.is_bankrupt else "🎮"
            round_log.append(f"| {p.name} | `{p.model}` | ${p.cash:.0f} | {len(p.items)} | {status} |")
        round_log.append("")
        
        # 收集所有玩家的出價
        round_log.append("### 💬 出價過程")
        round_log.append("")
        bids_info = []
        
        for player_id, agent in self.agents.items():
            player = state.players[player_id]
            
            if not player.is_active or player.is_bankrupt:
                round_log.append(f"❌ **{player.name}**: 已破產，無法出價")
                continue
            
            # 獲取其他玩家資訊
            other_players = [
                {
                    "name": p.name,
                    "model": p.model,
                    "cash": p.cash,
                    "items": len(p.items)
                }
                for pid, p in state.players.items()
                if pid != player_id and p.is_active
            ]
            
            round_log.append(f"**🤖 {player.name}** (`{player.model}`) 思考中...")
            
            # AI 決策
            decision = await agent.decide_bid(
                item=item,
                cash=player.cash,
                other_players=other_players,
                round_num=state.current_round,
                total_rounds=state.total_rounds
            )
            
            bid_amount = decision.get("bid", 0)
            reasoning = decision.get("reasoning", "無")
            
            if bid_amount > 0:
                bid = self.engine.submit_bid(
                    player_id=player_id,
                    amount=bid_amount,
                    reasoning=reasoning
                )
                
                status_emoji = "🥇 最高" if bid.result == BidResult.WINNING else "📊"
                error_flag = ""
                
                if bid.intent_errors:
                    error_flag = "\n   - ⚠️ **Intent Error**: "
                    error_flag += ", ".join([e["message"][:50] for e in bid.intent_errors])
                
                bids_info.append({
                    "name": player.name,
                    "model": player.model,
                    "amount": bid_amount,
                    "result": bid.result.value,
                    "errors": bid.intent_errors,
                    "reasoning": reasoning
                })
                
                round_log.append(f"   - 💰 出價: **${bid_amount:.2f}**")
                round_log.append(f"   - 💭 理由: _{reasoning}_")
                round_log.append(f"   - 📊 狀態: {status_emoji}{error_flag}")
            else:
                round_log.append(f"   - ⏭️ 決定不出價")
                round_log.append(f"   - 💭 理由: _{reasoning}_")
            
            round_log.append("")
        
        # 結算回合
        result = self.engine.end_auction_round()
        
        round_log.append("### 🏁 本輪結果")
        round_log.append("")
        
        if result.winner:
            winner_player = next(p for p in state.players.values() if p.name == result.winner)
            round_log.append(f"🎉 **得標者**: **{result.winner}** (`{winner_player.model}`)")
            round_log.append(f"💰 **成交價**: **${result.winning_bid:.2f}**")
            round_log.append(f"💵 **剩餘現金**: ${winner_player.cash:.0f}")
            
            # 顯示所有出價比較
            if bids_info:
                round_log.append("")
                round_log.append("**出價彙總**:")
                round_log.append("| 玩家 | 出價 | 結果 |")
                round_log.append("|------|------|------|")
                for b in sorted(bids_info, key=lambda x: x["amount"], reverse=True):
                    result_emoji = "🏆 得標" if b["name"] == result.winner else "❌"
                    round_log.append(f"| {b['name']} | ${b['amount']:.2f} | {result_emoji} |")
        else:
            round_log.append("😢 **本輪流標** - 無人出價或所有出價無效")
        
        # Intent Errors
        if result.intent_errors:
            round_log.append("")
            round_log.append("### ⚠️ 本輪 Intent Errors")
            for err in result.intent_errors:
                round_log.append(f"- ❌ **{err['type']}**: {err['message']}")
        
        # 談判階段（每3回合進行一次）
        if state.current_round % 3 == 0 and state.current_round < state.total_rounds:
            round_log.append("")
            round_log.append("### 🤝 談判階段")
            round_log.append("")
            
            # 尋找可能的交換機會
            active_players = [p for p in state.players.values() if p.is_active and not p.is_bankrupt]
            trades_proposed = []
            
            for player in active_players:
                if len(player.items) > 0:
                    # 有物品的玩家可能提出交換
                    for other in active_players:
                        if other.player_id != player.player_id and len(other.items) > 0:
                            # 簡化的談判邏輯：隨機決定是否提出交換
                            if random.random() < 0.3:  # 30% 機率提出交換
                                my_item = random.choice(player.items)
                                their_item = random.choice(other.items)
                                
                                # 計算估價差異決定現金補貼
                                my_est = (my_item.estimate_low + my_item.estimate_high) / 2
                                their_est = (their_item.estimate_low + their_item.estimate_high) / 2
                                cash_diff = their_est - my_est
                                
                                if cash_diff > 0 and player.cash >= cash_diff:
                                    # 需要補貼現金
                                    round_log.append(f"💬 **{player.name}** 向 **{other.name}** 提議:")
                                    round_log.append(f"   - 用 {my_item.name} + ${cash_diff:.0f} 換 {their_item.name}")
                                    
                                    # 對方決定是否接受 (簡化：50% 機率接受)
                                    if random.random() < 0.5:
                                        # 執行交換
                                        player.items.remove(my_item)
                                        other.items.append(my_item)
                                        other.items.remove(their_item)
                                        player.items.append(their_item)
                                        player.cash -= cash_diff
                                        other.cash += cash_diff
                                        
                                        # 轉移成本記錄
                                        if my_item.item_id in player.item_costs:
                                            other.item_costs[my_item.item_id] = player.item_costs.pop(my_item.item_id)
                                        if their_item.item_id in other.item_costs:
                                            player.item_costs[their_item.item_id] = other.item_costs.pop(their_item.item_id)
                                        
                                        round_log.append(f"   - ✅ **{other.name}** 接受交換！")
                                        trades_proposed.append(True)
                                    else:
                                        round_log.append(f"   - ❌ **{other.name}** 拒絕交換")
                                        trades_proposed.append(False)
                                    
                                    round_log.append("")
                                    break  # 每人每輪最多提一次
            
            if not trades_proposed:
                round_log.append("_本輪無人提出交換提議_")
                round_log.append("")
        
        return {
            "log": "\n".join(round_log),
            "bids": bids_info,
            "winner": result.winner,
            "winning_bid": result.winning_bid,
            "intent_errors": result.intent_errors
        }
    
    def get_leaderboard_md(self, reveal: bool = False) -> str:
        """獲取排行榜 Markdown"""
        if not self.engine:
            return ""
        
        state = self.engine.state
        leaderboard = state.get_leaderboard(reveal_true_value=reveal)
        
        lines = ["## 🏆 排行榜", ""]
        lines.append("| 排名 | 玩家 | Model | 資產 | 狀態 |")
        lines.append("|------|------|-------|------|------|")
        
        medals = ["🥇", "🥈", "🥉", "4️⃣"]
        
        for i, (name, score) in enumerate(leaderboard):
            player = next(p for p in state.players.values() if p.name == name)
            medal = medals[i] if i < 4 else f"{i+1}"
            status = "💀 破產" if player.is_bankrupt else "✅ 活躍"
            lines.append(
                f"| {medal} | {name} | {player.model} | ${score:.0f} | {status} |"
            )
        
        return "\n".join(lines)
    
    def get_player_cards_md(self) -> str:
        """獲取玩家卡片 Markdown"""
        if not self.engine:
            return ""
        
        state = self.engine.state
        lines = []
        
        avatars = ["🤖", "🦾", "🧠", "⚡"]
        colors = ["#4ecdc4", "#ff6b6b", "#ffd700", "#9b59b6"]
        
        for i, player in enumerate(state.players.values()):
            avatar = avatars[i % len(avatars)]
            status = "💀" if player.is_bankrupt else "✅"
            
            lines.append(f"### {avatar} {player.name} ({player.model})")
            lines.append(f"- 💰 現金: **${player.cash:.0f}**")
            lines.append(f"- 🎨 物品: **{len(player.items)}** 件")
            lines.append(f"- ⚠️ 錯誤: **{len(player.intent_errors)}** 次")
            lines.append(f"- 狀態: {status}")
            lines.append("")
        
        return "\n".join(lines)


# ============================================================
# Gradio UI
# ============================================================

# 全域遊戲管理器
game_manager = TournamentManager()


def run_tournament_generator(
    p1_name, p1_model,
    p2_name, p2_model,
    p3_name, p3_model,
    p4_name, p4_model,
    total_rounds,
    starting_cash
):
    """執行完整錦標賽 (Generator 版本，支援實時更新 UI)"""
    players = [
        {"name": p1_name, "model": p1_model},
        {"name": p2_name, "model": p2_model},
        {"name": p3_name, "model": p3_model},
        {"name": p4_name, "model": p4_model},
    ]
    
    # 過濾空玩家
    players = [p for p in players if p["name"].strip()]
    
    if len(players) < 2:
        yield "❌ 需要至少 2 位玩家", "❌ 無玩家", "❌ 無排行榜"
        return
    
    game_manager.create_game(
        player_configs=players,
        total_rounds=int(total_rounds),
        starting_cash=float(starting_cash)
    )
    
    game_manager.engine.start_game()
    
    state = game_manager.engine.state
    all_logs = []
    
    # 開始訊息
    init_log = f"""# 🏆 AI 拍賣錦標賽

## 📋 遊戲設定
| 設定 | 值 |
|------|-----|
| 總回合數 | **{total_rounds}** |
| 起始資金 | **${starting_cash}** |
| 參賽者 | **{len(players)}** 位 |

## 🎮 參賽者
| 玩家 | Model | 狀態 |
|------|-------|------|
"""
    for p in players:
        init_log += f"| {p['name']} | `{p['model']}` | ✅ 準備就緒 |\n"
    
    init_log += "\n---\n\n⏳ **遊戲開始中...**"
    all_logs.append(init_log)
    
    # 顯示初始狀態
    yield (
        "\n\n".join(all_logs), 
        game_manager.get_player_cards_md(), 
        game_manager.get_leaderboard_md()
    )
    
    print(f"\n🏆 錦標賽開始！玩家: {[p['name'] for p in players]}")
    
    # 用於同步執行異步代碼
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
    try:
        # 執行所有回合
        while state.phase != GamePhase.GAME_OVER:
            print(f"\n📍 執行第 {state.current_round}/{state.total_rounds} 回合...")
            
            # 執行回合 (同步方式)
            result = loop.run_until_complete(game_manager.run_round())
            all_logs.append(result["log"])
            
            # 即時更新 UI
            yield (
                "\n\n".join(all_logs), 
                game_manager.get_player_cards_md(), 
                game_manager.get_leaderboard_md()
            )
            
            # 進入下一回合
            has_next = game_manager.engine.next_round()
            
            if not has_next:
                break
    finally:
        loop.close()
    
    print("\n🏁 錦標賽結束！")
    
    # 遊戲結束
    final_results = game_manager.engine.get_final_results()
    
    final_log = f"""
---

# 🏁 遊戲結束！

## 🥇 冠軍: **{final_results['winner']}** 🎉

## 📊 最終排名 (揭曉真實價值)

| 排名 | 玩家 | Model | 最終得分 | 物品數 | Intent Errors |
|------|------|-------|----------|--------|---------------|
"""
    
    medals = ["🥇", "🥈", "🥉", "4️⃣"]
    for entry in final_results["leaderboard"]:
        medal = medals[entry["rank"]-1] if entry["rank"] <= 4 else str(entry["rank"])
        stats = final_results["player_stats"][entry["name"]]
        final_log += f"| {medal} | {entry['name']} | `{entry['model']}` | **${entry['score']:.0f}** | {stats['items_won']} | {stats['intent_errors']} |\n"
    
    # 物品盈虧明細
    final_log += "\n## 💰 物品盈虧明細\n\n"
    
    for name, stats in final_results["player_stats"].items():
        final_log += f"### {name} ({stats['model']})\n\n"
        
        if stats["is_bankrupt"]:
            final_log += f"💀 **第 {stats['bankrupt_round']} 輪破產**\n\n"
        
        if stats["items"]:
            final_log += "| 物品 | 購買價 | 真實價值 | 盈虧 |\n"
            final_log += "|------|--------|----------|------|\n"
            
            for item in stats["items"]:
                profit = item["profit"]
                profit_str = f"+${profit:.0f} 📈" if profit > 0 else f"-${abs(profit):.0f} 📉"
                final_log += f"| {item['name']} | ${item['paid']:.0f} | ${item['true_value']:.0f} | {profit_str} |\n"
            
            total_profit = stats.get("total_profit", 0)
            profit_emoji = "📈" if total_profit > 0 else "📉"
            final_log += f"\n**總盈虧**: {'+' if total_profit > 0 else ''}{total_profit:.0f} {profit_emoji}\n\n"
        else:
            final_log += "_未獲得任何物品_\n\n"
        
        # Intent Errors
        if stats["intent_errors"] > 0:
            final_log += f"⚠️ Intent Errors: {stats['intent_errors']} 次\n\n"
    
    all_logs.append(final_log)
    
    # 最終結果
    yield (
        "\n\n".join(all_logs), 
        game_manager.get_player_cards_md(), 
        game_manager.get_leaderboard_md(reveal=True)
    )




# ============================================================
# 創建 UI
# ============================================================

with gr.Blocks(title="Apollo - AI 拍賣錦標賽") as demo:
    
    gr.Markdown("""
    # 🏆 Apollo - AI 拍賣錦標賽
    
    **4 個 AI Model 對戰，觀察 Payment Intent 和決策行為**
    """)
    
    with gr.Row():
        # 左側：設定面板
        with gr.Column(scale=1):
            gr.Markdown("### 🎮 玩家設定")
            
            # Model 選項 (支援不同 Ollama 模型)
            model_choices = [
                "ollama:llama3.2",      # Ollama - Llama 3.2
                "ollama:llama3.1",      # Ollama - Llama 3.1
                "ollama:mistral",       # Ollama - Mistral
                "ollama:phi3",          # Ollama - Phi3
                "ollama:gemma2",        # Ollama - Gemma 2
                "gemini",               # Google Gemini
                "groq",                 # Groq
                "mock",                 # 模擬模式
            ]
            
            with gr.Group():
                gr.Markdown("**玩家 1** 🤖")
                p1_name = gr.Textbox(value="Llama3.2_Bot", label="名稱", max_lines=1)
                p1_model = gr.Dropdown(
                    choices=model_choices,
                    value="ollama:llama3.2",
                    label="Model"
                )
            
            with gr.Group():
                gr.Markdown("**玩家 2** 🦾")
                p2_name = gr.Textbox(value="Mistral_Bot", label="名稱", max_lines=1)
                p2_model = gr.Dropdown(
                    choices=model_choices,
                    value="ollama:mistral",
                    label="Model"
                )
            
            with gr.Group():
                gr.Markdown("**玩家 3** 🧠")
                p3_name = gr.Textbox(value="Phi3_Bot", label="名稱", max_lines=1)
                p3_model = gr.Dropdown(
                    choices=model_choices,
                    value="ollama:phi3",
                    label="Model"
                )
            
            with gr.Group():
                gr.Markdown("**玩家 4** ⚡")
                p4_name = gr.Textbox(value="Gemma_Bot", label="名稱", max_lines=1)
                p4_model = gr.Dropdown(
                    choices=model_choices,
                    value="ollama:gemma2",
                    label="Model"
                )
            
            gr.Markdown("### ⚙️ 遊戲設定")
            
            total_rounds = gr.Slider(
                minimum=5, maximum=20, value=10, step=1,
                label="總回合數"
            )
            
            starting_cash = gr.Slider(
                minimum=500, maximum=2000, value=1000, step=100,
                label="起始資金 ($)"
            )
            
            start_btn = gr.Button("🚀 開始錦標賽 (自動執行全部回合)", variant="primary", size="lg")
        
        # 中間：遊戲畫面
        with gr.Column(scale=2):
            gr.Markdown("### 📜 遊戲進行")
            
            game_log = gr.Markdown(
                value="設定玩家後點擊「開始錦標賽」...",
                label="遊戲記錄",
                height="full"
            )
        
        # 右側：狀態面板
        with gr.Column(scale=1):
            gr.Markdown("### 👥 玩家狀態")
            player_cards = gr.Markdown(value="")
            
            gr.Markdown("### 🏆 排行榜")
            leaderboard = gr.Markdown(value="")
    
    # 綁定事件 - 直接使用 generator 函數實現實時更新
    start_btn.click(
        fn=run_tournament_generator,
        inputs=[
            p1_name, p1_model,
            p2_name, p2_model,
            p3_name, p3_model,
            p4_name, p4_model,
            total_rounds,
            starting_cash
        ],
        outputs=[game_log, player_cards, leaderboard]
    )


# ============================================================
# 啟動
# ============================================================

if __name__ == "__main__":
    print("\n" + "="*60)
    print("🏆 Apollo - AI 拍賣錦標賽")
    print("="*60)
    print("\n📍 啟動後會自動打開瀏覽器")
    print("   按 Ctrl+C 停止服務器\n")
    
    demo.launch(
        server_name="0.0.0.0",
        server_port=7860,
        share=False,
        css=CUSTOM_CSS
    )

