import sqlite3


def update_pending_predictions(conn: sqlite3.Connection) -> None:
    cursor = conn.execute(
        "SELECT code FROM prediction_records WHERE status = '待开奖'"
    )
    pending_codes = [row[0] for row in cursor.fetchall()]
    for code in pending_codes:
        draw = conn.execute(
            "SELECT red FROM draw_results WHERE code = ?",
            (code,),
        ).fetchone()
        if draw:
            conn.execute(
                """
                UPDATE prediction_records
                SET red = ?, status = '已开奖'
                WHERE code = ?
                """,
                (draw[0], code),
            )
    conn.commit()
