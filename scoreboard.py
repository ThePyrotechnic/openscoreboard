import argparse
import logging

import OpenScore


def main(args):
    d = OpenScore.Demo(args.demo, args.type, args.config)
    d.parse_demo(args.skip_processing)
    pass


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate statistics for CS:GO demos")

    parser.add_argument("demo", help="The CS:GO .dem file to process")

    parser.add_argument("--config", default="config.yml", help="The path to the config YAML file")

    parser.add_argument("--type", default="valve", choices=["valve", "esea"],
                        help="Signals the matchmaking service that this demo is from")

    parser.add_argument("--skip-processing", action="store_true", help="Skip demoinfogo processing")

    parser.add_argument("--log", default="INFO", choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
                        help="Set the log level")

    parsed_args = parser.parse_args()

    # Set the log level
    logging.basicConfig(level=getattr(logging, parsed_args.log))

    main(parsed_args)
