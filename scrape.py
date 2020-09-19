import asyncio
import aiohttp
import argparse
import json

from fpl import FPL
from fpl.utils import get_current_gameweek

from db import create_connection, add_pick, create_picks_table, create_player_points_table, add_live_points, \
    create_live_table, update_live_scores, select_live_scores


async def load_users(fpl, leagueObj, gameweek):
    users = []
    pageCounter = 1
    while True:
        leaguePage = await leagueObj.get_standings(pageCounter, 1, gameweek)
        
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


async def sub_is_valid(fpl, playerId, subPlayerId, userPicks):
    print("Subbin in %d for %d" % (subPlayerId, playerId))
    valid_formations = {"1-3-5-2", "1-4-4-2", "1-4-5-2", "1-3-4-3", "1-4-3-3", "1-5-2-3", "1-5-3-1"}
    formation = {}
    for pick in userPicks:
        if ((pick['position'] <= 11 or pick['element'] == subPlayerId) and (pick['element'] != playerId)):
            player = await fpl.get_player(pick['element'])
            if formation[player['element_type']]:
                formation[player['element_type']] = formation[player['element_type']] + 1
            else:
                formation[player['element_type']] = 1
    print(vars(formation))

    #    1: "Goalkeeper",
    #    2: "Defender",
    #    3: "Midfielder",
    #    4: "Forward"
    formation_string = "{}-{}-{}-{}".format(formation[1], formation[2], formation[3], formation[4])

    print(formation_string in valid_formations)

    return formation_string in valid_formations


async def get_sub(fpl, playerId, subs, userPicks, playerData):
    for pick in userPicks:
        subPlayerId = pick["element"]
        if (pick['position'] > 11 and subPlayerId not in subs and subPlayerId in playerData):
            if (playerData[subPlayerId][2] != 0) and await sub_is_valid(fpl, playerId, subPlayerId, userPicks):
                return subPlayerId
    return 0
        

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
                    subPlayerId = await get_sub(fpl, playerId, subs, userPicks[gameweek].copy(), playerData)
                    if (subPlayerId > 0):
                        subs[subPlayerId] = True
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
        leagueObj = await fpl.get_classic_league(30724)
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

        output = select_live_scores(conn, gameweek)
        with open('/usr/share/nginx/html/out.json', 'w') as outfile:
            json.dump(output, outfile)


asyncio.run(main())
