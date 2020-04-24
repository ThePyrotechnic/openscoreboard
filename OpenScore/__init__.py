from collections import defaultdict
from dataclasses import dataclass, field
import logging
import math
from os import PathLike
from pathlib import Path
import subprocess
from typing import Dict, Union, List, Iterable, Tuple

import yaml

import OpenScore._Parser as Parser
import OpenScore._Constants as Constants

_logger = logging.getLogger(__name__)


# TODO see usage; there must be a better way to do that with dataclasses
def _defaultdict_int():
    return defaultdict(int)


def _add_dict_keys_to_obj(keys: Iterable[str], from_dict: dict, obj: object):
    """
    For each specified key in the dict, set obj's values to from_dict's value at the key.
    Update references only; do not copy object values.
    """
    for k in keys:
        obj.__dict__[k] = from_dict[k]


def str_to_path(path: Union[str, PathLike]) -> PathLike:
    if isinstance(path, str):
        path = Path(path)
    return path


@dataclass
class Defusal:
    success: bool = False
    defuse_tick: int = None


class Weapon:
    pass


class Shot:
    pass


class Hit:
    pass


class Death:
    pass


@dataclass
class Player:
    shots: List[Shot] = field(default_factory=list)
    hits_given: List[Hit] = field(default_factory=list)
    hits_taken: List[Hit] = field(default_factory=list)
    kills: List[Death] = field(default_factory=list)
    deaths: List[Death] = field(default_factory=list)
    assists: List[Death] = field(default_factory=list)
    last_orientation: dict = field(default_factory=dict)
    orientation_history: List[Dict[str, Dict]] = field(default_factory=list)
    footsteps: int = 0
    started_with_bomb: int = False
    bomb_carry_intervals: List[Tuple[int, int]] = field(default_factory=list)
    bomb_planted_tick: int = None
    bomb_defusal_attempts: List[Defusal] = field(default_factory=list)

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


class Round:
    def __init__(self, start_tick: int, overtime: bool = False):
        self.players: Dict[int, Player] = defaultdict(Player)
        self.overtime: bool = overtime
        self.start_tick = start_tick
        self.end_tick = None
        self.end_reason = None


@dataclass
class GameState:
    round: int = 0
    match_is_live: bool = False
    score: dict = field(default_factory=_defaultdict_int)
    rounds: List[Round] = field(default_factory=list)

    _can_buy: bool = False
    _overtime: bool = False
    _overtime_count = 0


class Demo:
    def __init__(self, demo_path: Union[str, PathLike], demo_type: str, config_path: Union[str, PathLike],
                 skip_processing: bool = False):
        # Convert string paths to path objects for ease of use
        self._demo_type = demo_type
        self._demo_path = str_to_path(demo_path)
        self._config_path = str_to_path(config_path)
        self.gamestate = None
        self.tick_rate = 64 if demo_type == "valve" else 128  # TODO extract from demo
        self.freeze_time = 15
        self.buy_time = 20 if demo_type == "valve" else 15

        with open(self._config_path) as config_file:
            self._config = yaml.safe_load(config_file)

        self._parse_demo(skip_processing)

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

    def _parse_demo(self, skip_processing: bool = False):
        tmp_dir = Path(self._config["tmp_dir"])
        tmp_dir.mkdir(parents=True, exist_ok=True)

        demoinfogo_exe = Path(self._config["demoinfogo_path"]) / Path("demoinfogo")
        output_path = tmp_dir / Path("output.txt")

        if not skip_processing:
            with open(output_path, "w") as output_file:
                subprocess.run([demoinfogo_exe, self._demo_path, "-gameevents", "-extrainfo"],
                               stdout=output_file, check=True)

        # Reset the gamestate
        self.gamestate = GameState()

        restart_counter = 0  # For ESEA demos
        for event in Parser.parse(output_path):
            if not self.gamestate.match_is_live:  # Ignore the warmup
                if self._demo_type == "esea":
                    if event["event_type"] == "begin_new_match":
                        restart_counter += 1
                        if restart_counter == 4:
                            restart_counter = 0
                            self.gamestate.round += 1
                            self.gamestate.match_is_live = True
                            self.gamestate._can_buy = True
                            self.gamestate.round_start_tick = event["tick"]
                            self.gamestate.rounds.append(Round(start_tick=event["tick"]))
                elif self._demo_type == "valve":
                    raise NotImplementedError("Valve demos are not currently supported")

            else:  # Match is live
                current_round_players = self.gamestate.rounds[-1].players
                player_id, attacker_id, assister_id = None, None, None

                # Set IDs and update last known positions
                # There will never be an attacker/assister without a player/attacker, so keep these nested
                if event.get("userid"):
                    player_id = event["userid"]["player_id"]
                    current_round_players[player_id].update_orientation(event["userid"], event["tick"])

                    if event.get("attacker"):
                        attacker_id = event["attacker"]["player_id"]
                        current_round_players[attacker_id].update_orientation(event["attacker"], event["tick"])

                        if event.get("assister"):
                            assister_id = event["assister"]["player_id"]
                            current_round_players[assister_id].update_orientation(event["assister"], event["tick"])

                # If buy_time + freeze_time seconds have passed, buy time has expired
                if self.gamestate._can_buy and \
                        self.ticks_to_time(
                            event["tick"] - self.gamestate.round_start_tick) > self.buy_time + self.freeze_time:
                    self.gamestate._can_buy = False

                # This occurs on the first tick of a new round
                # (When players respawn at the buyzones)
                if event["event_type"] == "round_prestart":
                    self.gamestate.round += 1
                    self.gamestate.rounds.append(Round(overtime=self.gamestate._overtime, start_tick=event["tick"]))
                    self.gamestate.round_start_tick = event["tick"]
                    self.gamestate._can_buy = True

                elif event["event_type"] == "round_end":
                    if Constants.round_end_winners[event["winner"]] == "Terrorists":
                        self.gamestate.score["t"] += 1
                    elif Constants.round_end_winners[event["winner"]] == "Counter-Terrorists":
                        self.gamestate.score["ct"] += 1
                    self.gamestate.rounds[-1].end_reason = event["reason"]
                    self.gamestate.rounds[-1].end_tick = event["tick"]

                    if self._demo_type == "esea":
                        if self.gamestate._overtime:
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
                                self.gamestate._overtime = True
                                overtime_score_target = 19

                        # Switch sides
                        if self.gamestate.round == 15:
                            if self._demo_type == "esea":  # Must wait 3 more restarts
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

                elif event["event_type"] == "bomb_begindefuse":
                    defusal = Defusal()
                    _add_dict_keys_to_obj(
                        ["userid", "haskit", "tick"],
                        event,
                        defusal
                    )
                    current_round_players[player_id].bomb_defusal_attempts.append(defusal)

                elif event["event_type"] == "bomb_defused":
                    current_round_players[player_id].bomb_defusal_attempts[-1].success = True
                    current_round_players[player_id].bomb_defusal_attempts[-1].defuse_tick = event["tick"]

                elif event["event_type"] == "player_footstep":
                    current_round_players[player_id].footsteps += 1

                elif event["event_type"] == "weapon_fire":
                    player_id = event["userid"]["player_id"]
                    shot = Shot()
                    _add_dict_keys_to_obj(
                        ["userid", "weapon", "silenced", "tick"],
                        event,
                        shot
                    )
                    current_round_players[player_id].shots.append(shot)

                elif event["event_type"] == "player_death":
                    death = Death()
                    _add_dict_keys_to_obj(
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
                        hit = Hit()
                        _add_dict_keys_to_obj(
                            ["userid", "attacker", "health", "armor", "weapon", "dmg_health", "dmg_armor",
                             "hitgroup", "tick"],
                            event,
                            hit
                        )
                        current_round_players[player_id].hits_taken.append(hit)
                        current_round_players[attacker_id].hits_given.append(hit)
