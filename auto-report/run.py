#!/usr/bin/env python3
"""AutoReport - one command, start to finish.

    python run.py

Runs the whole pipeline: load config -> fetch -> parse -> clean -> analyse -> report.
Everything is driven by ``config.json``; every stage is timed and logged. Standard library
only: no pip install, no virtualenv, no network needed for the bundled demo dataset.

Options
-------
    --config PATH   use a different config file (default: config.json next to this script)
    --offline       never touch the network; read the local fixtures
    --online        force live HTTP; fail loudly instead of falling back to a fixture
    --outdir PATH   override report.output_dir from the config
    --quiet         only warnings/errors and the final summary
    --verbose       include per-row debug output
"""

from __future__ import annotations

import argparse
import os
import sys
import traceback

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from autoreport import __version__, analysis, cleaning, config as config_module  # noqa: E402
from autoreport import fetchers, parsers, reporting  # noqa: E402
from autoreport.util import Logger, Stopwatch, integer, money, num, utc_now_text  # noqa: E402

TOTAL_STAGES = 6


def parse_args(argv):
    parser = argparse.ArgumentParser(
        prog="run.py",
        description="Config-driven web-scraping / cleaning / reporting pipeline (stdlib only).")
    parser.add_argument("--config", default=os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "config.json"),
        help="path to the JSON config file (default: ./config.json)")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--offline", action="store_true",
                      help="skip the network entirely and read the local fixtures")
    mode.add_argument("--online", action="store_true",
                      help="require live HTTP; do not fall back to fixtures")
    parser.add_argument("--outdir", default=None, help="override report.output_dir")
    verbosity = parser.add_mutually_exclusive_group()
    verbosity.add_argument("--quiet", action="store_true", help="warnings and summary only")
    verbosity.add_argument("--verbose", action="store_true", help="include debug output")
    parser.add_argument("--version", action="version", version="AutoReport {}".format(__version__))
    return parser.parse_args(argv)


def _relative(path):
    """Render a path relative to the project root.

    Keeps logs portable and machine-independent instead of leaking an
    absolute path from whoever happened to run it last.
    """
    root = os.path.dirname(os.path.abspath(__file__))
    try:
        rel = os.path.relpath(os.path.abspath(str(path)), root)
    except ValueError:
        return str(path)
    return rel.replace(os.sep, "/")


def _banner(logger, config, mode):
    logger.banner("AutoReport v{} - {}".format(__version__, config.section("project")["name"]))
    logger.info("run", "config      : {}".format(_relative(config.path)))
    logger.info("run", "output dir  : {}".format(_relative(config.output_dir)))
    logger.info("run", "fetch mode  : {}".format(mode))
    logger.info("run", "python      : {}".format(sys.version.split()[0]))
    logger.info("run", "third-party : none (standard library only)")


def _print_summary(logger, rows, metrics, quality, written, config, outcomes):
    base = metrics.get("base_currency", "USD")
    totals = metrics["totals"]
    price = metrics["price"]
    logger.banner("SUMMARY")
    logger.info("run", "rows parsed        : {}".format(integer(quality.rows_in)))
    logger.info("run", "rows clean         : {} ({})".format(
        integer(quality.rows_out), "{}% pass".format(
            round(100.0 * quality.rows_out / quality.rows_in, 1) if quality.rows_in else 0)))
    logger.info("run", "rows dropped       : {} ({})".format(
        integer(quality.drop_total),
        ", ".join("{}={}".format(reason, count)
                  for reason, count in quality.dropped.most_common()) or "none"))
    logger.info("run", "price min/mean/med : {} / {} / {}".format(
        money(price["min"]), money(price["mean"]), money(price["median"])))
    logger.info("run", "price max          : {}".format(money(price["max"])))
    logger.info("run", "catalogue value    : {} {:,.2f} ({} rows)".format(
        base, totals["catalog_value"] or 0.0, totals["rows"]))
    logger.info("run", "categories / brands: {} / {}".format(
        totals["categories"], totals["brands"]))
    logger.info("run", "mean rating        : {}".format(num(metrics["rating"]["mean"], 2)))
    route = ", ".join("{}={}".format(o.source_id, o.mode) for o in outcomes)
    logger.info("run", "collection route   : {}".format(route))
    print("")
    print(logger.summary_table())
    print("")
    print("Outputs written:")
    for path in written:
        print("  {:<44} {:>10,} bytes".format(os.path.relpath(path, config.root), 
                                               os.path.getsize(path)))
    print("")
    print("Open {} in a browser - it is fully self-contained.".format(
        os.path.relpath(config.output_file("html"), config.root)))


def main(argv=None):
    args = parse_args(argv if argv is not None else sys.argv[1:])
    level = "WARN" if args.quiet else ("DEBUG" if args.verbose else "INFO")
    logger = Logger(level=level)

    try:
        # ---- stage 1: config ---------------------------------------------------------
        watch = Stopwatch()
        config = config_module.load(args.config)
        if args.outdir:
            config.data["report"]["output_dir"] = os.path.abspath(args.outdir)
        logger.attach_file(config.output_file("log"))
        logger.note_stage("config", watch.stop(), "{} source(s)".format(
            len(config.section("fetch").get("sources", []))))

        mode = "offline" if args.offline else ("online" if args.online else
                                              config.section("fetch").get("mode", "auto"))
        _banner(logger, config, mode)

        # ---- stage 2: fetch ----------------------------------------------------------
        with logger.stage("fetch", 2, 6) as stage:
            outcomes = fetchers.collect_sources(config, logger,
                                                mode_override="offline" if args.offline else
                                                ("online" if args.online else None))
            total_chars = sum(len(o.content or "") for o in outcomes)
            stage.note = "{} source(s), {:,} chars".format(len(outcomes), total_chars)

        # ---- stage 3: parse ----------------------------------------------------------
        with logger.stage("parse", 3, 6) as stage:
            records, parse_stats = parsers.parse_documents(
                outcomes, config.section("selectors"), logger)
            stage.note = "{:,} raw record(s)".format(len(records))

        # ---- stage 4: clean ----------------------------------------------------------
        with logger.stage("clean", 4, 6) as stage:
            rows, quality = cleaning.clean_records(records, config, logger, parse_stats)
            stage.note = "{} kept / {} dropped".format(len(rows), quality.drop_total)

        # ---- stage 5: analyse --------------------------------------------------------
        with logger.stage("analyse", 5, 6) as stage:
            metrics = analysis.analyse(rows, config, quality, logger)
            stage.note = "{} categor(ies), {} metric group(s)".format(
                metrics["totals"]["categories"], len(metrics))

        # ---- stage 6: report ---------------------------------------------------------
        with logger.stage("report", 6, 6) as stage:
            run_info = reporting.runtime_info()
            if args.outdir:
                run_info["outdir_override"] = config.output_dir
            written = reporting.write_all(rows, metrics, quality, config, outcomes,
                                         parse_stats, run_info, logger)
            stage.note = "{} file(s)".format(len(written))

        _print_summary(logger, rows, metrics, quality, written, config, outcomes)
        logger.info("run", "finished with {} warning(s)".format(logger.counts.get("WARN", 0)))
        logger.close()
        return 0

    except config_module.ConfigError as exc:
        logger.error("config", str(exc))
        logger.close()
        return 2
    except fetchers.FetchError as exc:
        logger.error("fetch", str(exc))
        logger.error("fetch", "tip: run with --offline, or add a 'fixture' to the source "
                              "in config.json so the pipeline can fall back.")
        logger.close()
        return 3
    except KeyboardInterrupt:                                # pragma: no cover
        logger.error("run", "interrupted")
        logger.close()
        return 130
    except Exception as exc:                                 # noqa: BLE001
        logger.error("run", "unhandled {}: {}".format(type(exc).__name__, exc))
        if args.verbose or os.environ.get("AUTOREPORT_TRACEBACK"):
            traceback.print_exc()
        else:
            logger.error("run", "re-run with --verbose for a full traceback")
        logger.close()
        return 1


if __name__ == "__main__":
    sys.exit(main())
