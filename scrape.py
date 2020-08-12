import asyncio
import aiohttp
import argparse

from fpl import FPL
from fpl.utils import get_current_gameweek

from db import create_connection, add_pick, create_picks_table, create_player_points_table, add_live_points, create_live_table, update_live_scores


async def load_users(fpl, leagueObj, gameweek):
    users = []
    pageCounter = 1
    while True:
        leaguePage = await leagueObj.get_standings(pageCounter, 0, gameweek)
        
        for resultUser in leaguePage["results"]:
            userObj = await fpl.get_user(resultUser["entry"])
            users.append(userObj)
        
        if leaguePage["has_next"] is True:
            pageCounter = pageCounter + 1
        else:
            return users

async def load_user_picks(conn, users, gameweek):
    for userObj in users:
        #print(vars(userObj))
        userPicks = await userObj.get_picks(gameweek)
        #print(userPicks)
        if userPicks:
            for pick in userPicks[gameweek]:
                data = [gameweek, userObj.id, pick["element"], pick["position"], pick["multiplier"], pick["is_captain"], pick["is_vice_captain"]]
                add_pick(conn, data)

async def load_player_points(conn, fpl, gameweek):
    gameweekObj = await fpl.get_gameweek(gameweek, include_live=True, return_json=False)
    #print(gameweekObj.elements)
    for playerId in gameweekObj.elements:
        points = 0
        for detail in gameweekObj.elements[playerId]["explain"][0]["stats"]:
            points += detail["points"]
        data = [gameweek, playerId, points]
        add_live_points(conn, data)
        
async def update_user_points(conn, users, gameweek):
    for userObj in users:
        #print(vars(userObj))
        
        autoSubsArr = []
        autoSubObjArr = await userObj.get_automatic_substitutions(gameweek)
        if autoSubObjArr:
            for autoSubObj in autoSubObjArr:
                autoSubsArr.append(autoSubObj["element_in"])
        
        userActiveChips = await userObj.get_active_chips(gameweek)
        #print(userActiveChips)
        update_live_scores(conn, gameweek, userObj.id, autoSubsArr, userActiveChips == 'bboost')


async def main():
    parser = argparse.ArgumentParser(description='EliteFPL Scraper')
    parser.add_argument('email', type=str, help='FPL Email Address')
    parser.add_argument('password', type=str, help='FPL Password')
    parser.add_argument('--gameweek', type=int, default=0, help='Set the current gameweek')
    args = parser.parse_args()
    
    try:
        database = "/tmp/fplsqlite.db"
        conn = create_connection(database)
        create_picks_table(conn)
        create_player_points_table(conn)
        create_live_table(conn)
    except:
        raise
    
    async with aiohttp.ClientSession() as session:
        fpl = FPL(session)
        await fpl.login(args.email, args.password)
        leagueObj = await fpl.get_classic_league(345)
        #print(leagueObj)
        
        if args.gameweek > 0:
            gameweek = args.gameweek
        else:
            gameweek = await get_current_gameweek(fpl.session)
                
        users = await load_users(fpl, leagueObj, gameweek)
        
        #we only need to do this once per week, asap after game updates
        await load_user_picks(conn, users, gameweek)
        
        #we need to keep doing this until matches are finished
        await load_player_points(conn, fpl, gameweek)
        
        #and finally create a live table
        await update_user_points(conn, users, gameweek)


asyncio.run(main())
