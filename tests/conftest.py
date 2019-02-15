import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from flatpak_status.models import Base


@pytest.fixture
def Session():
    engine = create_engine('sqlite:///:memory:', echo=False)
    Session = sessionmaker(bind=engine)
    Base.metadata.create_all(engine)

    return Session


@pytest.fixture
def session(Session):
    session = Session()
    yield session
