import re
import sys
import imp
import time
import logging
import datetime
import multiprocessing

from django.conf import settings
from django.core.management import call_command

from .task import task
from .utils import set_process_title, get_backend

class CronScheduler(multiprocessing.Process):
    QUEUE = 'cron'

    def __init__(self, running, log_level, log_filename):
        self.running = running
        self.log_level = log_level
        self.log_filename = log_filename

        # Logfiles must be opened in child process
        self.log = None

        self.config = self.get_config()

        super(CronScheduler, self).__init__()

    def run(self):
        set_process_title("Cron scheduler process")

        self.log = logging.getLogger()
        for x in self.log.handlers:
            self.log.removeHandler(x)

        logging.basicConfig(
            level=self.log_level,
            format='%(asctime)-15s %(process)d cron_scheduler %(levelname).1s: '
                '%(message)s',
            filename=self.log_filename,
        )

        self.log.debug("Starting")

        backend = get_backend()
        self.log.info("Loaded backend %s", backend)

        while self.running.value:
            try:
                self.tick(backend)
                time.sleep(1)
            except KeyboardInterrupt:
                sys.exit(1)

        self.log.info("Exiting")

    def tick(self, backend):
        self.log.debug("tick()")

        t = datetime.datetime.utcnow()

        # Run once per minute
        if t.second != 0:
            return

        for row in self.config:
            if not (
                row['hour_matcher'](t.hour) and
                row['min_matcher'](t.minute) and
                row['day_matcher'](t.isoweekday())
            ):
                continue

            self.log.info("Enqueueing %s", row['command'])

            execute(
                row['command'],
                *row.get('command_args', []),
                **row.get('command_kwargs', {})
            )

            self.log.debug("Enqueued %s", row)

    def get_config(self):
        config = []

        def get_matcher(minval, maxval, t):
            if t == '*':
                return lambda x: True
            parts = re.split(r'\s*,\s*', t)
            if not parts:
                return
            t_parts = [int(x) for x in parts]
            for num in t_parts:
                assert num >= minval and num <= maxval, \
                    "Invalid time specified in cron config. " \
                    "Specified: %s, minval: %s, maxval: %s" % (
                        num,
                        minval,
                        maxval,
                    )
            return lambda x: x in t_parts

        for app in settings.INSTALLED_APPS:
            try:
                app_path = __import__(app, {}, {}, [app.split('.')[-1]]).__path__
            except AttributeError:
                continue

            try:
                imp.find_module('cron', app_path)
            except ImportError:
                continue

            mod = __import__('%s.cron' % app, fromlist=(app,))

            for row in mod.CONFIG:
                row['min_matcher'] = get_matcher(0, 59, row.get('minutes'))
                row['hour_matcher'] = get_matcher(0, 23, row.get('hours'))
                row['day_matcher'] = get_matcher(1,  7, row.get('days', '*'))
                config.append(row)

        return config

@task(queue=CronScheduler.QUEUE)
def execute(name, *args, **kwargs):
    call_command(name, *args, **kwargs)
