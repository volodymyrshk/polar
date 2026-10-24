import pytest

from polar.enums import TaxBehavior
from polar.models import Customer, Product
from polar.models.order import OrderStatus
from tests.fixtures.database import SaveFixture
from tests.fixtures.random_objects import create_order


@pytest.mark.parametrize(
    (
        "tax_behavior",
        "subtotal_amount",
        "tax_amount",
        "applied_balance_amount",
        "total_refund_amount",
        "expected_refund_amount",
        "expected_refund_tax_amount",
    ),
    [
        pytest.param(
            TaxBehavior.exclusive,
            1000,
            250,
            1000,
            1250,
            1000,
            250,
            id="exclusive refund subtotal amount with tax",
        ),
        pytest.param(
            TaxBehavior.exclusive,
            1000,
            250,
            1000,
            2250,
            2000,
            250,
            id="exclusive refund subtotal + balance with tax",
        ),
        pytest.param(
            TaxBehavior.exclusive,
            1000,
            250,
            -500,
            750,
            500,
            250,
            id="exclusive full refund with negative balance",
        ),
        pytest.param(
            TaxBehavior.exclusive,
            1000,
            250,
            0,
            1300,
            1050,
            250,
            id="exclusive refund exceeding original amount",
        ),
        pytest.param(
            TaxBehavior.inclusive,
            1000,
            200,
            0,
            1000,
            800,
            200,
            id="inclusive full amount",
        ),
        pytest.param(
            TaxBehavior.inclusive,
            1000,
            200,
            0,
            500,
            400,
            100,
            id="inclusive half amount",
        ),
    ],
)
@pytest.mark.anyio
async def test_calculate_refunded_tax_from_total(
    tax_behavior: TaxBehavior,
    subtotal_amount: int,
    tax_amount: int,
    applied_balance_amount: int,
    total_refund_amount: int,
    expected_refund_amount: int,
    expected_refund_tax_amount: int,
    save_fixture: SaveFixture,
    product: Product,
    customer: Customer,
) -> None:
    order = await create_order(
        save_fixture,
        product=product,
        customer=customer,
        subtotal_amount=subtotal_amount,
        tax_amount=tax_amount,
        applied_balance_amount=applied_balance_amount,
        tax_behavior=tax_behavior,
    )
    assert order.refunded_amount == 0
    assert order.refunded_tax_amount == 0
    assert order.net_amount == subtotal_amount - (
        tax_amount if tax_behavior == TaxBehavior.inclusive else 0
    )

    refund_amount, refund_tax_amount = order.calculate_refunded_tax_from_total(
        total_refund_amount
    )

    assert refund_amount == expected_refund_amount
    assert refund_tax_amount == expected_refund_tax_amount


@pytest.mark.parametrize(
    (
        "tax_behavior",
        "subtotal_amount",
        "tax_amount",
        "applied_balance_amount",
        "refund_amount",
        "expected_refund_tax_amount",
    ),
    [
        pytest.param(
            TaxBehavior.exclusive, 1000, 250, 0, 1000, 250, id="exclusive full amount"
        ),
        pytest.param(
            TaxBehavior.exclusive,
            1000,
            250,
            1000,
            2000,
            250,
            id="exclusive full amount with applied balance",
        ),
        pytest.param(
            TaxBehavior.exclusive,
            1000,
            250,
            1000,
            500,
            125,
            id="exclusive sub amount with applied balance",
        ),
        pytest.param(
            TaxBehavior.exclusive,
            1000,
            250,
            1000,
            1500,
            250,
            id="exclusive sub amount exceeding net with applied balance is capped",
        ),
        pytest.param(
            TaxBehavior.exclusive,
            1000,
            0,
            1000,
            1500,
            0,
            id="exclusive untaxed with applied balance",
        ),
        pytest.param(
            TaxBehavior.inclusive, 1000, 200, 0, 800, 200, id="inclusive full amount"
        ),
        pytest.param(
            TaxBehavior.inclusive, 1000, 200, 0, 400, 100, id="inclusive half amount"
        ),
    ],
)
@pytest.mark.anyio
async def test_calculate_refunded_tax_from_subtotal(
    tax_behavior: TaxBehavior,
    subtotal_amount: int,
    tax_amount: int,
    applied_balance_amount: int,
    refund_amount: int,
    expected_refund_tax_amount: int,
    save_fixture: SaveFixture,
    product: Product,
    customer: Customer,
) -> None:
    order = await create_order(
        save_fixture,
        product=product,
        customer=customer,
        subtotal_amount=subtotal_amount,
        tax_amount=tax_amount,
        applied_balance_amount=applied_balance_amount,
        tax_behavior=tax_behavior,
    )
    assert order.refunded_amount == 0
    assert order.refunded_tax_amount == 0

    refund_tax_amount = order.calculate_refunded_tax_from_subtotal(refund_amount)

    assert refund_tax_amount == expected_refund_tax_amount


@pytest.mark.anyio
class TestPartialRefunds:
    @pytest.mark.parametrize(
        ("tax_behavior", "subtotal_amount", "applied_balance_amount"),
        [
            pytest.param(TaxBehavior.exclusive, 52, 0, id="exclusive"),
            pytest.param(TaxBehavior.inclusive, 62, 0, id="inclusive"),
            pytest.param(TaxBehavior.exclusive, 42, 10, id="positive_balance"),
            pytest.param(TaxBehavior.exclusive, 62, -10, id="negative_balance"),
        ],
    )
    @pytest.mark.parametrize(
        "refund_totals",
        [
            pytest.param([32, 9, 8, 3, 6, 3, 1], id="rounded_partials"),
            pytest.param([1] * 62, id="small_partials"),
        ],
    )
    async def test_total_refund_preserves_net_and_tax_balances(
        self,
        tax_behavior: TaxBehavior,
        subtotal_amount: int,
        applied_balance_amount: int,
        refund_totals: list[int],
        save_fixture: SaveFixture,
        product: Product,
        customer: Customer,
    ) -> None:
        order = await create_order(
            save_fixture,
            product=product,
            customer=customer,
            subtotal_amount=subtotal_amount,
            tax_amount=10,
            applied_balance_amount=applied_balance_amount,
            tax_behavior=tax_behavior,
        )
        total_refunded = 0
        for total in refund_totals:
            amount, tax = order.calculate_refunded_tax_from_total(total)
            assert amount + tax == total
            order.update_refunds(amount, tax)
            total_refunded += total

            assert 0 <= order.refunded_amount <= 52
            assert 0 <= order.refunded_tax_amount <= 10
            assert order.refunded_amount + order.refunded_tax_amount == total_refunded
            assert order.remaining_balance == 62 - total_refunded
            assert order.status == (
                OrderStatus.refunded
                if total_refunded == 62
                else OrderStatus.partially_refunded
            )

        assert order.refunded_amount == 52
        assert order.refunded_tax_amount == 10


@pytest.mark.anyio
class TestUpdateRefunds:
    async def test_tax_only_refund_and_reversal(
        self,
        save_fixture: SaveFixture,
        product: Product,
        customer: Customer,
    ) -> None:
        order = await create_order(
            save_fixture,
            product=product,
            customer=customer,
            subtotal_amount=10,
            tax_amount=10,
            applied_balance_amount=-10,
        )
        for amount, expected_status in [
            (5, OrderStatus.partially_refunded),
            (5, OrderStatus.refunded),
            (-5, OrderStatus.partially_refunded),
            (-5, OrderStatus.paid),
        ]:
            order.update_refunds(0, amount)
            assert order.status == expected_status
