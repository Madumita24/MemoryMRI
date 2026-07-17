from enum import StrEnum


class DomainName(StrEnum):
    CUSTOMER_SUPPORT = "customer_support"
    DEVOPS = "devops"
    WORKPLACE_EXPENSE = "workplace_expense"


class CustomerSupportAction(StrEnum):
    ISSUE_REFUND = "ISSUE_REFUND"
    REQUEST_MANAGER_APPROVAL = "REQUEST_MANAGER_APPROVAL"
    DENY_REFUND = "DENY_REFUND"
    ASK_FOR_INFORMATION = "ASK_FOR_INFORMATION"


class DevOpsAction(StrEnum):
    DEPLOY_STAGING = "DEPLOY_STAGING"
    DEPLOY_PRODUCTION = "DEPLOY_PRODUCTION"
    BLOCK_DEPLOYMENT = "BLOCK_DEPLOYMENT"
    REQUEST_ENGINEER_REVIEW = "REQUEST_ENGINEER_REVIEW"


class WorkplaceExpenseAction(StrEnum):
    AUTO_APPROVE = "AUTO_APPROVE"
    ESCALATE_MANAGER = "ESCALATE_MANAGER"
    ESCALATE_DIRECTOR = "ESCALATE_DIRECTOR"
    DENY_EXPENSE = "DENY_EXPENSE"
    REQUEST_DOCUMENTATION = "REQUEST_DOCUMENTATION"


DOMAIN_ACTIONS: dict[DomainName, tuple[str, ...]] = {
    DomainName.CUSTOMER_SUPPORT: tuple(action.value for action in CustomerSupportAction),
    DomainName.DEVOPS: tuple(action.value for action in DevOpsAction),
    DomainName.WORKPLACE_EXPENSE: tuple(action.value for action in WorkplaceExpenseAction),
}
