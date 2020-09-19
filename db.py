import sqlite3
from sqlite3 import Error


def create_connection(db_file):
    """ create a database connection to the SQLite database
        specified by db_file
    :param db_file: database file
    :return: Connection object or None
    """
    conn = None
    try:
        conn = sqlite3.connect(db_file, detect_types=sqlite3.PARSE_DECLTYPES)
        sqlite3.register_adapter(bool, int)
        sqlite3.register_converter("BOOLEAN", lambda v: bool(int(v)))
    except Error as e:
        print(e)

    return conn

def create_live_table(conn):
    sql = """CREATE TABLE IF NOT EXISTS live_table (
                gameweek integer NOT NULL,
                user_id integer NOT NULL,
                event_total integer NOT NULL,
                UNIQUE(gameweek, user_id) ON CONFLICT REPLACE
            );
    """
    create_table(conn, sql)

def create_picks_table(conn):
    sql = """CREATE TABLE IF NOT EXISTS picks (
                picks_id integer PRIMARY KEY,
                gameweek integer NOT NULL,
                user_id integer NOT NULL,
                position integer NOT NULL,
                player_id integer NOT NULL,
                multiplier integer NOT NULL,
                is_captain BOOLEAN,
                is_vice_captain BOOLEAN,
                UNIQUE(gameweek, user_id, position) ON CONFLICT REPLACE
            );
    """
    create_table(conn, sql)
    
def create_player_points_table(conn):
    sql = """CREATE TABLE IF NOT EXISTS live_player_points (
                live_player_points_id integer PRIMARY KEY,
                gameweek integer NOT NULL,
                player_id integer NOT NULL,
                points integer NOT NULL,
                minutes integer,
                UNIQUE(gameweek, player_id) ON CONFLICT REPLACE
            );
    """
    create_table(conn, sql)

def create_table(conn, create_table_sql):
    """ create a table from the create_table_sql statement
    :param conn: Connection object
    :param create_table_sql: a CREATE TABLE statement
    :return:
    """
    try:
        c = conn.cursor()
        c.execute(create_table_sql)
    except Error as e:
        print(e)

def add_live_points(conn, data):
    sql = ''' REPLACE INTO live_player_points(gameweek, player_id, points, minutes)
              VALUES(?, ?, ?, ?) '''
    cur = conn.cursor()
    cur.execute(sql, data)
    conn.commit()
    return cur.lastrowid

def add_pick(conn, data):
    """
    Create a new data
    :param conn:
    :param data:
    :return:
    """
    
    #print(data)

    sql = ''' REPLACE INTO picks(gameweek, user_id, player_id, position, multiplier, is_captain, is_vice_captain)
              VALUES(?, ?, ?, ?, ?, ?, ?) '''
    cur = conn.cursor()
    cur.execute(sql, data)
    conn.commit()
    return cur.lastrowid

def update_live_scores(conn, gameweek, userId, autoSubsArr, bboostActive, xferCost):
    sql = ''' REPLACE INTO live_table (
                gameweek, user_id, event_total
            ) select 
                live_player_points.gameweek, picks.user_id, sum(live_player_points.points * picks.multiplier) - ? as event_total 
            from 
                live_player_points 
            left join 
                picks 
            on 
                live_player_points.player_id = picks.player_id and live_player_points.gameweek = picks.gameweek
            where 
                live_player_points.gameweek = ?
            and
                picks.user_id = ?
            and
                (picks.position <= ? OR picks.player_id in (?))
            group by 
                live_player_points.gameweek, picks.user_id '''
                
    cur = conn.cursor()
    playerLimit = 15 if bboostActive else 11
    if autoSubsArr:
        print("sql subs %s " % ','.join(str(v) for v in autoSubsArr))
    cur.execute(sql, [xferCost, gameweek, userId, playerLimit, ','.join(str(v) for v in autoSubsArr)])
    conn.commit()
    return cur.lastrowid
    
def select_live_scores(conn, gameweek):
    sql = ''' SELECT * FROM live_table WHERE gameweek = ? '''
    cur = conn.cursor()
    cur.execute(sql, [gameweek])
    result = cur.fetchall()
    return result