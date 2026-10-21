"""Exercise actual candidate methods with fake Discord objects, no login/token/network."""
import ast
import re
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace, MethodType
import unittest
from unittest.mock import AsyncMock, Mock
from support_delivery import deliver


def method(name, environment):
    tree = ast.parse((Path(__file__).parent / "bot.py").read_text(encoding="utf-8"))
    klass = next(item for item in tree.body if isinstance(item, ast.ClassDef) and item.name == "HolyLoisBot")
    fn = next(item for item in klass.body if isinstance(item, ast.AsyncFunctionDef) and item.name == name)
    module = ast.fix_missing_locations(ast.Module(body=[fn], type_ignores=[]))
    exec(compile(module, "candidate-bot-method", "exec"), environment)
    return environment[name]


class SupportRoutingTests(unittest.IsolatedAsyncioTestCase):
    async def invoke(self, channel):
        embed = SimpleNamespace(add_field=Mock(), to_dict=Mock(return_value={'title': 'Help request'}))
        discord = SimpleNamespace(Embed=Mock(return_value=embed), ui=SimpleNamespace(View=Mock(return_value=SimpleNamespace(add_item=Mock())),
            Button=Mock()), ButtonStyle=SimpleNamespace(primary=1, success=2), AllowedMentions=Mock(),
            utils=SimpleNamespace(escape_mentions=str, escape_markdown=str))
        fallback = AsyncMock()
        bot = SimpleNamespace(support_channel=channel, hold_button=Mock(), support_registry=Mock())
        environment = {'discord': discord, 'NAME': re.compile(r'^[A-Za-z0-9_]{3,16}$'), 'RED': 1, 'GOLD': 2,
                       'deliver_support': deliver, 'private_webhook': fallback, 'print': Mock()}
        await MethodType(method('post_support', environment), bot)({'player': 'Fixture', 'message': 'Generated help'})
        return bot, fallback

    async def test_missing_channel_routes_to_private_staff(self):
        bot, fallback = await self.invoke(None)
        fallback.assert_awaited_once()
        bot.support_registry.received.assert_not_called()

    async def test_forbidden_send_routes_to_private_staff(self):
        channel = SimpleNamespace(guild=SimpleNamespace(owner_id=1), send=AsyncMock(side_effect=PermissionError()))
        _, fallback = await self.invoke(channel)
        fallback.assert_awaited_once()

    async def test_delivered_ticket_is_registered_without_duplicate(self):
        sent = SimpleNamespace(id=30, channel=SimpleNamespace(id=20), created_at=datetime(2026, 10, 21, tzinfo=timezone.utc))
        channel = SimpleNamespace(guild=SimpleNamespace(owner_id=1), send=AsyncMock(return_value=sent))
        bot, fallback = await self.invoke(channel)
        fallback.assert_not_awaited()
        bot.support_registry.received.assert_called_once_with(30, 20, sent.created_at.isoformat(), retention_class='routine')


class BotIntegrationTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.tell = Mock()
        self.view = SimpleNamespace(add_item=Mock())
        discord = SimpleNamespace(
            InteractionType=SimpleNamespace(component=3),
            ui=SimpleNamespace(View=Mock(return_value=self.view), Button=Mock()),
            ButtonStyle=SimpleNamespace(success=1, secondary=2), utils=SimpleNamespace(
                utcnow=lambda: datetime(2026, 10, 14, tzinfo=timezone.utc)))
        self.environment = {"discord": discord, "tell_player": self.tell}
        self.bot = SimpleNamespace(user=SimpleNamespace(id=10), support_channel=SimpleNamespace(id=20),
                                   support_registry=Mock(), hold_button=Mock())
        self.bot.support_registry.snapshot.return_value={"held":False,"resolved":None}
        self.message = SimpleNamespace(id=30, author=SimpleNamespace(id=10), embeds=[])
        self.interaction = SimpleNamespace(type=3, data={"custom_id": "hl-support:solved:Fixture"},
            channel_id=20, message=self.message, user=SimpleNamespace(display_name="Staff"),
            permissions=SimpleNamespace(manage_messages=True, administrator=False),
            response=SimpleNamespace(send_message=AsyncMock(), edit_message=AsyncMock()),
            followup=SimpleNamespace(send=AsyncMock()))

    async def invoke(self):
        await MethodType(method("on_interaction", self.environment), self.bot)(self.interaction)

    async def test_solved_records_explicit_date_after_successful_edit(self):
        await self.invoke()
        self.interaction.response.edit_message.assert_awaited_once()
        self.bot.support_registry.resolve.assert_called_once_with(30, 20, "2026-10-14T00:00:00+00:00")

    async def test_unprivileged_click_does_not_mark_solved_or_tell_player(self):
        self.interaction.permissions.manage_messages = False
        await self.invoke()
        self.interaction.response.send_message.assert_awaited_once()
        self.bot.support_registry.resolve.assert_not_called()
        self.tell.assert_not_called()

    async def test_wrong_channel_wrong_author_unknown_action_ignored(self):
        self.interaction.channel_id = 999
        await self.invoke()
        self.interaction.channel_id = 20
        self.message.author.id = 999
        await self.invoke()
        self.message.author.id = 10
        self.interaction.data["custom_id"] = "hl-support:unknown:Fixture"
        await self.invoke()
        self.bot.support_registry.resolve.assert_not_called()
        self.tell.assert_not_called()

    async def test_failed_discord_edit_does_not_record_resolution(self):
        self.interaction.response.edit_message.side_effect = RuntimeError("synthetic edit failure")
        with self.assertRaises(RuntimeError):
            await self.invoke()
        self.bot.support_registry.resolve.assert_not_called()

    async def test_hold_and_release_do_not_notify_player(self):
        for action in ('hold','release'):
            self.interaction.data['custom_id']='hl-support:'+action+':Fixture'
            await self.invoke()
            self.bot.support_registry.hold.assert_called_with(30,20,action=='hold')
        self.tell.assert_not_called()
        self.bot.support_registry.resolve.assert_not_called()

    async def test_untracked_old_request_cannot_be_reclassified_by_click(self):
        self.bot.support_registry.snapshot.return_value=None
        await self.invoke()
        self.interaction.response.send_message.assert_awaited_once()
        self.tell.assert_not_called()

    async def test_raw_edit_tracks_only_our_channel(self):
        payload=SimpleNamespace(channel_id=20,message_id=30,data={'edited_timestamp':'2026-10-14T00:00:00Z'})
        await MethodType(method('on_raw_message_edit',self.environment),self.bot)(payload)
        self.bot.support_registry.touch_message.assert_called_once_with(30,20,'2026-10-14T00:00:00Z')
        payload.channel_id=999
        await MethodType(method('on_raw_message_edit',self.environment),self.bot)(payload)
        self.bot.support_registry.touch_message.assert_called_once()

    async def test_disconnect_places_records_on_hold(self):
        await MethodType(method('on_disconnect',self.environment),self.bot)()
        self.bot.support_registry.protect_after_gap.assert_called_once()
