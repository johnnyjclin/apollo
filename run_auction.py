#!/usr/bin/env python3
"""
🏷️ Apollo - 拍賣遊戲 PoC

驗證 AI Agent 的 Payment Intent 行為

執行方式:
    # 模擬模式 (無需 API Key)
    python run_auction.py --mock
    
    # 使用 Gemini
    export GOOGLE_API_KEY=your-api-key
    python run_auction.py

API Key 取得: https://aistudio.google.com/api-keys
"""

import asyncio
import argparse
import os
import sys
from pathlib import Path

# 確保路徑正確
sys.path.insert(0, str(Path(__file__).parent))

from games.auction import AuctionGame, AuctionItem
from agents.auction_agent import create_auction_agents


async def run_single_auction(
    item_name: str = "稀有 NFT 藝術品",
    reserve_price: float = 100,
    api_key: str = None
):
    """執行單場拍賣"""
    
    print("\n" + "=" * 60)
    print("🏷️  Apollo - AI Agent 拍賣遊戲 PoC")
    print("=" * 60)
    print("\n目的: 觀察 Agent 的談判行為與 Payment Intent")
    
    # 創建 Agents
    print("\n🔧 初始化 Agents...")
    seller, buyers, exchange_service = create_auction_agents(
        seller_name="Seller_Alice",
        buyer_names=["Buyer_Bob", "Buyer_Charlie"],
        api_key=api_key
    )
    
    # 創建拍賣物品
    item = AuctionItem.create(
        name=item_name,
        description="一件限量版數位藝術品，具有收藏價值",
        reserve_price=reserve_price,
        seller=seller.name
    )
    
    # 創建遊戲
    game = AuctionGame(
        seller_agent=seller,
        buyer_agents=buyers,
        item=item,
        max_rounds=5
    )
    
    # 執行拍賣
    final_state = await game.run_auction()
    
    # 分析結果
    print_analysis(final_state)
    
    return final_state


def print_analysis(state):
    """分析拍賣結果"""
    print("\n" + "=" * 60)
    print("📊 行為分析")
    print("=" * 60)
    
    # 談判分析
    print("\n🤝 談判行為分析:")
    
    accepts = [n for n in state.negotiation_history if n.action == "accept"]
    rejects = [n for n in state.negotiation_history if n.action == "reject"]
    counters = [n for n in state.negotiation_history if n.action == "counter"]
    
    print(f"   接受次數: {len(accepts)}")
    print(f"   拒絕次數: {len(rejects)}")
    print(f"   還價次數: {len(counters)}")
    
    # 出價分析
    print("\n💰 出價行為分析:")
    
    if state.bids:
        amounts = [b.amount for b in state.bids]
        print(f"   總出價次數: {len(state.bids)}")
        print(f"   最低出價: ${min(amounts)}")
        print(f"   最高出價: ${max(amounts)}")
        print(f"   平均出價: ${sum(amounts)/len(amounts):.2f}")
    
    # Payment Intent 分析
    print("\n💳 Payment Intent 分析:")
    
    if state.payment_intent:
        intent = state.payment_intent
        print(f"   選擇幣種: {intent.get('token', 'N/A')}")
        print(f"   支付金額: {intent.get('amount', 'N/A')} {intent.get('token', '')}")
        print(f"   等值 USD: ${intent.get('amount_usd', 'N/A')}")
        print(f"   收款方: {intent.get('recipient', 'N/A')}")
        print(f"   理由: {intent.get('reasoning', 'N/A')[:100]}...")
    
    if state.payment_errors:
        print("\n⚠️  發現的 Payment Intent 錯誤:")
        for error in state.payment_errors:
            print(f"   ❌ {error['type']}")
            print(f"      {error['message']}")
    else:
        print("\n✅ Payment Intent 無明顯錯誤")
    
    # 結論
    print("\n" + "=" * 60)
    print("🔑 關鍵觀察點")
    print("=" * 60)
    print("""
1. Agent 的出價策略是否合理？
   - 是否超出預算？
   - 是否合理評估物品價值？

2. 談判行為是否符合邏輯？
   - 還價金額是否合理？
   - 接受/拒絕的時機是否正確？

3. Payment Intent 是否正確？
   - 金額是否匹配成交價？
   - 收款方是否正確？
   - 幣種選擇是否合理？

這些觀察可以幫助驗證信任層的必要性！
""")


async def run_multiple_auctions(count: int = 3, api_key: str = None):
    """執行多場拍賣並統計"""
    
    print("\n" + "=" * 60)
    print(f"🏷️  批次執行 {count} 場拍賣")
    print("=" * 60)
    
    results = []
    error_count = 0
    
    items = [
        ("稀有 NFT #001", 100),
        ("限量版運動鞋", 200),
        ("古董手錶", 500),
        ("藝術畫作", 300),
        ("限量公仔", 150),
    ]
    
    for i in range(count):
        item_name, price = items[i % len(items)]
        print(f"\n{'='*40}")
        print(f"📍 拍賣 {i+1}/{count}")
        print(f"{'='*40}")
        
        state = await run_single_auction(
            item_name=f"{item_name} (#{i+1})",
            reserve_price=price,
            api_key=api_key
        )
        
        results.append(state)
        
        if state.payment_errors:
            error_count += len(state.payment_errors)
    
    # 統計
    print("\n" + "=" * 60)
    print("📊 批次統計")
    print("=" * 60)
    
    sold_count = sum(1 for r in results if r.winner)
    total_bids = sum(len(r.bids) for r in results)
    total_negotiations = sum(len(r.negotiation_history) for r in results)
    
    print(f"   總拍賣數: {count}")
    print(f"   成交數: {sold_count}")
    print(f"   流標數: {count - sold_count}")
    print(f"   總出價次數: {total_bids}")
    print(f"   總談判次數: {total_negotiations}")
    print(f"   Payment Intent 錯誤數: {error_count}")
    
    if error_count > 0:
        print(f"\n⚠️  錯誤率: {error_count}/{sold_count} = {error_count/max(sold_count,1)*100:.1f}%")
        print("   這說明信任層是必要的！")
    else:
        print("\n✅ 未發現 Payment Intent 錯誤")


async def main():
    parser = argparse.ArgumentParser(
        description="Apollo - AI Agent 拍賣遊戲 PoC"
    )
    parser.add_argument(
        "--mock", 
        action="store_true", 
        help="使用模擬模式 (無需 API Key)"
    )
    parser.add_argument(
        "--batch",
        type=int,
        default=0,
        help="批次執行多場拍賣 (指定場數)"
    )
    parser.add_argument(
        "--price",
        type=float,
        default=100,
        help="物品底價 (USD)"
    )
    args = parser.parse_args()
    
    # 檢查 Ollama 是否運行
    def check_ollama():
        try:
            import urllib.request
            req = urllib.request.Request("http://localhost:11434/api/tags", method="GET")
            with urllib.request.urlopen(req, timeout=2) as response:
                return response.status == 200
        except:
            return False
    
    ollama_running = check_ollama()
    groq_key = os.getenv("GROQ_API_KEY")
    gemini_key = os.getenv("GOOGLE_API_KEY")
    
    has_llm = ollama_running or groq_key or gemini_key
    
    if not has_llm and not args.mock:
        print("\n⚠️  未檢測到可用的 LLM!")
        print("\n" + "=" * 50)
        print("🏠 推薦：Ollama (本地運行，無地區限制)")
        print("=" * 50)
        print("1. 安裝: https://ollama.com/download")
        print("2. 拉取模型: ollama pull llama3.2")
        print("3. 啟動服務: ollama serve")
        print("4. 重新運行此程式")
        print("\n" + "=" * 50)
        print("☁️  或者：Google Gemini")
        print("=" * 50)
        print("1. 訪問: https://aistudio.google.com/api-keys")
        print("2. 設置: export GOOGLE_API_KEY=your-key")
        print("\n或使用模擬模式: python run_auction.py --mock")
        return
    
    if args.mock:
        print("\n📌 使用模擬模式 (無 LLM)")
    elif ollama_running:
        model = os.getenv("OLLAMA_MODEL", "llama3.2")
        print(f"\n✅ 檢測到 Ollama 運行中，使用本地模型: {model}")
    elif groq_key:
        print(f"\n✅ 使用 Groq: {groq_key[:10]}...")
    elif gemini_key:
        print(f"\n✅ 使用 Gemini: {gemini_key[:10]}...")
    
    # API Key 不需要傳遞，Agent 會自動從環境變數讀取
    # 執行
    if args.batch > 0:
        await run_multiple_auctions(count=args.batch, api_key=None)
    else:
        await run_single_auction(
            reserve_price=args.price,
            api_key=None
        )
    
    print("\n" + "=" * 60)
    print("✅ 實驗完成!")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())

