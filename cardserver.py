"""
Bridge: Server
"""

import socket
import threading
import pickle
import time
import random


# ──[ Parameter ]──────────────────────────────────────────────────────────────

FPS = 20
FULL_TABLE = 2


# ──[ Classes ]────────────────────────────────────────────────────────────────

class ServerCard:
    """ Simplified card for server logics """
    
    def __init__(self, card_id, card_type, value, owner, location):

        self.id = card_id
        self.type = card_type
        self.value = value
        self.owner = owner # player_name
        self.location = location # deck, discarded, removed, hand, table
        
        
        
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
        self.game_phase = "assembling"
        self.broadcast_timer = 0.0
        self.client_list = []
        self.current_turn = "north"
        self.current_sound = None
        
        # Sprite list with all the cards
        self.card_list = []
        
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
        
        # Create every card
        for i in range(19,27):
            card_id = f"ac{i:02d}"
            card = ServerCard(card_id, None, None, None, "deck")
            self.card_list.append(card)
        
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
        
        if self.game_phase == "assembling":
            self.assembling_logic()
            
        if self.game_phase == "playing":
            self.playing_logic()
            
            
            
    def assembling_logic(self):
        
        # missing
        pass
        
        
        
    def playing_logic(self):
        
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

            
            
    def play_card(self, action, client):
        """Move cards from table to trick stack"""
        
        # missing
        pass
        


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
                "game_phase": self.game_phase,
                "current_turn": self.current_turn,
            }
            
            # Add card information with appropriate visibility
            for card in self.card_list:
                card_info = {
                    "card_id": card.id,
                    "owner": card.owner,
                    "location": card.location
                }
                game_state["cards"].append(card_info)
            
            # Send game state to client
            try:
                size = pickle.dumps(game_state)
                print(f"Sending game state ({len(size)} bytes)")
                client.socket.sendall(pickle.dumps(game_state))
            except Exception:
                print(f"Error sending to {client.name}")
                self.remove_client(client.name)



# ──[ Main ]───────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    server = GameServer()
    server.start_server()


