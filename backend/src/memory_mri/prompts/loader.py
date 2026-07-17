from __future__ import annotations

from pathlib import Path

from memory_mri.domain.actions import DomainName

PROMPT_FILES: dict[DomainName, str] = {
    DomainName.CUSTOMER_SUPPORT: "customer_support_{version}.md",
    DomainName.DEVOPS: "devops_{version}.md",
    DomainName.WORKPLACE_EXPENSE: "workplace_expense_{version}.md",
}


def load_domain_prompt(domain: DomainName, version: str, allowed_actions: list[str]) -> str:
    prompt_dir = Path(__file__).resolve().parent
    filename = PROMPT_FILES[domain].format(version=version)
    template = (prompt_dir / filename).read_text(encoding="utf-8")
    return template.format(allowed_actions=", ".join(allowed_actions), prompt_version=version)
