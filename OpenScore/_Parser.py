import logging
from os import PathLike
from typing import Dict, Union, Tuple

_logger = logging.getLogger(__name__)


def parse(event_file_path: Union[str, PathLike]) -> Dict:
    """
    Very rudimentary parser for demoinfogo output. Only supports 2 indentation levels
    :param event_file_path: The path to the demoinfogo output file
    :yield: The next event from the demoinfogo output
    """
    current_event = {}
    last_indent = 1
    building_event = False
    last_line = None
    with open(event_file_path) as event_file:
        for line_number, line in enumerate(event_file):
            line = line.rstrip()

            if any([line.startswith(s) for s in ["Cannot", "userid"]]) or \
                    any([line.endswith(s) for s in ["Disconnect", "disconnected"]]):
                _logger.info(f"Skipping comment line {line_number}: {line}")
            elif not building_event:
                current_event["event_type"] = line
                current_event["line_number"] = line_number
                building_event = True
            elif line == "{":
                pass
            elif line == "}":
                yield current_event
                building_event = False
                current_event = {}
            else:
                indent_amount, key, data = _parse_line(line, last_line)

                if indent_amount != last_indent:
                    parent_key = last_key
                last_key = key
                last_indent = indent_amount

                if indent_amount == 1:
                    current_event[key] = data
                else:
                    current_event[parent_key][key] = data
            last_line = line


def _parse_line(line: str, last_line: str) -> Tuple[int, str, Dict]:
    """
    Parse a line of input from demoinfogo and return it as Python data
    :param line: The line to parse
    :param last_line: The last line that was parsed
    :return: The indentation level of the line, the key on the line, and that key's value
    """
    # Keys of the form <Username> <SteamID64> <Player ID>
    user_keys = ("userid", "attacker", "assister")

    # Keys with string values which require no processing
    simple_keys = ("team", "item", "weapon", "master", "message", "funfact_token", "objective", "othertype")

    # Keys with values of 0 or 1
    bool_keys = (
        "canzoom", "hassilencer", "ispainted", "issilenced", "silenced", "hastracers", "ineye", "assistedflash",
        "headshot", "dominated", "revenge", "wipe", "penetrated", "noreplay", "disconnect", "autoteam", "silent",
        "isbot", "legacy", "nomusic", "show_timer_defend", "show_timer_attack", "haskit")

    # Keys with integer values
    int_keys = (
        "defindex", "weptype", "target1", "target2", "entityid", "health", "armor", "dmg_health", "dmg_armor",
        "hitgroup", "weapon_itemid", "weapon_fauxitemid", "weapon_originalowner_xuid", "oldteam", "teamnum", "clients",
        "slots", "proxies", "externaltotal", "externallinked", "winner", "reason", "player_count", "timer_time",
        "final_event", "funfact_player", "funfact_data1", "funfact_data2", "funfact_data3", "timelimit", "fraglimit",
        "entindex", "site", "otherid", "tick", "account")

    # Keys with float values (or int keys which could theoretically hold float values)
    float_keys = ("theta", "phi", "inertia", "distance", "x", "y", "z", "blind_duration", "damage")

    key, value = line.lstrip(" ").split(":", maxsplit=1)
    value = value.strip()

    indent_amount = len(line) - len(line.lstrip(" "))

    if key == "position":
        x, y, z = value.split(",")
        data = {
            "x": float(x),
            "y": float(y),
            "z": float(z)
        }
    elif key == "facing":
        _, pitch, yaw = value.split(":")
        pitch = float(pitch.split(",")[0])
        yaw = float(yaw)
        data = {
            "pitch": pitch,
            "yaw": yaw
        }
    elif key in user_keys:
        try:
            *username, steamid64, player_id = value.split(" ")
            username = " ".join(username)
            player_id = player_id.strip("id:()")
            data = {
                "username": username,
                "steamid64": steamid64,
                "player_id": player_id
            }
        except ValueError as e:
            if last_line.startswith("Cannot find player"):
                data = {
                    "player_id": int(value)
                }
            else:
                raise e
    elif key in simple_keys:
        data = value
    elif key in bool_keys:
        data = bool(int(value))
    elif key in int_keys:
        data = "" if value == "" else int(value)
    elif key in float_keys:
        data = "" if value == "" else float(value)
    else:
        _logger.warning(f"Unknown key: {key}")
        data = {"data": value}

    return indent_amount, key, data
