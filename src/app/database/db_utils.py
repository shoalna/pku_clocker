from typing import Any
import logging
# import datetime
# import enum
from distutils.util import strtobool
import warnings

import pandas as pd
import numpy as np
# from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete, bindparam, update, and_
# from sqlalchemy.inspection import inspect
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy import Enum, Time, Boolean, Integer, DateTime

from . import model as dbmodel

warnings.simplefilter('ignore', FutureWarning)
pd.options.display.max_columns = 999

# async def get_user(db: AsyncSession, user_id: int):
#     result = await (db.execute(select(dbmodel.M_USERS).filter_by(
#         dbmodel.M_USERS.userId == user_id)))
#     user = result.first()
#     if user is None:
#         raise HTTPException(status_code=404, detail="user not found")
#     return user[0]



def assert_model_types(m: Any) -> None:
    pass
    # try:
    #     assert isinstance(m, (dbmodel.M_USERS,
    #                           dbmodel.T_CLOCK_SCHEDULES,
    #                           dbmodel.T_APPLIED_SCHEDULES))
    # except AssertionError:
    #     raise AssertionError(
    #         "Expect a type inherit from model.Base, "
    #         f"like: model.M_USERS, but got {type(m)}")


def get_db_keys(table: dbmodel.Base, primary: bool = False) -> list:
    if not primary:
        return [x.name for x in table.c]
    else:
        return [x.name for x in table.primary_key]


def get_db_sub_keys(table: dbmodel.Base) -> list:
    return list(set(get_db_keys(table=table)) -
                set(get_db_keys(table=table, primary=True)))


def format_df(
        df: pd.DataFrame,
        table: dbmodel.Base,
        logger: logging.Logger) -> pd.DataFrame:
    df = df.copy(deep=True)
    df = df.mask(df == "", np.nan)

    db_keys = get_db_keys(table)

    diff_kesy = set(df.columns) - set(db_keys)
    if diff_kesy:
        logger.warning("Skip format columns since not exist "
                       f"in input df: {diff_kesy}")

    for col in db_keys:
        if col not in df.columns:
            continue
        t_col = table.c[col]
        dtype = t_col.type
        ptype = dtype.python_type
        df[col] = df[col].astype(object)
        # logger.info(f"{col}: dtype - {dtype}, ptype - {ptype}")

        not_na = df[col].notnull()
        if isinstance(dtype, Time):
            df.loc[not_na, col] = df.loc[not_na, col].astype(
                str).apply(pd.Timestamp).apply(
                    lambda x: x.time())
            # logger.info(f"Format {col} to Time")
        elif isinstance(dtype, DateTime):
            df.loc[not_na, col] = pd.to_datetime(
                df.loc[not_na, col]).dt.to_pydatetime()
            # logger.info(f"Format {col} to Date")
        elif isinstance(dtype, Enum):
            # logger.info(f"Skip fromat enum {col}")
            pass
        elif isinstance(dtype, Integer):
            df.loc[not_na, col] = df.loc[not_na, col].astype("Int64")
            # logger.info(f"Format {col} to int")
        elif isinstance(dtype, Boolean):
            df.loc[not_na, col] = (
                df.loc[not_na, col].apply(
                    lambda x: bool(strtobool(str(x)))
                )
            )
            # logger.info(f"Format {col} to bool")


    # format dtypes
    df = df.astype(object)
    df = df.mask(pd.isnull(df), None)
    return df


async def get_rows(
        session: AsyncSession,
        table: dbmodel.Base,
        logger: logging.Logger,
        **filter_kwargs):
    """Get first row from db

    Parameters
    ----------
    session : AsyncSession
        _description_
    table : dbmodel.Base
        _description_
    **filter_kwargs : Any
        Used to filter records in db. Like: {"name": "liu", "userId": 1}

    Returns
    -------
    _type_
        _description_

    Raises
    ------
    AssertionError
        _description_
    HTTPException
        _description_
    """
    stmt = select(table)
    sup_values = {}
    for col, v in filter_kwargs.items():
        t_col = table.c[col]
        dtype = t_col.type

        if col not in table.c:
            raise

        if v is None:
            raise NotImplementedError
        
        stmt = stmt.where(t_col == bindparam(col, dtype))
        try:
            sup_values[col] = dtype.python_type(v)
        except ValueError:
            raise ValueError(f"Cast error. {v} to {dtype.python_type}")

    async with session.begin():
        res = await session.execute(stmt, sup_values)
        res = res.all()
        await session.commit()
    
    df = pd.DataFrame(res, columns=[x.name for x in table.c])
    df = df.drop_duplicates().reset_index(drop=True)

    db_keys = get_db_keys(table)
    for col in db_keys:
        if col not in df.columns:
            continue
        t_col = table.c[col]
        dtype = t_col.type
        # ptype = dtype.python_type
        if isinstance(dtype, Enum):
            df[col] = df[col].apply(lambda x: x.value)
    return df


async def update_table(
        *, df: pd.DataFrame,
        session: AsyncSession,
        table: dbmodel.Base,
        unique_keys: list[str],
        logger: logging.Logger,
        set_increment: str = None):
    db_keys = get_db_keys(table)
    pkeys = get_db_keys(table, primary=True)

    exsit = await get_rows(
        session=session, table=table, logger=logger)

    # merge new and old tables
    df = pd.merge(df, exsit,
                  on=unique_keys, how="outer", suffixes=("", "_old"),
                  indicator=True)

    # exclude rows have no changes
    same_rows = pd.Series(True, index=df.index)
    for col in set(db_keys) - set(unique_keys  + [set_increment]):
        same_rows = same_rows & (
            (df[col] == df[f"{col}_old"]) |
            (df[col].isnull() & df[f"{col}_old"].isnull())
        )
    df = df.loc[~same_rows].reset_index(drop=True)

    # delete those deleted in webapp
    del_df = df[df["_merge"]=="right_only"].reset_index(drop=True)
    del_df = format_df(del_df, table=table, logger=logger)
    if not del_df.empty:
        await delete_row(
            session=session, table=table,
            df=del_df[pkeys], logger=logger
        )
    logger.info(f"Delete {len(del_df)} rows from {table}")

    # set increment
    df = df[df["_merge"]!="right_only"]
    if set_increment is not None:
        df = df.sort_values(by=set_increment).reset_index(drop=True)
        inc_frm = df[set_increment].max()
        if pd.isnull(inc_frm):
            inc_frm = 0
        df[set_increment] = df[set_increment].fillna(
            df[set_increment].isnull().astype(int).cumsum() +
            inc_frm)
    
    logger.info(f"Upsert {len(df)} rows to {table}")
    df = format_df(df, table=table, logger=logger)

    await upsert_rows(
        session=session, table=table, df=df[db_keys], logger=logger
    )
    return df.reset_index(drop=True)


async def upsert_rows(
        *, df: pd.DataFrame,
        session: AsyncSession,
        table: dbmodel.Base,
        logger: logging.Logger):
    assert_model_types(table)
    pkeys = [x.name for x in table.primary_key]
    sub_keys = set([x.name for x in table.columns]) - set(pkeys)

    insert_stmt = insert(table).values(df.to_dict("records"))

    do_update_stmt = insert_stmt.on_conflict_do_update(
        constraint=f"{table.name}_pkey",
        set_={
            k: insert_stmt.excluded[k]
            for k in sub_keys
            if k in df.columns
        })
    async with session.begin():
        await session.execute(do_update_stmt)
        await session.commit()


async def insert_rows(
        *, df: pd.DataFrame,
        session: AsyncSession,
        table: dbmodel.Base,
        logger: logging.Logger,
        on_conflict_do_nothing: bool = False,
):
    insert_stmt = insert(table).values(df.to_dict("records"))
    if on_conflict_do_nothing:
        insert_stmt = insert_stmt.on_conflict_do_nothing()
    
    async with session.begin():
        await session.execute(insert_stmt)
        await session.commit()


async def update_rows(
        *, df: pd.DataFrame,
        session: AsyncSession,
        table: dbmodel.Base,
        logger: logging.Logger):
    assert_model_types(table)
    pkeys = [x.name for x in table.primary_key]
    pkey_diff = set(pkeys) - set(df.columns)
    if pkey_diff:
        raise ValueError(f"Pkey columns must be assigned. {pkey_diff}")

    sub_keys = set([x.name for x in table.c]) - set(pkeys)
    sub_keys = sub_keys & set(df.columns)

    stmt = update(table).\
        where(and_(*[table.c[col] == bindparam(f"b_{col}") for col in pkeys])).\
        values({col: bindparam(f"b_{col}") for col in sub_keys})
    
    df = format_df(df, table=table, logger=logger)
    async with session.begin():
        await session.execute(stmt, df.add_prefix("b_").to_dict("records"))
        await session.commit()


async def delete_row(
        *, df: pd.DataFrame,
        session: AsyncSession,
        table: dbmodel.Base,
        logger: logging.Logger):
    stmt = delete(table)
    df = df[get_db_keys(table=table, primary=True)]
    for col in df.columns:
        stmt = stmt.where(
            table.c[col] == bindparam(col, table.c[col].type)
        )
    async with session.begin():
        await session.execute(stmt, df.to_dict("records"))
        await session.commit()
