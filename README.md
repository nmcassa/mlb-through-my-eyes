# mlb-through-my-eyes

Hello, 

Inspired partial by the rategame.io app, I love the idea of being able to log my games and look back on them. One thing that I have been wondering is: *if i only watch some of the games, how does my perspective of a player differ from their true performance*

If I have a low sample size of Ian Happ games watched, but in those few games he played amazing... I might just think he is the best player ever. If I watch two Bryce Elder starts and he blows both of them wide open I think he is the worst starter ever. 

So the goal here is to make a little CLI app that can track the games I have logged and eventually give me fun stats about my small sample size of games and how they relate to a players career or season. 

Hopefully I can have a summary of players that I have seen play much better than their average, and some players that I have seen play much worse. 

## Current Example

Only my watched games (*40 braves games*)

```
============================================================
  ⚾  Batter Summary
============================================================

  145 batters  |  min 5 AB  |  sorted by Appearances  |  showing top 25

Name                    Team                     App     AB      H     AVG    OBP    SLG    OPS
  --------------------------------------------------------------------------------
  Matt Olson              Atlanta Braves            40    158     48   0.304  0.364  0.557  0.921
  Ozzie Albies            Atlanta Braves            40    147     45   0.306  0.370  0.510  0.881
  Austin Riley            Atlanta Braves            40    143     33   0.231  0.308  0.336  0.644
  Mauricio Dubón          Atlanta Braves            39    153     43   0.281  0.312  0.490  0.803
  Michael Harris II       Atlanta Braves            36    138     41   0.297  0.322  0.486  0.807
  Mike Yastrzemski        Atlanta Braves            35    102     21   0.206  0.277  0.304  0.581
  Dominic Smith           Atlanta Braves            31     84     22   0.262  0.319  0.429  0.747
  Drake Baldwin           Atlanta Braves            28    112     28   0.250  0.311  0.455  0.767
  Ronald Acuña Jr.        Atlanta Braves            26     97     27   0.278  0.381  0.402  0.783
  Jorge Mateo             Atlanta Braves            21     48     12   0.250  0.294  0.375  0.669
  Eli White               Atlanta Braves            18     42      9   0.214  0.250  0.405  0.655
  Sandy León              Atlanta Braves            10     26      4   0.154  0.154  0.154  0.308
  Ha-Seong Kim            Atlanta Braves             9     28      3   0.107  0.194  0.107  0.301
  Kyle Farmer             Atlanta Braves             6      8      2   0.250  0.250  0.375  0.625
  Jonah Heim              Atlanta Braves             6     18      2   0.111  0.273  0.167  0.439
  Rowdy Tellez            Atlanta Braves             6     10      2   0.200  0.200  0.500  0.700
  Austin Wynns            Atlanta Braves             5     17      2   0.118  0.118  0.118  0.235
  Max Muncy               Athletics                  4     13      2   0.154  0.214  0.308  0.522
  José Azócar             Atlanta Braves             4      6      2   0.333  0.333  0.333  0.667
  Carter Jensen           Kansas City Royals         3      8      1   0.125  0.222  0.500  0.722
  Salvador Perez          Kansas City Royals         3     12      2   0.167  0.167  0.417  0.583
  Vinnie Pasquantino      Kansas City Royals         3     11      2   0.182  0.182  0.182  0.364
  Maikel Garcia           Kansas City Royals         3     10      2   0.200  0.385  0.200  0.585
  Lane Thomas             Kansas City Royals         3      8      1   0.125  0.222  0.125  0.347
  Jac Caglianone          Kansas City Royals         3      7      2   0.286  0.375  0.429  0.804

  Sort by:
    [1] Name
    [2] Team
    [3] Appearances
    [4] AB
    [5] AVG
    [6] OBP
    [7] SLG
    [8] OPS
    [h] Show top N (head)
    [t] Show bottom N (tail)
    [c] Export to CSV
    [q] Back

```

## limitations

It is a bit dumb now... it just drops all of your *watched games* into a json file. This could become very large if you are a true sports fan and could cause long start up times.

It relies on the: 

MLB-StatsAPI: https://github.com/toddrob99/MLB-StatsAPI

Therefore, if that goes down, so does this. 

Adding games watched is a real pain right now... you just go one by one and add them. Would be better if you could import from a site like rategame.io. Or could add an option to add all games from a season/month and then the user could remove from there. Not sure the best way of doing this. 

Loading stats for players is low, we have to load boxscores from each game individually

The API counts games as 0-0 when they are canceled. It would just be better to filter these out when adding games

## todo

add a comparison from user watched games to career/season averages

add filter for batters (minimum PA)

the team filter... filters the game by the team. Meaning that it includes stats from all players that played in a game with a specific team. I instead just want stats from players that are on that team.

it's only regular season games (no need for preseason but definitely want postseason
