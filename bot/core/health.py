"""
Механика здоровья и смерти выдры
"""
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import List

from bot.core.models import UserState


class HealthState(Enum):
    """Состояние здоровья выдры"""
    HEALTHY = "healthy"  # Здорова (все параметры > 50)
    OK = "ok"  # Нормально (все параметры > 30)
    POOR = "poor"  # Плохо (хотя бы один параметр 20-30)
    VERY_POOR = "very_poor"  # Очень плохо (хотя бы один параметр 10-20)
    CRITICAL = "critical"  # Критическое (хотя бы один параметр < 10)
    DEAD = "dead"  # Мертва


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def get_health_state(pet) -> HealthState:
    """Определяет текущее состояние здоровья выдры"""
    if not pet.is_alive:
        return HealthState.DEAD
    
    min_stat = min(pet.happiness, pet.hunger, pet.thirst, pet.energy)
    
    if min_stat >= 50:
        return HealthState.HEALTHY
    elif min_stat >= 30:
        return HealthState.OK
    elif min_stat >= 20:
        return HealthState.POOR
    elif min_stat >= 10:
        return HealthState.VERY_POOR
    else:
        return HealthState.CRITICAL


def get_health_status_message(pet) -> str:
    """Возвращает сообщение о состоянии здоровья"""
    state = get_health_state(pet)
    
    if state == HealthState.HEALTHY:
        return "Выдра чувствует себя отлично! 💪"
    elif state == HealthState.OK:
        return "Выдра чувствует себя хорошо 😊"
    elif state == HealthState.POOR:
        return "Выдра чувствует себя не очень хорошо 😔"
    elif state == HealthState.VERY_POOR:
        return "Выдра чувствует себя очень плохо! Нужна помощь! 😰"
    elif state == HealthState.CRITICAL:
        return "⚠️ КРИТИЧЕСКОЕ СОСТОЯНИЕ! Выдра может умереть, если не получит помощь!"
    else:
        return "Выдра мертва 💀"


def touch_pet(user: UserState) -> None:
    """
    Обновляет время последнего взаимодействия.
    """
    user.pet.last_interaction = _now_iso()


def degrade_pet(user: UserState) -> None:
    """
    Улучшенная деградация состояний питомца по времени.
    
    Изменения:
    - Более мягкие таймауты (смерть через 48-72 часа, а не 16-17)
    - Промежуточные состояния (плохо, очень плохо, критическое)
    - Смерть от комбинации факторов, а не одного параметра
    - Режим отпуска для редких пользователей
    """
    pet = user.pet
    
    # Если выдра уже мертва, не деградируем дальше
    if not pet.is_alive:
        return
    
    # Если выдра в режиме отпуска, не деградируем
    if pet.vacation_mode:
        return
    
    if not pet.last_interaction:
        pet.last_interaction = _now_iso()
        return

    try:
        last = datetime.fromisoformat(pet.last_interaction)
    except Exception:
        last = datetime.now(timezone.utc)

    now = datetime.now(timezone.utc)
    delta: timedelta = now - last
    hours = delta.total_seconds() / 3600

    if hours <= 0:
        return

    # Более мягкая деградация (смерть через 48-72 часа вместо 16-17)
    # За каждый час без взаимодействия:
    degradation_rate = 1.0  # Базовый коэффициент (смягчен)
    
    # Если прошло больше 24 часов, немного ускоряем деградацию
    if hours > 24:
        degradation_rate = 1.2
    if hours > 48:
        degradation_rate = 1.5
    
    pet.happiness = max(0, int(pet.happiness - 1.5 * hours * degradation_rate))
    pet.hunger = max(0, int(pet.hunger - 2.0 * hours * degradation_rate))
    pet.thirst = max(0, int(pet.thirst - 2.0 * hours * degradation_rate))
    pet.energy = max(0, int(pet.energy - 0.8 * hours * degradation_rate))
    
    # Усталость тоже немного влияет на счастье и энергию
    if pet.fatigue > 70:
        pet.happiness = max(0, pet.happiness - 1)
        pet.energy = max(0, pet.energy - 1)

    # Проверяем состояние здоровья
    health_state = get_health_state(pet)
    
    # Если критическое состояние - запоминаем время
    if health_state == HealthState.CRITICAL:
        if not pet.critical_state_since:
            pet.critical_state_since = _now_iso()
    else:
        pet.critical_state_since = None
    
    # Условия смерти - ТОЛЬКО при комбинации факторов
    # Выдра умирает, если:
    # 1. В критическом состоянии более 24 часов И
    # 2. Хотя бы 2 параметра на 0 ИЛИ все 4 параметра < 5
    
    if health_state == HealthState.CRITICAL and pet.critical_state_since:
        try:
            critical_since = datetime.fromisoformat(pet.critical_state_since)
            critical_hours = (now - critical_since).total_seconds() / 3600
            
            # Проверяем комбинацию факторов
            zero_params = sum([
                1 if pet.happiness <= 0 else 0,
                1 if pet.hunger <= 0 else 0,
                1 if pet.thirst <= 0 else 0,
                1 if pet.energy <= 0 else 0,
            ])
            
            very_low_params = sum([
                1 if pet.happiness < 5 else 0,
                1 if pet.hunger < 5 else 0,
                1 if pet.thirst < 5 else 0,
                1 if pet.energy < 5 else 0,
            ])
            
            # Условие смерти: критическое состояние 24+ часов И (2+ параметра на 0 ИЛИ все 4 < 5)
            if critical_hours >= 24 and (zero_params >= 2 or very_low_params == 4):
                pet.is_alive = False
                pet.critical_state_since = None
        except Exception:
            pass
    
    # Режим отпуска для редких пользователей (если не было взаимодействия > 72 часов)
    # Вместо смерти - переводим в режим отпуска
    if hours > 72 and not pet.vacation_mode:
        # Проверяем, не была ли выдра уже в критическом состоянии
        if health_state in [HealthState.CRITICAL, HealthState.VERY_POOR]:
            # Если была в плохом состоянии - умирает
            if zero_params >= 2 or very_low_params == 4:
                pet.is_alive = False
            else:
                # Иначе - режим отпуска
                pet.vacation_mode = True
                pet.happiness = 30
                pet.hunger = 30
                pet.thirst = 30
                pet.energy = 30

    pet.last_interaction = _now_iso()


def check_critical_warnings(pet) -> List[str]:
    """
    Проверяет, нужны ли предупреждения о критическом состоянии.
    Возвращает список сообщений-предупреждений.
    """
    warnings = []
    health_state = get_health_state(pet)
    
    if health_state == HealthState.CRITICAL:
        if pet.hunger < 10:
            warnings.append("🆘 Выдра очень голодна! Нужно срочно покормить!")
        if pet.thirst < 10:
            warnings.append("🆘 Выдра очень хочет пить! Нужно срочно дать воды!")
        if pet.happiness < 10:
            warnings.append("🆘 Выдра очень несчастна! Нужна забота и внимание!")
        if pet.energy < 10:
            warnings.append("🆘 Выдра очень устала! Нужен сон и отдых!")
        
        if pet.critical_state_since:
            try:
                critical_since = datetime.fromisoformat(pet.critical_state_since)
                critical_hours = (datetime.now(timezone.utc) - critical_since).total_seconds() / 3600
                if critical_hours >= 12:
                    warnings.append(f"⚠️ Выдра в критическом состоянии уже {int(critical_hours)} часов! Если не помочь в ближайшие 12 часов, она может умереть!")
            except Exception:
                pass
    
    elif health_state == HealthState.VERY_POOR:
        if pet.hunger < 20:
            warnings.append("😰 Выдра очень голодна! Покорми её, пожалуйста!")
        if pet.thirst < 20:
            warnings.append("😰 Выдра очень хочет пить! Дай ей воды!")
        if pet.happiness < 20:
            warnings.append("😰 Выдра очень несчастна! Проведи с ней время!")
    
    elif health_state == HealthState.POOR:
        if pet.hunger < 30:
            warnings.append("😔 Выдра голодна. Не забудь покормить её.")
        if pet.thirst < 30:
            warnings.append("😔 Выдра хочет пить. Не забудь дать воды.")
    
    return warnings
