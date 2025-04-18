import inspect
import sys
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

    # fallback if nothing found
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
    config = load_config("config.json")
    logger = setup_logger(config.log_level)

    # Log application information
    logger.info(f"Starting {FRIENDLY_APP_NAME}")
    logger.info(f"  App Version: {APP_VERSION_STR}")
    logger.info(f"  App Channel: {APP_CHANNEL}")

    orchestrator = Orchestrator(
        config=config,
        logger=logger
    )
    orchestrator.execute()