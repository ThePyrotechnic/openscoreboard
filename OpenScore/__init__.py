import logging
from dataclasses import dataclass
from os import PathLike
from pathlib import Path
import subprocess
from typing import Dict, Union

import yaml

import OpenScore._Helpers as Helpers
import OpenScore._Parser as Parser

_logger = logging.getLogger(__name__)


@dataclass
class _GameState:
    warmup: bool = True


class _EventProcessor:
    def handle_round_freeze_end(self, data: Dict):
        pass


class Demo:
    def __init__(self, demo_path: Union[str, PathLike], config_path: Union[str, PathLike]):
        # Convert string paths to path objects for ease of use
        self.demo_path = Helpers.str_to_path(demo_path)
        self.config_path = Helpers.str_to_path(config_path)

        with open(self.config_path) as config_file:
            self._config = yaml.safe_load(config_file)

    def process_demo(self, skip_processing: bool = False):
        tmp_dir = Path(self._config["tmp_dir"])
        tmp_dir.mkdir(parents=True, exist_ok=True)

        demoinfogo_exe = Path(self._config["demoinfogo_path"]) / Path("demoinfogo")
        output_path = tmp_dir / Path("output.txt")

        if not skip_processing:
            with open(output_path, "w") as output_file:
                subprocess.run([demoinfogo_exe, self.demo_path, "-gameevents", "-extrainfo"],
                               stdout=output_file, check=True)
        for data in Parser.parse(output_path):
            print(data)
