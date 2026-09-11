# Up Front

**Up Front** is a two-player card game published in 1983 by Avalon Hill, designed by Courtney F. Allen. It simulates infantry combat (with some AFV support) at the squad level in WWII. The game became a cult classic in wargaming circles and spawned two expansions extending it to the North African and Pacific Theater.

This Projects aims for a truthful digital adapation of the game. It is designed as a peer-to-peer experience without a central online lobby or matchmaking system. Instead, one player hosts a session locally, while the remaining players connect directly as clients, enabling private games among friends.

Launcher:

!\[launcher interface](sources/readme/launcher.png)

Gameplay:

!\[gameplay view](sources/readme/gameplay.png)

## Motivation

Existing digital adaptations either lack rule enforcement (e.g. VASSAL) or provide limited visual presentation (e.g. Battlegrounds). This project aims to combine a visually appealing UI with a complete and accurate implementation of the game rules for a smooth, satisfying Up Front experience.

## Project Structure

```
bridge/
├── assets/          # Finalized images, sounds, and media files used directly in the game
├── logic/           # Game logic and core functionality
├── sources/         # Working files (e.g. SVG files and other editable sources)
└── cardgame.py      # Main script (Client)
├── cardserver.py    # Main script (Server)
├── start\_game.bat   # Launcher (Windows Client)
└── start\_server.bat # Launcher (Windows Server)
```

## Getting Started

Open terminal (Linux/macOS) or command prompt (Windows) in the directory where you want to clone the project. Then:

### Installation (Windows)

1. Clone the repository:

```bash
   git clone https://github.com/Ultimatthi/bridge-delta-null
   cd bridge-delta-null
   ```

2. Start either of the provided batch files:

   * `start\_server.bat`
   * `start\_game.bat`

   The scripts automatically create a local Python virtual environment and install all required dependencies. Once the setup is complete, they launch the server or the game, respectively (see section "Running the Game").

### Installation (Linux / macOS / manual installation):

1. Clone the repository:

```bash
   git clone https://github.com/Ultimatthi/bridge-delta-null
   cd bridge-delta-null
   ```

2. Install a Python runtime environment (version 3.10 or newer): [https://www.python.org/](https://www.python.org/)
3. Install required dependencies:

```bash
   pip install -r requirements.txt
   ```

### Network Setup

* **Local network (LAN)**: Players can connect directly using the host's local IP address
* **Online play**: The host must configure port forwarding on their router (default port: 55556)
* **Alternative**: Use virtual LAN solutions like Hamachi or ZeroTier

### Running the Game

1. Start the server (only 1 player, acting as host):

```bash
   python cardserver.py
```

2. Start the client (all 4 players, including the host):

```bash
   python cardgame.py
```

3. Join the game session by connecting to the server at `<host-ip>:<port>`

   * For online play: Use the host's public IP address (e.g., "88.214.164.224:55556")
   * For local network: Use the host's local IP address (e.g., "192.168.1.50:55556")
   * For singleplayer (and 3 bots): Use localhost (e.g., "localhost:55556")

## License

This project is licensed under the MIT License — see the LICENSE file for details.

## Credits

This project uses or builds upon the following open-source projects:

* **Arcade** – Python game development library  
https://api.arcade.academy/en/stable/
* **Endplay** – Bridge toolkit with Double Dummy Solver support  
https://github.com/dominicprice/endplay
* **SAYCBridge** – Standard American Yellow Card (SAYC) bidding engine  
https://github.com/eseidel/saycbridge

## Contributing

Contributions, bug reports, and feature suggestions are welcome!

\---

*Made with ❤️ using Python and Arcade.*

