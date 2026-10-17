"""
UpFront: Server
"""

import socket
import threading
import pickle
import time
import re
import random
import pandas as pd


# ──[ Parameter ]──────────────────────────────────────────────────────────────

FPS = 30
FULL_TABLE = 2

MAX_HAND = {"german": 5, "american": 6, "russian": 4, "british": 5,
            "japanese": 4, "french": 6, "italian": 4}

MAX_DISCARD = {"german": 1, "american": 2, "russian": 4, "british": 2,
               "japanese": 2, "french": 1, "italian": 2}

NATIONS = ["german", "american"] # implemented nations
SIDES = ["1", "2"]

ACTIONS = {
    "fire":     "fired",
    "hero":     "heroic",
    "movement": "moved",
    "rally":    "rallied",
    "smoke":    "smoked",
    "sniper":   "sniped",
    "terrain":  "entered",
    "wire":     "wired"
}

TERRAIN_MOD = {
    None:        (0,   0),
    "brush":     (0,  -1),
    "woods":     (0,  -2),
    "buildings": (0,  -2),  # TODO: some buildings are -3
    "hill":      (+1, -1),  # with conditions
    "marsh":     (-1, -1),
    "stream":    (-1,  0),
    "gully":     (0,  -2),  # with conditions
    "wall":      (0,  -1),  # with conditions
    "pillbox":   (0, - 4)
}



# ──[ Classes ]────────────────────────────────────────────────────────────────

class Card:
    """ Card for server logics """
    
    def __init__(self, card_id, card_type, card_subtype, rnc, breeze, color):

        self.id = card_id
        self.type = card_type
        self.subtype = card_subtype
        self.rnc = rnc
        self.breeze = breeze
        self.color = color
        self.location = "deck" # deck, discard, void, hand, table
        self.group = None
        self.owner = None # player_name
        self.stack_index = 0
        self.draw_index = 0
        
        
        
class Unit:
    """ Unit card for server logics """

    def __init__(self, unit_id, nation, rank, name, weapon, malfunction, 
                 ccv, firepower, morale, panic, rout, kia, points):
        
        # Attributes
        self.id = unit_id
        self.nation = nation
        self.rank = rank
        self.name = name
        self.weapon = weapon
        self.ccv = ccv # rallied|pinned|rallied(disarmed)|pinned(disarmed)
        self.morale = morale
        self.panic = panic
        self.rout = rout
        self.kia = kia # rallied|pinned
        self.points = points
        self.state = "rallied" # rallied, pinned, routed, kia
        self.group = None
        self.owner = None
        self.heroic = False
        
        # Attributes (crew related)
        self._firepower = firepower
        self._malfunction = malfunction
        self.set_mode("uncrewed")
            
    def set_mode(self, mode):
        
        self.mode = mode
        self.firepower = self._select(self._firepower)
        self.malfunction = self._select(self._malfunction)
    
    def _select(self, value):
        
        return value[self.mode] if isinstance(value, dict) else value
        
        

class Group:
    """ Group for server logics"""
    
    def __init__(self, group_id, label, owner):
        # Attribute
        self.id = group_id
        self.label = label
        self.owner = owner
        self.range = 0
        self.fp = [0, 0, 0, 0, 0, 0]
        self.moving = None
        self.terrain = None
        self.wire = False
        self.smoke = False
        self.has_acted = False
        self.last_action = None

        
        
class Client:
    
    def __init__(self, socket, name, nation, side, ready):
        
        # Identity
        self.socket = socket
        self.name = name
        self.nation = nation
        self.side = side
        self.ready = ready
        self.has_acted = False
        self.discard_count = 0
        


class GameServer:
    
    def __init__(self):
        
        # Game variables
        self.game_phase = "assignment"
        self.game_subphase = None
        self.broadcast_timer = 0.0
        self.client_list = []
        self.current_turn = None
        self.current_sound = None
        self.action_deck_counter = 0
        self.draw_counter = 0
        
        # Pending action
        self.pending_action = {"type": None, "card": None, "strength": None,
                               "offensive_group": None, "defensive_group": None}
        
        # List with all the cards
        self.card_list = []
        
        # List with all the unit cards
        self.unit_list = []
        
        # List with all the groups
        self.group_list = []
        
        # List with selected nations / sides
        self.nation_list = []
        self.side_list = []
        
        # Card table
        self.card_table = pd.read_csv("assets/cards/card_table.csv", sep=",")
        self.card_table.set_index("id", inplace=True)
        
        # Unit table
        df = pd.read_csv("assets/units/unit_table.csv", sep=",")
        self.unit_table = df.map(self.parse_cell)
        self.unit_table.set_index("id", inplace=True)
        
        # Thread lock (to avoid race conditions)
        self.lock = threading.Lock()
        


    def start_server(self):
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

        # Set ip adress
        host = "0.0.0.0"
        
        # Set port (user input)
        port_input = input("Enter port (press Enter for default 52000): ").strip()
        port = 52000 if not port_input else int(port_input)
        
        s.bind((host, port))
        s.listen(5)
        s.settimeout(5.0)
        
        print(f'Server runs on {host}:{port}')
        
        # Start update loop in seperate thread
        threading.Thread(target=self.update_loop, daemon=True).start()

        try:
            while True:
                try:
                    c, addr = s.accept()
                    data = c.recv(1024)
                    player_data = pickle.loads(data)
                    player_name = player_data.get("player_name")
                    player_nation = player_data.get("player_nation")
                    print(f"Connection accepted from {addr} with username {player_name}")
                    
                    with self.lock:
                        
                        # Decline if table is full
                        if len(self.client_list) == FULL_TABLE:
                            continue
                        
                        # Decline if nation if already taken
                        if player_nation not in NATIONS or player_nation in self.nation_list:
                            player_nation = next(nation for nation in NATIONS if nation not in self.nation_list)
                            
                        # Add nation to list
                        self.nation_list.append(player_nation)
                        
                        # Allocate side
                        player_side = next(side for side in SIDES if side not in self.side_list)
                        
                        # Add side to list
                        self.side_list.append(player_side)
                    
                        # Add to client list
                        client = Client(c, player_name, player_nation, player_side, False)
                        self.client_list.append(client)

                    
                    # Set sound to none
                    self.current_sound = None
                    
                    # Send board state
                    self.broadcast()
                    
                    # Starte a new thread for each client
                    client_thread = threading.Thread(target=self.handle_client, args=(c, player_name), daemon=True)
                    client_thread.start()
                except:
                    pass
        except KeyboardInterrupt:
            print('Server stopping...')
        finally:
            s.close()
            print('Server closed')



    def update_loop(self):
        
        # Init reference time
        last_time = time.time()
        
        while True:
            
            # Calcualte delta time
            now = time.time()
            delta_time = now - last_time
            last_time = now
    
            # Call update function
            self.on_update(delta_time)
    
            # 60 FPS-Update-Loop
            time.sleep(1/FPS)  
            
            
            
    def on_update(self, delta_time):
        
        # Send heartbeat
        self.broadcast_timer += delta_time
        if self.broadcast_timer > 2.0:
            self.broadcast_timer = 0.0
            self.send_heartbeat()
        
        # Check if required number of players are on server
        if len(self.client_list) < FULL_TABLE:
            return
        
        # Call respective game phase logic
        with self.lock:
            if self.game_phase == "assignment":
                self.assignment_logic()
            elif self.game_phase == "setup":
                self.setup_logic()
            elif self.game_phase == "gameplay":
                self.gameplay_logic()
            
            
            
    def send_heartbeat(self):

        for client in list(self.client_list):
            try:
                client.socket.sendall(pickle.dumps({"type": "ping"}))
            except Exception:
                print(f"Heartbeat failed for {client.name}")
                self.remove_client(client.name)
            
            
            
    def assignment_logic(self):
        
        # missing
        
        self.game_phase = "setup"
        
        
    
    def setup_logic(self):
        
        # Create every card
        for i in range(162):
            card_id = f"ac{i+1:02d}"
            row = self.card_table.loc[card_id]
            card = Card(card_id, row["type"], row["subtype"], row["rnc"], row["breeze"], row["color"])
            self.card_list.append(card)
            
        # Create every unit
        for unit_id in self.unit_table.index:
            row = self.unit_table.loc[unit_id]
            if row["nation"] not in self.nation_list:
                continue
            unit = Unit(unit_id, row["nation"], row["rank"], row["name"], row["weapon"], 
                        row["malfunction"], row["ccv"], row["firepower"], row["morale"], 
                        row["panic"], row["rout"], row["kia"], row["points"])
            self.unit_list.append(unit)

        # Create every group
        for client in self.client_list:
            for label in ["A", "B", "C", "D"]:
                group_id = label + client.side
                owner = client.name
                group = Group(group_id, label, owner)
                self.group_list.append(group)
        
        # Set first turn
        first_client = random.choice(self.client_list)
        self.current_turn = first_client.name
        
        # Shuffle cards
        self.shuffle_cards()   
        
        # Distribute cards
        for client in self.client_list:
            self.draw_cards(client)
            
        # Distribute units
        for client in self.client_list:
            for unit in self.unit_list:
                if unit.nation == client.nation:
                    unit.group = random.choice(["A", "B"]) + client.side
                    unit.owner = client.name
            
        # Start playing phase
        self.game_phase = "gameplay"
        self.game_subphase = "action" # action, discard
        self.broadcast()
    
    
    def gameplay_logic(self):
        
        # missing
        pass

                
                
    def handle_client(self, c, player_name):

        while True:
            
            try:
                # Receive data
                data = c.recv(1024)
                
                if data:
                    
                    # Reset sound
                    self.current_sound = None
                    
                    # Get client
                    client = next((client for client in self.client_list if client.name == player_name), None)
                    
                    # Process client action
                    action = pickle.loads(data)
                    with self.lock:
                        self.process_action(action, client)
                        self.broadcast()
                    
            except:
                pass



    def process_action(self, action, client):
        
        # Get action type
        action_type = action.get("type")

        # Play card action
        if action_type == "play_card":
            self.play_card(action, client)
            
        # End player's turn
        if action_type == "advance_turn":
            self.advance_turn(action, client)

            
            
    def play_card(self, action, client):
        
        # Check game phase
        if self.game_phase != "gameplay":
            return
        
        # Find card
        card_id = action.get("card_id")
        played_card = None
        for card in self.card_list:
            if card.id == card_id:
                played_card = card
                break
                    
        # Find groups
        group_ids = action.get("group_ids")
        target_groups = [None, None]
        for group in self.group_list:
            if group.id == group_ids[0]:
                target_groups[0] = group
            elif group.id == group_ids[1]:
                target_groups[1] = group
                
        # Find units
        unit_ids = action.get("unit_ids")
        target_units = []
        for unit in self.unit_list:
            if unit.id in unit_ids:
                target_units.append(unit)
                    
        # Card not found
        if played_card is None:
            return
            
        # Check if card is in player's hand
        if played_card.owner != client.name or played_card.location != "hand":
            return
        
        # Get card mode
        card_mode = action.get("card_mode")
        
        # Resolve card
        if self.pending_action["type"] is not None:
            self.counter_card(played_card, target_groups, client)
        elif self.game_subphase == "action":
            self.execute_card(played_card, card_mode, target_groups, target_units, client)
        else:
            self.discard_card(played_card, card_mode, target_groups, client)
        
 
    
    def execute_card(self, played_card, card_mode, target_groups, target_units, client):
        
        # Check if it's this player's turn
        if client.name != self.current_turn:
            return
        
        # Check if group has already acted
        if target_groups[0].has_acted:
            return
        
        # Resolve actions
        if played_card.type == "movement":
            success = self.resolve_movement(target_groups[0], played_card, card_mode)
        elif played_card.type == "terrain":
            success = self.resolve_terrain(target_groups[0], played_card)
        elif played_card.type == "smoke":
            success = self.resolve_smoke(target_groups[0], played_card)
        elif played_card.type == "rally":
            success = self.resolve_rally(target_groups[0], target_units, played_card)
        elif played_card.type == "hero":
            success = self.resolve_hero(target_units, played_card)
        elif played_card.type == "fire":
            success = self.prepare_fire(target_groups, played_card)
        else:
            success = False
            
        # Check if card was resolved successfully
        if not success:
            return
            
        # Add card to the group (if not already discarded)
        if played_card.location == "hand":
            played_card.location = "table"
            played_card.group = target_groups[0].id
        
        # Fill history
        target_groups[0].last_action = ACTIONS[played_card.type]
        
        # Set flag
        if played_card.type != "hero":
            client.has_acted = True
            target_groups[0].has_acted = True
        
        # Set sound
        self.current_sound = "play_card"
    
    
            
    def resolve_movement(self, target_group, played_card, card_mode):
        
        # No movement with pinned units
        if any(unit.state == "pinned" and unit.group == target_group.id for unit in self.unit_list):
            return False
        
        # Get wire card (if present):
        wire = next((card for card in self.card_list if card.type == "wire" and card.group == target_group.id), None)

        # Remove wire (if present and no pinned men)
        if wire:
            self.move_card_to_discard(wire)
            self.move_card_to_discard(played_card)
            target_group.wire = False
            return True
            
        # Remove any terrain card if group is already moving
        if target_group.moving:
            for card in self.card_list:
                if card.group == target_group.id and card.type == "terrain":
                    self.move_card_to_discard(card)
        
        # Modify group attributes
        if card_mode == "forward":
            target_group.range += 1
        elif card_mode == "backward":
            target_group.range -= 1
        target_group.moving = card_mode
    
        # Set stack count
        played_card.stack_index = sum(1 for card in self.card_list 
                                      if card.group == target_group.id 
                                      and card.type in ["movement", "terrain"])
        
        return True
        
        
    def resolve_terrain(self, target_group, played_card):
        
        # Modify group attributes
        target_group.terrain = played_card.subtype
        target_group.moving = None

        # Remove movement/smoke cards from the group (if necessary)
        for card in self.card_list:
            if card.group == target_group.id and card.type in ["movement", "smoke"]:
                self.move_card_to_discard(card)
    
        return True



    def resolve_smoke(self, target_group, played_card):
        
        if target_group.smoke:
            return
        
        # Modify group attributes
        target_group.smoke = True
        
        # Set stack count
        played_card.stack_index = sum(1 for card in self.card_list 
                                      if card.group == target_group.id 
                                      and card.type in ["movement", "terrain"])
        
        return True
    

    
    def resolve_rally(self, target_group, target_units, played_card):
        
        # Restrict selected units to target group
        target_units = [unit for unit in target_units if unit.group == target_group.id]
        
        # Maximum rally capacity
        if played_card.subtype == "rally all":
            max_capacity = 10
        else:
            max_capacity = int(played_card.subtype.split()[1])  
            
        # Pinned unit in that group
        pinned = [unit for unit in self.unit_list
              if unit.group == target_group.id and unit.state == "pinned"]
        
        # Validity check: At least 1 pinned unit required
        if not pinned:
            return
        
        # Validity check: Capacity must be used fully
        if len(target_units) != min(max_capacity, len(pinned)):
            return
        
        # Validity check: Selected units must rallyable
        for unit in target_units:
            if unit.group != target_group.id or unit.state != "pinned":
                return
        
        for unit in target_units:
            unit.state = "rallied"
        
        return True
    
    
    
    def resolve_hero(self, target_units, played_card):
        
        # Validity check (1)
        if len(target_units) != 1:
            return
        
        # Validity check (2)
        if target_units[0].owner != self.current_turn:
            return
        
        # Modify attributes
        target_units[0].state = "rallied"
        target_units[0].heroic = True
        
        return True
        
        
            
    def prepare_fire(self, target_groups, played_card):
        
        # Get fire attributes
        card_firestrength, card_firepower = [int(n) for n in re.findall(r"\d+", played_card.subtype)]
        
        # Player units
        player_units = [unit for unit in self.unit_list if unit.group == target_groups[0].id]
        
        # Relative range
        total = target_groups[0].range + target_groups[1].range
        relative_range = min(total, 10-total)
        
        # Relative range: Deduction for lateral distance
        lateral_gap = abs(ord(target_groups[0].id[0]) - ord(target_groups[1].id[0]))
        if lateral_gap >= 2 and relative_range > 0:
            relative_range -= 1
            
        # Relative range cannot < 0 for firepower / to hit purposes
        relative_range = max(relative_range, 0)
        
        # Check firepower
        firepower = sum(unit.firepower[relative_range] * (unit.heroic+1) for unit in player_units if unit.state == "rallied")
        if firepower < card_firepower:
            return
        
        # Calculate firestrength
        modified_firestrength = self.modify_base_firestrength(card_firestrength, target_groups[0], target_groups[1], relative_range)
        if modified_firestrength is None:
            return
        
        # Set pending action
        self.pending_action["type"] = "fire"
        self.pending_action["card"] = played_card
        self.pending_action["strength"] = modified_firestrength
        self.pending_action["offensive_group"] = target_groups[0]
        self.pending_action["defensive_group"] = target_groups[1]
        
        # Annotate target information
        target_groups[1].last_action = "targeted"
        
        return True
    
    
    
    def counter_card(self, played_card, target_groups, client):
        
        # Validity check (1)
        if client.name == self.current_turn:
            return
        
        # Validity check (2)
        if played_card.type != "concealed":
            return
        
        # Validity check (3)
        if target_groups[0] != self.pending_action["defensive_group"]:
            return
    
        # Resolve counter
        if self.pending_action["type"] == "fire":
            self.resolve_fire(played_card)
        
        # Add card to the group
        played_card.location = "table"
        played_card.group = target_groups[0].id
            

    
    def resolve_fire(self, concealed_card):
        
        # Get base firestrength
        base_firestrength = self.pending_action["strength"] 
        
        # Get concealed firestrength
        concealed_firestrength = int(concealed_card.subtype.split()[-1]) if concealed_card else 0
        
        # Defensive units
        defensive_units = [unit for unit in self.unit_list if unit.group == self.pending_action["defensive_group"].id]
        
        # Attack defensive units
        for unit in defensive_units:
            attack = base_firestrength - concealed_firestrength + self.draw_rnc()
            
            if unit.state == "rallied":
                if attack >= unit.kia[0]:
                    unit.state = "kia"
                elif attack >= unit.morale:
                    unit.state = "pinned"
            
            elif unit.state == "pinned":
                if attack >= unit.kia[1]:
                    unit.state = "kia"
                elif attack >= unit.panic:
                    unit.state = "routed"

            if unit.state in ["routed", "kia"]:
                unit.group = None
                
        # Reset pending action
        for key in self.pending_action:
            self.pending_action[key] = None
            
        # Reset target information
        self.pending_action["defensive_group"].last_action = None
                
            
            
    def advance_turn(self, action, client):
        
        # Check game phase
        if self.game_phase != "gameplay":
            return
                
        # Check turn
        if client.name != self.current_turn:
            if self.pending_action["type"] == "fire":
                self.resolve_fire(None)
            return
        
        # Check pending actions
        if self.pending_action["type"] is not None:
            return
                
        # Advance turn
        if self.game_subphase == "action":
            self.game_subphase = "discard"
        else:
            self.game_subphase = "action"
            
        # Check if player has discarded
        if self.game_subphase == "discard":
            return
            
        # Refill player's hand
        self.draw_cards(client)
        
        # Remove action cards on table
        for card in self.card_list:
            if card.location == "table" and card.type not in ["movement", "terrain", "wire", "smoke"]:
                self.move_card_to_discard(card)
        
        # Reset groups
        for group in self.group_list:
            group.has_acted = False
            group.last_action = None
            
        # Reset units
        for unit in self.unit_list:
            unit.heroic = False
        
        # Reset client
        client.has_acted = False
        client.discard_count = 0
        
        # End turn
        i = (self.client_list.index(client) + 1) % len(self.client_list)
        self.current_turn = self.client_list[i].name
        
        

    def remove_client(self, player_name):
        """Removes client from game"""
        
        # Remove from client list
        client = next((client for client in self.client_list if client.name == player_name), None)
        self.client_list.remove(client)
        self.nation_list.remove(client.nation)
        self.side_list.remove(client.side)
        
        # Close socket
        try:
            client.socket.shutdown(socket.SHUT_RDWR)
        except Exception:
            pass
        finally:
            client.socket.close()
            
        print(f"Client {player_name} was removed from the game")
        
        

    def broadcast(self):
        """Send game state to all connected clients"""
        
        for client in self.client_list:
            
            # Create a personalized game state for this player
            game_state = {
                "cards": [],
                "units": [],
                "groups": [],
                "game_phase": self.game_phase,
                "game_subphase": self.game_subphase,
                "current_turn": self.current_turn,
                "sound": self.current_sound,
                "side": client.side,
                "pending_action": True if self.pending_action["type"] else False
            }
            
            # Add card information
            for card in self.card_list:
                card_info = {
                    "card_id": card.id,
                    "owner": "player" if client.name == card.owner else "opponent",
                    "location": card.location,
                    "group": card.group,
                    "stack_index": card.stack_index,
                    "draw_index": card.draw_index
                }
                game_state["cards"].append(card_info)
                
            # Add unit information
            for unit in self.unit_list:
                unit_info = {
                    "unit_id": unit.id,
                    "owner": "player" if client.name == unit.owner else "opponent",
                    "group": unit.group,
                    "state": unit.state,
                }
                game_state["units"].append(unit_info)
                
            # Add group information
            for group in self.group_list:
                group_info = {
                    "group_id": group.id,
                    "owner": "player" if client.name == group.owner else "opponent",
                    "range": group.range,
                    "moving": group.moving,
                    "terrain": group.terrain,
                    "last_action": group.last_action
                }
                game_state["groups"].append(group_info)
            
            # Send game state to client
            try:
                size = pickle.dumps(game_state)
                print(f"Sending game state ({len(size)} bytes)")
                client.socket.sendall(pickle.dumps(game_state))
            except Exception:
                print(f"Error sending to {client.name}")
                self.remove_client(client.name)
                
                
                
    def shuffle_cards(self):
        
        # Indicies of all cards in action deck and discard pile
        indices = [i for i, card in enumerate(self.card_list) 
                   if card.location in ("deck", "discard")]
        
        # Extract and shuffle these cards
        cards_to_shuffle = [self.card_list[i] for i in indices]
        random.shuffle(cards_to_shuffle)
        
        # Re-insert shuffled cards
        for i, card in zip(indices, cards_to_shuffle):
            self.card_list[i] = card
            card.location = "deck"
        
        # Increase action deck counter
        self.action_deck_counter += 1
        
        
        
    def draw_cards(self, client):
        
        # Get hand size maximum for this nation
        max_hand = MAX_HAND[client.nation]
        
        # Get cards in action deck
        deck = [card for card in self.card_list if card.location == "deck"]
        
        # Get cards in player's hand
        hand = [card for card in self.card_list if card.location == "hand" and card.owner == client.name]
        
        # Get number of cards to draw
        n_cards = max(max_hand - len(hand), 0)
        
        for _ in range(n_cards):
    
            # Reshuffle if necessary
            if len(deck) == 0:
                self.shuffle_cards()
                deck = [card for card in self.card_list if card.location == "deck"]
                            
            # Draw top card
            card = deck.pop()
            card.location = "hand"
            card.owner = client.name
            
            # Index card
            self.draw_counter += 1
            card.draw_index = self.draw_counter
            
            
            
    def discard_card(self, played_card, card_mode, target_groups, client):
        
        # Check if it's this player's turn
        if client.name != self.current_turn:
            return
        
        # Get discard maximum for this nation
        max_discard = MAX_DISCARD[client.nation] - client.discard_count
        
        # Check if discard is legal (1)
        if max_discard < 1:
            return
        
        # Check if discard is legal (2)
        if client.has_acted and client.nation != "german":
            return
                
        # Discard card
        if played_card.type == "sniper":
            success = self.resolve_sniper(played_card, target_groups[1])
        elif played_card.type == "wire":
            success = self.resolve_wire(played_card, target_groups[1])
        else:
            self.move_card_to_discard(played_card)
            success = True
            
        # Check if card was resolved successfully
        if not success:
            return
            
        # Update discard count
        client.discard_count += 1
        
        # Add card to the group (if discarded on group)
        if played_card.location != "discard":
            played_card.location = "table"
            played_card.group = target_groups[1].id
            played_card.owner = target_groups[1].owner 
        
        # Set sound
        self.current_sound = "play_card"
        
        
    
    def resolve_sniper(self, played_card, target_group):
        
        thresholds = [5, 3] # replace
        
        # Get units in target group
        units = [unit for unit in self.unit_list if unit.group == target_group.id]
        if not units:
            return False
        
        # Select unit by RPC
        unit = random.choice(units)  # TODO: RPC
        
        # Random number check
        rnc = abs(self.draw_rnc())
        
        # Set attributes
        if rnc >=thresholds[0]:
            unit.state = "kia"
            unit.group = None
        elif rnc > thresholds[1]:
            unit.state = "pinned"
        
        return True
        
    
    
    def resolve_wire(self, played_card, target_group):
        
        if target_group.wire:
            return
        
        if target_group.terrain in ["marsh", "pillbox"]:
            return
        
        if target_group.terrain == "stream" and target_group.moving == False:
            return
        
        target_group.wire = True
            
        return True
        
    
            
    def draw_rnc(self):
        
        # Get cards in action deck
        deck = [card for card in self.card_list if card.location == "deck"]
        
        # Reshuffle if necessary
        if len(deck) == 0:
            self.shuffle_cards()
            deck = [card for card in self.card_list if card.location == "deck"]
        
        # Draw top card
        rnc_card = deck.pop()
        rnc_card.location = "discard"
        
        # Check for breeze
        if rnc_card.breeze:
            for card in self.card_list:
                if card.type == "smoke" and card.location == "table":
                    self.move_card_to_discard(card)
            for group in self.group_list:
                group.smoke = 0
        
        return(rnc_card.rnc)
    
    
    
    def modify_base_firestrength(self, firestrength, source_group, target_group, relative_range):
        
        # TODO: Mortar/Ordnance fire implementation
        # TODO: encirclement check
        
        # No fire from gully
        if source_group.terrain == "gully":
            return None
        
        # No fire against gully
        if target_group.terrain == "gully" and source_group.terrain != "hill" and relative_range != 5:
            return None
        
        # Movement modifier
        if source_group.moving:
            firestrength //= 2
        if target_group.moving:
            firestrength += 1
            
        # Terrain modifier (outgoing)
        firestrength += TERRAIN_MOD[source_group.terrain][0]
            
        # Terrain modifier (incoming)
        firestrength += TERRAIN_MOD[target_group.terrain][1]
        
        # Artificial terrain modifier (outgoing)
        firestrength += -source_group.wire - source_group.smoke
        
        # Artificial terrain modifier (incoming)
        firestrength += target_group.wire - target_group.smoke
        
        # Enhanced protection behind wall
        if target_group.terrain == "wall" and target_group.label == source_group.label:
            firestrength -= 1

        return(firestrength)
    
    
            
    def parse_cell(self, cell):
        
        # Transform to string
        cell = str(cell).strip()
        
        # Parse to values and lists
        if "/" in cell:
            crewed, uncrewed = (self.parse_cell(p) for p in cell.split("/"))
            return {"crewed": crewed, "uncrewed": uncrewed}
        elif "|" in cell:
            return [self.parse_cell(x) for x in cell.split("|")]
        else:
            return int(cell) if cell.lstrip("-").isdigit() else cell
        
        
        
    def move_card_to_discard(self, card):
        
        card.owner = None
        card.group = None
        card.stack_index = 0
        card.location = "discard"
        
        

# ──[ Main ]───────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    server = GameServer()
    server.start_server()


