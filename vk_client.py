import os
from datetime import date

import vk_api
from dotenv import load_dotenv
from vk_api.exceptions import ApiError


def parse_age_from_bdate(bdate):
    """Return integer age from VK bdate string (DD.MM.YYYY), or None if partial/absent/invalid."""
    if not bdate:
        return None
    parts = bdate.split(".")
    if len(parts) != 3:
        return None
    try:
        day, month, year = int(parts[0]), int(parts[1]), int(parts[2])
        born = date(year, month, day)
        today = date.today()
        return (
            today.year
            - born.year
            - ((today.month, today.day) < (born.month, born.day))
        )
    except (ValueError, TypeError):
        return None


class VKClient:
    """
    VK API client that handles both User and Group tokens.
    Uses User token for searching and Group token for messaging.
    """

    def __init__(self, user_token=None, group_token=None):
        # Explicitly load .env if it exists
        load_dotenv()

        self.user_token = user_token or os.getenv("VK_USER_TOKEN")
        self.group_token = group_token or os.getenv("VK_GROUP_TOKEN")

        if not self.user_token or not self.group_token:
            raise ValueError(
                "Missing required environment variables: VK_USER_TOKEN and/or VK_GROUP_TOKEN"
            )

        # Initialize sessions
        self.user_session = vk_api.VkApi(token=self.user_token)
        self.group_session = vk_api.VkApi(token=self.group_token)

        # Get API objects
        self.user_api = self.user_session.get_api()
        self.group_api = self.group_session.get_api()

    def search_users(self, **params):
        """
        Wraps users.search API method.
        Requires User token.
        """
        return self.user_api.users.search(**params)

    def get_user_info(self, user_id):
        """
        Wraps users.get API method.
        Requires User token.
        """
        return self.user_api.users.get(
            user_ids=user_id, fields="bdate,city,sex"
        )

    def get_photos(self, owner_id):
        """Return profile photos sorted by likes descending. Empty list if inaccessible."""
        try:
            response = self.user_api.photos.get(
                owner_id=owner_id,
                album_id="profile",
                extended=1,
                count=50,
            )
            items = response.get("items", [])
            return sorted(
                items,
                key=lambda p: p.get("likes", {}).get("count", 0),
                reverse=True,
            )
        except ApiError:
            return []

    def find_candidates(
        self,
        sex=None,
        city_id=None,
        age_from=None,
        age_to=None,
        count=50,
        offset=0,
    ):
        """Search users with given filters. Returns items list."""
        params = {
            "count": count,
            "offset": offset,
            "has_photo": 1,
            "fields": "bdate,city,sex",
        }
        if sex is not None:
            params["sex"] = sex
        if city_id is not None:
            params["city"] = city_id
        if age_from is not None:
            params["age_from"] = age_from
        if age_to is not None:
            params["age_to"] = age_to
        result = self.user_api.users.search(**params)
        return result.get("items", [])
