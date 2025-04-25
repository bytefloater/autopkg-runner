import argparse
import inspect
import platform
import sys
import textwrap
from logbook import Logger, Processor, StreamHandler

from __info__ import LOGGER_NAME, FRIENDLY_APP_NAME, APP_VERSION_STR, APP_CHANNEL
from libs.stage import Stage
from libs.config import load_config
from libs.orchestrator import Orchestrator


def _inject_classprefix(record):
    # Start at current frame, walk backwards until we find a 'self' attribute
    frame = inspect.currentframe()
    while frame:
        if 'self' in frame.f_locals:
            candidate = frame.f_locals['self']

            # Check the found class is a 'Stage' class
            if isinstance(candidate, Stage):
                record.extra['classprefix'] = f"{candidate.__class__.__name__}:"
                return
        frame = frame.f_back

    # Fallback if nothing found
    record.extra['classprefix'] = ''

def setup_logger(log_level) -> Logger:
    FORMAT_STRING = '[{record.time:%Y-%m-%d %H:%M:%S.%f}] {record.level_name:<8} : [{record.extra[classprefix]}{record.func_name}] {record.message}'

    # Enable class name injection into logging calls
    class_processor = Processor(_inject_classprefix)
    class_processor.push_application()

    if sys.stdout:
        streamhandler = StreamHandler(
            sys.stdout,
            level=log_level.upper(),
            bubble=True,
            format_string=FORMAT_STRING
        )
        streamhandler.push_application()

    return Logger(LOGGER_NAME)


if __name__ == "__main__":
    stages_available = {cls.__name__: cls for cls in Orchestrator.STAGE_CLASSES}
    parser = argparse.ArgumentParser(
        formatter_class=argparse.RawTextHelpFormatter,
        description=textwrap.dedent("""\
        AutoPkg Runner
        --------------
        A wrapper to run AutoPkg on a remote SMB repository and peform post-run
        clean-up tasks
        """)
    )
    pipeline_args = parser.add_argument_group("workflow options")
    pipeline_args.add_argument(
        "-c", "--config",
        default="config.json",
        help="Path to your JSON config file (default: config.json)"
    )
    testing_args = parser.add_argument_group("stage testing options")
    testing_args.add_argument(
        "-s", "--stage",
        choices=stages_available.keys(),
        metavar="STAGE",
        help=(
            "Run one stage for testing\n"
            f"Stages: {', '.join(stages_available.keys())}"
        )
    )

    # Application setup
    args = parser.parse_args()
    config = load_config(args.config)
    logger = setup_logger(config.log_level)

    # Platform Check
    if platform.system() != "Darwin":
        logger.error("This utility only works on macOS!")
        sys.exit(126)

    # Log application information
    logger.info(f"Starting {FRIENDLY_APP_NAME}")
    logger.info(f"  App Version: {APP_VERSION_STR}")
    logger.info(f"  App Channel: {APP_CHANNEL}")

    # Setup workflow orchestrator
    orchestrator = Orchestrator(
        config=config,
        logger=logger
    )
    orchestrator.configure_stages(args.stage)
    orchestrator.execute()