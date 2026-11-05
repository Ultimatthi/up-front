import math

import arcade



# ──[ Parameters ]─────────────────────────────────────────────────────────────

WAITING_PERIOD = 2.4  # s, one shuffle cycle
WAITING_CARDS = 4
WAITING_VEIL_ALPHA = 170
WAITING_SOUND = "assets/sounds/waiting.wav"  # loop of two shuffle cycles
READY_SOUND = "assets/sounds/ready.wav"
WAITING_VOLUME = 0.5



# ──[ Waiting Animation ]──────────────────────────────────────────────────────

class WaitingAnimation:

    def __init__(self, card_texture, card_scale, veil_color):

        # Appearance
        self.texture = card_texture
        self.card_scale = card_scale
        self.veil_color = tuple(veil_color[:3]) + (WAITING_VEIL_ALPHA,)

        # Elapsed time (loops every WAITING_PERIOD)
        self.time = 0.0

        # Looping drum sound, in sync with the shuffle
        self.sound = arcade.load_sound(WAITING_SOUND)
        self.sound_ready = arcade.load_sound(READY_SOUND)
        self.player = None
        self.active = False

    def update(self, delta_time, active):

        # Game got ready: stop the loop and signal the connection
        if self.active and not active and self.player is not None:
            self.stop()
            arcade.play_sound(self.sound_ready, volume=WAITING_VOLUME)

        self.active = active

        # Start sound and animation together
        if active and self.player is None:
            self.time = 0.0
            self.player = arcade.play_sound(self.sound, volume=WAITING_VOLUME, loop=True)

        self.time += delta_time

    def stop(self):

        if self.player is not None:
            arcade.stop_sound(self.player)
            self.player = None

    def draw(self, width, height, scale):

        # Smooth easing between 0 and 1
        def smoothstep(x):
            x = min(max(x, 0.0), 1.0)
            return x * x * (3 - 2 * x)

        cx, cy = width / 2, height / 2 + 30 * scale
        w = self.texture.width * self.card_scale * scale
        h = self.texture.height * self.card_scale * scale
        step = 4 * scale
        p = (self.time % WAITING_PERIOD) / WAITING_PERIOD

        # Dim the board
        arcade.draw_lrbt_rectangle_filled(0, width, 0, height, self.veil_color)

        # Top card slides out, then tucks back under the pile
        out = smoothstep(p / 0.4)
        back = smoothstep((p - 0.4) / 0.35)
        lift = math.sin(math.pi * min(p / 0.75, 1))

        # Remaining cards sink one level while the top card moves to the bottom
        cards = []
        for i in range(WAITING_CARDS - 1):
            level = i + back
            cards.append((level, cx - level * step, cy + level * step, level - 2, 0.0))
        level = (WAITING_CARDS - 1) * (1 - back)
        x = cx - level * step + (out - back) * w * 1.15
        y = cy + level * step + lift * 10 * scale
        angle = (out - back) * 12 + level - 2
        cards.append((level if p >= 0.4 else WAITING_CARDS, x, y, angle, lift))

        # Draw cards bottom to top with shadows
        for _, x, y, angle, l in sorted(cards, key=lambda card: card[0]):
            shadow = arcade.XYWH(x + (6 + 8 * l) * scale, y - (6 + 8 * l) * scale, w, h)
            arcade.draw_texture_rect(self.texture, shadow, color=arcade.color.BLACK,
                                     angle=angle, alpha=int(70 - 30 * l))
            arcade.draw_texture_rect(self.texture, arcade.XYWH(x, y, w, h), angle=angle)

        # Label with dots in sync with the shuffle
        dots = int(p * 3) + 1
        label = "Waiting for opponent" + "." * dots + " " * (3 - dots)
        arcade.Text(
            label,
            x=cx, y=cy - h / 2 - 50 * scale,
            color=arcade.color.WHITE,
            font_size=18 * scale, font_name="Arial", bold=True,
            anchor_x="center", anchor_y="center"
        ).draw()
