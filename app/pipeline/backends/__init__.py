from ... import config

_backend = None


def get_backend():
    global _backend
    if _backend is None:
        if config.MODE == "real":
            from .real import RealBackend

            _backend = RealBackend()
        else:
            from .fake import FakeBackend

            _backend = FakeBackend()
    return _backend


def set_backend(b) -> None:  # usado nos testes
    global _backend
    _backend = b
