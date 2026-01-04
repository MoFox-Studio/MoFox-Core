import hashlib

JSON_SERIALIZED_FIELDS = ["points", "forgotten_points", "info_list"]

person_info_default = {
    "person_id": None,
    "person_name": None,
    "name_reason": None,
    "platform": "unknown",
    "user_id": "unknown",
    "nickname": "Unknown",
    "know_times": 0,
    "know_since": None,
    "last_know": None,
    "impression": None,
    "short_impression": None,
    "info_list": None,
    "points": None,
    "forgotten_points": None,
    "relation_value": None,
    "attitude": 50,
}


def get_person_id(platform: str, user_id: int | str) -> str:
    """Return stable MD5-based person_id for platform/user_id pair."""
    if platform is None:
        platform = "unknown"

    if "-" in platform:
        platform = platform.split("-")[1]

    key = "_".join([platform, str(user_id)])
    return hashlib.md5(key.encode()).hexdigest()


__all__ = ["JSON_SERIALIZED_FIELDS", "person_info_default", "get_person_id"]
