import json
import os
import shutil
import tempfile
import unittest
from unittest.mock import MagicMock, patch

import main
import storage
from main import (
    NEXT_KEYWORDS,
    VKinderBot,
    format_candidate_text,
    format_photo_attachment,
    get_keyboard,
    normalize_text,
)


class TestVKinderBot(unittest.TestCase):
    @patch("main.VkBotLongPoll")
    def setUp(self, mock_longpoll):
        self.mock_vk_client = MagicMock()
        # Mock group_api.groups.getById to return a list with a dict containing 'id'
        self.mock_vk_client.group_api.groups.getById.return_value = [
            {"id": 123456}
        ]
        self.bot = VKinderBot(self.mock_vk_client)

    def test_initialization(self):
        self.assertEqual(self.bot.vk_client, self.mock_vk_client)
        self.assertEqual(self.bot.group_id, 123456)

    @patch("main.VkBotLongPoll")
    def test_listen_loop_starts(self, mock_longpoll):
        # We need to re-patch here because the setUp also patches it,
        # but the bot already has self.longpoll set up in __init__
        mock_instance = self.bot.longpoll
        mock_instance.listen.return_value = []

        self.bot.listen()

        mock_instance.listen.assert_called_once()

    def test_send_message(self):
        self.bot.send_message(123, "Hello")
        self.mock_vk_client.group_api.messages.send.assert_called_once()
        args, kwargs = self.mock_vk_client.group_api.messages.send.call_args
        self.assertEqual(kwargs["user_id"], 123)
        self.assertEqual(kwargs["message"], "Hello")
        self.assertIn("random_id", kwargs)

    def test_handle_greeting(self):
        # Mock event object
        event = MagicMock()
        event.object.message = {"text": "привет", "from_id": 123}

        # Mock get_user_info
        self.mock_vk_client.get_user_info.return_value = [
            {"first_name": "Иван"}
        ]

        with patch.object(self.bot, "send_message") as mock_send:
            self.bot.handle_message(event)
            mock_send.assert_called_once()
            args, kwargs = mock_send.call_args
            self.assertEqual(args[0], 123)
            self.assertIn("Привет, Иван", args[1])
            self.assertIsNotNone(
                kwargs.get("keyboard"), "Greeting must include keyboard"
            )

    def test_handle_help(self):
        # Mock event object
        event = MagicMock()
        event.object.message = {"text": "/help", "from_id": 123}

        with patch.object(self.bot, "send_message") as mock_send:
            self.bot.handle_message(event)
            mock_send.assert_called_once()
            args, kwargs = mock_send.call_args
            self.assertIn("Инструкция", args[1])

    def test_handle_test_search(self):
        # Mock event object
        event = MagicMock()
        event.object.message = {"text": "/test_search", "from_id": 123}

        # Mock search_users
        self.mock_vk_client.search_users.return_value = {
            "count": 1234567,
            "items": [],
        }

        with patch.object(self.bot, "send_message") as mock_send:
            self.bot.handle_message(event)
            mock_send.assert_called_once_with(
                123, "User search API: OK (1234567 результатов)"
            )

    def test_handle_test_search_error(self):
        # Mock event object
        event = MagicMock()
        event.object.message = {"text": "/test_search", "from_id": 123}

        # Mock search_users to raise an exception
        self.mock_vk_client.search_users.side_effect = Exception("API Error")

        with patch.object(self.bot, "send_message") as mock_send:
            self.bot.handle_message(event)
            mock_send.assert_called_once_with(
                123, "User search API: ERROR (API Error)"
            )


if __name__ == "__main__":
    unittest.main()


# ── Task 2 tests: send_message attachment, _handle_next, command routing ─────


class TestSendMessageAttachment(unittest.TestCase):
    @patch("main.VkBotLongPoll")
    def setUp(self, mock_longpoll):
        self.mock_vk_client = MagicMock()
        self.mock_vk_client.group_api.groups.getById.return_value = [
            {"id": 123456}
        ]
        self.bot = VKinderBot(self.mock_vk_client)

    def test_send_message_with_attachment(self):
        self.bot.send_message(123, "hello", attachment="photo10_100")
        _, kwargs = self.mock_vk_client.group_api.messages.send.call_args
        self.assertEqual(kwargs.get("attachment"), "photo10_100")

    def test_send_message_without_attachment(self):
        self.bot.send_message(123, "hello")
        self.mock_vk_client.group_api.messages.send.assert_called_once()
        _, kwargs = self.mock_vk_client.group_api.messages.send.call_args
        self.assertNotIn("attachment", kwargs)


class TestHandleNext(unittest.TestCase):
    @patch("main.VkBotLongPoll")
    def setUp(self, mock_longpoll):
        self.mock_vk_client = MagicMock()
        self.mock_vk_client.group_api.groups.getById.return_value = [
            {"id": 123456}
        ]
        self.bot = VKinderBot(self.mock_vk_client)

    def _make_event(self, text, user_id=123):
        event = MagicMock()
        event.object.message = {"text": text, "from_id": user_id}
        return event

    def test_handle_next_first_call(self):
        """First 'next': fetches user info, searches candidates, retrieves photos, sends card."""
        self.mock_vk_client.get_user_info.return_value = [
            {
                "id": 123,
                "first_name": "Тест",
                "last_name": "Юзер",
                "sex": 2,
                "bdate": "01.01.1995",
                "city": {"id": 1, "title": "Москва"},
            }
        ]
        self.mock_vk_client.find_candidates.return_value = [
            {
                "id": 456,
                "first_name": "Мария",
                "last_name": "Иванова",
                "bdate": "15.06.1998",
                "city": {"id": 1, "title": "Москва"},
            }
        ]
        self.mock_vk_client.get_photos.return_value = [
            {"owner_id": 456, "id": 100, "likes": {"count": 10}},
            {"owner_id": 456, "id": 200, "likes": {"count": 5}},
        ]
        with patch.object(self.bot, "send_message") as mock_send:
            self.bot.handle_message(self._make_event("next"))
            # find_candidates called once with sex=1 (opposite of female=2), city_id=1
            self.mock_vk_client.find_candidates.assert_called_once()
            call_kwargs = self.mock_vk_client.find_candidates.call_args[1]
            self.assertEqual(call_kwargs.get("sex"), 1)
            self.assertEqual(call_kwargs.get("city_id"), 1)
            # get_photos called with candidate id 456
            self.mock_vk_client.get_photos.assert_called_with(456)
            # send_message called with card text and attachment
            mock_send.assert_called_once()
            args, kwargs = mock_send.call_args
            self.assertIn("Мария Иванова", args[1])
            self.assertIn("https://vk.com/id456", args[1])
            self.assertIn("photo456_100", kwargs.get("attachment", ""))

    def test_handle_next_cached(self):
        """Second 'next' uses cached candidates without calling find_candidates."""
        candidate1 = {"id": 111, "first_name": "А", "last_name": "Б"}
        candidate2 = {"id": 222, "first_name": "В", "last_name": "Г"}
        self.bot.user_state = {
            123: {
                "candidates": [candidate1, candidate2],
                "index": 0,
                "city_hint_sent": False,
                "search_params": {
                    "sex": 1
                },  # no city_id -> cached_city_id=None
                "current_candidate": None,
            }
        }
        # Profile also has no city -> current_city_id=None -> matches -> cache preserved
        self.mock_vk_client.get_user_info.return_value = [
            {"id": 123, "sex": 2}
        ]
        self.mock_vk_client.get_photos.return_value = [
            {"owner_id": 111, "id": 10, "likes": {"count": 1}},
        ]
        with patch.object(self.bot, "send_message"):
            self.bot.handle_message(self._make_event("next"))
        self.mock_vk_client.find_candidates.assert_not_called()
        self.mock_vk_client.get_photos.assert_called_with(111)
        self.assertEqual(self.bot.user_state[123]["index"], 1)

    def test_handle_next_exhausted(self):
        """When candidates exhausted, sends info message then fetches new batch."""
        candidate1 = {"id": 777, "first_name": "Х", "last_name": "Й"}
        self.bot.user_state = {
            123: {
                "candidates": [candidate1],
                "index": 1,  # already past the only candidate
                "city_hint_sent": True,
                "search_params": {"sex": 2},
                "current_candidate": None,
            }
        }
        self.mock_vk_client.get_user_info.return_value = [
            {
                "id": 123,
                "sex": 1,
                "city": {"id": 2, "title": "СПб"},
            }
        ]
        self.mock_vk_client.find_candidates.return_value = [
            {
                "id": 888,
                "first_name": "Новый",
                "last_name": "Кандидат",
            }
        ]
        self.mock_vk_client.get_photos.return_value = [
            {"owner_id": 888, "id": 50, "likes": {"count": 3}},
        ]
        with patch.object(self.bot, "send_message") as mock_send:
            self.bot.handle_message(self._make_event("next"))
        calls = [str(c) for c in mock_send.call_args_list]
        exhausted_sent = any("Кандидаты закончились" in c for c in calls)
        self.assertTrue(
            exhausted_sent, "Expected 'Кандидаты закончились' message"
        )
        self.mock_vk_client.find_candidates.assert_called_once()

    def test_handle_next_skip_no_photos(self):
        """Candidates with 0 photos are silently skipped; next candidate shown."""
        cand_no_photos = {
            "id": 1,
            "first_name": "Пусто",
            "last_name": "Пустой",
        }
        cand_with_photos = {
            "id": 2,
            "first_name": "Реальный",
            "last_name": "Кандидат",
        }
        self.bot.user_state = {
            123: {
                "candidates": [cand_no_photos, cand_with_photos],
                "index": 0,
                "city_hint_sent": True,
                "search_params": {
                    "sex": 1
                },  # no city_id -> cached_city_id=None
                "current_candidate": None,
            }
        }
        # Profile also has no city -> current_city_id=None -> matches -> cache preserved
        self.mock_vk_client.get_user_info.return_value = [
            {"id": 123, "sex": 2}
        ]

        def get_photos_side_effect(owner_id):
            if owner_id == 1:
                return []
            return [{"owner_id": 2, "id": 99, "likes": {"count": 5}}]

        self.mock_vk_client.get_photos.side_effect = get_photos_side_effect
        with patch.object(self.bot, "send_message") as mock_send:
            self.bot.handle_message(self._make_event("next"))
        args, _ = mock_send.call_args
        self.assertIn("Реальный Кандидат", args[1])

    def test_handle_next_russian_alias(self):
        """'дальше' triggers same _handle_next handler as 'next'."""
        self.mock_vk_client.get_user_info.return_value = [
            {
                "id": 123,
                "sex": 2,
                "city": {"id": 1, "title": "Казань"},
            }
        ]
        self.mock_vk_client.find_candidates.return_value = [
            {
                "id": 500,
                "first_name": "Ян",
                "last_name": "Ко",
            }
        ]
        self.mock_vk_client.get_photos.return_value = [
            {"owner_id": 500, "id": 1, "likes": {"count": 1}},
        ]
        with patch.object(self.bot, "send_message"):
            self.bot.handle_message(self._make_event("дальше"))
        self.mock_vk_client.find_candidates.assert_called_once()

    def test_handle_next_city_hint(self):
        """User with no city gets one-time hint and search without city_id."""
        self.mock_vk_client.get_user_info.return_value = [
            {
                "id": 123,
                "sex": 2,
                "bdate": "01.01.1990",
                # No 'city' key
            }
        ]
        self.mock_vk_client.find_candidates.return_value = [
            {
                "id": 600,
                "first_name": "Дима",
                "last_name": "Громов",
            }
        ]
        self.mock_vk_client.get_photos.return_value = [
            {"owner_id": 600, "id": 1, "likes": {"count": 1}},
        ]
        with patch.object(self.bot, "send_message") as mock_send:
            self.bot.handle_message(self._make_event("next"))
        calls = [str(c) for c in mock_send.call_args_list]
        hint_sent = any("Укажи город в профиле" in c for c in calls)
        self.assertTrue(hint_sent, "Expected city hint message")
        # find_candidates should NOT have city_id param
        call_kwargs = self.mock_vk_client.find_candidates.call_args[1]
        self.assertNotIn("city_id", call_kwargs)

    def test_handle_next_no_city_hint_repeat(self):
        """City hint is NOT sent on subsequent 'next' calls."""
        self.bot.user_state = {
            123: {
                "candidates": [],
                "index": 0,
                "city_hint_sent": True,  # already sent
                "search_params": None,
                "current_candidate": None,
            }
        }
        self.mock_vk_client.get_user_info.return_value = [
            {
                "id": 123,
                "sex": 1,
                # No city
            }
        ]
        self.mock_vk_client.find_candidates.return_value = [
            {
                "id": 700,
                "first_name": "Ел",
                "last_name": "На",
            }
        ]
        self.mock_vk_client.get_photos.return_value = [
            {"owner_id": 700, "id": 1, "likes": {"count": 1}},
        ]
        with patch.object(self.bot, "send_message") as mock_send:
            self.bot.handle_message(self._make_event("next"))
        calls = [str(c) for c in mock_send.call_args_list]
        hint_sent = any("Укажи город в профиле" in c for c in calls)
        self.assertFalse(
            hint_sent, "City hint should NOT appear on second call"
        )

    def test_handle_next_city_change_mid_batch(self):
        """Mid-batch city removal invalidates cache and triggers fresh search without city_id."""
        candidate1 = {"id": 111, "first_name": "А", "last_name": "Б"}
        candidate2 = {"id": 222, "first_name": "В", "last_name": "Г"}
        # Batch was fetched with city_id=1
        self.bot.user_state = {
            123: {
                "candidates": [candidate1, candidate2],
                "index": 0,
                "city_hint_sent": False,
                "search_params": {"sex": 2, "city_id": 1},
                "current_candidate": None,
            }
        }
        # User has now removed their city from profile
        self.mock_vk_client.get_user_info.return_value = [
            {"id": 123, "sex": 1}
        ]  # no 'city'
        self.mock_vk_client.find_candidates.return_value = [
            {
                "id": 999,
                "first_name": "Новый",
                "last_name": "Кандидат",
            }
        ]
        self.mock_vk_client.get_photos.return_value = [
            {"owner_id": 999, "id": 1, "likes": {"count": 1}},
        ]
        with patch.object(self.bot, "send_message"):
            self.bot.handle_message(self._make_event("next"))
        # Batch must be invalidated -> find_candidates called
        self.mock_vk_client.find_candidates.assert_called_once()
        # New search must NOT include city_id (city was removed)
        call_kwargs = self.mock_vk_client.find_candidates.call_args[1]
        self.assertNotIn("city_id", call_kwargs)

    def test_handle_next_city_unchanged_uses_cache(self):
        """When city_id is unchanged mid-batch, cached candidates are served without re-fetching."""
        candidate1 = {"id": 111, "first_name": "А", "last_name": "Б"}
        candidate2 = {"id": 222, "first_name": "В", "last_name": "Г"}
        self.bot.user_state = {
            123: {
                "candidates": [candidate1, candidate2],
                "index": 0,
                "city_hint_sent": False,
                "search_params": {"sex": 2, "city_id": 1},
                "current_candidate": None,
            }
        }
        # City is still the same (city_id=1)
        self.mock_vk_client.get_user_info.return_value = [
            {"id": 123, "sex": 1, "city": {"id": 1, "title": "Москва"}}
        ]
        self.mock_vk_client.get_photos.return_value = [
            {"owner_id": 111, "id": 10, "likes": {"count": 1}},
        ]
        with patch.object(self.bot, "send_message"):
            self.bot.handle_message(self._make_event("next"))
        # Cache still valid -> find_candidates NOT called
        self.mock_vk_client.find_candidates.assert_not_called()

    def test_handle_next_city_change_to_different_city(self):
        """Mid-batch city change to a different city triggers fresh search with new city_id."""
        candidate1 = {"id": 111, "first_name": "А", "last_name": "Б"}
        candidate2 = {"id": 222, "first_name": "В", "last_name": "Г"}
        # Batch was fetched with city_id=1
        self.bot.user_state = {
            123: {
                "candidates": [candidate1, candidate2],
                "index": 0,
                "city_hint_sent": False,
                "search_params": {"sex": 2, "city_id": 1},
                "current_candidate": None,
            }
        }
        # User now has city_id=2
        self.mock_vk_client.get_user_info.return_value = [
            {"id": 123, "sex": 1, "city": {"id": 2, "title": "СПб"}}
        ]
        self.mock_vk_client.find_candidates.return_value = [
            {
                "id": 888,
                "first_name": "Петр",
                "last_name": "Спб",
            }
        ]
        self.mock_vk_client.get_photos.return_value = [
            {"owner_id": 888, "id": 1, "likes": {"count": 1}},
        ]
        with patch.object(self.bot, "send_message"):
            self.bot.handle_message(self._make_event("next"))
        # Batch invalidated -> find_candidates called with new city_id=2
        self.mock_vk_client.find_candidates.assert_called_once()
        call_kwargs = self.mock_vk_client.find_candidates.call_args[1]
        self.assertEqual(call_kwargs.get("city_id"), 2)


# ── Task 1 tests: format_candidate_text and format_photo_attachment ──────────


class TestFormatCandidateText(unittest.TestCase):

    def test_format_candidate_text_full(self):
        candidate = {
            "id": 123,
            "first_name": "Мария",
            "last_name": "Петрова",
            "bdate": "15.06.1995",
            "city": {"id": 1, "title": "Москва"},
        }
        result = format_candidate_text(candidate)
        self.assertIn("Мария Петрова,", result)
        self.assertIn("Москва", result)
        self.assertIn("https://vk.com/id123", result)
        # Age should be a valid integer, not the em-dash fallback
        lines = result.split("\n")
        parts = lines[0].split(", ")
        self.assertTrue(
            parts[1].strip().isdigit(),
            f"Expected digit age, got: {parts[1]!r}",
        )

    def test_format_candidate_text_no_age(self):
        candidate = {
            "id": 123,
            "first_name": "Иван",
            "last_name": "Иванов",
            "city": {"id": 1, "title": "СПб"},
        }
        result = format_candidate_text(candidate)
        self.assertIn("\u2014", result)  # em-dash for missing age

    def test_format_candidate_text_no_city(self):
        candidate = {
            "id": 123,
            "first_name": "Иван",
            "last_name": "Иванов",
            "bdate": "01.01.2000",
        }
        result = format_candidate_text(candidate)
        lines = result.split("\n")
        # First line should end with em-dash for missing city
        self.assertIn("\u2014", lines[0])
        self.assertIn("https://vk.com/id", result)


class TestFormatPhotoAttachment(unittest.TestCase):

    def test_format_photo_attachment_three(self):
        photos = [
            {"owner_id": 10, "id": 100},
            {"owner_id": 10, "id": 200},
            {"owner_id": 10, "id": 300},
        ]
        result = format_photo_attachment(photos)
        self.assertEqual(result, "photo10_100,photo10_200,photo10_300")

    def test_format_photo_attachment_one(self):
        photos = [{"owner_id": 10, "id": 100}]
        result = format_photo_attachment(photos)
        self.assertEqual(result, "photo10_100")

    def test_format_photo_attachment_empty(self):
        result = format_photo_attachment([])
        self.assertEqual(result, "")


# ── Task 1 (03-02): keyboard, normalization, new handlers — RED phase ─────────


class TestKeyboard(unittest.TestCase):
    def test_get_keyboard_returns_string(self):
        self.assertIsInstance(get_keyboard(), str)

    def test_get_keyboard_valid_json(self):
        json.loads(get_keyboard())  # must not raise

    def test_keyboard_has_three_rows(self):
        parsed = json.loads(get_keyboard())
        buttons = parsed["buttons"]
        self.assertEqual(len(buttons), 3, "Keyboard must have 3 rows")

    def test_keyboard_not_one_time(self):
        parsed = json.loads(get_keyboard())
        self.assertFalse(parsed["one_time"])

    def test_keyboard_button_labels(self):
        parsed = json.loads(get_keyboard())
        row0 = parsed["buttons"][0]
        row1 = parsed["buttons"][1]
        self.assertEqual(row0[0]["action"]["label"], "👉 Далее")
        self.assertEqual(row1[0]["action"]["label"], "⭐ В избранное")
        self.assertEqual(row1[1]["action"]["label"], "🚫 В чёрный список")

    def test_keyboard_button_colors(self):
        parsed = json.loads(get_keyboard())
        row0 = parsed["buttons"][0]
        row1 = parsed["buttons"][1]
        self.assertEqual(row0[0]["color"], "primary")
        self.assertEqual(row1[0]["color"], "positive")
        self.assertEqual(row1[1]["color"], "negative")

    def test_keyboard_third_row_label(self):
        kb = json.loads(main.KEYBOARD)
        third_row = kb["buttons"][2]
        label = third_row[0]["action"]["label"]
        self.assertIn("Избранное", label)


class TestNormalizeText(unittest.TestCase):
    def test_strips_next_emoji(self):
        self.assertEqual(normalize_text("👉 Далее"), "далее")

    def test_strips_fav_emoji(self):
        self.assertEqual(normalize_text("⭐ В избранное"), "в избранное")

    def test_strips_blacklist_emoji(self):
        self.assertEqual(
            normalize_text("🚫 В чёрный список"), "в чёрный список"
        )

    def test_plain_text_unchanged(self):
        self.assertEqual(normalize_text("next"), "next")

    def test_uppercased(self):
        self.assertEqual(normalize_text("NEXT"), "next")

    def test_strips_punctuation(self):
        self.assertEqual(normalize_text("Привет!"), "привет")


class TestSendMessageKeyboard(unittest.TestCase):
    @patch("main.VkBotLongPoll")
    def setUp(self, mock_longpoll):
        self.mock_vk_client = MagicMock()
        self.mock_vk_client.group_api.groups.getById.return_value = [
            {"id": 123456}
        ]
        self.bot = VKinderBot(self.mock_vk_client)

    def test_keyboard_kwarg_passed(self):
        self.bot.send_message(123, "msg", keyboard="FAKE_JSON")
        _, kwargs = self.mock_vk_client.group_api.messages.send.call_args
        self.assertEqual(kwargs["keyboard"], "FAKE_JSON")

    def test_no_keyboard_kwarg_absent(self):
        self.bot.send_message(123, "msg")
        _, kwargs = self.mock_vk_client.group_api.messages.send.call_args
        self.assertNotIn("keyboard", kwargs)


class TestHandleNextSetsCandidate(unittest.TestCase):
    @patch("main.VkBotLongPoll")
    def setUp(self, mock_longpoll):
        self.mock_vk_client = MagicMock()
        self.mock_vk_client.group_api.groups.getById.return_value = [
            {"id": 123456}
        ]
        self.bot = VKinderBot(self.mock_vk_client)

    def _make_event(self, text, user_id=123):
        event = MagicMock()
        event.object.message = {"text": text, "from_id": user_id}
        return event

    def _setup_candidate_mocks(self):
        self.mock_vk_client.get_user_info.return_value = [
            {
                "id": 123,
                "first_name": "Тест",
                "last_name": "Юзер",
                "sex": 2,
                "bdate": "01.01.1995",
                "city": {"id": 1, "title": "Москва"},
            }
        ]
        self.mock_vk_client.find_candidates.return_value = [
            {
                "id": 456,
                "first_name": "Мария",
                "last_name": "Иванова",
                "bdate": "15.06.1998",
                "city": {"id": 1, "title": "Москва"},
            }
        ]
        self.mock_vk_client.get_photos.return_value = [
            {"owner_id": 456, "id": 100, "likes": {"count": 10}},
            {"owner_id": 456, "id": 200, "likes": {"count": 5}},
        ]

    def test_current_candidate_set(self):
        self._setup_candidate_mocks()
        with patch.object(self.bot, "send_message"):
            self.bot.handle_message(self._make_event("next"))
        self.assertIsNotNone(self.bot.user_state[123]["current_candidate"])

    def test_current_candidate_fields(self):
        self._setup_candidate_mocks()
        with patch.object(self.bot, "send_message"):
            self.bot.handle_message(self._make_event("next"))
        cc = self.bot.user_state[123]["current_candidate"]
        for key in ("id", "first_name", "last_name", "profile_url", "photos"):
            self.assertIn(key, cc)

    def test_current_candidate_id_matches(self):
        self._setup_candidate_mocks()
        with patch.object(self.bot, "send_message"):
            self.bot.handle_message(self._make_event("next"))
        cc = self.bot.user_state[123]["current_candidate"]
        self.assertEqual(cc["id"], 456)

    def test_current_candidate_photos_format(self):
        self._setup_candidate_mocks()
        with patch.object(self.bot, "send_message"):
            self.bot.handle_message(self._make_event("next"))
        cc = self.bot.user_state[123]["current_candidate"]
        self.assertIsInstance(cc["photos"], list)
        for p in cc["photos"]:
            self.assertTrue(p.startswith("photo"))

    def test_handle_next_sends_keyboard(self):
        self._setup_candidate_mocks()
        with patch.object(self.bot, "send_message") as mock_send:
            self.bot.handle_message(self._make_event("next"))
        _, kwargs = mock_send.call_args
        self.assertIsNotNone(kwargs.get("keyboard"))


class TestHandleFavorite(unittest.TestCase):
    @patch("main.VkBotLongPoll")
    def setUp(self, mock_longpoll):
        self.mock_vk_client = MagicMock()
        self.mock_vk_client.group_api.groups.getById.return_value = [
            {"id": 123456}
        ]
        self.bot = VKinderBot(self.mock_vk_client)
        self.candidate = {
            "id": 456,
            "first_name": "Мария",
            "last_name": "Иванова",
            "profile_url": "https://vk.com/id456",
            "photos": ["photo456_100", "photo456_200"],
        }
        self.bot.user_state[123] = {
            "candidates": [],
            "index": 0,
            "city_hint_sent": False,
            "search_params": None,
            "current_candidate": self.candidate,
        }

    def test_no_candidate_warning(self):
        self.bot.user_state[123]["current_candidate"] = None
        with patch.object(self.bot, "send_message") as mock_send:
            self.bot._handle_favorite(123)
        args, kwargs = mock_send.call_args
        self.assertIn("⚠️", args[1])
        self.assertIsNone(kwargs.get("keyboard"))

    def test_no_candidate_no_advance(self):
        self.bot.user_state[123]["current_candidate"] = None
        with patch.object(self.bot, "_handle_next") as mock_next:
            with patch.object(self.bot, "send_message"):
                self.bot._handle_favorite(123)
        mock_next.assert_not_called()

    @patch("main.storage.add_to_favorites", return_value="added")
    def test_favorite_added_sends_confirmation(self, mock_add):
        with patch.object(self.bot, "send_message") as mock_send:
            with patch.object(self.bot, "_handle_next"):
                self.bot._handle_favorite(123)
        call_messages = [c[0][1] for c in mock_send.call_args_list]
        self.assertTrue(
            any("✅ Добавлено в избранное" in m for m in call_messages)
        )

    @patch("main.storage.add_to_favorites", return_value="added")
    def test_favorite_added_with_keyboard(self, mock_add):
        with patch.object(self.bot, "send_message") as mock_send:
            with patch.object(self.bot, "_handle_next"):
                self.bot._handle_favorite(123)
        confirmation_call = None
        for call in mock_send.call_args_list:
            if "✅" in call[0][1]:
                confirmation_call = call
        self.assertIsNotNone(confirmation_call)
        self.assertIsNotNone(confirmation_call[1].get("keyboard"))

    @patch("main.storage.add_to_favorites", return_value="added")
    def test_favorite_added_auto_advance(self, mock_add):
        with patch.object(self.bot, "_handle_next") as mock_next:
            with patch.object(self.bot, "send_message"):
                self.bot._handle_favorite(123)
        mock_next.assert_called_once_with(123)

    @patch("main.storage.add_to_favorites", return_value="duplicate")
    def test_favorite_duplicate_info(self, mock_add):
        with patch.object(self.bot, "send_message") as mock_send:
            with patch.object(self.bot, "_handle_next"):
                self.bot._handle_favorite(123)
        call_messages = [c[0][1] for c in mock_send.call_args_list]
        self.assertTrue(any("ℹ️ Уже в избранном" in m for m in call_messages))

    @patch("main.storage.add_to_favorites", return_value="duplicate")
    def test_favorite_duplicate_auto_advance(self, mock_add):
        with patch.object(self.bot, "_handle_next") as mock_next:
            with patch.object(self.bot, "send_message"):
                self.bot._handle_favorite(123)
        mock_next.assert_called_once_with(123)


class TestHandleBlacklist(unittest.TestCase):
    @patch("main.VkBotLongPoll")
    def setUp(self, mock_longpoll):
        self.mock_vk_client = MagicMock()
        self.mock_vk_client.group_api.groups.getById.return_value = [
            {"id": 123456}
        ]
        self.bot = VKinderBot(self.mock_vk_client)
        self.candidate = {
            "id": 456,
            "first_name": "Мария",
            "last_name": "Иванова",
            "profile_url": "https://vk.com/id456",
            "photos": ["photo456_100", "photo456_200"],
        }
        self.bot.user_state[123] = {
            "candidates": [],
            "index": 0,
            "city_hint_sent": False,
            "search_params": None,
            "current_candidate": self.candidate,
        }

    def test_no_candidate_warning(self):
        self.bot.user_state[123]["current_candidate"] = None
        with patch.object(self.bot, "send_message") as mock_send:
            self.bot._handle_blacklist(123)
        args, kwargs = mock_send.call_args
        self.assertIn("⚠️", args[1])
        self.assertIsNone(kwargs.get("keyboard"))

    @patch("main.storage.add_to_blacklist", return_value="added")
    def test_blacklist_added_sends_confirmation(self, mock_add):
        with patch.object(self.bot, "send_message") as mock_send:
            with patch.object(self.bot, "_handle_next"):
                self.bot._handle_blacklist(123)
        call_messages = [c[0][1] for c in mock_send.call_args_list]
        self.assertTrue(
            any("✅ Добавлено в чёрный список" in m for m in call_messages)
        )

    @patch("main.storage.add_to_blacklist", return_value="added")
    def test_blacklist_added_with_keyboard(self, mock_add):
        with patch.object(self.bot, "send_message") as mock_send:
            with patch.object(self.bot, "_handle_next"):
                self.bot._handle_blacklist(123)
        confirmation_call = None
        for call in mock_send.call_args_list:
            if "✅" in call[0][1]:
                confirmation_call = call
        self.assertIsNotNone(confirmation_call)
        self.assertIsNotNone(confirmation_call[1].get("keyboard"))

    @patch("main.storage.add_to_blacklist", return_value="added")
    def test_blacklist_added_auto_advance(self, mock_add):
        with patch.object(self.bot, "_handle_next") as mock_next:
            with patch.object(self.bot, "send_message"):
                self.bot._handle_blacklist(123)
        mock_next.assert_called_once_with(123)

    @patch("main.storage.add_to_blacklist", return_value="duplicate")
    def test_blacklist_duplicate_info(self, mock_add):
        with patch.object(self.bot, "send_message") as mock_send:
            with patch.object(self.bot, "_handle_next"):
                self.bot._handle_blacklist(123)
        call_messages = [c[0][1] for c in mock_send.call_args_list]
        self.assertTrue(
            any("ℹ️ Уже в чёрном списке" in m for m in call_messages)
        )

    @patch("main.storage.add_to_blacklist", return_value="duplicate")
    def test_blacklist_duplicate_auto_advance(self, mock_add):
        with patch.object(self.bot, "_handle_next") as mock_next:
            with patch.object(self.bot, "send_message"):
                self.bot._handle_blacklist(123)
        mock_next.assert_called_once_with(123)


class TestHandleMessageRouting(unittest.TestCase):
    @patch("main.VkBotLongPoll")
    def setUp(self, mock_longpoll):
        self.mock_vk_client = MagicMock()
        self.mock_vk_client.group_api.groups.getById.return_value = [
            {"id": 123456}
        ]
        self.bot = VKinderBot(self.mock_vk_client)

    def _make_event(self, text, user_id=123):
        event = MagicMock()
        event.object.message = {"text": text, "from_id": user_id}
        return event

    def test_button_next_routes_to_handle_next(self):
        with patch.object(self.bot, "_handle_next") as mock_next:
            self.bot.handle_message(self._make_event("👉 Далее"))
        mock_next.assert_called_once_with(123)

    def test_button_fav_routes_to_handle_favorite(self):
        with patch.object(self.bot, "_handle_favorite") as mock_fav:
            self.bot.handle_message(self._make_event("⭐ В избранное"))
        mock_fav.assert_called_once_with(123)

    def test_button_blacklist_routes_to_handle_blacklist(self):
        with patch.object(self.bot, "_handle_blacklist") as mock_bl:
            self.bot.handle_message(self._make_event("🚫 В чёрный список"))
        mock_bl.assert_called_once_with(123)

    def test_dalye_keyword_in_next_keywords(self):
        self.assertIn("далее", NEXT_KEYWORDS)

    def test_favorites_keyword_routes_to_handler(self):
        event = MagicMock()
        event.object.message = {"text": "📋 Избранное", "from_id": 123}
        with patch.object(self.bot, "_handle_favorites") as mock_handler:
            self.bot.handle_message(event)
        mock_handler.assert_called_once_with(123)

    def test_favorites_slash_command_routes_to_handler(self):
        event = MagicMock()
        event.object.message = {"text": "/favorites", "from_id": 123}
        with patch.object(self.bot, "_handle_favorites") as mock_handler:
            self.bot.handle_message(event)
        mock_handler.assert_called_once_with(123)

    def test_fav_button_still_routes_to_handle_favorite(self):
        event = MagicMock()
        event.object.message = {"text": "⭐ В избранное", "from_id": 123}
        with patch.object(self.bot, "_handle_favorite") as mock_handler:
            self.bot.handle_message(event)
        mock_handler.assert_called_once_with(123)


# ── Task 1 (04-01): exclusion filter tests — RED phase ───────────────────────


class TestHandleNextExcludesIds(unittest.TestCase):
    @patch("main.VkBotLongPoll")
    def setUp(self, mock_longpoll):
        self.mock_vk_client = MagicMock()
        self.mock_vk_client.group_api.groups.getById.return_value = [
            {"id": 123456}
        ]
        self.bot = VKinderBot(self.mock_vk_client)
        self.tmp_dir = tempfile.mkdtemp()
        self._orig_favorites = storage.FAVORITES_FILE
        self._orig_blacklist = storage.BLACKLIST_FILE
        storage.FAVORITES_FILE = os.path.join(self.tmp_dir, "favorites.json")
        storage.BLACKLIST_FILE = os.path.join(self.tmp_dir, "blacklist.json")

    def tearDown(self):
        storage.FAVORITES_FILE = self._orig_favorites
        storage.BLACKLIST_FILE = self._orig_blacklist
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def _setup_mocks(self, excluded_id, extra_candidate_id=101):
        self.mock_vk_client.get_user_info.return_value = [
            {
                "first_name": "Test",
                "last_name": "User",
                "sex": 1,
                "city": {"id": 1, "title": "Moscow"},
                "bdate": "1.1.2000",
            }
        ]
        self.mock_vk_client.find_candidates.return_value = [
            {"id": excluded_id, "first_name": "X", "last_name": "Y"},
            {"id": extra_candidate_id, "first_name": "A", "last_name": "B"},
        ]
        self.mock_vk_client.get_photos.return_value = [
            {"owner_id": extra_candidate_id, "id": 1, "likes": {"count": 10}}
        ]

    def test_batch_excludes_favorited_ids(self):
        """Candidates in favorites.json must not appear in state['candidates']."""
        with open(storage.FAVORITES_FILE, "w", encoding="utf-8") as f:
            json.dump(
                [
                    {
                        "id": 100,
                        "first_name": "X",
                        "last_name": "Y",
                        "owner_id": 1,
                        "added_at": "2026-01-01T00:00:00",
                    }
                ],
                f,
            )
        self._setup_mocks(excluded_id=100, extra_candidate_id=101)
        with patch.object(self.bot, "send_message"):
            self.bot._handle_next(999)
        state = self.bot._get_or_init_state(999)
        self.assertNotIn(100, [c["id"] for c in state["candidates"]])

    def test_batch_excludes_blacklisted_ids(self):
        """Candidates in blacklist.json must not appear in state['candidates']."""
        with open(storage.BLACKLIST_FILE, "w", encoding="utf-8") as f:
            json.dump(
                [
                    {
                        "id": 200,
                        "first_name": "X",
                        "last_name": "Y",
                        "owner_id": 1,
                        "added_at": "2026-01-01T00:00:00",
                    }
                ],
                f,
            )
        self._setup_mocks(excluded_id=200, extra_candidate_id=201)
        with patch.object(self.bot, "send_message"):
            self.bot._handle_next(999)
        state = self.bot._get_or_init_state(999)
        self.assertNotIn(200, [c["id"] for c in state["candidates"]])

    def test_excluded_ids_is_set_type(self):
        """state['excluded_ids'] must be a set after _handle_next runs."""
        self._setup_mocks(excluded_id=999, extra_candidate_id=101)
        with patch.object(self.bot, "send_message"):
            self.bot._handle_next(999)
        state = self.bot._get_or_init_state(999)
        self.assertIsInstance(state["excluded_ids"], set)


class TestHandleFavoriteUpdatesExcluded(unittest.TestCase):
    @patch("main.VkBotLongPoll")
    def setUp(self, mock_longpoll):
        self.mock_vk_client = MagicMock()
        self.mock_vk_client.group_api.groups.getById.return_value = [
            {"id": 123456}
        ]
        self.bot = VKinderBot(self.mock_vk_client)
        self.tmp_dir = tempfile.mkdtemp()
        self._orig_favorites = storage.FAVORITES_FILE
        self._orig_blacklist = storage.BLACKLIST_FILE
        storage.FAVORITES_FILE = os.path.join(self.tmp_dir, "favorites.json")
        storage.BLACKLIST_FILE = os.path.join(self.tmp_dir, "blacklist.json")

    def tearDown(self):
        storage.FAVORITES_FILE = self._orig_favorites
        storage.BLACKLIST_FILE = self._orig_blacklist
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def test_favorite_adds_to_excluded(self):
        """_handle_favorite must add candidate id to state['excluded_ids']."""
        state = self.bot._get_or_init_state(999)
        state["current_candidate"] = {
            "id": 300,
            "first_name": "A",
            "last_name": "B",
            "profile_url": "https://vk.com/id300",
            "photos": [],
        }
        state["excluded_ids"] = set()
        self.mock_vk_client.get_user_info.return_value = [
            {
                "sex": 1,
                "city": {"id": 1, "title": "Moscow"},
                "bdate": "1.1.2000",
            }
        ]
        self.mock_vk_client.find_candidates.return_value = []
        self.mock_vk_client.get_photos.return_value = []
        with patch.object(self.bot, "send_message"):
            self.bot._handle_favorite(999)
        self.assertIn(300, state["excluded_ids"])

    def test_blacklist_adds_to_excluded(self):
        """_handle_blacklist must add candidate id to state['excluded_ids']."""
        state = self.bot._get_or_init_state(999)
        state["current_candidate"] = {
            "id": 400,
            "first_name": "A",
            "last_name": "B",
            "profile_url": "https://vk.com/id400",
            "photos": [],
        }
        state["excluded_ids"] = set()
        self.mock_vk_client.get_user_info.return_value = [
            {
                "sex": 1,
                "city": {"id": 1, "title": "Moscow"},
                "bdate": "1.1.2000",
            }
        ]
        self.mock_vk_client.find_candidates.return_value = []
        self.mock_vk_client.get_photos.return_value = []
        with patch.object(self.bot, "send_message"):
            self.bot._handle_blacklist(999)
        self.assertIn(400, state["excluded_ids"])


# ── Task 1 (04-02): view favorites tests — RED phase ─────────────────────────


class TestHandleFavorites(unittest.TestCase):
    @patch("main.VkBotLongPoll")
    def setUp(self, mock_longpoll):
        self.mock_vk_client = MagicMock()
        self.mock_vk_client.group_api.groups.getById.return_value = [
            {"id": 123456}
        ]
        self.bot = VKinderBot(self.mock_vk_client)
        self.tmp_dir = tempfile.mkdtemp()
        self._orig_favorites = storage.FAVORITES_FILE
        self._orig_blacklist = storage.BLACKLIST_FILE
        storage.FAVORITES_FILE = os.path.join(self.tmp_dir, "favorites.json")
        storage.BLACKLIST_FILE = os.path.join(self.tmp_dir, "blacklist.json")

    def tearDown(self):
        storage.FAVORITES_FILE = self._orig_favorites
        storage.BLACKLIST_FILE = self._orig_blacklist
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def test_empty_list(self):
        # Do NOT create favorites.json — missing file -> _load_json returns []
        with patch.object(self.bot, "send_message") as mock_send:
            self.bot._handle_favorites(999)
        mock_send.assert_called_once()
        msg = mock_send.call_args[0][1]
        self.assertIn("Список пуст", msg)

    def test_formatted_list(self):
        entries = [
            {
                "id": 123,
                "first_name": "Мария",
                "last_name": "Петрова",
                "profile_url": "https://vk.com/id123",
                "photos": [],
                "owner_id": 1,
                "added_at": "2026-03-22T14:30:00",
            },
            {
                "id": 456,
                "first_name": "Анна",
                "last_name": "Смирнова",
                "profile_url": "https://vk.com/id456",
                "photos": [],
                "owner_id": 1,
                "added_at": "2026-03-21T10:00:00",
            },
        ]
        with open(storage.FAVORITES_FILE, "w", encoding="utf-8") as f:
            json.dump(entries, f)
        with patch.object(self.bot, "send_message") as mock_send:
            self.bot._handle_favorites(999)
        msg = mock_send.call_args[0][1]
        self.assertIn("1.", msg)
        self.assertIn("2.", msg)
        self.assertIn("https://vk.com/id123", msg)
        self.assertIn("Добавлен:", msg)
        self.assertIn("Мария Петрова", msg)

    def test_cap_at_50(self):
        entries = [
            {
                "id": i,
                "first_name": f"Name{i}",
                "last_name": "Last",
                "owner_id": 1,
                "added_at": "2026-01-01T00:00:00",
            }
            for i in range(55)
        ]
        with open(storage.FAVORITES_FILE, "w", encoding="utf-8") as f:
            json.dump(entries, f)
        with patch.object(self.bot, "send_message") as mock_send:
            self.bot._handle_favorites(999)
        msg = mock_send.call_args[0][1]
        self.assertIn("показано 50 из 55", msg)
        self.assertNotIn("51.", msg)

    def test_no_keyboard(self):
        entries = [
            {
                "id": 1,
                "first_name": "Тест",
                "last_name": "Тестов",
                "owner_id": 1,
                "added_at": "2026-01-01T00:00:00",
            }
        ]
        with open(storage.FAVORITES_FILE, "w", encoding="utf-8") as f:
            json.dump(entries, f)
        with patch.object(self.bot, "send_message") as mock_send:
            self.bot._handle_favorites(999)
        call_kwargs = mock_send.call_args[1] if mock_send.call_args[1] else {}
        self.assertTrue(
            "keyboard" not in call_kwargs
            or call_kwargs.get("keyboard") is None,
            "send_message must be called without keyboard kwarg for favorites list",
        )


# ── Plan 01-03: error-resilience tests (RED phase) ────────────────────────────


class TestErrorResilience(unittest.TestCase):
    @patch("main.VkBotLongPoll")
    def setUp(self, mock_longpoll):
        self.mock_vk_client = MagicMock()
        self.mock_vk_client.group_api.groups.getById.return_value = [
            {"id": 123456}
        ]
        self.bot = VKinderBot(self.mock_vk_client)

    def test_handle_greeting_get_user_info_error(self):
        """When get_user_info raises, greeting still sends a fallback reply containing 'Привет'."""
        self.mock_vk_client.get_user_info.side_effect = Exception(
            "token error"
        )
        event = MagicMock()
        event.object.message = {"text": "hello", "from_id": 123}
        with patch.object(self.bot, "send_message") as mock_send:
            self.bot.handle_message(event)
            mock_send.assert_called_once()
            args, _ = mock_send.call_args
            self.assertIn(
                "Привет", args[1], "Fallback greeting must contain 'Привет'"
            )

    def test_send_message_api_error(self):
        """When messages.send raises, send_message does NOT re-raise the exception."""
        self.mock_vk_client.group_api.messages.send.side_effect = Exception(
            "API Error"
        )
        with patch("builtins.print") as mock_print:
            # Must complete without raising
            self.bot.send_message(123, "Test")
            mock_print.assert_called_once()
            printed_msg = str(mock_print.call_args)
            self.assertIn("123", printed_msg)
