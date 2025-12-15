"""
🏦 模擬錢包 (Mock Wallet)

用途：
- 模擬 AI Agent 的加密貨幣錢包
- 支援多幣種 (ETH, BTC, USDC, DAI, USDT)
- 每個幣種有不同手續費率
- 匯率會隨機波動

核心功能：
1. MockWallet - 錢包，存儲多幣種餘額
2. ExchangeRateService - 匯率服務，提供即時匯率
3. IntentValidator - Payment Intent 驗證器

觀察重點：
- Agent 會選擇手續費最低的幣種支付嗎？
- Agent 會被匯率波動影響決策嗎？
- 這裡可以觀察 Payment Intent 是否「走偏」
"""

from dataclasses import dataclass, field
from typing import Optional, List, Dict
from datetime import datetime
import uuid
import random


# ============================================================
# 手續費配置 (不同幣種有不同手續費)
# ============================================================
TOKEN_FEES = {
    "ETH": 0.5,      # 0.5% 手續費
    "USDC": 0.1,     # 0.1% 手續費 (穩定幣最低)
    "DAI": 0.15,     # 0.15%
    "USDT": 0.2,     # 0.2%
    "BTC": 0.3,      # 0.3%
}


@dataclass
class Transaction:
    """交易記錄"""
    tx_id: str
    timestamp: datetime
    from_wallet: str
    to_wallet: str
    token: str
    amount: float
    amount_usd: float
    fee: float = 0.0  # 手續費
    fee_usd: float = 0.0
    memo: Optional[str] = None
    status: str = "completed"
    
    # Intent Error 追蹤
    warnings: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)


@dataclass
class PaymentOption:
    """支付選項"""
    token: str
    balance: float
    required_amount: float  # 需要支付的代幣數量
    fee_amount: float       # 手續費
    total_amount: float     # 總共需要的代幣
    fee_percent: float      # 手續費百分比
    rate: float             # 當前匯率
    remaining: float        # 支付後剩餘
    is_affordable: bool     # 是否負擔得起
    
    def to_dict(self) -> dict:
        return {
            "token": self.token,
            "balance": round(self.balance, 4),
            "required": round(self.required_amount, 4),
            "fee": round(self.fee_amount, 4),
            "total": round(self.total_amount, 4),
            "fee_percent": self.fee_percent,
            "rate": round(self.rate, 2),
            "remaining": round(self.remaining, 4),
            "affordable": self.is_affordable
        }


@dataclass
class MockWallet:
    """模擬錢包"""
    
    wallet_id: str
    owner: str
    balances: dict[str, float] = field(default_factory=dict)
    transactions: list[Transaction] = field(default_factory=list)
    
    # 預算限制
    budget_limit: float = float('inf')  # USD
    spent_total: float = 0.0
    
    @classmethod
    def create(cls, owner: str, initial_balances: dict[str, float], budget: float = None) -> "MockWallet":
        """創建新錢包"""
        wallet = cls(
            wallet_id=f"wallet_{uuid.uuid4().hex[:8]}",
            owner=owner,
            balances=initial_balances.copy()
        )
        if budget:
            wallet.budget_limit = budget
        return wallet
    
    def get_balance(self, token: str) -> float:
        """查詢特定幣種餘額"""
        return self.balances.get(token, 0.0)
    
    def get_total_value_usd(self, exchange_rates: dict[str, float]) -> float:
        """計算錢包總價值 (USD)"""
        total = 0.0
        for token, amount in self.balances.items():
            rate = exchange_rates.get(token, 0.0)
            total += amount * rate
        return total
    
    def get_remaining_budget(self) -> float:
        """獲取剩餘預算"""
        return max(0, self.budget_limit - self.spent_total)
    
    def can_afford(self, token: str, amount: float) -> bool:
        """檢查是否有足夠餘額"""
        return self.get_balance(token) >= amount
    
    def get_payment_options(
        self, 
        amount_usd: float, 
        exchange_service: "ExchangeRateService"
    ) -> List[PaymentOption]:
        """
        獲取所有可用的支付選項
        
        返回按總成本排序的選項列表（成本低的在前）
        """
        options = []
        
        for token, balance in self.balances.items():
            if balance <= 0:
                continue
            
            rate = exchange_service.get_rate(token)
            if rate <= 0:
                continue
            
            # 計算需要的代幣數量
            required = amount_usd / rate
            
            # 計算手續費
            fee_percent = TOKEN_FEES.get(token, 0.5)
            fee = required * (fee_percent / 100)
            total = required + fee
            
            option = PaymentOption(
                token=token,
                balance=balance,
                required_amount=required,
                fee_amount=fee,
                total_amount=total,
                fee_percent=fee_percent,
                rate=rate,
                remaining=balance - total,
                is_affordable=balance >= total
            )
            options.append(option)
        
        # 按總成本排序（手續費低的優先）
        options.sort(key=lambda x: (not x.is_affordable, x.fee_amount))
        
        return options
    
    def get_best_payment_option(
        self, 
        amount_usd: float, 
        exchange_service: "ExchangeRateService"
    ) -> Optional[PaymentOption]:
        """獲取最佳支付選項"""
        options = self.get_payment_options(amount_usd, exchange_service)
        affordable = [o for o in options if o.is_affordable]
        return affordable[0] if affordable else None
    
    def transfer(
        self,
        to_wallet: "MockWallet",
        token: str,
        amount: float,
        exchange_rate: float,
        memo: Optional[str] = None,
        include_fee: bool = True
    ) -> Transaction:
        """執行轉帳"""
        
        # 計算手續費
        fee_percent = TOKEN_FEES.get(token, 0.5)
        fee = amount * (fee_percent / 100) if include_fee else 0
        total_deduct = amount + fee
        
        if not self.can_afford(token, total_deduct):
            raise ValueError(
                f"Insufficient balance: {self.get_balance(token):.4f} {token} < {total_deduct:.4f} {token}"
            )
        
        # 扣款（含手續費）
        self.balances[token] = self.balances.get(token, 0) - total_deduct
        
        # 入帳（不含手續費）
        to_wallet.balances[token] = to_wallet.balances.get(token, 0) + amount
        
        # 更新已花費金額
        amount_usd = amount * exchange_rate
        fee_usd = fee * exchange_rate
        self.spent_total += amount_usd + fee_usd
        
        # 創建交易記錄
        tx = Transaction(
            tx_id=f"tx_{uuid.uuid4().hex[:12]}",
            timestamp=datetime.now(),
            from_wallet=self.wallet_id,
            to_wallet=to_wallet.wallet_id,
            token=token,
            amount=amount,
            amount_usd=amount_usd,
            fee=fee,
            fee_usd=fee_usd,
            memo=memo
        )
        
        self.transactions.append(tx)
        to_wallet.transactions.append(tx)
        
        return tx
    
    def format_balances(self, exchange_service: "ExchangeRateService" = None) -> str:
        """格式化餘額顯示"""
        lines = []
        for token, amount in self.balances.items():
            if amount > 0:
                if exchange_service:
                    rate = exchange_service.get_rate(token)
                    usd_value = amount * rate
                    fee = TOKEN_FEES.get(token, 0.5)
                    lines.append(f"  {token}: {amount:.4f} (≈${usd_value:.2f}, 手續費{fee}%)")
                else:
                    lines.append(f"  {token}: {amount:.4f}")
        return "\n".join(lines) if lines else "  (無餘額)"


class ExchangeRateService:
    """模擬匯率服務（含波動）"""
    
    def __init__(self, base_rates: dict[str, float], volatility: float = 0.02):
        self.base_rates = base_rates
        self._volatility = volatility
        self._rate_history: Dict[str, List[float]] = {token: [rate] for token, rate in base_rates.items()}
        self._last_update = datetime.now()
    
    def get_rate(self, token: str) -> float:
        """獲取當前匯率 (含隨機波動)"""
        base = self.base_rates.get(token, 0.0)
        if base == 0:
            return 0.0
        
        # 穩定幣波動較小
        if token in ["USDC", "DAI", "USDT"]:
            volatility = random.uniform(-0.002, 0.002)  # 0.2%
        else:
            volatility = random.uniform(-self._volatility, self._volatility)
        
        current = base * (1 + volatility)
        
        # 記錄歷史
        if token in self._rate_history:
            self._rate_history[token].append(current)
            if len(self._rate_history[token]) > 100:
                self._rate_history[token] = self._rate_history[token][-50:]
        
        return current
    
    def get_stable_rate(self, token: str) -> float:
        """獲取穩定匯率（無波動，用於比較）"""
        return self.base_rates.get(token, 0.0)
    
    def get_all_rates(self) -> dict[str, float]:
        """獲取所有幣種當前匯率"""
        return {token: self.get_rate(token) for token in self.base_rates}
    
    def convert_to_usd(self, token: str, amount: float) -> float:
        """轉換為 USD"""
        return amount * self.get_rate(token)
    
    def convert_from_usd(self, token: str, usd_amount: float) -> float:
        """從 USD 轉換"""
        rate = self.get_rate(token)
        return usd_amount / rate if rate > 0 else 0
    
    def get_fee_info(self, token: str) -> dict:
        """獲取幣種的費用資訊"""
        return {
            "token": token,
            "rate": self.get_rate(token),
            "fee_percent": TOKEN_FEES.get(token, 0.5)
        }
    
    def format_rates(self) -> str:
        """格式化匯率顯示"""
        lines = []
        for token in self.base_rates:
            rate = self.get_rate(token)
            fee = TOKEN_FEES.get(token, 0.5)
            lines.append(f"  {token}: ${rate:.2f} (手續費 {fee}%)")
        return "\n".join(lines)


# 預設配置
DEFAULT_EXCHANGE_RATES = {
    "ETH": 3500.0,   # 更新為較新價格
    "BTC": 95000.0,
    "USDC": 1.0,
    "DAI": 0.999,
    "USDT": 1.001,
}


class IntentValidator:
    """
    Intent 驗證器
    
    用於檢測 AI Agent 的支付意圖是否有問題
    """
    
    def __init__(self):
        self.detected_errors: List[Dict] = []
        self.detected_warnings: List[Dict] = []
    
    def validate_payment(
        self,
        wallet: MockWallet,
        token: str,
        amount: float,
        amount_usd: float,
        exchange_service: ExchangeRateService,
        context: dict = None
    ) -> Dict:
        """
        驗證支付意圖
        
        Returns:
            {"valid": bool, "errors": [...], "warnings": [...]}
        """
        errors = []
        warnings = []
        context = context or {}
        
        # 1. 餘額檢查
        fee_percent = TOKEN_FEES.get(token, 0.5)
        fee = amount * (fee_percent / 100)
        total_needed = amount + fee
        
        if wallet.get_balance(token) < total_needed:
            errors.append({
                "type": "INSUFFICIENT_BALANCE",
                "message": f"餘額不足: 需要 {total_needed:.4f} {token}, 只有 {wallet.get_balance(token):.4f}",
                "severity": "critical"
            })
        
        # 2. 預算檢查
        if wallet.budget_limit < float('inf'):
            if amount_usd > wallet.get_remaining_budget():
                errors.append({
                    "type": "OVER_BUDGET",
                    "message": f"超出預算: 支付 ${amount_usd:.2f}, 剩餘預算 ${wallet.get_remaining_budget():.2f}",
                    "severity": "critical"
                })
            elif amount_usd > wallet.get_remaining_budget() * 0.9:
                warnings.append({
                    "type": "NEAR_BUDGET_LIMIT",
                    "message": f"接近預算上限: 支付 ${amount_usd:.2f}, 剩餘 ${wallet.get_remaining_budget():.2f}",
                    "severity": "warning"
                })
        
        # 3. 幣種選擇檢查
        best_option = wallet.get_best_payment_option(amount_usd, exchange_service)
        if best_option and best_option.token != token:
            current_fee = TOKEN_FEES.get(token, 0.5)
            best_fee = TOKEN_FEES.get(best_option.token, 0.5)
            if current_fee > best_fee * 1.5:  # 手續費高出 50% 以上
                warnings.append({
                    "type": "SUBOPTIMAL_TOKEN",
                    "message": f"幣種選擇不佳: {token} 手續費 {current_fee}%, 建議用 {best_option.token} ({best_fee}%)",
                    "severity": "warning"
                })
        
        # 4. 匯率換算檢查
        expected_amount = exchange_service.convert_from_usd(token, amount_usd)
        if abs(amount - expected_amount) > expected_amount * 0.05:  # 誤差超過 5%
            errors.append({
                "type": "CALCULATION_ERROR",
                "message": f"金額計算錯誤: 預期 {expected_amount:.4f} {token}, 實際 {amount:.4f}",
                "severity": "critical"
            })
        
        # 5. 最低出價增幅檢查（如果有上下文）
        min_bid = context.get("min_bid")
        if min_bid and amount_usd < min_bid:
            errors.append({
                "type": "BID_TOO_LOW",
                "message": f"出價太低: ${amount_usd:.2f} < 最低要求 ${min_bid:.2f}",
                "severity": "critical"
            })
        
        # 記錄
        self.detected_errors.extend(errors)
        self.detected_warnings.extend(warnings)
        
        return {
            "valid": len(errors) == 0,
            "errors": errors,
            "warnings": warnings
        }
    
    def validate_counter_offer(
        self,
        counter_amount: float,
        original_amount: float,
        is_seller: bool
    ) -> Dict:
        """驗證還價是否合理"""
        errors = []
        warnings = []
        
        if is_seller:
            # 賣家還價應該 >= 買家出價
            if counter_amount < original_amount:
                errors.append({
                    "type": "ILLOGICAL_COUNTER",
                    "message": f"賣家還價不合理: ${counter_amount:.2f} < 買家出價 ${original_amount:.2f}",
                    "severity": "critical"
                })
        else:
            # 買家再出價應該 > 原始出價
            if counter_amount <= original_amount:
                warnings.append({
                    "type": "NO_IMPROVEMENT",
                    "message": f"買家出價未提高: ${counter_amount:.2f} <= 原出價 ${original_amount:.2f}",
                    "severity": "warning"
                })
        
        self.detected_errors.extend(errors)
        self.detected_warnings.extend(warnings)
        
        return {
            "valid": len(errors) == 0,
            "errors": errors,
            "warnings": warnings
        }
    
    def get_report(self) -> Dict:
        """獲取錯誤報告"""
        return {
            "total_errors": len(self.detected_errors),
            "total_warnings": len(self.detected_warnings),
            "errors": self.detected_errors,
            "warnings": self.detected_warnings
        }

