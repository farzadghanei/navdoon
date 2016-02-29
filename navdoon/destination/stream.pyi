from typing import List, AnyStr, Tuple, io, Union
from io import FileIO
from navdoon.destination.abstract import AbstractDestination

Metrics = List[Tuple(AnyStr, float, float)]
Lines = List[AnyStr]
IO = Union[io.IO, FileIO]

class Stream(AbstractDestination):
    def __init__(self, file_handle: IO) -> None: ...
    def create_output_from_metrics(self, metrics: Metrics) -> Lines: ...
    def flush(self, metrics: Metrics) -> None: ...
    def _write_lines(self, lines: Lines) -> None: ...


class Stdout(Stream):
    def __init__(self) -> None: ...