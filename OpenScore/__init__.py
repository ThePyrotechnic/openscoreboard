from io import StringIO
from os import PathLike
from pathlib import Path
from typing import Union
import struct


import logging


logger = logging.getLogger(__name__)


class Demo:
    def __init__(self, demo_path: Union[str, PathLike]):
        # Convert string paths to path objects for ease of use
        if isinstance(demo_path, str):
            demo_path = Path(demo_path)
        self.demo_path = demo_path

        # For an official explanation of the .dem format,
        #   see https://developer.valvesoftware.com/wiki/DEM_Format
        with open(demo_path, "rb") as demo_file:
            self.header = demo_file.read(8).decode(encoding="UTF-8")

            # See https://docs.python.org/3/library/struct.html#format-strings
            self.demo_protocol = struct.unpack("<i", demo_file.read(4))[0]
            self.network_protocol = struct.unpack("<i", demo_file.read(4))[0]

            self.server_name = demo_file.read(260).decode(encoding="UTF-8").split("\0")[0]
            self.client_name = demo_file.read(260).decode(encoding="UTF-8").split("\0")[0]
            self.map_name = demo_file.read(260).decode(encoding="UTF-8").split("\0")[0]
            self.game_directory = demo_file.read(260).decode(encoding="UTF-8").split("\0")[0]

            self.playback_time = struct.unpack("<f", demo_file.read(4))[0]
            self.ticks = struct.unpack("<i", demo_file.read(4))[0]
            self.frames = struct.unpack("<i", demo_file.read(4))[0]
            self.signon_length = struct.unpack("<i", demo_file.read(4))[0]

        self.tickrate = round(self.ticks / self.playback_time)

    def __str__(self) -> str:
        with StringIO() as str_output:
            str_output.write(str(self.demo_path))
            str_output.write("\n")
            for key, value in self.__dict__.items():
                str_output.write(f"\t{key}: {value}\n")

            return str_output.getvalue()
