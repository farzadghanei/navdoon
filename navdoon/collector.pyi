from typing import Optional, Union, List, AnyStr
from socket import socket
from navdoon.utils import LoggerMixIn

class SocketServer(LoggerMixIn):
    def __init__(self, **kargs) -> None: ...
    def __del__(self) -> None: ...
    def configure(self, **kargs) -> List[AnyStr]: ...
    def serve(self) -> None: ...
    def is_queuing_requests(self) -> bool: ...
    def wait_until_queuing_requests(self, timeout:float = None) -> None: ...
    def shutdown(self) -> None: ...
    def wait_until_shutdown(self, timeout:float = None) -> None: ...
    def _pre_serve(self) -> None: ...
    def _queue_requests_udp(self) -> None: ...
    def _queue_requests_tcp(self) -> None: ...
    def _post_serve(self) -> None: ...
    def _do_shutdown(self, join_queue: bool=True) -> None: ...
    def _close_queue(self, join: bool=True) -> None: ...
    def _bind_socket(self, sock=Optional[socket]) -> None: ...
    def _create_socket(self) -> socket: ...
    def _close_socket(self) -> None: ...
    def _change_process_user_group(self) -> None: ...