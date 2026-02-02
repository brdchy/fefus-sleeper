import asyncio
from datetime import datetime, time, date, timezone
from typing import Dict

from aiogram import Bot
from zoneinfo import ZoneInfo

from bot.core.repositories import UsersRepository
from bot.core.health import get_health_state, HealthState
from bot.core.menu import main_menu_keyboard


REMINDER_TIMES: Dict[str, time] = {
    "water_morning": time(10, 0),
    "lunch": time(13, 0),
    "water_afternoon": time(17, 0),
    "evening": time(20, 0),
    "sleep": time(22, 0),
}


REMINDER_TEXTS: Dict[str, str] = {
    "water_morning": "🦦 Выдра просыпается и предлагает начать день со стаканчика воды. Пойдём выпьем вместе? 💧",
    "lunch": "🦦 Выдра хочет пообедать вместе с тобой. Давай накормим её и себя? 🍽️",
    "water_afternoon": "🦦 Выдра напоминает: сделаем перерыв и выпьем воды? Вместе веселее! 💧",
    "evening": "🦦 Выдра зевает и предлагает начать готовиться ко сну. Пора укладываться! 😴",
    "sleep": "🦦 Уже 22:00! Выдра напоминает: пора ложиться спать. Давай уложим её и сам(а) тоже отдохни? 😴💤",
}


async def reminders_worker(bot: Bot, users_repo: UsersRepository) -> None:
    """
    Периодически проходит по всем пользователям и отправляет напоминания
    в локальном времени пользователя. Также увеличивает возраст выдр раз в день.
    """
    while True:
        users = users_repo.get_all_users()
        today = date.today().isoformat()

        for uid_str, user in users.items():
            chat_id = int(uid_str)
            last = user.last_reminders
            pet = user.pet

            try:
                tz = ZoneInfo(user.settings.timezone)
            except Exception:
                tz = ZoneInfo("Asia/Vladivostok")

            now_dt = datetime.now(tz)
            now = now_dt.time()
            today_date = now_dt.date()
            
            # Увеличиваем возраст выдры раз в день (при первом взаимодействии за день)
            last_age_update = last.get("age_update")
            if last_age_update != today:
                pet.age_days += 1
                last["age_update"] = today
                users_repo.save_user(user)
            
            # Проверяем еженедельный отчет (воскресенье вечером, 21:00)
            if today_date.weekday() == 6 and now.hour == 21 and now.minute == 0:  # Воскресенье
                weekly_report_key = f"weekly_report_{today_date.isoformat()}"
                if last.get(weekly_report_key) != today:
                    from bot.core.advice import get_weekly_advice_summary
                    from bot.core.menu import weekly_advice_answer_keyboard, main_menu_keyboard
                    
                    advice_summary = get_weekly_advice_summary(user)
                    if advice_summary and advice_summary != "На этой неделе ты ещё не получал советы.":
                        try:
                            await bot.send_message(
                                chat_id,
                                f"📋 Еженедельный отчет по советам:\n\n{advice_summary}\n\n"
                                f"Как успехи? Соблюдал ли ты советы?",
                                reply_markup=weekly_advice_answer_keyboard()
                            )
                            last[weekly_report_key] = today
                            users_repo.save_user(user)
                        except Exception:
                            pass
            
            # Проверяем ежемесячный отчет (через 30 дней после первого совета)
            advice_state = user.advice_state
            if advice_state.first_advice_date:
                try:
                    first_advice_date = date.fromisoformat(advice_state.first_advice_date)
                    days_passed = (today_date - first_advice_date).days
                    
                    # Проверяем, не отправляли ли уже месячный отчет
                    monthly_report_key = f"monthly_report_{first_advice_date.isoformat()}"
                    if days_passed >= 30 and last.get(monthly_report_key) != today:
                        from bot.core.advice import get_monthly_advice_summary
                        
                        monthly_summary = get_monthly_advice_summary(user)
                        if monthly_summary and monthly_summary != "За этот месяц ты ещё не получал советы.":
                            try:
                                await bot.send_message(
                                    chat_id,
                                    f"📊 Ежемесячный отчет по советам:\n\n{monthly_summary}",
                                    reply_markup=main_menu_keyboard()
                                )
                                last[monthly_report_key] = today
                                users_repo.save_user(user)
                            except Exception:
                                pass
                except Exception:
                    pass
            
            # Проверяем, не работает ли выдра больше 10 часов
            if pet.is_alive and pet.at_work and pet.last_work_start:
                try:
                    from datetime import timezone
                    work_start = datetime.fromisoformat(pet.last_work_start)
                    work_end = datetime.now(timezone.utc)
                    work_duration_hours = (work_end - work_start).total_seconds() / 3600.0
                    
                    # Получаем уже отработанные часы за сегодня
                    worked_hours_today = user.work_hours_by_date.get(today, 0.0)
                    total_worked = worked_hours_today + work_duration_hours
                    
                    # Если выдра работает больше 10 часов, отправляем напоминание
                    if total_worked >= 10.0:
                        reminder_key = "work_limit_reached"
                        # Отправляем напоминание не чаще раза в час
                        last_reminder_time = last.get(reminder_key)
                        if last_reminder_time:
                            try:
                                last_reminder_dt = datetime.fromisoformat(last_reminder_time)
                                hours_since_reminder = (now_dt - last_reminder_dt).total_seconds() / 3600.0
                                if hours_since_reminder < 1.0:
                                    # Уже отправляли напоминание в последний час
                                    pass
                                else:
                                    # Прошёл час, можно отправить снова
                                    await bot.send_message(
                                        chat_id,
                                        "🦦 Выдра уже отработала 10 часов и ждёт тебя на лавочке! "
                                        "Пора забирать её с работы. Она устала и хочет отдохнуть 💼😴"
                                    )
                                    last[reminder_key] = now_dt.isoformat()
                                    users_repo.save_user(user)
                            except Exception:
                                # Если ошибка парсинга, отправляем напоминание
                                await bot.send_message(
                                    chat_id,
                                    "🦦 Выдра уже отработала 10 часов и ждёт тебя на лавочке! "
                                    "Пора забирать её с работы. Она устала и хочет отдохнуть 💼😴"
                                )
                                last[reminder_key] = now_dt.isoformat()
                                users_repo.save_user(user)
                        else:
                            # Первое напоминание
                            await bot.send_message(
                                chat_id,
                                "🦦 Выдра уже отработала 10 часов и ждёт тебя на лавочке! "
                                "Пора забирать её с работы. Она устала и хочет отдохнуть 💼😴"
                            )
                            last[reminder_key] = now_dt.isoformat()
                            users_repo.save_user(user)
                except Exception:
                    # Игнорируем ошибки при проверке времени работы
                    pass
            
            # Проверка критического состояния отключена (навязчивые напоминания убраны)
            
            # Проверяем, не умерла ли выдра, и отправляем уведомление (только один раз)
            if not pet.is_alive:
                death_notification_key = "death_notification_sent"
                if not last.get(death_notification_key):
                    try:
                        await bot.send_message(
                            chat_id,
                            f"💀 К сожалению, твоя выдра {pet.name} умерла...\n\n"
                            f"Она не получила достаточной заботы и ушла в мир иной.\n\n"
                            f"Но не расстраивайся! Ты можешь попробовать воскресить её командой /revive\n\n"
                            f"У тебя есть 1 бесплатное воскрешение. После этого воскрешение будет доступно через подписку на канал.",
                            reply_markup=main_menu_keyboard()
                        )
                        last[death_notification_key] = datetime.now(timezone.utc).isoformat()
                        users_repo.save_user(user)
                    except Exception:
                        pass
            
            for key, t in REMINDER_TIMES.items():
                # Если напоминание за сегодня уже было — пропускаем
                if last.get(key) == today:
                    continue

                # Проверяем время с небольшой погрешностью (в пределах минуты)
                if now.hour == t.hour and abs(now.minute - t.minute) <= 1:
                    # Не отправляем напоминания, если выдра мертва или в отпуске
                    if not pet.is_alive:
                        continue
                    if pet.vacation_mode:
                        continue
                    
                    # Для напоминания о сне проверяем, что выдра еще не спит
                    if key == "sleep":
                        # Проверяем, спит ли выдра (avatar_key == "sleep" или есть last_sleep_start)
                        if pet.avatar_key == "sleep" or pet.last_sleep_start is not None:
                            # Выдра уже спит, пропускаем напоминание
                            last[key] = today
                            users_repo.save_user(user)
                            continue
                    
                    text = REMINDER_TEXTS.get(key)
                    if text:
                        try:
                            await bot.send_message(chat_id, text)
                        except Exception:
                            # Игнорируем ошибки отправки отдельным пользователям
                            pass
                    last[key] = today
                    users_repo.save_user(user)

        await asyncio.sleep(60)

