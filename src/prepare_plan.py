"""Local T02 web page. Only explicit AI POST actions can create paid requests."""

import argparse

from app import create_app


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8010)
    args = parser.parse_args()
    create_app().run(host="127.0.0.1", port=args.port, debug=False)
