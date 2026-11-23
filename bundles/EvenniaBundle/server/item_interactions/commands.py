from evennia import Command

from .actions import ACTIONS, interact

ACTION_VERBS = {label: key for key, (label, _, _) in ACTIONS.items()}


class CmdInteract(Command):
    """输入 交互 <物品> 查看动作，或直接输入 动作名 物品名，例如：阅读 公交站牌。"""

    key = '交互'
    aliases = ['interact', *ACTION_VERBS]

    def func(self):
        if self.cmdname in ACTION_VERBS:
            name = self.args
            action = ACTION_VERBS[self.cmdname]
            usage = f'用法：{self.cmdname} 物品名'
        else:
            name, _, action = self.args.partition('=')
            usage = self.__doc__
        if not name.strip():
            self.caller.msg(usage)
            return
        item = self.caller.search(name.strip())
        if item:
            self.caller.msg(interact(self.caller, item, action.strip()))
