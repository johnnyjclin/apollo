"""
Base Agent - 基礎 Agent 抽象類
"""

from abc import ABC, abstractmethod
from typing import Any, Optional
from dataclasses import dataclass, field


@dataclass
class AgentConfig:
    """Agent 配置"""
    name: str
    model: str = "gemini-2.0-flash"
    temperature: float = 0.7
    max_tokens: int = 4096
    system_prompt: Optional[str] = None


class BaseAgent(ABC):
    """
    Agent 基礎類
    
    所有 Agent 都需要實現：
    1. invoke - 執行單次對話
    2. run - 執行任務（可能包含多輪對話）
    """
    
    def __init__(self, config: AgentConfig):
        self.config = config
        self.name = config.name
        self.conversation_history: list[dict] = []
    
    @abstractmethod
    async def invoke(self, message: str) -> str:
        """執行單次對話"""
        pass
    
    @abstractmethod
    async def run(self, task: str) -> Any:
        """執行任務"""
        pass
    
    def add_to_history(self, role: str, content: str):
        """添加到對話歷史"""
        self.conversation_history.append({
            "role": role,
            "content": content
        })
    
    def clear_history(self):
        """清除對話歷史"""
        self.conversation_history = []
    
    def get_history(self) -> list[dict]:
        """獲取對話歷史"""
        return self.conversation_history.copy()

