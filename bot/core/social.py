from dataclasses import dataclass, asdict
from typing import Dict, List

from bot.storage.json_db import JsonDB


@dataclass
class Room:
    id: str
    type: str  # "work" или "lunch"
    users: List[int]


class SocialRooms:
    """
    Примитивные "комнаты" для совместных активностей:
    совместная работа или совместный обед.
    """

    def __init__(self) -> None:
        self._db = JsonDB("social_rooms.json")

    def _load_all(self) -> Dict[str, Room]:
        raw = self._db.get_all()
        return {rid: Room(**data) for rid, data in raw.items()}

    def _save_all(self, rooms: Dict[str, Room]) -> None:
        self._db._write({rid: asdict(room) for rid, room in rooms.items()})  # type: ignore

    def join(self, room_id: str, room_type: str, user_id: int) -> Room:
        rooms = self._load_all()
        room = rooms.get(room_id)
        if room is None:
            room = Room(id=room_id, type=room_type, users=[])
            rooms[room_id] = room
        if user_id not in room.users:
            room.users.append(user_id)
        self._save_all(rooms)
        return room

