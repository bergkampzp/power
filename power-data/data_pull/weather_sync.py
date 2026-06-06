import weather_forecast_fetch as wf

def sync_weather_incremental(conn):
    """Pull next-day weather forecast (no cookie needed). Returns row count."""
    wf.ensure_table(conn)
    wf.run_live(conn)
    return conn.execute("SELECT COUNT(*) FROM weather_forecast").fetchone()[0]
