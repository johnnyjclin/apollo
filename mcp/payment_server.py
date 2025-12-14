"""
MCP Payment Server - Model Context Protocol 支付服務

MCP (Model Context Protocol) 是一個標準化的 AI 工具調用協議。
這個服務器提供支付相關的工具給 AI Agent 使用。

使用方式：
    1. 啟動 MCP Server
    2. 在 Agent 中連接此 Server
    3. Agent 可以調用支付工具
"""

import json
from typing import Any, Optional
from dataclasses import dataclass

# MCP 相關導入 (需要 mcp 套件)
try:
    from mcp.server import Server
    from mcp.types import Tool, TextContent
    MCP_AVAILABLE = True
except ImportError:
    MCP_AVAILABLE = False
    print("⚠️ MCP 套件未安裝。運行: pip install mcp")


@dataclass
class PaymentRequest:
    """支付請求"""
    amount_usd: float
    recipient: str
    preferred_token: Optional[str] = None
    memo: Optional[str] = None


@dataclass
class PaymentResponse:
    """支付回應"""
    success: bool
    tx_id: Optional[str] = None
    token: Optional[str] = None
    amount: Optional[float] = None
    error: Optional[str] = None


class PaymentMCPServer:
    """
    MCP 支付服務器
    
    提供以下工具：
    1. get_wallet_balance - 查詢錢包餘額
    2. get_exchange_rates - 獲取匯率
    3. calculate_payment - 計算支付選項
    4. execute_payment - 執行支付
    """
    
    def __init__(self, wallet, exchange_service):
        self.wallet = wallet
        self.exchange_service = exchange_service
        
        if MCP_AVAILABLE:
            self.server = Server("payment-server")
            self._setup_tools()
        else:
            self.server = None
    
    def _setup_tools(self):
        """設置 MCP 工具"""
        
        @self.server.tool()
        async def get_wallet_balance(token: Optional[str] = None) -> str:
            """
            查詢錢包餘額
            
            Args:
                token: 幣種名稱 (可選)
            
            Returns:
                餘額信息
            """
            if token:
                balance = self.wallet.get_balance(token)
                rate = self.exchange_service.get_rate(token)
                return json.dumps({
                    "token": token,
                    "balance": balance,
                    "usd_value": balance * rate
                })
            else:
                balances = {}
                rates = self.exchange_service.get_all_rates()
                total = 0
                for t, b in self.wallet.balances.items():
                    rate = rates.get(t, 0)
                    usd = b * rate
                    balances[t] = {"balance": b, "usd_value": usd}
                    total += usd
                return json.dumps({
                    "balances": balances,
                    "total_usd": total
                })
        
        @self.server.tool()
        async def get_exchange_rates() -> str:
            """獲取當前匯率"""
            rates = self.exchange_service.get_all_rates()
            return json.dumps(rates)
        
        @self.server.tool()
        async def calculate_payment(amount_usd: float) -> str:
            """
            計算支付選項
            
            Args:
                amount_usd: 需支付的 USD 金額
            
            Returns:
                各幣種的支付選項
            """
            rates = self.exchange_service.get_all_rates()
            options = []
            
            for token, balance in self.wallet.balances.items():
                rate = rates.get(token, 0)
                if rate <= 0:
                    continue
                
                required = amount_usd / rate
                can_afford = balance >= required
                
                options.append({
                    "token": token,
                    "required_amount": required,
                    "current_balance": balance,
                    "can_afford": can_afford,
                    "remaining_after": balance - required if can_afford else None
                })
            
            return json.dumps({
                "amount_usd": amount_usd,
                "options": options
            })
        
        @self.server.tool()
        async def execute_payment(
            token: str,
            amount: float,
            recipient_address: str,
            memo: Optional[str] = None
        ) -> str:
            """
            執行支付
            
            Args:
                token: 幣種
                amount: 數量
                recipient_address: 收款地址
                memo: 備註
            
            Returns:
                交易結果
            """
            try:
                rate = self.exchange_service.get_rate(token)
                
                # 這裡需要有收款錢包的引用
                # 在實際使用中，需要通過 recipient_address 查找
                
                return json.dumps({
                    "success": True,
                    "message": f"模擬支付: {amount} {token} to {recipient_address}",
                    "usd_value": amount * rate
                })
                
            except Exception as e:
                return json.dumps({
                    "success": False,
                    "error": str(e)
                })
    
    async def run(self, transport="stdio"):
        """啟動 MCP Server"""
        if not MCP_AVAILABLE:
            print("❌ MCP 不可用，請安裝: pip install mcp")
            return
        
        print(f"🚀 啟動 Payment MCP Server (transport: {transport})")
        
        if transport == "stdio":
            from mcp.server.stdio import stdio_server
            async with stdio_server() as (read_stream, write_stream):
                await self.server.run(
                    read_stream,
                    write_stream,
                    self.server.create_initialization_options()
                )


# MCP Client 輔助類
class PaymentMCPClient:
    """
    MCP 支付客戶端 - Agent 用來連接 MCP Server
    """
    
    def __init__(self, server_command: list[str]):
        """
        Args:
            server_command: 啟動 server 的命令
                          例如: ["python", "mcp/payment_server.py"]
        """
        self.server_command = server_command
        self.client = None
    
    async def connect(self):
        """連接到 MCP Server"""
        if not MCP_AVAILABLE:
            raise ImportError("MCP 套件未安裝")
        
        from mcp.client import Client
        from mcp.client.stdio import stdio_client
        
        self.client = Client("payment-client")
        
        # 啟動並連接 server
        async with stdio_client(self.server_command) as (read, write):
            await self.client.connect(read, write)
    
    async def call_tool(self, tool_name: str, arguments: dict) -> Any:
        """調用 MCP 工具"""
        if not self.client:
            raise RuntimeError("未連接到 MCP Server")
        
        result = await self.client.call_tool(tool_name, arguments)
        return json.loads(result.content[0].text)


# 獨立運行時啟動 Server
if __name__ == "__main__":
    import asyncio
    import sys
    sys.path.insert(0, str(Path(__file__).parent.parent))
    
    from experiments.wallet.mock_wallet import (
        MockWallet,
        ExchangeRateService,
        DEFAULT_EXCHANGE_RATES
    )
    from pathlib import Path
    
    # 創建模擬錢包
    wallet = MockWallet.create(
        owner="MCP_Test_Wallet",
        initial_balances={"ETH": 1.0, "USDC": 1000.0, "DAI": 500.0}
    )
    exchange = ExchangeRateService(DEFAULT_EXCHANGE_RATES)
    
    # 創建並運行 Server
    server = PaymentMCPServer(wallet, exchange)
    asyncio.run(server.run())

