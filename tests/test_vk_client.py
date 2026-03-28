from datetime import date
from unittest.mock import MagicMock

import pytest
from vk_api.exceptions import ApiError

from vk_client import VKClient, parse_age_from_bdate


def test_vk_client_init_error_on_missing_env(monkeypatch):
    # Block dotenv from loading .env file
    monkeypatch.setattr("vk_client.load_dotenv", lambda: None)
    # Ensure environment variables are not set
    monkeypatch.delenv("VK_USER_TOKEN", raising=False)
    monkeypatch.delenv("VK_GROUP_TOKEN", raising=False)

    with pytest.raises(ValueError) as excinfo:
        VKClient()
    assert "Missing required environment variables" in str(excinfo.value)


def test_vk_client_has_required_methods():
    client = VKClient(user_token="user", group_token="group")
    assert hasattr(client, "search_users")
    assert hasattr(client, "get_user_info")


# ---------------------------------------------------------------------------
# parse_age_from_bdate tests
# ---------------------------------------------------------------------------


def test_parse_age_full_bdate():
    bdate = "15.06.1995"
    result = parse_age_from_bdate(bdate)
    today = date.today()
    expected = today.year - 1995 - ((today.month, today.day) < (6, 15))
    assert result == expected


def test_parse_age_partial_bdate():
    result = parse_age_from_bdate("15.06")
    assert result is None


def test_parse_age_none_input():
    result = parse_age_from_bdate(None)
    assert result is None


def test_parse_age_invalid_string():
    result = parse_age_from_bdate("abc")
    assert result is None


# ---------------------------------------------------------------------------
# get_photos tests
# ---------------------------------------------------------------------------


def test_get_photos_sorted_by_likes():
    client = VKClient(user_token="u", group_token="g")
    client.user_api = MagicMock()
    client.user_api.photos.get.return_value = {
        "items": [
            {"id": 1, "owner_id": 10, "likes": {"count": 5}},
            {"id": 2, "owner_id": 10, "likes": {"count": 20}},
            {"id": 3, "owner_id": 10, "likes": {"count": 10}},
        ]
    }
    result = client.get_photos(10)
    assert result[0]["id"] == 2  # 20 likes
    assert result[1]["id"] == 3  # 10 likes
    assert result[2]["id"] == 1  # 5 likes
    client.user_api.photos.get.assert_called_once_with(
        owner_id=10,
        album_id="profile",
        extended=1,
        count=50,
    )


def test_get_photos_api_error():
    client = VKClient(user_token="u", group_token="g")
    client.user_api = MagicMock()
    error_dict = {"error_code": 30, "error_msg": "This profile is private"}
    raw = {"error": error_dict}
    client.user_api.photos.get.side_effect = ApiError(
        vk=MagicMock(),
        method="photos.get",
        values={},
        raw=raw,
        error=error_dict,
    )
    result = client.get_photos(10)
    assert result == []


def test_get_photos_empty():
    client = VKClient(user_token="u", group_token="g")
    client.user_api = MagicMock()
    client.user_api.photos.get.return_value = {"items": []}
    result = client.get_photos(10)
    assert result == []


# ---------------------------------------------------------------------------
# find_candidates tests
# ---------------------------------------------------------------------------


def test_find_candidates_all_params():
    client = VKClient(user_token="u", group_token="g")
    client.user_api = MagicMock()
    client.user_api.users.search.return_value = {
        "count": 50,
        "items": [{"id": 1}],
    }
    result = client.find_candidates(
        sex=1, city_id=2, age_from=20, age_to=30, count=50
    )
    client.user_api.users.search.assert_called_once_with(
        sex=1,
        city=2,
        age_from=20,
        age_to=30,
        count=50,
        offset=0,
        has_photo=1,
        fields="bdate,city,sex",
    )
    assert result == [{"id": 1}]


def test_find_candidates_minimal():
    client = VKClient(user_token="u", group_token="g")
    client.user_api = MagicMock()
    client.user_api.users.search.return_value = {"count": 0, "items": []}
    client.find_candidates()
    call_kwargs = client.user_api.users.search.call_args[1]
    assert "sex" not in call_kwargs
    assert "city" not in call_kwargs
    assert "age_from" not in call_kwargs
    assert "age_to" not in call_kwargs
    assert call_kwargs.get("has_photo") == 1
