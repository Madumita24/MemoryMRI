from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from memory_mri.domain.actions import CustomerSupportAction, DomainName
from memory_mri.schemas import AgentScenario, Memory, MemoryStatus


def test_memory_date_validation() -> None:
    with pytest.raises(ValidationError):
        Memory(
            id="mem_bad",
            entity_id="cust_1",
            domain=DomainName.CUSTOMER_SUPPORT,
            content="bad dates",
            source="seed",
            created_at=datetime.now(UTC),
            valid_from=datetime(2026, 1, 2, tzinfo=UTC),
            valid_until=datetime(2026, 1, 1, tzinfo=UTC),
            status=MemoryStatus.ACTIVE,
            confidence=0.9,
            retrieval_priority=10,
        )


def test_scenario_requires_expected_action_membership() -> None:
    with pytest.raises(ValidationError):
        AgentScenario(
            id="scn_bad",
            title="bad",
            domain=DomainName.CUSTOMER_SUPPORT,
            user_input="help",
            allowed_actions=[CustomerSupportAction.ISSUE_REFUND.value],
            expected_action=CustomerSupportAction.DENY_REFUND.value,
            memory_ids=["mem_1"],
            expected_problematic_memory_ids=[],
            failure_category="stale-memory",
            explanation="bad action",
            evaluator_config={},
        )
