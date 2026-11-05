"""Phone numbers typed or pasted with Bengali digits, invisible marks or separators are made
plain before the check, so a real number is not refused; other characters still fail."""

import pytest

from app.auth.inputs import check_phone, normalize_phone
from app.errors import ApiError
from app.routers.pay import BD_MOBILE


@pytest.mark.parametrize(
    "typed",
    [
        "01721307072",
        "‪01721307072‬",  # direction marks from copy and paste
        "0172​1307072",  # zero-width space
        "⁨017 2130 7072⁩",
        "০১৭২১৩০৭০৭২",  # Bengali digits
        "0172-130-7072",
        "(+88) 01721307072",
        "+880 1721.307072",
        " 01721307072 ",  # non-breaking spaces
    ],
)
def test_real_numbers_are_accepted(typed: str) -> None:
    phone = normalize_phone(typed)
    assert BD_MOBILE.fullmatch(phone)
    assert check_phone(typed) == phone


@pytest.mark.parametrize("typed", ["0172130707", "01221307072", "0172130707a", "017213O7072", "phone"])
def test_wrong_numbers_still_fail(typed: str) -> None:
    assert not BD_MOBILE.fullmatch(normalize_phone(typed))
    with pytest.raises(ApiError):
        check_phone(typed)
