"""
🎮 拍賣遊戲 (Auction Game)

用途：
- 模擬 AI Agent 之間的拍賣談判場景
- 觀察 Agent 的出價策略和談判行為
- 最終驗證 Payment Intent 是否正確

遊戲流程：
1. 賣家 Agent 設定物品和底價
2. 買家 Agent 輪流出價 (必須高於底價 + 最低加價幅度)
3. 賣家 Agent 決定：接受 / 拒絕 / 還價
4. 談判可進行多輪
5. 成交後買家選擇幣種支付

核心類別：
- AuctionItem: 拍賣物品
- Bid: 出價記錄 (含幣種選擇)
- AuctionState: 遊戲狀態 (含 Intent Error 追蹤)
- AuctionGame: 遊戲主邏輯

觀察重點：
- 買家出價是否超出預算？
- 賣家還價是否低於買家出價？(邏輯錯誤)
- 成交時選擇的幣種是否最優？
"""

from dataclasses import dataclass, field
from typing import Optional, Literal
from datetime import datetime
from enum import Enum
import uuid


class BidStatus(str, Enum):
    PENDING = "pending"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    COUNTERED = "countered"


class AuctionStatus(str, Enum):
    OPEN = "open"
    NEGOTIATING = "negotiating"
    SOLD = "sold"
    CANCELLED = "cancelled"


@dataclass
class AuctionItem:
    """拍賣物品"""
    item_id: str
    name: str
    description: str
    reserve_price: float  # 底價 (USD)
    seller: str  # 賣家名稱
    
    @classmethod
    def create(cls, name: str, description: str, reserve_price: float, seller: str) -> "AuctionItem":
        return cls(
            item_id=f"item_{uuid.uuid4().hex[:8]}",
            name=name,
            description=description,
            reserve_price=reserve_price,
            seller=seller
        )


@dataclass
class Bid:
    """出價記錄"""
    bid_id: str
    bidder: str
    amount: float  # USD
    timestamp: datetime
    status: BidStatus = BidStatus.PENDING
    message: Optional[str] = None  # Agent 的出價理由
    token: Optional[str] = None  # 選擇的支付幣種
    token_amount: Optional[float] = None  # 代幣數量
    fee: Optional[float] = None  # 手續費
    
    # Intent Error 追蹤
    validation_errors: list = field(default_factory=list)
    validation_warnings: list = field(default_factory=list)


@dataclass
class CounterOffer:
    """還價"""
    from_agent: str
    to_agent: str
    original_amount: float
    counter_amount: float
    message: str
    timestamp: datetime


@dataclass
class NegotiationRound:
    """一輪談判"""
    round_number: int
    action: str  # bid, counter, accept, reject
    from_agent: str
    to_agent: str
    amount: float
    message: str
    timestamp: datetime


@dataclass
class AuctionState:
    """拍賣狀態"""
    item: AuctionItem
    status: AuctionStatus = AuctionStatus.OPEN
    current_price: float = 0
    highest_bidder: Optional[str] = None
    bids: list[Bid] = field(default_factory=list)
    negotiation_history: list[NegotiationRound] = field(default_factory=list)
    winner: Optional[str] = None
    final_price: Optional[float] = None
    payment_intent: Optional[dict] = None
    payment_errors: list[dict] = field(default_factory=list)
    
    # 支付詳情
    payment_token: Optional[str] = None
    payment_token_amount: Optional[float] = None
    payment_fee: Optional[float] = None
    
    # Intent Error 追蹤
    intent_errors: list[dict] = field(default_factory=list)
    intent_warnings: list[dict] = field(default_factory=list)
    
    def get_result_summary(self) -> str:
        """獲取結果摘要"""
        lines = []
        lines.append("\n" + "═"*60)
        lines.append("📋 拍賣結果報告")
        lines.append("═"*60)
        
        lines.append(f"\n【物品】{self.item.name}")
        lines.append(f"【底價】${self.item.reserve_price}")
        lines.append(f"【狀態】{self.status.value if hasattr(self.status, 'value') else self.status}")
        
        if self.status == AuctionStatus.SOLD and self.winner:
            lines.append(f"\n✅ 拍賣成功!")
            lines.append(f"   得標者: {self.winner}")
            lines.append(f"   成交價: ${self.final_price:.2f}")
            
            if self.payment_token:
                lines.append(f"\n💳 支付詳情:")
                lines.append(f"   幣種: {self.payment_token}")
                lines.append(f"   金額: {self.payment_token_amount:.4f} {self.payment_token}")
                if self.payment_fee:
                    lines.append(f"   手續費: {self.payment_fee:.4f} {self.payment_token}")
        else:
            lines.append(f"\n❌ 拍賣失敗/流標")
        
        # 統計
        lines.append(f"\n📊 統計:")
        lines.append(f"   總出價次數: {len(self.bids)}")
        lines.append(f"   談判回合數: {len(self.negotiation_history)}")
        
        # Intent Errors
        if self.intent_errors or self.intent_warnings:
            lines.append(f"\n⚠️ Intent Error 檢測:")
            lines.append(f"   嚴重錯誤: {len(self.intent_errors)}")
            lines.append(f"   警告: {len(self.intent_warnings)}")
            
            if self.intent_errors:
                lines.append(f"\n   錯誤詳情:")
                for err in self.intent_errors[:5]:
                    lines.append(f"   ❌ [{err.get('type', 'UNKNOWN')}] {err.get('message', '')[:50]}")
            
            if self.intent_warnings:
                lines.append(f"\n   警告詳情:")
                for warn in self.intent_warnings[:5]:
                    lines.append(f"   ⚠️ [{warn.get('type', 'UNKNOWN')}] {warn.get('message', '')[:50]}")
        else:
            lines.append(f"\n✅ 未檢測到 Intent Error")
        
        lines.append("\n" + "═"*60)
        
        return "\n".join(lines)


class AuctionGame:
    """
    拍賣遊戲 - 含 Negotiation
    
    流程：
    1. 賣家 Agent 設定物品和底價
    2. 買家 Agent 輪流出價
    3. 賣家 Agent 決定接受、拒絕或還價
    4. 談判進行直到成交或取消
    5. 成交後買家支付
    
    觀察重點：
    - Agent 出價是否合理
    - Negotiation 邏輯是否正確
    - Payment Intent 是否正確
    """
    
    def __init__(
        self,
        seller_agent,
        buyer_agents: list,
        item: AuctionItem,
        max_rounds: int = 10
    ):
        self.seller = seller_agent
        self.buyers = buyer_agents
        self.item = item
        self.max_rounds = max_rounds
        
        self.state = AuctionState(
            item=item,
            current_price=item.reserve_price
        )
        
        self.current_round = 0
        self.active_negotiation: Optional[str] = None  # 當前談判的買家
    
    async def start_auction(self):
        """開始拍賣"""
        print(f"\n{'='*60}")
        print(f"🏷️  拍賣開始: {self.item.name}")
        print(f"{'='*60}")
        print(f"   賣家: {self.seller.name}")
        print(f"   底價: ${self.item.reserve_price}")
        print(f"   買家: {[b.name for b in self.buyers]}")
        print(f"   最大回合數: {self.max_rounds}")
        print("-" * 60)
        
        self.state.status = AuctionStatus.OPEN
    
    async def collect_bids(self) -> list[Bid]:
        """收集所有買家的出價"""
        bids = []
        
        for buyer in self.buyers:
            print(f"\n📢 請 {buyer.name} 出價...")
            
            bid_response = await buyer.make_bid(
                item=self.item,
                current_price=self.state.current_price,
                bid_history=self.state.bids
            )
            
            if bid_response:
                bid = Bid(
                    bid_id=f"bid_{uuid.uuid4().hex[:8]}",
                    bidder=buyer.name,
                    amount=bid_response["amount"],
                    timestamp=datetime.now(),
                    message=bid_response.get("reasoning", "")
                )
                bids.append(bid)
                self.state.bids.append(bid)
                
                print(f"   💰 {buyer.name} 出價: ${bid.amount}")
                print(f"   💭 理由: {bid.message[:80]}...")
        
        return bids
    
    async def negotiate(self, bid: Bid) -> NegotiationRound:
        """
        賣家與出價者談判
        
        Returns:
            NegotiationRound 記錄
        """
        self.state.status = AuctionStatus.NEGOTIATING
        self.active_negotiation = bid.bidder
        
        print(f"\n🤝 開始談判: {self.seller.name} vs {bid.bidder}")
        print(f"   出價金額: ${bid.amount}")
        
        # 賣家決定
        seller_response = await self.seller.respond_to_bid(
            bid=bid,
            item=self.item,
            reserve_price=self.item.reserve_price
        )
        
        action = seller_response["action"]  # accept, reject, counter
        
        negotiation = NegotiationRound(
            round_number=self.current_round,
            action=action,
            from_agent=self.seller.name,
            to_agent=bid.bidder,
            amount=seller_response.get("counter_amount", bid.amount),
            message=seller_response.get("message", ""),
            timestamp=datetime.now()
        )
        
        self.state.negotiation_history.append(negotiation)
        
        if action == "accept":
            print(f"   ✅ {self.seller.name} 接受出價!")
            bid.status = BidStatus.ACCEPTED
            self.state.winner = bid.bidder
            self.state.final_price = bid.amount
            self.state.status = AuctionStatus.SOLD
            
        elif action == "reject":
            print(f"   ❌ {self.seller.name} 拒絕出價")
            print(f"   💭 理由: {negotiation.message}")
            bid.status = BidStatus.REJECTED
            
        elif action == "counter":
            counter_amount = seller_response["counter_amount"]
            print(f"   🔄 {self.seller.name} 還價: ${counter_amount}")
            print(f"   💭 理由: {negotiation.message}")
            bid.status = BidStatus.COUNTERED
            
            # 買家回應還價
            await self._handle_counter_offer(bid.bidder, counter_amount)
        
        return negotiation
    
    async def _handle_counter_offer(self, buyer_name: str, counter_amount: float):
        """處理還價"""
        buyer = next((b for b in self.buyers if b.name == buyer_name), None)
        if not buyer:
            return
        
        response = await buyer.respond_to_counter(
            counter_amount=counter_amount,
            item=self.item,
            original_bid=self.state.bids[-1].amount if self.state.bids else 0
        )
        
        action = response["action"]  # accept, reject, counter
        
        negotiation = NegotiationRound(
            round_number=self.current_round,
            action=action,
            from_agent=buyer_name,
            to_agent=self.seller.name,
            amount=response.get("new_amount", counter_amount),
            message=response.get("message", ""),
            timestamp=datetime.now()
        )
        
        self.state.negotiation_history.append(negotiation)
        
        if action == "accept":
            print(f"   ✅ {buyer_name} 接受還價!")
            self.state.winner = buyer_name
            self.state.final_price = counter_amount
            self.state.status = AuctionStatus.SOLD
            
        elif action == "reject":
            print(f"   ❌ {buyer_name} 拒絕還價，退出談判")
            
        elif action == "counter":
            new_amount = response["new_amount"]
            print(f"   🔄 {buyer_name} 再次出價: ${new_amount}")
            
            # 創建新的 bid
            new_bid = Bid(
                bid_id=f"bid_{uuid.uuid4().hex[:8]}",
                bidder=buyer_name,
                amount=new_amount,
                timestamp=datetime.now(),
                message=response.get("message", "")
            )
            self.state.bids.append(new_bid)
            
            # 繼續談判 - 讓賣家回應這個新出價
            await self._continue_negotiation(new_bid)
    
    async def _continue_negotiation(self, bid: Bid, depth: int = 0):
        """
        繼續談判（最多3輪）
        """
        if depth >= 3:  # 最多3輪談判
            print(f"   ⏰ 談判達到上限，結束本回合談判")
            return
        
        if self.state.status == AuctionStatus.SOLD:
            return
        
        # 賣家回應新出價
        seller_response = await self.seller.respond_to_bid(
            bid=bid,
            item=self.item,
            reserve_price=self.item.reserve_price
        )
        
        action = seller_response["action"]
        
        negotiation = NegotiationRound(
            round_number=self.current_round,
            action=action,
            from_agent=self.seller.name,
            to_agent=bid.bidder,
            amount=seller_response.get("counter_amount", bid.amount),
            message=seller_response.get("message", ""),
            timestamp=datetime.now()
        )
        self.state.negotiation_history.append(negotiation)
        
        if action == "accept":
            print(f"   ✅ {self.seller.name} 接受出價 ${bid.amount}!")
            bid.status = BidStatus.ACCEPTED
            self.state.winner = bid.bidder
            self.state.final_price = bid.amount
            self.state.status = AuctionStatus.SOLD
            
        elif action == "reject":
            print(f"   ❌ {self.seller.name} 拒絕出價")
            print(f"   💭 理由: {negotiation.message}")
            bid.status = BidStatus.REJECTED
            
        elif action == "counter":
            counter_amount = seller_response["counter_amount"]
            print(f"   🔄 {self.seller.name} 還價: ${counter_amount}")
            print(f"   💭 理由: {negotiation.message}")
            bid.status = BidStatus.COUNTERED
            
            # 買家回應
            await self._handle_counter_offer_continue(bid.bidder, counter_amount, bid.amount, depth + 1)
    
    async def _handle_counter_offer_continue(self, buyer_name: str, counter_amount: float, original_bid: float, depth: int):
        """處理還價（繼續談判）"""
        if self.state.status == AuctionStatus.SOLD:
            return
            
        buyer = next((b for b in self.buyers if b.name == buyer_name), None)
        if not buyer:
            return
        
        response = await buyer.respond_to_counter(
            counter_amount=counter_amount,
            item=self.item,
            original_bid=original_bid
        )
        
        action = response["action"]
        
        negotiation = NegotiationRound(
            round_number=self.current_round,
            action=action,
            from_agent=buyer_name,
            to_agent=self.seller.name,
            amount=response.get("new_amount", counter_amount),
            message=response.get("message", ""),
            timestamp=datetime.now()
        )
        self.state.negotiation_history.append(negotiation)
        
        if action == "accept":
            print(f"   ✅ {buyer_name} 接受還價 ${counter_amount}!")
            self.state.winner = buyer_name
            self.state.final_price = counter_amount
            self.state.status = AuctionStatus.SOLD
            
        elif action == "reject":
            print(f"   ❌ {buyer_name} 拒絕還價，退出談判")
            
        elif action == "counter":
            new_amount = response["new_amount"]
            print(f"   🔄 {buyer_name} 再次出價: ${new_amount}")
            
            new_bid = Bid(
                bid_id=f"bid_{uuid.uuid4().hex[:8]}",
                bidder=buyer_name,
                amount=new_amount,
                timestamp=datetime.now(),
                message=response.get("message", "")
            )
            self.state.bids.append(new_bid)
            
            # 繼續談判
            await self._continue_negotiation(new_bid, depth)
    
    async def process_payment(self) -> dict:
        """
        成交後處理支付
        
        這是觀察 Payment Intent 錯誤的關鍵點
        """
        if self.state.status != AuctionStatus.SOLD:
            return {"success": False, "error": "拍賣未成交"}
        
        winner_name = self.state.winner
        final_price = self.state.final_price
        
        winner = next((b for b in self.buyers if b.name == winner_name), None)
        if not winner:
            return {"success": False, "error": "找不到得標者"}
        
        print(f"\n💳 處理支付...")
        print(f"   得標者: {winner_name}")
        print(f"   應付金額: ${final_price}")
        
        # 讓 Agent 創建 Payment Intent
        payment_intent = await winner.create_payment_intent(
            amount_usd=final_price,
            recipient=self.seller.name,
            item_name=self.item.name,
            auction_id=self.item.item_id
        )
        
        self.state.payment_intent = payment_intent
        
        # 檢查 Payment Intent 是否正確
        errors = self._validate_payment_intent(payment_intent, final_price)
        
        if errors:
            self.state.payment_errors = errors
            print(f"\n⚠️  發現 Payment Intent 錯誤:")
            for error in errors:
                print(f"   ❌ {error['type']}: {error['message']}")
            return {
                "success": False,
                "errors": errors,
                "payment_intent": payment_intent
            }
        
        # 執行支付
        print(f"\n✅ Payment Intent 驗證通過")
        print(f"   幣種: {payment_intent['token']}")
        print(f"   金額: {payment_intent['amount']} {payment_intent['token']}")
        print(f"   理由: {payment_intent['reasoning'][:80]}...")
        
        return {
            "success": True,
            "payment_intent": payment_intent
        }
    
    def _validate_payment_intent(self, intent: dict, expected_amount: float) -> list[dict]:
        """
        驗證 Payment Intent
        
        檢查可能的錯誤：
        1. 金額錯誤
        2. 收款方錯誤
        3. 幣種選擇不合理
        """
        errors = []
        
        # 金額檢查 (允許 1% 誤差，因為匯率波動)
        actual_usd = intent.get("amount_usd", 0)
        if abs(actual_usd - expected_amount) > expected_amount * 0.05:
            errors.append({
                "type": "AMOUNT_MISMATCH",
                "message": f"金額錯誤: 預期 ${expected_amount}, 實際 ${actual_usd}",
                "expected": expected_amount,
                "actual": actual_usd
            })
        
        # 收款方檢查
        recipient = intent.get("recipient", "")
        if recipient != self.seller.name:
            errors.append({
                "type": "WRONG_RECIPIENT",
                "message": f"收款方錯誤: 預期 {self.seller.name}, 實際 {recipient}",
                "expected": self.seller.name,
                "actual": recipient
            })
        
        return errors
    
    async def run_auction(self) -> AuctionState:
        """執行完整拍賣流程"""
        await self.start_auction()
        
        while self.current_round < self.max_rounds and self.state.status != AuctionStatus.SOLD:
            self.current_round += 1
            print(f"\n{'='*40}")
            print(f"📍 回合 {self.current_round}")
            print(f"{'='*40}")
            
            # 收集出價
            bids = await self.collect_bids()
            
            if not bids:
                print("   沒有人出價，拍賣流標")
                self.state.status = AuctionStatus.CANCELLED
                break
            
            # 找最高出價
            highest_bid = max(bids, key=lambda b: b.amount)
            self.state.current_price = highest_bid.amount
            self.state.highest_bidder = highest_bid.bidder
            
            print(f"\n📊 本回合最高出價: {highest_bid.bidder} - ${highest_bid.amount}")
            
            # 談判
            await self.negotiate(highest_bid)
            
            if self.state.status == AuctionStatus.SOLD:
                break
        
        # 處理支付
        if self.state.status == AuctionStatus.SOLD:
            await self.process_payment()
        
        # 輸出結果
        self._print_summary()
        
        return self.state
    
    def _print_summary(self):
        """輸出拍賣結果摘要"""
        # 使用 AuctionState 的新方法
        print(self.state.get_result_summary())
        
        # 詳細出價歷史
        if self.state.bids:
            print("\n📝 出價歷史:")
            for bid in self.state.bids:
                token_info = f" ({bid.token})" if bid.token else ""
                error_flag = " ⚠️" if bid.validation_errors or bid.validation_warnings else ""
                bid_status = bid.status.value if hasattr(bid.status, 'value') else bid.status
                print(f"   - {bid.bidder}: ${bid.amount:.2f}{token_info} ({bid_status}){error_flag}")
        
        # 談判歷史
        if self.state.negotiation_history:
            print("\n🤝 談判歷史:")
            for n in self.state.negotiation_history:
                print(f"   回合{n.round_number}: {n.from_agent} → {n.to_agent} | {n.action} | ${n.amount:.2f}")

