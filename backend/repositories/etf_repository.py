from sqlalchemy.orm import Session

from models import LeveragedEtf


class EtfRepository:
    def __init__(self, db: Session) -> None:
        self._db = db

    def get_all_ordered(self) -> list[LeveragedEtf]:
        return self._db.query(LeveragedEtf).order_by(LeveragedEtf.ticker).all()

    def find_by_ticker(self, ticker: str) -> LeveragedEtf | None:
        return self._db.query(LeveragedEtf).filter(LeveragedEtf.ticker == ticker).first()

    def get_map(self) -> dict[str, LeveragedEtf]:
        return {etf.ticker: etf for etf in self._db.query(LeveragedEtf).all()}

    def add(self, etf: LeveragedEtf) -> LeveragedEtf:
        self._db.add(etf)
        self._db.commit()
        self._db.refresh(etf)
        return etf

    def delete(self, etf: LeveragedEtf) -> None:
        self._db.delete(etf)
        self._db.commit()
