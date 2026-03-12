def get_reputation_level(rep: float) -> str:
    if rep >= 1.4:
        return "platinum"
    if rep >= 1.2:
        return "gold"
    if rep >= 0.9:
        return "silver"
    return "bronze"


REPUTATION_MULTIPLIER = {
    "bronze": 1.0,
    "silver": 1.1,
    "gold": 1.25,
    "platinum": 1.5
}
