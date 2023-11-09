from distutils.util import strtobool
from typing import List, Dict, Literal
import json
import datetime
from contextlib import asynccontextmanager

import pandas as pd
import numpy as np

from fastapi import FastAPI
from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import delete
from fastapi import Depends
from starlette.middleware import Middleware
from starlette.middleware.cors import CORSMiddleware
from fastapi import HTTPException
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from custom_logger import set_logger
# from model import ConfigModel
from database import model, db_utils
from database.database import get_session
from core import task


# CORS config
middleware = [
    Middleware(
        CORSMiddleware,
        allow_origins=['*'],
        allow_credentials=True,
        allow_methods=['*'],
        allow_headers=['*']
    )
]

logger = set_logger(__name__, fname=None)


# @asynccontextmanager
# async def lifespan(app: FastAPI):
#     # await task.background_updater(logger)
#     await task.background_runner(logger)
#     yield


# app = FastAPI(middleware=middleware, lifespan=lifespan)
app = FastAPI(middleware=middleware)


@app.on_event("startup")
async def startup_event():
    import asyncio
    # update schedules and init runners
    asyncio.create_task(task.background_updater(logger))
    asyncio.create_task(task.background_runner(logger))


# HTML Response
app.mount("/assets", StaticFiles(directory="templates/assets",html = True), name="assets")
templates = Jinja2Templates(directory="templates")


@app.get("/", response_class=HTMLResponse, tags=["html"])
def index(request: Request):
    context = {"request": request}
    return templates.TemplateResponse("index.html", context)


@app.get("/api/users")
async def get_users(
        brief: str = "False",
        session: AsyncSession = Depends(get_session)):
    """_summary_

    Parameters
    ----------
    name : str, optional
        _description_, by default None
    email : str, optional
        _description_, by default None
    password : str, optional
        _description_, by default None
    brief : str, optional
        only return email list when true, by default "False"
    session : AsyncSession, optional
        _description_, by default Depends(get_session)

    Returns
    -------
    _type_
        _description_
    """
    m_users = await db_utils.get_rows(
        session=session, table=model.m_users, logger=logger)
    if m_users.empty:
        logger.info("Empty m_users")
        return []

    if strtobool(brief):
        return list(m_users["email"].unique())

    m_users.drop(columns=["user_id"], inplace=True)
    return m_users.to_dict('records')


@app.post("/api/users/update")
async def insert_user(
        users: List[Dict],
        session: AsyncSession = Depends(get_session)):
    df = pd.DataFrame(users)
    upserted_df: pd.DataFrame = await db_utils.update_table(
        df=df,
        session=session,
        table=model.m_users,
        unique_keys="email",
        set_increment="user_id",
        logger=logger,
    )

    # insert users to t_basic_types
    keys = [x.name for x in model.t_basic_types.c]
    t_basic = await db_utils.get_rows(
        session=session, table=model.t_basic_types, logger=logger)
    upserted_df = pd.merge(upserted_df, t_basic, on="user_id",
                           suffixes=("_drop", ""), how="left")

    await db_utils.update_table(
        df=upserted_df[keys],
        session=session,
        table=model.t_basic_types,
        unique_keys="user_id",
        logger=logger,
    )
    return "OK"


@app.get("/api/users/delete")
async def delete_user(
        uid: int,
        name: str,
        email: str,
        password: str,
        session: AsyncSession = Depends(get_session)):
    df = pd.DataFrame({"user_id": [uid], "name": [name],
                       "email": [email], "password": [password]})
    await db_utils.delete_row(
        session=session, table=model.m_users, df=df, logger=logger
    )
    return "OK"


# work types
@app.get("/api/selectTypes")
async def get_all_types(session: AsyncSession = Depends(get_session)):
    wtypes: pd.DataFrame = await db_utils.get_rows(
        session=session, table=model.m_work_types, logger=logger)

    stypes: pd.DataFrame = await db_utils.get_rows(
        session=session, table=model.m_work_schedule_types, logger=logger)
    
    return list(set((wtypes["type_name"]).to_list()) |
                set((stypes["type_name"]).to_list()))


# work types
@app.get("/api/worktypes")
async def get_work_types(
        brief: str = "false",
        type: Literal["in", "out"] = "in",
        session: AsyncSession = Depends(get_session)):
    types: pd.DataFrame = await db_utils.get_rows(
        session=session, table=model.m_work_types, logger=logger)

    if strtobool(brief):
        if type == "in":
            return types.loc[
                types["run_type"] == model.ENUM_RUN_TYPE_NAME.cin.value,
                "type_name"].to_list()
        elif type == "out":
            return types.loc[
                types["run_type"] == model.ENUM_RUN_TYPE_NAME.cout.value,
                "type_name"].to_list()
        else:
            raise
    return types.drop(columns="id").to_dict('records')


# work types
@app.post("/api/worktypes/update")
async def add_work_types(
        work_types: List[Dict],
        session: AsyncSession = Depends(get_session)):
    df = pd.DataFrame(work_types)
    await db_utils.update_table(
        df=df,
        session=session,
        table=model.m_work_types,
        unique_keys=["run_type", "run_time", "gps"],
        set_increment="id",
        logger=logger,
    )
    return "OK"


# work_schedule_types
@app.get("/api/stypes")
async def get_work_stypes(
        brief: str = "false",
        session: AsyncSession = Depends(get_session)):
    types: pd.DataFrame = await db_utils.get_rows(
        session=session, table=model.m_work_schedule_types, logger=logger)
    if strtobool(brief):
        return list(types["type_name"].unique())
    return types.drop(columns="id").to_dict('records')


# work_schedule_types
@app.post("/api/stypes/update")
async def update_work_stypes(
        stypes: List[Dict],
        session: AsyncSession = Depends(get_session)):
    df = pd.DataFrame(stypes)
    await db_utils.update_table(
        df=df,
        session=session,
        table=model.m_work_schedule_types,
        unique_keys=["type_name"],
        set_increment="id",
        logger=logger,
    )
    return "OK"


@app.get("/api/run_types")
async def get_run_types():
    return {"types": [model.ENUM_RUN_TYPE_NAME.cin.value,
                      model.ENUM_RUN_TYPE_NAME.cout.value]}


@app.get("/api/test")
async def get_something(session: AsyncSession = Depends(get_session)):
    from sqlalchemy import select, func
    logger.info("hello!!!!")

    table = model.t_clock_schedules
    stmt = select(table).where(
        table.c.run_time == select(func.min(table.c.run_time)).scalar_subquery())
    logger.info(stmt)

    async with session.begin():
        res = await session.execute(stmt)
        res = res.all()
        await session.commit()
    logger.info(res)
    from database import schemas
    res_t = schemas.T_CLOCK_SCHEDULES(**(dict(zip([x.name for x in table.c], res[0]))))
    logger.info(res_t)
    logger.info(res_t.user_id)
    
    df = pd.DataFrame(res, columns=[x.name for x in table.c])
    df = df.drop_duplicates().reset_index(drop=True)
    return df.to_dict('records')


@app.post("/api/tasks/update")
async def update_all_tasks(
        tasks: Dict,
        session: AsyncSession = Depends(get_session)):
    
    email = tasks.pop("email")
    tasks = tasks["tasks"]
    assert (email is not None) and (tasks is not None)

    # get user id
    users: pd.DataFrame = await db_utils.get_rows(
        session=session, table=model.m_users,
        email=email, logger=logger)

    if users.empty:
        return []
    uid = users["user_id"].values[0]

    rename = {
        "task_name": "run_type",
        "task_type": "type_name",
        "runtime": "run_time",
        "actions": "active",
        "status": "applied",
    }
    df = pd.DataFrame(json.loads(tasks))[list(rename.keys())].rename(columns=rename)
    df["run_date"] = pd.to_datetime(pd.to_datetime(df["run_time"]).dt.date)

    # update the part of t_clock_schedules
    ctask_df = df[df["run_type"].isin([
        model.ENUM_RUN_TYPE_NAME.cin.value,
        model.ENUM_RUN_TYPE_NAME.cout.value,
    ])].reset_index(drop=True)
    # ctask_df["run_date"] = pd.to_datetime(ctask_df["run_time"]).dt.date()
    ctask_df["user_id"] = uid

    # merge work types id
    ctypes: pd.DataFrame = await db_utils.get_rows(
        session=session, table=model.m_work_types, logger=logger)
    ctask_df = pd.merge(ctask_df, ctypes.add_prefix("work_type_"),
                        left_on="type_name", right_on="work_type_type_name",
                        how="left")
    
    db_keys = db_utils.get_db_keys(model.t_clock_schedules)
    pkeys = db_utils.get_db_keys(model.t_clock_schedules, primary=True)
    subkeys = db_utils.get_db_sub_keys(model.t_clock_schedules)

    ctask_df = ctask_df.reset_index(drop=True)

    # getold table and overwrite run time when type is changed
    old_ctasks: pd.DataFrame = await db_utils.get_rows(
        session=session, table=model.t_clock_schedules,
        logger=logger, user_id=uid)
    # old_ctasks["run_type"] = old_ctasks["run_type"].apply(lambda x: x.value)
    # old_ctasks["applied"] = old_ctasks["applied"].apply(lambda x: x.value)

    ctask_df = pd.merge(ctask_df, old_ctasks,
                        on=pkeys, how="left", suffixes=("", "_old"))

    same_row = pd.Series(True, index=ctask_df.index)
    for col in subkeys:
        same_row = same_row & (ctask_df[col] == ctask_df[f"{col}_old"])
    ctask_df = ctask_df.loc[~same_row].reset_index(drop=True)

    if not ctask_df.empty:        
        # renew run_time by changed run_type
        ctask_df["run_time"] = pd.to_datetime(
            ctask_df["run_date"].astype(str) + " " +
            ctask_df["work_type_run_time"].astype(str))

        # add random time diff
        ctask_df["run_time"] = ctask_df["run_time"] + pd.to_timedelta(
            np.random.randint(-300, 300, size=len(ctask_df)), unit="s")

        await db_utils.update_rows(
            df=ctask_df,
            session=session,
            table=model.t_clock_schedules,
            logger=logger,
        )

    # update the part of t_applied_schedules
    stask_df = df[df["run_type"].isin([
        model.ENUM_RUN_TYPE_NAME.schedule.value,
    ])]
    stask_df["user_id"] = uid
    # stask_df["run_date"] = pd.to_datetime(stask_df["run_date"]).dt.date

    # merge schedule types
    stypes: pd.DataFrame = await db_utils.get_rows(
        session=session, table=model.m_work_schedule_types, logger=logger)
    stask_df = pd.merge(stask_df, stypes.add_prefix("schedule_type_"),
                        left_on="type_name", right_on="schedule_type_type_name",
                        how="left")

    await db_utils.update_rows(
        df=stask_df,
        session=session,
        table=model.t_applied_schedules,
        logger=logger,
    )

@app.get("/api/tasks")
async def get_all_tasks(
        email: str,
        session: AsyncSession = Depends(get_session)):
    return await get_merged_tasks(email=email, session=session)


async def get_merged_tasks(email: str, session: AsyncSession):

    # get user id
    users: pd.DataFrame = await db_utils.get_rows(
        session=session, table=model.m_users,
        email=email, logger=logger)

    if users.empty:
        return []
    uid = users["user_id"].values[0]

    # get planned clock tasks
    clock_tasks: pd.DataFrame = await db_utils.get_rows(
        session=session, table=model.t_clock_schedules,
        logger=logger, user_id=uid)
    clock_tasks = clock_tasks[clock_tasks["user_id"] == uid]
    
    # get planned apply tasks
    apply_tasks: pd.DataFrame = await db_utils.get_rows(
        session=session, table=model.t_applied_schedules,
        logger=logger, user_id=uid)
    apply_tasks = apply_tasks[apply_tasks["user_id"] == uid]

    # return empty result if no tasks created yet
    if clock_tasks.empty and apply_tasks.empty:
        return []

    # transfer id to name
    tmp: pd.DataFrame = await db_utils.get_rows(
        session=session, table=model.m_work_types, logger=logger)
    clock_tasks = pd.merge(clock_tasks, tmp, left_on="work_type_id",
                           right_on="id", how="left", suffixes=("", "_drop"))

    # format date to response webapp
    clock_tasks["apply_date"] = clock_tasks["run_time"].copy()

    tmp: pd.DataFrame = await db_utils.get_rows(
        session=session, table=model.m_work_schedule_types, logger=logger)
    apply_tasks = pd.merge(apply_tasks, tmp, left_on="schedule_type_id",
                           right_on="id", how="left", suffixes=("", "_drop"))

    # merge clock_tasks with details
    rename = {
        "run_type": "task_name",
        "type_name": "task_type",
        "run_time": "runtime",
        "applied": "status",
        "active": "actions",
        "apply_date": "apply_date",
    }
    cols = list(set(rename.values()))
    res = pd.concat([
        clock_tasks.rename(columns=rename)[cols],
        apply_tasks.rename(columns=rename)[cols],
    ], axis=0).reset_index(drop=True)

    # format date to response webapp
    res["apply_date"] = pd.to_datetime(
        res["apply_date"]).dt.strftime("%Y-%m-%d").fillna("")
    res["runtime"] = pd.to_datetime(res["runtime"]).dt.strftime("%Y-%m-%d %H:%M:%S")
    return res.to_dict('records')


@app.get("/api/tasks/delete")
async def delete_old_tasks(
        email: str,
        session: AsyncSession = Depends(get_session)):
    # NOTE:
    # Use emial only for webapp content.
    # The email assgined have no influence on the result
    async def delete_lt_now_rows(table, time_col: str):
        stmt = delete(table).where(
            table.c[time_col] < datetime.datetime.now())
        async with session.begin():
            await session.execute(stmt)
            logger.info(stmt)
            await session.commit()

    await delete_lt_now_rows(model.t_clock_schedules, "run_time")
    await delete_lt_now_rows(model.t_applied_schedules, "run_time")
    return await get_merged_tasks(email=email, session=session)


# work_schedule_types
@app.get("/api/usersBasic")
async def get_basic(session: AsyncSession = Depends(get_session)):
    types: pd.DataFrame = await db_utils.get_rows(
        session=session, table=model.t_basic_types, logger=logger)
    if types.empty:
        return []
    
    users: pd.DataFrame = await db_utils.get_rows(
        session=session, table=model.m_users, logger=logger)
    types = pd.merge(types, users, on="user_id", validate="1:1")
    return types[["email", "clockin_type_name",
                  "clockout_type_name", "schedule_type_name"]].to_dict('records')


@app.post("/api/usersBasic/update")
async def update_basic(
        types: List[Dict],
        session: AsyncSession = Depends(get_session)):
    df = pd.DataFrame(types)

    # merge user_id to email
    users: pd.DataFrame = await db_utils.get_rows(
        session=session, table=model.m_users, logger=logger)
    df = pd.merge(df, users, how="left", on="email", validate="1:1")

    # update t_basic_types
    keys = [x.name for x in model.t_basic_types.c]
    await db_utils.update_table(
        df=df[keys],
        session=session,
        table=model.t_basic_types,
        unique_keys=["user_id"],
        set_increment=None,
        logger=logger,
    )

    # update t_clock_schedules and t_applied_schedules
    await task.build_tasks(session ,logger)
    return "OK"