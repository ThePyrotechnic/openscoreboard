from _collections import defaultdict
from dataclasses import dataclass, field
import logging
import math
from os import PathLike
from pathlib import Path
import subprocess
from typing import Dict, Union, List, Iterable, Tuple

import yaml

import OpenScore._Parser as Parser

_logger = logging.getLogger(__name__)


# TODO see usage; there must be a better way to do that with dataclasses
def defaultdict_int():
    return defaultdict(int)


def add_dict_keys_to_obj(keys: Iterable[str], from_dict: dict, obj: object):
    """
    For each specified key in the dict, set obj's values to from_dict's value at the key.
    Update references only; do not copy object values.
    """
    for k in keys:
        obj.__dict__[k] = from_dict[k]


class _Weapon:
    pass


class _Shot:
    pass


class _Hit:
    pass


class _Death:
    pass


@dataclass
class _Player:
    shots: List[_Shot] = field(default_factory=list)
    hits_given: List[_Hit] = field(default_factory=list)
    hits_taken: List[_Hit] = field(default_factory=list)
    kills: List[_Death] = field(default_factory=list)
    deaths: List[_Death] = field(default_factory=list)
    assists: List[_Death] = field(default_factory=list)
    last_orientation: dict = field(default_factory=dict)
    orientation_history: List[Dict[str, Dict]] = field(default_factory=list)
    footsteps: int = 0
    started_with_bomb: int = False
    bomb_carry_intervals: List[Tuple[int, int]] = field(default_factory=list)
    bomb_planted_tick: int = None

    _bomb_carry_start: int = None

    def update_orientation(self, orientation_data: dict, tick: int):
        """
        Set self.last_orientation's "position" and "facing" keys with the values in the given dict
        :param orientation_data: A dict with "position" and "facing" keys
        :param tick: The tick that the orientation data comes from
        """
        steamid64 = orientation_data.get("steamid64")
        if steamid64 is not None and steamid64 != "0":
            last_orientation = {
                "position": orientation_data["position"],
                "facing": orientation_data["facing"],
                "tick": tick
            }
            self.last_orientation = last_orientation
            self.orientation_history.append(last_orientation)
        else:
            _logger.info("Ignoring position update for player 0")


class _Round:
    def __init__(self, start_tick: int, overtime: bool = False):
        self.players: Dict[int, _Player] = defaultdict(_Player)
        self.overtime: bool = overtime
        self.start_tick = start_tick


@dataclass
class _GameState:
    time: int = 0
    round: int = 0
    match_is_live: bool = False
    can_buy: bool = False
    score: dict = field(default_factory=defaultdict_int)
    rounds: List[_Round] = field(default_factory=list)
    overtime: bool = False
    overtime_count = 0


class Demo:
    def __init__(self, demo_path: Union[str, PathLike], demo_type: str, config_path: Union[str, PathLike]):
        # Convert string paths to path objects for ease of use
        self.demo_type = demo_type
        self.demo_path = str_to_path(demo_path)
        self.config_path = str_to_path(config_path)
        self.gamestate = None
        self.tick_rate = 64 if demo_type == "valve" else 128  # TODO extract from demo
        self.freeze_time = 15
        self.buy_time = 20 if demo_type == "valve" else 15

        with open(self.config_path) as config_file:
            self._config = yaml.safe_load(config_file)

    def time_to_ticks(self, seconds: float) -> int:
        """
        Convert a given amount of time to ticks
        :param seconds: The amount of time to convert. Can be fractional
        :return: The amount of ticks that would contain the given amount of time, rounded to the next whole tick
        """
        return math.ceil(self.tick_rate * seconds)

    def ticks_to_time(self, ticks: int) -> float:
        """
        Convert a given amount of ticks to time in seconds
        :param ticks: The amount of ticks to convert
        :return: The seconds that would contain the given amount of ticks
        """
        return math.ceil(ticks / self.tick_rate)

    def parse_demo(self, skip_processing: bool = False):
        tmp_dir = Path(self._config["tmp_dir"])
        tmp_dir.mkdir(parents=True, exist_ok=True)

        demoinfogo_exe = Path(self._config["demoinfogo_path"]) / Path("demoinfogo")
        output_path = tmp_dir / Path("output.txt")

        if not skip_processing:
            with open(output_path, "w") as output_file:
                subprocess.run([demoinfogo_exe, self.demo_path, "-gameevents", "-extrainfo"],
                               stdout=output_file, check=True)

        # Reset the gamestate
        self.gamestate = _GameState()

        restart_counter = 0  # For ESEA demos
        for event in Parser.parse(output_path):
            if not self.gamestate.match_is_live:  # Ignore the warmup
                if self.demo_type == "esea":
                    if event["event_type"] == "begin_new_match":
                        restart_counter += 1
                        if restart_counter == 4:
                            restart_counter = 0
                            self.gamestate.round += 1
                            self.gamestate.match_is_live = True
                            self.gamestate.can_buy = True
                            self.gamestate.round_start_tick = event["tick"]
                            self.gamestate.rounds.append(_Round(start_tick=event["tick"]))
                elif self.demo_type == "valve":
                    raise NotImplementedError("Valve demos are not currently supported")

            else:  # Match is live
                current_round_players = self.gamestate.rounds[-1].players
                player_id, attacker_id, assister_id = None, None, None

                # Set IDs and update last known positions
                # There will never bee an attacker/assister without a player/attacker, so keep these nested
                if event.get("userid"):
                    player_id = event["userid"]["player_id"]
                    current_round_players[player_id].update_orientation(event["userid"], event["tick"])

                    if event.get("attacker_id"):
                        attacker_id = event["attacker"]["player_id"]
                        current_round_players[attacker_id].update_orientation(event["attacker"], event["tick"])

                        if event.get("assister"):
                            assister_id = event["assister"]["player_id"]
                            current_round_players[assister_id].update_orientation(event["assister"], event["tick"])

                # If buy_time + freeze_time seconds have passed, buy time is expired
                if self.gamestate.can_buy and \
                        self.ticks_to_time(
                            event["tick"] - self.gamestate.round_start_tick) > self.buy_time + self.freeze_time:
                    self.gamestate.can_buy = False

                # This occurs on the first tick of a new round
                # (When players respawn at the buyzones)
                if event["event_type"] == "round_prestart":
                    self.gamestate.round += 1
                    self.gamestate.rounds.append(_Round(overtime=self.gamestate.overtime, start_tick=event["tick"]))
                    self.gamestate.round_start_tick = event["tick"]
                    self.gamestate.can_buy = True

                elif event["event_type"] == "round_end":
                    if event["winner"] == 2:
                        self.gamestate.score["t"] += 1
                    elif event["winner"] == 3:
                        self.gamestate.score["ct"] += 1

                    if self.demo_type == "esea":
                        if self.gamestate.overtime:
                            # Someone won in overtime
                            if self.gamestate.score["t"] == overtime_score_target or \
                                    self.gamestate.score["ct"] == overtime_score_target:
                                break

                            # Need another overtime
                            if self.gamestate.score["t"] == overtime_score_target - 1 and \
                                    self.gamestate.score["ct"] == overtime_score_target - 1:
                                overtime_score_target += 3
                        else:
                            # Someone won
                            if self.gamestate.score["t"] == 16 or self.gamestate.score["ct"] == 16:
                                break

                            # Overtime
                            if self.gamestate.score["t"] == 15 and self.gamestate.score["ct"] == 15:
                                self.gamestate.overtime = True
                                overtime_score_target = 19

                        # Switch sides
                        if self.gamestate.round == 15:
                            if self.demo_type == "esea":  # Must wait 3 more restarts
                                # NOTE: This means that all events after the "T/CTs win" message will be ignored
                                self.gamestate.match_is_live = False

                            temp_score = self.gamestate.score["t"]
                            self.gamestate.score["t"] = self.gamestate.score["ct"]
                            self.gamestate.score["ct"] = temp_score

                elif event["event_type"] == "bomb_pickup":
                    if event["tick"] == self.gamestate.round_start_tick:
                        current_round_players[player_id].started_with_bomb = True

                    current_round_players[player_id]._bomb_carry_start = event["tick"]

                elif event["event_type"] in ("bomb_dropped", "bomb_planted"):
                    carry_start_tick = current_round_players[player_id]._bomb_carry_start
                    carry_end_tick = event["tick"]
                    current_round_players[player_id].bomb_carry_intervals.append((carry_start_tick, carry_end_tick))

                    if event["event_type"] == "bomb_planted":
                        current_round_players[player_id].bomb_planted_tick = event["tick"]

                elif event["event_type"] == "player_footstep":
                    current_round_players[player_id].footsteps += 1

                elif event["event_type"] == "weapon_fire":
                    player_id = event["userid"]["player_id"]
                    shot = _Shot()
                    add_dict_keys_to_obj(
                        ["userid", "weapon", "silenced", "tick"],
                        event,
                        shot
                    )
                    current_round_players[player_id].shots.append(shot)

                elif event["event_type"] == "player_death":
                    death = _Death()
                    add_dict_keys_to_obj(
                        ["userid", "attacker", "assister", "assistedflash", "weapon", "weapon_itemid", "headshot",
                         "penetrated", "tick"],
                        event,
                        death
                    )
                    current_round_players[player_id].deaths.append(death)
                    current_round_players[attacker_id].kills.append(death)
                    current_round_players[assister_id].assists.append(death)

                elif event["event_type"] == "player_hurt":
                    if player_id != 0:
                        hit = _Hit()
                        add_dict_keys_to_obj(
                            ["userid", "attacker", "health", "armor", "weapon", "dmg_health", "dmg_armor",
                             "hitgroup", "tick"],
                            event,
                            hit
                        )
                        current_round_players[player_id].hits_taken.append(hit)
                        current_round_players[attacker_id].hits_given.append(hit)

        print(self.gamestate.score["t"], self.gamestate.score["ct"])


def str_to_path(path: Union[str, PathLike]) -> PathLike:
    if isinstance(path, str):
        path = Path(path)
    return path
