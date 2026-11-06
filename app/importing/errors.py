class ImportFileError(ValueError):
    """파일을 읽을 수 없거나 필수 열을 찾을 수 없다."""

    def __init__(self, message: str, **extra: object) -> None:
        super().__init__(message)
        self.message = message
        self.extra = extra
