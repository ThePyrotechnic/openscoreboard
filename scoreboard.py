import argparse
import logging

import OpenScore


def main(args):
    d = OpenScore.Demo(args.demo, args.config)
    d.process_demo(args.skip_processing)
    pass


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate statistics for CS:GO demos")

    parser.add_argument("demo", help="The CS:GO .dem file to process")

    parser.add_argument("--config", default="config.yml", help="The path to the config YAML file")

    parser.add_argument("--esea", action="store_true", help="Signals that this demo is an ESEA demo")

    parser.add_argument("--skip-processing", action="store_true", help="Skip demoinfogo processing")

    parser.add_argument("--log", default="INFO", choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
                        help="Set the log level")

    main(parser.parse_args())
