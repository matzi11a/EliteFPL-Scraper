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

async def get_player_points(fpl, gameweek):
    gameweekObj = await fpl.get_gameweek(gameweek, include_live=True, return_json=False)
    #print(gameweekObj.elements)
    playerPoints = {}
    for playerId in gameweekObj.elements:
        points = 0
        minutes = 0;
        for detail in gameweekObj.elements[playerId]["explain"][0]["stats"]:
            points += detail["points"]
            if (detail["identifier"] == 'minutes'):            
                minutes += detail["value"]
        playerPoints[playerId] = [gameweek, playerId, points, minutes]
    return playerPoints

async def load_live_points(conn, data):
    for playerId in data:
        add_live_points(conn, data[playerId])
    
async def update_user_points(conn, users, gameweek, subs):
    for userObj in users:
        #print(vars(userObj))
        
        autoSubsArr = list(subs[userObj.id].keys()) 
        #autoSubObjArr = await userObj.get_automatic_substitutions(gameweek)
        #if autoSubObjArr:
        #    for autoSubObj in autoSubObjArr:
        #        autoSubsArr.append(autoSubObj["element_in"])
        #        print("subs arr %s %s" % (userObj.id, autoSubObj))
        
        userActiveChips = await userObj.get_active_chips(gameweek)
        #print(userActiveChips)
        update_live_scores(conn, gameweek, userObj.id, autoSubsArr, userActiveChips == 'bboost')

async def process_team(team, tmp, finished):
    for player in await team.get_players():
        #print(player)
        if (player.id in tmp):
            tmp[player.id] = tmp[player.id] and finished
        else:
            tmp[player.id] = finished

async def sub_is_valid(playerId, subPlayerId, userPicks):
    print("Subbin in %d for %d" % (subPlayerId, playerId))
    #need to check formation
    return True

async def get_sub(playerId, subs, userPicks):
    for pick in userPicks:
        subPlayerId = pick["element"]
        if (pick['position'] > 11 and subPlayerId not in subs):
            if await sub_is_valid(playerId, subPlayerId, userPicks):
                return subPlayerId
        

async def _calc_auto_subs(fpl, users, gameweek, playerData):
    fixtures = await fpl.get_fixtures_by_gameweek(gameweek)
    tmp = {}
    for fixture in fixtures:
        homeTeam = await fpl.get_team(fixture.team_h)
        for player in await homeTeam.get_players():
            #print(player)
            if (player.id in tmp):
                tmp[player.id] = tmp[player.id] and fixture.finished
            else:
                tmp[player.id] = fixture.finished
        awayTeam = await fpl.get_team(fixture.team_a)
        for player in await awayTeam.get_players():
            #print(player)
            if (player.id in tmp):
                tmp[player.id] = tmp[player.id] and fixture.finished
            else:
                tmp[player.id] = fixture.finished

    #for pid, fixtureFinished in tmp.items():
    #    playerData[pid].append(fixtureFinished)
    userSubs = {}
    for userObj in users:
        #print(vars(userObj))
        userPicks = await userObj.get_picks(gameweek)
        #print(userPicks)
        if userPicks:
            subs = {}
            for pick in userPicks[gameweek]:
                playerId = pick["element"]
                #print(playerData)
                if (tmp[playerId] and pick['position'] <= 11 and playerData[playerId][3] == 0):
                    print("didnt play: %s %s" % (userObj.id, pick))
                    sub = await get_sub(playerId, subs, userPicks[gameweek])
                    if (sub > 0):
                        subs[sub] = True
            userSubs[userObj.id] = subs
    return userSubs
                    


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
        
        
        playerPoints = await get_player_points(fpl, gameweek)
        await load_live_points(conn, playerPoints)
        
        
        subs = await _calc_auto_subs(fpl, users, gameweek, playerPoints)
        

        await load_user_picks(conn, users, gameweek)

        #and finally create a live table
        await update_user_points(conn, users, gameweek, subs)


asyncio.run(main())
