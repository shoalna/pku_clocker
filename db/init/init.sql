
CREATE DATABASE auto_clockin;
\c auto_clockin

--テーブルを作成
CREATE TABLE m_users (
  user_id integer PRIMARY KEY, 
  email text UNIQUE, 
  password text,
  memo text
);


CREATE TYPE enum_run_type_name AS ENUM ('出勤', '退勤', '実績スケジュール申請');

CREATE TABLE m_work_types (
  id integer PRIMARY KEY, 
  type_name text UNIQUE,
  run_type enum_run_type_name,
  run_time time,
  gps text
);


CREATE TYPE enum_task_status AS ENUM ('success', 'failed', 'running', 'pending');
CREATE TABLE t_clock_schedules (
  user_id integer, 
  work_type_id integer,
  run_type enum_run_type_name,
  run_time timestamp,
  run_date timestamp,
  applied enum_task_status default 'pending',
  active boolean,
  FOREIGN KEY (user_id) references m_users(user_id) ON DELETE cascade,
  FOREIGN KEY (work_type_id) references m_work_types(id) ON DELETE cascade,
  PRIMARY KEY (user_id, run_date, run_type)
);


-- CREATE TYPE enum_schedule_clock_type_name AS ENUM ('通常勤務', 'カスタム');

CREATE TABLE m_work_schedule_types (
  id integer PRIMARY KEY, 
  type_name text UNIQUE,
  memo text,
  run_time time,
  telework boolean,
  clock_type text,
  clockin time,
  clockout time,
  breakin time,
  breakout time,
  msg text
);


CREATE TABLE t_applied_schedules (
  user_id integer, 
  schedule_type_id integer,
  run_type enum_run_type_name,
  run_date timestamp,
  run_time timestamp,
  apply_date timestamp,
  applied enum_task_status,
  active boolean,
  FOREIGN KEY (user_id) references m_users(user_id) ON DELETE cascade,
  FOREIGN KEY (schedule_type_id) references m_work_schedule_types(id) ON DELETE cascade,
  PRIMARY KEY (user_id, run_date)
);

CREATE TABLE t_basic_types (
  user_id integer PRIMARY KEY, 
  clockin_type_name text,
  clockout_type_name text,
  schedule_type_name text,
  FOREIGN KEY (user_id) references m_users(user_id) ON DELETE cascade,
  FOREIGN KEY (clockin_type_name) references m_work_types(type_name) ON DELETE cascade,
  FOREIGN KEY (clockout_type_name) references m_work_types(type_name) ON DELETE cascade,
  FOREIGN KEY (schedule_type_name) references m_work_schedule_types(type_name) ON DELETE cascade
);

\COPY m_users from './m_user.csv' with csv header;
\COPY m_work_schedule_types from './m_work_schedule_types.csv' with csv header;
\COPY m_work_types from './m_work_types.csv' with csv header;

\COPY t_basic_types from './t_basic_types.csv' with csv header;
\COPY t_applied_schedules from './t_applied_schedules.csv' with csv header;
\COPY t_clock_schedules from './t_clock_schedules.csv' with csv header;