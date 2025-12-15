"""
🏆 拍賣錦標賽 (Tournament Mode)

完整版遊戲邏輯：
- 4 個 AI Agent 對戰（可用不同 LLM）
- 物品有「估價範圍」和「真實價值」
- 談判機制（轉售、結盟）
- 計分系統
- Intent Error 追蹤
"""

from dataclasses import dataclass, field
from typing import Optional, List, Dict, Tuple
from datetime import datetime
from enum import Enum
import uuid
import random


# ============================================================
# 枚舉類型
# ============================================================

class GamePhase(str, Enum):
    """遊戲階段"""
    LOBBY = "lobby"           # 等待開始
    AUCTION = "auction"       # 拍賣中
    NEGOTIATION = "negotiation"  # 談判中
    SETTLEMENT = "settlement"    # 結算中
    GAME_OVER = "game_over"      # 遊戲結束


class BidResult(str, Enum):
    """出價結果"""
    WINNING = "winning"       # 目前最高
    OUTBID = "outbid"         # 被超過
    INVALID = "invalid"       # 無效（餘額不足等）


class NegotiationType(str, Enum):
    """談判類型"""
    RESALE = "resale"         # 轉售物品
    ALLIANCE = "alliance"     # 結盟
    LOAN = "loan"             # 借貸


class IntentErrorType(str, Enum):
    """Intent Error 類型"""
    OVERPAY = "overpay"                   # 出價超過估價上限
    SUBOPTIMAL_TOKEN = "suboptimal_token" # 幣種選擇不當
    BUDGET_EXCEED = "budget_exceed"       # 超出預算
    ILLOGICAL_BID = "illogical_bid"       # 不合邏輯的出價
    BROKEN_PROMISE = "broken_promise"     # 違背承諾
    CALCULATION_ERROR = "calculation_error"  # 計算錯誤


# ============================================================
# 數據類型
# ============================================================

@dataclass
class TournamentItem:
    """錦標賽物品"""
    item_id: str
    name: str
    description: str
    hint: str                 # 給 AI 的提示（可能誤導）
    estimate_low: float       # 估價下限
    estimate_high: float      # 估價上限
    true_value: float         # 真實價值（遊戲結束揭曉）
    category: str = "art"     # 類別
    rarity: str = "common"    # 稀有度


# ============================================================
# 10 種固定商品定義（每場遊戲隨機打亂順序）
# ============================================================

FIXED_ITEMS = [
    {
        "name": "🎨 畢卡索素描稿",
        "category": "art",
        "description": "據稱是畢卡索 1937 年的素描習作，紙張有明顯老化痕跡。",
        "hint": "專家意見分歧：有人認為是真跡，也有人質疑簽名筆觸。",
        "estimate_low": 150,
        "estimate_high": 300,
        "true_value_range": (80, 450),  # 可能是假的(虧)，也可能是真的(賺)
    },
    {
        "name": "💎 斯里蘭卡藍寶石",
        "category": "gem",
        "description": "3.2 克拉藍寶石，附帶 GIA 鑑定證書，但證書日期較舊。",
        "hint": "市場上近期有大量合成藍寶石流入，需謹慎評估。",
        "estimate_low": 200,
        "estimate_high": 350,
        "true_value_range": (120, 500),
    },
    {
        "name": "🏺 明代青花瓷瓶",
        "category": "antique",
        "description": "瓶身有修復痕跡，底部有款識但較模糊。",
        "hint": "類似器物在蘇富比拍出高價，但也有仿品案例。",
        "estimate_low": 180,
        "estimate_high": 320,
        "true_value_range": (50, 600),  # 波動很大
    },
    {
        "name": "🎮 初代 PlayStation 原型機",
        "category": "tech",
        "description": "標示為 Sony 1994 年開發原型機，序號已磨損。",
        "hint": "收藏市場對遊戲機歷史物件需求增加，但驗證困難。",
        "estimate_low": 120,
        "estimate_high": 250,
        "true_value_range": (60, 400),
    },
    {
        "name": "👟 Air Jordan 1 OG (1985)",
        "category": "fashion",
        "description": "聲稱全新未穿，鞋盒完整，但氧化程度有疑慮。",
        "hint": "市面上高仿品極為精密，專業鑑定也有失誤案例。",
        "estimate_low": 100,
        "estimate_high": 220,
        "true_value_range": (40, 350),
    },
    {
        "name": "🍷 1982 拉菲紅酒",
        "category": "wine",
        "description": "酒標完整，液面正常，來源為私人酒窖。",
        "hint": "1982 是傳奇年份，但假酒問題嚴重，需確認儲存條件。",
        "estimate_low": 160,
        "estimate_high": 280,
        "true_value_range": (70, 450),
    },
    {
        "name": "🎸 據稱 Jimi Hendrix 簽名吉他",
        "category": "music",
        "description": "Fender Stratocaster，附有簽名照片但無第三方認證。",
        "hint": "Hendrix 遺物極為稀少，市場價值高但偽造也多。",
        "estimate_low": 200,
        "estimate_high": 400,
        "true_value_range": (100, 700),
    },
    {
        "name": "📱 Apple-1 電腦主板",
        "category": "tech",
        "description": "標示為 1976 年生產，有部分零件更換痕跡。",
        "hint": "真品在拍賣會上屢創新高，但流通數量存疑。",
        "estimate_low": 250,
        "estimate_high": 450,
        "true_value_range": (150, 800),
    },
    {
        "name": "🖼️ Banksy 碎紙畫複製品",
        "category": "art",
        "description": "聲稱為官方授權複製品，附編號證書。",
        "hint": "Banksy 市場火熱，但官方從未確認授權計畫。",
        "estimate_low": 80,
        "estimate_high": 180,
        "true_value_range": (20, 300),
    },
    {
        "name": "⌚ Rolex Daytona 「Paul Newman」",
        "category": "luxury",
        "description": "1960年代款式，錶面有使用痕跡，機芯需保養。",
        "hint": "Paul Newman 配色近年價格飆升，但市場有大量改裝錶。",
        "estimate_low": 220,
        "estimate_high": 380,
        "true_value_range": (100, 650),
    },
]


def generate_item_for_round(round_num: int, shuffled_items: list) -> TournamentItem:
    """根據回合生成物品"""
    # 使用預先打亂的列表
    item_data = shuffled_items[round_num - 1] if round_num <= len(shuffled_items) else random.choice(FIXED_ITEMS)
    
    # 在真實價值範圍內隨機生成（偏離估價）
    true_low, true_high = item_data["true_value_range"]
    
    # 70% 機率偏離估價範圍（30% 機率在範圍內）
    if random.random() < 0.7:
        # 偏離：可能遠高於或遠低於估價
        if random.random() < 0.5:
            # 低估：真實價值高於估價
            true_value = random.uniform(item_data["estimate_high"], true_high)
        else:
            # 高估：真實價值低於估價  
            true_value = random.uniform(true_low, item_data["estimate_low"])
    else:
        # 正常範圍
        true_value = random.uniform(
            item_data["estimate_low"] * 0.9,
            item_data["estimate_high"] * 1.1
        )
    
    # 確保在合理範圍
    true_value = max(true_low, min(true_high, true_value))
    
    return TournamentItem(
        item_id=f"item_{round_num}_{uuid.uuid4().hex[:6]}",
        name=item_data["name"],
        description=item_data["description"],
        hint=item_data["hint"],
        estimate_low=item_data["estimate_low"],
        estimate_high=item_data["estimate_high"],
        true_value=round(true_value, 2),
        category=item_data["category"],
        rarity="unique"
    )


@dataclass
class PlayerState:
    """玩家狀態"""
    player_id: str
    name: str
    model: str                # LLM 模型名稱
    cash: float = 1000.0      # 現金 (USD)
    items: List[TournamentItem] = field(default_factory=list)  # 持有物品
    is_active: bool = True    # 是否還在遊戲中
    is_bankrupt: bool = False # 是否破產
    bankrupt_round: int = -1  # 破產回合
    
    # 統計
    total_spent: float = 0.0
    total_items_won: int = 0
    intent_errors: List[Dict] = field(default_factory=list)
    
    # 物品購買記錄 (用於計算盈虧)
    item_costs: Dict[str, float] = field(default_factory=dict)  # item_id -> 購買價格
    
    def get_total_value(self, reveal_true_value: bool = False) -> float:
        """計算總資產"""
        item_value = sum(
            item.true_value if reveal_true_value else (item.estimate_low + item.estimate_high) / 2
            for item in self.items
        )
        return self.cash + item_value
    
    def get_item_profit(self, item: TournamentItem) -> float:
        """計算單件物品盈虧"""
        cost = self.item_costs.get(item.item_id, 0)
        return item.true_value - cost
    
    def can_afford(self, amount: float) -> bool:
        """是否能負擔"""
        return self.cash >= amount
    
    def add_intent_error(self, error_type: IntentErrorType, message: str, round_num: int):
        """記錄 Intent Error"""
        self.intent_errors.append({
            "type": error_type.value,
            "message": message,
            "round": round_num,
            "timestamp": datetime.now().isoformat()
        })


@dataclass
class Bid:
    """出價"""
    bid_id: str
    player_id: str
    player_name: str
    amount: float
    reasoning: str = ""       # 出價理由
    timestamp: datetime = field(default_factory=datetime.now)
    result: BidResult = BidResult.WINNING
    intent_errors: List[Dict] = field(default_factory=list)


@dataclass
class NegotiationOffer:
    """談判提議"""
    offer_id: str
    from_player: str
    to_player: str
    offer_type: NegotiationType
    details: Dict               # 具體內容
    message: str
    response: Optional[str] = None  # accept / reject / counter
    counter_offer: Optional[Dict] = None
    timestamp: datetime = field(default_factory=datetime.now)


@dataclass
class RoundResult:
    """回合結果"""
    round_num: int
    item: TournamentItem
    winner: Optional[str]
    winning_bid: Optional[float]
    all_bids: List[Bid]
    negotiations: List[NegotiationOffer]
    events: List[str]         # 回合事件
    intent_errors: List[Dict]


@dataclass
class GameState:
    """遊戲狀態"""
    game_id: str
    phase: GamePhase = GamePhase.LOBBY
    current_round: int = 0
    total_rounds: int = 10
    players: Dict[str, PlayerState] = field(default_factory=dict)
    round_results: List[RoundResult] = field(default_factory=list)
    current_item: Optional[TournamentItem] = None
    current_bids: List[Bid] = field(default_factory=list)
    
    # 遊戲設定
    starting_cash: float = 1000.0
    enable_negotiation: bool = True
    
    # 統計
    total_intent_errors: int = 0
    events_log: List[str] = field(default_factory=list)
    
    def get_active_players(self) -> List[PlayerState]:
        """獲取活躍玩家"""
        return [p for p in self.players.values() if p.is_active and not p.is_bankrupt]
    
    def get_leaderboard(self, reveal_true_value: bool = False) -> List[Tuple[str, float]]:
        """獲取排行榜"""
        scores = [
            (p.name, p.get_total_value(reveal_true_value))
            for p in self.players.values()
        ]
        return sorted(scores, key=lambda x: x[1], reverse=True)
    
    def add_event(self, event: str):
        """添加事件日誌"""
        self.events_log.append(f"[R{self.current_round}] {event}")


# ============================================================
# 遊戲引擎
# ============================================================

class TournamentEngine:
    """錦標賽遊戲引擎"""
    
    def __init__(
        self,
        total_rounds: int = 10,
        starting_cash: float = 1000.0,
        enable_negotiation: bool = True
    ):
        self.state = GameState(
            game_id=f"game_{uuid.uuid4().hex[:8]}",
            total_rounds=total_rounds,
            starting_cash=starting_cash,
            enable_negotiation=enable_negotiation
        )
        
        # 打亂商品順序（10種不重複）
        self.shuffled_items = FIXED_ITEMS.copy()
        random.shuffle(self.shuffled_items)
    
    def add_player(self, name: str, model: str) -> PlayerState:
        """添加玩家"""
        player = PlayerState(
            player_id=f"player_{uuid.uuid4().hex[:6]}",
            name=name,
            model=model,
            cash=self.state.starting_cash
        )
        self.state.players[player.player_id] = player
        self.state.add_event(f"🎮 {name} ({model}) 加入遊戲")
        return player
    
    def start_game(self):
        """開始遊戲"""
        if len(self.state.players) < 2:
            raise ValueError("需要至少 2 位玩家")
        
        self.state.phase = GamePhase.AUCTION
        self.state.current_round = 1
        self.state.add_event("🏁 遊戲開始！")
        
        # 生成第一輪物品
        self._generate_round_item()
    
    def _generate_round_item(self):
        """生成當前回合物品（使用不重複的固定商品列表）"""
        self.state.current_item = generate_item_for_round(
            self.state.current_round,
            self.shuffled_items
        )
        self.state.current_bids = []
        self.state.add_event(
            f"📦 本輪物品: {self.state.current_item.name} "
            f"(估價 ${self.state.current_item.estimate_low:.0f}-${self.state.current_item.estimate_high:.0f})"
        )
    
    def submit_bid(
        self,
        player_id: str,
        amount: float,
        reasoning: str = ""
    ) -> Bid:
        """提交出價"""
        player = self.state.players.get(player_id)
        if not player or not player.is_active:
            raise ValueError("無效玩家")
        
        item = self.state.current_item
        bid = Bid(
            bid_id=f"bid_{uuid.uuid4().hex[:6]}",
            player_id=player_id,
            player_name=player.name,
            amount=amount,
            reasoning=reasoning
        )
        
        # 驗證出價
        errors = self._validate_bid(player, bid, item)
        bid.intent_errors = errors
        
        if errors:
            bid.result = BidResult.INVALID
            for err in errors:
                player.add_intent_error(
                    IntentErrorType(err["type"]),
                    err["message"],
                    self.state.current_round
                )
                self.state.total_intent_errors += 1
        
        self.state.current_bids.append(bid)
        
        # 更新出價狀態
        self._update_bid_results()
        
        return bid
    
    def _validate_bid(
        self,
        player: PlayerState,
        bid: Bid,
        item: TournamentItem
    ) -> List[Dict]:
        """驗證出價"""
        errors = []
        
        # 檢查是否超出預算
        if bid.amount > player.cash:
            errors.append({
                "type": IntentErrorType.BUDGET_EXCEED.value,
                "message": f"出價 ${bid.amount:.2f} 超出現金 ${player.cash:.2f}"
            })
        
        # 檢查是否超過估價上限（非理性）- 寬鬆一點，允許超過 50%
        if bid.amount > item.estimate_high * 1.5:
            errors.append({
                "type": IntentErrorType.OVERPAY.value,
                "message": f"出價 ${bid.amount:.2f} 遠超估價上限 ${item.estimate_high:.2f}"
            })
        
        return errors
    
    def _update_bid_results(self):
        """更新出價結果"""
        valid_bids = [b for b in self.state.current_bids if b.result != BidResult.INVALID]
        if not valid_bids:
            return
        
        max_bid = max(valid_bids, key=lambda b: b.amount)
        
        for bid in self.state.current_bids:
            if bid.result == BidResult.INVALID:
                continue
            if bid.bid_id == max_bid.bid_id:
                bid.result = BidResult.WINNING
            else:
                bid.result = BidResult.OUTBID
    
    def end_auction_round(self) -> RoundResult:
        """結束當前拍賣回合"""
        item = self.state.current_item
        valid_bids = [b for b in self.state.current_bids if b.result != BidResult.INVALID]
        
        winner = None
        winning_bid = None
        
        if valid_bids:
            # 找最高出價
            max_bid = max(valid_bids, key=lambda b: b.amount)
            winner_player = self.state.players[max_bid.player_id]
            
            # 扣款
            winner_player.cash -= max_bid.amount
            winner_player.total_spent += max_bid.amount
            winner_player.items.append(item)
            winner_player.item_costs[item.item_id] = max_bid.amount  # 記錄購買價格
            winner_player.total_items_won += 1
            
            winner = winner_player.name
            winning_bid = max_bid.amount
            
            self.state.add_event(
                f"🎉 {winner} 以 ${winning_bid:.2f} 得標 {item.name}"
            )
            
            # 檢查破產
            self._check_bankruptcies()
        else:
            self.state.add_event(f"😢 {item.name} 流標")
        
        # 記錄回合結果
        result = RoundResult(
            round_num=self.state.current_round,
            item=item,
            winner=winner,
            winning_bid=winning_bid,
            all_bids=self.state.current_bids.copy(),
            negotiations=[],
            events=[],
            intent_errors=[
                err for bid in self.state.current_bids 
                for err in bid.intent_errors
            ]
        )
        self.state.round_results.append(result)
        
        return result
    
    def _check_bankruptcies(self):
        """檢查破產"""
        for player in self.state.players.values():
            if player.is_active and player.cash <= 0:
                player.is_bankrupt = True
                player.is_active = False
                player.bankrupt_round = self.state.current_round
                self.state.add_event(f"💀 {player.name} 破產！")
    
    def next_round(self) -> bool:
        """進入下一回合"""
        # 檢查遊戲是否結束
        active_players = self.state.get_active_players()
        
        if len(active_players) <= 1:
            self.state.phase = GamePhase.GAME_OVER
            return False
        
        if self.state.current_round >= self.state.total_rounds:
            self.state.phase = GamePhase.GAME_OVER
            return False
        
        self.state.current_round += 1
        self._generate_round_item()
        return True
    
    def propose_trade(
        self,
        from_player_id: str,
        to_player_id: str,
        offer_item_id: Optional[str],
        request_item_id: Optional[str],
        cash_offer: float = 0,
        cash_request: float = 0,
        message: str = ""
    ) -> NegotiationOffer:
        """提出交換提議
        
        可以是：
        - 物品換物品
        - 物品換現金
        - 物品 + 現金 換 物品
        """
        from_player = self.state.players.get(from_player_id)
        to_player = self.state.players.get(to_player_id)
        
        if not from_player or not to_player:
            raise ValueError("無效玩家")
        
        offer = NegotiationOffer(
            offer_id=f"offer_{uuid.uuid4().hex[:6]}",
            from_player=from_player.name,
            to_player=to_player.name,
            offer_type=NegotiationType.RESALE,
            details={
                "offer_item_id": offer_item_id,
                "request_item_id": request_item_id,
                "cash_offer": cash_offer,
                "cash_request": cash_request,
            },
            message=message
        )
        
        self.state.add_event(
            f"💬 {from_player.name} 向 {to_player.name} 提出交換提議"
        )
        
        return offer
    
    def execute_trade(
        self,
        offer: NegotiationOffer,
        from_player_id: str,
        to_player_id: str
    ) -> bool:
        """執行交換"""
        from_player = self.state.players.get(from_player_id)
        to_player = self.state.players.get(to_player_id)
        
        if not from_player or not to_player:
            return False
        
        details = offer.details
        
        # 找到要交換的物品
        offer_item = None
        request_item = None
        
        if details.get("offer_item_id"):
            offer_item = next(
                (i for i in from_player.items if i.item_id == details["offer_item_id"]),
                None
            )
        
        if details.get("request_item_id"):
            request_item = next(
                (i for i in to_player.items if i.item_id == details["request_item_id"]),
                None
            )
        
        cash_offer = details.get("cash_offer", 0)
        cash_request = details.get("cash_request", 0)
        
        # 驗證交換可行性
        if offer_item and offer_item not in from_player.items:
            return False
        if request_item and request_item not in to_player.items:
            return False
        if cash_offer > from_player.cash:
            return False
        if cash_request > to_player.cash:
            return False
        
        # 執行交換
        if offer_item:
            from_player.items.remove(offer_item)
            to_player.items.append(offer_item)
            # 轉移成本記錄
            if offer_item.item_id in from_player.item_costs:
                to_player.item_costs[offer_item.item_id] = from_player.item_costs.pop(offer_item.item_id)
        
        if request_item:
            to_player.items.remove(request_item)
            from_player.items.append(request_item)
            if request_item.item_id in to_player.item_costs:
                from_player.item_costs[request_item.item_id] = to_player.item_costs.pop(request_item.item_id)
        
        if cash_offer > 0:
            from_player.cash -= cash_offer
            to_player.cash += cash_offer
        
        if cash_request > 0:
            to_player.cash -= cash_request
            from_player.cash += cash_request
        
        self.state.add_event(
            f"🤝 交換完成: {from_player.name} ↔ {to_player.name}"
        )
        
        return True
    
    def get_final_results(self) -> Dict:
        """獲取最終結果"""
        # 揭曉所有物品真實價值
        leaderboard = self.state.get_leaderboard(reveal_true_value=True)
        
        # 統計
        results = {
            "winner": leaderboard[0][0] if leaderboard else None,
            "leaderboard": [
                {
                    "rank": i + 1,
                    "name": name,
                    "score": score,
                    "model": self.state.players[
                        next(p.player_id for p in self.state.players.values() if p.name == name)
                    ].model
                }
                for i, (name, score) in enumerate(leaderboard)
            ],
            "total_rounds": self.state.current_round,
            "total_intent_errors": self.state.total_intent_errors,
            "player_stats": {}
        }
        
        for player in self.state.players.values():
            # 計算每件物品的盈虧
            items_detail = []
            total_profit = 0
            
            for item in player.items:
                cost = player.item_costs.get(item.item_id, 0)
                profit = item.true_value - cost
                total_profit += profit
                
                items_detail.append({
                    "name": item.name,
                    "paid": cost,
                    "true_value": item.true_value,
                    "profit": profit,
                    "profit_pct": (profit / cost * 100) if cost > 0 else 0
                })
            
            results["player_stats"][player.name] = {
                "model": player.model,
                "final_cash": player.cash,
                "items_won": player.total_items_won,
                "total_spent": player.total_spent,
                "total_profit": total_profit,
                "intent_errors": len(player.intent_errors),
                "is_bankrupt": player.is_bankrupt,
                "bankrupt_round": player.bankrupt_round if player.is_bankrupt else None,
                "items": items_detail
            }
        
        return results



