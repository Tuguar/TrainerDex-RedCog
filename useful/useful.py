import random
import humanize
from datetime import datetime
from dateutil.rrule import rrule, WEEKLY, TH
from discord.ext import commands

class Useful:
	"""Easter Eggs and Useful tools for a pokemon server"""
	
	def __init__(self, bot):
		self.bot = bot
	
	@commands.command(pass_context=True)
	async def excuse(self, ctx):
		excuses = [
			'{} is finding socks.', 
			'{} is only '+str(random.randint(61,300))+' minutes away.', 
			'{} has pizzzaaaaaaa 🍕🍍', 
			'{} accidentally got on a plane. ✈️', 
		]
		await self.bot.delete_message(ctx.message)
		await self.bot.send_typing(ctx.message.channel)
		await self.bot.say(random.choice(excuses).format(ctx.message.author.display_name))
	
	@commands.command()
	async def migration(self):
		migrations = rrule(WEEKLY, dtstart=datetime(2017,2,23,0,0), interval=2, byweekday=(TH,))
		await self.bot.say("The next migration is in {}".format(humanize.naturaltime([x for x in migrations if x >= datetime.now()][0])))

def setup(bot):
	bot.add_cog(Useful(bot))
