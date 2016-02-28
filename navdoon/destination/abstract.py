from abc import abstractmethod


class AbstractDestination(object):
    @abstractmethod
    def flush(self, metrics):
        raise NotImplementedError
