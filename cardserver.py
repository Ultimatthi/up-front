"""
UpFront: Server
"""

import socket
import threading
import pickle
import time
import re
import random
import yaml
import pandas as pd
import traceback


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
    "buildings -2": (0,  -2),
    "buildings -3": (0,  -3),
    "hill":      (+1, -1),  # with conditions
    "marsh":     (-1, -1),
    "stream":    (-1,  0),
    "gully":     (0,  -2),  # with conditions
    "wall":      (0,  -2),  # with conditions
    "pillbox":   (0, - 4),
    "minefield": (0,   0)   # with conditions
}

# Cards treated as cower cards (subtypes)
COWER_CARDS = {
    "A": ["pillbox", "minefield"]
}

# Cards to remove from the game when first discarded or drawn as RNC (kind: count)
REMOVE_CARDS = {
    "A": {"buildings": 5}
}

TIME_LIMIT = 3

# Axis nations (French not treated as Vichy France)
AXIS = ["german", "japanese", "italian"]


# ──[ Classes ]────────────────────────────────────────────────────────────────

class Card:
    
    def __init__(self, card_id, card_type, card_subtype, rnc, breeze, color, rpn):

        self.id = card_id
        self.type = card_type
        self.subtype = card_subtype
        self.rnc = rnc
        self.breeze = breeze
        self.color = color

        # Random position numbers: index = group size, rpn[10] = 0r (printed 0 = 10)
        self.rpn = [None] + [10 if n == "0" else int(n) for n in rpn.split("|")]

        self.location = "deck" # deck, discard, void, hand, table
        self.group = None
        self.owner = None # player_name
        self.mode = None
        self.stack_index = 0
        self.draw_index = 0
        
        
        
class Unit:

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
        self.owner = None
        self.group = None
        self.slot = 0
        self.heroic = False
        
        # Attributes (crew related)
        self.crew_partner = None # unit id of crew partner
        self.crew_served = isinstance(firepower, dict) # True, False
        self._firepower = firepower
        self._malfunction = malfunction
        self.set_mode("uncrewed")
            
    def set_mode(self, mode): # crewed, uncrewed, assistant
        
        self.mode = mode
        self.firepower = self._select(self._firepower)
        self.malfunction = self._select(self._malfunction)
    
    def _select(self, value):
        
        return value[self.mode] if isinstance(value, dict) else value

    def get_firepower(self, group, relative_range):

        # Only rallied units fire
        if self.state != "rallied":
            return 0

        # Assistants forfeit their own firepower
        if self.mode == "assistant":
            return 0

        # Moving light machine guns: bracketed firepower, only when fully crewed
        if group.moving and self.weapon == "Light Machinegun":
            if self.mode != "crewed":
                return 0
            return self._firepower["uncrewed"][relative_range] * (self.heroic+1)

        # Base firepower (doubled for heroes)
        firepower = self.firepower[relative_range] * (self.heroic+1)

        # Moving fire: halve bolt-action rifles (rounded down)
        if group.moving and self.weapon == "Bolt-Action Rifle":
            firepower //= 2

        return firepower

        

class Group:
    
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
        self.acted = False
        self.leader = False
        self.empty = True
        self.last_action = None
        self.sniper_rnc = None
        
        
        
class Client:
    
    def __init__(self, socket, name, nation, side, unit_allocation, ready):
        
        # Identity
        self.socket = socket
        self.name = name
        self.nation = nation
        self.side = side
        self.unit_allocation = unit_allocation
        self.ready = ready
        self.acted = False
        self.discard_count = 0
        self.passed = False
        self.sniper_lost = False
        


class GameServer:
    
    def __init__(self):
        
        # Scenario
        self.scenario = "A" # TODO: introduce more scenarios
        
        # Game variables
        self.game_phase = "assignment"
        self.game_subphase = None
        self.broadcast_timer = 0.0
        self.client_list = []
        self.current_turn = None
        self.current_sound = None
        self.action_deck_counter = 0
        self.breeze = False # breeze drawn in current player turn
        self.draw_counter = 0
        self.winner = None
        
        # Pending action
        self.pending_action = {"type": None, "card": None, "strength": None,
                               "offensive_group": None, "defensive_group": None}
        
        # List with all the cards
        self.card_list = []
        
        # List with all the unit cards
        self.unit_list = []
        
        # List with all the groups
        self.group_list = []
        
        # Clients that left the game, kept for rejoining
        self.left_clients = {}

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
                    unit_allocation = player_data.get("unit_allocation")
                    print(f"Connection accepted from {addr} with username {player_name}")
                    
                    with self.lock:

                        # Same player connects again: drop the old connection first
                        if any(client.name == player_name for client in self.client_list):
                            self.remove_client(player_name)

                        # Decline if table is full
                        if len(self.client_list) == FULL_TABLE:
                            continue

                        # Decline new players once the game has started (rejoin only)
                        if self.game_phase != "assignment" and player_name not in self.left_clients:
                            continue

                        # Get nations and sides already taken
                        nations = [client.nation for client in self.client_list]
                        sides = [client.side for client in self.client_list]

                        # Decline if nation if already taken
                        if player_nation not in NATIONS or player_nation in nations:
                            player_nation = next(nation for nation in NATIONS if nation not in nations)

                        # Allocate side
                        player_side = next(side for side in SIDES if side not in sides)

                        # Create new client
                        client = Client(c, player_name, player_nation, player_side, unit_allocation, False)

                        # Rejoining player gets his old client back (nation, side and state)
                        if player_name in self.left_clients:
                            client = self.left_clients.pop(player_name)
                            client.socket = c

                        # Add to client list
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
            with self.lock:
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
            card = Card(card_id, row["type"], row["subtype"], row["rnc"], row["breeze"], row["color"], row["rpn"])
            self.card_list.append(card)
            
        # Create every unit
        nations = [client.nation for client in self.client_list]
        for unit_id in self.unit_table.index:
            row = self.unit_table.loc[unit_id]
            if row["nation"] not in nations:
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
        
        # Axis moves first (scenarios A and B), otherwise random
        axis = [client for client in self.client_list if client.nation in AXIS]
        first_client = random.choice(axis or self.client_list)
        self.current_turn = first_client.name
            
        # Distribute units
        scenario = "scenario " + self.scenario
        units = {unit.name: unit for unit in self.unit_list}
        for client in self.client_list:
            for group, names in client.unit_allocation[scenario][client.nation].items():
                for slot, name in enumerate(names or []):
                    units[name].group = group + client.side
                    units[name].owner = client.name
                    units[name].slot = slot
                    
        # Set empty groups
        for group in self.group_list:
            group.empty = not any(unit.group == group.id for unit in self.unit_list)
            
        # Shuffle cards
        self.shuffle_cards()   
        
        # Distribute cards
        for client in self.client_list:
            self.draw_cards(client)
            
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
                        self.process_aftermath()
                        self.broadcast()
                        
                else:
                    break

            except OSError:
                # Socket closed by server (client left or rejoined)
                break
            except Exception:
                traceback.print_exc()
                break



    def process_action(self, action, client):
        
        # Get action type
        action_type = action.get("type")

        # Play card action
        if action_type == "play_card":
            self.play_card(action, client)
            
        # End player's turn
        if action_type == "advance_turn":
            self.advance_turn(action, client)

        # Group action without card
        if action_type == "group_action":
            self.group_action(action, client)



    def group_action(self, action, client):

        # Check game phase
        if self.game_phase != "gameplay":
            return

        # Rejecting terrain is the opponent's decision
        if action.get("action") == "reject_terrain":
            self.reject_terrain(client)
            return

        # Check if it's this player's turn
        if client.name != self.current_turn or self.pending_action["type"] is not None:
            return

        # Find own active group
        target_group = next((group for group in self.group_list if group.id == action.get("group_ids")[0]), None)

        # Check if group exists
        if target_group is None or target_group.empty:
            return

        # Get targeted units
        target_units = action.get("unit_ids")

        # Voluntary panic is no action (any subphase, also after an action)
        if action.get("action") == "voluntary_panic":
            self.resolve_voluntary_panic(target_group, target_units)
            return

        # Check if group can act
        if self.game_subphase != "action" or target_group.acted:
            return

        # Resolve action
        if action.get("action") == "sniper_check":
            success = self.resolve_sniper_check(target_group)
        elif action.get("action") == "crew":
            success = self.resolve_crew(target_group, target_units)
        else:
            success = False

        # Check if action was resolved successfully
        if not success:
            return

        # Set flags
        target_group.acted = True
        client.acted = True

        # Set sound
        self.current_sound = "play_card"

            
            
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
        
        # Check if group is empty
        if target_groups[0].empty:
            return
        
        # Check if group has already acted
        if target_groups[0].acted and played_card.type != "hero":
            return
        
        # Resolve actions
        if played_card.type == "movement":
            success = self.resolve_movement(played_card, card_mode, target_groups[0])
        elif played_card.type == "terrain":
            success = self.resolve_terrain(played_card, target_groups[0])
        elif played_card.type == "smoke":
            success = self.resolve_smoke(played_card, target_groups[0])
        elif played_card.type == "rally":
            success = self.resolve_rally(played_card, target_groups[0], target_units)
        elif played_card.type == "hero":
            success = self.resolve_hero(played_card, target_units)
        elif played_card.type == "fire":
            success = self.prepare_fire(played_card, target_groups)
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
            client.acted = True
            target_groups[0].acted = True
        
        # Set sound
        self.current_sound = "play_card"
    
    
            
    def resolve_movement(self, played_card, card_mode, target_group):
        
        # No movement with pinned units
        if any(unit.state == "pinned" and unit.group == target_group.id for unit in self.unit_list):
            return False
        
        # Get wire card (if present):
        wire = next((card for card in self.card_list if card.type == "wire" and card.group == target_group.id), None)

        # Remove wire (if present and no pinned units)
        if wire:
            self.move_card_to_discard(wire)
            self.move_card_to_discard(played_card)
            target_group.wire = False
            return True

        # Get enemy groups still in play
        enemy_groups = [group for group in self.group_list if group.owner != target_group.owner and not group.empty]

        # Check retreat I: relative range to closest enemy group must not drop below 0
        closest_range = max(self.get_relative_range([target_group, enemy]) for enemy in enemy_groups)
        if card_mode == "backward" and closest_range <= 0:
            return False

        # Check retreat II: at range number 0 or less only with red RNC
        if card_mode == "backward" and target_group.range <= 0 and played_card.color != "red":
            return False

        # Check blocking: relative range to opposite group must not exceed 5
        opposite = next((group for group in enemy_groups if group.label == target_group.label), None)
        if card_mode == "forward" and opposite and target_group.range + 1 + opposite.range > 5:
            return False

        # Second movement card: group leaves its terrain
        if target_group.moving:
            target_group.terrain = None
        
        # Modify group attributes
        if card_mode == "forward":
            target_group.range += 1
        elif card_mode == "backward":
            target_group.range -= 1
        target_group.moving = card_mode
        played_card.mode = card_mode

        # Set stack count
        played_card.stack_index = sum(1 for card in self.card_list
                                      if card.group == target_group.id
                                      and card.type in ["movement", "terrain"])

        # Get smoke card (if present)
        smoke = next((card for card in self.card_list if card.type == "smoke" and card.group == target_group.id), None)

        # Second movement card on top of smoke removes it (smoke lies below played card)
        if smoke and smoke.stack_index < played_card.stack_index:
            self.move_card_to_discard(smoke)
            target_group.smoke = False

        return True
        
        
    def check_terrain_entry(self, played_card, target_group):

        # Terrain can only be entered by a moving group
        if not target_group.moving:
            return False

        # Terrain types without implemented rules cannot be played
        if played_card.subtype not in TERRAIN_MOD:
            return False

        # Cower cards of the scenario cannot be played
        if played_card.subtype in COWER_CARDS.get(self.scenario, []):
            return False

        # Cards to be removed by the scenario are cower cards until then
        if self.check_card_removal(played_card):
            return False

        # No terrain on wire (remove wire with movement card first)
        if target_group.wire:
            return False

        # No new terrain on marsh before two movement cards
        if target_group.terrain == "marsh":
            return False

        return True



    def check_card_removal(self, card):

        # Scenario removes the first cards of this kind from the game
        remove_cards = REMOVE_CARDS.get(self.scenario, {})
        kind = card.subtype.split()[0]
        if kind not in remove_cards:
            return False
        removed = [card for card in self.card_list
                   if card.location == "void" and card.subtype.split()[0] == kind]
        return len(removed) < remove_cards[kind]



    def resolve_terrain(self, played_card, target_group):

        # Check if group can enter terrain
        if not self.check_terrain_entry(played_card, target_group):
            return False

        # Modify group attributes
        target_group.terrain = played_card.subtype
        target_group.moving = None
        target_group.smoke = False

        # Remove all cards beneath the new terrain card
        for card in self.card_list:
            if card is not played_card and card.group == target_group.id and card.type in ["movement", "smoke", "terrain"]:
                self.move_card_to_discard(card)

        # Terrain card lies at the bottom of the stack
        played_card.stack_index = 0
    
        return True



    def offer_terrain(self, played_card, target_group):

        # Check if target group is empty
        if target_group.empty:
            return

        # Check if enemy group can enter terrain
        if not self.check_terrain_entry(played_card, target_group):
            return

        # Stream cannot be rejected
        if played_card.subtype == "stream":
            return self.resolve_terrain(played_card, target_group)

        # Place terrain on top of the stack
        played_card.stack_index = sum(1 for card in self.card_list
                                      if card.group == target_group.id
                                      and card.type in ["movement", "terrain"])

        # Set pending action
        self.pending_action["type"] = "terrain"
        self.pending_action["card"] = played_card
        self.pending_action["defensive_group"] = target_group

        # Annotate target information
        target_group.last_action = "enter?"

        return True



    def accept_terrain(self):

        # Enter terrain (card already lies on the group)
        self.resolve_terrain(self.pending_action["card"], self.pending_action["defensive_group"])

        # Annotate target information
        self.pending_action["defensive_group"].last_action = "entered"

        # Reset pending action
        for key in self.pending_action:
            self.pending_action[key] = None

        # Set sound
        self.current_sound = "play_card"



    def reject_terrain(self, client):

        # Only the opponent can reject
        if self.pending_action["type"] != "terrain" or client.name == self.current_turn:
            return

        # Get target group
        target_group = self.pending_action["defensive_group"]

        # Discard terrain card
        self.move_card_to_discard(self.pending_action["card"])

        # Get cards of target group
        group_cards = [card for card in self.card_list if card.group == target_group.id]

        # Get movement cards (top card last) and terrain card
        movements = [card for card in group_cards if card.type == "movement"]
        movements.sort(key=lambda card: card.stack_index)
        terrain = next((card for card in group_cards if card.type == "terrain"), None)

        # Sideways movement is discarded, advance or retreat turns sideways
        if movements[-1].mode == "sideways":
            self.move_card_to_discard(movements.pop())
        else:
            target_group.range += -1 if movements[-1].mode == "forward" else 1
            movements[-1].mode = "sideways"

        # Group keeps moving with the top remaining movement card
        target_group.moving = movements[-1].mode if movements else None

        # Group is (again) in its terrain with less than two movement cards
        if terrain and len(movements) < 2:
            target_group.terrain = terrain.subtype

        # Annotate target information
        target_group.last_action = "rejected"

        # Reset pending action
        for key in self.pending_action:
            self.pending_action[key] = None

        # Set sound
        self.current_sound = "play_card"



    def resolve_smoke(self, played_card, target_group):
        
        if target_group.leader is False:
            return
        
        if target_group.smoke:
            return

        # No smoke in marsh
        if target_group.terrain == "marsh":
            return

        # No smoke in a player turn with breeze
        if self.breeze:
            return

        # Modify group attributes
        target_group.smoke = True
        
        # Set stack count
        played_card.stack_index = sum(1 for card in self.card_list 
                                      if card.group == target_group.id 
                                      and card.type in ["movement", "terrain"])
        
        return True
    

    
    def resolve_rally(self, played_card, target_group, target_units):
        
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
    
    
    
    def resolve_hero(self, played_card, target_units):
        
        # Validity check (1): At least one unit
        if len(target_units) != 1:
            return
        
        # Validity check (2): Only units owned by player
        if target_units[0].owner != self.current_turn:
            return

        # Validity check (3): Only units still in play
        if target_units[0].state not in ("rallied", "pinned") or target_units[0].group is None:
            return

        # Modify attributes
        target_units[0].state = "rallied"
        target_units[0].heroic = True
        
        return True



    def get_relative_range(self, target_groups):

        # Relative range
        total = target_groups[0].range + target_groups[1].range
        relative_range = min(total, 10-total)

        # Relative range: Deduction for lateral distance
        lateral_gap = abs(ord(target_groups[0].id[0]) - ord(target_groups[1].id[0]))
        if lateral_gap >= 2 and relative_range > 0:
            relative_range -= 1

        return relative_range



    def prepare_fire(self, played_card, target_groups):
        
        # Get fire attributes
        card_firestrength, card_firepower = [int(n) for n in re.findall(r"\d+", played_card.subtype)]
        
        # Player units
        player_units = [unit for unit in self.unit_list if unit.group == target_groups[0].id]
        
        # Relative range
        relative_range = self.get_relative_range(target_groups)

        # Relative range cannot < 0 for firepower / to hit purposes
        relative_range = max(relative_range, 0)
        
        # Check firepower
        firepower = sum(unit.get_firepower(target_groups[0], relative_range) for unit in player_units)
        if firepower < card_firepower:
            return
        
        # Calculate firestrength
        firestrength = self.get_firestrength(card_firestrength, target_groups[0], target_groups[1], relative_range)
        if firestrength is None:
            return
        
        # Set pending action
        self.pending_action["type"] = "fire"
        self.pending_action["card"] = played_card
        self.pending_action["strength"] = firestrength
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

        # Validity check (4)
        if self.pending_action["type"] != "fire":
            return
    
        # Resolve counter
        self.resolve_fire(played_card)
        
        # Add card to the group
        played_card.location = "table"
        played_card.group = target_groups[0].id
            

    
    def resolve_fire(self, concealed_card):
        
        # Get firestrength
        firestrength = self.pending_action["strength"] 
        
        # Get concealed firestrength
        concealed_firestrength = int(concealed_card.subtype.split()[-1]) if concealed_card else 0
        
        # Defensive units
        defensive_units = [unit for unit in self.unit_list if unit.group == self.pending_action["defensive_group"].id]

        # Sort defensive units by position within the group
        defensive_units.sort(key=lambda unit: unit.slot)

        # Attack defensive units
        for unit in defensive_units:
            rnc_card = self.draw_rnc_card()
            attack = firestrength + concealed_firestrength + rnc_card.rnc
            
            if unit.state == "rallied":
                if attack >= unit.kia[0]:
                    unit.state = "kia"
                elif attack >= unit.morale:
                    unit.state = "pinned"
            
            elif unit.state == "pinned":
                if attack >= unit.kia[1]:
                    unit.state = "kia"
                elif attack >= unit.panic:
                    # Panic: KIA if 0r does not exceed rout value, otherwise rout
                    unit.state = "kia" if rnc_card.rpn[10] <= unit.rout else "routed"

            if unit.state in ["routed", "kia"]:
                unit.group = None

        # Reset pending action
        for key in self.pending_action:
            self.pending_action[key] = None
                
            
            
    def advance_turn(self, action, client):
        
        # Check game phase
        if self.game_phase != "gameplay":
            return
                
        # Check turn
        if client.name != self.current_turn:
            if self.pending_action["type"] == "fire":
                self.resolve_fire(None)
            elif self.pending_action["type"] == "terrain":
                self.accept_terrain()
            return
        
        # Check pending actions
        if self.pending_action["type"] is not None:
            return
        
        # Check if player is passing
        client.passed = not client.acted and client.discard_count == 0

        # Get opponent
        opponent = next(c for c in self.client_list if c is not client)

        # Check if passing is allowed
        if self.game_subphase == "discard" and client.passed and opponent.passed:
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
            group.acted = False
            group.last_action = None
            if group.owner == client.name:
                group.sniper_rnc = None

        # Reset units
        for unit in self.unit_list:
            unit.heroic = False
        
        # Reset client
        client.acted = False
        client.discard_count = 0

        # Reset breeze
        self.breeze = False
        
        # End turn
        i = (self.client_list.index(client) + 1) % len(self.client_list)
        self.current_turn = self.client_list[i].name
        
        

    def remove_client(self, player_name):
        
        # Remove from client list
        client = next((client for client in self.client_list if client.name == player_name), None)
        self.client_list.remove(client)

        # Keep client for rejoining
        self.left_clients[player_name] = client

        # Close socket
        try:
            client.socket.shutdown(socket.SHUT_RDWR)
        except Exception:
            pass
        finally:
            client.socket.close()
            
        print(f"Client {player_name} was removed from the game")
        
        

    def broadcast(self):
        
        for client in self.client_list:
            
            # Create a personalized game state for this player
            game_state = {
                "cards": [],
                "units": [],
                "groups": [],
                "game_phase": self.game_phase,
                "game_subphase": self.game_subphase,
                "current_turn": "player" if client.name == self.current_turn else "opponent",
                "sound": self.current_sound,
                "side": client.side,
                "pending_action": self.pending_action["type"],
                "winner": "draw" if self.winner == "draw" else "player" if client.name == self.winner else "opponent"
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
                    "slot": unit.slot,
                    "state": unit.state,
                    "crew_partner": unit.crew_partner
                }
                game_state["units"].append(unit_info)
                
            # Add group information
            for group in self.group_list:
                group_info = {
                    "group_id": group.id,
                    "owner": "player" if client.name == group.owner else "opponent",
                    "empty": group.empty,
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
        
        # Get squad leader and assistant squad leader
        sl = next(unit for unit in self.unit_list if unit.owner == client.name and unit.rank == "SGT")
        asl = next(unit for unit in self.unit_list if unit.owner == client.name and unit.rank == "CPL")
        
        # Check for max hand size reduction
        if sl.state == "rallied":
            pass
        elif sl.state == "pinned":
            max_hand -= 1
        elif asl.state != "rallied":
            max_hand -= 1
            
        # Get enemy groups
        enemy_groups = [group for group in self.group_list if group.owner != client.name and not group.empty]
            
        # Check for max hand size increase (unbalanced position)
        if len(enemy_groups) < 2:
            max_hand += 1
        
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
        if client.acted and client.nation != "german":
            return
                
        # Discard card (on enemy group or discard pile)
        if card_mode == "enemy" and played_card.type == "sniper" and not client.sniper_lost:
            success = self.resolve_sniper(played_card, target_groups[1])
        elif card_mode == "enemy" and played_card.type == "wire":
            success = self.resolve_wire(played_card, target_groups[1])
        elif card_mode == "enemy" and played_card.type == "terrain":
            success = self.offer_terrain(played_card, target_groups[1])
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
        
        # Check if target group is empty
        if target_group.empty:
            return
        
        # KIA and PIN thresholds from card, e.g. "sniper (kia 5 pin 3)"
        kia, pin = [int(n) for n in re.findall(r"\d+", played_card.subtype)]
        
        # Get units in target group
        units = [unit for unit in self.unit_list if unit.group == target_group.id]
        if not units:
            return False

        # Sort units by position within the group
        units.sort(key=lambda unit: unit.slot)

        # Select unit by RPC
        unit = random.choice(units)  # TODO: RPC
        
        # Random number check
        rnc_card = self.draw_rnc_card()
        rnc = abs(rnc_card.rnc)

        # Remember lowest sniper RNC for sniper check
        if target_group.sniper_rnc is None or rnc < target_group.sniper_rnc:
            target_group.sniper_rnc = rnc

        # Set attributes
        if rnc >= kia:
            unit.state = "kia"
            unit.group = None
        elif rnc >= pin and unit.state == "pinned":
            # Panic: KIA if 0r does not exceed rout value, otherwise rout
            unit.state = "kia" if rnc_card.rpn[10] <= unit.rout else "routed"
            unit.group = None
        elif rnc >= pin:
            unit.state = "pinned"

        return True



    def resolve_sniper_check(self, target_group):

        # Group must have been sniped in the opponent's last turn
        if target_group.sniper_rnc is None:
            return False

        # Needs an unpinned unit
        if not any(unit.group == target_group.id and unit.state == "rallied" for unit in self.unit_list):
            return False

        # Black RNC higher than sniper RNC eliminates the opponent's sniper
        rnc_card = self.draw_rnc_card()
        if rnc_card.color == "black" and abs(rnc_card.rnc) > target_group.sniper_rnc:
            opponent = next(client for client in self.client_list if client.name != target_group.owner)
            opponent.sniper_lost = True
            target_group.last_action = "killed snpr"
        else:
            target_group.last_action = "checked snpr"

        # Only one check per sniper attack
        target_group.sniper_rnc = None

        return True



    def resolve_crew(self, target_group, unit_ids):

        # Get targeted units
        units = [unit for unit in self.unit_list if unit.id in unit_ids]

        # Check validity (1)
        if not all(unit.group == target_group.id for unit in units):
            return False

        # Check validity (2)
        if len(units) != 2 or any(unit.state != "rallied" for unit in units):
            return False

        # Uncrew: relieve the assistant of a crewed pair
        if units[0].crew_partner == units[1].id:
            for unit in units:
                unit.crew_partner = None
                unit.set_mode("uncrewed")
            target_group.last_action = "uncrewed"
            return True

        # Crew: exactly one crew-served weapon, neither unit already crew
        gunners = [unit for unit in units if unit.crew_served]
        if len(gunners) != 1 or any(unit.crew_partner for unit in units):
            return False
        gunner = gunners[0]
        assistant = next(unit for unit in units if unit is not gunner)
        gunner.crew_partner, assistant.crew_partner = assistant.id, gunner.id
        gunner.set_mode("crewed")
        assistant.set_mode("assistant")

        # Assistant is placed next to the weapon (gaps are closed in aftermath)
        assistant.slot = gunner.slot + 0.5

        target_group.last_action = "crewed"
        return True



    def resolve_voluntary_panic(self, target_group, unit_ids):

        # Selected pinned units of the group
        units = [unit for unit in self.unit_list if unit.id in unit_ids and unit.group == target_group.id and unit.state == "pinned"]

        # Every unit panics with its own RNC
        for unit in units:
            rnc_card = self.draw_rnc_card()
            # Panic: KIA if 0r does not exceed rout value, otherwise rout
            unit.state = "kia" if rnc_card.rpn[10] <= unit.rout else "routed"
            unit.group = None

        # Set sound
        if units:
            self.current_sound = "play_card"
        
    
    
    def resolve_wire(self, played_card, target_group):
        
        # Check if target group is empty
        if target_group.empty:
            return
        
        if target_group.wire:
            return
        
        if target_group.terrain in ["marsh", "pillbox"]:
            return
        
        if target_group.terrain == "stream" and not target_group.moving:
            return
        
        target_group.wire = True
            
        return True
        
    
            
    def draw_rnc_card(self):
        
        # Get cards in action deck
        deck = [card for card in self.card_list if card.location == "deck"]
        
        # Reshuffle if necessary
        if len(deck) == 0:
            self.shuffle_cards()
            deck = [card for card in self.card_list if card.location == "deck"]
        
        # Draw top card
        rnc_card = deck.pop()
        self.move_card_to_discard(rnc_card)
        
        # Check for breeze
        if rnc_card.breeze:
            self.breeze = True
            for card in self.card_list:
                if card.type == "smoke" and card.location == "table":
                    self.move_card_to_discard(card)
            for group in self.group_list:
                group.smoke = False
        
        return(rnc_card)
    
    
    
    def get_firestrength(self, firestrength, source_group, target_group, relative_range):
        
        # TODO: Mortar/Ordnance fire implementation
        # TODO: encirclement check
        
        # No fire from gully
        if source_group.terrain == "gully" and relative_range != 5:
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
        
        # Reduced protection behind wall against groups not directly opposite
        if target_group.terrain == "wall" and target_group.label != source_group.label:
            firestrength += 1

        # No elevated fire from hill against pillbox
        if source_group.terrain == "hill" and target_group.terrain == "pillbox":
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

        # Cards to be removed by the scenario go out of the game
        if self.check_card_removal(card):
            card.location = "void"
        
        
        
    def process_aftermath(self):
        
        for group in self.group_list:
    
            # Units in group
            units = [unit for unit in self.unit_list if unit.group == group.id]

            # Close gaps in positions after losses
            for slot, unit in enumerate(sorted(units, key=lambda unit: unit.slot)):
                unit.slot = slot

            # Get crew members
            crews = [unit for unit in units if unit.crew_partner]

            # Update crew members
            for unit in crews:
                partner = next((partner for partner in units if partner.id == unit.crew_partner), None)
                # Lost partner ends crew
                if partner is None:
                    unit.crew_partner = None
                    unit.set_mode("uncrewed")
                # Pinned assistant leaves the weapon uncrewed
                elif unit.mode != "assistant":
                    unit.set_mode("crewed" if partner.state == "rallied" else "uncrewed")

            # Group empty?
            group.empty = len(units) == 0
        
            # Group has active leader?
            group.leader = any(unit.rank in ("SGT", "CPL") and unit.state == "rallied" for unit in units)
  
            # Discard placed cards of empty group
            if group.empty:
                for card in self.card_list:
                    if card.group == group.id:
                        self.move_card_to_discard(card)

        self.check_victory()
        
        
        
    def check_victory(self):
        
        # Instant victory
        for client in self.client_list:
            opponent = next(c for c in self.client_list if c is not client)
            if self.check_scenario_condition(self.scenario, client) or self.check_broken_group(opponent):
                self.winner = client.name
                self.game_phase = "finished"
                return
        
        # Time limit victory
        if self.action_deck_counter > TIME_LIMIT:
            a, b = self.client_list
            pa, pb = self.calculate_victory_points(a), self.calculate_victory_points(b)
            self.winner = a.name if pa > pb else b.name if pb > pa else "draw"
            self.game_phase = "finished"

                
                
    def check_scenario_condition(self, scenario, client):
        
        # TODO: more scenarios
        
        count = 0
        
        if scenario == "A":

            for group in self.group_list:
                if group.owner != client.name:
                    continue
                if group.range < 4:
                    continue
                if group.moving:
                    continue
                # Terrain must reduce fire strength, wire counts against it, smoke doesn't help
                if TERRAIN_MOD[group.terrain][1] + group.wire >= 0:
                    continue
                count += sum(1 for unit in self.unit_list if unit.group == group.id and unit.state == "rallied")
    
            return count >= 4
        
        return False
            
    
    
    
    def check_broken_group(self, client):
        
        # Total units
        total_units = [unit for unit in self.unit_list if unit.owner == client.name]
        
        # Broken units
        broken_units = [unit for unit in total_units if unit.state not in ["rallied", "pinned"]]
        
        # Broken group
        return len(broken_units) / len(total_units) > 0.5
            
    
        
    def calculate_victory_points(self, client):
        
        # TODO: AFV, prisoners, wounded men
        
        points = 0
        
        # Victory points: range number x rallied units in stationary groups
        for group in self.group_list:
            if group.owner != client.name:
                continue
            if group.moving:
                continue
            points += group.range * sum(1 for unit in self.unit_list if unit.group == group.id and unit.state == "rallied")
                
         # Victory points for enemy casualties and routed units
        for unit in self.unit_list:
            if unit.owner == client.name:
                continue
            if unit.state == "kia":
                points += 2
            elif unit.state == "routed":
                points += 1
                
        return points
                
        

# ──[ Main ]───────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    server = GameServer()
    server.start_server()


