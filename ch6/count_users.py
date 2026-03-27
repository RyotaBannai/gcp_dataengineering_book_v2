"""
ワークフロー管理
"""

import datetime
import os

import airflow
import pendulum
from airflow.contrib.operators import (
    bigquery_operator,
    bigquery_table_delete_operator,
    gcs_to_bq,
)

# DAG内のオペレータ共通のパラメータを定義する。
default_args = {
    "owner": "gcpbook",
    "depends_on_past": False,
    "email": [""],
    "email_on_failure": False,
    "email_on_retry": False,
    "retries": 1,
    "retry_delay": datetime.timedelta(minutes=5),
    # DAG作成日の午前2時(JST)を開始日時とする。
    "start_date": pendulum.today("Asia/Tokyo").add(hours=2),
}

# DAGを定義する。
with airflow.DAG(
    "count_users",
    default_args=default_args,
    # 日次でDAGを実行する。
    schedule_interval=datetime.timedelta(days=1),
    catchup=False,
) as dag:
    # Cloud Storage上のユーザ行動ログをBigQueryの作業用テーブルへ
    # 取り込むタスクを定義する。
    load_events = gcs_to_bq.GoogleCloudStorageToBigQueryOperator(
        task_id="load_events",
        # Cloud Composerで作成した環境にセットしている環境変数を取り出す（ここではMY_PROJECT_IDを事前に設定していることを想定）
        bucket=os.environ.get("MY_PROJECT_ID") + "-gcpbook-ch05",
        source_objects=["data/events/{{ ds_nodash }}/*.json.gz"],
        destination_project_dataset_table="gcpbook_ch5_table.work_events",
        source_format="NEWLINE_DELIMITED_JSON",
    )

    # BigQueryの作業用テーブルとユーザ情報テーブルを結合し、
    # 課金ユーザと無課金ユーザそれぞれのユーザ数を算出して、結果をgcpbook_ch5.dau
    # テーブルへ書き込むタスクを定義する。
    insert_dau = bigquery_operator.BigQueryOperator(
        task_id="insert_dau",
        use_legacy_sql=False,
        sql="""
            insert gcpbook_ch5_table.dau
            select
                date('{{ ds }}') as dt
            ,   countif(u.is_paid_user) as paid_users
            ,   countif(not u.is_paid_user) as free_to_play_users
            from
                (
                    select distinct
                        user_pseudo_id
                    from
                        gcpbook_ch5_table.work_events
                ) e
                    inner join
                        gcpbook_ch5_table.users u
                    on
                        u.user_pseudo_id = e.user_pseudo_id
        """,
    )

    # BigQueryの作業用テーブルを削除するタスクを定義する。
    delete_work_table = bigquery_table_delete_operator.BigQueryTableDeleteOperator(
        task_id="delete_work_table",
        deletion_dataset_table="gcpbook_ch5_table.work_events",
    )

    # 各タスクの依存関係を定義する。
    load_events >> insert_dau >> delete_work_table
