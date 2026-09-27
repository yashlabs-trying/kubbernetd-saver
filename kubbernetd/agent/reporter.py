import os
import socket
import structlog

log = structlog.get_logger()


class StatusReporter:
    def report_online(self):
        hostname = socket.gethostname()
        log.debug("agent online", host=hostname)