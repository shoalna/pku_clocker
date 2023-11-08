import enum

from pydantic import BaseModel
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.schema import Table
from sqlalchemy import MetaData
from sqlalchemy import ForeignKey
from sqlalchemy import Table, Column, Integer, String
from sqlalchemy import Enum, Time, Boolean, DateTime


class ConfigModel(BaseModel):
    schedule_enable: str
    email: str
    password: str
    cin_time: str
    cout_time: str
    s_type: str
    scin_time: str
    scout_time: str
    telework: str
    telework_apply: str
    do_date: str or list
    skip_date: str or list
    geo_latitude: str
    geo_longitude: str


class Base(DeclarativeBase):
    pass


# class M_USERS(Base):
#     __tablename__ = "m_users"

#     userId: Mapped[int] = mapped_column(
#         name="user_id", primary_key=True)
#     name: Mapped[str] = mapped_column(name="name")
#     email: Mapped[str] = mapped_column(name="email")
#     password: Mapped[str] = mapped_column(name="password")

metadata = MetaData()


class ENUM_RUN_TYPE_NAME(enum.Enum):
    cin = "出勤"
    cout = "退勤"
    schedule = "実績スケジュール申請"


class ENUM_SCHEDULE_CLOCK_TYPE_NAME(enum.Enum):
    normal = "通常勤務"
    custom = "カスタム"


class ENUM_TASK_STATUS(enum.Enum):
    success = "success"
    failed = "failed"
    running = "running"
    pending = "pending"


m_users = Table(
    "m_users", metadata,
    Column('user_id', Integer, primary_key=True),
    Column('email', String(50)),
    Column('password', String(50)),
    Column('memo', String(50)),
)


t_clock_schedules = Table(
    "t_clock_schedules", metadata,
    Column('user_id', Integer,
           ForeignKey("m_users.user_id", ondelete="CASCADE"),
           primary_key=True, ),
    Column('work_type_id', Integer,
           ForeignKey("m_work_types.id", ondelete="CASCADE")),
    Column('run_type',
           Enum(ENUM_RUN_TYPE_NAME,
                values_callable=lambda x:
                [str(e.value) for e in ENUM_RUN_TYPE_NAME]),
           primary_key=True, ),
    Column('run_date', DateTime, primary_key=True),
    Column('run_time', DateTime),
    Column('applied', Enum(ENUM_TASK_STATUS), default=ENUM_TASK_STATUS.pending),
    Column('active', Boolean, default=True),
)


t_basic_types = Table(
    "t_basic_types", metadata,
    Column('user_id', Integer,
           ForeignKey("m_users.user_id", ondelete="CASCADE"),
           primary_key=True, ),
    Column('clockin_type_name', String(50),
           ForeignKey("m_work_types.type_name", ondelete="CASCADE"),),
    Column('clockout_type_name', String(50),
           ForeignKey("m_work_types.type_name", ondelete="CASCADE"),),
    Column("schedule_type_name", String(50),
           ForeignKey("m_work_schedule_types.type_name", ondelete="CASCADE"),),
)


m_work_types = Table(
    "m_work_types", metadata,
    Column("id", Integer, primary_key=True),
    Column('type_name', String(50)),
    Column('run_type', Enum(ENUM_RUN_TYPE_NAME,
                            values_callable=lambda x:
                            [str(e.value) for e in ENUM_RUN_TYPE_NAME])),
    Column('run_time', Time),
    Column("gps", String(50),),
)


m_work_schedule_types = Table(
    "m_work_schedule_types", metadata,
    Column("id", Integer, primary_key=True),
    Column('type_name', String(50), primary_key=True),
    Column('memo', String(50)),
    Column('workday', Boolean),
    Column('telework', Boolean),
    # Column('clock_type', String(50)),
    Column('clock_type', Enum(ENUM_SCHEDULE_CLOCK_TYPE_NAME,
                              values_callable=lambda x:
                              [str(e.value) for e in ENUM_SCHEDULE_CLOCK_TYPE_NAME])),
    Column('clockin', Time),
    Column('clockout', Time),
    Column('breakin', Time),
    Column('breakout', Time),
    Column('msg', String(50)),
)


t_applied_schedules = Table(
    "t_applied_schedules", metadata,
    Column('user_id', Integer,
           ForeignKey("m_users.user_id", ondelete="CASCADE"),
           primary_key=True),
    Column('schedule_type_id', Integer,
           ForeignKey("m_work_schedule_types.id", ondelete="CASCADE")),
    Column('run_type',
           Enum(ENUM_RUN_TYPE_NAME,
                values_callable=lambda x:
                [str(e.value) for e in ENUM_RUN_TYPE_NAME]),
           primary_key=True, ),
    Column('run_date', DateTime, primary_key=True),
    Column('run_time', DateTime, nullable=False),
    Column('apply_date', DateTime, nullable=False),
    Column('applied', Enum(ENUM_TASK_STATUS), default=ENUM_TASK_STATUS.pending),
    Column('active', Boolean, default=True),
)
