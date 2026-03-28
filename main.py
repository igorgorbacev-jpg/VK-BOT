import datetime
import re

from vk_api.bot_longpoll import VkBotEventType, VkBotLongPoll
from vk_api.keyboard import VkKeyboard, VkKeyboardColor

import storage
from vk_client import VKClient, parse_age_from_bdate

OPPOSITE_SEX = {1: 2, 2: 1}

NEXT_KEYWORDS = {"next", "дальше", "ещё", "далее"}
FAV_KEYWORDS = {"в избранное", "favorite"}
BLACKLIST_KEYWORDS = {
    "чёрный список",
    "черный список",
    "blacklist",
    "в чёрный список",
    "в черный список",
}
FAVORITES_KEYWORDS = {"избранное"}


def normalize_text(text: str) -> str:
    """Strip emojis/punctuation and normalize to lowercase for routing (D-07, D-08)."""
    return re.sub(r"[^\w\s]", "", text, flags=re.UNICODE).lower().strip()


def get_keyboard():
    """Build and return persistent VK keyboard JSON string (D-01 through D-03)."""
    kb = VkKeyboard(one_time=False)
    kb.add_button("👉 Далее", color=VkKeyboardColor.PRIMARY)
    kb.add_line()
    kb.add_button("⭐ В избранное", color=VkKeyboardColor.POSITIVE)
    kb.add_button("🚫 В чёрный список", color=VkKeyboardColor.NEGATIVE)
    kb.add_line()
    kb.add_button("📋 Избранное", color=VkKeyboardColor.PRIMARY)
    return kb.get_keyboard()


KEYBOARD = get_keyboard()


def format_candidate_text(candidate):
    """Return formatted text for a candidate card per D-23/D-24."""
    name = f"{candidate.get('first_name', '')} {candidate.get('last_name', '')}".strip()
    age = parse_age_from_bdate(candidate.get("bdate"))
    city_obj = candidate.get("city")
    city = city_obj.get("title") if city_obj else None
    age_str = str(age) if age else "\u2014"
    city_str = city if city else "\u2014"
    uid = candidate["id"]
    return f"{name}, {age_str}, {city_str}\nhttps://vk.com/id{uid}"


def format_photo_attachment(photos):
    """Return comma-joined photo attachment strings for up to 3 photos (D-25)."""
    top3 = photos[:3]
    return ",".join(f"photo{p['owner_id']}_{p['id']}" for p in top3)


class VKinderBot:
    def __init__(self, vk_client):
        self.vk_client = vk_client
        # In-memory session state keyed by user_id (D-06, D-07)
        self.user_state = {}
        # Get group info to find the group ID for LongPoll
        group_info = self.vk_client.group_api.groups.getById()[0]
        self.group_id = group_info["id"]
        self.longpoll = VkBotLongPoll(
            self.vk_client.group_session, self.group_id
        )

    def listen(self):
        for event in self.longpoll.listen():
            if event.type == VkBotEventType.MESSAGE_NEW:
                self.handle_message(event)

    def handle_message(self, event):
        raw_text = event.object.message["text"].strip()
        message_text = normalize_text(raw_text)
        user_id = event.object.message["from_id"]

        if message_text in NEXT_KEYWORDS:
            self._handle_next(user_id)
        elif message_text in FAV_KEYWORDS:
            self._handle_favorite(user_id)
        elif message_text in BLACKLIST_KEYWORDS:
            self._handle_blacklist(user_id)
        elif message_text in FAVORITES_KEYWORDS or raw_text == "/favorites":
            self._handle_favorites(user_id)
        elif any(
            keyword in message_text
            for keyword in ["привет", "hello", "start", "начать"]
        ):
            try:
                user_info = self.vk_client.get_user_info(user_id)
                first_name = user_info[0]["first_name"]
            except Exception as e:
                print(f"[VKinderBot] get_user_info failed: {e}")
                first_name = "друг"
            self.send_message(
                user_id,
                f"Привет, {first_name}! Я VKinder. Нажми «👉 Далее» для поиска.",
                keyboard=KEYBOARD,
            )
        elif raw_text == "/help":
            self.send_message(
                user_id,
                "Это бот для поиска партнеров ВКонтакте. Инструкция:\n"
                "- Кнопка «👉 Далее» (или текст: next, дальше, ещё, далее) — найти кандидата\n"
                "- Кнопка «⭐ В избранное» (или текст: в избранное) — сохранить\n"
                "- Кнопка «🚫 В чёрный список» (или текст: чёрный список, черный список) — заблокировать\n"
                "- Кнопка «📋 Избранное» (или текст: /favorites) — посмотреть избранное\n"
                "- '/help' — эта помощь\n"
                "- '/test_search' — тестовый поиск",
                keyboard=KEYBOARD,
            )
        elif raw_text == "/test_search":
            try:
                results = self.vk_client.search_users(count=1)
                count = results.get("count", 0)
                self.send_message(
                    user_id, f"User search API: OK ({count} результатов)"
                )
            except Exception as e:
                self.send_message(
                    user_id, f"User search API: ERROR ({str(e)})"
                )

    def send_message(self, user_id, message, attachment=None, keyboard=None):
        from random import randrange

        kwargs = {
            "user_id": user_id,
            "message": message,
            "random_id": randrange(10**7),
        }
        if attachment:
            kwargs["attachment"] = attachment
        if keyboard:
            kwargs["keyboard"] = keyboard
        try:
            self.vk_client.group_api.messages.send(**kwargs)
        except Exception as e:
            print(f"[VKinderBot] send_message failed for user {user_id}: {e}")

    # ── Session state helpers ─────────────────────────────────────────────────

    def _get_or_init_state(self, user_id):
        """Return user's session state dict, creating it if absent (D-06)."""
        if user_id not in self.user_state:
            self.user_state[user_id] = {
                "candidates": [],
                "index": 0,
                "city_hint_sent": False,
                "search_params": None,
                "current_candidate": None,
                "excluded_ids": set(),
            }
        return self.user_state[user_id]

    def _build_search_params(self, user_id):
        """
        Derive find_candidates kwargs from user profile (D-08 through D-14).
        Returns (params dict, no_city bool).
        """
        user_info = self.vk_client.get_user_info(user_id)[0]
        age = parse_age_from_bdate(user_info.get("bdate"))
        city_obj = user_info.get("city")
        city_id = city_obj["id"] if city_obj else None
        user_sex = user_info.get("sex", 0)
        target_sex = OPPOSITE_SEX.get(user_sex)

        params = {}
        if target_sex is not None:
            params["sex"] = target_sex
        if city_id is not None:
            params["city_id"] = city_id
        if age is not None:
            params["age_from"] = max(18, age - 5)
            params["age_to"] = age + 5

        return params, city_id is None

    # ── next command handler ──────────────────────────────────────────────────

    def _get_current_city_id(self, user_id):
        """Return current city_id from user VK profile, or None if no city set."""
        user_info = self.vk_client.get_user_info(user_id)[0]
        city_obj = user_info.get("city")
        return city_obj["id"] if city_obj else None

    def _handle_next(self, user_id):
        """
        Handle 'next'/'дальше'/'ещё' command (D-01 through D-21).
        Fetches candidate, skips those with no photos, shows card with attachment.
        """
        state = self._get_or_init_state(user_id)

        # Detect mid-batch city change (UAT gap closure)
        if state["candidates"] and state["index"] < len(state["candidates"]):
            current_city_id = self._get_current_city_id(user_id)
            cached_city_id = (state["search_params"] or {}).get("city_id")
            if current_city_id != cached_city_id:
                state["candidates"] = []
                state["index"] = 0

        # Need a fresh batch if list is empty or exhausted
        if not state["candidates"] or state["index"] >= len(
            state["candidates"]
        ):
            if state["candidates"]:
                # Inform user the current batch is done (D-04)
                self.send_message(
                    user_id,
                    "Кандидаты закончились, ищу новых...",
                    keyboard=KEYBOARD,
                )

            params, no_city = self._build_search_params(user_id)
            state["search_params"] = params

            # One-time city hint (D-13, D-14)
            if no_city and not state["city_hint_sent"]:
                self.send_message(
                    user_id,
                    "Укажи город в профиле, чтобы улучшить результаты",
                    keyboard=KEYBOARD,
                )
                state["city_hint_sent"] = True

            candidates = self.vk_client.find_candidates(**params, count=50)
            fav_ids = {
                e["id"] for e in storage._load_json(storage.FAVORITES_FILE)
            }
            bl_ids = {
                e["id"] for e in storage._load_json(storage.BLACKLIST_FILE)
            }
            state["excluded_ids"] = fav_ids | bl_ids
            candidates = [
                c for c in candidates if c["id"] not in state["excluded_ids"]
            ]
            state["candidates"] = candidates
            state["index"] = 0

            if not candidates:
                self.send_message(
                    user_id,
                    "Никого не найдено. Попробуй позже.",
                    keyboard=KEYBOARD,
                )
                return

        # Advance through candidates, skipping those with no accessible photos (D-19, D-20)
        while state["index"] < len(state["candidates"]):
            candidate = state["candidates"][state["index"]]
            state["index"] += 1
            photos = self.vk_client.get_photos(candidate["id"])
            if not photos:
                continue  # silently skip (D-21)
            state["current_candidate"] = {
                "id": candidate["id"],
                "first_name": candidate.get("first_name", ""),
                "last_name": candidate.get("last_name", ""),
                "profile_url": f"https://vk.com/id{candidate['id']}",
                "photos": [
                    f"photo{p['owner_id']}_{p['id']}" for p in photos[:3]
                ],
            }
            text = format_candidate_text(candidate)
            attachment = format_photo_attachment(photos)
            self.send_message(
                user_id, text, attachment=attachment, keyboard=KEYBOARD
            )
            return

        # Whole batch had no accessible photos — try a fresh search
        self.send_message(
            user_id, "Кандидаты закончились, ищу новых...", keyboard=KEYBOARD
        )
        state["candidates"] = []
        state["index"] = 0
        self._handle_next(user_id)

    def _handle_favorite(self, user_id):
        """Handle '⭐ В избранное' button press (D-11 through D-16)."""
        state = self._get_or_init_state(user_id)
        candidate = state.get("current_candidate")
        if candidate is None:
            self.send_message(
                user_id, "⚠️ Сначала нажмите «Далее», чтобы получить кандидата"
            )
            return
        result = storage.add_to_favorites(user_id, candidate)
        state.setdefault("excluded_ids", set()).add(candidate["id"])
        if result == "duplicate":
            self.send_message(user_id, "ℹ️ Уже в избранном", keyboard=KEYBOARD)
        else:
            self.send_message(
                user_id, "✅ Добавлено в избранное", keyboard=KEYBOARD
            )
        self._handle_next(user_id)

    def _handle_blacklist(self, user_id):
        """Handle '🚫 В чёрный список' button press (D-11 through D-16)."""
        state = self._get_or_init_state(user_id)
        candidate = state.get("current_candidate")
        if candidate is None:
            self.send_message(
                user_id, "⚠️ Сначала нажмите «Далее», чтобы получить кандидата"
            )
            return
        result = storage.add_to_blacklist(user_id, candidate)
        state.setdefault("excluded_ids", set()).add(candidate["id"])
        if result == "duplicate":
            self.send_message(
                user_id, "ℹ️ Уже в чёрном списке", keyboard=KEYBOARD
            )
        else:
            self.send_message(
                user_id, "✅ Добавлено в чёрный список", keyboard=KEYBOARD
            )
        self._handle_next(user_id)

    def _handle_favorites(self, user_id):
        """Handle 'view favorites' command (UI-04, D-05 through D-08)."""
        data = storage._load_json(storage.FAVORITES_FILE)
        if not data:
            msg = "📋 Избранные:\n\nСписок пуст 😢\nДобавляйте пользователей с помощью кнопки ⭐"
            self.send_message(user_id, msg)
            return

        total = len(data)
        shown = data[:50]
        lines = ["📋 Избранные:\n"]
        for i, entry in enumerate(shown, start=1):
            try:
                dt = datetime.datetime.strptime(
                    entry["added_at"], "%Y-%m-%dT%H:%M:%S"
                )
                date_str = dt.strftime("%d %b %Y")
            except (KeyError, ValueError):
                date_str = "\u2014"
            name = f"{entry.get('first_name', '')} {entry.get('last_name', '')}".strip()
            uid = entry.get("id", "")
            lines.append(
                f"{i}. {name}\nhttps://vk.com/id{uid}\nДобавлен: {date_str}\n"
            )
        if total > 50:
            lines.append(f"... (показано 50 из {total})")
        self.send_message(user_id, "\n".join(lines))


if __name__ == "__main__":
    vk_client = VKClient()
    bot = VKinderBot(vk_client)
    bot.listen()

