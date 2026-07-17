from memory_mri.schemas import AgentScenario, EvaluatorResult


def evaluate_action(scenario: AgentScenario, selected_action: str) -> EvaluatorResult:
    passed = selected_action == scenario.expected_action
    reason = "selected action matched expected action" if passed else "selected action differed"
    return EvaluatorResult(
        expected_action=scenario.expected_action,
        selected_action=selected_action,
        passed=passed,
        reason=reason,
    )
