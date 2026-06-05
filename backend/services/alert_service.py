from sqlalchemy.orm import Session

from core.logging import get_logger
from models import AlertCondition, PriceAlert
from repositories.alert_repository import AlertRepository
from schemas import AlertCreate, AlertResponse
from services.price_service import PriceService

logger = get_logger(__name__)


class AlertService:
    def __init__(self, db: Session, price_service: PriceService, user_id: int) -> None:
        self._repo = AlertRepository(db, user_id)
        self._price_service = price_service
        self._user_id = user_id

    def _to_response(self, alert: PriceAlert, price: float | None) -> AlertResponse:
        return AlertResponse(
            id=alert.id,
            ticker=alert.ticker,
            condition=alert.condition,
            target_price=alert.target_price,
            note=alert.note,
            active=alert.active,
            current_price=price,
            triggered_at=alert.triggered_at,
            created_at=alert.created_at,
        )

    def list(self) -> list[AlertResponse]:
        alerts = self._repo.get_all()
        tickers = list({a.ticker for a in alerts})
        prices = self._price_service.get_live_prices(tickers) if tickers else {}
        return [self._to_response(a, prices.get(a.ticker)) for a in alerts]

    def create(self, payload: AlertCreate) -> AlertResponse:
        ticker = payload.ticker.upper()
        # Seed last_price so the checker only fires on a genuine *crossing* of the
        # target, never immediately just because the price is already past it.
        current = self._price_service.get_live_price(ticker)
        alert = self._repo.add(PriceAlert(
            user_id=self._user_id,
            ticker=ticker,
            condition=payload.condition,
            target_price=payload.target_price,
            note=payload.note,
            active=True,
            last_price=current,
        ))
        logger.info(
            "Alert created  user=%d  %s %s %.2f",
            self._user_id, ticker, alert.condition.value, alert.target_price,
        )
        return self._to_response(alert, current)

    def set_active(self, alert_id: int, active: bool) -> AlertResponse | None:
        alert = self._repo.get_by_id(alert_id)
        if not alert:
            return None
        fields = {"active": active}
        if active:
            # Re-arming: clear the fired state and re-baseline against the live price.
            current = self._price_service.get_live_price(alert.ticker)
            fields.update(triggered_at=None, last_price=current)
        alert = self._repo.update(alert, **fields)
        price = self._price_service.get_live_price(alert.ticker)
        return self._to_response(alert, price)

    def delete(self, alert_id: int) -> bool:
        alert = self._repo.get_by_id(alert_id)
        if not alert:
            return False
        self._repo.delete(alert)
        logger.info("Alert deleted  user=%d  id=%d", self._user_id, alert_id)
        return True
