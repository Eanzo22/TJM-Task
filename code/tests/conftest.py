import json
from pathlib import Path

import pytest

from fakturama_cash.models import OrderInput


@pytest.fixture
def payload():
    return json.loads((Path(__file__).parent / "fixtures/synthetic_order.json").read_text())


@pytest.fixture
def order(payload):
    return OrderInput.model_validate(payload).reconcile()
