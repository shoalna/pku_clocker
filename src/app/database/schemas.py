from enum import Enum
import datetime

from pydantic import BaseModel


from .model import (
    ENUM_RUN_TYPE_NAME,
    ENUM_SCHEDULE_CLOCK_TYPE_NAME,
    ENUM_TASK_STATUS,
)

# class RUN_TYPE_NAME(str, Enum):
#     cin = '出勤'
#     cout = '退勤'
#     schedule = '実績スケジュール申請'


# class TASK_STATUS(str, Enum):
#     success = 'success'
#     failed = 'failed'
#     running = 'running'
#     pending = 'pending'



# class SCHEDULE_CLOCK_TYPE_NAME(str, Enum):
#     normal = '通常勤務(9-18)'
#     custom = 'カスタム'


class M_USERS(BaseModel):
    user_id: int
    email: str
    password: str
    memo: str

    class Config:
        orm_mode = True


class M_WORK_TYPES(BaseModel):
    id: int
    type_name: str
    run_type: ENUM_RUN_TYPE_NAME
    run_time: datetime.time
    gps: str



class T_CLOCK_SCHEDULES(BaseModel):
    user_id: int
    work_type_id: int
    run_type: ENUM_RUN_TYPE_NAME
    run_time: datetime.datetime
    run_date: datetime.datetime
    applied: ENUM_TASK_STATUS
    active: bool


class M_WORK_SCHEDULE_TYPES(BaseModel):
    id: int
    type_name: str
    memo: str
    workday: bool
    telework: bool
    clock_type: ENUM_SCHEDULE_CLOCK_TYPE_NAME
    clockin: datetime.time
    clockout: datetime.time
    breakin: datetime.time
    breakout: datetime.time
    msg: str

    class Config:
        orm_mode = True


class T_BASIC_TYPES(BaseModel):
    user_id: int
    clockin_type_name: str
    clockout_type_name: str
    schedule_type_name: str

    class Config:
        orm_mode = True


class T_APPLIED_SCHEDULES(BaseModel):
    user_id: int
    schedule_type_id: int
    run_type: ENUM_RUN_TYPE_NAME
    run_date: datetime.datetime
    run_time: datetime.datetime
    apply_date: datetime.datetime
    applied: ENUM_TASK_STATUS
    active: bool

    class Config:
        orm_mode = True
