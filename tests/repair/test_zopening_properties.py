from itertools import count
from decimal import Decimal
import uuid

from hypothesis import (
    given,
    settings as hypothesis_settings,
    strategies as st,
    HealthCheck,
)
import requests
from sympy import Rational

from conftest import BASE
from app.models.models import JournalLine

years = count(2040)


@hypothesis_settings(
    max_examples=8,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
@given(
    assets=st.decimals(
        min_value=Decimal("0.01"), max_value=Decimal("100000"), places=2
    ),
    liabilities=st.decimals(
        min_value=Decimal("0.01"), max_value=Decimal("100000"), places=2
    ),
)
def test_opening_equity_across_random_balances(headers, db, assets, liabilities):
    year = next(years)
    response = requests.post(
        BASE + "/opening-balances/",
        headers=headers["super_admin"],
        timeout=15,
        json={
            "submission_id": uuid.uuid4().hex,
            "opening_date": f"{year}-04-01",
            "financial_year": f"{year}-{str(year + 1)[-2:]}",
            "other_assets": str(assets),
            "other_liabilities": str(liabilities),
        },
    )
    assert response.status_code == 201, response.text
    db.rollback()
    lines = (
        db.query(JournalLine)
        .filter_by(journal_entry_id=response.json()["journal_entry_id"])
        .all()
    )
    debit = sum(
        (
            Rational(str(line.amount))
            for line in lines
            if line.transaction_type == "debit"
        ),
        Rational(0),
    )
    credit = sum(
        (
            Rational(str(line.amount))
            for line in lines
            if line.transaction_type == "credit"
        ),
        Rational(0),
    )
    assert debit == credit == max(Rational(str(assets)), Rational(str(liabilities)))
