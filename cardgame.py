"""
UpFront: Client
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
from collections import defaultdict

# Third-party
import numpy as np
import pandas as pd
import pyperclip
import arcade
import arcade.gui
from PIL import Image, ImageDraw
from arcade.exceptions import PerformanceWarning
from arcade.future.light import Light, LightLayer

# ──[ Parameters ]─────────────────────────────────────────────────────────────

# General
CARD_SCALE = 144/675
UNIT_SCALE = 144/600
CARD_ENLARGE = 1.05
UNIT_ENLARGE = 1.5
GROUP_ENLARGE = 1.1
BUTTON_ENLARGE = 1.1

# Lobby parameters
LOBBY_WIDTH = 1280
LOBBY_HEIGHT = 720
LOBBY_TITLE = "Up Front: Lobby"
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
        self.unit_scale = resize * UNIT_SCALE
        self.light_radius = width * 0.5
        self.card_width = 144 * resize
        self.card_height = 224 * resize



class Card(arcade.Sprite):
    """ Card sprite """

    def __init__(self, card_id, card_type, scale=1):

        # Attributes
        self.id = card_id
        self.type = card_type
        self.facing = "down" # up, down
        self.owner = None # player_name
        self.location = "deck" # deck, discard, void, hand, table
        self.group_id = None

        # Image to use for the sprite when face up
        self.texture_front = self.load_texture(f'assets/cards/{self.id}.jpg')
        
        # Image to use for the sprite when face down
        self.texture_back = self.load_texture(r'assets/cards/cardback.jpg')
        
        # Call the parent
        super().__init__(self.texture_back, scale*CARD_SCALE, hit_box_algorithm="None")
        
    def adjust_texture(self):
        
        # Get new texture
        if self.facing == "up":
            target_texture = self.texture_front
        else:
            target_texture = self.texture_back
            
        # Set new texture (only when needed)
        if self.texture != target_texture:
            self.texture = target_texture
            
    def load_texture(self, image_path):
    
        # Load image and mask
        image = Image.open(image_path).convert("RGBA")
        mask = Image.open(r'assets/cards/mask.png').convert("L")
        
        # Adjust size if mask and image size differ
        if mask.size != image.size:
            mask = mask.resize(image.size)
        
        # Apply mask
        image.putalpha(mask)
        return arcade.Texture(image)
    
    
    
class Unit(arcade.Sprite):
    """ Card sprite """

    def __init__(self, unit_id, nation, group_id, scale=1):

        # Attributes
        self.id = unit_id
        self.nation = nation
        self.group = group_id
        self.pinned = False

        base = f'assets/units/{nation}s/{unit_id}'

        # Image to use for the sprite when face up
        self.texture_front = arcade.load_texture(f'{base}.jpg')

        # Image to use for the sprite when face down
        self.texture_back = arcade.load_texture(f'{base}b.jpg')
        
        # Call the parent
        super().__init__(self.texture_front, scale*UNIT_SCALE, hit_box_algorithm="None")
        
    def adjust_texture(self):
        
        # Get new texture
        if self.pinned == False:
            target_texture = self.texture_front
        else:
            target_texture = self.texture_back
            
        # Set new texture (only when needed)
        if self.texture != target_texture:
            self.texture = target_texture


        
class Group(arcade.Sprite):
    """ Group sprite """
    
    def __init__(self, group_id, label, scale=1):
        
        # Attribute
        self.id = group_id
        self.label = label
        self.owner = None # player, opponent
        self.range = 0
        self.moving = False
        self.terrain = None
        self.active = True
        
        # Textures
        self.textures_map = {}
        for owner in ("player", "opponent"):
            for state in ("inactive", "active", "inactive_moving", "active_moving"):
                path = rf'assets/tiles/tile.{owner}.{state}.png'
                self.textures_map[(owner, state)] = arcade.load_texture(path)
        
        # Call the parent
        super().__init__(None, scale, hit_box_algorithm="None")
        
    def set_position(self, layout):
        
        if self.owner == None:
            return

        i = ord(self.label) - 65 + 1
        j = self.range if self.owner == "player" else 5 - self.range
        self.center_x = layout.width / 2 -  150 * layout.scale + i * 60 * layout.scale
        self.center_y = layout.height / 2 - 150 * layout.scale + j * 60 * layout.scale
        
    def adjust_texture(self):
        
        if self.owner is None:
            return
        
        state = "active" if self.active else "inactive"
        if self.moving:
            state += "_moving"
        
        target_texture = self.textures_map[(self.owner, state)]
        
        if self.texture != target_texture:
            self.texture = target_texture
            
            

class Button(arcade.Sprite):
    """ Board element sprite """

    def __init__(self, name, image_path, scale):
        
        # Attribute
        self.name = name

        # Image to use for the sprite
        self.image_file_name = image_path

        # Call the parent
        super().__init__(self.image_file_name, scale, hit_box_algorithm = "None")
            


class BoardElement(arcade.Sprite):
    """ Board element sprite """

    def __init__(self, image_path, scale):

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
        self.sound_knock = arcade.load_sound(r'assets/sounds/knock.mp3')
        self.sound_play = arcade.load_sound(r'assets/sounds/play_card.mp3')
        self.sound_select = arcade.load_sound(r'assets/sounds/select.mp3')
        
        
        # Layout
        self.layout = Layout(self.window.width, self.window.height)
        
        # Tables
        self.card_table = pd.read_csv("assets/cards/card_table.txt", sep=";")
        self.card_table.set_index("id", inplace=True)
    


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
        self.game_phase = "assignment"
        
        # Mouse position
        self.mouse_x = 0
        self.mouse_y = 0
        
        # Set modifier
        self.ctrl_held = False
        
        # Sprite list with all the cards, no matter what pile they are in
        self.card_list = arcade.SpriteList()
        
        # Sprite list with all the cards, no matter what pile they are in
        self.unit_list = arcade.SpriteList()
        
        # Sprite list with all the group tile elements
        self.group_list = arcade.SpriteList()
        
        # Board element list with all the buttons
        self.button_list = arcade.SpriteList()
        
        # Board element list with all the board elements
        self.board_elements = arcade.SpriteList()
        
        # Create light
        self.create_light()
        
        # Init game state
        self.current_turn = None
        
        # Hovered card
        self.hover_card = None
        
        # Hovered unit
        self.hover_unit = None
        
        # Hovered group tile
        self.hover_group = None
        
        # Hovered button
        self.hover_button = None
        
        # Thread
        self.running = True
        
        # Sprite list with all the dust particles (visual effect only)
        self.dust_list = arcade.SpriteList()

        # Create every card
        for i in range(19,27):
            card_id = f"ac{i:02d}"
            row = self.card_table.loc[card_id]
            card = Card(card_id, row["type"], self.layout.scale)
            card.position = (-10000, -10000)
            self.card_list.append(card)
            
        # Create every unit
        for i in range(1,6):
            unit_id = f"ge{i:02d}"
            group_id = "A1"
            unit = Unit(unit_id, "german", group_id, self.layout.scale)
            unit.position = (-10000, -10000)
            self.unit_list.append(unit)
                
        # Create every group tile
        for label in ["A", "B", "C", "D"]:
            for section in [0, 1]:
                group_id = label + str(section+1)
                group = Group(group_id, label, self.layout.scale)
                group.position = (-10000, -10000)
                if group_id == "A":
                    group.active = True
                self.group_list.append(group)
                
        # Init active groups
        self.active_groups = {"player": self.group_list[0], "opponent": self.group_list[1]}

        # Create board element: Texture
        image_path =  r'assets/boardelements/board.texture.png'
        self.board_texture = BoardElement(image_path, self.layout.scale)
        self.board_elements.append(self.board_texture)
        
        # Create board element: Contour
        image_path =  r'assets/boardelements/board.contour.png'
        self.board_contour = BoardElement(image_path, self.layout.scale)
        self.board_contour.alpha = 20
        self.board_elements.append(self.board_contour)
        
        # Create board element: Group frame (player)
        image_path =  r'assets/boardelements/board.group.player.png'
        self.board_group_player = BoardElement(image_path, self.layout.scale)
        self.board_elements.append(self.board_group_player)
        
        # Create board element: Group frame (player)
        image_path =  r'assets/boardelements/board.group.opponent.png'
        self.board_group_opponent = BoardElement(image_path, self.layout.scale)
        self.board_elements.append(self.board_group_opponent)
        
        # Create board element: Grid
        image_path =  r'assets/boardelements/board.grid.png'
        self.board_grid = BoardElement(image_path, self.layout.scale)
        self.board_elements.append(self.board_grid)
        
        # Create board element: Piles
        image_path =  r'assets/boardelements/board.piles.png'
        self.board_piles = BoardElement(image_path, self.layout.scale)
        self.board_elements.append(self.board_piles)
        
        # Create button: End turn
        image_path =  r'assets/boardelements/button.endturn.png'
        self.button_endturn = Button("endturn", image_path, self.layout.scale)
        self.button_list.append(self.button_endturn)
        
        # Create button: Surrender
        image_path =  r'assets/boardelements/button.surrender.png'
        self.button_surrender = Button("surrender", image_path, self.layout.scale)
        self.button_list.append(self.button_surrender)
        
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
            
        # Board element: Texture
        self.board_texture.width = self.layout.width
        self.board_texture.height = self.layout.height
        self.board_texture.position = self.layout.width / 2, self.layout.height / 2
        
        # Board element: Contour
        self.board_contour.width = self.layout.width
        self.board_contour.height = self.layout.height
        self.board_contour.position = self.layout.width / 2, self.layout.height / 2
        
        # Board element: Board 1
        self.board_group_player.scale = self.layout.scale
        self.board_group_player.left = (20 - 1) * self.layout.scale
        self.board_group_player.bottom = (20 - 1) * self.layout.scale
     
        # Board element: Board 2
        self.board_group_opponent.scale = self.layout.scale
        self.board_group_opponent.right = self.window.width - (20 - 1) * self.layout.scale
        self.board_group_opponent.top = self.window.height - (20 - 1) * self.layout.scale
        
        # Board element: Grid
        self.board_grid.scale = self.layout.scale
        self.board_grid.position = self.layout.width / 2, self.layout.height / 2
        
        # Board element: Piles
        self.board_piles.scale = self.layout.scale
        self.board_piles.left = (20 - 1) * self.layout.scale
        self.board_piles.top = self.window.height - (20 - 1) * self.layout.scale
        
        
        # Button: End turn
        self.button_endturn.scale = self.layout.scale
        self.button_endturn.right = self.window.width - 20 * self.layout.scale
        self.button_endturn.bottom = 20 * self.layout.scale
        
        # Button: Surrender
        self.button_surrender.scale = self.layout.scale
        self.button_surrender.right = self.window.width - 120 * self.layout.scale
        self.button_surrender.bottom = 20 * self.layout.scale

            
        
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
        
        # Reposition cards
        self.adjust_unit_position()
        
        # Reposition group tiles
        self.adjust_group_position()
        
        
        
    def on_update(self, delta_time):
        """Update sprites. """
        
        # Adjust hovered elements
        self.adjust_hovered_elements()
                
        # Adjust card texture
        for card in self.card_list:
            card.adjust_texture()
            
        # Set active group flag
        for group in self.group_list:
            group.active = group in self.active_groups.values()
                
        # Adjust group textgure
        for group in self.group_list:
            group.adjust_texture()
                
        # Update dust particles
        self.dust_list.update(delta_time)
                
                
        
    def on_draw(self):
        """ Render the screen. """
        
        # Clear the screen
        self.clear()
        
        with self.light_layer:
            
            # Draw board elements
            self.board_elements.draw()
            
            # Draw buttons
            self.button_list.draw()
            
            # Draw group tiles
            self.group_list.draw(pixelated=True)
            
            # Draw the cards
            self.card_list.draw()
            
            # Draw the units
            self.unit_list.draw()
            
            # Draw hovered unit
            if self.hover_unit is not None:
                arcade.draw_sprite(self.hover_unit)
            
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
                self.play_card(held_card, self.active_groups["player"])
        
        # Get list of group tiles we've clicked on
        groups = arcade.get_sprites_at_point((x, y), self.group_list)
        
        # Have we clicked on a group tile?
        if len(groups) > 0:
            
            # Might be a stack of tiles, get the top one
            held_group = groups[-1]
            
            # Switch to that group
            self.active_groups[held_group.owner] = held_group
            
            # Play sound
            self.play_sound("select")
            
        # Get list of buttons we've clicked on
        buttons = arcade.get_sprites_at_point((x, y), self.button_list)
            
        # Have we clicked on a button?
        if len(buttons) > 0:
            
            # Might be a stack of tiles, get the top one
            held_button = buttons[-1]
            
            # Play sound
            self.play_sound("select")
            
            # End turn
            if held_button.name == "endturn":
                self.end_turn()
                
        # Get list of unit cards we've clicked on
        units = arcade.get_sprites_at_point((x, y), self.unit_list)
            
        # Have we clicked on the empty board?
        if len(cards) == 0 and len(groups) == 0 and len(buttons) == 0 and len(units) == 0:
            
            # Generatge dust
            for _ in range(24):
                self.dust_list.append(DustParticle(x, y))
            # Play sound
            self.play_sound("knock")
        
        # Adjust card position
        self.adjust_card_position()
        
        # Update unit position
        self.adjust_unit_position()
        
    
    
    def on_mouse_scroll(self, x, y, scroll_x, scroll_y):
        """ Called when the user scrolls the mouse wheel. """
        
        # Check if groups are assigned
        if any(group.owner is None for group in self.group_list):
            return
        
        # Select side
        target_owner = "opponent" if self.ctrl_held else "player"
                
        # Change active group
        if scroll_y < 0:
            target_label = chr((ord(self.active_groups[target_owner].label) - ord('A') + 1) % 4 + ord('A'))
        else:
            target_label = chr((ord(self.active_groups[target_owner].label) - ord('A') - 1) % 4 + ord('A'))
            
        # Find group
        target_group = next(group for group in self.group_list if group.label == target_label and group.owner == target_owner)
    
        # Change active group
        self.active_groups[target_owner] = target_group
            
        # Adjust card position
        self.adjust_card_position()
        
        # Adjust card position
        self.adjust_unit_position()
        
        # Play sound
        self.play_sound("select")

        
        
    def on_mouse_motion(self, x: float, y: float, dx: float, dy: float):
        """ User moves mouse """
        
        # Update mouse position
        self.mouse_x = x
        self.mouse_y = y
        
        # Set cursor type to default
        cursor_type = self.window.CURSOR_DEFAULT
        
        
        # Get list of cards we'are hovering above
        cards = arcade.get_sprites_at_point((x, y), self.card_list)
        
        # Declare top card as hovered card
        if len(cards) > 0:
            self.hover_card = cards[-1]
        else:
            self.hover_card = None
            
        # Set cursor type to "hand" if hovering above hand card
        if len(cards) > 0 and self.current_turn == self.player_name:
            if cards[-1].location == "hand" and cards[-1].owner == "player":
                cursor_type = self.window.CURSOR_HAND
                
                
        # Get list of cards we'are hovering above
        units = arcade.get_sprites_at_point((x, y), self.unit_list)
                
        # Declare top unit as hovered unit
        if len(units) > 0:
            self.hover_unit = units[-1]
        else:
            self.hover_unit = None
            
        # Get list of group tiles we'are hovering above
        groups = arcade.get_sprites_at_point((x, y), self.group_list)
        
        # Declare top tile as hovered tile
        if len(groups) > 0:
            self.hover_group = groups[-1]
        else:
            self.hover_group = None
            
        # Set cursor type to "hand" if hovering above group tile
        if len(groups) > 0:
            cursor_type = self.window.CURSOR_HAND
            
        
        # Get list of buttons we'are hovering above
        buttons = arcade.get_sprites_at_point((x, y), self.button_list)
        
        # Declare top button as hovered button
        if len(buttons) > 0:
            self.hover_button = buttons[-1]
        else:
            self.hover_button = None
            
        # Set cursor type to "hand" if hovering above button
        if len(buttons) > 0:
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
            
            
            
    def play_card(self, card, group):
        """Send play card action to server"""

        # Create action for server
        action = {
            "type": "play_card",
            "card_id": card.id,
            "group_id": group.id
        }
        
        # Bring card on top
        self.card_list.remove(card)
        self.card_list.append(card)
        
        # Send action to server
        try:
            self.socket.sendall(pickle.dumps(action))
        except Exception as e:
            print(f"Error sending to server: {e}")
            
            
            
    def end_turn(self):
        """Send end_turn action to server"""

        # Create action for server
        action = {
            "type": "end_turn"
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
                card.group_id = logical_card["group_id"]
                
        # Get logical group variables
        logical_group_list = game_state.get("groups")
        
        # Setup map for fast access
        group_map = {group.id: group for group in self.group_list}
        
        # Update card variables
        for logical_group in logical_group_list:
            key = logical_group["group_id"]
            if key in group_map:
                group = group_map[key]
                group.owner = logical_group["owner"]
                group.range = logical_group["range"]
                group.moving = logical_group["moving"]
                group.terrain = logical_group["terrain"]

        # Update card position
        self.adjust_card_position()
        
        # Update card position
        self.adjust_unit_position()
        
        # Update group position
        self.adjust_group_position()
        
        # Refresh layout
        self.layout_elements()
            
            

    def play_sound(self, sound):
        
        if sound == 'knock':
            arcade.play_sound(self.sound_knock)
        elif sound == 'play_card':
            arcade.play_sound(self.sound_play)
        elif sound == 'select':
            arcade.play_sound(self.sound_select)
            
            
    
    def adjust_hovered_elements(self):
        
        # Shrink previous enlarged card
        for card in self.card_list:
            if card != self.hover_card and card.scale != self.layout.card_scale:
                card.scale = self.layout.card_scale
        
        # Enlarge card we are hovering above
        if (self.hover_card != None):
            self.hover_card.scale = self.layout.card_scale*CARD_ENLARGE
            
        # Shrink previous enlarged group tile
        for group in self.group_list:
            if group != self.hover_group and group.scale != self.layout.scale:
                group.scale = self.layout.scale
        
        # Enlarge group tile we are hovering above
        if (self.hover_group != None):
            self.hover_group.scale = self.layout.scale*GROUP_ENLARGE
            
        # Shrink previous enlarged button
        for button in self.button_list:
            if button != self.hover_button and button.scale != self.layout.scale:
                button.scale = self.layout.scale
        
        # Enlarge group tile we are hovering above
        if (self.hover_button != None):
            self.hover_button.scale = self.layout.scale*BUTTON_ENLARGE
            
            
        # Shrink previous enlarged unit
        for unit in self.unit_list:
            if unit != self.hover_unit and unit.scale != self.layout.unit_scale:
                unit.scale = self.layout.unit_scale
                self.adjust_unit_position()
        
        # Enlarge unit we are hovering above
        if (self.hover_unit != None):
            self.hover_unit.scale = self.layout.unit_scale*UNIT_ENLARGE
            self.keep_sprite_within_window(self.hover_unit)

            
        
    def adjust_card_position(self):
        
        # Get cards in player's hand
        hand = [card for card in self.card_list if card.location == "hand"]
        
        # Get cards on table
        table = [card for card in self.card_list if card.location == "table"]

        # Get cards in piles
        deck = [card for card in self.card_list if card.location == "deck"]
        
        # Get cards in discard pile
        discard = [card for card in self.card_list if card.location == "discard"]
        
        # Get cards in removed card pile
        void = [card for card in self.card_list if card.location == "void"]
        
        # Count terrain/movement cards per (owner, group_id)
        stack_counts = defaultdict(int)

        # Player's hand
        for i, card in enumerate(hand):
            
            # Check if owned by player
            if card.owner != "player":
                continue
            
            # Set facing
            card.facing = "up"
            
            # Get position
            x = (721 + i*154) * self.layout.scale
            y = 132 * self.layout.scale
            
            # Set position
            card.position = (x, y)
            
        # Opponent's hand
        for i, card in enumerate(hand):
            
            # Check if owned by opponent
            if card.owner != "opponent":
                continue
            
            # Set facing
            card.facing = "down"
            
            # Get position
            x = (721 + i*154) * self.layout.scale
            y = 632 * self.layout.scale
            
            # Set position
            card.position = (x, y)
            
        # Player's table card
        for card in table:
            
            # Check if owned by player
            if card.owner != "player":
                continue
            
            # Check if its group id is active
            if card.group_id != self.active_groups["player"].id:
                card.position = (-10000, -10000)
                continue
            
            # Set facing
            card.facing = "up"
            
            # Set position
            if card.type in ["movement", "terrain"]:
                key = (card.owner, card.group_id)
                stack_counts[key] += 1
                card.position = (598*self.layout.scale, 544*self.layout.scale)
            else:
                card.position = (420*self.layout.scale, 544*self.layout.scale)
            
            # Adjust position of movement card other cards are present
            if card.type == "movement" and stack_counts[key] > 1:
                offset = 40*(stack_counts[key]-1)*self.layout.scale
                x, y = card.position
                card.position = (x + offset, y - offset)
                self.card_list.remove(card)
                self.card_list.append(card)
                
        # Action deck
        for card in deck:
            card.position = (-10000, -10000)
            
        # Discard pile
        for card in discard:
            card.position = (-10000, -10000)
            
        # Removed cards
        for card in void:
            card.position = (-10000, -10000)
            
            
    def adjust_unit_position(self):
        
        # Get units of active group
        group = [unit for unit in self.unit_list if unit.group == self.active_groups["player"].id]
        
        # Get units of inactive groups
        inactive_groups = set(self.unit_list) - set(group)
        
        # Adjust active unit cards
        for i, unit in enumerate(group):
            x = (100 + 150 * (i % 4)) * self.layout.scale
            y = (120 + 192 * int(i/4)) * self.layout.scale
            unit.position = (x, y)
            
        # Adjust inactive unit cards
        for unit in inactive_groups:
            unit.position = (-10000, -10000)
            
            
            
    def adjust_group_position(self):
        
        # Adjust group tiles
        for group in self.group_list:
            group.set_position(self.layout)
            
            
            
    def keep_sprite_within_window(self, sprite):
        
        offset = 10 * self.layout.scale
        
        sprite.left = max(sprite.left, offset)
        sprite.right = min(sprite.right, self.window.height - offset)
        sprite.bottom = max(sprite.bottom, offset)
        sprite.top = min(sprite.top, self.window.width - offset)
            
        
            
    def annotate(self):
        
        # Player's active group
        label = "Group " + str(self.active_groups["player"].label)
        x = 70*self.layout.scale
        y = 625*self.layout.scale
        text = self.annotate_text(label, x, y, 0, 18)
        text.draw()
        
        # Opponent's active group
        label = "Group " + str(self.active_groups["opponent"].label)
        x = self.window.width - 70*self.layout.scale
        y = self.window.height - 625*self.layout.scale
        text = self.annotate_text(label, x, y, 0, 18)
        text.draw()
        
        # Counter: Action deck pile
        deck = [card for card in self.card_list if card.location == "deck"]
        label = len(deck) if deck else 0
        x = self.board_piles.left + 40*self.layout.scale
        y = self.board_piles.top - 60*self.layout.scale
        text = self.annotate_text(label, x, y, 0, 18)
        text.draw()
        
        # Counter: Discard pile
        discard = [card for card in self.card_list if card.location == "discard"]
        label = len(discard) if discard else 0
        x = self.board_piles.left + (40+80+20)*self.layout.scale
        y = self.board_piles.top - 60*self.layout.scale
        text = self.annotate_text(label, x, y, 0, 18)
        text.draw()
        
        # Counter: Removed card
        void = [card for card in self.card_list if card.location == "void"]
        label = len(void) if void else 0
        x = self.board_piles.left + (40+160+40)*self.layout.scale
        y = self.board_piles.top - 60*self.layout.scale
        text = self.annotate_text(label, x, y, 0, 18)
        text.draw()
        
        # Terrain on group tiles
        for group in self.group_list:
            label = group.terrain
            x = group.center_x
            y = group.center_y - 10 * self.layout.scale
            color = arcade.color.BLACK
            text = self.annotate_text(label, x, y, 0, 10, color, False)
            text.draw()
            
    
  
    def annotate_text(self, label, x, y, angle, size, color=arcade.color.WHITE, bold=True):
        
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
            label,
            x=x, y=y,
            color=color,
            font_size=size*self.layout.scale, font_name="Arial",
            anchor_x="center", anchor_y="center",
            align="center", rotation=angle, bold=bold
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
    