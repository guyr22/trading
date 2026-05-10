from sqlalchemy.orm import Session

from models import AppConfig


class ConfigRepository:
    def __init__(self, db: Session) -> None:
        self._db = db

    def get(self, key: str) -> AppConfig | None:
        return self._db.query(AppConfig).filter(AppConfig.key == key).first()

    def set(self, key: str, value: str) -> AppConfig:
        config = self.get(key)
        if config:
            config.value = value
        else:
            config = AppConfig(key=key, value=value)
            self._db.add(config)
        self._db.commit()
        return config
