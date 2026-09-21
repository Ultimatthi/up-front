# Up Front

**Up Front** is a two-player card game published in 1983 by Avalon Hill, designed by Courtney F. Allen. It simulates WWII infantry combat (with some armored fighting vehicle support) at the squad level. The game became a cult classic in wargaming circles and spawned two expansions extending it to the North African and Pacific Theaters.

Existing digital adaptations either lack rule enforcement or provide limited visual presentation. This project aims to combine a visually appealing UI with a faithful and complete implementation of the game rules for a smooth, satisfying Up Front experience.

It is designed as a peer-to-peer experience without a central online lobby or matchmaking system. Instead, one player hosts a session locally, while the other player connects directly as a client, enabling private games among friends.

**Launcher:**

![launcher interface](sources/readme/launcher.png)

**Gameplay:**

![gameplay view](sources/readme/gameplay.png)

## Status

This project is in early development and not yet fully playable.
Currently, work is focused on implementing Scenario A of the base game.

Expect missing rules and bugs until the first stable release.

## Project Structure

```text
up-front/
├── assets/            # Finalized images, sounds, and media files used directly in the game
├── logic/             # Game logic and core functionality
├── sources/           # Working files (e.g. SVG files and other editable sources)
├── cardgame.py        # Main script (Client)
├── cardserver.py      # Main script (Server)
├── requirements.txt   # Python dependencies
├── LICENSE            # MIT License
└── README.md
```

## Getting Started

Open a terminal (Linux/macOS) or command prompt (Windows) in the directory where you want to clone the project. Then:

1. Clone the repository:

   ```bash
   git clone https://github.com/Ultimatthi/up-front
   cd up-front
   ```

2. Install a Python runtime environment (version 3.11 or newer): <https://www.python.org/>

3. Install required dependencies:

   ```bash
   pip install -r requirements.txt
   ```

   On Linux/macOS you may need to use `python3` and `pip3` instead of `python` and `pip`.

## Network Setup

* **Local network (LAN)**: Players can connect directly using the host's local IP address
* **Online play**: The host must configure port forwarding on their router (default port: 52000) and allow the port in their firewall
* **Alternative**: Use virtual LAN solutions like [ZeroTier](https://www.zerotier.com)

## Running the Game

1. Start the server (only 1 player, acting as host):

   ```bash
   python cardserver.py
   ```

2. Start the client (both players, including the host):

   ```bash
   python cardgame.py
   ```

3. Join the game session by connecting to the server at `<host-ip>:<port>`

   * For online play: Use the host's public IP address (e.g., `203.0.113.42:52000`)
   * For local network: Use the host's local IP address (e.g., `192.168.1.10:52000`)
   * For singleplayer, or as the host yourself: Use localhost (e.g., `localhost:52000`)

## License

The source code of this project is licensed under the MIT License. See the [LICENSE](LICENSE) file for details.

## Credits

This project uses or builds upon the following:

* **Arcade** – Open-source Python game development library.

* **Up Front** – Original card game by Courtney F. Allen, published by
  Avalon Hill (1983). This project is an unofficial, non-commercial
  fan adaptation and is not affiliated with or endorsed by Avalon Hill
  or Hasbro. All rights to the original game belong to their respective owners.

## Contributing

Contributions, bug reports, and feature suggestions are welcome!

---

*Made with ❤️ using Python and Arcade.*