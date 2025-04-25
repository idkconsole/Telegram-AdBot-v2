import os
import sys
import toml
import asyncio
import time
from telethon.sessions import StringSession
from telethon.tl.functions.channels import JoinChannelRequest, LeaveChannelRequest
from telethon import TelegramClient, errors
from telethon.sessions import StringSession
from urllib.parse import urlparse
from ui import Console
import ctypes
import requests
from telethon import functions
import random

console = Console()
messages_sent = 0
messages_forwarded = 0
cycles_completed = 0
start_time = time.time()

def load_config():
    with open("config.toml", "r") as config_file:
        return toml.load(config_file)   
    
def load_groups(file_name):
    with open(file_name, "r") as groups_file:
        return [group.strip() for group in groups_file.readlines()]
    
def load_all_groups():
    forward_groups = load_groups("forward.txt")
    send_groups = load_groups("send.txt")
    return forward_groups, send_groups

def save_session(session_string):
    os.makedirs("sessions", exist_ok=True)
    with open("sessions/session.dat", "w") as session_file:
        session_file.write(session_string)

def load_session():
    try:
        with open("sessions/session.dat", "r") as session_file:
            return session_file.read().strip()
    except FileNotFoundError:
        return ""

def title():
    elapsed_time = int(time.time() - start_time)
    title = f"Telegram Adbot | Messages Sent: {messages_sent} | Messages Forwarded: {messages_forwarded} | Cycles Completed: {cycles_completed} | Time Elapsed: {elapsed_time}s"
    if os.name == 'nt':
        ctypes.windll.kernel32.SetConsoleTitleW(title)
    else:
        sys.stdout.write(f"\33]0;{title}\a")
        sys.stdout.flush()

async def update_terminal_title():
    while True:
        title()
        await asyncio.sleep(1)

def webhook_logs(embed):
    if not bot.config['logging']['discord_logging']:
        return
    webhook_url = bot.config['logging']['webhook_url']
    if not webhook_url:
        console.error("Webhook URL is not set in the configuration file.")
        exit(1)
    headers = {
        "Content-Type": "application/json"
    }
    payload = {
        "embeds": [embed]
    }
    response = requests.post(webhook_url, json=payload, headers=headers)
    if response.status_code != 204:
        pass

def create_embed(title, description, color, fields=None):
    embed = {
        "title": title,
        "description": description,
        "color": color,
        "fields": [],
        "footer": {
            "text": f"Timestamp: {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime())}"
        }
    }
    if fields:
        for name, value, inline in fields:
            embed['fields'].append({
                "name": name,
                "value": value,
                "inline": inline
            })
    return embed

def print_settings(config):
    console.info("Configuration Settings:")
    console.info(f"API ID: {config['telegram']['api_id']}")
    console.info(f"API Hash: {config['telegram']['api_hash']}")
    console.info(f"Phone Numbers: {', '.join(config['telegram']['phone_numbers'])}")
    console.info(f"Password: {'Set' if config['telegram']['password'] else 'Not Set'}")
    console.info(f"Joiner: {config['settings']['joiner']}")
    console.info(f"Forward Message Url: {config['settings']['forward_msg_url']}")
    console.info(f"Send Message Url: {config['settings']['send_msg_url']}")
    console.info(f"Delay: {config['settings']['delay']}")
    console.info(f"Cycle Delay: {config['settings']['cycle_delay']}")
    console.info(f"Skip Messages: {config['settings']['skip_msg']}")
    console.info(f"Discord Logging: {config['logging']['discord_logging']}")
    console.info(f"Webhook URL: {'Set' if config['logging']['webhook_url'] else 'Not Set'}\n\n")

def send_settings_to_discord(config):
    fields = [
        ("API ID", config['telegram']['api_id'], True),
        ("API Hash", config['telegram']['api_hash'], True),
        ("Phone Numbers", ', '.join(config['telegram']['phone_numbers']), False),
        ("Password", "Set" if config['telegram']['password'] else "Not Set", True),
        ("Joiner", str(config['settings']['joiner']), True),
        ("Forward Message Url", config['settings']['forward_msg_url'], False),
        ("Send Message Url", config['settings']['send_msg_url'], False),
        ("Delay", str(config['settings']['delay']), True),
        ("Cycle Delay", str(config['settings']['cycle_delay']), True),
        ("Skip Messages", str(config['settings']['skip_msg']), True),
        ("Discord Logging", str(config['logging']['discord_logging']), True),
        ("Webhook URL", "Set" if config['logging']['webhook_url'] else "Not Set", True)
    ]
    embed = create_embed(
        title="Configuration Settings",
        description="The following are the current configuration settings of the bot.",
        color=0x3498db,
        fields=fields
    )
    webhook_logs(embed)

class TelegramAdBot:
    def __init__(self):
        self.config = load_config()
        session_string = load_session()
        self.client = TelegramClient(StringSession(session_string), self.config['telegram']['api_id'], self.config['telegram']['api_hash'])
        self.session_exists = bool(session_string)
        self.total_fails = 0
        self.start_time = time.time()
        self.skipped_groups = 0
        self.rate_limited_count = 0
        self.media_restricted_count = 0
        self.restricted_groups = []
        self.banned_groups = []
        self.private_groups = []
        self.groups_left = 0

    def load_current_groups(self):
        return load_all_groups()

    def format_time_elapsed(self):
        elapsed = int(time.time() - self.start_time)
        hours = elapsed // 3600
        minutes = (elapsed % 3600) // 60
        seconds = elapsed % 60
        return f"{hours}h {minutes}m {seconds}s"

    async def handle_restricted_group(self, group_name, reason):
        if group_name not in self.restricted_groups:
            self.restricted_groups.append(group_name)
            try:
                if "banned from it" in str(reason).lower():
                    self.banned_groups.append(group_name)
                elif "private" in str(reason).lower():
                    self.private_groups.append(group_name)
                try:
                    await self.client(LeaveChannelRequest(group_name))
                    self.groups_left += 1
                    console.warning(f"Left restricted group: {group_name}")
                except Exception as e:
                    console.error(f"Failed to leave group {group_name}: {str(e)}")
                updated_groups = []
                with open("groups.txt", "r") as f:
                    groups = f.readlines()
                    for group in groups:
                        if group_name not in group.strip():
                            updated_groups.append(group)
                with open("groups.txt", "w") as f:
                    f.writelines(updated_groups)
                embed = create_embed(
                    title="Restricted Group Removed",
                    description=f"Group {group_name} has been removed from groups.txt",
                    color=0xff0000,
                    fields=[
                        ("Group Name", group_name, True),
                        ("Reason", str(reason), True),
                        ("Action", "Removed and Left", True)
                    ]
                )
                webhook_logs(embed)
            except Exception as e:
                console.error(f"Failed to handle restricted group {group_name}: {str(e)}")

    async def send_completion_stats(self):
        global messages_sent, messages_forwarded, cycles_completed
        current_groups = self.load_current_groups()
        elapsed_time = time.time() - self.start_time
        elapsed_hours, rem = divmod(elapsed_time, 3600)
        elapsed_minutes, elapsed_seconds = divmod(rem, 60)
        start_time_str = time.strftime('%H:%M:%S  %d-%m-%Y', time.localtime(self.start_time))
        next_cycle_time = time.strftime('%H:%M:%S  %d-%m-%Y', time.localtime(time.time() + self.config['settings']['cycle_delay']))
        fields = [
            ("Total Messages Sent", str(messages_sent), True),
            ("Total Messages Forwarded", str(messages_forwarded), True),
            ("Total Groups", str(len(current_groups)), True),
            ("Failed Attempts", str(self.total_fails), True),
            ("Total Cycles Completed", str(cycles_completed), True),
            ("Time Elapsed", f"{int(elapsed_hours)} hours, {int(elapsed_minutes)} minutes, {int(elapsed_seconds)} seconds", False),
            ("Start Time", start_time_str, True),
            ("Next Cycle In", f"{self.config['settings']['cycle_delay']}s ({next_cycle_time})", True)
        ]
        embed = create_embed(
            title="🎯 Cycle Completion Report",
            description="Summary of the completed advertising cycle",
            color=0x00ff00,
            fields=fields
        )
        webhook_logs(embed)
        self.skipped_groups = 0
        self.rate_limited_count = 0
        self.media_restricted_count = 0

    async def start(self):
        await self.check_config_settings()
        await self.validate_settings()
        await self.connect()
        await self.join_groups()

    async def check_config_settings(self):
        if self.config['show_settings']['print_settings']:
            print_settings(self.config)
        if self.config['show_settings']['webhook_settings']:
            send_settings_to_discord(self.config)
        if not self.config['telegram']['api_id']:
            console.error("API ID is not set.")
            embed = create_embed("Configuration Error", "API ID is missing in the configuration file.", 0xff0000)
            webhook_logs(embed)
            exit(1)
        if not self.config['telegram']['api_hash']:
            console.error("API Hash is not set.")
            embed = create_embed("Configuration Error", "API Hash is missing in the configuration file.", 0xff0000)
            webhook_logs(embed)
            exit(1)
        if not self.config['telegram']['phone_numbers']:
            console.error("Phone Number is not set.")
            embed = create_embed("Configuration Error", "Phone number is missing in the configuration file.", 0xff0000)
            webhook_logs(embed)
            exit(1)

    async def validate_settings(self):
        pass

    async def connect(self):
        try:
            await self.client.connect()
            if not self.session_exists and not await self.client.is_user_authorized():
                await self.authenticate()
        except errors.AuthKeyDuplicatedError:
            console.error("Session is invalid or used elsewhere. Reconnecting...")
            embed = create_embed(
                title="Session Invalid",
                description="Session is invalid or used elsewhere. Reconnecting...",
                color=0xff0000
            )
            webhook_logs(embed)
            self.client = TelegramClient(StringSession(), self.config['telegram']['api_id'], self.config['telegram']['api_hash'])
            await self.client.connect()
            await self.authenticate()
        phone_number = self.config['telegram']['phone_numbers'][0]
        masked_number = '*' * (len(phone_number) - 4) + phone_number[-4:]
        console.info(f"Connecting to Telegram ({masked_number})")
        embed = create_embed(
            title="Connecting to Telegram",
            description=f"Connecting to Telegram ({masked_number})",
            color=0xffff00,
            fields=[("Phone Number", masked_number, False)]
        )
        self.user = await self.client.get_me()
        console.info(f"Successfully signed into account {self.user.username if self.user else 'N/A'}")
        embed = create_embed(
            title="Connected to Telegram",
            description=f"Successfully signed into account {self.user.username if self.user else 'N/A'}",
            color=0x00ff00,
            fields=[("Phone Number", masked_number, False)]
        )
        webhook_logs(embed)

    async def authenticate(self):
        phone_number = self.config['telegram']['phone_numbers'][0]
        masked_number = '*' * (len(phone_number) - 4) + phone_number[-4:]
        try:
            await self.client.send_code_request(phone_number)
            console.info(f"Sent verification code to {masked_number}")
            embed = create_embed(
                title="Sent Verification Code",
                description=f"Sent verification code to {masked_number}",
                color=0xffff00,
                fields=[("Phone Number", masked_number, False)]
            )
            verification_code = input(f"{console.colors['lightblack']}{console.timestamp()} » {console.colors['lightblue']}INFO    {console.colors['lightblack']}• {console.colors['white']}Enter the verification code: {console.colors['reset']}")
            await self.client.sign_in(phone_number, verification_code)
            embed = create_embed(
                title="Verification Code Entered",
                description="Verification code entered. Signing in...",
                color=0xffff00,
                fields=[("Phone Number", masked_number, False)]
            )
            webhook_logs(embed)
            save_session(self.client.session.save())
        except errors.PhoneNumberBannedError:
            console.error("Your phone number has been banned from Telegram")
            embed = create_embed(
                title="Phone Number Banned",
                description="Your phone number has been banned from Telegram",
                color=0xff0000,
                fields=[("Phone Number", masked_number, False)]
            )
            webhook_logs(embed)
            exit(1)
        except errors.SessionPasswordNeededError:
            password = self.config['telegram']['password']
            await self.client.sign_in(password=password)
            console.info("Two-step verification is enabled. Password entered.")
            embed = create_embed(
                title="Two-Step Verification",
                description="Two-step verification is enabled. Password entered.",
                color=0xffff00,
                fields=[("Phone Number", masked_number, False)]
            )
            webhook_logs(embed)
            save_session(self.client.session.save())

    async def get_last_message_in_group(self, group):
        try:
            messages = await self.client.get_messages(group, limit=3)
            if not messages:
                return None
            for msg in messages:
                if msg.action:
                    continue
                return msg
            return None
        except Exception as e:
            console.error(f"Error checking last message: {str(e)}")
            return None
        
    async def join_groups(self):
        if not self.client.is_connected():
            await self.client.connect()
        if self.config['settings']['joiner']:
            groups = load_groups("groups.txt")
            total_groups = len(groups)
            console.info(f"Joining {total_groups} groups")
            embed = create_embed(
                title="Joining Groups",
                description=f"Joining {total_groups} groups",
                color=0xffff00,
                fields=[("Total Groups", str(total_groups), True)]
            )
            webhook_logs(embed)
            for group in groups:
                try:
                    await self.client(JoinChannelRequest(group))
                    console.success(f"Joined group: {group}")
                    embed = create_embed(
                        title="Group Joined",
                        description=f"Joined group: {group}",
                        color=0x00ff00,
                        fields=[("Group Name", group, True)]
                    )
                    webhook_logs(embed)
                except errors.ChannelInvalidError:
                    console.error(f"Invalid group: {group}")
                    embed = create_embed(
                        title="Invalid Group",
                        description=f"Invalid group: {group}",
                        color=0xff0000,
                        fields=[("Group Name", group, True)]
                    )
                    webhook_logs(embed)
                except errors.ChannelPrivateError:
                    console.error(f"Group is private: {group}")
                    embed = create_embed(
                        title="Group is Private",
                        description=f"Group is private: {group}",
                        color=0xff0000,
                        fields=[("Group Name", group, True)]
                    )
                    webhook_logs(embed)
                except errors.ChannelPublicGroupNaError:
                    console.error(f"Group is not accessible: {group}")
                    embed = create_embed(
                        title="Group Not Accessible",
                        description=f"Group is not accessible: {group}",
                        color=0xff0000,
                        fields=[("Group Name", group, True)]
                    )
                    webhook_logs(embed)
                except errors.ChannelSuspendedError:
                    console.error(f"Group is suspended: {group}")
                    embed = create_embed(
                        title="Group Suspended",
                        description=f"Group is suspended: {group}",
                        color=0xff0000,
                        fields=[("Group Name", group, True)]
                    )
                    webhook_logs(embed)
                except errors.ChatAdminRequiredError:
                    console.error(f"Admin rights required to join group: {group}")
                    embed = create_embed(
                        title="Admin Rights Required",
                        description=f"Admin rights required to join group: {group}",
                        color=0xff0000,
                        fields=[("Group Name", group, True)]
                    )
                    webhook_logs(embed)
                except errors.ChatWriteForbiddenError:
                    console.error(f"Cannot write in group: {group}")
                    embed = create_embed(
                        title="Cannot Write in Group",
                        description=f"Cannot write in group: {group}",
                        color=0xff0000,
                        fields=[("Group Name", group, True)]
                    )
                    webhook_logs(embed)
                except errors.FloodWaitError as e:
                    console.warning(f"Flood wait error. Must wait {e.seconds} seconds")
                    embed = create_embed(
                        title="Flood Wait Error",
                        description=f"Flood wait error. Must wait {e.seconds} seconds",
                        color=0xffff00,
                        fields=[("Group Name", group, True), ("Wait Time", f"{e.seconds}s", True)]
                    )
                    webhook_logs(embed)
                    continue
                except Exception as e:
                    console.error(f"Failed to join group: {group} - {str(e)}")
                    embed = create_embed(
                        title="Failed to Join Group",
                        description=f"Failed to join group: {group}",
                        color=0xff0000,
                        fields=[("Group Name", group, True), ("Error", str(e), False)]
                    )
                    webhook_logs(embed)
            console.info("Completed joining groups.")
        
    async def send_custom_message(self):
        global messages_sent
        if not self.client.is_connected():
            await self.client.connect() 
        _, send_groups = load_all_groups()
        total_groups = len(send_groups)
        embed = create_embed(
            title="Starting Message Send Process",
            description=f"Sending messages to {total_groups} groups",
            color=0xffff00,
            fields=[("Total Groups", str(total_groups), True)]
        )
        webhook_logs(embed)
        try:
            send_msg_url = self.config['settings']['send_msg_url']
            channel, message_id = send_msg_url.split('/')[-2:]
            message = await self.client.get_messages(channel, ids=int(message_id))
            if not message:
                console.error(f"Could not find message at {send_msg_url}")
                embed = create_embed(
                    title="Message Not Found",
                    description=f"Could not find message at {send_msg_url}",
                    color=0xff0000
                )
                webhook_logs(embed)
                return
            custom_message = message.message
        except Exception as e:
            console.error(f"Failed to get message to send: {str(e)}")
            embed = create_embed(
                title="Failed to Get Message",
                description=f"Failed to get message to send: {str(e)}",
                color=0xff0000
            )
            webhook_logs(embed)
            return
        for url in send_groups:
            try:
                parsed_url = urlparse(url)
                path_parts = parsed_url.path.strip('/').split('/')
                group_name = path_parts[0]
                try:
                    to_peer = await self.client.get_input_entity(group_name)
                except ValueError:
                    console.error(f"Could not find group: {group_name}")
                    embed = create_embed(
                        title="Group Not Found",
                        description=f"Could not find group: {group_name}",
                        color=0xff0000,
                        fields=[("Group Name", group_name, True)]
                    )
                    webhook_logs(embed)
                    continue     
                if self.config['settings']['skip_msg']:
                    last_message = await self.get_last_message_in_group(to_peer)
                    if last_message and last_message.sender_id == self.user.id and not last_message.action:
                        console.info(f"Skipping {group_name} as the last message is already from the bot.")
                        self.skipped_groups += 1
                        embed = create_embed(
                            title="Group Skipped",
                            description=f"Last message in {group_name} is from bot",
                            color=0xffff00,
                            fields=[("Group Name", group_name, True)]
                        )
                        webhook_logs(embed)
                        continue
                try:
                    if len(path_parts) == 2:
                        forum_id = int(path_parts[1])
                        await self.client.send_message(to_peer, custom_message, reply_to=forum_id)
                        embed = create_embed(
                            title="Message Sent",
                            description=f"Message sent to {group_name} in topic {forum_id}",
                            color=0x00ff00,
                            fields=[
                                ("Group Name", group_name, True),
                                ("Topic ID", str(forum_id), True)
                            ]
                        )
                    else:
                        await self.client.send_message(to_peer, custom_message)
                        embed = create_embed(
                            title="Message Sent",
                            description=f"Message sent to {group_name}",
                            color=0x00ff00,
                            fields=[("Group Name", group_name, True)]
                        )
                    messages_sent += 1
                    console.success(f"Message sent to {group_name}")
                    webhook_logs(embed)
                    await asyncio.sleep(self.config['settings']['delay'])  
                except errors.ChatWriteForbiddenError:
                    await self.handle_restricted_group(group_name, "Writing messages is forbidden")              
                except errors.UserBannedInChannelError:
                    await self.handle_restricted_group(group_name, "User banned from channel")         
                except errors.ChannelPrivateError:
                    await self.handle_restricted_group(group_name, "Channel is private")       
                except errors.SlowModeWaitError as e:
                    console.warning(f"Slow mode active in {group_name}. Must wait {e.seconds} seconds")
                    embed = create_embed(
                        title="Slow Mode Active",
                        description=f"Must wait {e.seconds} seconds before sending to {group_name}",
                        color=0x0000ff,
                        fields=[
                            ("Group Name", group_name, True),
                            ("Wait Time", f"{e.seconds}s", True)
                        ]
                    )
                    webhook_logs(embed)
                    continue            
                except errors.FloodWaitError as e:
                    console.warning(f"Flood wait error. Must wait {e.seconds} seconds")
                    embed = create_embed(
                        title="Flood Wait Error",
                        description=f"Must wait {e.seconds} seconds before continuing",
                        color=0x0000ff,
                        fields=[
                            ("Group Name", group_name, True),
                            ("Wait Time", f"{e.seconds}s", True)
                        ]
                    )
                    webhook_logs(embed)
                    continue
                except errors.MessageTooLongError:
                    self.total_fails += 1
                    console.error(f"Message too long for {group_name}")
                    embed = create_embed(
                        title="Message Too Long",
                        description=f"Failed to send to {group_name} - Message exceeds length limit",
                        color=0xff0000,
                        fields=[("Group Name", group_name, True)]
                    )
                    webhook_logs(embed)              
            except Exception as e:
                self.total_fails += 1
                console.error(f"Failed to handle message for {group_name}: {str(e)}")
                embed = create_embed(
                    title="Message Send Failed",
                    description=f"Failed to send message to {group_name}",
                    color=0xff0000,
                    fields=[
                        ("Group Name", group_name, True),
                        ("Error", str(e), False)
                    ]
                )
                webhook_logs(embed)

    async def forward_message(self):
        global messages_forwarded
        if not self.client.is_connected():
            await self.client.connect()
        forward_groups, _ = load_all_groups()
        total_groups = len(forward_groups)
        embed = create_embed(
            title="Starting Message Forward Process",
            description=f"Forwarding messages to {total_groups} groups",
            color=0xffff00,
            fields=[("Total Groups", str(total_groups), True)]
        )
        webhook_logs(embed)
        try:
            forward_msg_url = self.config['settings']['forward_msg_url']
            channel, message_id = forward_msg_url.split('/')[-2:]
            message = await self.client.get_messages(channel, ids=int(message_id))
            if not message:
                console.error(f"Could not find message at {forward_msg_url}")
                embed = create_embed(
                    title="Message Not Found",
                    description=f"Could not find message at {forward_msg_url}",
                    color=0xff0000
                )
                webhook_logs(embed)
                return
        except Exception as e:
            console.error(f"Failed to get message to forward: {str(e)}")
            embed = create_embed(
                title="Failed to Get Message",
                description=f"Failed to get message to forward: {str(e)}",
                color=0xff0000
            )
            webhook_logs(embed)
            return
        for group_url in forward_groups:
            try:
                parsed_url = urlparse(group_url)
                path_parts = parsed_url.path.strip('/').split('/')
                group_name = path_parts[0]
                topic_id = None
                if len(path_parts) > 1:
                    try:
                        topic_id = int(path_parts[1])
                    except ValueError:
                        console.error(f"Invalid topic ID in URL: {group_url}")
                        embed = create_embed(
                            title="Invalid Topic ID",
                            description=f"Invalid topic ID in URL: {group_url}",
                            color=0xff0000,
                            fields=[("Group URL", group_url, False)]
                        )
                        webhook_logs(embed)
                        continue
                target_group_entity = await self.client.get_input_entity(group_name)
                if self.config['settings']['skip_msg']:
                    last_message = await self.get_last_message_in_group(target_group_entity)
                    if last_message and last_message.sender_id == self.user.id:
                        console.info(f"Skipping {group_name} as the last message is already from the bot.")
                        self.skipped_groups += 1
                        embed = create_embed(
                            title="Skipped Group",
                            description=f"Skipping {group_name} as the last message is already from the bot.",
                            color=0xffff00,
                            fields=[("Group Name", group_name, False)]
                        )
                        webhook_logs(embed)
                        continue 
                try:
                    forwarded = await self.client(functions.messages.ForwardMessagesRequest(
                        from_peer=await self.client.get_input_entity(channel),
                        id=[message.id],
                        to_peer=target_group_entity,
                        top_msg_id=topic_id if topic_id else None,
                        random_id=[random.randint(0, 2147483647)],
                        drop_author=False,
                        drop_media_captions=False
                    ))
                    messages_forwarded += 1
                    console.success(f"Message forwarded to {group_name}" + (f" topic {topic_id}" if topic_id else ""))
                    embed = create_embed(
                        title="Message Forwarded",
                        description=f"Message forwarded to {group_name}" + (f" topic {topic_id}" if topic_id else ""),
                        color=0x00ff00,
                        fields=[
                            ("Group Name", group_name, True),
                            ("Topic ID", str(topic_id) if topic_id else "None", True),
                            ("Status", "Success", True)
                        ]
                    )
                    webhook_logs(embed)
                except errors.ChatRestrictedError as e:
                    self.media_restricted_count += 1
                    text_content = message.message if message.message else "‎"
                    await self.client.send_message(
                        target_group_entity,
                        text_content,
                        reply_to=topic_id if topic_id else None
                    )
                    messages_forwarded += 1
                    console.success(f"Media restricted in {group_name}, sent text only")
                    embed = create_embed(
                        title="Media Restricted - Text Only Sent",
                        description=f"Media restricted in {group_name}, sent text only version",
                        color=0xffff00,
                        fields=[("Group Name", group_name, True), ("Status", "Partial Success", True)]
                    )
                    webhook_logs(embed)
                except errors.RPCError as e:
                    if "CHAT_SEND_MEDIA_FORBIDDEN" in str(e) or "CHAT_SEND_VIDEOS_FORBIDDEN" in str(e) or "CHAT_SEND_GIFS_FORBIDDEN" in str(e):
                        self.media_restricted_count += 1
                        text_content = message.message if message.message else "‎"
                        await self.client.send_message(
                            target_group_entity,
                            text_content,
                            reply_to=topic_id if topic_id else None
                        )
                        messages_forwarded += 1
                        console.success(f"Media restricted in {group_name}, sent text only")
                        embed = create_embed(
                            title="Media Restricted - Text Only Sent",
                            description=f"Media restricted in {group_name}, sent text only version",
                            color=0xffff00,
                            fields=[
                                ("Group Name", group_name, True),
                                ("Status", "Partial Success", True),
                                ("Error", str(e), False)
                            ]
                        )
                        webhook_logs(embed)
                    elif "CHAT_WRITE_FORBIDDEN" in str(e):
                        await self.handle_restricted_group(group_name, str(e))
                    else:
                        raise e
                await asyncio.sleep(self.config['settings']['delay'])
            except errors.SlowModeWaitError as e:
                console.warning(f"Slow mode active in {group_name}. Must wait {e.seconds} seconds")
                embed = create_embed(
                    title="Slow Mode Wait Error",
                    description=f"Must wait {e.seconds} seconds before sending to {group_name}",
                    color=0x0000ff,
                    fields=[
                        ("Group Name", group_name, True),
                        ("Wait Time", f"{e.seconds}s", True)
                    ]
                )
                webhook_logs(embed)
                continue    
            except errors.FloodWaitError as e:
                console.warning(f"Flood wait error. Must wait {e.seconds} seconds")
                embed = create_embed(
                    title="Flood Wait Error", 
                    description=f"Must wait {e.seconds} seconds before sending to {group_name}", 
                    color=0x0000ff,
                    fields=[
                        ("Group Name", group_name, True),
                        ("Wait Time", f"{e.seconds}s", True),
                        ("Error Type", "Flood Control", True)
                    ]
                )
                webhook_logs(embed)
                continue
            except Exception as e:
                self.total_fails += 1
                console.error(f"Failed to forward message to {group_name}: {str(e)}")
                embed = create_embed(
                    title="Message Forward Failed",
                    description=f"Failed to forward message to {group_name}",
                    color=0xff0000,
                    fields=[
                        ("Group Name", group_name, True),
                        ("Error", str(e), False)
                    ]
                )
                webhook_logs(embed)

    async def handle_messages(self):
        global cycles_completed
        forward_groups, send_groups = load_all_groups()
        if not forward_groups and not send_groups:
            console.error("Both forward.txt and send.txt are empty. Stopping the bot.")
            embed = create_embed(
                title="Bot Stopped",
                description="Both forward.txt and send.txt are empty.",
                color=0xff0000
            )
            webhook_logs(embed)
            return False
        if not forward_groups:
            console.warning("forward.txt is empty. Skipping forwarding messages.")
            embed = create_embed(
                title="Forwarding Skipped",
                description="forward.txt is empty.",
                color=0xffff00
            )
            webhook_logs(embed)
        else:
            try:
                await self.forward_message()
            except errors.AuthKeyDuplicatedError:
                console.error("Session is invalid or used elsewhere. Reconnecting...")
                await self.connect()
                await self.forward_message()
        if not send_groups:
            console.warning("send.txt is empty. Skipping sending custom messages.")
            embed = create_embed(
                title="Custom Messages Skipped",
                description="send.txt is empty.",
                color=0xffff00
            )
            webhook_logs(embed)
        else:
            try:
                await self.send_custom_message()
            except errors.AuthKeyDuplicatedError:
                console.error("Session is invalid or used elsewhere. Reconnecting...")
                await self.connect()
                await self.send_custom_message()
        cycles_completed += 1
        return True

    async def run(self):
        await self.start()
        while True:
            should_continue = await self.handle_messages()
            if not should_continue:
                break
            console.info("Completed all tasks. Sleeping...")
            await self.send_completion_stats()
            await asyncio.sleep(self.config['settings']['cycle_delay'])
        console.info("Bot has stopped.")

if __name__ == "__main__":
    bot = TelegramAdBot()
    loop = asyncio.get_event_loop()
    loop.create_task(update_terminal_title())
    loop.run_until_complete(bot.run())
    loop.close()
