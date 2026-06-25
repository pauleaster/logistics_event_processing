"""
Simple password generator to be used by the setup process.
Note that this does not use non alphanumeric characters.
This is only to aid quoting/escaping issues when using the generated password in shell commands.
Production use should definitely use a more secure password generator that includes special characters.
"""

#!/usr/bin/env python3

import argparse
import secrets
import string


def generate_alphanumeric_password(length: int = 24) -> str:
    if length < 12:
        raise ValueError("Password length should be at least 12 characters.")

    alphabet = string.ascii_letters + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(length))


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate a local alphanumeric password."
    )
    parser.add_argument(
        "--length",
        type=int,
        default=24,
        help="Password length. Default: 24.",
    )
    args = parser.parse_args()

    password = generate_alphanumeric_password(args.length)
    print(password)


if __name__ == "__main__":
    main()