"""
模擬錢包 - 用於 PoC 實驗

支援多幣種餘額管理
"""

from dataclasses import dataclass, field
from typing import Optional
from datetime import datetime
import uuid
import random


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
    memo: Optional[str] = None
    status: str = "completed"


@dataclass
class MockWallet:
    """模擬錢包"""
    
    wallet_id: str
    owner: str
    balances: dict[str, float] = field(default_factory=dict)
    transactions: list[Transaction] = field(default_factory=list)
    
    @classmethod
    def create(cls, owner: str, initial_balances: dict[str, float]) -> "MockWallet":
        """創建新錢包"""
        return cls(
            wallet_id=f"wallet_{uuid.uuid4().hex[:8]}",
            owner=owner,
            balances=initial_balances.copy()
        )
    
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
    
    def can_afford(self, token: str, amount: float) -> bool:
        """檢查是否有足夠餘額"""
        return self.get_balance(token) >= amount
    
    def transfer(
        self,
        to_wallet: "MockWallet",
        token: str,
        amount: float,
        exchange_rate: float,
        memo: Optional[str] = None
    ) -> Transaction:
        """執行轉帳"""
        if not self.can_afford(token, amount):
            raise ValueError(
                f"Insufficient balance: {self.get_balance(token)} {token} < {amount} {token}"
            )
        
        # 扣款
        self.balances[token] = self.balances.get(token, 0) - amount
        
        # 入帳
        to_wallet.balances[token] = to_wallet.balances.get(token, 0) + amount
        
        # 創建交易記錄
        tx = Transaction(
            tx_id=f"tx_{uuid.uuid4().hex[:12]}",
            timestamp=datetime.now(),
            from_wallet=self.wallet_id,
            to_wallet=to_wallet.wallet_id,
            token=token,
            amount=amount,
            amount_usd=amount * exchange_rate,
            memo=memo
        )
        
        self.transactions.append(tx)
        to_wallet.transactions.append(tx)
        
        return tx


class ExchangeRateService:
    """模擬匯率服務"""
    
    def __init__(self, base_rates: dict[str, float], volatility: float = 0.02):
        self.base_rates = base_rates
        self._volatility = volatility
    
    def get_rate(self, token: str) -> float:
        """獲取當前匯率 (含隨機波動)"""
        base = self.base_rates.get(token, 0.0)
        volatility = random.uniform(-self._volatility, self._volatility)
        return base * (1 + volatility)
    
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


# 預設配置
DEFAULT_EXCHANGE_RATES = {
    "ETH": 2000.0,
    "USDC": 1.0,
    "DAI": 0.999,
    "USDT": 1.001,
}

