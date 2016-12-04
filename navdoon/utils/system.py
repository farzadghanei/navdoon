"""
navdoon.utils.system
--------------------
System utilities and mixin classes
"""

import platform
from time import time
from multiprocessing import cpu_count
from threading import Thread, RLock, Event
from navdoon.pystdlib.queue import Queue, Empty
from navdoon.pystdlib.typing import Dict, Callable, List, Any, Sequence
from navdoon.utils.common import LoggerMixIn

PLATFORM_NAME = platform.system().strip().lower()


def available_cpus():
    # type: () -> int
    try:
        cpus = cpu_count()
    except Exception:
        cpus = 1
    return cpus


def os_syslog_socket():
    # type: () -> str
    syslog_addresses = dict(
        linux="/dev/log",
        darwin="/var/run/syslog",
        freebsd="/var/run/log"
    )
    return syslog_addresses.get(PLATFORM_NAME, None)


class WorkerThread(Thread):
    """A thread to keep consuming tasks from a task queue and store
    the results in a dictionary of task_ids => results
    """

    def __init__(self, queue, stop_event, results):
        # type: (Queue, Event, Dict[int, Any]) -> None
        self.queue = queue  # type: Queue
        self.stop_event = stop_event  # type: Event
        self.results = results  # type: Dict[int, Any]
        Thread.__init__(self)

    def _consume_queue(self):
        # type: () -> None
        should_stop = self.stop_event.is_set
        while not should_stop():
            try:
                self._run_task_from_queue(timeout=1)
            except Empty:
                pass

    def _run_task_from_queue(self, timeout=None):
        # type: (float) -> None
        (task_id, func, args, kwargs) = self.queue.get(True, timeout)
        result = func(*args, **kwargs)
        self.results[task_id] = result
        self.queue.task_done()

    def run(self):
        # type: () -> None
        self._consume_queue()


class TemporaryWorkerThread(WorkerThread):
    """A worker thread that only consumes the queue as long as the queue is not
    empty.
    """

    def _consume_queue(self):
        # type: () -> None
        should_stop = self.stop_event.is_set
        while not should_stop():
            try:
                self._run_task_from_queue(1)
            except Empty:
                break


class ThreadPool(LoggerMixIn):
    def __init__(self, size):
        # type: (int) -> None
        LoggerMixIn.__init__(self)
        self._size = int(size)  # type: int
        self._threads = []  # type: List[Thread]
        self._queue = Queue()  # type: Queue
        self._queue_lock = RLock()  # type: RLock
        self._task_counter = 0  # type: int
        self._task_results = dict()  # type: Dict[int, Any]
        self._stop_event = Event()  # type: Event
        self.log_signature = "threadpool "  # type: str

    def __del__(self):
        # type: () -> None
        if not self._stop_event.is_set():
            self.stop()

    @property
    def size(self):
        # type: () -> int
        return self._size

    @property
    def threads(self):
        # type: () -> List[Thread]
        return self._threads

    def initialize(self):
        # type: () -> ThreadPool
        self._queue = Queue()
        self._create_worker_threads()
        self._start_worker_threads()
        return self

    def do(self, func, *args, **kwargs):
        # type: (Callable, *Any, **Any) -> int
        if self._stop_event.is_set():
            raise Exception("Task thread pool has stopped")
        with self._queue_lock:
            task_id = self._task_counter
            self._task_counter += 1
            self._handle_task(task_id, func, args, kwargs)
        return task_id

    def is_done(self):
        # type: () -> bool
        with self._queue_lock:
            is_done = self._queue.empty()
        return is_done

    def wait_until_done(self):
        # type: () -> ThreadPool
        self._queue.join()
        return self

    def stop(self, wait=True, timeout=None):
        # type: (bool, float) -> None
        self._stop_event.set()
        if wait:
            num_threads = len(self._threads)
            self._log_debug(
                "joining {} worker threads ...".format(num_threads))
            start_time = time()
            counter = 0
            for thread in self._threads:
                counter += 1
                self._log_debug("joining thread {} ...".format(counter))
                thread.join(timeout)
                if timeout is None:
                    continue
                elif time() - start_time > timeout:
                    raise Exception("Stopping thread pool timedout")
            self._log_debug("joined worker {} threads".format(num_threads))
            self._threads = []

    def get_result(self, task_id):
        # type: (int) -> Any
        if task_id not in self._task_results:
            raise ValueError(
                "No results found for task id '{}'".format(task_id))
        return self._task_results[task_id]

    def _handle_task(self, task_id, func, args, kwargs):
        # type: (int, Callable, Sequence[Any], Dict[Any, Any]) -> None
        self._queue.put((task_id, func, args, kwargs))

    def _create_worker_threads(self):
        # type: () -> None
        for i in range(self._size):
            worker = WorkerThread(self._queue, self._stop_event, self._task_results)
            self._threads.append(worker)

    def _start_worker_threads(self):
        # type: () -> ThreadPool
        for thread in self._threads:
            thread.start()
        self._stop_event.clear()
        return self


class ExpandableThreadPool(ThreadPool):
    def __init__(self, size, workers_limit=0):
        # type: (int, int) -> None
        ThreadPool.__init__(self, size)
        self._spawn_worker_threshold = 0.5  # type: float
        self._max_workers_count = 0  # type: int
        self._workers_limit = workers_limit  # type: int

    @property
    def workers_limit(self):
        # type: () -> int
        return self._workers_limit

    @workers_limit.setter
    def workers_limit(self, limit):
        # type: (int) -> None
        limit = int(limit)
        if limit < 0:
            raise ValueError("Thread pool workers limit can't be negative")
        self._workers_limit = limit

    @property
    def max_workers_count(self):
        # type: () -> int
        return self._max_workers_count

    @property
    def spawn_workers_threshold(self):
        # type: () -> float
        return self._spawn_worker_threshold

    @spawn_workers_threshold.setter
    def spawn_workers_threshold(self, threshold):
        # type: (float) -> None
        threshold = float(threshold)
        if threshold < 0:
            raise ValueError("Thread pool spawn workers threshold can't be negative")
        self._spawn_worker_threshold = threshold

    def _start_worker_threads(self):
        # type: () -> ExpandableThreadPool
        ThreadPool._start_worker_threads(self)
        self._max_workers_count = len(self._threads)
        return self

    def _handle_task(self, task_id, func, args, kwargs):
        # type: (int, Callable, Sequence[Any], Dict[Any, Any]) -> None
        ThreadPool._handle_task(self, task_id, func, args, kwargs)
        if not self._stop_event.is_set() and self._can_spawn_temp_worker():
            self._spawn_temp_worker()

    def _can_spawn_temp_worker(self):
        # type: () -> bool
        return self._queue.qsize() > (self._spawn_worker_threshold * self._size) \
               and (self._workers_limit == 0 or len(self._threads) < self._workers_limit)

    def _spawn_temp_worker(self):
        # type: () -> None
        thread = TemporaryWorkerThread(self._queue, self._stop_event, self._task_results)
        self._threads.append(thread)
        thread.start()
        self._max_workers_count += 1
