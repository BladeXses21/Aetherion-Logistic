from sqlalchemy import Float, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class City(Base, TimestampMixin):
    __tablename__ = "ua_cities"
    __table_args__ = (Index("ix_ua_cities_name_ua", "name_ua"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name_ua: Mapped[str] = mapped_column(String(150), nullable=False)
    region_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    lat: Mapped[float] = mapped_column(Float, nullable=False)
    lon: Mapped[float] = mapped_column(Float, nullable=False)
    lardi_town_id: Mapped[int | None] = mapped_column(Integer, unique=True, nullable=True)
    source: Mapped[str] = mapped_column(String(30), nullable=False, default="nominatim")
