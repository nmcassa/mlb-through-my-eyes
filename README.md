# mlb-through-my-eyes

Hello, 

Inspired partial by the rategame.io app, I love the idea of being able to log my games and look back on them. One thing that I have been wondering is: *if i only watch some of the games, how does my perspective of a player differ from their true performance*

If I have a low sample size of Ian Happ games watched, but in those few games he played amazing... I might just think he is the best player ever. If I watch two Bryce Elder starts and he blows both of them wide open I think he is the worst starter ever. 

So the goal here is to make a little CLI app that can track the games I have logged and eventually give me fun stats about my small sample size of games and how they relate to a players career or season. 

Hopefully I can have a summary of players that I have seen play much better than their average, and some players that I have seen play much worse. 

## limitations

It is a bit dumb now... it just drops all of your *watched games* into a json file. This could become very large if you are a true sports fan and could cause long start up times.

It relies on the: 

MLB-StatsAPI: https://github.com/toddrob99/MLB-StatsAPI

Therefore, if that goes down, so does this. 

Adding games watched is a real pain right now... you just go one by one and add them. Would be better if you could import from a site like rategame.io. Or could add an option to add all games from a season/month and then the user could remove from there. Not sure the best way of doing this. 

Loading stats for players is low, we have to load boxscores from each game individually

## todo

add sorting by column in the player summaries
