"""Areas group rooms but cannot themselves contain characters or items."""
from evennia.objects.objects import DefaultRoom


class Area(DefaultRoom):
    def at_pre_object_receive(self, moved_object, source_location, **kwargs):
        moved_object.msg('这里是区域，请通过它的入口进入。')
        return False
