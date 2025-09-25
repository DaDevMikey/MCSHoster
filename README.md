# MCSHoster

A graphical user interface for managing a local Minecraft server on Windows.

MCSHoster simplifies the process of downloading, configuring, and running a Minecraft server. It provides tools for managing server properties, users (ops/whitelist), plugins, backups, and more, all from a user-friendly desktop application.

 <!-- TODO: Replace with a real screenshot -->

## Features

*   **Easy Setup**: Download official Vanilla server JARs directly or use your own custom JAR (Paper, Spigot, etc.).
*   **Server Configuration**: A full GUI for editing the `server.properties` file with helpful tooltips.
*   **User Management**: Easily add/remove OPs and whitelisted players.
*   **Plugin Management**: Upload, remove, enable, and disable plugins for Paper/Spigot servers.
*   **Live Console**: View the live server console, send commands, and start/stop the server.
*   **Backup & Restore**: Create and restore backups of your world folder.
*   **Scheduler**: Set up automated daily server restarts and backups.
*   **Firewall Helper**: A simple one-click button to open the default Minecraft port (25565) in Windows Firewall.

## Requirements

*   Windows 10 or newer.
*   Java (JRE or JDK) installed and available in your system's PATH.

## Installation

1.  Go to the Releases page. <!-- TODO: Update URL -->
2.  Download the latest `MCSHoster.exe` file.
3.  Place the executable in a folder of your choice and run it.

> **Note**: Some actions, like modifying the Windows Firewall, require administrator privileges. If an action fails, please try running `MCSHoster.exe` as an administrator.

## How to Use

1.  **Setup Tab**:
    *   Choose a `Server directory`. This is where all your server files will be stored.
    *   Select a `Server type`. For a standard server, choose `Vanilla`.
    *   If using Vanilla, select a version and click `Download`.
    *   If using a custom server type like Paper or Spigot, download the JAR from their website and use the `Upload custom server.jar` button.
    *   Click `Bootstrap server` to generate the initial server files (`eula.txt`, `server.properties`).
    *   Check the `Accept EULA` box.

2.  **Settings Tab**:
    *   Modify your server settings like MOTD, difficulty, and max players. Click `Save settings` when done.

3.  **Console Tab**:
    *   Click `Start` to run your server.
    *   You can now connect to your server in Minecraft at `localhost`.

## Building from Source

If you want to contribute or build the project yourself:

1.  Clone the repository:
    ```sh
    git clone https://github.com/your-username/MCSHoster.git
    cd MCSHoster
    ```
2.  Create a virtual environment and install dependencies:
    ```sh
    python -m venv .venv
    .\.venv\Scripts\activate
    pip install -r requirements.txt
    ```
3.  Run the application:
    ```sh
    python main.py
    ```

## License

This project is open-source and licensed under the MIT License. See the `LICENSE` file for details.