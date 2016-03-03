from typing import Iterable, Union, List
import multiprocessing
from threading import Thread
from navdoon.pystdlib import queue
from navdoon.collector import AbstractCollector
from navdoon.utils import LoggerMixIn
from navdoon.processor import QueueProcessor


Queue = Union[multiprocessing.Queue, queue.Queue]
QueueProcess = Union[Thread]

def validate_collectors(collectors: Iterable[AbstractCollector]) -> None: ...


class Server(LoggerMixIn):
    def __init__(self) -> None: ...
    @property
    def queue_processor(self) -> QueueProcessor: ...
    @queue_processor.setter
    def queue_processor(self, processor: QueueProcessor) -> None: ...
    def set_collectors(self, collectors: Iterable[AbstractCollector]) -> 'Server': ...
    def start(self) -> None: ...
    def is_running(self) -> bool: ...
    def wait_until_running(self, timeout: float=None) -> None: ...
    def shutdown(self, process_queue: bool=True, timeout: float=None) -> None: ...
    def wait_until_shutdown(self, timeout: float=None) -> None: ...
    def create_queue_processor(self) -> QueueProcessor: ...
    def reload(self) -> None: ...
    @staticmethod
    def _use_multiprocessing() -> bool: ...
    @classmethod
    def _create_queue(cls: 'Server') -> Queue: ...
    def _close_queue(self) -> None: ...
    def _start_queue_processor(self) -> QueueProcess: ...
    def _share_queue_with_collectors_and_processor(self) -> None: ...
    def _shutdown_queue_processor(self, process: bool=True, timeout: float=None): ...
    def _start_collector_threads(self) -> List[Thread]: ...
    def _shutdown_collectors(self, timeout: float=None) -> None: ...