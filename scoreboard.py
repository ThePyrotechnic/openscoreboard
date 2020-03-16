import argparse
import logging

import OpenScore


def main(args):
    d = OpenScore.Demo(args.demo)
    print(d)
    pass


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate statistics for CS:GO demos")

    parser.add_argument("demo", help="The CS:GO .dem file to process")

    parser.add_argument("--log", default="INFO", choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
                        help="Set the log level")

    main(parser.parse_args())
