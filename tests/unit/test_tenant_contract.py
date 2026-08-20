from app.domain.tenancy import Role, TenantPrincipal


def test_principal_requires_organization_scope() -> None:
    principal = TenantPrincipal(
        subject="user-123",
        organization_id="org-123",
        role=Role.ANALYST,
    )

    assert principal.organization_id == "org-123"
    assert principal.role is Role.ANALYST
