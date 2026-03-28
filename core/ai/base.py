from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import List


@dataclass
class ProviderConfig:
    model: str
    base_url: str
    timeout: int = 60


class AIProvider(ABC):
    config: ProviderConfig

    @abstractmethod
    def generate(self, prompt: str) -> str:
        """Send a prompt and return the raw text response."""
        ...

    @abstractmethod
    def ping(self) -> bool:
        """Return True if the provider endpoint is reachable."""
        ...

    @abstractmethod
    def list_models(self) -> List[str]:
        """Return a list of available model names."""
        ...
