from datetime import date, datetime
from decimal import Decimal

import pytest
from fastapi import FastAPI
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from auth_microservice.db.models.oltp import (
    BillingCycleEnum,
    Invoice,
    InvoiceStatusEnum,
    PaymentMethodEnum,
    PaymentStatusEnum,
    PlanTypeEnum,
    SubscriptionHistoryStatusEnum,
    SupportLevelEnum,
)
from auth_microservice.settings import settings


@pytest.fixture
def bootstrap_secret() -> str:
    original = settings.bootstrap_secret
    secret = "billing-bootstrap-secret"
    settings.bootstrap_secret = secret
    try:
        yield secret
    finally:
        settings.bootstrap_secret = original


async def _bootstrap_and_login(
    client: AsyncClient,
    fastapi_app: FastAPI,
    secret: str,
) -> tuple[int, dict[str, str]]:
    bootstrap_url = fastapi_app.url_path_for("bootstrap_organization")
    payload = {
        "bootstrap_secret": secret,
        "organization_name": "Billing Academy",
        "admin_user": {
            "first_name": "Bill",
            "last_name": "Admin",
            "username": "bill.admin",
            "password": "BillingPass123!",
            "contact_information": {"email": "bill.admin@example.com"},
        },
    }
    response = await client.post(bootstrap_url, json=payload)
    assert response.status_code == 201
    organization_id = response.json()["organization_id"]

    login_url = fastapi_app.url_path_for("login")
    login_response = await client.post(
        login_url,
        json={"username": payload["admin_user"]["username"], "password": payload["admin_user"]["password"]},
    )
    assert login_response.status_code == 200
    tokens = login_response.json()["tokens"]
    headers = {"Authorization": f"Bearer {tokens['access_token']}"}
    return organization_id, headers


@pytest.mark.anyio
async def test_billing_flow(
    client: AsyncClient,
    fastapi_app: FastAPI,
    dbsession: AsyncSession,
    bootstrap_secret: str,
) -> None:
    organization_id, headers = await _bootstrap_and_login(client, fastapi_app, bootstrap_secret)

    plans_url = fastapi_app.url_path_for("list_billing_plans")
    response = await client.get(plans_url, headers=headers)
    assert response.status_code == 200
    assert response.json()["items"] == []

    create_plan_url = fastapi_app.url_path_for("create_billing_plan")
    plan_payload = {
        "plan_name": "Gold",
        "plan_description": "Gold tier",
        "price": "49.99",
        "billing_cycle": BillingCycleEnum.MONTHLY.value,
        "max_users": 100,
        "max_storage": 500,
        "support_level": SupportLevelEnum.PREMIUM.value,
    }
    create_plan_response = await client.post(create_plan_url, json=plan_payload, headers=headers)
    assert create_plan_response.status_code == 201
    plan_data = create_plan_response.json()
    plan_id = plan_data["plan_id"]

    list_response = await client.get(plans_url, headers=headers)
    assert list_response.status_code == 200
    assert len(list_response.json()["items"]) == 1

    update_plan_url = fastapi_app.url_path_for("update_billing_plan", plan_id=str(plan_id))
    update_response = await client.patch(
        update_plan_url,
        json={"plan_description": "Gold tier updated"},
        headers=headers,
    )
    assert update_response.status_code == 200
    assert update_response.json()["plan_description"] == "Gold tier updated"

    create_subscription_url = fastapi_app.url_path_for(
        "create_subscription",
        organization_id=str(organization_id),
    )
    subscription_payload = {
        "plan_id": plan_id,
        "plan_type": PlanTypeEnum.PREMIUM.value,
        "payment_status": PaymentStatusEnum.PAID.value,
        "subscription_start": date.today().isoformat(),
        "history_status": "active",
    }
    create_subscription_response = await client.post(
        create_subscription_url,
        json=subscription_payload,
        headers=headers,
    )
    assert create_subscription_response.status_code == 201
    subscription_id = create_subscription_response.json()["subscription_id"]
    assert subscription_id is not None

    get_subscription_url = fastapi_app.url_path_for(
        "get_subscription",
        organization_id=str(organization_id),
    )
    get_subscription_response = await client.get(get_subscription_url, headers=headers)
    assert get_subscription_response.status_code == 200

    update_subscription_url = fastapi_app.url_path_for(
        "update_subscription",
        organization_id=str(organization_id),
    )
    update_subscription_response = await client.patch(
        update_subscription_url,
        json={
            "payment_status": PaymentStatusEnum.OVERDUE.value,
            "history_status": SubscriptionHistoryStatusEnum.CANCELLED.value,
            "plan_id": plan_id,
        },
        headers=headers,
    )
    assert update_subscription_response.status_code == 200
    assert update_subscription_response.json()["payment_status"] == PaymentStatusEnum.OVERDUE.value

    invoice = Invoice(
        school_id=organization_id,
        plan_id=plan_id,
        amount=Decimal("49.99"),
        billing_cycle=BillingCycleEnum.MONTHLY,
        invoice_date=datetime.utcnow(),
        due_date=datetime.utcnow(),
        status=InvoiceStatusEnum.PENDING,
        payment_method=PaymentMethodEnum.CREDIT_CARD,
    )
    dbsession.add(invoice)
    await dbsession.flush()

    list_invoices_url = fastapi_app.url_path_for(
        "list_invoices",
        organization_id=str(organization_id),
    )
    list_invoices_response = await client.get(list_invoices_url, headers=headers)
    assert list_invoices_response.status_code == 200
    invoices = list_invoices_response.json()["items"]
    assert len(invoices) == 1
    invoice_id = invoices[0]["invoice_id"]

    get_invoice_url = fastapi_app.url_path_for("get_invoice", invoice_id=str(invoice_id))
    get_invoice_response = await client.get(get_invoice_url, headers=headers)
    assert get_invoice_response.status_code == 200

    update_invoice_url = fastapi_app.url_path_for("update_invoice", invoice_id=str(invoice_id))
    update_invoice_response = await client.patch(
        update_invoice_url,
        json={
            "status": InvoiceStatusEnum.PAID.value,
            "payment_date": datetime.utcnow().isoformat(),
        },
        headers=headers,
    )
    assert update_invoice_response.status_code == 200
    assert update_invoice_response.json()["status"] == InvoiceStatusEnum.PAID.value
