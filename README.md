<div align=center>
<img src="db6.png" alt="Logo" width="512"/>
  
### Welcome to Database|6!
**Database|6** is a simple Database tracker for OldR6 builds, tools, cheats and more! 

![License](https://img.shields.io/badge/license-MIT-blue)
![Made with Python](https://img.shields.io/badge/made%20with-Python-3776AB)
![Designed for R6](https://img.shields.io/badge/classic-Rainbow%20Six-fcc200)
</div>

# Getting Started
# You can get **Database|6** from [Releases](https://github.com/Wiilly-i-am/database6/releases)
> [!NOTE]
> This is the first release. There may be bugs.

To get started, Import a Database by Navigating to Settings > Import Database, or Add an entry.

If the entries freeze or you wish to delete all current entries, you can go to Settings > Force Clear (no confirm) or, Settings > Refresh Entries.

If you make a new database, it is possible to export it by navigating to Settings > Export Database.




> [!WARNING]
> For Developers and Advanced Users only,
> 
> You can build directly from source using the following powershell command
> 
> ```pyinstaller --onefile --windowed --icon="db6.ico" --add-data "db6.png;." --add-data "db6.ico;." db.py```
> 
> You might need to install pyinstaller with
> 
> ```pip install pyinstaller```


> [!IMPORTANT]
> The app includes a migration routine which attempts to map and preserve columns when importing older or slightly different databases. It:
> - matches column names case-insensitively and by a normalized form (alphanumeric only)
> - supports aliases (e.g., `manifestid` → `manifest_id`, `md5sum` → `md5`)
> - recreates tables and copies mapped data when automatic column-add isn't sufficient
> Important: migrations can drop unmapped columns. Back up your DB before import if data is important.








