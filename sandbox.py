import arcade
import markdown  # pip install markdown
import pyglet
from pyglet.text.layout import ScrollableTextLayout


class Window(arcade.Window):
    def __init__(self):
        super().__init__(800, 600, "Markdown scroll")
        self.background_color = arcade.color.WHITE
        
        text = open("assets/menu/helptext.md", encoding="utf-8").read().replace("\t", "    ")
        html = markdown.markdown(text, extensions=["fenced_code"])
        html = f'<font face="Arial">{html}</font>'
        doc = pyglet.text.decode_html(html)
        
        self.layout = ScrollableTextLayout(
            doc, width=self.width - 80, height=self.height - 80, multiline=True
        )
        self.layout.x = 40
        self.layout.y = 40

    def on_draw(self):
        self.clear()
        self.layout.draw()

    def on_mouse_scroll(self, x, y, scroll_x, scroll_y):
        layout = self.layout
        # view_y = 0 ist ganz oben, negative Werte scrollen nach unten
        min_y = min(0, -(layout.content_height - layout.height))
        layout.view_y = max(min_y, min(0, layout.view_y + scroll_y * 30))

Window()
arcade.run()