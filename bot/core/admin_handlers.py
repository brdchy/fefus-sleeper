from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message, FSInputFile

from bot.core.repositories import AdminRepository, HobbiesRepository, UsersRepository
from bot.core.models import Hobby
from bot.core.stats import StatsRepository
from pathlib import Path
import matplotlib.pyplot as plt
from datetime import datetime, timedelta, timezone
from typing import Dict


admin_router = Router()
admin_repo = AdminRepository()
hobbies_repo = HobbiesRepository()
stats_repo = StatsRepository()


def is_admin(user_id: int) -> bool:
    settings = admin_repo.get_settings()
    return user_id in settings.admin_ids


@admin_router.message(Command("admin"))
async def cmd_admin(message: Message) -> None:
    if not is_admin(message.from_user.id):
        await message.answer("Эта команда доступна только администратору.")
        return

    settings = admin_repo.get_settings()
    channel = settings.required_channel_username or "не задан"
    await message.answer(
        "Панель администратора:\n"
        f"- Текущий канал для подписки: {channel}\n\n"
        "Команды:\n"
        "/set_channel @username — указать канал для подписки\n"
        "/broadcast текст — мгновенная рассылка всем пользователям\n"
        "/add_hobby id|Название|цена|avatar_key — добавить новое хобби\n"
        "/list_hobbies — показать все хобби\n"
        "/stats — показать инфографику статистики\n"
        "/bot_stats — подробная статистика использования бота\n"
    )


@admin_router.message(Command("set_channel"))
async def cmd_set_channel(message: Message) -> None:
    if not is_admin(message.from_user.id):
        await message.answer("Эта команда доступна только администратору.")
        return

    parts = message.text.split(maxsplit=1) if message.text else []
    if len(parts) < 2:
        await message.answer("Укажи имя канала, например: /set_channel @fefus_sleep")
        return

    channel_username = parts[1].strip()

    settings = admin_repo.get_settings()
    settings.required_channel_username = channel_username
    admin_repo.save_settings(settings)

    await message.answer(f"Канал для проверки подписки обновлён: {channel_username}")


@admin_router.message(Command("broadcast"))
async def cmd_broadcast(message: Message) -> None:
    if not is_admin(message.from_user.id):
        await message.answer("Эта команда доступна только администратору.")
        return

    parts = message.text.split(maxsplit=1) if message.text else []
    if len(parts) < 2:
        await message.answer("Укажи текст рассылки: /broadcast Текст сообщения")
        return

    text = parts[1]
    from bot.core.repositories import UsersRepository
    users_repo = UsersRepository()
    all_users = users_repo.get_all_users()
    
    sent = 0
    failed = 0
    for uid_str in all_users.keys():
        try:
            await message.bot.send_message(int(uid_str), text)
            sent += 1
        except Exception:
            failed += 1
    
    await message.answer(
        f"Рассылка завершена.\n"
        f"Отправлено: {sent}\n"
        f"Ошибок: {failed}"
    )


@admin_router.message(Command("add_hobby"))
async def cmd_add_hobby(message: Message) -> None:
    if not is_admin(message.from_user.id):
        await message.answer("Эта команда доступна только администратору.")
        return

    parts = message.text.split(maxsplit=1) if message.text else []
    if len(parts) < 2:
        await message.answer(
            "Формат: /add_hobby id|Название|цена|avatar_key\n"
            "Например: /add_hobby sport|Спортзал|20|hobby"
        )
        return

    try:
        raw = parts[1]
        hid, title, price_str, avatar_key = [x.strip() for x in raw.split("|")]
        price = int(price_str)
    except Exception:
        await message.answer("Не удалось распарсить параметры. Проверь формат.")
        return

    hobby = Hobby(id=hid, title=title, price=price, avatar_key=avatar_key)
    hobbies_repo.save(hobby)
    await message.answer(f"Хобби '{title}' добавлено. Цена: {price} монет.")


@admin_router.message(Command("list_hobbies"))
async def cmd_list_hobbies(message: Message) -> None:
    if not is_admin(message.from_user.id):
        await message.answer("Эта команда доступна только администратору.")
        return

    hobbies = hobbies_repo.get_all()
    if not hobbies:
        await message.answer("Хобби пока не добавлены.")
        return

    lines = ["Список хобби:"]
    for hobby in hobbies.values():
        lines.append(f"- {hobby.id}: {hobby.title} — {hobby.price} монет (avatar_key={hobby.avatar_key})")
    await message.answer("\n".join(lines))


@admin_router.message(Command("stats"))
async def cmd_stats(message: Message) -> None:
    if not is_admin(message.from_user.id):
        await message.answer("Эта команда доступна только администратору.")
        return

    all_stats = stats_repo.get_all()
    if not all_stats:
        await message.answer("Статистика пока пуста.")
        return

    labels = []
    sleep_hours = []
    work_sessions = []
    hobby_sessions = []

    for uid, s in all_stats.items():
        labels.append(str(s.user_id))
        sleep_hours.append(s.total_sleep_minutes / 60)
        work_sessions.append(s.work_sessions)
        hobby_sessions.append(s.hobby_sessions)

    fig, ax = plt.subplots(figsize=(8, 4))
    x = range(len(labels))
    ax.bar(x, sleep_hours, label="Часы сна")
    ax.bar(x, work_sessions, bottom=sleep_hours, label="Сессии работы")
    ax.bar(
        x,
        hobby_sessions,
        bottom=[sleep_hours[i] + work_sessions[i] for i in x],
        label="Сессии хобби",
    )
    ax.set_xticks(list(x))
    ax.set_xticklabels(labels, rotation=45)
    ax.set_ylabel("Условные единицы")
    ax.set_title("Активность пользователей FEFUS")
    ax.legend()
    fig.tight_layout()

    stats_path = Path("bot/data/stats.png")
    stats_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(stats_path)
    plt.close(fig)

    photo = FSInputFile(stats_path)
    await message.answer_photo(
        photo,
        caption="Инфографика по сну и активности пользователей.",
    )


@admin_router.message(Command("bot_stats"))
async def cmd_bot_stats(message: Message) -> None:
    """Подробная статистика использования бота"""
    if not is_admin(message.from_user.id):
        await message.answer("Эта команда доступна только администратору.")
        return
    
    users_repo = UsersRepository()
    stats_repo = StatsRepository()
    hobbies_repo = HobbiesRepository()
    
    all_users = users_repo.get_all_users()
    all_stats = stats_repo.get_all()
    
    if not all_users:
        await message.answer("В боте пока нет пользователей.")
        return
    
    now = datetime.now(timezone.utc)
    week_ago = now - timedelta(days=7)
    
    # Общая статистика
    total_users = len(all_users)
    active_users = 0
    new_users = 0
    dead_otters = 0
    vacation_otters = 0
    total_friendships = 0
    total_coop_sessions = 0
    
    # Статистика по выдрам
    total_age_days = 0
    total_happiness = 0
    total_energy = 0
    total_money = 0
    total_unlocked_hobbies = 0
    total_achievements = 0
    
    # Статистика по активности
    total_sleep_minutes = 0
    total_feed_events = 0
    total_water_events = 0
    total_work_sessions = 0
    total_hobby_sessions = 0
    total_advice_requests = 0
    
    # Топ пользователи
    most_active_users = []
    longest_sleep_users = []
    most_friends_users = []
    
    for uid_str, user in all_users.items():
        # Активность
        if user.last_main_menu_return:
            try:
                last_return = datetime.fromisoformat(user.last_main_menu_return)
                if last_return >= week_ago:
                    active_users += 1
            except:
                pass
        
        # Новые пользователи
        if user.pet.last_interaction:
            try:
                first_interaction = datetime.fromisoformat(user.pet.last_interaction)
                if first_interaction >= week_ago:
                    new_users += 1
            except:
                pass
        
        # Статус выдры
        if not user.pet.is_alive:
            dead_otters += 1
        if user.pet.vacation_mode:
            vacation_otters += 1
        
        # Дружба
        friendships = getattr(user, 'friendships', {})
        if friendships:
            total_friendships += len(friendships)
            most_friends_users.append((user.user_id, len(friendships)))
        
        # Совместные активности
        coop_sessions = getattr(user, 'coop_sessions', [])
        if coop_sessions:
            total_coop_sessions += len(coop_sessions)
        
        # Статистика выдры
        total_age_days += user.pet.age_days
        total_happiness += user.pet.happiness
        total_energy += user.pet.energy
        total_money += user.pet.money
        total_unlocked_hobbies += len(user.pet.unlocked_hobbies)
        total_achievements += len(user.pet.unlocked_achievements)
        
        # Статистика активности
        if hasattr(user, 'daily_stats'):
            for day_stats in user.daily_stats.values():
                total_sleep_minutes += day_stats.sleep_minutes
        
        # Статистика из stats_repo
        user_stats = all_stats.get(uid_str)
        if user_stats:
            total_feed_events += user_stats.feed_events
            total_water_events += user_stats.water_events
            total_work_sessions += user_stats.work_sessions
            total_hobby_sessions += user_stats.hobby_sessions
            total_sleep_minutes += user_stats.total_sleep_minutes
            
            # Топ активные
            activity_score = (
                user_stats.feed_events +
                user_stats.water_events +
                user_stats.work_sessions +
                user_stats.hobby_sessions
            )
            most_active_users.append((user.user_id, activity_score))
            
            # Топ сон
            sleep_hours = user_stats.total_sleep_minutes / 60
            longest_sleep_users.append((user.user_id, sleep_hours))
        
        # Советы
        if hasattr(user, 'advice_state') and user.advice_state.shown_advice_ids:
            total_advice_requests += len(user.advice_state.shown_advice_ids)
    
    # Сортируем топы
    most_active_users.sort(key=lambda x: x[1], reverse=True)
    longest_sleep_users.sort(key=lambda x: x[1], reverse=True)
    most_friends_users.sort(key=lambda x: x[1], reverse=True)
    
    # Формируем сообщение
    stats_text = "📊 СТАТИСТИКА ИСПОЛЬЗОВАНИЯ БОТА FEFUS\n\n"
    
    stats_text += "👥 ОБЩАЯ СТАТИСТИКА\n"
    stats_text += f"Всего пользователей: {total_users}\n"
    stats_text += f"Активных (за 7 дней): {active_users}\n"
    stats_text += f"Новых (за 7 дней): {new_users}\n"
    stats_text += f"Мёртвых выдр: {dead_otters}\n"
    stats_text += f"Выдр в отпуске: {vacation_otters}\n\n"
    
    stats_text += "🦦 СТАТИСТИКА ПО ВЫДРАМ\n"
    if total_users > 0:
        stats_text += f"Средний возраст: {total_age_days / total_users:.1f} дней\n"
        stats_text += f"Среднее счастье: {total_happiness / total_users:.1f}/100\n"
        stats_text += f"Средняя энергия: {total_energy / total_users:.1f}/100\n"
        stats_text += f"Всего монет у всех: {total_money}\n"
        stats_text += f"Среднее разблокированных хобби: {total_unlocked_hobbies / total_users:.1f}\n"
        stats_text += f"Всего достижений разблокировано: {total_achievements}\n\n"
    
    stats_text += "📈 СТАТИСТИКА ПО АКТИВНОСТИ\n"
    stats_text += f"Всего часов сна: {total_sleep_minutes / 60:.1f}\n"
    stats_text += f"Всего кормлений: {total_feed_events}\n"
    stats_text += f"Всего воды выпито: {total_water_events} стаканов\n"
    stats_text += f"Всего рабочих сессий: {total_work_sessions}\n"
    stats_text += f"Всего хобби сессий: {total_hobby_sessions}\n"
    stats_text += f"Всего дружб: {total_friendships}\n"
    stats_text += f"Всего совместных активностей: {total_coop_sessions}\n"
    stats_text += f"Всего запросов советов: {total_advice_requests}\n\n"
    
    stats_text += "🏆 ТОП ПОЛЬЗОВАТЕЛИ\n"
    if most_active_users:
        stats_text += "Самые активные (топ-5):\n"
        for i, (uid, score) in enumerate(most_active_users[:5], 1):
            user = users_repo.get_user(uid)
            name = user.pet.name if user else "Неизвестно"
            stats_text += f"{i}. {name} (ID: {uid}) — {score} действий\n"
        stats_text += "\n"
    
    if longest_sleep_users:
        stats_text += "Самый долгий сон (топ-5):\n"
        for i, (uid, hours) in enumerate(longest_sleep_users[:5], 1):
            user = users_repo.get_user(uid)
            name = user.pet.name if user else "Неизвестно"
            stats_text += f"{i}. {name} (ID: {uid}) — {hours:.1f} часов\n"
        stats_text += "\n"
    
    if most_friends_users:
        stats_text += "Больше всего друзей (топ-5):\n"
        for i, (uid, friends_count) in enumerate(most_friends_users[:5], 1):
            user = users_repo.get_user(uid)
            name = user.pet.name if user else "Неизвестно"
            stats_text += f"{i}. {name} (ID: {uid}) — {friends_count} друзей\n"
    
    # Разбиваем на части если слишком длинное
    if len(stats_text) > 4000:
        parts = stats_text.split("\n\n")
        current_part = ""
        for part in parts:
            if len(current_part) + len(part) + 2 > 4000:
                await message.answer(current_part)
                current_part = part + "\n\n"
            else:
                current_part += part + "\n\n"
        if current_part:
            await message.answer(current_part)
    else:
        await message.answer(stats_text)

