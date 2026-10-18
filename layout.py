# SPDX-License-Identifier: GPL-3.0-only
"""GTK layout helpers. Reflow keeps the same widgets, focus and callbacks."""
from gi.repository import Gtk


class AdaptiveBox(Gtk.Box):
    """Use one column when the horizontal contents would exceed the width."""
    def __init__(self,spacing=12,**kwargs):
        super().__init__(orientation=Gtk.Orientation.VERTICAL,spacing=spacing,**kwargs)

    def widths(self):
        sizes=[child.get_preferred_width() for child in self.get_children() if child.get_visible()]
        border,_vertical=self.insets()
        return max((s[0] for s in sizes),default=0)+border,sum(s[1] for s in sizes)+max(0,len(sizes)-1)*self.get_spacing()+border

    def insets(self):
        context=self.get_style_context();state=self.get_state_flags()
        padding=context.get_padding(state);border=context.get_border(state)
        extra=self.get_border_width()*2
        return padding.left+padding.right+border.left+border.right+extra,padding.top+padding.bottom+border.top+border.bottom+extra

    def arrange(self,width):
        _minimum,horizontal=self.widths()
        direction=Gtk.Orientation.HORIZONTAL if width>=horizontal else Gtk.Orientation.VERTICAL
        if direction!=self.get_orientation():self.set_orientation(direction)

    def do_get_request_mode(self):return Gtk.SizeRequestMode.HEIGHT_FOR_WIDTH

    def do_get_preferred_width(self):
        return self.widths()

    def do_get_preferred_width_for_height(self,height):return self.get_preferred_width()

    def do_get_preferred_height_for_width(self,width):
        # GTK measures several widths before allocating. Changing orientation
        # while measuring would queue another resize and can loop indefinitely.
        children=[child for child in self.get_children() if child.get_visible()]
        horizontal_border,border=self.insets()
        gap=max(0,len(children)-1)*self.get_spacing()
        _minimum,horizontal=self.widths()
        if width>=horizontal:
            expandable=[child for child in children if self.child_get_property(child,'expand')]
            extra=max(0,width-horizontal)//max(1,len(expandable))
            sizes=[child.get_preferred_height_for_width(child.get_preferred_width()[1]+(extra if child in expandable else 0)) for child in children]
            return tuple(max((size[index] for size in sizes),default=0)+border for index in (0,1))
        sizes=[child.get_preferred_height_for_width(max(1,width-horizontal_border)) for child in children]
        return tuple(sum(size[index] for size in sizes)+gap+border for index in (0,1))

    def do_size_allocate(self,allocation):
        self.arrange(allocation.width)
        Gtk.Box.do_size_allocate(self,allocation)


class AdaptiveStackSwitcher(Gtk.StackSwitcher):
    """Native stack tabs, stacked vertically when their labels do not fit."""
    def __init__(self):
        super().__init__()
        self.set_orientation(Gtk.Orientation.VERTICAL)
        self.set_homogeneous(False)

    widths=AdaptiveBox.widths
    insets=AdaptiveBox.insets
    arrange=AdaptiveBox.arrange
    do_get_request_mode=AdaptiveBox.do_get_request_mode
    do_get_preferred_width=AdaptiveBox.do_get_preferred_width
    do_get_preferred_width_for_height=AdaptiveBox.do_get_preferred_width_for_height
    do_get_preferred_height_for_width=AdaptiveBox.do_get_preferred_height_for_width
    do_size_allocate=AdaptiveBox.do_size_allocate


def fit_window(window,width,height):
    display=window.get_display()
    monitor=display.get_monitor_at_window(window.get_window()) if window.get_window() else display.get_primary_monitor()
    if monitor is None and display.get_n_monitors():monitor=display.get_monitor(0)
    if monitor:
        area=monitor.get_workarea();width=min(width,area.width);height=min(height,max(240,area.height-48))
    window.set_default_size(width,height)
