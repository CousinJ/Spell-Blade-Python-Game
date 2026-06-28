"""Server-side rules lookup over :mod:`coordinator.action_data`.

A thin, validated service the coordinator uses to interpret ``action_id`` strings
arriving from clients. Pygame-free.
"""
from __future__ import annotations

from coordinator import action_data
from coordinator.action_data import ActionData


class RulesError(ValueError):
    """Raised for an unknown action id or invalid hero."""


def get_action(action_id: str) -> ActionData:
    a = action_data.ACTIONS.get(action_id)
    if a is None:
        raise RulesError(f"unknown action_id: {action_id!r}")
    return a


def is_attack(action_id: str) -> bool:
    return action_id in action_data.ATTACK_ACTIONS


def damage_of(action_id: str) -> int:
    return get_action(action_id).damage


def is_valid_hero(hero: str) -> bool:
    return hero in action_data.HEROES


def hero_attacks(hero: str) -> list[str]:
    if hero not in action_data.HEROES:
        raise RulesError(f"unknown hero: {hero!r}")
    return list(action_data.HEROES[hero]["attacks"])
