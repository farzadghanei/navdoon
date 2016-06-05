"""
navdoon.utils.system
--------------------
System utilities and mixin classes
"""

import platform
from multiprocessing import cpu_count
from threading import Thread, RLock, Event
from navdoon.pystdlib.queue import Queue, Empty


PLATFORM_NAME = platform.system().strip().lower()


def available_cpus():
    try:
        cpus = cpu_count()
    except Exception:
        cpus = 1
    return cpus


def os_syslog_socket():
    syslog_addresses = dict(
        linux="/dev/log",
        darwin="/var/run/syslog",
        freebsd="/var/run/log"
    )
    return syslog_addresses.get(PLATFORM_NAME, None)


class TaskThreadPool(object):
    def __init__(self, size):
        self._size = int(size)
        self._threads = []
        self._queue = Queue()
        self._task_counter = 0
        self._task_counter_lock = RLock()
        self._task_results = dict()
        self._stop_event = Event()

    def __del__(self):
        self.stop()

    @property
    def size(self):
        return self._size

    @property
    def threads(self):
        return self._threads

    def initialize(self):
        self._queue = Queue()
        self._refill_worker_threads()
        self._start_worker_threads()
        return self

    def do(self, func, *args, **kwargs):
        if self._stop_event.is_set():
            raise Exception("Task thread pool has stopped")
        task_id = self._get_next_task_counter()
        self._queue.put((task_id, func, args, kwargs))
        return task_id

    def wait_until_done(self):
        self._queue.join()
        return self

    def stop(self, wait=True):
        self._stop_event.set()
        if wait:
            for thread in self._threads:
                thread.join()

    def get_result(self, task_id):
        if not task_id in self._task_results:
            raise ValueError(
                "no such task exists with id '{}'".format(task_id))
        return self._task_results[task_id]

    def _get_next_task_counter(self):
        self._task_counter_lock.acquire()
        counter = self._task_counter
        self._task_counter += 1
        self._task_counter_lock.release()
        return counter

    def _consume_task_queue(self):
        while not self._stop_event.is_set():
            try:
                self._run_task_from_queue(1)
            except Empty:
                pass

    def _run_task_from_queue(self, timeout=None):
        (task_id, func, args, kwargs) = self._queue.get(True, timeout)
        result = func(*args, **kwargs)
        self._queue.task_done()
        self._task_results[task_id] = result

    def _refill_worker_threads(self):
        self._threads.extend(
            self._create_worker_threads(
                self._size - len(self._threads)
            )
        )

    def _start_worker_threads(self):
        for thread in self._threads:
            thread.start()
        self._stop_event.clear()
        return self

    def _create_worker_threads(self, size):
        threads = []
        for i in range(size):
            threads.append(
                Thread(target=self._consume_task_queue)
            )

        return threads