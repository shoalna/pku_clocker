from typing import List, Dict
import logging
import os
import datetime
import asyncio
import traceback
import random

import pandas as pd
import numpy as np
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_
from filelock import Timeout, FileLock

from database import model, db_utils
from database.database import async_session
from database import schemas
from core.clocker import Clocker
from core.utils import is_holiday


N_DAYS2BUILD = 14


class Task:
    ...


class ClockTask(Task):
    ...


class ApplyTask(Task):
    ...


async def build_tasks(session: AsyncSession, logger: logging.Logger) -> pd.DataFrame:

    def get_radnom_time_delta(
            size: int, delta_seconds: int = 300) -> pd.Series:
        return pd.to_timedelta(np.random.randint(
            -delta_seconds, delta_seconds, size=size), unit="s")
        
    # filter users ready to build
    basic = await db_utils.get_rows(
        session=session, table=model.t_basic_types, logger=logger)
    pkeys = set(db_utils.get_db_keys(model.t_basic_types, primary=True))
    sub_keys = set(db_utils.get_db_keys(model.t_basic_types)) - pkeys
    basic.dropna(subset=sub_keys, inplace=True, how="any")

    # do nothing if no user is ready
    if basic.empty:
        return []

    # format t_basic to long-type-dataframe
    # 3 rows(cin time, cout time, schedule time) for every email
    df = pd.melt(basic, value_vars=sub_keys, id_vars=pkeys,
                 var_name="types", value_name="tasks")

    # merge real time
    work_types = await db_utils.get_rows(
        session=session, table=model.m_work_types, logger=logger)

    tcs = pd.merge(df, work_types, how="left",
                   left_on="tasks", right_on="type_name")
    tcs.dropna(subset="id", inplace=True)
    tcs.rename(columns={"id": "work_type_id"}, inplace=True)
    tcs["applied"] = model.ENUM_TASK_STATUS.pending.value

    now = pd.Timestamp.now()
    tasks = []
    for n in range(N_DAYS2BUILD):
        tmp = tcs.copy(deep=True)
        rundate = (now + pd.Timedelta(n, "d")).date()
        if is_holiday(rundate):
            continue
        tmp["run_time"] = tmp["run_time"].apply(
            lambda x: pd.Timestamp.combine(rundate, x))
        tasks.append(tmp)

    # random diff 5 min
    res = pd.concat(tasks, axis=0)
    res = res[pd.to_datetime(res["run_time"]) >
              pd.Timestamp.now()].reset_index(drop=True)
    res["run_time"] = res["run_time"] + get_radnom_time_delta(size=len(res))
    res["run_date"] = res["run_time"].dt.date
    res["active"] = True

    await db_utils.insert_rows(
        df=res[db_utils.get_db_keys(model.t_clock_schedules)],
        session=session,
        table=model.t_clock_schedules,
        logger=logger,
        on_conflict_do_nothing=True,
    )

    # merge real time
    stypes = await db_utils.get_rows(
        session=session, table=model.m_work_schedule_types, logger=logger)

    tas = pd.merge(df, stypes, how="left",
                   left_on="tasks", right_on="type_name")
    tas.dropna(subset="id", inplace=True)
    tas.rename(columns={"id": "schedule_type_id"}, inplace=True)
    tas["applied"] = "pending"

    tasks = []
    for n in range(N_DAYS2BUILD):
        tmp = tas.copy(deep=True)
        rundate = (now + pd.Timedelta(n, "d")).date()
        if is_holiday(rundate):
            continue
        tmp["run_time"] = tmp["run_time"].apply(
            lambda x: pd.Timestamp.combine(rundate, x))
        tasks.append(tmp)
    
    # random diff 5 min
    res = pd.concat(tasks, axis=0)
    res = res[pd.to_datetime(res["run_time"]) >
              pd.Timestamp.now()].reset_index(drop=True)
    res["run_time"] = res["run_time"] + get_radnom_time_delta(len(res))
    res["run_date"] = res["run_time"].dt.date
    res["active"] = True
    res["run_type"] = model.ENUM_RUN_TYPE_NAME.schedule
    res["apply_date"] = res["run_time"].apply(get_next_work_day)

    await db_utils.insert_rows(
        df=res[db_utils.get_db_keys(model.t_applied_schedules)],
        session=session,
        table=model.t_applied_schedules,
        logger=logger,
        on_conflict_do_nothing=True,
    )


async def execute_stmt(stmt):
    async with async_session() as session:
        res = await session.execute(stmt)
        res = res.all()
        await session.commit()
    return res


def render2pydantic(*, table, schema, values: List):
    if len(values) == 0:
        raise ValueError(
            "Empty values. Cannot dump to pydantic object."
            f"({table})")
    assert len(values) == 1
    values = values[0]
    return schema(**(dict(zip(
        db_utils.get_db_keys(table), values))))


def get_next_work_day(x: pd.Timestamp) -> datetime.date:
    nextday = pd.Timestamp(x) + pd.Timedelta(days=1)
    while is_holiday(nextday):
        nextday = pd.Timestamp(nextday) + pd.Timedelta(days=1)
    return nextday.date()


async def get_user_info(uid: int):
    table = model.m_users
    stmt = select(table).where(table.c.user_id == uid)
    return render2pydantic(
        table=table,
        schema=schemas.M_USERS,
        values= await execute_stmt(stmt),
    )


async def background_updater(logger):
    write_pid(fname="updater.pid")
    while True:
        await asyncio.sleep(5)
        if not check_pid(fname="updater.pid"):
            logger.info(f"process [{os.getpid()}] updater quit")
            break

        # run in next day 00:00:00 ~ 00:10:00
        sleep2tomorrow = (datetime.datetime.combine(
            datetime.date.today() + datetime.timedelta(days=1),
            datetime.time(0, random.randint(0, 9), random.randint(0, 59)),
        ) - datetime.datetime.now()).total_seconds()
        # sleep2tomorrow = 10
        logger.info(f"Build scheduler after {sleep2tomorrow} seconds")
        await asyncio.sleep(sleep2tomorrow)

        async with async_session() as session:
            await build_tasks(session, logger)
            await session.commit()
        logger.info(f"Build scheduler done")


async def get_work_type_info(tid):
    table = model.m_work_types
    stmt = select(table).where(table.c.id == tid)
    return render2pydantic(
        table=table,
        schema=schemas.M_WORK_TYPES,
        values= await execute_stmt(stmt),
    )


async def check_is_apply_day(date) -> bool:
    table = model.t_applied_schedules
    stmt = select(table).where(table.c.run_time == date)

    applied_task = render2pydantic(
        table=table,
        schema=schemas.T_APPLIED_SCHEDULES,
        values=await execute_stmt(stmt),
    )
    if applied_task:
        return True
    return False


async def get_tasks(logger):
    # get nearest actived task from t_clock_schedules
    table = model.t_clock_schedules

    sub_stmt = select(table).where(
        and_(
            table.c.active == True,
            table.c.applied == model.ENUM_TASK_STATUS.pending,
        )
    ).subquery()
    stmt = select(sub_stmt).where(
        sub_stmt.c.run_time ==
        select(func.min(sub_stmt.c.run_time)).scalar_subquery(),
    )
    clock_task = render2pydantic(
        table=table,
        schema=schemas.T_CLOCK_SCHEDULES,
        values= await execute_stmt(stmt),
    )

    # get nearest actived task from t_applied_schedules
    table = model.t_applied_schedules
    sub_stmt = select(table).where(
        and_(
            table.c.active == True,
            table.c.applied == model.ENUM_TASK_STATUS.pending,
        )
    ).subquery()

    stmt = select(sub_stmt).where(
        sub_stmt.c.run_time ==
        select(func.min(sub_stmt.c.run_time)).scalar_subquery(),
    )

    applied_task = render2pydantic(
        table=table,
        schema=schemas.T_APPLIED_SCHEDULES,
        values=await execute_stmt(stmt),
    )

    # get id reference table
    if clock_task.run_time < applied_task.run_time:
        latest_task = clock_task
        table = model.m_work_types
        stmt = select(table).where(table.c.id == clock_task.work_type_id)
        sup_info = render2pydantic(
            table=table,
            schema=schemas.M_WORK_TYPES,
            values= await execute_stmt(stmt),
        )
    else:
        latest_task = applied_task
        table = model.m_work_schedule_types
        stmt = select(table).where(table.c.id == applied_task.schedule_type_id)
        sup_info = render2pydantic(
            table=table,
            schema=schemas.M_WORK_SCHEDULE_TYPES,
            values= await execute_stmt(stmt),
        )

    if latest_task.run_time > datetime.datetime.now():
        if datetime.datetime.now().minute == 0:
            logger.info(f"Next task: {latest_task.run_time}")
        return False, None
    return latest_task, sup_info


def write_pid(fname):
    open(fname, mode="w").close()
    lock = FileLock(f"{fname}.lock")
    with lock:
        with open(fname, mode="w") as f:
            f.write(f"{os.getpid()}")


def check_pid(fname):
    with open(fname, mode='r') as f:
        pid = f.read()
    return float(os.getpid()) == float(pid)


async def background_runner(logger: logging.Logger):
    async def update_rows(*, table, item):
        async with async_session() as session:
            await db_utils.update_rows(
                df=pd.DataFrame([item.__dict__]),
                session=session,
                table=table,
                logger=logger,
            )
            await session.commit()

    logger = logger.getChild("bg")
    logger.info(f"process [{os.getpid()}] runner started")
    write_pid(fname="runner.pid")

    while True:
        await asyncio.sleep(5)

        # keep process which have same pid
        if not check_pid(fname="runner.pid"):
            logger.info(f"process [{os.getpid()}] runner quit")
            break

        latest_task, sup_info = await get_tasks(logger)

        # sleep until next task
        if not latest_task:
            await asyncio.sleep(30)
            continue

        # set running status of task
        latest_task.applied = model.ENUM_TASK_STATUS.running
        schema = latest_task.__class__.__name__
        table = model.__dict__[schema.lower()]

        # update to running status
        await update_rows(table=table, item=latest_task)

        # run
        user = await get_user_info(latest_task.user_id)
        if isinstance(latest_task, schemas.T_CLOCK_SCHEDULES):
            runner = Clocker(
                email=user.email,
                password=user.password,
                gps=sup_info.gps,
                runner=sup_info.run_type,
            )
        elif isinstance(latest_task, schemas.T_APPLIED_SCHEDULES):
            nextday = pd.Timestamp.now() + pd.Timedelta(days=1)
            while is_holiday(nextday):
                nextday = pd.Timestamp(nextday) + pd.Timedelta(days=1)
            nextday = nextday.date()

            runner = Clocker(
                email=user.email,
                password=user.password,
                schedule_type=sup_info.clock_type,
                details=sup_info,
                day2apply=nextday.strftime("%Y-%m-%d"),
                runner="apply_telework",
            )
        else:
            raise NotImplementedError
            
        try:
            runner(logger=logger)
            latest_task.applied = model.ENUM_TASK_STATUS.success
            await update_rows(table=table, item=latest_task)

        except Exception:
            logger.error(traceback.format_exc())
            logger.error("An error occuered when running background task.")
            latest_task.applied = model.ENUM_TASK_STATUS.failed

            # update to failed status
            await update_rows(table=table, item=latest_task)
