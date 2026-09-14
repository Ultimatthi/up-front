"""
UpFront: Server
"""

import socket
import threading
import pickle
import time
import random
import pandas as pd


# ──[ Parameter ]──────────────────────────────────────────────────────────────

FPS = 20
FULL_TABLE = 1


# ──[ Classes ]────────────────────────────────────────────────────────────────

class Card:
    """ Card for server logics """
    
    def __init__(self, card_id, rnc, color, card_type, card_subtype, owner, location, group_id):

        self.id = card_id
        self.rnc = rnc
        self.color = color
        self.type = card_type
        self.subtype = card_subtype
        self.owner = owner # player_name
        self.location = location # deck, discard, void, hand, table
        self.group_id = group_id
        
        
        
class Group:
    """ Group for server logics"""
    
    def __init__(self, group_id, label, owner):
        # Attribute
        self.id = group_id
        self.label = label
        self.owner = owner
        self.range = 0
        self.fp = [0, 0, 0, 0, 0, 0]
        self.moving = False
        self.terrain = None

        
        
class Client:
    
    def __init__(self, socket, name, nation, ready):
        
        # Identity
        self.socket = socket
        self.name = name
        self.nation = nation
        self.ready = ready
        


class GameServer:
    
    def __init__(self):
        
        # Game variables
        self.game_phase = "assignment"
        self.broadcast_timer = 0.0
        self.client_list = []
        self.current_turn = None
        self.current_sound = None
        self.action_deck_counter = 0
        
        # List with all the cards
        self.card_list = []
        
        # List with all the groups
        self.group_list = []
        
        # Tables
        self.card_table = pd.read_csv("assets/cards/card_table.txt", sep=";")
        self.card_table.set_index("id", inplace=True)
        
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
                    
                        # Add to client list
                        client = Client(c, player_name, player_nation, False)
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
        
        # Update time since last broadcast
        self.broadcast_timer += delta_time
        
        # Send heartbeat to all clients
        if self.broadcast_timer > 2.0:
            # Reset timer
            self.broadcast_timer = 0.0
            # Set sound to silent
            original_sound = self.current_sound
            self.current_sound = None
            # Send hearbeat
            self.broadcast()
            # Reset sound
            self.current_sound = original_sound
        
        # Check if required number of players are on server
        if len(self.client_list) < FULL_TABLE:
            return
        
        # Call respective game phase logic
        if self.game_phase == "assignment":
            self.assignment_logic()
        elif self.game_phase == "setup":
            self.setup_logic()
        elif self.game_phase == "gameplay":
            self.gameplay_logic()
            
            
            
    def assignment_logic(self):
        
        # missing
        
        self.game_phase = "setup"
        
        
    
    def setup_logic(self):
        
        # Create every card
        for i in range(19, 27):
            card_id = f"ac{i:02d}"
            row = self.card_table.loc[card_id]
            card = Card(card_id, row["rnc"], row["color"], row["type"],
                        row["subtype"], None, "deck", None)
            self.card_list.append(card)
            
        # Create every group
        for label in ["A", "B", "C", "D"]:
            for section in [0, 1]:
                group_id = label + str(section+1)
                owner = self.client_list[section].name if section < len(self.client_list) else "bot"
                group = Group(group_id, label, owner)
                self.group_list.append(group)
        
        # Set first turn
        first_client = random.choice(self.client_list)
        self.current_turn = first_client.name
        
        # Shuffle cards
        self.shuffle_cards()
        
        # Distribute cards
        for client in self.client_list:
            self.draw_cards(4, client)
            
        # Start playing phase
        self.game_phase = "gameplay"
                
    
    
    def gameplay_logic(self):
        
        # missing
        pass

                
                
    def handle_client(self, c, player_name):

        while True:
            
            try:
                # Receive data
                data = c.recv(4096)
                
                if data:
                    
                    # Reset sound
                    self.current_sound = None
                    
                    # Get client
                    client = next((client for client in self.client_list if client.name == player_name), None)
                    
                    # Process client action
                    action = pickle.loads(data)
                    self.process_action(action, client)

                    # Send updated game state to all clients
                    self.broadcast()
                    
            except:
                pass



    def process_action(self, action, client):
        
        # Get action type
        action_type = action.get("type")

        # Play card action
        if action_type == "play_card":
            self.play_card(action, client)
            self.current_sound = "play_card"
            
        # End player's turn
        if action_type == "end_turn":
            self.end_turn(action, client)

            
            
    def play_card(self, action, client):
        """Move cards from table to trick stack"""
        
        # Check game phase
        if self.game_phase != "gameplay":
            return
        
        # Check if it's this player's turn
        if client.name != self.current_turn:
            return
                
        # Get played card
        card_id = action.get("card_id")
        
        # Get targeted group
        target_group_id = action.get("group_id")
        
        # Find card
        played_card = None
        for card in self.card_list:
            if card.id == card_id:
                played_card = card
                break
            
        # Find group
        for group in self.group_list:
            if group.id == target_group_id:
                target_group = group
            
        # Card not found
        if played_card is None:
            return
            
        # Check if card is in player's hand
        if played_card.owner != client.name:
            return
        
        # Remove any cards from the group (if necessary)
        if played_card.type == "terrain":
            for card in self.card_list:
                if card.group_id == target_group.id:
                    card.group_id = None
                    card.location = "discard"
                    card.owner = None
            
        # Add card to the group
        played_card.location = "table"
        played_card.group_id = target_group_id
        
        # Alter group attributes
        if played_card.type == "movement":
            target_group.range += 1
            target_group.moving = True
        elif played_card.type == "terrain":
            target_group.terrain = played_card.subtype
            target_group.moving = False
            
            
            
    def end_turn(self, action, client):
        
        # Check game phase
        if self.game_phase != "gameplay":
            return
        
        # Check if it's this player's turn
        if client.name != self.current_turn:
            return
        
        # Get cards in player's hand
        hand = [card for card in self.card_list if card.location == "hand" and card.owner == client.name]
        
        # Calculate number of cards to be drawn
        n_cards = 6 - len(hand)
        
        # Refill player's hand
        self.draw_cards(n_cards, client)
        


    def remove_client(self, player_name):
        """Removes client from game"""
        
        # Remove from client list
        client = next((client for client in self.client_list if client.name == player_name), None)
        self.client_list.remove(client)
        
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
                "groups": [],
                "game_phase": self.game_phase,
                "current_turn": self.current_turn,
                "sound": self.current_sound
            }
            
            # Add card information
            for card in self.card_list:
                card_info = {
                    "card_id": card.id,
                    "owner": "player" if client.name == card.owner else "opponent",
                    "location": card.location,
                    "group_id": card.group_id
                }
                game_state["cards"].append(card_info)
                
            # Add group information
            for group in self.group_list:
                group_info = {
                    "group_id": group.id,
                    "owner": "player" if client.name == group.owner else "opponent",
                    "range": group.range,
                    "moving": group.moving,
                    "terrain": group.terrain
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
        
        
        
    def draw_cards(self, n_cards, client):
        
        # Get cards in action deck
        deck = [card for card in self.card_list if card.location == "deck"]
        
        for _ in range(n_cards):
    
            # Reshuffle if necessary
            if len(deck) == 0:
                self.shuffle_cards()
                deck = [card for card in self.card_list if card.location == "deck"]
                            
            # Draw top card
            card = deck.pop()
            card.location = "hand"
            card.owner = client.name
        
    

# ──[ Main ]───────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    server = GameServer()
    server.start_server()


