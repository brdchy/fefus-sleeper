import asyncio
from datetime import datetime, timedelta, date, timezone

from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart, Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton

from bot.core.config import load_config
from bot.core.models import PetState, UserSettings, UserState
from bot.core.repositories import UsersRepository, AdminRepository, HobbiesRepository
from bot.core.admin_handlers import admin_router, cmd_admin
from bot.core.reminders import reminders_worker
from bot.core.health import degrade_pet, touch_pet, get_health_state, get_health_status_message, HealthState
from bot.core.hobby_system import (
    get_hobby_effectiveness,
    get_duration_for_hobby,
    calculate_mastery_level,
    get_mastery_bonus,
    get_random_event,
    update_hobby_streak,
    get_streak_bonus,
    get_overuse_penalty,
    format_hobby_session_result,
    get_hobby_recommendations,
    get_hobby_stats_summary,
    get_social_hobby_event,
    get_social_bonus,
    format_social_hobby_result,
)
from bot.core.social import SocialRooms
from bot.core.friends_system import (
    get_friendship_level,
    get_friendship_bonuses,
    get_num_participants_bonus,
    get_friendship_stars,
    get_random_coop_event,
    format_friendship_info,
    format_coop_result,
)
from bot.core.repositories import FriendsRepository, CoopSessionsRepository
from bot.core.stats import StatsRepository
from bot.core.menu import (
    main_menu_keyboard,
    actions_menu_keyboard,
    settings_menu_keyboard,
    friends_menu_keyboard,
    get_today_stats,
    format_weekly_stats,
)
from bot.core.advice import get_advice_for_today, get_weekly_advice_summary, get_monthly_advice_summary


# FSM для ввода кода дружбы
class FriendshipFSM(StatesGroup):
    waiting_for_friend_code = State()

# FSM для настройки воды
class WaterSettingsFSM(StatesGroup):
    waiting_for_glass_volume = State()  # Ожидание ввода объема стакана

# FSM для настройки нормы сна
class SleepNormFSM(StatesGroup):
    waiting_for_sleep_norm_answer = State()  # Ожидание ответа на вопрос о сне


DISLCAIMER_TEXT = (
    "Бот «FEFUS» не является медицинским помощником и не предоставляет "
    "медицинских консультаций. Информация и рекомендации носят исключительно "
    "информационный характер и не являются прямым указанием к действию.\n\n"
    "Создадим твою выдру-спутника сна?"
)


users_repo = UsersRepository()
admin_repo = AdminRepository()
hobbies_repo = HobbiesRepository()
social_rooms = SocialRooms()
stats_repo = StatsRepository()
friends_repo = FriendsRepository()
coop_sessions_repo = CoopSessionsRepository()


# Старое меню оставлено для обратной совместимости, но теперь используется новое главное меню


async def cmd_start(message: Message) -> None:
    existing = users_repo.get_user(message.from_user.id)

    if existing is None:
        # Первый запуск пользователя
        await message.answer(
            DISLCAIMER_TEXT + "\n\nНапиши имя для своей выдры:",
        )
    else:
        pet = existing.pet
        status_emoji = "🦦" if pet.is_alive else "💀"
        await message.answer(
            f"{status_emoji} Привет! Рад снова видеть тебя и выдру {pet.name}!\n\n"
            f"Выбери действие в главном меню:",
            reply_markup=main_menu_keyboard(),
        )


async def handle_pet_name(message: Message) -> None:
    # Проверяем, существует ли пользователь
    user = users_repo.get_user(message.from_user.id)
    
    # Если пользователь уже существует, проверяем, не вводит ли он норму воды
    if user is not None:
        # Имя уже задано — передадим управление в общий обработчик
        # Но сначала проверяем, не вводит ли пользователь норму воды
        if not user.settings.water_norm_set:
            # Пользователь может вводить норму воды
            await handle_water_norm_setup(message)
            return
        # Если пользователь существует и норма воды установлена, это не ввод имени
        await handle_unknown(message)
        return

    # Пользователя нет в базе - это новый пользователь, вводящий имя выдры
    name = message.text.strip() if message.text else "Выдра"
    
    # Проверяем, что имя не пустое
    if not name:
        name = "Выдра"

    config = load_config()

    pet = PetState(name=name)
    settings = UserSettings(timezone=config.default_timezone)
    user_state = UserState(
        user_id=message.from_user.id,
        pet=pet,
        settings=settings,
    )
    users_repo.save_user(user_state)

    # Первый пользователь становится администратором
    admin_settings = admin_repo.get_settings()
    if not admin_settings.admin_ids:
        admin_settings.admin_ids.append(message.from_user.id)
        admin_repo.save_settings(admin_settings)

    # Спрашиваем про норму воды при первом запуске
    if not user_state.settings.water_norm_set:
        await message.answer(
            f"Отлично! Твою выдру зовут {name}. Позаботься о ней ❤️\n\n"
            f"Выдра только родилась и ждёт твоей заботы.\n\n"
            f"💧 Знаешь ли ты свою норму воды в день?",
            reply_markup=water_norm_setup_keyboard()
        )
    else:
        await message.answer(
            f"Отлично! Твою выдру зовут {name}. Позаботься о ней ❤️\n\n"
            f"Выдра только родилась и ждёт твоей заботы. "
            f"Используй кнопки ниже для взаимодействия!",
            reply_markup=main_menu_keyboard()
        )


async def cmd_pet_status(message: Message) -> None:
    user = users_repo.get_user(message.from_user.id)
    if user is None:
        await message.answer("Сначала нажми /start и создай свою выдру 🦦")
        return

    # Деградируем состояние выдры перед проверкой
    degrade_pet(user)
    users_repo.save_user(user)
    
    pet = user.pet
    
    # Получаем состояние здоровья
    health_state = get_health_state(pet)
    health_status = get_health_status_message(pet)
    
    status_emoji = "🦦" if pet.is_alive else "💀"
    status_text = "жива и полна сил" if pet.is_alive else "мертва"
    
    if pet.vacation_mode:
        status_text = "в отпуске (неактивна)"
        status_emoji = "🏖️"
    
    await message.answer(
        f"{status_emoji} Состояние выдры {pet.name}:\n\n"
        f"Статус: {status_text}\n"
        f"Состояние здоровья: {health_status}\n"
        f"Счастье: {pet.happiness}/100 {'😊' if pet.happiness > 70 else '😐' if pet.happiness > 40 else '😢'}\n"
        f"Энергия: {pet.energy}/100 {'⚡' if pet.energy > 70 else '🔋' if pet.energy > 40 else '🪫'}\n"
        f"Сытость: {pet.hunger}/100 {'🍽️' if pet.hunger > 70 else '🥄' if pet.hunger > 40 else '🍽️'}\n"
        f"Вода: {pet.thirst}/100 {'💧' if pet.thirst > 70 else '💦' if pet.thirst > 40 else '🏜️'}\n"
        f"Монеты: {pet.money} 💰\n"
        f"Возраст: {pet.age_days} дней\n"
        f"Хобби: {len(pet.unlocked_hobbies)} разблокировано\n"
        f"Бесплатных воскрешений: {pet.free_revives_left}"
    )


async def cmd_my_stats(message: Message) -> None:
    user = users_repo.get_user(message.from_user.id)
    if user is None:
        await message.answer("Сначала нажми /start и создай свою выдру 🦦")
        return

    stats = stats_repo.get_user_stats(user.user_id)
    sleep_hours = stats.total_sleep_minutes / 60
    
    await message.answer(
        f"📊 Твоя статистика:\n\n"
        f"💤 Всего сна: {sleep_hours:.1f} часов ({stats.total_sleep_minutes} минут)\n"
        f"🍽️ Кормлений: {stats.feed_events}\n"
        f"💧 Воды: {stats.water_events}\n"
        f"💼 Рабочих сессий: {stats.work_sessions}\n"
        f"🎨 Хобби: {stats.hobby_sessions}\n\n"
        f"Продолжай заботиться о выдре! 🦦"
    )


async def handle_unknown(message: Message) -> None:
    await message.answer("Используй кнопки ниже, чтобы взаимодействовать с выдрой.")


async def cmd_settings(message: Message) -> None:
    user = users_repo.get_user(message.from_user.id)
    if user is None:
        await message.answer("Сначала нажми /start и создай свою выдру 🦦")
        return

    pet = user.pet
    await message.answer(
        "Настройки выдры:\n"
        f"- Имя: {pet.name}\n"
        f"- Часовой пояс: {user.settings.timezone}\n"
        f"- Монеты: {pet.money}\n"
        f"- Возраст: {pet.age_days} дней\n\n"
        "Команды:\n"
        "/set_name НовоеИмя — изменить имя выдры\n"
        "/set_timezone Region/City — изменить часовой пояс (например, Asia/Vladivostok)\n"
        "/pet_status — показать состояние выдры\n"
        "/my_stats — показать твою статистику",
    )


async def cmd_set_name(message: Message) -> None:
    user = users_repo.get_user(message.from_user.id)
    if user is None:
        await message.answer("Сначала нажми /start и создай свою выдру 🦦")
        return

    parts = message.text.split(maxsplit=1) if message.text else []
    if len(parts) < 2:
        await message.answer("Укажи новое имя: /set_name Имя")
        return

    new_name = parts[1].strip()
    if not new_name:
        await message.answer("Имя не может быть пустым.")
        return

    user.pet.name = new_name
    if user.settings.pet_name is None:
        user.settings.pet_name = new_name
    else:
        user.settings.pet_name = new_name
    users_repo.save_user(user)
    await message.answer(f"Теперь выдру зовут {new_name} 🦦")


async def cmd_set_timezone(message: Message) -> None:
    user = users_repo.get_user(message.from_user.id)
    if user is None:
        await message.answer("Сначала нажми /start и создай свою выдру 🦦")
        return

    parts = message.text.split(maxsplit=1) if message.text else []
    if len(parts) < 2:
        await message.answer(
            "Укажи часовой пояс в формате Region/City, например:\n"
            "/set_timezone Asia/Vladivostok"
        )
        return

    tz = parts[1].strip()
    # Пока без валидации списка таймзон — просто сохраняем строку
    user.settings.timezone = tz
    users_repo.save_user(user)
    await message.answer(f"Часовой пояс обновлён: {tz}")


async def cmd_revive(message: Message) -> None:
    user = users_repo.get_user(message.from_user.id)
    if user is None:
        await message.answer("Сначала нажми /start и создай свою выдру 🦦")
        return

    pet = user.pet
    
    # Если выдра в режиме отпуска, выводим из отпуска
    if pet.vacation_mode:
        pet.vacation_mode = False
        pet.is_alive = True
        pet.happiness = 50
        pet.energy = 50
        pet.hunger = 50
        pet.thirst = 50
        pet.critical_state_since = None
        # Сбрасываем флаг уведомления о смерти (на случай, если была мертва)
        if "death_notification_sent" in user.last_reminders:
            del user.last_reminders["death_notification_sent"]
        users_repo.save_user(user)
        await message.answer(
            "🦦 Выдра вернулась из отпуска и снова активна!\n"
            "Она скучала по тебе и готова к новым приключениям!",
            reply_markup=main_menu_keyboard()
        )
        return
    
    if pet.is_alive:
        await message.answer("Выдра и так жива и полна сил 🦦")
        return

    # Бесплатное воскрешение
    if pet.free_revives_left > 0:
        pet.free_revives_left -= 1
        pet.is_alive = True
        pet.happiness = 50
        pet.energy = 50
        pet.hunger = 50
        pet.thirst = 50
        pet.critical_state_since = None
        # Сбрасываем флаг уведомления о смерти
        if "death_notification_sent" in user.last_reminders:
            del user.last_reminders["death_notification_sent"]
        touch_pet(user)
        users_repo.save_user(user)
        await message.answer("Выдра воскресла благодаря твоей заботе 🦦❤️")
        return

    # Второе воскрешение — через подписку на канал
    settings = admin_repo.get_settings()
    channel = settings.required_channel_username
    if not channel:
        await message.answer(
            "Канал для проверки подписки ещё не настроен администратором. "
            "Попроси админа указать его через /set_channel."
        )
        return

    try:
        member = await message.bot.get_chat_member(channel, message.from_user.id)
        if member.status not in ("left", "kicked"):
            pet.is_alive = True
            pet.happiness = 60
            pet.energy = 60
            pet.hunger = 60
            pet.thirst = 60
            pet.critical_state_since = None
            # Сбрасываем флаг уведомления о смерти
            if "death_notification_sent" in user.last_reminders:
                del user.last_reminders["death_notification_sent"]
            touch_pet(user)
            users_repo.save_user(user)
            await message.answer(
                "Спасибо за поддержку канала! Выдра воскресла и готова продолжать путь сна и здоровья 🦦✨"
            )
            return
    except Exception:
        # Если не удалось проверить подписку, сообщаем об этом
        await message.answer(
            "Не удалось проверить подписку на канал. Убедись, что бот добавлен как администратор в канале "
            "и указан корректный @username в /set_channel."
        )
        return

    await message.answer(
        f"Чтобы воскресить выдру, подпишись на канал {channel}, а затем снова отправь /revive."
    )


async def get_or_ask_start(message: Message) -> UserState | None:
    user = users_repo.get_user(message.from_user.id)
    if user is None:
        await message.answer("Сначала нажми /start и создай свою выдру 🦦")
        return None
    
    # Деградируем состояние выдры перед проверкой
    degrade_pet(user)
    users_repo.save_user(user)
    
    pet = user.pet
    
    if not pet.is_alive:
        await message.answer(
            "Твоя выдра сейчас мертва 🥺\n"
            "Попробуй команду /revive, чтобы попытаться её воскресить."
        )
        return None
    
    # Если выдра в режиме отпуска, сообщаем об этом
    if pet.vacation_mode:
        await message.answer(
            "🦦 Выдра вернулась из отпуска! Она скучала по тебе.\n"
            "Теперь она снова активна и готова к взаимодействию!",
            reply_markup=main_menu_keyboard()
        )
        pet.vacation_mode = False
        users_repo.save_user(user)
    
    return user


async def handle_wake_pet(message: Message) -> None:
    user = await get_or_ask_start(message)
    if not user:
        return

    pet = user.pet
    
    # Проверяем, спит ли выдра
    if pet.avatar_key != "sleep" and pet.last_sleep_start is None:
        await message.answer(
            "🦦 Выдра уже бодрствует! 😊\n\n"
            "Она готова к действиям.",
            reply_markup=main_menu_keyboard()
        )
        return
    
    # Проверяем, не на работе ли выдра
    if pet.at_work:
        await message.answer(
            "🦦 Выдра сейчас на работе и не может проснуться!\n\n"
            "Сначала забери её с работы, а потом уже можно будить.",
            reply_markup=main_menu_keyboard()
        )
        return

    degrade_pet(user)
    pet.avatar_key = "awake"
    
    # Учитываем сон: если была запись о начале сна, считаем продолжительность
    from datetime import datetime, timezone
    if pet.last_sleep_start:
        try:
            sleep_start = datetime.fromisoformat(pet.last_sleep_start)
            wake_time = datetime.now(timezone.utc)
            sleep_duration = (wake_time - sleep_start).total_seconds() / 60  # минуты
            if sleep_duration > 0:
                stats_repo.add_sleep_minutes(user.user_id, int(sleep_duration))
                hours = int(sleep_duration // 60)
                minutes = int(sleep_duration % 60)
                sleep_msg = f"\nВыдра спала {hours}ч {minutes}м."
            else:
                sleep_msg = ""
            pet.last_sleep_start = None
        except Exception:
            sleep_msg = ""
            pet.last_sleep_start = None
    else:
        sleep_msg = ""
    
    pet.energy = min(100, pet.energy + 15)
    pet.happiness = min(100, pet.happiness + 5)
    pet.last_wake_time = datetime.now(timezone.utc).isoformat()
    touch_pet(user)
    users_repo.save_user(user)

    await message.answer(
        f"Выдра проснулась и энергично потянулась 🦦{sleep_msg}",
        reply_markup=main_menu_keyboard()
    )


async def handle_sleep_pet(message: Message) -> None:
    user = await get_or_ask_start(message)
    if not user:
        return

    pet = user.pet
    
    # Проверяем, не спит ли выдра уже
    if pet.avatar_key == "sleep" or pet.last_sleep_start is not None:
        await message.answer(
            "🦦 Выдра уже спит! 😴\n\n"
            "Если хочешь её разбудить, нажми 'Разбудить питомца'.",
            reply_markup=main_menu_keyboard()
        )
        return
    
    # Проверяем, не на работе ли выдра
    if pet.at_work:
        await message.answer(
            "🦦 Выдра сейчас на работе и не может лечь спать!\n\n"
            "Сначала забери её с работы, а потом уже можно укладывать спать.",
            reply_markup=main_menu_keyboard()
        )
        return

    degrade_pet(user)
    pet.avatar_key = "sleep"
    from datetime import datetime, timezone
    pet.last_sleep_start = datetime.now(timezone.utc).isoformat()
    touch_pet(user)
    users_repo.save_user(user)

    await message.answer(
        "Выдра уютно устроилась спать. Постарайся и сам(а) лечь вовремя 😴",
        reply_markup=main_menu_keyboard()
    )


async def handle_feed(message: Message) -> None:
    user = await get_or_ask_start(message)
    if not user:
        return

    pet = user.pet
    
    # Проверяем, не спит ли выдра
    if pet.avatar_key == "sleep" or pet.last_sleep_start is not None:
        await message.answer(
            "🦦 Выдра сейчас спит и не может есть!\n\n"
            "Сначала разбуди её, а потом уже можно кормить.",
            reply_markup=main_menu_keyboard()
        )
        return

    degrade_pet(user)
    pet.hunger = min(100, pet.hunger + 25)
    pet.happiness = min(100, pet.happiness + 5)
    touch_pet(user)
    users_repo.save_user(user)
    stats_repo.inc_feed(user.user_id)

    meal_type = "завтрак" if "завтрак" in message.text else "обед" if "обед" in message.text else "ужин"
    await message.answer(
        f"Выдра вкусно поела {meal_type} вместе с тобой 🍽️\n"
        f"Сытость: {pet.hunger}/100, Счастье: {pet.happiness}/100",
        reply_markup=main_menu_keyboard()
    )


async def cmd_lunch_together(message: Message) -> None:
    user = await get_or_ask_start(message)
    if not user:
        return

    room = social_rooms.join("lunch_default", "lunch", message.from_user.id)
    await message.answer(
        "Ты и твоя выдра присоединились к совместному обеду.\n"
        f"Сейчас за виртуальным столом: {len(room.users)} выдр(ы).\n"
        "Можно представить, что вы обедаете вместе и поддерживаете друг друга 🍽️🦦"
    )


async def handle_water(message: Message) -> None:
    user = await get_or_ask_start(message)
    if not user:
        return

    pet = user.pet
    
    # Проверяем, не спит ли выдра
    if pet.avatar_key == "sleep" or pet.last_sleep_start is not None:
        await message.answer(
            "🦦 Выдра сейчас спит и не может пить!\n\n"
            "Сначала разбуди её, а потом уже можно дать воды.",
            reply_markup=main_menu_keyboard()
        )
        return

    degrade_pet(user)
    pet.thirst = min(100, pet.thirst + 25)
    pet.happiness = min(100, pet.happiness + 3)
    touch_pet(user)
    users_repo.save_user(user)
    stats_repo.inc_water(user.user_id)

    await message.answer(
        f"Выдра сделала глоток воды. Пойдём и ты выпьешь стаканчик воды 💧\n"
        f"Вода: {pet.thirst}/100, Счастье: {pet.happiness}/100",
        reply_markup=main_menu_keyboard()
    )


async def handle_work_start(message: Message) -> None:
    user = await get_or_ask_start(message)
    if not user:
        return

    degrade_pet(user)
    pet = user.pet
    if pet.at_work:
        await message.answer("Выдра уже на работе.", reply_markup=main_menu_keyboard())
        return
    
    # Проверяем, не спит ли выдра
    if pet.avatar_key == "sleep" or pet.last_sleep_start is not None:
        await message.answer(
            "🦦 Выдра сейчас спит и не может идти на работу!\n\n"
            "Сначала разбуди её, а потом уже можно отправлять на работу.",
            reply_markup=main_menu_keyboard()
        )
        return

    # Проверяем лимит работы (10 часов в сутки)
    from datetime import datetime, timezone, date
    from zoneinfo import ZoneInfo
    
    try:
        tz = ZoneInfo(user.settings.timezone)
    except Exception:
        tz = ZoneInfo("Asia/Vladivostok")
    
    today = date.today().isoformat()
    worked_hours_today = user.work_hours_by_date.get(today, 0.0)
    
    if worked_hours_today >= 10.0:
        await message.answer(
            "🦦 Выдра уже отработала 10 часов сегодня! Это максимальная норма работы в сутки. "
            "Давай дадим ей отдохнуть и вернёмся завтра 💼",
            reply_markup=main_menu_keyboard()
        )
        return

    pet.at_work = True
    touch_pet(user)
    users_repo.save_user(user)
    stats_repo.inc_work(user.user_id)
    pet.last_work_start = datetime.now(timezone.utc).isoformat()
    users_repo.save_user(user)
    
    remaining_hours = 10.0 - worked_hours_today
    await message.answer(
        f"Выдра отправилась на работу. Ты тоже можешь заняться делами 💼\n"
        f"Осталось отработать сегодня: {remaining_hours:.1f} часов\n"
        f"Когда закончишь, нажми 'Забрать с работы', чтобы выдра заработала монеты!",
        reply_markup=main_menu_keyboard()
    )


async def cmd_work_together(message: Message) -> None:
    user = await get_or_ask_start(message)
    if not user:
        return

    room = social_rooms.join("work_default", "work", message.from_user.id)
    await message.answer(
        "Ты и твоя выдра присоединились к совместной работе.\n"
        f"Сейчас в комнате: {len(room.users)} выдр(ы).\n"
        "Представь, что вы все работаете вместе за одним столом 💼🦦"
    )


async def handle_work_end(message: Message) -> None:
    user = await get_or_ask_start(message)
    if not user:
        return

    pet = user.pet
    
    # Проверяем, не спит ли выдра
    if pet.avatar_key == "sleep" or pet.last_sleep_start is not None:
        await message.answer(
            "🦦 Выдра сейчас спит и не может быть на работе!\n\n"
            "Сначала разбуди её.",
            reply_markup=main_menu_keyboard()
        )
        return
    
    if not pet.at_work:
        await message.answer("Выдра сейчас не на работе.", reply_markup=main_menu_keyboard())
        return

    degrade_pet(user)

    from datetime import datetime, timezone, date
    from zoneinfo import ZoneInfo
    
    try:
        tz = ZoneInfo(user.settings.timezone)
    except Exception:
        tz = ZoneInfo("Asia/Vladivostok")
    
    today = date.today().isoformat()
    
    # Вычисляем отработанные часы
    if not pet.last_work_start:
        await message.answer("Ошибка: не найдено время начала работы.", reply_markup=main_menu_keyboard())
        return
    
    try:
        work_start = datetime.fromisoformat(pet.last_work_start)
        work_end = datetime.now(timezone.utc)
        work_duration_hours = (work_end - work_start).total_seconds() / 3600.0
        
        # Получаем уже отработанные часы за сегодня
        worked_hours_today = user.work_hours_by_date.get(today, 0.0)
        
        # Ограничиваем работу до 10 часов в сутки
        max_workable_hours = 10.0 - worked_hours_today
        actual_work_hours = min(work_duration_hours, max_workable_hours)
        
        # Обновляем счетчик отработанных часов
        user.work_hours_by_date[today] = worked_hours_today + actual_work_hours
        
        # Почасовая оплата: 5 монет за час работы (улучшенная экономика)
        # Начисляем точно за отработанные часы с математическим округлением
        hourly_rate = 5
        if actual_work_hours > 0:
            # Точное начисление: округляем по математическим правилам
            # 0.1 часа = 0.5 монеты → 1 монета (округление)
            # 0.2 часа = 1.0 монета → 1 монета
            # 0.3 часа = 1.5 монеты → 2 монеты
            # 1 час = 5 монет
            earned = round(actual_work_hours * hourly_rate)
            # Минимум 1 монета только если проработала больше 1 минуты (0.017 часа)
            if earned == 0 and actual_work_hours >= 0.017:
                earned = 1
            elif earned == 0:
                earned = 0  # Если проработала меньше минуты, не начисляем
        else:
            earned = 0
        
        pet.at_work = False
        pet.money += earned
        pet.happiness = min(100, pet.happiness + 5)
        pet.last_work_start = None
        touch_pet(user)
        users_repo.save_user(user)
        
        total_worked_today = user.work_hours_by_date[today]
        remaining_hours = 10.0 - total_worked_today
        
        # Форматируем время работы
        hours_int = int(actual_work_hours)
        minutes_int = int((actual_work_hours - hours_int) * 60)
        if hours_int > 0:
            time_str = f"{hours_int}ч {minutes_int}м"
        else:
            time_str = f"{minutes_int}м"
        
        message_text = (
            f"Выдра вернулась с работы и заработала {earned} монет! 💰\n"
            f"Отработано: {time_str} ({actual_work_hours:.2f} часов)\n"
            f"Оплата: {earned} монет (5 монет/час)\n"
            f"Всего отработано сегодня: {total_worked_today:.2f} / 10 часов\n"
            f"Всего монет: {pet.money}\n"
            f"Счастье: {pet.happiness}/100"
        )
        
        if remaining_hours > 0:
            message_text += f"\n\nОсталось отработать сегодня: {remaining_hours:.1f} часов"
        else:
            message_text += "\n\nВыдра отработала максимальную норму на сегодня! 🎉"
        
        message_text += "\n\nМожешь потратить монеты на хобби командой /buy_hobby"
        
        await message.answer(message_text, reply_markup=main_menu_keyboard())
        
    except Exception as e:
        await message.answer(f"Ошибка при расчете работы: {e}", reply_markup=main_menu_keyboard())
        pet.at_work = False
        pet.last_work_start = None
        users_repo.save_user(user)


def get_hobby_description(hobby_id: str, hobby_title: str) -> str:
    """Возвращает описание хобби для сообщения после покупки"""
    descriptions = {
        "running": "Выдра теперь в спортивной форме и с новыми кроссовками готова покорять беговые дорожки! 🏃",
        "swimming": "Выдра теперь в стильном купальнике и с очками для плавания готова покорять водные просторы! 🏊",
        "volleyball": "Выдра теперь в спортивной форме и с волейбольным мячом готова покорять волейбольные площадки! 🏐",
        "basketball": "Выдра теперь в баскетбольной форме и с баскетбольным мячом готова покорять баскетбольные корты! 🏀",
        "football": "Выдра теперь в футбольной форме и с футбольным мячом готова покорять футбольные поля! ⚽",
        "yoga": "Выдра теперь в удобной одежде для йоги и с ковриком готова покорять мир гармонии и спокойствия! 🧘",
        "cycling": "Выдра теперь в велосипедной форме и с новым велосипедом готова покорять велосипедные дорожки! 🚴",
        "gym": "Выдра теперь в спортивной форме и с перчатками готова покорять тренажерные залы! 💪",
        "tennis": "Выдра теперь в красивой форме и с новой ракеткой и теннисным мячиком готова покорять теннисные корты! 🎾",
        "badminton": "Выдра теперь в спортивной форме и с ракеткой для бадминтона готова покорять бадминтонные корты! 🏸",
        "drawing": "Выдра теперь с набором кистей и красок готова создавать настоящие произведения искусства! 🎨",
        "writing": "Выдра теперь с красивой ручкой и блокнотом готова писать увлекательные рассказы! ✍️",
        "music": "Выдра теперь с музыкальным инструментом готова создавать прекрасную музыку! 🎵",
        "handicraft": "Выдра теперь с набором для рукоделия готова создавать красивые поделки своими лапками! 🧵",
        "photography": "Выдра теперь с профессиональной камерой готова запечатлевать прекрасные моменты! 📸",
        "cooking": "Выдра теперь с поварским колпаком и фартуком готова готовить вкуснейшие блюда! 👨‍🍳",
        "museum": "Выдра теперь с блокнотом для заметок готова изучать историю и искусство в музеях! 🏛️",
        "cinema": "Выдра теперь с попкорном и билетом готова наслаждаться новыми фильмами в кинотеатре! 🎬",
        "exhibition": "Выдра теперь с блокнотом готова изучать произведения искусства на выставках! 🖼️",
        "theater": "Выдра теперь в нарядной одежде и с билетом готова наслаждаться театральными постановками! 🎭",
        "concert": "Выдра теперь в нарядной одежде и с билетом готова наслаждаться живой музыкой на концертах! 🎤",
        "opera": "Выдра теперь в элегантной одежде и с билетом готова наслаждаться оперными постановками! 🎼",
    }
    return descriptions.get(hobby_id, f"Выдра теперь готова заниматься {hobby_title.lower()}! 🎉")


def hobby_selection_keyboard(available_hobbies: list) -> ReplyKeyboardMarkup:
    """Создает клавиатуру для выбора хобби"""
    keyboard = []
    
    # Добавляем базовое хобби первым
    keyboard.append([KeyboardButton(text="🆓 Прогулка по парку")])
    
    # Группируем купленные хобби по 2 в ряд
    for i in range(0, len(available_hobbies), 2):
        row = []
        for j in range(2):
            if i + j < len(available_hobbies):
                hobby = available_hobbies[i + j]
                row.append(KeyboardButton(text=f"🎨 {hobby.title}"))
        keyboard.append(row)
    
    # Добавляем кнопку "Назад" в конец
    keyboard.append([KeyboardButton(text="Назад в меню")])
    
    return ReplyKeyboardMarkup(
        keyboard=keyboard,
        resize_keyboard=True,
    )


def buy_hobby_keyboard(locked_hobbies: list, pet_money: int) -> ReplyKeyboardMarkup:
    """Создает клавиатуру с доступными хобби для покупки"""
    keyboard = []
    
    # Группируем хобби по 2 в ряд
    for i in range(0, len(locked_hobbies), 2):
        row = []
        for j in range(2):
            if i + j < len(locked_hobbies):
                hobby = locked_hobbies[i + j]
                # Формат: "Название (цена 💰)"
                button_text = f"{hobby.title} ({hobby.price}💰)"
                row.append(KeyboardButton(text=button_text))
        keyboard.append(row)
    
    # Добавляем кнопку "Назад" в конец
    keyboard.append([KeyboardButton(text="Назад в меню")])
    
    return ReplyKeyboardMarkup(
        keyboard=keyboard,
        resize_keyboard=True,
    )


async def handle_buy_hobby_menu(message: Message) -> None:
    """Показывает меню покупки хобби с кнопками"""
    user = await get_or_ask_start(message)
    if not user:
        return
    
    pet = user.pet
    
    # Проверяем, не спит ли выдра
    if pet.avatar_key == "sleep" or pet.last_sleep_start is not None:
        await message.answer(
            "🦦 Выдра сейчас спит и не может покупать хобби!\n\n"
            "Сначала разбуди её, а потом уже можно покупать хобби.",
            reply_markup=main_menu_keyboard()
        )
        return
    hobbies = hobbies_repo.get_all()
    
    # Базовое хобби "Прогулка по парку" всегда бесплатно и не продается
    BASE_HOBBY_ID = "walk"
    
    # Получаем только недоступные (некупленные) хобби, исключая базовое
    locked = [
        h for h in hobbies.values() 
        if h.id not in pet.unlocked_hobbies and h.id != BASE_HOBBY_ID
    ]
    
    # Если хобби вообще не добавлены администратором
    if not hobbies:
        await message.answer(
            "📋 Хобби пока не добавлены в магазин.\n\n"
            "Администратор скоро добавит новые хобби для покупки!\n\n"
            "Пока выдра может бесплатно гулять по парку через кнопку 'Хобби / тренировка'.",
            reply_markup=main_menu_keyboard()
        )
        return
    
    # Если все хобби (кроме базового) уже куплены
    if not locked:
        await message.answer(
            "🎉 Поздравляем! Все хобби уже куплены!\n\n"
            "Выдра может заниматься любым из них через кнопку 'Хобби / тренировка'.",
            reply_markup=main_menu_keyboard()
        )
        return
    
    # Сортируем по цене для удобства
    locked_sorted = sorted(locked, key=lambda h: h.price)
    
    message_text = (
        f"🛒 Магазин хобби\n\n"
        f"💰 У выдры сейчас: {pet.money} монет\n\n"
        f"📋 Доступные хобби для покупки ({len(locked_sorted)}):\n\n"
    )
    
    # Показываем список с индикаторами доступности
    for hobby in locked_sorted:
        can_afford = "✅" if pet.money >= hobby.price else "❌"
        message_text += f"{can_afford} {hobby.title} — {hobby.price} монет\n"
    
    message_text += "\n💡 Нажми на кнопку с хобби, чтобы купить его!"
    message_text += "\n\n🆓 Базовое хобби 'Прогулка по парку' всегда доступно бесплатно!"
    
    await message.answer(
        message_text,
        reply_markup=buy_hobby_keyboard(locked_sorted, pet.money)
    )


async def handle_back_to_menu(message: Message) -> None:
    """Возвращает пользователя в главное меню"""
    user = users_repo.get_user(message.from_user.id)
    if user is None:
        await message.answer("Сначала нажми /start и создай свою выдру 🦦")
        return
    
    await message.answer(
        "🏠 Главное меню\n\n"
        "Используй кнопки ниже для взаимодействия с выдрой!",
        reply_markup=main_menu_keyboard()
    )


async def handle_buy_hobby_button(message: Message) -> None:
    """Обрабатывает покупку хобби через кнопку"""
    user = await get_or_ask_start(message)
    if not user:
        return
    
    # Парсим текст кнопки: "Название (цена💰)"
    button_text = message.text
    if not button_text or "(" not in button_text:
        await message.answer("Ошибка при обработке покупки.", reply_markup=main_menu_keyboard())
        return
    
    # Извлекаем название хобби (до скобки)
    hobby_title = button_text.split(" (")[0].strip()
    
    degrade_pet(user)
    pet = user.pet
    hobbies = hobbies_repo.get_all()
    
    # Ищем хобби по названию
    hobby = None
    for h in hobbies.values():
        if h.title == hobby_title:
            hobby = h
            break
    
    if not hobby:
        await message.answer(
            f"Хобби '{hobby_title}' не найдено.",
            reply_markup=main_menu_keyboard()
        )
        return
    
    # Проверяем, не куплено ли уже
    if hobby.id in pet.unlocked_hobbies:
        await message.answer(
            f"Хобби '{hobby.title}' уже куплено! 🎉\n\n"
            f"Выдра может заниматься им через кнопку 'Хобби / тренировка'.",
            reply_markup=main_menu_keyboard()
        )
        return
    
    # Проверяем баланс
    if pet.money < hobby.price:
        await message.answer(
            f"❌ Недостаточно монет!\n\n"
            f"Нужно: {hobby.price} монет\n"
            f"У выдры сейчас: {pet.money} монет\n\n"
            f"💡 Отправь выдру на работу, чтобы заработать монеты!",
            reply_markup=main_menu_keyboard()
        )
        return
    
    # Покупаем хобби
    pet.money -= hobby.price
    pet.unlocked_hobbies.append(hobby.id)
    pet.happiness = min(100, pet.happiness + 15)
    touch_pet(user)
    users_repo.save_user(user)
    
    # Получаем описание хобби
    hobby_description = get_hobby_description(hobby.id, hobby.title)
    
    await message.answer(
        f"🎉 Хобби '{hobby.title}' успешно куплено!\n\n"
        f"{hobby_description}\n\n"
        f"💰 Осталось монет: {pet.money}\n"
        f"😊 Счастье выдры: {pet.happiness}/100\n\n"
        f"Теперь выдра может заниматься этим хобби через кнопку 'Хобби / тренировка'!",
        reply_markup=main_menu_keyboard()
    )


async def handle_hobby(message: Message) -> None:
    """Показывает меню выбора хобби"""
    user = await get_or_ask_start(message)
    if not user:
        return

    pet = user.pet
    
    # Проверяем, не спит ли выдра
    if pet.avatar_key == "sleep" or pet.last_sleep_start is not None:
        await message.answer(
            "🦦 Выдра сейчас спит и не может заниматься хобби!\n\n"
            "Сначала разбуди её, а потом уже можно заниматься хобби.",
            reply_markup=main_menu_keyboard()
        )
        return
    
    # Проверяем, не на работе ли выдра
    if pet.at_work:
        await message.answer(
            "🦦 Выдра сейчас на работе и не может заниматься хобби!\n\n"
            "Сначала забери её с работы, а потом уже можно заниматься хобби.",
            reply_markup=main_menu_keyboard()
        )
        return
    
    hobbies = hobbies_repo.get_all()

    # Базовое хобби "Прогулка по парку" всегда бесплатно
    BASE_HOBBY_ID = "walk"
    
    # Получаем купленные хобби (исключаем базовое, так как оно не покупается)
    available = [h for h in hobbies.values() if h.id in pet.unlocked_hobbies]
    
    # Если нет купленных хобби, сразу используем базовое
    if not available:
        degrade_pet(user)
        pet.happiness = min(100, pet.happiness + 10)
        pet.avatar_key = "hobby"
        touch_pet(user)
        users_repo.save_user(user)
        stats_repo.inc_hobby(user.user_id)
        
        await message.answer(
            f"🦦 Твоя выдра пошла прогуляться по парку. "
            f"Пока она наслаждается свежим воздухом, ты тоже можешь заниматься своими делами, "
            f"но не забывай кормить её и вовремя уложить спать! 🌳\n\n"
            f"Счастье выдры: {pet.happiness}/100\n\n"
            f"💡 Совет: зарабатывай монеты на работе, чтобы купить выдре другие хобби! "
            f"Используй кнопку 'Купить хобби' для покупки.",
            reply_markup=main_menu_keyboard()
        )
        return
    
    # Если есть купленные хобби, показываем меню выбора
    message_text = (
        f"🎨 Выбери, каким хобби заняться выдре:\n\n"
        f"💰 У выдры сейчас: {pet.money} монет\n"
        f"😊 Счастье: {pet.happiness}/100\n\n"
        f"Доступно хобби: {len(available) + 1} (включая бесплатную прогулку)"
    )
    
    await message.answer(
        message_text,
        reply_markup=hobby_selection_keyboard(available)
    )


async def handle_hobby_selection(message: Message) -> None:
    """Обрабатывает выбор конкретного хобби"""
    user = await get_or_ask_start(message)
    if not user:
        return
    
    pet = user.pet
    
    # Проверяем, не спит ли выдра
    if pet.avatar_key == "sleep" or pet.last_sleep_start is not None:
        await message.answer(
            "🦦 Выдра сейчас спит и не может заниматься хобби!\n\n"
            "Сначала разбуди её, а потом уже можно заниматься хобби.",
            reply_markup=main_menu_keyboard()
        )
        return
    
    # Проверяем, не на работе ли выдра
    if pet.at_work:
        await message.answer(
            "🦦 Выдра сейчас на работе и не может заниматься хобби!\n\n"
            "Сначала забери её с работы, а потом уже можно заниматься хобби.",
            reply_markup=main_menu_keyboard()
        )
        return
    
    degrade_pet(user)
    hobbies = hobbies_repo.get_all()
    
    from datetime import datetime, timezone, date
    today = date.today().isoformat()
    
    button_text = message.text
    
    # Обработка базового хобби
    if button_text == "🆓 Прогулка по парку":
        walk_hobby = hobbies.get("walk")
        if not walk_hobby:
            await message.answer("Ошибка при загрузке хобби.", reply_markup=main_menu_keyboard())
            return
        
        # Рассчитываем эффективность и получаем случайное событие
        happiness, recovery, energy_cost = get_hobby_effectiveness(walk_hobby)
        event_type, emoji, event_text, happiness_mod = get_random_event(walk_hobby.hobby_type)
        
        # Получаем или создаём запись о мастерстве
        if walk_hobby.id not in pet.hobby_mastery:
            from bot.core.models import HobbyMastery
            pet.hobby_mastery[walk_hobby.id] = HobbyMastery(hobby_id=walk_hobby.id)
        
        mastery = pet.hobby_mastery[walk_hobby.id]
        mastery.total_sessions += 1
        update_hobby_streak(mastery, today)
        
        # Применяем множители за мастерство и стрик
        mastery_level = calculate_mastery_level(mastery.total_sessions)
        happiness_mult, recovery_mult = get_mastery_bonus(mastery_level)
        streak_mult = get_streak_bonus(mastery.streak)
        overuse_mult = get_overuse_penalty(mastery.streak)
        
        final_multiplier = happiness_mult * streak_mult * overuse_mult
        
        final_happiness = int(happiness * final_multiplier) + happiness_mod
        final_recovery = int(recovery * recovery_mult * streak_mult * overuse_mult)
        final_energy_cost = max(1, int(energy_cost * 0.7))  # Энергия расходуется меньше при прогулке
        
        # Применяем эффекты
        pet.happiness = min(100, pet.happiness + final_happiness)
        pet.energy = max(0, pet.energy - final_energy_cost)
        pet.fatigue = max(0, pet.fatigue - final_recovery)
        pet.avatar_key = "hobby"
        
        touch_pet(user)
        users_repo.save_user(user)
        stats_repo.inc_hobby(user.user_id)
        
        result_text = format_hobby_session_result(
            walk_hobby,
            final_happiness,
            final_recovery,
            final_energy_cost,
            emoji,
            event_text,
            mastery_level,
            mastery.streak,
        )
        
        await message.answer(result_text, reply_markup=main_menu_keyboard())
        return
    
    # Обработка купленных хобби (формат: "🎨 Название")
    if button_text.startswith("🎨 "):
        hobby_title = button_text.replace("🎨 ", "").strip()
        
        # Ищем хобби по названию
        selected_hobby = None
        for h in hobbies.values():
            if h.title == hobby_title and h.id in pet.unlocked_hobbies:
                selected_hobby = h
                break
        
        if not selected_hobby:
            await message.answer(
                "Хобби не найдено или не куплено.",
                reply_markup=main_menu_keyboard()
            )
            return
        
        # Рассчитываем эффективность и получаем случайное событие
        happiness, recovery, energy_cost = get_hobby_effectiveness(selected_hobby)
        event_type, emoji, event_text, happiness_mod = get_random_event(selected_hobby.hobby_type)
        
        # Получаем или создаём запись о мастерстве
        if selected_hobby.id not in pet.hobby_mastery:
            from bot.core.models import HobbyMastery
            pet.hobby_mastery[selected_hobby.id] = HobbyMastery(hobby_id=selected_hobby.id)
        
        mastery = pet.hobby_mastery[selected_hobby.id]
        mastery.total_sessions += 1
        update_hobby_streak(mastery, today)
        
        # Применяем множители за мастерство и стрик
        mastery_level = calculate_mastery_level(mastery.total_sessions)
        happiness_mult, recovery_mult = get_mastery_bonus(mastery_level)
        streak_mult = get_streak_bonus(mastery.streak)
        overuse_mult = get_overuse_penalty(mastery.streak)
        
        final_multiplier = happiness_mult * streak_mult * overuse_mult
        
        final_happiness = int(happiness * final_multiplier) + happiness_mod
        final_recovery = int(recovery * recovery_mult * streak_mult * overuse_mult)
        
        # Применяем эффекты
        pet.happiness = min(100, pet.happiness + final_happiness)
        pet.energy = max(0, pet.energy - energy_cost)
        pet.fatigue = max(0, pet.fatigue - final_recovery)
        pet.avatar_key = selected_hobby.avatar_key
        
        touch_pet(user)
        users_repo.save_user(user)
        stats_repo.inc_hobby(user.user_id)
        
        result_text = format_hobby_session_result(
            selected_hobby,
            final_happiness,
            final_recovery,
            energy_cost,
            emoji,
            event_text,
            mastery_level,
            mastery.streak,
        )
        
        await message.answer(result_text, reply_markup=main_menu_keyboard())
        return
    
    await message.answer("Неизвестное действие.", reply_markup=main_menu_keyboard())


async def cmd_buy_hobby(message: Message) -> None:
    user = await get_or_ask_start(message)
    if not user:
        return

    parts = message.text.split(maxsplit=1) if message.text else []
    if len(parts) < 2:
        await message.answer("Укажи id хобби: /buy_hobby id")
        return

    hid = parts[1].strip()
    hobbies = hobbies_repo.get_all()
    hobby = hobbies.get(hid)
    if not hobby:
        await message.answer("Хобби с таким id не найдено.")
        return

    degrade_pet(user)
    pet = user.pet
    if hid in pet.unlocked_hobbies:
        await message.answer("Это хобби уже разблокировано.")
        return

    if pet.money < hobby.price:
        await message.answer(
            f"Недостаточно монет. Нужно {hobby.price}, у выдры сейчас {pet.money}."
        )
        return

    pet.money -= hobby.price
    pet.unlocked_hobbies.append(hid)
    pet.happiness = min(100, pet.happiness + 15)
    touch_pet(user)
    users_repo.save_user(user)
    await message.answer(
        f"Хобби '{hobby.title}' куплено! 🎉\n"
        f"Осталось монет: {pet.money}\n"
        f"Счастье выдры: {pet.happiness}/100\n\n"
        f"Теперь выдра может заниматься этим хобби через кнопку 'Хобби / тренировка'!"
    )


# ========== НОВОЕ МЕНЮ ==========

async def handle_main_menu(message: Message) -> None:
    """Обработка главного меню"""
    user = users_repo.get_user(message.from_user.id)
    if user is None:
        await message.answer("Сначала нажми /start и создай свою выдру 🦦")
        return
    
    from datetime import datetime, timezone
    user.last_main_menu_return = datetime.now(timezone.utc).isoformat()
    users_repo.save_user(user)
    
    text = message.text
    if text == "Действия с выдрой":
        await message.answer(
            "🦦 Действия с выдрой\n\n"
            "Здесь ты можешь взаимодействовать со своей выдрой:\n"
            "• Укладывать и будить выдру\n"
            "• Кормить и поить\n"
            "• Отправлять на работу\n"
            "• Заниматься хобби и тренировками\n\n"
            "Выбери действие из меню ниже:",
            reply_markup=actions_menu_keyboard()
        )
    elif text == "Настройки":
        await message.answer(
            "⚙️ Настройки\n\n"
            "Здесь ты можешь просмотреть и изменить параметры бота.",
            reply_markup=settings_menu_keyboard()
        )
    elif text == "Статистика":
        # Создаем FSM context для передачи в handle_weekly_stats
        from aiogram.fsm.context import FSMContext
        state = FSMContext(storage=dp.storage, key=dp.storage.resolve_key(message.chat.id, message.from_user.id))
        await handle_weekly_stats(message, state)
    elif text == "Совет дня":
        await handle_daily_advice(message)
    elif text == "👥 Друзья":
        await handle_friends_menu(message)
    elif text == "Назад в главное меню":
        await message.answer(
            "🏠 Главное меню\n\nВыбери действие:",
            reply_markup=main_menu_keyboard()
        )


async def handle_actions_menu(message: Message) -> None:
    """Меню действий с выдрой - все старые действия + новые"""
    user = users_repo.get_user(message.from_user.id)
    if user is None:
        await message.answer("Сначала нажми /start и создай свою выдру 🦦")
        return
    
    text = message.text
    
    # Действия с выдрой (геймификация)
    elif text == "Разбудить питомца":
        await handle_wake_pet(message)
        return
    elif text == "Уложить спать":
        await handle_sleep_pet(message)
        return
    elif text in ["Накормить (завтрак)", "Накормить (обед)", "Накормить (ужин)"]:
        await handle_feed(message)
        return
    elif text == "Дать воды":
        await handle_water(message)
        return
    elif text == "Отправить на работу":
        await handle_work_start(message)
        return
    elif text == "Забрать с работы":
        await handle_work_end(message)
        return
    elif text == "Хобби / тренировка":
        await handle_hobby(message)
        return
    elif text == "Купить хобби":
        await handle_buy_hobby_menu(message)
        return
    
    # Если действие не распознано, показываем меню
    await message.answer(
        "Выбери действие из меню:",
        reply_markup=actions_menu_keyboard()
    )


async def handle_go_to_sleep(message: Message) -> None:
    """Обработка 'Ложусь спать'"""
    user = users_repo.get_user(message.from_user.id)
    if user is None:
        await message.answer("Сначала нажми /start и создай свою выдру 🦦")
        return
    
    from datetime import datetime, timezone
    today_stats = get_today_stats(user)
    
    # Записываем время засыпания
    today_stats.sleep_time = datetime.now(timezone.utc).isoformat()
    user.pet.last_sleep_start = today_stats.sleep_time
    user.pet.avatar_key = "sleep"
    
    users_repo.save_user(user)
    
    # Выдра тоже ложится спать вместе с пользователем
    today_stats.pet_sleep_minutes = 0  # Сброс, начнем считать с момента пробуждения
    
    users_repo.save_user(user)
    
    await message.answer(
        "😴 Отлично! Записал время, когда ты лёг(ла) спать.\n\n"
        "Выдра тоже устроилась поудобнее и легла спать вместе с тобой. Утром нажми 'Проснулся', "
        "и я посчитаю, сколько вы оба спали.\n\n"
        "Спокойной ночи! 🌙",
        reply_markup=main_menu_keyboard()  # Автоматически возвращаем в главное меню
    )


async def handle_wake_up(message: Message) -> None:
    """Обработка 'Проснулся'"""
    user = users_repo.get_user(message.from_user.id)
    if user is None:
        await message.answer("Сначала нажми /start и создай свою выдру 🦦")
        return
    
    from datetime import datetime, timezone
    today_stats = get_today_stats(user)
    
    # Записываем время пробуждения
    wake_time = datetime.now(timezone.utc)
    today_stats.wake_time = wake_time.isoformat()
    
    # Вычисляем продолжительность сна пользователя
    sleep_duration_minutes = 0
    if today_stats.sleep_time:
        try:
            sleep_start = datetime.fromisoformat(today_stats.sleep_time)
            sleep_duration = (wake_time - sleep_start).total_seconds() / 60
            if sleep_duration > 0:
                sleep_duration_minutes = int(sleep_duration)
                today_stats.sleep_minutes = sleep_duration_minutes
                # Выдра спала столько же, сколько пользователь
                today_stats.pet_sleep_minutes = sleep_duration_minutes
                stats_repo.add_sleep_minutes(user.user_id, sleep_duration_minutes)
        except Exception:
            pass
    
    user.pet.avatar_key = "awake"
    user.pet.last_sleep_start = None
    user.pet.energy = min(100, user.pet.energy + 15)
    user.pet.happiness = min(100, user.pet.happiness + 5)
    
    users_repo.save_user(user)
    
    # Форматируем сообщение
    hours = sleep_duration_minutes // 60
    minutes = sleep_duration_minutes % 60
    
    if sleep_duration_minutes > 0:
        sleep_msg = f"Ты спал(а) {hours}ч {minutes}м, выдра спала столько же."
        if hours >= 7:
            sleep_msg += " Отличный сон! 👍"
        elif hours >= 6:
            sleep_msg += " Неплохо, но можно больше."
        else:
            sleep_msg += " Мало для полноценного отдыха."
    else:
        sleep_msg = "Не удалось посчитать сон — возможно, ты забыл(а) нажать 'Ложусь спать' вчера."
    
    await message.answer(
        f"🌅 Доброе утро! {sleep_msg}\n\n"
        f"Выдра проснулась вместе с тобой и готова к новому дню! 🦦\n\n"
        f"Не забудь выпить воды и дать воды выдре!",
        reply_markup=main_menu_keyboard()  # Автоматически возвращаем в главное меню
    )


async def handle_settings_menu(message: Message, state: FSMContext = None) -> None:
    """Меню настроек"""
    user = users_repo.get_user(message.from_user.id)
    if user is None:
        await message.answer("Сначала нажми /start и создай свою выдру 🦦")
        return
    
    text = message.text
    if text == "Просмотреть настройки":
        await message.answer(
            f"📋 Твои текущие настройки:\n\n"
            f"Имя выдры: {user.pet.name}\n"
            f"Часовой пояс: {user.settings.timezone}\n"
            f"Возраст выдры: {user.pet.age_days} дней\n",
            reply_markup=settings_menu_keyboard()
        )
    elif text == "Изменить часовой пояс":
        await message.answer(
            "Используй команду /set_timezone Region/City\n"
            "Например: /set_timezone Asia/Vladivostok",
            reply_markup=settings_menu_keyboard()
        )
    elif text == "Изменить имя выдры":
        await message.answer(
            "Используй команду /set_name НовоеИмя\n"
            "Например: /set_name Выдра",
            reply_markup=settings_menu_keyboard()
        )
    elif text == "Настроить норму воды":
        # Показываем меню настройки нормы воды
        await message.answer(
            "💧 Настройка нормы воды\n\n"
            "Выбери один из вариантов или введи свою норму:",
            reply_markup=water_norm_setup_keyboard()
        )
        return
    elif text == "Настроить объем стакана":
        # Используем FSM для ввода объема стакана
        if state is None:
            # Если state не передан, создаем его
            from aiogram.fsm.context import FSMContext
            state = FSMContext(storage=dp.storage, key=dp.storage.resolve_key(message.chat.id, message.from_user.id))
        await state.set_state(WaterSettingsFSM.waiting_for_glass_volume)
        await message.answer(
            "💧 Настройка объема стакана\n\n"
            "Напиши объем стакана в миллилитрах.\n"
            "Например: 250 или 300\n\n"
            "Или просто напиши число без единиц измерения (например, 250)",
            reply_markup=settings_menu_keyboard()
        )
        return


async def handle_weekly_stats(message: Message, state: FSMContext = None) -> None:
    """Статистика за неделю"""
    user = users_repo.get_user(message.from_user.id)
    if user is None:
        await message.answer("Сначала нажми /start и создай свою выдру 🦦")
        return
    
    try:
        stats_text = format_weekly_stats(user)
        
        # Вычисляем среднее количество часов сна за неделю
        from datetime import date, timedelta
        today = date.today()
        week_dates = [today - timedelta(days=i) for i in range(7)]
        
        total_sleep_minutes = 0
        days_with_sleep = 0
        for day_date in week_dates:
            day_str = day_date.isoformat()
            if day_str in user.daily_stats:
                stats = user.daily_stats[day_str]
                if stats.sleep_minutes > 0:
                    total_sleep_minutes += stats.sleep_minutes
                    days_with_sleep += 1
        
        avg_sleep_hours = 0.0
        if days_with_sleep > 0:
            avg_sleep_hours = (total_sleep_minutes / days_with_sleep) / 60.0
        
        # Всегда отправляем статистику
        if not stats_text or len(stats_text.strip()) == 0:
            stats_text = "📊 Твоя статистика за последние 7 дней:\n\n📝 Данных за эту неделю пока нет.\nНачни записывать свой сон и воду через 'Действия с выдрой'!"
        
        await message.answer(
            stats_text,
            reply_markup=main_menu_keyboard()
        )
        
        # Если норма сна не установлена и есть данные о сне, спрашиваем пользователя
        if user.settings.sleep_norm_hours == 0.0 and avg_sleep_hours > 0:
            if state is None:
                from aiogram.fsm.context import FSMContext
                state = FSMContext(storage=dp.storage, key=dp.storage.resolve_key(message.chat.id, message.from_user.id))
            
            # Сохраняем среднее значение в FSM для использования в обработчике
            await state.update_data(avg_sleep_hours=avg_sleep_hours)
            await state.set_state(SleepNormFSM.waiting_for_sleep_norm_answer)
            
            await message.answer(
                f"💤 Вопрос о твоем сне:\n\n"
                f"За последнюю неделю ты спал(а) в среднем {avg_sleep_hours:.1f} часов в день.\n\n"
                f"Ты нормально высыпаешься?",
                reply_markup=ReplyKeyboardMarkup(
                    keyboard=[
                        [KeyboardButton(text="Да"), KeyboardButton(text="Нет")],
                    ],
                    resize_keyboard=True,
                )
            )
    except Exception as e:
        # В случае ошибки отправляем сообщение об ошибке
        await message.answer(
            f"❌ Произошла ошибка при формировании статистики.\n\n"
            f"Попробуй еще раз или обратись к администратору.",
            reply_markup=main_menu_keyboard()
        )
        # Логируем ошибку (в продакшене можно использовать logger)
        print(f"Error in handle_weekly_stats: {e}")


async def handle_sleep_norm_answer(message: Message, state: FSMContext) -> None:
    """Обработка ответа на вопрос о сне"""
    user = users_repo.get_user(message.from_user.id)
    if user is None:
        await state.clear()
        await message.answer("Сначала нажми /start и создай свою выдру 🦦")
        return
    
    text = message.text.strip()
    data = await state.get_data()
    avg_sleep_hours = data.get("avg_sleep_hours", 0.0)
    
    if text == "Да":
        # Пользователь нормально высыпается - сохраняем среднее значение как норму
        if avg_sleep_hours > 0:
            user.settings.sleep_norm_hours = avg_sleep_hours
            users_repo.save_user(user)
            await state.clear()
            await message.answer(
                f"💤 Отлично! Установлена норма сна: {avg_sleep_hours:.1f} часов в день.\n\n"
                f"Теперь бот будет отслеживать, соблюдаешь ли ты эту норму.",
                reply_markup=main_menu_keyboard()
            )
        else:
            await state.clear()
            await message.answer(
                "💤 Не удалось определить среднее количество часов сна.\n"
                "Попробуй еще раз через неделю, когда накопится больше данных.",
                reply_markup=main_menu_keyboard()
            )
    elif text == "Нет":
        # Пользователь не высыпается - предлагаем решение
        await state.clear()
        
        # Предложения в зависимости от среднего количества часов
        suggestions = []
        if avg_sleep_hours < 6:
            suggestions.append("• Ложись спать на 1-2 часа раньше")
            suggestions.append("• Создай регулярный режим сна")
            suggestions.append("• Избегай экранов за час до сна")
        elif avg_sleep_hours < 7:
            suggestions.append("• Ложись спать на 30-60 минут раньше")
            suggestions.append("• Установи фиксированное время отхода ко сну")
            suggestions.append("• Создай расслабляющий ритуал перед сном")
        else:
            suggestions.append("• Старайся спать 7-9 часов в день")
            suggestions.append("• Ложись и вставай в одно и то же время")
            suggestions.append("• Создай комфортные условия для сна")
        
        suggestions_text = "\n".join(suggestions)
        
        await message.answer(
            f"💤 Понятно, ты не высыпаешься.\n\n"
            f"Сейчас ты спишь в среднем {avg_sleep_hours:.1f} часов в день.\n\n"
            f"Рекомендации для улучшения сна:\n{suggestions_text}\n\n"
            f"Когда начнешь лучше высыпаться, бот сможет установить новую норму сна "
            f"при следующем просмотре статистики за неделю.",
            reply_markup=main_menu_keyboard()
        )
    else:
        # Неожиданный ответ
        await message.answer(
            "Пожалуйста, ответь 'Да' или 'Нет' на вопрос о сне.",
            reply_markup=ReplyKeyboardMarkup(
                keyboard=[
                    [KeyboardButton(text="Да"), KeyboardButton(text="Нет")],
                ],
                resize_keyboard=True,
            )
        )


async def handle_daily_advice(message: Message) -> None:
    """Совет дня"""
    user = users_repo.get_user(message.from_user.id)
    if user is None:
        await message.answer("Сначала нажми /start и создай свою выдру 🦦")
        return
    
    advice = get_advice_for_today(user)
    
    if advice is None:
        await message.answer(
            "💡 Ты уже получил(а) совет на сегодня!\n\n"
            "Советы обновляются каждый день в 00:00 по твоему местному времени. "
            "Завтра сможешь получить новый совет!",
            reply_markup=main_menu_keyboard()
        )
        users_repo.save_user(user)
        return
    
    # Сохраняем дату первого совета для расчета месячного отчета
    if user.advice_state.first_advice_date is None:
        from datetime import date
        user.advice_state.first_advice_date = date.today().isoformat()
    
    users_repo.save_user(user)
    
    await message.answer(
        f"💡 Совет дня:\n\n{advice}\n\n"
        f"Выдра надеется, что этот совет поможет тебе! 🦦",
        reply_markup=main_menu_keyboard()
    )


async def handle_water_norm_setup(message: Message) -> None:
    """Обработка настройки нормы воды"""
    user = users_repo.get_user(message.from_user.id)
    if user is None:
        await message.answer("Сначала нажми /start и создай свою выдру 🦦")
        return
    
    text = message.text
    
    if text == "Знаю свою норму":
        await message.answer(
            "💧 Отлично! Напиши свою норму воды в литрах.\n"
            "Например: 2.5 или 3",
            reply_markup=water_norm_setup_keyboard()
        )
        # Устанавливаем флаг, что пользователь вводит норму
        user.settings.water_norm_set = False  # Временно, чтобы обработать ввод
        users_repo.save_user(user)
        return
    elif text == "Не знаю, предложи норму":
        user.settings.water_norm_liters = 2.5
        user.settings.water_norm_set = True
        users_repo.save_user(user)
        await message.answer(
            f"💧 Установлена стандартная норма: 2.5 литра в день.\n\n"
            f"Ты всегда можешь изменить её в настройках!",
            reply_markup=main_menu_keyboard()
        )
        return
    elif text == "2 литра":
        user.settings.water_norm_liters = 2.0
        user.settings.water_norm_set = True
        users_repo.save_user(user)
        await message.answer(
            f"💧 Норма воды установлена: 2 литра в день.",
            reply_markup=main_menu_keyboard()
        )
        return
    elif text == "2.5 литра":
        user.settings.water_norm_liters = 2.5
        user.settings.water_norm_set = True
        users_repo.save_user(user)
        await message.answer(
            f"💧 Норма воды установлена: 2.5 литра в день.",
            reply_markup=main_menu_keyboard()
        )
        return
    elif text == "3 литра":
        user.settings.water_norm_liters = 3.0
        user.settings.water_norm_set = True
        users_repo.save_user(user)
        await message.answer(
            f"💧 Норма воды установлена: 3 литра в день.",
            reply_markup=main_menu_keyboard()
        )
        return
    elif text == "Другое":
        await message.answer(
            "💧 Напиши свою норму воды в литрах.\n"
            "Например: 2.5 или 3",
            reply_markup=water_norm_setup_keyboard()
        )
        return
    elif text == "Назад в настройки":
        await message.answer(
            "⚙️ Настройки",
            reply_markup=settings_menu_keyboard()
        )
        return
    
    # Попытка распарсить число как норму воды или объем стакана
    try:
        # Сначала пробуем как float (норма воды в литрах)
        norm = float(text.replace(",", "."))
        
        # Проверяем, может ли это быть объем стакана (целое число от 50 до 1000)
        if norm.is_integer() and 50 <= int(norm) <= 1000:
            # Это может быть объем стакана - проверяем контекст
            # Если пользователь только что нажал "Настроить объем стакана", это объем стакана
            # Иначе это может быть норма воды
            volume = int(norm)
            user.settings.glass_volume_ml = volume
            users_repo.save_user(user)
            await message.answer(
                f"💧 Объем стакана установлен: {volume}мл.",
                reply_markup=main_menu_keyboard()
            )
        elif 0.5 <= norm <= 10:  # Разумные пределы для нормы воды
            user.settings.water_norm_liters = norm
            user.settings.water_norm_set = True
            users_repo.save_user(user)
            await message.answer(
                f"💧 Норма воды установлена: {norm} литров в день.",
                reply_markup=main_menu_keyboard()
            )
        else:
            await message.answer(
                "💧 Пожалуйста, введи число от 0.5 до 10 литров для нормы воды,\n"
                "или от 50 до 1000 для объема стакана.",
                reply_markup=water_norm_setup_keyboard()
            )
    except ValueError:
        # Если это не число, возможно это настройка объема стакана с "мл"
        if "мл" in text.lower() or "ml" in text.lower():
            try:
                volume = int(text.replace("мл", "").replace("ml", "").replace(" ", "").strip())
                if 50 <= volume <= 1000:
                    user.settings.glass_volume_ml = volume
                    users_repo.save_user(user)
                    await message.answer(
                        f"💧 Объем стакана установлен: {volume}мл.",
                        reply_markup=main_menu_keyboard()
                    )
                else:
                    await message.answer(
                        "💧 Пожалуйста, введи объем от 50 до 1000 мл.",
                        reply_markup=settings_menu_keyboard()
                    )
            except ValueError:
                await message.answer(
                    "💧 Не понял. Попробуй еще раз или вернись в настройки.",
                    reply_markup=water_norm_setup_keyboard()
                )
        else:
            await message.answer(
                "💧 Не понял. Попробуй еще раз или вернись в настройки.",
                reply_markup=water_norm_setup_keyboard()
            )


async def handle_weekly_advice_answer(message: Message) -> None:
    """Обработка ответа на вопрос о соблюдении советов"""
    user = users_repo.get_user(message.from_user.id)
    if user is None:
        await message.answer("Сначала нажми /start и создай свою выдру 🦦")
        return
    
    from datetime import date
    today = date.today().isoformat()
    
    text = message.text
    if text == "Да":
        user.advice_state.weekly_answers[today] = True
        users_repo.save_user(user)
        await message.answer(
            "На этой неделе ты следовал советам, это очень приятно. Продолжай в том же духе, спасибо. 👍",
            reply_markup=main_menu_keyboard()
        )
    elif text == "Нет":
        user.advice_state.weekly_answers[today] = False
        users_repo.save_user(user)
        await message.answer(
            "На этой неделе ты не следовал моим советам. 😔\n\n"
            "Но это нормально! Каждый день — новая возможность начать заботиться о себе. "
            "Выдра верит в тебя! 🦦",
            reply_markup=main_menu_keyboard()
        )


async def cmd_hobby_recommendations(message: Message) -> None:
    """Показывает рекомендации по хобби на основе состояния выдры"""
    user = await get_or_ask_start(message)
    if not user:
        return
    
    pet = user.pet
    
    # Получаем рекомендации
    recommendations = get_hobby_recommendations(pet)
    
    if not recommendations:
        await message.answer(
            "🦦 Твоя выдра кажется, в отличной форме! "
            "Она может выбрать любое хобби по своему вкусу! 🎨",
            reply_markup=main_menu_keyboard()
        )
        return
    
    message_text = "📋 Рекомендации для твоей выдры:\n\n"
    for hobby_type, recommendation in recommendations:
        message_text += f"{recommendation}\n\n"
    
    message_text += "💡 Чтобы заняться хобби, нажми кнопку 'Хобби / тренировка' в меню действий!"
    
    await message.answer(message_text, reply_markup=main_menu_keyboard())


async def cmd_hobby_stats(message: Message) -> None:
    """Показывает статистику по хобби"""
    user = await get_or_ask_start(message)
    if not user:
        return
    
    stats_text = get_hobby_stats_summary(user.pet, hobbies_repo)
    await message.answer(stats_text, reply_markup=main_menu_keyboard())


async def cmd_hobby_help(message: Message) -> None:
    """Показывает справку по системе хобби"""
    help_text = (
        "📚 Справка по системе хобби:\n\n"
        
        "💰 **Стоимость хобби:**\n"
        "Более дорогие хобби приносят больше счастья и лучше восстанавливают от усталости!\n"
        "Цена 50₽ = 2.5x эффективность vs цена 20₽\n\n"
        
        "⭐ **Уровни мастерства (1–5 звёзд):**\n"
        "Чем больше занимаешься хобби, тем выше уровень:\n"
        "- Уровень 1: 0–2 сессии\n"
        "- Уровень 2: 3–7 сессий\n"
        "- Уровень 5: 30+ сессий\n"
        "Каждый уровень даёт +10% бонус к счастью и восстановлению!\n\n"
        
        "🔥 **Стрик (дни подряд):**\n"
        "Занимайся одним хобби несколько дней подряд и получай бонусы:\n"
        "- 7+ дней = +30% к эффективности\n\n"
        
        "⚠️ **Переутомление:**\n"
        "Если заниматься одним хобби более 3 дней подряд, эффект снижается на 10–25%\n"
        "Чередуй разные хобби для максимальной эффективности!\n\n"
        
        "🎲 **Случайные события:**\n"
        "Каждое занятие может принести случайное событие — от победы до смешной ситуации!\n\n"
        
        "💡 **Совет:** Используй /hobby_recommendations для рекомендаций!\n"
    )
    
    await message.answer(help_text, reply_markup=main_menu_keyboard())


async def cmd_work_together_hobby(message: Message) -> None:
    """Совместное хобби с друзьями (социальное)"""
    user = await get_or_ask_start(message)
    if not user:
        return
    
    pet = user.pet
    
    # Проверяем, не спит ли выдра
    if pet.avatar_key == "sleep" or pet.last_sleep_start is not None:
        await message.answer(
            "🦦 Выдра сейчас спит и не может заниматься хобби!\n\n"
            "Сначала разбуди её, а потом уже можно заниматься хобби.",
            reply_markup=main_menu_keyboard()
        )
        return
    
    degrade_pet(user)
    
    # Проверяем, не на работе ли выдра
    if pet.at_work:
        await message.answer(
            "🦦 Выдра сейчас на работе и не может развлекаться!\n\n"
            "Сначала забери её с работы.",
            reply_markup=main_menu_keyboard()
        )
        return
    
    # Используем социальную комнату для хобби (например, "art_class")
    room = social_rooms.join("hobby_together", "hobby", message.from_user.id)
    
    # Эффект зависит от числа участников
    num_participants = len(room.users)
    base_happiness = 15
    base_recovery = 120
    
    social_bonus = get_social_bonus(num_participants)
    happiness_gained = int(base_happiness * social_bonus)
    recovery_gained = int(base_recovery * social_bonus)
    
    # Случайное событие для социального хобби
    event_type, emoji, event_text, happiness_mod = get_social_hobby_event()
    
    final_happiness = happiness_gained + happiness_mod
    pet.happiness = min(100, pet.happiness + final_happiness)
    pet.fatigue = max(0, pet.fatigue - recovery_gained)
    pet.avatar_key = "hobby"
    
    touch_pet(user)
    users_repo.save_user(user)
    stats_repo.inc_hobby(user.user_id)
    
    result_text = format_social_hobby_result(
        "Совместное хобби 🎉",
        num_participants,
        final_happiness,
        recovery_gained,
        emoji,
        event_text,
    )
    
    await message.answer(result_text, reply_markup=main_menu_keyboard())


# ===== СИСТЕМА ДРУЖБЫ И СОВМЕСТНЫХ АКТИВНОСТЕЙ =====

async def handle_friends_menu(message: Message) -> None:
    """Меню друзей и совместных активностей"""
    user = await get_or_ask_start(message)
    if not user:
        return
    
    await message.answer(
        "👥 Совместный гейминг\n\n"
        "Проводи время со своими друзьями и их выдрами!\n\n"
        "💡 Как добавить друга:\n"
        "1️⃣ Нажми 🔗 Мой код дружбы\n"
        "2️⃣ Отправь свой код другу\n"
        "3️⃣ Друг нажимает ➕ Добавить друга\n"
        "4️⃣ Друг вводит твой код\n"
        "5️⃣ Готово! Вы друзья! 🎉",
        reply_markup=friends_menu_keyboard()
    )


async def cmd_my_friend_code(message: Message) -> None:
    """Показать мой код дружбы"""
    user = await get_or_ask_start(message)
    if not user:
        return
    
    friend_code = str(user.user_id)
    
    await message.answer(
        f"🔗 Твой код дружбы:\n\n"
        f"{friend_code}\n\n"
        f"Отправь этот код своему другу, "
        f"чтобы он мог добавить тебя в друзья!\n\n"
        f"Просто выдели код выше и скопируй его 📋",
        reply_markup=friends_menu_keyboard()
    )


async def cmd_add_friend_by_code(message: Message, state: FSMContext) -> None:
    """Добавить друга по коду"""
    user = await get_or_ask_start(message)
    if not user:
        return
    
    await state.set_state(FriendshipFSM.waiting_for_friend_code)
    
    await message.answer(
        "➕ Введи код дружбы друга\n\n"
        "Попроси друга отправить тебе его код "
        "(нажав на 🔗 Мой код дружбы)"
    )


async def handle_add_friend_code(message: Message, state: FSMContext) -> None:
    """Обработка введённого кода дружбы"""
    try:
        # Проверяем, что это не команда
        if message.text and message.text.startswith("/"):
            await state.clear()
            return
        
        user = await get_or_ask_start(message)
        if not user:
            await state.clear()
            return
        
        # Проверяем, что это не кнопка меню
        menu_buttons = [
        "Действия с выдрой", "👥 Друзья", "Настройки", "Статистика", "Совет дня", "Назад в главное меню",
        "Разбудить питомца", "Уложить спать", "Накормить (завтрак)", "Накормить (обед)", 
        "Накормить (ужин)", "Дать воды", "Отправить на работу", "Забрать с работы",
        "Хобби / тренировка", "Купить хобби",
        "Просмотреть настройки", "Изменить часовой пояс", "Изменить имя выдры",
        "Настроить норму воды", "Настроить объем стакана", "Знаю свою норму",
        "Не знаю, предложи норму", "2 литра", "2.5 литра", "3 литра", "Другое",
        "Назад в настройки", "Да", "Нет", "Назад в меню",
        "📋 Мои друзья", "🤝 Совместное хобби", "💼 Совместная работа",
        "🚶 Совместная прогулка", "🍽️ Совместный обед", "💪 Совместная тренировка",
        "🏆 Спортивный вызов", "🌲 Приключение", "🎁 Подарок другу",
            "🔗 Мой код дружбы", "➕ Добавить друга",
        ]
        
        if message.text in menu_buttons:
            await state.clear()
            if message.text == "Назад в главное меню":
                await message.answer("🏠 Главное меню", reply_markup=main_menu_keyboard())
            elif message.text == "👥 Друзья":
                await handle_friends_menu(message)
            return
        
        if not message.text:
            await message.answer("❌ Пожалуйста, введи код дружбы (только цифры).")
            return
        
        code = message.text.strip()
        
        # Проверяем, что это цифры (ID)
        if not code or not code.isdigit():
            await message.answer(
                "❌ Неверный код! Код должен состоять из цифр.\n"
                "Попроси друга отправить тебе его код ещё раз.\n\n"
                "Пример: 123456789"
            )
            return
        
        try:
            friend_id = int(code)
        except ValueError:
            await message.answer("❌ Ошибка при обработке кода!")
            return
        
        if friend_id == user.user_id:
            await message.answer("❌ Нельзя добавить самого себя в друзья 😅", reply_markup=friends_menu_keyboard())
            await state.clear()
            return
        
        # Проверяем, существует ли друг
        friend_user = users_repo.get_user(friend_id)
        if not friend_user:
            await message.answer(
                f"❌ Пользователь с кодом {code} не найден в боте 🤔\n"
                "Проверь код и попробуй снова.\n\n"
                "Убедись, что друг уже зарегистрирован в боте (нажал /start).",
                reply_markup=friends_menu_keyboard()
            )
            await state.clear()
            return
        
        # Проверяем, нет ли уже дружбы
        from bot.core.models import Friendship
        from dataclasses import asdict
        
        # Ищем в обе стороны в друзьях
        existing = False
        if user.friendships and friend_id in user.friendships:
            existing = True
        
        if existing:
            await message.answer(
                f"✅ Ты уже дружишь с выдрой {friend_user.pet.name}! 👥",
                reply_markup=friends_menu_keyboard()
            )
            await state.clear()
            return
        
        # Создаём дружбу в обе стороны
        now = datetime.now(timezone.utc).isoformat()
        
        new_friendship = Friendship(
            user_id_1=user.user_id,
            user_id_2=friend_id,
            friendship_level=1,
            total_sessions_together=0,
            first_met_date=now,
            last_interaction=now,
        )
        
        # Инициализируем friendships если его нет
        if not user.friendships:
            user.friendships = {}
        
        user.friendships[friend_id] = new_friendship
        users_repo.save_user(user)
        
        # Также добавляем обратную ссылку у друга
        if not friend_user.friendships:
            friend_user.friendships = {}
        
        friend_user.friendships[user.user_id] = new_friendship
        users_repo.save_user(friend_user)
        
        await message.answer(
            f"🎉 Поздравляем! Ты теперь друг выдры {friend_user.pet.name}! 👥\n\n"
            f"⭐ Уровень дружбы: ⭐☆☆☆☆☆☆☆☆☆ (1/10)\n"
            f"💕 Начните совместные активности для укрепления дружбы!\n\n"
            f"Выбери активность ниже 👇",
            reply_markup=friends_menu_keyboard()
        )
        
        await state.clear()
    except Exception as e:
        # Обработка ошибок
        await message.answer(
            f"❌ Произошла ошибка при добавлении друга.\n"
            f"Попробуй ещё раз или обратись к администратору.",
            reply_markup=friends_menu_keyboard()
        )
        await state.clear()
        print(f"Error in handle_add_friend_code: {e}")  # Для отладки
    except Exception as e:
        # Обработка ошибок
        await message.answer(
            f"❌ Произошла ошибка при добавлении друга.\n"
            f"Попробуй ещё раз или обратись к администратору.",
            reply_markup=friends_menu_keyboard()
        )
        await state.clear()
        print(f"Error in handle_add_friend_code: {e}")  # Для отладки


async def cmd_add_friend(message: Message) -> None:
    """Добавить друга по ID"""
    user = await get_or_ask_start(message)
    if not user:
        return
    
    args = message.text.split() if message.text else []
    if len(args) < 2:
        await message.answer(
            "Используй: /add_friend <ID друга>\n"
            "Например: /add_friend 123456789",
            reply_markup=main_menu_keyboard()
        )
        return
    
    try:
        friend_id = int(args[1])
    except ValueError:
        await message.answer("ID должен быть числом!", reply_markup=main_menu_keyboard())
        return
    
    if friend_id == user.user_id:
        await message.answer("Нельзя добавить самого себя в друзья 😅", reply_markup=main_menu_keyboard())
        return
    
    # Проверяем, существует ли друг
    friend_user = users_repo.get_user(friend_id)
    if not friend_user:
        await message.answer(
            f"Пользователь {friend_id} не найден в боте 🤔",
            reply_markup=main_menu_keyboard()
        )
        return
    
    # Проверяем, нет ли уже дружбы
    existing = friends_repo.get_friendship(user.user_id, friend_id)
    if existing:
        await message.answer(
            f"Ты уже дружишь с выдрой {friend_user.pet.name}! 👥",
            reply_markup=main_menu_keyboard()
        )
        return
    
    # Создаём дружбу
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc).isoformat()
    
    friendship = Friendship(
        user_id_1=user.user_id,
        user_id_2=friend_id,
        friendship_level=1,
        total_sessions_together=0,
        first_met_date=now,
        last_interaction=now,
    )
    
    friends_repo.save_friendship(friendship)
    
    await message.answer(
        f"🎉 Поздравляем! Ты теперь друг выдры {friend_user.pet.name}! 👥\n\n"
        f"⭐ Уровень дружбы: {get_friendship_stars(1)} (1/10)\n"
        f"💕 Начните совместные активности для укрепления дружбы!\n\n"
        f"Команды для совместных активностей:\n"
        f"/hobby_together — совместное хобби\n"
        f"/work_together — совместная работа\n"
        f"/coop_walk — совместная прогулка\n"
        f"/coop_meal — совместный обед\n",
        reply_markup=main_menu_keyboard()
    )


async def cmd_list_friends(message: Message) -> None:
    """Показать список друзей"""
    user = await get_or_ask_start(message)
    if not user:
        return
    
    friends = friends_repo.get_all_friends(user.user_id)
    
    if not friends:
        await message.answer(
            "У тебя нет друзей 😢\n"
            "Используй /add_friend <ID> чтобы добавить друга!",
            reply_markup=main_menu_keyboard()
        )
        return
    
    message_text = f"👥 Твои друзья ({len(friends)}):\n\n"
    
    for friend_id, friendship in friends.items():
        friend_user = users_repo.get_user(friend_id)
        if friend_user:
            level = friendship.friendship_level
            stars = get_friendship_stars(level)
            sessions = friendship.total_sessions_together
            
            message_text += (
                f"🦦 {friend_user.pet.name} (ID: {friend_id})\n"
                f"{stars} Уровень {level}/10 | {sessions} сессий\n\n"
            )
    
    await message.answer(message_text, reply_markup=main_menu_keyboard())


async def cmd_friend_info(message: Message) -> None:
    """Информация о дружбе с конкретным другом"""
    user = await get_or_ask_start(message)
    if not user:
        return
    
    args = message.text.split() if message.text else []
    if len(args) < 2:
        await message.answer(
            "Используй: /friend_info <ID друга>",
            reply_markup=main_menu_keyboard()
        )
        return
    
    try:
        friend_id = int(args[1])
    except ValueError:
        await message.answer("ID должен быть числом!", reply_markup=main_menu_keyboard())
        return
    
    friendship = friends_repo.get_friendship(user.user_id, friend_id)
    if not friendship:
        await message.answer(
            "Ты не дружишь с этой выдрой 🤔",
            reply_markup=main_menu_keyboard()
        )
        return
    
    friend_user = users_repo.get_user(friend_id)
    if not friend_user:
        await message.answer("Друг не найден!", reply_markup=main_menu_keyboard())
        return
    
    info = format_friendship_info(user.user_id, friend_id, friendship)
    
    await message.answer(
        f"🦦 Выдра: {friend_user.pet.name}\n\n"
        + info,
        reply_markup=main_menu_keyboard()
    )


async def cmd_coop_walk(message: Message) -> None:
    """Совместная прогулка (простая версия без ID)"""
    user = await get_or_ask_start(message)
    if not user:
        return
    
    pet = user.pet
    
    # Проверяем, не спит ли выдра
    if pet.avatar_key == "sleep" or pet.last_sleep_start is not None:
        await message.answer(
            "🦦 Выдра сейчас спит и не может гулять!\n\n"
            "Сначала разбуди её, а потом уже можно идти на прогулку.",
            reply_markup=main_menu_keyboard()
        )
        return
    
    degrade_pet(user)
    
    # Одиночная прогулка (рассчитываем как совместную с 1 участником)
    base_happiness = 15
    participant_bonus = get_num_participants_bonus(1)
    
    event_type, emoji, event_text, happiness_mod = get_random_coop_event("walk")
    
    happiness_gained = int(base_happiness * participant_bonus) + happiness_mod
    pet.happiness = min(100, pet.happiness + happiness_gained)
    pet.fatigue = max(0, pet.fatigue - 80)
    
    touch_pet(user)
    users_repo.save_user(user)
    
    result_text = format_coop_result(
        "walk",
        1,
        happiness_gained,
        0,
        emoji,
        event_text,
        0,
    )
    
    await message.answer(result_text, reply_markup=main_menu_keyboard())


async def cmd_coop_meal(message: Message) -> None:
    """Совместный обед (пикник с выдрой)"""
    user = await get_or_ask_start(message)
    if not user:
        return
    
    pet = user.pet
    
    # Проверяем, не спит ли выдра
    if pet.avatar_key == "sleep" or pet.last_sleep_start is not None:
        await message.answer(
            "🦦 Выдра сейчас спит и не может обедать!\n\n"
            "Сначала разбуди её, а потом уже можно обедать.",
            reply_markup=main_menu_keyboard()
        )
        return
    
    degrade_pet(user)
    
    base_happiness = 20
    base_money = 0
    
    event_type, emoji, event_text, happiness_mod = get_random_coop_event("meal")
    
    happiness_gained = base_happiness + happiness_mod
    pet.happiness = min(100, pet.happiness + happiness_gained)
    pet.hunger = min(100, pet.hunger + 30)
    
    touch_pet(user)
    users_repo.save_user(user)
    
    result_text = format_coop_result(
        "meal",
        1,
        happiness_gained,
        base_money,
        emoji,
        event_text,
        0,
    )
    
    await message.answer(result_text, reply_markup=main_menu_keyboard())


async def main() -> None:
    config = load_config()
    bot = Bot(token=config.token)
    
    # Инициализируем FSM storage
    from aiogram.fsm.storage.memory import MemoryStorage
    storage = MemoryStorage()
    
    dp = Dispatcher(storage=storage)

    # Роутер администратора
    dp.include_router(admin_router)

    # Дублируем регистрацию /admin на корневом диспетчере, чтобы команда
    # гарантированно не перехватывалась другими обработчиками
    dp.message.register(cmd_admin, Command("admin"))
    
    # Команды для рекомендаций и статистики хобби
    dp.message.register(cmd_hobby_recommendations, Command("hobby_recommendations"))
    dp.message.register(cmd_hobby_stats, Command("hobby_stats"))
    dp.message.register(cmd_hobby_help, Command("hobby_help"))
    dp.message.register(cmd_work_together_hobby, Command("hobby_together"))
    
    # Команды для дружбы и совместных активностей
    dp.message.register(cmd_add_friend, Command("add_friend"))
    dp.message.register(cmd_list_friends, Command("list_friends"))
    dp.message.register(cmd_friend_info, Command("friend_info"))
    dp.message.register(cmd_coop_walk, Command("coop_walk"))
    dp.message.register(cmd_coop_meal, Command("coop_meal"))

    dp.message.register(cmd_buy_hobby, Command("buy_hobby"))
    dp.message.register(cmd_settings, Command("settings"))
    dp.message.register(cmd_set_name, Command("set_name"))
    dp.message.register(cmd_set_timezone, Command("set_timezone"))
    dp.message.register(cmd_revive, Command("revive"))
    dp.message.register(cmd_work_together, Command("work_together"))
    dp.message.register(cmd_lunch_together, Command("lunch_together"))
    dp.message.register(cmd_pet_status, Command("pet_status"))
    dp.message.register(cmd_my_stats, Command("my_stats"))

    dp.message.register(cmd_start, CommandStart())
    
    # Обработчик имени выдры — только если питомец ещё не создан и это не команда
    # Также обрабатывает ввод нормы воды, если она не установлена
    # ВАЖНО: Регистрируем ПЕРЕД другими обработчиками текста, чтобы он обрабатывался первым
    # Исключаем FSM состояние для добавления друга
    dp.message.register(
        handle_pet_name,
        ~StateFilter(FriendshipFSM.waiting_for_friend_code) &
        F.text & ~F.text.startswith("/") &
        ~F.text.in_([
            "Разбудить питомца",
            "Уложить спать",
            "Накормить (завтрак)",
            "Накормить (обед)",
            "Накормить (ужин)",
            "Дать воды",
            "Отправить на работу",
            "Забрать с работы",
            "Хобби / тренировка",
            "Купить хобби",
            "Назад в меню",
            "Действия с выдрой",
            "👥 Друзья",
            "Настройки",
            "Статистика",
            "Совет дня",
            "Назад в главное меню",
            "Просмотреть настройки",
            "Изменить часовой пояс",
            "Изменить имя выдры",
            "Настроить норму воды",
            "Настроить объем стакана",
            "Знаю свою норму",
            "Не знаю, предложи норму",
            "2 литра",
            "2.5 литра",
            "3 литра",
            "Другое",
            "Назад в настройки",
            "Да",
            "Нет",
            "📋 Мои друзья",
            "🤝 Совместное хобби",
            "💼 Совместная работа",
            "🚶 Совместная прогулка",
            "🍽️ Совместный обед",
            "💪 Совместная тренировка",
            "🏆 Спортивный вызов",
            "🌲 Приключение",
            "🎁 Подарок другу",
            "🔗 Мой код дружбы",
            "➕ Добавить друга",
        ]) & ~F.text.contains("💰") & ~F.text.startswith("🎨 ") & ~F.text.startswith("🆓"),
    )

    # Новое главное меню
    dp.message.register(
        handle_main_menu,
        F.text.in_([
            "Действия с выдрой",
            "Настройки",
            "Статистика",
            "Совет дня",
            "Назад в главное меню",
        ])
    )
    
    # Меню действий с выдрой - ВСЕ действия
    dp.message.register(
        handle_actions_menu,
        F.text.in_([
            # Действия с выдрой (геймификация)
            "Разбудить питомца",
            "Уложить спать",
            "Накормить (завтрак)",
            "Накормить (обед)",
            "Накормить (ужин)",
            "Дать воды",
            "Отправить на работу",
            "Забрать с работы",
            "Хобби / тренировка",
            "Купить хобби",
        ])
    )
    
    # Меню настроек
    # Создаем обертку для передачи state
    async def handle_settings_menu_wrapper(message: Message, state: FSMContext = None) -> None:
        await handle_settings_menu(message, state)
    
    dp.message.register(
        handle_settings_menu_wrapper,
        F.text.in_([
            "Просмотреть настройки",
            "Изменить часовой пояс",
            "Изменить имя выдры",
            "Настроить норму воды",
            "Настроить объем стакана",
            "Назад в главное меню",
        ])
    )
    
    # Обработка настройки нормы воды
    dp.message.register(
        handle_water_norm_setup,
        F.text.in_([
            "Знаю свою норму",
            "Не знаю, предложи норму",
            "2 литра",
            "2.5 литра",
            "3 литра",
            "Другое",
            "Назад в настройки",
        ])
    )
    
    # Обработчик ввода объема стакана (FSM)
    async def handle_glass_volume_input(message: Message, state: FSMContext) -> None:
        """Обработка ввода объема стакана"""
        user = users_repo.get_user(message.from_user.id)
        if user is None:
            await state.clear()
            await message.answer("Сначала нажми /start и создай свою выдру 🦦")
            return
        
        text = message.text.strip()
        
        # Проверяем, не кнопка ли это меню
        if text in ["Назад в главное меню", "Настройки", "Назад в настройки"]:
            await state.clear()
            if text == "Настройки" or text == "Назад в настройки":
                await message.answer("⚙️ Настройки", reply_markup=settings_menu_keyboard())
            else:
                await message.answer("🏠 Главное меню", reply_markup=main_menu_keyboard())
            return
        
        # Пробуем распарсить как число
        try:
            # Убираем "мл" или "ml" если есть
            clean_text = text.replace("мл", "").replace("ml", "").replace(" ", "").strip()
            volume = int(clean_text)
            
            if 50 <= volume <= 1000:
                user.settings.glass_volume_ml = volume
                users_repo.save_user(user)
                await state.clear()
                await message.answer(
                    f"💧 Объем стакана установлен: {volume}мл.",
                    reply_markup=main_menu_keyboard()
                )
            else:
                await message.answer(
                    "💧 Пожалуйста, введи объем от 50 до 1000 мл.",
                    reply_markup=settings_menu_keyboard()
                )
        except ValueError:
            await message.answer(
                "💧 Не понял. Введи число от 50 до 1000 (например, 250).",
                reply_markup=settings_menu_keyboard()
            )
    
    dp.message.register(
        handle_glass_volume_input,
        StateFilter(WaterSettingsFSM.waiting_for_glass_volume)
    )
    
    # Обработка ответов на еженедельный вопрос о соблюдении советов
    dp.message.register(
        handle_weekly_advice_answer,
        F.text.in_(["Да", "Нет"])
    )
    
    # Обработчик ответа на вопрос о сне (FSM) - регистрируем ПЕРЕД общим обработчиком "Да"/"Нет"
    dp.message.register(
        handle_sleep_norm_answer,
        StateFilter(SleepNormFSM.waiting_for_sleep_norm_answer)
    )
    
    # Обработчик ввода объема стакана (FSM) - регистрируем ПЕРЕД общим обработчиком текста
    dp.message.register(
        handle_glass_volume_input,
        StateFilter(WaterSettingsFSM.waiting_for_glass_volume)
    )
    
    # Обработчик меню друзей
    dp.message.register(
        handle_friends_menu,
        F.text == "👥 Друзья"
    )
    
    # Обработчик отображения моего кода дружбы
    dp.message.register(
        cmd_my_friend_code,
        F.text == "🔗 Мой код дружбы"
    )
    
    # Обработчик кнопки добавления друга по коду
    dp.message.register(
        cmd_add_friend_by_code,
        F.text == "➕ Добавить друга"
    )

    # Обработчик ввода кода дружбы (обработка текста после нажатия ➕)
    # ВАЖНО: Регистрируем с фильтром, чтобы не перехватывать команды
    dp.message.register(
        handle_add_friend_code,
        StateFilter(FriendshipFSM.waiting_for_friend_code) & 
        ~F.text.startswith("/")  # Не обрабатываем команды
    )

    # Обработчик имени выдры — только если питомец ещё не создан и это не команда
    # Также обрабатывает ввод нормы воды, если она не установлена
    # ВАЖНО: Регистрируем ПЕРЕД общим обработчиком текста, чтобы он обрабатывался первым
    dp.message.register(
        handle_pet_name,
        F.text & ~F.text.startswith("/") &
        ~F.text.in_([
            "Разбудить питомца",
            "Уложить спать",
            "Накормить (завтрак)",
            "Накормить (обед)",
            "Накормить (ужин)",
            "Дать воды",
            "Отправить на работу",
            "Забрать с работы",
            "Хобби / тренировка",
            "Купить хобби",
            "Назад в меню",
            "Действия с выдрой",
            "👥 Друзья",
            "Настройки",
            "Статистика",
            "Совет дня",
            "Назад в главное меню",
            "Просмотреть настройки",
            "Изменить часовой пояс",
            "Изменить имя выдры",
            "Настроить норму воды",
            "Настроить объем стакана",
            "Знаю свою норму",
            "Не знаю, предложи норму",
            "2 литра",
            "2.5 литра",
            "3 литра",
            "Другое",
            "Назад в настройки",
            "Да",
            "Нет",
            "📋 Мои друзья",
            "🤝 Совместное хобби",
            "💼 Совместная работа",
            "🚶 Совместная прогулка",
            "🍽️ Совместный обед",
            "💪 Совместная тренировка",
            "🏆 Спортивный вызов",
            "🌲 Приключение",
            "🎁 Подарок другу",
            "🔗 Мой код дружбы",
            "➕ Добавить друга",
        ]) & ~F.text.contains("💰") & ~F.text.startswith("🎨 ") & ~F.text.startswith("🆓"),
    )

    # Старые обработчики теперь обрабатываются через handle_actions_menu
    # Удаляем дублирующую регистрацию, чтобы избежать конфликтов
    dp.message.register(handle_buy_hobby_button, F.text.contains("💰") & F.text.contains("("))
    dp.message.register(handle_back_to_menu, F.text == "Назад в меню")
    # Обработчик выбора хобби (базовое или купленное)
    dp.message.register(handle_hobby_selection, F.text.in_(["🆓 Прогулка по парку"]) | F.text.startswith("🎨 "))

    # Общий обработчик текста — не трогаем команды вида /...
    # Также проверяем долгое бездействие и возвращаем в главное меню
    # ВАЖНО: Этот обработчик должен быть последним и не перехватывать кнопки меню
    async def handle_text_with_inactivity_check(message: Message) -> None:
        # Исключаем все кнопки меню, которые уже обрабатываются другими обработчиками
        menu_buttons = [
            "Действия с выдрой", "👥 Друзья", "Настройки", "Статистика", "Совет дня", "Назад в главное меню",
            "Разбудить питомца", "Уложить спать", "Накормить (завтрак)", "Накормить (обед)", 
            "Накормить (ужин)", "Дать воды", "Отправить на работу", "Забрать с работы",
            "Хобби / тренировка", "Купить хобби",
            "Просмотреть настройки", "Изменить часовой пояс", "Изменить имя выдры",
            "Настроить норму воды", "Настроить объем стакана", "Знаю свою норму",
            "Не знаю, предложи норму", "2 литра", "2.5 литра", "3 литра", "Другое",
            "Назад в настройки", "Да", "Нет", "Назад в меню",
            "📋 Мои друзья", "🤝 Совместное хобби", "💼 Совместная работа",
            "🚶 Совместная прогулка", "🍽️ Совместный обед", "💪 Совместная тренировка",
            "🏆 Спортивный вызов", "🌲 Приключение", "🎁 Подарок другу",
            "🔗 Мой код дружбы", "➕ Добавить друга",
        ]
        
        if message.text in menu_buttons:
            # Это кнопка меню, она должна обрабатываться другими обработчиками
            # Если мы здесь, значит что-то пошло не так - просто игнорируем
            return
        
        user = users_repo.get_user(message.from_user.id)
        
        # Если пользователя нет в базе, это может быть ввод имени выдры - пропускаем
        if user is None:
            return
        if user and user.last_main_menu_return:
            from datetime import datetime, timezone, timedelta
            try:
                last_return = datetime.fromisoformat(user.last_main_menu_return)
                now = datetime.now(timezone.utc)
                # Если прошло больше 2 часов без взаимодействия, возвращаем в главное меню
                if (now - last_return).total_seconds() > 2 * 3600:
                    await message.answer(
                        "🦦 Давно не виделись! Возвращаю тебя в главное меню.",
                        reply_markup=main_menu_keyboard()
                    )
                    user.last_main_menu_return = now.isoformat()
                    users_repo.save_user(user)
                    return
            except Exception:
                pass
        
        await handle_unknown(message)
    
    # Регистрируем общий обработчик последним, чтобы он не перехватывал кнопки меню
    dp.message.register(
        handle_text_with_inactivity_check, 
        F.text & 
        ~F.text.startswith("/") &
        ~F.text.in_([
            "Действия с выдрой", "Настройки", "Статистика", "Совет дня", "Назад в главное меню",
            "Разбудить питомца", "Уложить спать", "Накормить (завтрак)", "Накормить (обед)", 
            "Накормить (ужин)", "Дать воды", "Отправить на работу", "Забрать с работы",
            "Хобби / тренировка", "Купить хобби",
            "Просмотреть настройки", "Изменить часовой пояс", "Изменить имя выдры",
            "Настроить норму воды", "Настроить объем стакана", "Знаю свою норму",
            "Не знаю, предложи норму", "2 литра", "2.5 литра", "3 литра", "Другое",
            "Назад в настройки", "Да", "Нет", "Назад в меню",
        ]) &
        ~F.text.contains("💰") & 
        ~F.text.startswith("🎨 ") & 
        ~F.text.startswith("🆓")
    )

    # Запускаем фоновый воркер напоминаний
    asyncio.create_task(reminders_worker(bot, users_repo))

    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
    