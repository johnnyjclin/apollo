"""
拍賣遊戲 - 含 Negotiation 的 Agent 對戰

場景：
1. 多個 Agent 競標一個物品
2. Agent 可以出價、談判、接受/拒絕
3. 觀察 Agent 的 Payment Intent 是否正確

Negotiation 流程：
1. 賣家設定底價
2. 買家出價
3. 賣家可接受、拒絕、或還價
4. 買家可接受還價或再次出價
5. 成交後買家需支付
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
        print(f"\n{'='*60}")
        print(f"📋 拍賣結果摘要")
        print(f"{'='*60}")
        print(f"   物品: {self.item.name}")
        print(f"   狀態: {self.state.status.value}")
        
        if self.state.status == AuctionStatus.SOLD:
            print(f"   得標者: {self.state.winner}")
            print(f"   成交價: ${self.state.final_price}")
            print(f"   談判回合: {len(self.state.negotiation_history)}")
            
            if self.state.payment_errors:
                print(f"\n   ⚠️  Payment Intent 錯誤:")
                for e in self.state.payment_errors:
                    print(f"      - {e['type']}: {e['message']}")
            else:
                print(f"\n   ✅ 支付成功完成")
        
        print(f"\n   出價歷史:")
        for bid in self.state.bids:
            print(f"      - {bid.bidder}: ${bid.amount} ({bid.status.value})")
        
        print(f"\n   談判歷史:")
        for n in self.state.negotiation_history:
            print(f"      回合{n.round_number}: {n.from_agent} → {n.to_agent} | {n.action} | ${n.amount}")

