#!/usr/bin/env python3
import argparse
import hashlib
import os
import pathlib
import re
from bisect import bisect
from datetime import datetime
from typing import Any, Dict, List

import mysql.connector as msc

MIGR_MATCH = re.compile("^(?P<type>[UV])(?P<num>\d+)(__(?P<desc>.+))?.sql$")

# TODO(@pdunham113): implement these checks
# migration_hash - used to ensure previous migrations haven't modified since application
# schema_hash - used to ensure schema has not changed outside of tracked migrations
MIGR_TABLE = """
    CREATE TABLE `_migration` (
        `date` DATETIME(6) DEFAULT NOW(6),
        `version` INT NOT NULL,
        `migration` VARCHAR(255) NOT NULL,
        `migration_hash` CHAR(40) COMMENT "Hash of SQL transaction used for migration + previous migration hash",
        `schema_hash` CHAR(40) COMMENT "[NOT IMPLEMENTED] Hash of full SHOW CREATE TABLE output post-migration",
        PRIMARY KEY (`date`)
    )
"""

PREFIX_TO_TYPE = {"V": "up", "U": "down"}


class Migration:
    def __init__(self, type: str, ver: int, desc: str, file: os.PathLike):
        self.type = type
        if self.type == "up":
            self.ver_from = ver - 1
            self.ver_to = ver
        elif self.type == "down":
            self.ver_from = ver
            self.ver_to = ver - 1
        else:
            raise NotImplementedError(self.type)
        self.desc = desc
        self.file = file

    @property
    def ver(self) -> int:
        if self.type == "up":
            return self.ver_to
        elif self.type == "down":
            return self.ver_from
        else:
            raise NotImplementedError(self.type)

    def __str__(self) -> str:
        return f"{self.ver}: {self.desc}"

    def __repr__(self) -> str:
        return f"{self.ver}: {self.desc:<24}\t ({self.file})"


def create(args: argparse.Namespace) -> None:
    """Creates a database & defines a migration table for use with jaunt"""
    with open(__file__, "rb") as _self:
        base_hash = hashlib.sha1(_self.read()).hexdigest()

    conn = msc.MySQLConnection(
        host=args.host,
        port=args.port,
        user=args.user,
        password=args.password,
    )

    with conn.cursor() as cursor:
        cursor.execute(f"CREATE DATABASE `{args.db}`")
        cursor.execute(f"USE `{args.db}`")
        cursor.execute(MIGR_TABLE)
        _record_migration(cursor, -1, "__baseline__", base_hash)

    conn.commit()
    conn.close()


def down(args: argparse.Namespace) -> None:
    """Apply requested migrations in order, from highest to lowest"""
    migrations = _get_migrations_from_dir(args.migration_dir)["down"]
    conn = msc.MySQLConnection(
        host=args.host,
        port=args.port,
        user=args.user,
        password=args.password,
        database=args.db,
    )

    end = bisect(migrations, args.version, key=lambda x: x.ver)

    with conn.cursor() as cursor:
        cursor.execute(
            """
                SELECT date, version, migration, migration_hash
                FROM _migration ORDER BY date DESC LIMIT 1
            """
        )
        date, curr_version, migration, migration_hash = next(cursor)
    conn.commit()

    print(f"Currently at {curr_version}: {migration} ({date})")
    start = bisect(migrations, curr_version, key=lambda x: x.ver)

    migrations = sorted(migrations[end:start], key=lambda x: x.ver, reverse=True)

    if migrations == []:
        print("WARN: No migrations to apply")
    else:
        print(f"{len(migrations)} migrations to apply:")
        for migr in migrations:
            print(f"\t{migr!r}")

        for migr in migrations:
            print(f"Applying {migr}...", end="")
            with conn.cursor() as cursor:
                migration_hash = _apply_migration(cursor, migr, migration_hash)
            conn.commit()
            print("Done!")

        print("All done!")


def list_migrations(args: argparse.Namespace) -> None:
    migrations = _get_migrations_from_dir(args.migration_dir)

    for migr_type, migr_list in migrations.items():
        print(f"{migr_type.title()}:")
        for migr in migr_list:
            print(f"\t{migr!r}")


def up(args: argparse.Namespace) -> None:
    """Apply requested migrations in order, from lowest to highest"""
    migrations = _get_migrations_from_dir(args.migration_dir)["up"]
    conn = msc.MySQLConnection(
        host=args.host,
        port=args.port,
        user=args.user,
        password=args.password,
        database=args.db,
    )

    if args.version is not None:
        end = bisect(migrations, args.version, key=lambda x: x.ver)
        migrations = migrations[:end]

    with conn.cursor() as cursor:
        cursor.execute(
            """
                SELECT date, version, migration, migration_hash
                FROM _migration ORDER BY date DESC LIMIT 1
            """
        )
        date, curr_version, migration, migration_hash = next(cursor)
    conn.commit()
    print(migration_hash)

    print(f"Currently at {curr_version}: {migration} ({date})")
    start = bisect(migrations, curr_version, key=lambda x: x.ver)

    migrations = migrations[start:]

    if migrations == []:
        print("WARN: No migrations to apply")
    else:
        print(f"{len(migrations)} migrations to apply:")
        for migr in migrations:
            print(f"\t{migr!r}")

        for migr in migrations:
            print(f"Applying {migr}...", end="")
            with conn.cursor() as cursor:
                migration_hash = _apply_migration(cursor, migr, migration_hash)
            conn.commit()
            print("Done!")

        print("All done!")


def jaunt_cli() -> None:
    parser = argparse.ArgumentParser(description="Barebones database migration utility")
    parser.set_defaults(func=None, has_conn=False)

    subparsers = parser.add_subparsers()

    auth_args = argparse.ArgumentParser(add_help=False)
    auth_args.add_argument("host", help="MySQL server IP or hostname")
    auth_args.add_argument("db", help="MySQL database name")
    auth_args.add_argument("user", help="Name of MySQL user")
    auth_args.add_argument("password", help="MySQL user password")
    auth_args.add_argument(
        "-p", "--port", type=int, default=3306, help="Port mysql server is on"
    )
    auth_args.set_defaults(has_conn=True)

    migrate_args = argparse.ArgumentParser(add_help=False)
    migrate_args.add_argument(
        "-m",
        "--migration-dir",
        default=pathlib.Path.cwd(),
        type=pathlib.Path,
        help="Directory containing migration files",
    )

    sub_create = subparsers.add_parser(
        "create", parents=(auth_args,), help="Create a database"
    )
    sub_create.set_defaults(func=create)

    sub_list = subparsers.add_parser(
        "list", parents=(migrate_args,), help="List available migrations"
    )
    sub_list.set_defaults(func=list_migrations)

    sub_up = subparsers.add_parser(
        "up",
        parents=(auth_args, migrate_args),
        help="Migrate a database up to a given version",
    )
    sub_up.set_defaults(func=up)
    sub_up.add_argument(
        "-v",
        "--version",
        type=int,
        help="Version to migrate up to - must be greater than current version. Default is latest",
    )

    sub_down = subparsers.add_parser(
        "down",
        parents=(auth_args, migrate_args),
        help="Migrate a database down to a given version",
    )
    sub_down.set_defaults(func=down)
    sub_down.add_argument(
        "-v",
        "--version",
        type=int,
        required=True,
        help="Version to migrate down to - must be less than current version",
    )

    args = parser.parse_args()

    args.func(args)


def _get_migrations_from_dir(path: os.PathLike) -> Dict[str, List[Migration]]:
    """Fetches all migration files from a path

    Returns a dict of all migrations split by type, with each type sorted in ascending
    application order.
    """
    migrations = {_type: [] for _type in PREFIX_TO_TYPE.values()}

    for file in path.iterdir():
        match = MIGR_MATCH.fullmatch(file.name)
        if match:
            migr_type = PREFIX_TO_TYPE[match["type"]]
            migr = Migration(migr_type, int(match["num"]), match["desc"], file)
            migrations[migr_type].append(migr)

    for migr_type, migr_list in migrations.items():
        migr_list.sort(key=lambda x: x.ver)

    # TODO(@pdunham113): Warn if there's gaps in version numbers
    # TODO(@pdunham113): Warn if "up" and "down" desc don't match for a given version
    # TODO(@pdunham113): Warn if no "down" for "up" desc

    return migrations


def _apply_migration(
    cursor: msc.cursor.MySQLCursor, migration: Migration, last_hash: str
) -> str:
    """Applies a migration"""
    with open(migration.file, "r") as migr_file:
        query = migr_file.read()

    results = cursor.execute(query, multi=True)
    if results is None:
        print("WARN: Migration is empty!")
    else:
        for result in results:
            pass  # Accessing the iterator entry raises cmd errors

    to_hash = last_hash + query
    hash = hashlib.sha1(to_hash.encode()).hexdigest()

    _record_migration(cursor, migration.ver_to, migration.file, hash)

    return hash


def _record_migration(
    cursor: msc.cursor.MySQLCursor,
    version: int,
    migration: str,
    migr_hash: str,
) -> None:
    """Records a migration in the existing table"""
    cursor.execute(
        "INSERT INTO `_migration`VALUES (%s, %s, %s, %s, %s)",
        (datetime.now(), version, migration, migr_hash, None),
    )


if __name__ == "__main__":
    jaunt_cli()
