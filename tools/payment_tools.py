"""
支付工具 - 供 Agent 使用的支付相關工具

這些工具讓 Agent 能夠：
1. 查詢錢包餘額
2. 查詢匯率
3. 創建支付意圖
4. 執行轉帳
"""

from typing import Optional
from langchain_core.tools import tool, StructuredTool
from pydantic import BaseModel, Field


class WalletBalanceInput(BaseModel):
    """查詢錢包餘額的輸入"""
    token: Optional[str] = Field(
        default=None,
        description="要查詢的幣種，如 ETH, USDC, DAI。留空則查詢所有幣種。"
    )


class PaymentInput(BaseModel):
    """支付輸入"""
    token: str = Field(description="支付使用的幣種")
    amount: float = Field(description="支付數量")
    recipient: str = Field(description="收款方")
    reasoning: str = Field(description="選擇此支付方式的理由")


def create_payment_tools(wallet, exchange_service, recipient_wallet=None):
    """
    創建支付相關工具
    
    Args:
        wallet: 錢包實例
        exchange_service: 匯率服務
        recipient_wallet: 收款錢包 (可選)
    
    Returns:
        工具列表
    """
    
    @tool
    def get_wallet_balance(token: Optional[str] = None) -> str:
        """
        查詢錢包餘額。
        
        Args:
            token: 幣種名稱 (如 ETH, USDC)。留空則返回所有餘額。
        
        Returns:
            餘額信息
        """
        if token:
            balance = wallet.get_balance(token)
            rate = exchange_service.get_rate(token)
            usd_value = balance * rate
            return f"{token}: {balance:.6f} (≈${usd_value:.2f} USD)"
        else:
            result = "錢包餘額:\n"
            rates = exchange_service.get_all_rates()
            total_usd = 0
            for t, balance in wallet.balances.items():
                rate = rates.get(t, 0)
                usd_value = balance * rate
                total_usd += usd_value
                result += f"  {t}: {balance:.6f} (≈${usd_value:.2f})\n"
            result += f"總價值: ${total_usd:.2f} USD"
            return result
    
    @tool
    def get_exchange_rates() -> str:
        """
        獲取當前所有幣種的匯率 (相對於 USD)。
        
        Returns:
            匯率信息
        """
        rates = exchange_service.get_all_rates()
        result = "當前匯率 (1 token = ? USD):\n"
        for token, rate in rates.items():
            result += f"  {token}: ${rate:.4f}\n"
        return result
    
    @tool
    def calculate_payment_options(amount_usd: float) -> str:
        """
        計算支付指定 USD 金額的各種選項。
        
        Args:
            amount_usd: 需要支付的 USD 金額
        
        Returns:
            各幣種的支付選項
        """
        rates = exchange_service.get_all_rates()
        result = f"支付 ${amount_usd} USD 的選項:\n\n"
        
        for token, balance in wallet.balances.items():
            rate = rates.get(token, 0)
            if rate <= 0:
                continue
            
            required = amount_usd / rate
            can_afford = balance >= required
            remaining = balance - required if can_afford else 0
            
            status = "✅ 可支付" if can_afford else "❌ 餘額不足"
            result += f"{token}:\n"
            result += f"  需要: {required:.6f} {token}\n"
            result += f"  現有: {balance:.6f} {token}\n"
            result += f"  剩餘: {remaining:.6f} {token}\n"
            result += f"  狀態: {status}\n\n"
        
        return result
    
    @tool
    def execute_payment(token: str, amount: float, reasoning: str) -> str:
        """
        執行支付。選擇一種幣種並支付指定數量。
        
        Args:
            token: 選擇的幣種 (如 ETH, USDC, DAI)
            amount: 支付數量
            reasoning: 選擇此支付方式的理由
        
        Returns:
            支付結果
        """
        if recipient_wallet is None:
            return "錯誤: 未設置收款錢包"
        
        try:
            rate = exchange_service.get_rate(token)
            tx = wallet.transfer(
                to_wallet=recipient_wallet,
                token=token,
                amount=amount,
                exchange_rate=rate,
                memo=reasoning[:100]
            )
            
            return (
                f"✅ 支付成功!\n"
                f"交易 ID: {tx.tx_id}\n"
                f"支付: {amount:.6f} {token} (≈${tx.amount_usd:.2f})\n"
                f"理由: {reasoning}"
            )
        except ValueError as e:
            return f"❌ 支付失敗: {str(e)}"
    
    return [
        get_wallet_balance,
        get_exchange_rates,
        calculate_payment_options,
        execute_payment
    ]


# 專門用於遊戲的工具
def create_game_tools():
    """創建遊戲相關工具"""
    
    @tool
    def make_rps_choice(choice: str) -> str:
        """
        在剪刀石頭布遊戲中做出選擇。
        
        Args:
            choice: 選擇 'rock' (石頭), 'paper' (布), 或 'scissors' (剪刀)
        
        Returns:
            確認選擇
        """
        valid = ["rock", "paper", "scissors"]
        if choice.lower() not in valid:
            return f"無效選擇！請選擇: {valid}"
        return f"你選擇了: {choice}"
    
    return [make_rps_choice]

