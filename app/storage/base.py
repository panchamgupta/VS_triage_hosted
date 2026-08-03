from abc import ABC, abstractmethod


class ReleaseStore(ABC):
    @abstractmethod
    def list_release_dirs(self):
        raise NotImplementedError

    @abstractmethod
    def resolve_release_dir(self, release_id):
        raise NotImplementedError

    @abstractmethod
    def load_manifest(self, release_dir):
        raise NotImplementedError

    @abstractmethod
    def resolve_release_file(self, release_dir, relative_path):
        raise NotImplementedError

    @abstractmethod
    def load_json(self, path):
        raise NotImplementedError