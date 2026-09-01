"""
Bridge: Client
"""

# Standard library
import os
import ctypes
import json
import pickle
import random
import re
import socket
import threading
import time
import warnings
from datetime import datetime
import math

# Third-party
import numpy as np
import pyperclip
import arcade
import arcade.gui
from arcade.exceptions import PerformanceWarning
from arcade.future.light import Light, LightLayer

# ──[ Parameters ]─────────────────────────────────────────────────────────────

# General
CARD_SCALE = 144/675
CARD_ENLARGE = 2

# Lobby parameters
LOBBY_WIDTH = 1280
LOBBY_HEIGHT = 720
LOBBY_TITLE = "Bridge: Lobby"
LOBBY_SCALE = min(LOBBY_HEIGHT/1080, LOBBY_WIDTH/1920)

# Visual appearance
MAIN_COLOR = (50, 59, 64, 255)



# ──[ Classes ]────────────────────────────────────────────────────────────────

class Layout:
    """ Layout variables """
    
    def __init__(self, width: int, height: int):
        self.update(width, height)

    def update(self, width: int, height: int):
        
        resize = min(height / 1080, width / 1920)
        
        self.width = width
        self.height = height
        self.scale = resize
        self.card_scale = resize * CARD_SCALE
        self.light_radius = width * 0.8
        self.card_width = 144 * resize
        self.card_height = 224 * resize



class Card(arcade.Sprite):
    """ Card sprite """

    def __init__(self, card_id, card_type, value, facing, owner, location, scale=1):
        """ Card constructor """

        # Attributes
        self.id = card_id
        self.type = card_type
        self.value = value
        self.facing = facing # up, down
        self.owner = owner # player_name
        self.location = location # deck, discarded, removed, hand, table

        # Image to use for the sprite when face up
        self.image = f'assets/cards/{self.id}.jpg'
        
        # Call the parent
        super().__init__(self.image, scale*CARD_SCALE, hit_box_algorithm="None")
        
    def face_down(self):
        """ Turn card face-down """
        self.texture = arcade.load_texture(r'assets/images/cards/cardback.jpg')
        
    def face_up(self):
        """ Turn card face-up """
        self.texture = arcade.load_texture(self.image)
        
        
        
class Tile(arcade.Sprite):
    """ Bid sprite """
    
    def __init__(self, column, row, side, scale = 1):
        
        # Attributes
        self.column = column
        self.row = row
        self.side = side # player, opponent
        
        # Image
        self.image = f'assets/tiles/tile.{self.side}.png'
        
        # Call the parent
        super().__init__(self.image, scale, hit_box_algorithm="None")
        
    def set_position(self, layout):

        i = ord(self.column) - 65
        j = self.row
        self.center_x = layout.width / 2 -  150 * layout.scale + i * 60 * layout.scale
        self.center_y = layout.height / 2 - 150 * layout.scale + j * 60 * layout.scale



class BoardElement(arcade.Sprite):
    """ Sector sprite """

    def __init__(self, image_path, scale):
        """ Board element constructor """
        
        # Image to use for the sprite
        self.image_file_name = image_path

        # Call the parent
        super().__init__(self.image_file_name, scale, hit_box_algorithm = "None")

    
    
class DustParticle(arcade.SpriteCircle):
    """Single dust particle"""

    def __init__(self, x, y):
        
        radius = random.uniform(4, 8)

        offset = random.randint(10, 30)
        color = (50 + offset, 59 + offset, 64 + offset)
        
        super().__init__(radius, color)

        self.center_x = x
        self.center_y = y

        angle = random.uniform(0, 2 * math.pi)
        speed = random.uniform(20, 60)  # pixel/s
        self.change_x = math.cos(angle) * speed
        self.change_y = math.sin(angle) * speed

        self.lifetime = 1.2 # s
        self.age = 0.0

    def update(self, delta_time):
        
        self.center_x += self.change_x * delta_time
        self.center_y += self.change_y * delta_time

        self.age += delta_time
        remaining = max(0.0, 1 - self.age / self.lifetime)
        self.alpha = int(255 * remaining)
        self.scale = 0.4 + 0.6 * remaining

        if self.age >= self.lifetime:
            self.remove_from_sprite_lists()



# ──[ Game View ]─────────────────────────────────────────────────────────────

class Game(arcade.View):
    """ Main application class. """

    def __init__(self, username='anonymous', server='localhost:52000', nation="Germany"):
        super().__init__()
        
        # Transfer parameters
        self.player_name = username
        self.player_nation = nation
        host_str, port_str = server.split(":")
        self.host = host_str
        self.port = int(port_str)

        # Play mat colour
        self.background_color = arcade.color.ARSENIC
        
        # Sound effects
        self.sound_slide = arcade.load_sound(r'assets/sounds/slide.mp3')
        self.sound_knock = arcade.load_sound(r'assets/sounds/knock.mp3')
        
        # Layout
        self.layout = Layout(self.window.width, self.window.height)
        
    def setup(self):
        """ Set up the game here. Call this function to restart the game. """
        
        # Check connection ----------------------------------------------------
        
        # Connect to socket
        try:
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.socket.connect((self.host, self.port))
        except:
            print('No connection possible')
            return False
        
        # Init game -----------------------------------------------------------
        
        # Set game phase
        self.game_phase = "playing"
        
        # Set playing history
        self.playing_history = []
        
        # Mouse position
        self.mouse_x = 0
        self.mouse_y = 0
        
        # Set modifier
        self.ctrl_held = False
        
        # Sprite list with all the cards, no matter what pile they are in
        self.card_list = arcade.SpriteList()
        
        # Sprite list with all the tile elements
        self.tile_list = arcade.SpriteList()
        
        # Board element list with all the board elements
        self.board_elements = arcade.SpriteList()
        
        # Create light
        self.create_light()
        
        # Init game state
        self.current_turn = None
        
        # Hovered card
        self.hover_card = None
        
        # Hovered tile
        self.hover_tile = None
        
        # Thread
        self.running = True
        
        # Sprite list with all the dust particles (visual effect only)
        self.dust_list = arcade.SpriteList()

        # Create every card
        for i in range(19,27):
            card_id = f"ac{i:02d}"
            card = Card(card_id, None, None, "up", None, "deck", self.layout.scale)
            card.position = (400, 400)
            self.card_list.append(card)
                
        # Create every group tile
        for column in ["A", "B", "C"]:
            tile = Tile(column, 0, "player", self.layout.scale)
            tile.position = (-10000, -10000)
            self.tile_list.append(tile)

        # Create board element: Texture
        image_path =  r'assets/boardelements/board.texture.png'
        self.board_texture = BoardElement(image_path, self.layout.scale)
        self.board_elements.append(self.board_texture)
        
        # Layout elements
        self.layout_elements()
        
        # Start network -------------------------------------------------------
        
        # Send player data to server
        data = {
            "player_name": self.player_name,
            "player_nation": self.player_nation
        }
        self.socket.sendall(pickle.dumps(data))
        
        # Start thread to receive messages
        self.recv_thread = threading.Thread(target=self.receive_state, daemon=True)
        self.recv_thread.start()
        
        return True
        
    
        
    def layout_elements(self):
            
        # Tiles
        for tile in self.tile_list:
            tile.scale = self.layout.scale
            tile.set_position(self.layout)
            
        # Board element: Texture
        self.board_texture.scale = self.layout.scale
        self.board_texture.position = self.layout.width / 2, self.layout.height / 2
            
            
        
    def create_light(self):
        
        # Layer to handle light sources
        self.light_layer = LightLayer(self.layout.width, self.layout.height)
        
        # Set background of light layer
        self.light_layer.set_background_color(self.background_color)
        
        # Create main light source
        self.center_light = Light(self.layout.width / 2, self.layout.height / 2,
                             radius=self.layout.light_radius,
                             color=[200, 200, 200, 255],
                             mode='soft')
        
        # Add light sources to light layer
        self.light_layer.add(self.center_light)
        
        
        
    def on_resize(self, width, height):
        """Rescales sprites"""

        # Calculate resize factors
        resize_x = width / self.layout.width
        resize_y = height / self.layout.height
        
        # Update layout variables
        self.layout.update(width, height)
        
        # Layout elements
        self.layout_elements()
        
        # Rescale light source
        self.create_light()
            
        # Reposition cards
        self.adjust_card_position()
        
        
        
    def on_update(self, delta_time):
        """Update sprites. """
        
        # Shrink previous enlarged card
        for card in self.card_list:
            if card != self.hover_card and card.scale != self.layout.card_scale:
                card.scale = self.layout.card_scale
        
        # Enlarge card we are hovering above
        if (self.hover_card != None):
            self.hover_card.scale = self.layout.card_scale*CARD_ENLARGE
                
        # Adjust card facing
        for card in self.card_list:
            if card.facing == "down":
                card.face_down()
            else:
                card.face_up()
                
        # Update dust particles
        self.dust_list.update(delta_time)
                
                
        
    def on_draw(self):
        """ Render the screen. """
        
        # Clear the screen
        self.clear()
        
        with self.light_layer:
            
            # Draw board elements
            self.board_elements.draw()
            
            # Draw tiles
            self.tile_list.draw()
            
            # Draw the cards
            self.card_list.draw()
            
            # Annotations
            self.annotate()
            
            # Dust particles
            self.dust_list.draw()
            
        self.light_layer.draw()

        

    def on_mouse_press(self, x, y, button, key_modifiers):
        """ Called when the user presses a mouse button. """

        # Get list of cards we've clicked on
        cards = arcade.get_sprites_at_point((x, y), self.card_list)

        # Have we clicked on a card?
        if len(cards) > 0:

            # Might be a stack of cards, get the top one
            held_card = cards[-1]
            
            # Play card
            if held_card.location == "hand":
                self.play_card(held_card)
                        
        # Get list of tiles we've clicked on
        tiles = arcade.get_sprites_at_point((x, y), self.tile_list)
        
        # Have we clicked on a tile?
        if len(tiles) > 0:
            
            # Might be a stack of tiles, get the top one
            held_tile = tiles[-1]
            
            # missing
            
        # Have we clicked on the empty board?
        if len(cards) == 0 and len(tiles) == 0:
            
            # Generatge dust
            for _ in range(24):
                self.dust_list.append(DustParticle(x, y))
            # Play sound
            self.play_sound("knock")
        
    
    
    def on_mouse_scroll(self, x, y, scroll_x, scroll_y):
        """ Called when the user scrolls the mouse wheel. """
                
        pass

        
        
    def on_mouse_motion(self, x: float, y: float, dx: float, dy: float):
        """ User moves mouse """
        
        # Update mouse position
        self.mouse_x = x
        self.mouse_y = y
        
        # Get list of cards we'are hovering above
        cards = arcade.get_sprites_at_point((x, y), self.card_list)
        
        # Declare top card as hovered card
        if len(cards) > 0:
            self.hover_card = cards[-1]
        else:
            self.hover_card = None
            
        # Get list of tiles we'are hovering above
        tiles = arcade.get_sprites_at_point((x, y), self.tile_list)
        
        # Declare top tile as hovered tile
        if len(tiles) > 0:
            self.hover_tile = tiles[-1]
        else:
            self.hover_tile = None
        
        # Set cursor type to default
        cursor_type = self.window.CURSOR_DEFAULT
                
        # Set cursor type to "hand" if hovering above hand card
        if len(cards) > 0 and self.current_turn == self.player_name:
            if cards[-1].location == "hand" and cards[-1].owner == self.player_name:
                cursor_type = self.window.CURSOR_HAND
                
        # Set cursor type to "hand" if hovering above tile
        if len(tiles) > 0:
            cursor_type = self.window.CURSOR_HAND
                     
        # Set cursor
        self.window.set_mouse_cursor(self.window.get_system_mouse_cursor(cursor_type))
                
        
        
    def on_key_press(self, key, _modifiers):
        """ Handle keypresses. """
        
        # Set modifier
        if key == arcade.key.LCTRL:
            self.ctrl_held = True
            
        # Leave game
        if key == arcade.key.ESCAPE and self.ctrl_held == False:
            
            # Set running to False to stop thread
            self.running = False
            
            # Send action to server
            action = {"type": "leave_game"}
            
            # Disconnect
            try:
                self.socket.sendall(pickle.dumps(action))
            except Exception:
                pass
            finally:
                self.socket.shutdown(socket.SHUT_RDWR)
                
            # De-maximize window
            hwnd = self.window._hwnd
            if ctypes.windll.user32.IsZoomed(hwnd):
                ctypes.windll.user32.ShowWindow(hwnd, 9)

            # Switch to Lobby
            menu_view = MenuView()
            self.window.set_size(LOBBY_WIDTH, LOBBY_HEIGHT)
            self.window.set_caption(LOBBY_TITLE)
            self.window.show_view(menu_view)
            
            
            
    def on_key_release(self, key, _modifiers):
        """ Handle keypresses. """
        
        # Set modifier
        if key == arcade.key.LCTRL:
            self.ctrl_held = False
            
            
            
    def play_card(self, card):
        """Send play card action to server"""

        # Create action for server
        action = {
            "type": "play_card",
            "card_id": card.id,
        }
        
        # Send action to server
        try:
            self.socket.sendall(pickle.dumps(action))
        except Exception as e:
            print(f"Error sending to server: {e}")
            


    def receive_state(self):
        """Receive game state from server"""
        
        while self.running:
            try:
                data = self.socket.recv(8192)
                self.update_state(data)
            except:
                print("Connection lost")
                time.sleep(0.1)
                continue
                
            
            
    def update_state(self, data):
        """Update game state from server data"""
        
        # Load game state
        game_state = pickle.loads(data)
        
        # Update game state variables
        self.game_phase = game_state.get("game_phase")
        
        if self.game_phase == "setup":
            return

        # Update game state variables
        self.current_turn = game_state.get("current_turn")
        
        # Play sound
        sound = game_state.get("sound")
        self.play_sound(sound)
            
        # Get logical card variables
        logical_card_list = game_state.get("cards")
        
        # Setup map for fast access
        card_map = {card.id: card for card in self.card_list}
        
        # Update card variables
        for logical_card in logical_card_list:
            key = logical_card["card_id"]
            if key in card_map:
                card = card_map[key]
                card.owner = logical_card["owner"]
                card.location = logical_card["location"]

        # Update card position
        self.adjust_card_position()
        
        # Refresh layout
        self.layout_elements()
            
            

    def play_sound(self, sound):
        
        if sound == 'play_card':
            arcade.play_sound(self.sound_slide)
        elif sound == 'knock':
            arcade.play_sound(self.sound_knock)
            
            
        
    def adjust_card_position(self):
        """Position the card based on location"""
        
        # missing
        pass
        
        
        
    def annotate(self):
        
        # missing
        pass
        
    
  
    def annotate_text(self, label, x, y, angle, size, color=arcade.color.WHITE):
        
        # Set to "" if None
        label = "" if label is None else label
        
        # Transfrom to int (if a number)
        try:
            label = int(label)
        except (ValueError, TypeError):
            pass
        
        # Transform to string
        label = str(label)
        
        # Text object
        text = arcade.Text(
            label.upper(),
            x=x, y=y,
            color=color,
            font_size=size*self.layout.scale, font_name="Courier New",
            anchor_x="center", anchor_y="center",
            align="center", rotation=angle
        )
        
        # Return
        return(text)
  


# ──[ Main ]───────────────────────────────────────────────────────────────────

def main():
    """ Main function """
    window = arcade.Window(LOBBY_WIDTH, LOBBY_HEIGHT, LOBBY_TITLE, resizable=True, antialiasing=True, vsync=True)
    # menu_view = MenuView()  # Start with menu view
    menu_view = Game()        
    menu_view.setup()     
    window.show_view(menu_view)
    arcade.run()

if __name__ == "__main__":
    main()
    