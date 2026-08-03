from threading import RLock


class SimpleCache:
    def __init__(self):
        self._data = {}
        self._lock = RLock()

    def get(self, key, default=None):
        with self._lock:
            return self._data.get(key, default)

    def set(self, key, value):
        with self._lock:
            self._data[key] = value
        return value

    def get_or_set(self, key, loader):
        with self._lock:
            if key in self._data:
                return self._data[key]
        value = loader()
        with self._lock:
            self._data[key] = value
        return value

    def invalidate_prefix(self, prefix):
        with self._lock:
            doomed = [key for key in self._data if str(key).startswith(prefix)]
            for key in doomed:
                del self._data[key]