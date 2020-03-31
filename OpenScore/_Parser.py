import logging
from os import PathLike
from typing import Dict, Union


_logger = logging.getLogger(__name__)


def parse(event_file_path: Union[str, PathLike]) -> Dict:
    """Very rudimentary parser for output. Only supports 2 indentation levels"""
    current_event = {}
    last_indent = 1
    building_event = False
    with open(event_file_path) as event_file:
        for line in event_file:
            line = line.rstrip()
            if not building_event:
                current_event["title"] = line
                building_event = True
            elif line == "{":
                pass
            elif line == "}":
                yield current_event
                building_event = False
                current_event = {}
            else:
                try:
                    indent_amount, key, data = _parse_line(line)
                except ValueError as e:
                    if line.startswith("Cannot"):
                        _logger.info(f"Skipping comment line: {line}")
                    else:
                        raise e

                if indent_amount != last_indent:
                    parent_key = last_key
                last_key = key
                last_indent = indent_amount

                if indent_amount == 1:
                    current_event[key] = data
                else:
                    current_event[parent_key][key] = data


def _parse_line(line: str) -> Union[int, str, Dict]:
    key, value = line.lstrip(" ").split(":", maxsplit=1)

    indent_amount = len(line) - len(line.lstrip(" "))

    if key == "userid":
        # TODO usernames might have spaces so this won't work
        username, steamid64, player_id = value.split(" ")[1:]
        player_id = player_id.strip("id:()")
        data = {
            "username": username,
            "steamid64": steamid64,
            "player_id": player_id
        }
    else:
        _logger.warning(f"Unknown key: {key}")
        data = {"data": value}

    return indent_amount, key, data
