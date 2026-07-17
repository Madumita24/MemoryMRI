from __future__ import annotations

from memory_mri.agents.base import AgentRunner
from memory_mri.schemas import AgentInput, AgentScenario, ExecutionTrace, Memory, build_agent_input


class OpenAIAgentRunner(AgentRunner):
    model_name = "gpt-5.6"
    prompt_version = "unimplemented"

    def build_request_payload(self, scenario: AgentScenario, memories: list[Memory]) -> AgentInput:
        return build_agent_input(scenario, memories)

    def run_scenario(self, scenario: AgentScenario, memories: list[Memory]) -> ExecutionTrace:
        raise NotImplementedError("OpenAI runner integration is scheduled for a later milestone")
