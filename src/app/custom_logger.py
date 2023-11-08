import logging
import logging.handlers


def set_logger(module_name, fname="log", level=logging.INFO):
    logger = logging.getLogger(module_name)
    logger.handlers.clear()

    formatter = logging.Formatter(
        "%(levelname)s (%(funcName)s) %(message)s")

    streamHandler = logging.StreamHandler()
    streamHandler.setFormatter(formatter)
    logger.setLevel(level)
    streamHandler.setLevel(level)
    logger.addHandler(streamHandler)

    if fname is not None:
        fileHandler = logging.handlers.RotatingFileHandler(
            fname, maxBytes=10000000, backupCount=5)
        fileHandler.setFormatter(formatter)
        fileHandler.setLevel(level)
        logger.addHandler(fileHandler)
    return logger
