"""
Новая структура меню бота
"""
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
from datetime import datetime, date, timedelta
from zoneinfo import ZoneInfo

from bot.core.models import UserState, DailyStats
from bot.core.advice import get_advice_for_today, get_weekly_advice_summary, get_monthly_advice_summary


def main_menu_keyboard() -> ReplyKeyboardMarkup:
    """Главное меню с 5 кнопками (добавлена социальная)"""
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="Действия с выдрой"), KeyboardButton(text="👥 Друзья")],
            [KeyboardButton(text="Настройки"), KeyboardButton(text="Статистика")],
            [KeyboardButton(text="Совет дня")],
        ],
        resize_keyboard=True,
    )


def actions_menu_keyboard() -> ReplyKeyboardMarkup:
    """Меню действий с выдрой - все старые действия + новые"""
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="Разбудить питомца"), KeyboardButton(text="Уложить спать")],
            [KeyboardButton(text="Накормить (завтрак)"), KeyboardButton(text="Накормить (обед)")],
            [KeyboardButton(text="Накормить (ужин)"), KeyboardButton(text="Дать воды")],
            [KeyboardButton(text="Отправить на работу"), KeyboardButton(text="Забрать с работы")],
            [KeyboardButton(text="Хобби / тренировка"), KeyboardButton(text="Купить хобби")],
            [KeyboardButton(text="Ложусь спать"), KeyboardButton(text="Проснулся")],
            [KeyboardButton(text="Назад в главное меню")],
        ],
        resize_keyboard=True,
    )


def friends_menu_keyboard() -> ReplyKeyboardMarkup:
    """Меню друзей и совместных активностей"""
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🔗 Мой код дружбы"), KeyboardButton(text="➕ Добавить друга")],
            [KeyboardButton(text="📋 Мои друзья")],
            [KeyboardButton(text="🤝 Совместное хобби"), KeyboardButton(text="💼 Совместная работа")],
            [KeyboardButton(text="🚶 Совместная прогулка"), KeyboardButton(text="🍽️ Совместный обед")],
            [KeyboardButton(text="💪 Совместная тренировка"), KeyboardButton(text="🏆 Спортивный вызов")],
            [KeyboardButton(text="🌲 Приключение"), KeyboardButton(text="🎁 Подарок другу")],
            [KeyboardButton(text="Назад в главное меню")],
        ],
        resize_keyboard=True,
    )


def settings_menu_keyboard() -> ReplyKeyboardMarkup:
    """Меню настроек"""
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="Просмотреть настройки")],
            [KeyboardButton(text="Изменить часовой пояс")],
            [KeyboardButton(text="Изменить имя выдры")],
            [KeyboardButton(text="Настроить норму воды")],
            [KeyboardButton(text="Настроить объем стакана")],
            [KeyboardButton(text="Назад в главное меню")],
        ],
        resize_keyboard=True,
    )


def water_norm_setup_keyboard() -> ReplyKeyboardMarkup:
    """Клавиатура для настройки нормы воды"""
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="Знаю свою норму")],
            [KeyboardButton(text="Не знаю, предложи норму")],
            [KeyboardButton(text="2 литра"), KeyboardButton(text="2.5 литра")],
            [KeyboardButton(text="3 литра"), KeyboardButton(text="Другое")],
            [KeyboardButton(text="Назад в настройки")],
        ],
        resize_keyboard=True,
    )


def weekly_advice_answer_keyboard() -> ReplyKeyboardMarkup:
    """Клавиатура для ответа на вопрос о соблюдении советов"""
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="Да"), KeyboardButton(text="Нет")],
        ],
        resize_keyboard=True,
    )


def get_today_stats(user: UserState) -> DailyStats:
    """Получить или создать статистику на сегодня"""
    today = date.today().isoformat()
    if today not in user.daily_stats:
        user.daily_stats[today] = DailyStats(date=today)
    return user.daily_stats[today]


def format_weekly_stats(user: UserState) -> str:
    """
    Форматирует детальную персонализированную статистику за неделю.
    С разбивкой по дням и сравнением с выдрой.
    """
    try:
        tz = ZoneInfo(user.settings.timezone)
    except Exception:
        tz = ZoneInfo("Asia/Vladivostok")
    
    today = date.today()
    week_dates = [today - timedelta(days=i) for i in range(7)]
    
    # Названия дней недели
    weekdays_ru = ["Понедельник", "Вторник", "Среда", "Четверг", "Пятница", "Суббота", "Воскресенье"]
    
    lines = ["📊 Твоя статистика за последние 7 дней:\n"]
    
    # Разбивка по дням
    total_sleep_minutes = 0
    total_water_liters = 0.0
    total_pet_sleep_minutes = 0
    total_pet_water_glasses = 0
    days_with_data = 0
    
    for i, day_date in enumerate(reversed(week_dates)):  # От старых к новым
        day_str = day_date.isoformat()
        weekday_name = weekdays_ru[day_date.weekday()]
        
        if day_str in user.daily_stats:
            stats = user.daily_stats[day_str]
            has_data = False
            
            day_lines = [f"\n📅 {weekday_name}:"]
            
            # Сон
            if stats.sleep_minutes > 0:
                hours = stats.sleep_minutes // 60
                minutes = stats.sleep_minutes % 60
                total_sleep_minutes += stats.sleep_minutes
                has_data = True
                
                # Сравнение с выдрой
                if stats.pet_sleep_minutes > 0:
                    pet_hours = stats.pet_sleep_minutes // 60
                    pet_minutes = stats.pet_sleep_minutes % 60
                    day_lines.append(
                        f"   💤 Ты спал(а) {hours}ч {minutes}м, "
                        f"выдра спала {pet_hours}ч {pet_minutes}м."
                    )
                    total_pet_sleep_minutes += stats.pet_sleep_minutes
                else:
                    day_lines.append(f"   💤 Ты спал(а) {hours}ч {minutes}м.")
            
            # Вода
            if stats.water_liters > 0:
                total_water_liters += stats.water_liters
                has_data = True
                
                # Сравнение с выдрой
                if stats.pet_water_glasses > 0:
                    glass_volume_liters = user.settings.glass_volume_ml / 1000.0
                    pet_water_liters = stats.pet_water_glasses * glass_volume_liters
                    day_lines.append(
                        f"   💧 Ты выпил(а) {stats.water_liters:.2f}л, "
                        f"выдра выпила {stats.pet_water_glasses} стаканов ({pet_water_liters:.2f}л)."
                    )
                    total_pet_water_glasses += stats.pet_water_glasses
                else:
                    day_lines.append(f"   💧 Ты выпил(а) {stats.water_liters:.2f}л.")
                
                # Проверка нормы
                norm = user.settings.water_norm_liters
                if stats.water_liters >= norm:
                    day_lines.append(f"   ✅ Норма воды достигнута ({norm}л/день)")
                else:
                    remaining = norm - stats.water_liters
                    day_lines.append(f"   ⚠️ Не достигнута норма. Осталось {remaining:.2f}л до нормы ({norm}л/день)")
            
            if has_data:
                lines.extend(day_lines)
                days_with_data += 1
    
    if days_with_data == 0:
        lines.append("\n📝 Данных за эту неделю пока нет.")
        lines.append("Начни записывать свой сон и воду через 'Действия с выдрой'!")
        return "\n".join(lines)
    
    # Итоговая статистика
    lines.append("\n" + "="*30)
    lines.append("\n📈 Итоги за неделю:\n")
    
    # Сон
    if total_sleep_minutes > 0:
        total_hours = total_sleep_minutes / 60
        avg_hours = total_hours / 7
        lines.append(f"💤 Сон:")
        lines.append(f"   Ты спал(а) {total_hours:.1f} часов за неделю.")
        if total_pet_sleep_minutes > 0:
            pet_total_hours = total_pet_sleep_minutes / 60
            lines.append(f"   Выдра спала {pet_total_hours:.1f} часов.")
        lines.append(f"   В среднем {avg_hours:.1f} часов в день.")
    
    # Вода
    if total_water_liters > 0:
        norm_per_week = user.settings.water_norm_liters * 7
        avg_per_day = total_water_liters / 7
        lines.append(f"\n💧 Вода:")
        lines.append(f"   Ты выпил(а) {total_water_liters:.2f}л за неделю.")
        if total_pet_water_glasses > 0:
            glass_volume_liters = user.settings.glass_volume_ml / 1000.0
            pet_total_liters = total_pet_water_glasses * glass_volume_liters
            lines.append(f"   Выдра выпила {total_pet_water_glasses} стаканов ({pet_total_liters:.2f}л).")
        lines.append(f"   В среднем {avg_per_day:.2f}л в день.")
        lines.append(f"   Норма: {user.settings.water_norm_liters}л/день ({norm_per_week:.1f}л/неделю).")
        if total_water_liters >= norm_per_week:
            lines.append(f"   ✅ Норма за неделю достигнута!")
        else:
            remaining = norm_per_week - total_water_liters
            lines.append(f"   ⚠️ Осталось {remaining:.2f}л до нормы за неделю.")
    
    # Соблюдение советов
    advice_state = user.advice_state
    if advice_state.weekly_answers:
        lines.append(f"\n💡 Соблюдение советов:")
        total_weeks = len(advice_state.weekly_answers)
        followed_weeks = sum(1 for v in advice_state.weekly_answers.values() if v)
        lines.append(f"   За последние {total_weeks} недель(и) ты соблюдал(а) советы {followed_weeks} раз(а).")
        if followed_weeks > 0:
            percentage = (followed_weeks / total_weeks) * 100
            lines.append(f"   Это {percentage:.0f}% времени. Отлично! 👍")
    
    return "\n".join(lines)
