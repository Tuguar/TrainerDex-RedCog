import random
import humanize
from datetime import datetime
from datetime.util import rrule, WEEKLY, TH
from discord.ext import commands

class EasterEggs:
	"""Easter Eggs"""
	
	def __init__(self, bot):
		self.bot = bot
	
	@commands.command(pass_context=True)
	async def excuse(self, ctx):
		excuses = [
			'{} is finding socks.', 
			'{} is only '+str(random.randint(1,120))+' minutes away.', 
			'{}’s cat got stuck in the toilet.', 
			'Pizzzaaaaaaa 🍕🍍', 
			'{} just put a casserole in the oven.', 
			'{} accidentally got on a plane. ✈️', 
		]
		await self.bot.send_typing(ctx.message.channel)
		await self.bot.say(random.choice(excuses).format(ctx.message.author.display_name))
	
	@command.command()
	async def migration(self):
		migrations = rrule(WEEKLY, dtstart=datetime(2017,2,23,0,0), interval=2, byweekday=(TH,))
		await self.bot.say("The next migration is in {}".format(humanize.naturaltime([x for x in fortnight if x >= datetime.now()][0])))

def setup(bot):
	bot.add_cog(EasterEggs(bot))
