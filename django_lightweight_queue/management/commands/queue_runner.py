from optparse import make_option

from django.core.management.base import NoArgsCommand

from ...utils import get_tasks, get_backend

class Command(NoArgsCommand):
    option_list = NoArgsCommand.option_list + (
        make_option('--pidfile', action='store', dest='pidfile', default=None,
            help="Fork and write pidfile to this file."),
    )

    def handle_noargs(self, **options):
        tasks = get_tasks()
        backend = get_backend()

        while True:
            job = backend.dequeue()
            job.run()
