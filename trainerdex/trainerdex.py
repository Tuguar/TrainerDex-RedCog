﻿# coding=utf-8
import os
import asyncio
import datetime
import humanize
import maya
import pytz
import discord
import random
import requests
import pycent
import trainerdex
from collections import namedtuple
from discord.ext import commands
from .utils import checks
from .utils.dataIO import dataIO
from pendulum.parsing.exceptions import ParserError


settings_file = 'data/trainerdex/settings.json'
json_data = dataIO.load_json(settings_file)
token = json_data['token']

Difference = namedtuple('Difference', [
	'old_date',
	'old_xp',
	'new_date',
	'new_xp',
	'change_time',
	'change_xp',
])

levelup = ["You reached your goal, well done. Now if only applied that much effort at buying {member} pizza, I might be happy!", "Well done on reaching {goal:,}", "much xp, very goal", "Great, you got to {goal:,} XP, now what?"]

class StartDateUpdate:
	
	def __init__(self, trainer):
		self.raw = None
		self.id = 0-trainer.id
		self.time_updated = trainer.start_date
		self.xp = 0
	
	@classmethod
	def level(cls):
		return 1
	
	@classmethod
	def trainer(cls):
		return trainer

class TrainerDex:
	
	def __init__(self, bot):
		self.bot = bot
		self.client = trainerdex.Client(token)
		self.teams = self.client.get_teams()
		
	async def get_trainer(self, username=None, discord=None, account=None, prefered=True, respect_privacy=True):
		"""Returns a Trainer object for a given discord, trainer username or account id
		
		Search is done in the order of username > discord > account, if you specify more than one, it will ONLY search the first one.
		"""
		
		if username:
			try:
				return self.client.get_trainer_from_username(username, respect_privacy=respect_privacy)
			except LookupError:
				raise
		elif discord and prefered==True:
			return self.client.get_discord_user(discord).owner().trainer(all_=False)
		elif discord and prefered==False:
			return self.client.get_discord_user(discord).owner().trainer(all_=True)
		elif account and prefered==True:
			return self.client.get_user(account).trainer(all_=False)
		elif account and prefered==False:
			return self.client.get_user(account).trainer(all_=True)
		
	async def getTeamByName(self, team: str):
		for item in self.teams:
			if item.name.title()==team.title():
				return item
	
	async def getDiff(self, trainer, days: int):
		updates = trainer.updates()
		if trainer.start_date!=datetime.date(2016,7,13): 
			updates.append(StartDateUpdate(trainer))
		updates.sort(key=lambda x: x.time_updated)
		latest = trainer.update
		first = updates[1]
		reference = [x for x in updates if x.time_updated <= (datetime.datetime.now(pytz.utc)-datetime.timedelta(days=days)+datetime.timedelta(hours=6))]
		reference.sort(key=lambda x: x.time_updated, reverse=True)
		if reference==[]:
			if latest==first:
				diff = Difference(
					old_date = None,
					old_xp = None,
					new_date = latest.time_updated,
					new_xp = latest.xp,
					change_time = None,
					change_xp = None
				)
				return diff
			elif first.time_updated > (latest.time_updated-datetime.timedelta(days=days)+datetime.timedelta(hours=3)):
				reference=first
		else:
			reference = reference[0]
		diff = Difference(
				old_date = reference.time_updated,
				old_xp = reference.xp,
				new_date = latest.time_updated,
				new_xp = latest.xp,
				change_time = latest.time_updated-reference.time_updated,
				change_xp = latest.xp-reference.xp
			)
		
		return diff
	
	async def updateCard(self, trainer):
		dailyDiff = await self.getDiff(trainer, 1)
		level=trainer.level
		embed=discord.Embed(timestamp=dailyDiff.new_date, colour=int(trainer.team().colour.replace("#", ""), 16))
		try:
			embed.set_author(name=trainer.username, icon_url=trainer.account().discord().avatar_url)
		except:
			embed.set_author(name=trainer.username)
		embed.add_field(name='Level', value=level.level)
		if level.level != 40:
			embed.add_field(name='XP', value='{:,} / {:,}'.format(trainer.update.xp-level.total_xp,level.xp_required))
		else:
			embed.add_field(name='Total XP', value='{}'.format(humanize.intword(level.total_xp)))
		if dailyDiff.change_xp and dailyDiff.change_time:
			gain = '{:,} since {}. '.format(dailyDiff.change_xp, humanize.naturalday(dailyDiff.old_date))
			if dailyDiff.change_time.days>1:
				gain += "That's {:,} xp/day.".format(round(dailyDiff.change_xp/dailyDiff.change_time.days))
			embed.add_field(name='Gain', value=gain)
			if trainer.goal_daily and dailyDiff.change_time.days>0:
				dailyGoal = trainer.goal_daily
				embed.add_field(name='Daily completion', value='{}% towards {:,}'.format(pycent.percentage(dailyDiff.change_xp/max(1,dailyDiff.change_time.days), dailyGoal), dailyGoal))
		if trainer.goal_total and trainer.goal_total!=0:
			totalGoal = trainer.goal_total
		elif level.level < 40:
			totalGoal = trainerdex.Level.from_level(level.level+1).total_xp
		else:
			totalGoal = None
		if totalGoal:
			totalDiff = await self.getDiff(trainer, 7)
			embed.add_field(name='Goal remaining', value='{:,} out of {}'.format(totalGoal-totalDiff.new_xp, humanize.intword(totalGoal)))
			if totalDiff.change_time.seconds>=1:
				eta = lambda x, y, z: round(x/(y/z))
				eta = eta(totalGoal-totalDiff.new_xp, totalDiff.change_xp, totalDiff.change_time.total_seconds())
				eta = totalDiff.new_date+datetime.timedelta(seconds=eta)
				embed.add_field(name='Goal ETA', value=humanize.naturaltime(eta.replace(tzinfo=None)))
			if totalDiff.change_time.total_seconds()<583200:
				embed.description = "ETA may be inaccurate. Using {} of data.".format(humanize.naturaldelta(totalDiff.change_time))
		embed.set_footer(text="Total XP: {:,}".format(dailyDiff.new_xp))
		
		return embed
	
	async def profileCard(self, name: str, force=False):
		try:
			trainer = await self.get_trainer(username=name, respect_privacy=False)
		except LookupError:
			raise
		account = trainer.owner()
		discordUser = account.discord()
		level=trainer.level
		
		embed=discord.Embed(timestamp=trainer.update.time_updated, colour=int(trainer.team().colour.replace("#", ""), 16))
		try:
			embed.set_author(name=trainer.username, icon_url=discordUser.avatar_url)
		except:
			embed.set_author(name=trainer.username)
		if account and (account.first_name or account.last_name) and (trainer.statistics is True or force is True) and trainer.cheater is False:
			embed.add_field(name='Name', value=account.first_name+' '+account.last_name)
		embed.add_field(name='Team', value=trainer.team().name)
		embed.add_field(name='Level', value=level.level)
		if trainer.statistics is True or force is True:
			if level.level != 40:
				embed.add_field(name='XP', value='{:,} / {:,}'.format(trainer.update.xp-level.total_xp,level.xp_required))
			else:
				embed.add_field(name='Total XP', value='{}'.format(humanize.intword(level.total_xp)))
			if discordUser:
				embed.add_field(name='Discord', value='<@{}>'.format(discordUser.id))
		if trainer.cheater is True or trainer.statistics is False:
			desc = '{0} '
			desc_also = False
			if trainer.statistics is False:
				desc += "has chosen to opt out of statistics, and the trainer profile system"
				if force is True:
					desc += ", however, you can see this information anyway. This is most likely because you are {1}."
				desc_also = True
			if trainer.cheater is True:
				if desc_also is True:
					desc += "Additionally, {0} "
					desc_also = False
				desc += "has been known to cheat."
				desc_also = True
			embed.description = desc.format(trainer.username)
		embed.set_footer(text="Total XP: {:,}".format(trainer.update.xp))
		return embed
	
	async def _addProfile(self, message, mention, username: str, xp: int, team, has_cheated=False, currently_cheats=False, name: str=None, prefered=True):
		#Check existance
		try:
			print('Attempting to add {} to database, checking if they already exist'.format(username))
			await self.get_trainer(username=username, prefered=prefered)
		except LookupError:
			pass
		else:
			print('Found {}, aborting...'.format(username))
			await self.bot.edit_message(message, "A record already exists in the database for this trainer. Aborted.")
			return
		#Create or get auth.User and discord user
		discordUser=None
		if mention.avatar_url=='' or mention.avatar_url is None:
			avatarUrl = mention.default_avatar_url
		else:
			avatarUrl = mention.avatar_url
		try:
			print('Checking if existing Discord User {} exists in our database...'.format(mention.id))
			discordUser=self.client.get_discord_user(mention.id)
		except requests.exceptions.HTTPError as e:
			print(e)
			user = self.client.create_user(username='_'+username, first_name=name)
			discordUser = self.client.import_discord_user(name=mention.name, discriminator=mention.discriminator, id_=mention.id, avatar_url=avatarUrl, creation=mention.created_at, user=user.id)
		else:
			print('Found... Using that.')
			user = discordUser.owner()
		finally:
			#create or update trainer
			print('Creating trainer...')
			trainer = self.client.create_trainer(username=username, team=team.id, has_cheated=has_cheated, currently_cheats=currently_cheats, prefered=prefered, account=user.id)
			print('Trainer created. Creating update object...')
			#create update object
			update = self.client.create_update(trainer.id, xp)
			print('Update object created')
			return trainer
	
	#Public Commands
	
	@commands.command(pass_context=True, name="trainer")
	async def trainer(self, ctx, trainer: str): 
		"""Look up a Pokemon Go Trainer
		
		Example: trainer JayTurnr
		"""
		
		message = await self.bot.say('Searching...')
		await self.bot.send_typing(ctx.message.channel)
		try:
			embed = await self.profileCard(trainer)
			await self.bot.edit_message(message, new_content='I found this one...', embed=embed)
		except LookupError as e:
			await self.bot.say('`Error: '+str(e)+'`')
	
	@commands.command(pass_context=True)
	async def progress(self, ctx):
		"""Find out information about your own progress"""
		
		trainer = await self.get_trainer(discord=ctx.message.author.id)
		
		message = await self.bot.say('Thinking...')
		await self.bot.send_typing(ctx.message.channel)
		
		embed = await self.updateCard(trainer)
		await self.bot.edit_message(message, new_content='Here we go...', embed=embed)
		
	
	@commands.group(pass_context=True)
	async def update(self, ctx):
		"""Update information about your TrainerDex profile"""
			
		if ctx.invoked_subcommand is None:
			await self.bot.send_cmd_help(ctx)
	
	@update.command(name="xp", pass_context=True)
	async def xp(self, ctx, xp: int): 
		"""Update your xp
		
		Example: update xp 6000000
		"""
		
		message = await self.bot.say('Processing...')
		await self.bot.send_typing(ctx.message.channel)
		trainer = await self.get_trainer(discord=ctx.message.author.id)
		if trainer is not None:
			if int(trainer.update.xp) >= int(xp):
				await self.bot.edit_message(message, "Error: You last set your XP to {xp:,}, please try a higher number. `ValidationError: {usr}, {xp}`".format(usr= trainer.username, xp=trainer.update.xp))
				return
			if trainer.goal_total:
				if trainer.goal_total<=xp and trainer.goal_total != 0:
					await self.bot.say(random.choice(levelup).format(goal=trainer.goal_total, member=random.choice(list(ctx.message.server.members)).mention))
					self.client.update_trainer(trainer, total_goal=0)
			update = self.client.create_update(trainer.id, xp)
			await asyncio.sleep(1)
			trainer = self.client.get_trainer(trainer.id) #Refreshes the trainer
			embed = await self.updateCard(trainer)
			await self.bot.edit_message(message, new_content='Success 👍', embed=embed)
	
	@update.command(name="name", pass_context=True)
	async def name(self, ctx, first_name: str, last_name: str=None): 
		"""Update your name on your profile
		
		Set your name in form of <first_name> <last_name>
		If you want to blank your last name set it to two dots '..'
		
		Example: update xp Bob ..
		Example: update xp Jay Turner
		"""
		
		message = await self.bot.say('Processing...')
		await self.bot.send_typing(ctx.message.channel)
		trainer = await self.get_trainer(discord=ctx.message.author.id)
		account = trainer.account()
		if last_name=='..':
			last_name=' '
		if account:
			self.client.update_user(account, first_name=first_name, last_name=last_name)
			try:
				embed = await self.profileCard(trainer.username)
				await self.bot.edit_message(message, new_content='Success 👍', embed=embed)
			except LookupError as e:
				await self.bot.edit_message(message, new_content='`Error: '+str(e)+'`')
		else:
			await self.bot.edit_message(message, new_content="Not found!")
	
	@update.command(name="start", pass_context=True)
	async def start_date(self, ctx, *, date: str):
		"""Set the day you started Pokemon Go"""
		
		message = await self.bot.say('Thinking...')
		await self.bot.send_typing(ctx.message.channel)
		trainer = await self.get_trainer(discord=ctx.message.author.id)
		try:
			suspected_time = maya.parse(date, day_first=True)
		except ParserError:
			await self.bot.edit_message(message, "I can't figure out what you mean by '{}', can you please be a bit more... inteligible?".format(date))
			return
		await self.bot.edit_message(message, "Just to confirm, you mean {}, right?".format(suspected_time.slang_date()))
		answer = await self.bot.wait_for_message(timeout=30, author=ctx.message.author)
		if answer is None:
			message = await self.bot.say('Timeout. Not setting start date')
			return
		elif 'yes' not in answer.content.lower():
			message = await self.bot.say("It seems you didn't agree that the date was the correct date. Not setting date.")
			return
		else:
			self.client.update_trainer(trainer, start_date=suspected_time.datetime(to_timezone='UTC'))
			message = await self.bot.say("{}, your start date has been set to {}".format(ctx.message.author.mention, suspected_time.slang_date()))
	
	@update.command(name="goal", pass_context=True)
	async def goal(self, ctx, which: str, goal: int):
		"""Update your goals
		
		Example: update goal daily 2000
		"""
		
		message = await self.bot.say('Processing...')
		await self.bot.send_typing(ctx.message.channel)
		trainer = await self.get_trainer(discord=ctx.message.author.id)
		if which.title()=='Daily':
			self.client.update_trainer(trainer, daily_goal=goal)
			await self.bot.edit_message(message, "{}, your daily goal has been set to {:,}".format(ctx.message.author.mention, goal))
		elif which.title()=='Total':
			if goal>trainer.update.xp or goal==0:
				self.client.update_trainer(trainer, total_goal=goal)
				await self.bot.edit_message(message, "{}, your total goal has been set to {:,}".format(ctx.message.author.mention, goal))
			else:
				await self.bot.edit_message(message, "{}, try something higher than your current XP of {:,}.".format(ctx.message.author.mention, trainer.update.xp))
		else:
			await self.bot.edit_message(message, "{}, please choose 'Daily' or 'Total' for after goal.".format(ctx.message.author.mention))
	
	@commands.command(pass_context=True, no_pm=True)
	async def leaderboard(self, ctx):
		"""View the leaderboard for your server"""
		
		message = await self.bot.say("Thinking...")
		await self.bot.send_typing(ctx.message.channel)
		user_list = self.client.get_discord_server(ctx.message.server.id).get_users(ctx.message.server)
		users = []
		for user in user_list:
			if user.trainer().statistics==True:
				users.append(user)
		users.sort(key=lambda x:x.trainer().update.xp, reverse=True)
		embed=discord.Embed(title="Leaderboard")
		if len(ctx.message.mentions) >= 1:
			for _, mbr in zip(range(25), ctx.message.mentions):
				try:
					i = users.index(self.client.get_discord_user(mbr.id).owner())
				except requests.exceptions.HTTPError as e:
					await self.bot.say('Could not be magic with {}: `{}`'.format(mbr.mention, e))
				else:
					trainer = users[i].trainer()
					embed.add_field(name='{}. {} {} {}'.format(i+1, trainer.username, trainer.level.level, trainer.team().name), value="{:,}".format(trainer.update.xp))
		else:
			for i in range(min(25, len(users))):
				trainer = users[i].trainer()
				embed.add_field(name='{}. {} {} {}'.format(i+1, trainer.username, trainer.level.level, trainer.team().name), value="{:,}".format(trainer.update.xp))
		await self.bot.edit_message(message, new_content=str(datetime.date.today()), embed=embed)
	
	#Mod-commands
	
	@commands.command(pass_context=True, enabled=False, no_pm=True)
	@checks.mod_or_permissions(assign_roles=True)
	async def spoofer(self, ctx):
		"""Set a user as a spoofer"""
		pass
	
	@commands.command(name="addprofile", no_pm=True, pass_context=True, alias="newprofile")
	@checks.mod_or_permissions(assign_roles=True)
	async def addprofile(self, ctx, mention, name: str, team: str, level: int, xp: int, opt: str=''): 
		"""Add a user to the Trainer Dex database
		
		Optional arguments:
		spoofer - sets the user as a spoofer
		
		Example: addprofile @JayTurnr#1234 JayTurnr Valor 34 1234567
		"""
		
		message = await self.bot.say('Processing...')
		await self.bot.send_typing(ctx.message.channel)
		mbr = ctx.message.mentions[0]
		xp = trainerdex.Level.from_level(level).total_xp + xp
		team = await self.getTeamByName(team)
		if team is None:
			await self.bot.edit_message(message, "That isn't a valid team. Please ensure that you have used the command correctly.")
			return
		if opt.title() == 'Spoofer':
			await self._addProfile(message, mbr, name, xp, team, has_cheated=True, currently_cheats=True)
		else:
			await self._addProfile(message, mbr, name, xp, team)
		try:
			embed = await self.profileCard(name)
			await self.bot.edit_message(message, new_content='Success 👍', embed=embed)
		except LookupError as e:
			await self.bot.edit_message(message, '`Error: '+str(e)+'`')
	
	@commands.command(pass_context=True, no_pm=True)
	@checks.mod_or_permissions(assign_roles=True)
	async def addsecondary(self, ctx, mention, name: str, team: str, level: int, xp: int, opt: str=''):
		"""Add a user to the Trainer Dex database as a secondary profile
		
		Optional arguments:
		spoofer - sets the user as a spoofer
		
		Example: addsecondary @JayTurnr#1234 JayTurnr Valor 34 1234567 spoofer
		"""
		
		message = await self.bot.say('Processing...')
		await self.bot.send_typing(ctx.message.channel)
		mbr = ctx.message.mentions[0]
		xp = trainerdex.Level.from_level(level).total_xp + xp
		team = await self.getTeamByName(team)
		if team is None:
			await self.bot.edit_message(message, "That isn't a valid team. Please ensure that you have used the command correctly.")
			return
		if opt.title() == 'Spoofer':
			await self._addProfile(message, mbr, name, xp, team, has_cheated=True, currently_cheats=True, prefered=False)
		else:
			await self._addProfile(message, mbr, name, xp, team, prefered=False)
		try:
			embed = await self.profileCard(name)
			await self.bot.edit_message(message, new_content='Success 👍', embed=embed)
		except LookupError as e:
			await self.bot.edit_message(message, '`Error: '+str(e)+'`')
	
	@commands.command(pass_context=True, no_pm=True)
	@checks.mod_or_permissions(assign_roles=True)
	async def approve(self, ctx, mention, name: str, team: str, level: int, xp: int, opt: str=''): 
		"""Add a user to the Trainer Dex database and set the correct role on Discord
		
		Roles and renaming based on the ekpogo.uk discord - options coming soon.
		
		Optional arguments:
		spoofer - sets the user as a spoofer (db only)
		minor/child - sets the 'Minor' role instead of the 'Trainer' role (discord only)
		
		Example: approve @JayTurnr#1234 JayTurnr Valor 34 1234567 minor
		"""
		
		message = await self.bot.say('Processing step 1 of 2...')
		await self.bot.send_typing(ctx.message.channel)
		xp = trainerdex.Level.from_level(level).total_xp + xp
		team = await self.getTeamByName(team)
		if team is None:
			await self.bot.edit_message(message, "That isn't a valid team. Please ensure that you have used the command correctly.")
			return
		mbr = ctx.message.mentions[0]
		try:
			await self.bot.change_nickname(mbr, name)
		except discord.errors.Forbidden:
			await self.bot.edit_message(message, "Error: I don't have permission to change nicknames. Aborted!")
		else:
			if (opt.title() in ['Minor', 'Child']) and discord.utils.get(ctx.message.server.roles, name='Minor'):
				approved_mentionable = discord.utils.get(ctx.message.server.roles, name='Minor')
			else:
				approved_mentionable = discord.utils.get(ctx.message.server.roles, name='Trainer')
			team_mentionable = discord.utils.get(ctx.message.server.roles, name=team.name)
			try:
				await self.bot.add_roles(mbr, approved_mentionable)
				if team_mentionable is not None:
					await asyncio.sleep(2.5) #Waits for 2.5 seconds to pass to get around Discord rate limiting
					await self.bot.add_roles(mbr, team_mentionable)
			except discord.errors.Forbidden:
				await self.bot.edit_message(message, "Error: I don't have permission to set roles. Aborted!")
			else:
				await self.bot.edit_message(message, "{} has been approved! 👍".format(name))
				message = await self.bot.say('Processing step 2 of 2...')
				await self.bot.send_typing(ctx.message.channel)
				if opt.title() == 'Spoofer':
					await self._addProfile(message, mbr, name, xp, team, has_cheated=True, currently_cheats=True)
				else:
					await self._addProfile(message, mbr, name, xp, team)
				try:
					embed = await self.profileCard(name)
					await self.bot.edit_message(message, new_content='Success 👍', embed=embed)
				except LookupError as e:
					await self.bot.edit_message(message, '`Error: '+str(e)+'`')
	
	@commands.group(pass_context=True)
	@checks.is_owner()
	async def tdset(self, ctx):
		"""Settings for TrainerDex cog"""
		
		if ctx.invoked_subcommand is None:
			await self.bot.send_cmd_help(ctx)
	
	@tdset.command(pass_context=True)
	@checks.is_owner()
	async def api(self, ctx, token: str):
		"""Sets the TrainerDex API token - owner only"""
		
		message = await self.bot.say('Processing...')
		await self.bot.send_typing(ctx.message.channel)
		settings = dataIO.load_json(settings_file)
		if token:
			settings['token'] = token
			dataIO.save_json(settings_file, settings)
			await self.bot.edit_message(message, '```API token set - please restart cog```')
	
	@tdset.command(pass_context=True, no_pm=True)
	@checks.is_owner()
	async def register_server(self, ctx, cheaters, minors):
		"""Register Server to database, required before leaderboards can work
		
		arguments:
		cheaters - allowed, ban, segregate
		minors - allowed, ban, segregate
		"""
		
		message = await self.bot.say('Processing...')
		await self.bot.send_typing(ctx.message.channel)
		if cheaters == 'allowed':
			c1=False
			c2=False
		elif cheaters == 'ban':
			c1=True
			c2=False
		elif cheaters in ('segregate','seg'):
			c1=False
			c2=True
		if minors == 'allowed':
			m1=False
			m2=False
		elif minors == 'ban':
			m1=True
			m2=False
		elif minors in ('segregate','seg'):
			m1=False
			m2=True
		print('{}{}{}{}'.format(c1,c2,m1,m2))
		svr = ctx.message.server
		server = self.client.import_discord_server(svr.name, str(svr.region), svr.id, owner=svr.owner.id, bans_cheaters=c1, seg_cheaters=c2, bans_minors=m1, seg_minors=m2)
		await self.bot.edit_message(message, 'Server #{s.id} {s.name} succesfully added.'.format(server))

def check_folders():
	if not os.path.exists("data/trainerdex"):
		print("Creating data/trainerdex folder...")
		os.makedirs("data/trainerdex")

def check_file():
	f = 'data/trainerdex/settings.json'
	data = {}
	data['token'] = ''
	if not dataIO.is_valid_json(f):
		print("Creating default token.json...")
		dataIO.save_json(f, data)

def setup(bot):
	check_folders()
	check_file()
	bot.add_cog(TrainerDex(bot))
