from __future__ import annotations

from abc import ABC, abstractmethod

from memory_mri.schemas import AgentScenario, ExecutionTrace, Memory


class AgentRunner(ABC):
    model_name: str
    prompt_version: str

    @abstractmethod
    def run_scenario(self, scenario: AgentScenario, memories: list[Memory]) -> ExecutionTrace:
        raise NotImplementedError
