from pydantic import Field

from . import schemas


class RefundCreate(schemas.RefundCreate):
    amount: int = Field(description="Amount to refund in cents. Minimum is 1.", gt=0)
